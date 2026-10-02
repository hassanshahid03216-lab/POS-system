"""Local browser-based ShopFlow POS. Run with: python web_app.py"""

from __future__ import annotations

import json
import secrets
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_file, session, url_for)

from app_settings import load_settings, save_settings
from db import db
from services.receipts import available_printers, print_or_save_receipt, test_printer


app = Flask(__name__)
settings = load_settings()
if not settings.get("web_secret"):
    settings["web_secret"] = secrets.token_hex(32)
    save_settings(settings)
app.secret_key = settings["web_secret"]
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
printer_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shopflow-printer")


def signed_in(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_only(view):
    @wraps(view)
    @signed_in
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(24)
    return session["csrf_token"]


@app.context_processor
def inject_layout_values():
    return {"shop_name": load_settings().get("shop_name", "ShopFlow POS"), "csrf_token": csrf_token}


@app.before_request
def protect_post_forms():
    if request.method == "POST":
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            abort(400, "The form expired. Reload the page and try again.")


@app.route("/", methods=("GET", "POST"))
def login():
    if "user_id" in session:
        return redirect(url_for("billing"))
    first_run = db.user_count() == 0
    if request.method == "POST":
        action = request.form.get("action", "login")
        pin = request.form.get("pin", "")
        if action == "setup" and first_run:
            name = request.form.get("name", "").strip()
            confirm = request.form.get("confirm_pin", "")
            if not name or pin != confirm:
                flash("Enter a name and matching PINs.", "error")
            else:
                try:
                    db.create_user_with_pin(name, "admin", pin)
                    flash("Owner account created. Sign in with the new PIN.", "success")
                except ValueError as error:
                    flash(str(error), "error")
            return redirect(url_for("login"))
        user = db.authenticate_pin(pin)
        if user:
            session.clear()
            session.update(user_id=user["id"], name=user["name"], role=user["role"])
            return redirect(url_for("billing"))
        flash("PIN not recognized. Enter your 4 to 8 digit PIN.", "error")
    return render_template("login.html", first_run=first_run)


@app.post("/logout")
@signed_in
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/billing")
@signed_in
def billing():
    products = db.list_products()
    held = db.list_held_bills()
    return render_template("billing.html", products=products, held_bills=held)


@app.post("/checkout")
@signed_in
def checkout():
    try:
        cart = json.loads(request.form.get("cart", "[]"))
        bill_discount = float(request.form.get("bill_discount", 0))
        payment = request.form.get("payment_mode", "Cash")
        products = {p["id"]: p for p in db.list_products()}
        receipt_items = []
        subtotal = 0.0
        for item in cart:
            product = products.get(int(item["id"]))
            if product is None:
                raise ValueError("A product in this bill no longer exists.")
            entry = {"id": int(item["id"]), "name": product["name"], "qty": int(item["qty"]),
                     "unit_price": float(item["unit_price"]), "discount": float(item.get("discount", 0))}
            subtotal += entry["qty"] * entry["unit_price"]
            receipt_items.append(entry)
        held_id = session.get("held_bill_id")
        sale = db.checkout_sale(receipt_items, payment, bill_discount, held_id)
        session.pop("held_bill_id", None)
        receipt = {"sale_id": sale["sale_id"], "timestamp": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "items": receipt_items, "subtotal": subtotal, "discount": sale["discount"],
                   "total": sale["total"], "payment_mode": payment}
        printer_pool.submit(print_or_save_receipt, receipt)
        flash(f"Sale #{sale['sale_id']} completed — Rs {sale['total']:,.2f}. Receipt is printing or saving.", "success")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        flash(str(error), "error")
        return redirect(url_for("billing"))
    return redirect(url_for("billing"))


@app.post("/hold")
@signed_in
def hold_bill():
    try:
        payload = {"items": json.loads(request.form.get("cart", "[]")),
                   "bill_discount": float(request.form.get("bill_discount", 0)),
                   "payment_mode": request.form.get("payment_mode", "Cash")}
        if not payload["items"]:
            raise ValueError("Add products before holding a bill.")
        held_id = db.save_held_bill(payload, session.get("held_bill_id"))
        session.pop("held_bill_id", None)
        flash("Bill held. Start another sale or resume it when ready.", "success")
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        flash(str(error), "error")
    return redirect(url_for("billing"))


@app.post("/resume/<int:held_id>")
@signed_in
def resume_bill(held_id):
    payload = db.get_held_bill(held_id)
    if payload is None:
        flash("That held bill is no longer available.", "error")
    else:
        session["held_bill_id"] = held_id
        session["resume_bill"] = payload
        flash("Held bill loaded. Review quantities and prices before checkout.", "success")
    return redirect(url_for("billing"))


@app.route("/products", methods=("GET", "POST"))
@admin_only
def products():
    if request.method == "POST":
        try:
            values = _product_form_values()
            db.create_product(*values)
            flash("Product added.", "success")
        except Exception as error:
            flash("Could not add product: " + _product_error(error), "error")
        return redirect(url_for("products"))
    return render_template("products.html", products=db.list_products(), editing=None)


@app.route("/products/<int:product_id>/edit", methods=("GET", "POST"))
@admin_only
def edit_product(product_id):
    product = db.get_product(product_id)
    if product is None:
        abort(404)
    if request.method == "POST":
        try:
            db.update_product(product_id, *_product_form_values())
            flash("Product updated.", "success")
            return redirect(url_for("products"))
        except Exception as error:
            flash("Could not update product: " + _product_error(error), "error")
    return render_template("products.html", products=db.list_products(), editing=product)


@app.post("/products/<int:product_id>/delete")
@admin_only
def delete_product(product_id):
    try:
        db.delete_product(product_id)
        flash("Product deleted.", "success")
    except Exception as error:
        flash(f"Could not delete product: {error}", "error")
    return redirect(url_for("products"))


def _product_form_values():
    name = request.form.get("name", "").strip()
    barcode = request.form.get("barcode", "").strip() or None
    cost = float(request.form.get("cost_price", 0))
    sale = float(request.form.get("sale_price", 0))
    qty = int(request.form.get("stock_qty", 0))
    category = request.form.get("category", "").strip() or None
    threshold = int(request.form.get("low_stock_threshold", 5))
    if not name or sale <= 0 or cost < 0 or qty < 0 or threshold < 0:
        raise ValueError("Name and a positive sale price are required; quantities and prices cannot be negative.")
    return name, barcode, cost, sale, qty, category, threshold


def _product_error(error):
    if "UNIQUE constraint failed: products.barcode" in str(error):
        return "that barcode is already assigned to another product."
    return str(error)


@app.route("/insights")
@admin_only
def insights():
    period = request.args.get("period", "week")
    data = db.get_dashboard_insights(period)
    return render_template("insights.html", data=data, period=period,
                           summary=data["summary"])


@app.route("/settings", methods=("GET", "POST"))
@admin_only
def admin_settings():
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "add_user":
                db.create_user_with_pin(request.form.get("name", ""), request.form.get("role", "cashier"),
                                        request.form.get("pin", ""))
                flash("User added.", "success")
            elif action == "printer":
                values = load_settings()
                values["shop_name"] = request.form.get("shop_name", "").strip() or "ShopFlow POS"
                values["printer_name"] = request.form.get("printer_name", "")
                save_settings(values)
                flash("Printer settings saved.", "success")
            elif action == "test_printer":
                printer_pool.submit(test_printer, request.form.get("printer_name", ""))
                flash("Printer test sent in the background.", "success")
            elif action == "backup":
                folder = request.form.get("backup_dir", "").strip()
                if not folder:
                    folder = str(Path.home() / "Documents" / "ShopFlow POS" / "Backups")
                values = load_settings()
                values["backup_dir"] = folder
                save_settings(values)
                path = db.backup_database(folder)
                flash(f"Backup saved: {path}", "success")
        except Exception as error:
            flash(str(error), "error")
        return redirect(url_for("admin_settings"))
    try:
        printers = available_printers()
        printer_error = ""
    except Exception as error:
        printers, printer_error = [], str(error)
    return render_template("settings.html", users=db.list_users(), settings=load_settings(),
                           printers=printers, printer_error=printer_error)


@app.post("/settings/backup")
@admin_only
def download_backup():
    folder = request.form.get("backup_dir", "").strip()
    if not folder:
        folder = str(Path.home() / "Documents" / "ShopFlow POS" / "Backups")
    values = load_settings()
    values["backup_dir"] = folder
    save_settings(values)
    path = db.backup_database(folder)
    flash(f"Backup saved: {path}", "success")
    return redirect(url_for("admin_settings"))


@app.post("/settings/export")
@admin_only
def export_csv():
    start, end = request.form.get("start_date", ""), request.form.get("end_date", "")
    if not start or not end or start > end:
        flash("Choose a valid date range.", "error")
        return redirect(url_for("admin_settings"))
    folder = Path(tempfile.gettempdir()) / "ShopFlowPOS" / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"sales_{start}_to_{end}.csv"
    db.export_sales_csv(str(path), start, end)
    return send_file(path, as_attachment=True, download_name=path.name, mimetype="text/csv")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", message="Admin access is required for that page."), 403


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", message=getattr(error, "description", "Please reload and try again.")), 400


def main():
    db.init_db()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
