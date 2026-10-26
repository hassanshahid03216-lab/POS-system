import sqlite3
import os
import json
import hashlib
import hmac
import secrets
import csv
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ShopFlowPOS"
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = str(APP_DATA_DIR / "pos.db")
else:
    DB_PATH = os.path.join(BASE_DIR, "pos.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # Enable WAL for better concurrent read/write performance
    conn.execute("PRAGMA journal_mode=WAL")
    # Enforce foreign key constraints (SQLite ignores them by default)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            barcode TEXT UNIQUE,
            cost_price REAL DEFAULT 0,
            sale_price REAL NOT NULL,
            stock_qty INTEGER DEFAULT 0,
            category TEXT,
            low_stock_threshold INTEGER DEFAULT 5
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            cashier_id INTEGER,
            customer_id INTEGER,
            total REAL NOT NULL DEFAULT 0,
            discount REAL DEFAULT 0,
            payment_mode TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sale_items (
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            discount REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (sale_id, product_id),
            FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'cashier')),
            pin_hash TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('restock', 'sale', 'adjustment', 'return')),
            qty INTEGER NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS held_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            payload TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            balance REAL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS customer_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            sale_id INTEGER,
            type TEXT NOT NULL CHECK(type IN ('sale', 'payment', 'return')),
            amount REAL NOT NULL,
            notes TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sale_returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            refund_amount REAL NOT NULL,
            notes TEXT,
            FOREIGN KEY (sale_id) REFERENCES sales(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sale_return_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            return_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            refund_price REAL NOT NULL,
            FOREIGN KEY (return_id) REFERENCES sale_returns(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    cur.execute("""CREATE TABLE IF NOT EXISTS cash_closings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, cashier_id INTEGER,
        cashier_name TEXT NOT NULL, opening REAL NOT NULL, expected REAL NOT NULL,
        actual REAL NOT NULL, discrepancy REAL NOT NULL, notes TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS cash_shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cashier_id INTEGER, cashier_name TEXT NOT NULL,
        opening REAL NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS cash_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL, notes TEXT, cashier_id INTEGER,
        timestamp TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, company TEXT, phone TEXT,
        address TEXT, balance_owed REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id INTEGER NOT NULL, invoice_no TEXT,
        timestamp TEXT NOT NULL, total_amount REAL NOT NULL, paid_amount REAL NOT NULL DEFAULT 0,
        payment_status TEXT NOT NULL, FOREIGN KEY(supplier_id) REFERENCES suppliers(id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS purchase_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, purchase_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
        qty INTEGER NOT NULL, unit_cost REAL NOT NULL, FOREIGN KEY(purchase_id) REFERENCES purchases(id),
        FOREIGN KEY(product_id) REFERENCES products(id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS supplier_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id INTEGER NOT NULL, purchase_id INTEGER,
        type TEXT NOT NULL CHECK(type IN ('purchase','payment','return')), amount REAL NOT NULL,
        notes TEXT, timestamp TEXT NOT NULL, FOREIGN KEY(supplier_id) REFERENCES suppliers(id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS return_vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, return_id INTEGER NOT NULL UNIQUE,
        code TEXT NOT NULL UNIQUE, amount REAL NOT NULL, remaining REAL NOT NULL,
        created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS return_stock_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT, return_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('restock','damaged_return','write_off')),
        qty INTEGER NOT NULL, timestamp TEXT NOT NULL)""")

    for table, column, definition in (
        ("sale_returns", "refund_method", "TEXT NOT NULL DEFAULT 'Cash'"),
        ("sale_returns", "customer_id", "INTEGER"),
        ("sale_returns", "voucher_code", "TEXT"),
        ("customer_transactions", "payment_method", "TEXT NOT NULL DEFAULT 'Cash'"),
        ("sales", "exchange_credit", "REAL NOT NULL DEFAULT 0"),
        ("sales", "voucher_code", "TEXT"),
    ):
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    stock_sql = cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='stock_movements'").fetchone()[0]
    if "damaged_return" not in stock_sql:
        cur.execute("ALTER TABLE stock_movements RENAME TO stock_movements_old")
        cur.execute("""CREATE TABLE stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('restock','sale','adjustment','return','damaged_return','write_off')),
            qty INTEGER NOT NULL, timestamp TEXT NOT NULL)""")
        cur.execute("INSERT INTO stock_movements SELECT * FROM stock_movements_old")
        cur.execute("DROP TABLE stock_movements_old")

    sale_cols = {row[1] for row in cur.execute("PRAGMA table_info(sales)")}
    if "customer_id" not in sale_cols:
        cur.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER")

    item_cols = {row[1] for row in cur.execute("PRAGMA table_info(sale_items)")}
    if "discount" not in item_cols:
        cur.execute("ALTER TABLE sale_items ADD COLUMN discount REAL NOT NULL DEFAULT 0")

    # Seed default Admin account (PIN: 1234) if no users exist
    user_cnt = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_cnt == 0:
        default_hash = hash_pin("1234")
        cur.execute("INSERT INTO users (name, role, pin_hash) VALUES (?, ?, ?)", ("Admin", "admin", default_hash))

    conn.commit()
    conn.close()


def checkout_sale(items, payment_mode, bill_discount=0, held_bill_id=None, customer_id=None,
                  exchange_credit=0, voucher_code=None):
    valid_modes = ("Cash", "Card", "JazzCash", "EasyPaisa", "Credit / Khata")
    if payment_mode not in valid_modes:
        raise ValueError(f"Choose a valid payment mode: {', '.join(valid_modes)}.")
    if not items:
        raise ValueError("The cart is empty.")
    if payment_mode == "Credit / Khata" and not customer_id:
        raise ValueError("Please select a Customer for Credit / Khata payment.")

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        prepared = []
        subtotal = 0.0
        item_discounts = 0.0
        for item in items:
            qty = int(item["qty"])
            price = float(item["unit_price"])
            discount = float(item.get("discount", 0))
            if qty <= 0 or price < 0 or discount < 0 or discount > qty * price:
                raise ValueError("A quantity, price, or item discount is invalid.")
            row = conn.execute("SELECT name, stock_qty FROM products WHERE id = ?", (item["id"],)).fetchone()
            if row is None:
                raise ValueError("A product in this bill no longer exists.")
            if int(row["stock_qty"]) < qty:
                raise ValueError(f"Not enough stock for {row['name']} (available: {row['stock_qty']}).")
            line_total = qty * price
            subtotal += line_total
            item_discounts += discount
            prepared.append((int(item["id"]), qty, price, discount))
            
        bill_discount = float(bill_discount)
        if bill_discount < 0 or bill_discount > subtotal - item_discounts:
            raise ValueError("Bill discount cannot exceed the remaining total.")
        total_discount = item_discounts + bill_discount
        total = subtotal - total_discount
        exchange_credit = float(exchange_credit)
        if exchange_credit < 0 or exchange_credit > total + 0.005:
            raise ValueError("Voucher credit cannot exceed the bill total.")
        if exchange_credit > 0:
            voucher = conn.execute("SELECT remaining FROM return_vouchers WHERE code=?", (voucher_code,)).fetchone()
            if not voucher or exchange_credit > float(voucher["remaining"]) + 0.005:
                raise ValueError("The voucher is invalid, already used, or has insufficient balance.")
            conn.execute("UPDATE return_vouchers SET remaining=remaining-? WHERE code=?", (exchange_credit, voucher_code))
        elif voucher_code:
            raise ValueError("Select a voucher credit amount before checkout.")
        amount_due = max(0.0, total - exchange_credit)
        timestamp = datetime.now().isoformat(timespec="seconds")
        
        cursor = conn.execute(
            "INSERT INTO sales (timestamp, customer_id, total, discount, payment_mode, exchange_credit, voucher_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (timestamp, customer_id, total, total_discount, payment_mode, exchange_credit, voucher_code),
        )
        sale_id = cursor.lastrowid
        
        for product_id, qty, price, discount in prepared:
            conn.execute(
                "INSERT INTO sale_items (sale_id, product_id, qty, unit_price, discount) VALUES (?, ?, ?, ?, ?)",
                (sale_id, product_id, qty, price, discount),
            )
            changed = conn.execute(
                "UPDATE products SET stock_qty = stock_qty - ? WHERE id = ? AND stock_qty >= ?",
                (qty, product_id, qty),
            ).rowcount
            if changed != 1:
                raise ValueError("Stock changed while this bill was being checked out. Please review the cart.")
            conn.execute(
                "INSERT INTO stock_movements (product_id, type, qty, timestamp) VALUES (?, 'sale', ?, ?)",
                (product_id, -qty, timestamp),
            )
            
        if customer_id and payment_mode == "Credit / Khata":
            conn.execute("UPDATE customers SET balance = balance + ? WHERE id = ?", (amount_due, customer_id))
            conn.execute(
                "INSERT INTO customer_transactions (customer_id, sale_id, type, amount, notes, timestamp) VALUES (?, ?, 'sale', ?, ?, ?)",
                (customer_id, sale_id, amount_due, f"Bill #{sale_id} on credit", timestamp)
            )
            
        if held_bill_id is not None:
            conn.execute("DELETE FROM held_bills WHERE id = ?", (int(held_bill_id),))
            
        conn.commit()
        return {"sale_id": sale_id, "total": total, "amount_due": amount_due,
                "discount": total_discount, "exchange_credit": exchange_credit, "voucher_code": voucher_code}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_held_bill(payload, held_bill_id=None):
    conn = get_connection()
    try:
        timestamp = datetime.now().isoformat(timespec="seconds")
        label = ", ".join(f"{item['name']} × {item['qty']}" for item in payload.get("items", []))[:120]
        label = label or "Empty bill"
        encoded = json.dumps(payload)
        if held_bill_id is None:
            cursor = conn.execute("INSERT INTO held_bills (label, payload, timestamp) VALUES (?, ?, ?)",
                                  (label, encoded, timestamp))
            result = cursor.lastrowid
        else:
            conn.execute("UPDATE held_bills SET label = ?, payload = ?, timestamp = ? WHERE id = ?",
                         (label, encoded, timestamp, int(held_bill_id)))
            result = int(held_bill_id)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_held_bills():
    conn = get_connection()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT id, label, timestamp FROM held_bills ORDER BY id DESC").fetchall()]
    finally:
        conn.close()


def get_held_bill(held_bill_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT payload FROM held_bills WHERE id = ?", (held_bill_id,)).fetchone()
        return json.loads(row["payload"]) if row else None
    finally:
        conn.close()


def list_recent_sales(limit=50):
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT s.id, s.timestamp, s.total, s.discount, s.payment_mode,
                   COALESCE(c.name, 'Walk-in Customer') AS customer_name,
                   COUNT(si.product_id) AS item_count,
                   COALESCE((SELECT SUM(sr.refund_amount) FROM sale_returns sr WHERE sr.sale_id = s.id), 0) AS refunded_amount
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            LEFT JOIN sale_items si ON si.sale_id = s.id
            GROUP BY s.id
            ORDER BY s.id DESC LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["original_total"] = float(d["total"])
            d["refunded_amount"] = float(d.get("refunded_amount") or 0)
            d["net_total"] = max(0.0, d["original_total"] - d["refunded_amount"])
            d["total"] = d["net_total"]
            result.append(d)
        return result
    finally:
        conn.close()


def get_sale_for_return(sale_id):
    conn = get_connection()
    try:
        sale = conn.execute("""
            SELECT s.id, s.timestamp, s.total, s.discount, s.payment_mode, s.customer_id,
                   COALESCE(c.name, 'Walk-in Customer') AS customer_name
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            WHERE s.id = ?
        """, (sale_id,)).fetchone()
        if not sale:
            return None
        items = conn.execute("""
            SELECT si.product_id, p.name, p.barcode, si.qty, si.unit_price, si.discount,
                   COALESCE(SUM(sri.qty), 0) AS already_returned,
                   COALESCE(SUM(sri.qty * sri.refund_price), 0) AS already_refunded
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            LEFT JOIN sale_returns sr ON sr.sale_id = si.sale_id
            LEFT JOIN sale_return_items sri ON sri.return_id = sr.id AND sri.product_id = si.product_id
            WHERE si.sale_id = ?
            GROUP BY si.product_id
        """, (sale_id,)).fetchall()
        
        return {
            "sale": dict(sale),
            "items": [dict(it) for it in items]
        }
    finally:
        conn.close()


def process_sale_return(sale_id, returned_items, notes="", refund_method="Cash", restock=True):
    if not returned_items:
        raise ValueError("No items selected for return.")
        
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        sale = conn.execute("SELECT customer_id, payment_mode, discount FROM sales WHERE id = ?", (sale_id,)).fetchone()
        if not sale:
            raise ValueError("Sale record not found.")
        if refund_method not in ("Cash", "Credit / Khata Adjustment", "Store Credit Voucher", "Exchange Credit"):
            raise ValueError("Choose a valid refund method.")
        if refund_method == "Credit / Khata Adjustment" and not sale["customer_id"]:
            raise ValueError("This sale has no linked customer for a Khata adjustment.")
            
        timestamp = datetime.now().isoformat(timespec="seconds")
        total_refund = 0.0
        lines = {}
        item_discount_total = 0.0
        sale_subtotal = 0.0
        for row in conn.execute("SELECT product_id,qty,unit_price,discount FROM sale_items WHERE sale_id=?", (sale_id,)):
            gross = int(row["qty"]) * float(row["unit_price"])
            line_discount = min(gross, float(row["discount"] or 0))
            lines[int(row["product_id"])] = {"qty": int(row["qty"]), "price": float(row["unit_price"]),
                                             "discount": line_discount, "net": gross - line_discount}
            sale_subtotal += gross
            item_discount_total += line_discount
        net_before_bill_discount = max(0.0, sale_subtotal - item_discount_total)
        bill_discount = min(net_before_bill_discount, max(0.0, float(sale["discount"] or 0) - item_discount_total))
        for item in returned_items:
            qty = int(item["qty"])
            sold = lines.get(int(item["product_id"]))
            already = conn.execute("""SELECT COALESCE(SUM(sri.qty),0) AS qty,
                                           COALESCE(SUM(sri.qty * sri.refund_price),0) AS refunded
                                    FROM sale_return_items sri
                                    JOIN sale_returns sr ON sr.id=sri.return_id
                                    WHERE sr.sale_id=? AND sri.product_id=?""",
                                   (sale_id, int(item["product_id"]))).fetchone()
            already_qty = int(already["qty"])
            remaining_qty = sold["qty"] - already_qty if sold else 0
            if qty <= 0 or not sold or qty > remaining_qty:
                raise ValueError("Return quantity exceeds the quantity available on the original sale.")
            sale_line_refund = sold["net"]
            if net_before_bill_discount:
                sale_line_refund -= bill_discount * sold["net"] / net_before_bill_discount
            refund_remaining = max(0.0, sale_line_refund - float(already["refunded"]))
            # Guard against zero-division if remaining_qty is 0 due to concurrent updates
            item["refund_amount"] = refund_remaining * qty / max(1, remaining_qty)
            item["unit_price"] = item["refund_amount"] / max(1, qty)
        
        for item in returned_items:
            qty = int(item["qty"])
            total_refund += float(item["refund_amount"])
            
        if total_refund <= 0:
            raise ValueError("Total refund amount must be greater than zero.")
            
        voucher_code = None
        if refund_method in ("Store Credit Voucher", "Exchange Credit"):
            voucher_code = secrets.token_hex(4).upper()
        cur = conn.execute(
            "INSERT INTO sale_returns (sale_id, timestamp, refund_amount, notes, refund_method, customer_id, voucher_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sale_id, timestamp, total_refund, notes, refund_method, sale["customer_id"], voucher_code)
        )
        return_id = cur.lastrowid
        
        for item in returned_items:
            pid = int(item["product_id"])
            qty = int(item["qty"])
            price = float(item["unit_price"])
            if qty <= 0:
                continue
            conn.execute(
                "INSERT INTO sale_return_items (return_id, product_id, qty, refund_price) VALUES (?, ?, ?, ?)",
                (return_id, pid, qty, price)
            )
            disposition = "restock" if restock else "damaged_return"
            if restock:
                conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (qty, pid))
            conn.execute("INSERT INTO stock_movements (product_id, type, qty, timestamp) VALUES (?, ?, ?, ?)",
                         (pid, disposition, qty, timestamp))
            conn.execute("INSERT INTO return_stock_movements (return_id, product_id, type, qty, timestamp) VALUES (?, ?, ?, ?, ?)",
                         (return_id, pid, disposition, qty, timestamp))
            
        if refund_method == "Credit / Khata Adjustment":
            conn.execute("UPDATE customers SET balance = balance - ? WHERE id = ?", (total_refund, sale["customer_id"]))
            conn.execute(
                "INSERT INTO customer_transactions (customer_id, sale_id, type, amount, notes, timestamp) VALUES (?, ?, 'return', ?, ?, ?)",
                (sale["customer_id"], sale_id, -total_refund, f"Refund for Return #{return_id} (Sale #{sale_id})", timestamp)
            )
        elif voucher_code:
            conn.execute("INSERT INTO return_vouchers (return_id, code, amount, remaining, created_at) VALUES (?, ?, ?, ?, ?)",
                         (return_id, voucher_code, total_refund, total_refund, timestamp))
            
        conn.commit()
        return {"return_id": return_id, "refund_amount": total_refund, "timestamp": timestamp,
                "refund_method": refund_method, "voucher_code": voucher_code}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def return_voucher_balance(code):
    conn = get_connection()
    try:
        row = conn.execute("SELECT remaining FROM return_vouchers WHERE code=?", (str(code).strip().upper(),)).fetchone()
        return float(row["remaining"]) if row and float(row["remaining"]) > 0 else 0.0
    finally:
        conn.close()


def list_customers():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM customers ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_customer(customer_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_customer(name, phone="", address=""):
    if not name.strip():
        raise ValueError("Customer name is required.")
    conn = get_connection()
    try:
        timestamp = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            "INSERT INTO customers (name, phone, address, balance, created_at) VALUES (?, ?, ?, 0, ?)",
            (name.strip(), phone.strip(), address.strip(), timestamp)
        )
        cid = cur.lastrowid
        conn.commit()
        return cid
    finally:
        conn.close()


def update_customer(customer_id, name, phone="", address=""):
    if not name.strip():
        raise ValueError("Customer name is required.")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE customers SET name = ?, phone = ?, address = ? WHERE id = ?",
            (name.strip(), phone.strip(), address.strip(), customer_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_customer(customer_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT balance FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if row and abs(float(row["balance"])) > 0.005:
            raise ValueError(
                f"Customer has a balance of Rs {float(row['balance']):,.2f}. "
                "Clear the balance before deleting this customer."
            )
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        conn.commit()
    finally:
        conn.close()


def get_customer_ledger(customer_id):
    conn = get_connection()
    try:
        customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not customer:
            return None
        transactions = conn.execute("""
            SELECT id, sale_id, type, amount, notes, timestamp
            FROM customer_transactions
            WHERE customer_id = ?
            ORDER BY id DESC
        """, (customer_id,)).fetchall()
        return {
            "customer": dict(customer),
            "transactions": [dict(t) for t in transactions]
        }
    finally:
        conn.close()


def record_customer_payment(customer_id, amount, notes="Payment received", payment_method="Cash"):
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        timestamp = datetime.now().isoformat(timespec="seconds")
        conn.execute("UPDATE customers SET balance = balance - ? WHERE id = ?", (amount, customer_id))
        cur = conn.execute(
            "INSERT INTO customer_transactions (customer_id, type, amount, notes, timestamp, payment_method) VALUES (?, 'payment', ?, ?, ?, ?)",
            (customer_id, -amount, notes, timestamp, payment_method)
        )
        tx_id = cur.lastrowid
        conn.commit()
        return tx_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_dashboard_insights(period="week"):
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    starts = {"today": today, "week": week, "month": month}
    if period not in starts:
        period = "week"
        
    now_text = now.isoformat(timespec="seconds")
    today_text = today.isoformat(timespec="seconds")
    week_text = week.isoformat(timespec="seconds")
    month_text = month.isoformat(timespec="seconds")
    conn = get_connection()
    try:
        summary = conn.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN s.timestamp >= ? AND s.timestamp <= ? THEN s.total ELSE 0 END), 0) AS today_sales,
              COALESCE(SUM(CASE WHEN s.timestamp >= ? AND s.timestamp <= ? THEN s.total - COALESCE(c.cost, 0) ELSE 0 END), 0) AS today_profit,
              COALESCE(SUM(CASE WHEN s.timestamp >= ? AND s.timestamp <= ? THEN s.total ELSE 0 END), 0) AS week_sales,
              COALESCE(SUM(CASE WHEN s.timestamp >= ? AND s.timestamp <= ? THEN s.total - COALESCE(c.cost, 0) ELSE 0 END), 0) AS week_profit,
              COALESCE(SUM(CASE WHEN s.timestamp >= ? AND s.timestamp <= ? THEN s.total ELSE 0 END), 0) AS month_sales,
              COALESCE(SUM(CASE WHEN s.timestamp >= ? AND s.timestamp <= ? THEN s.total - COALESCE(c.cost, 0) ELSE 0 END), 0) AS month_profit
            FROM sales s
            LEFT JOIN (SELECT si.sale_id, SUM(si.qty * p.cost_price) AS cost
                       FROM sale_items si JOIN products p ON p.id = si.product_id
                       GROUP BY si.sale_id) c ON c.sale_id = s.id
        """, (today_text, now_text, today_text, now_text,
              week_text, now_text, week_text, now_text,
              month_text, now_text, month_text, now_text)).fetchone()
              
        period_start = starts[period].isoformat(timespec="seconds")
        
        top = [dict(row) for row in conn.execute("""
            SELECT p.id, p.name, SUM(si.qty) AS quantity, SUM(si.qty * si.unit_price) AS total_revenue
            FROM sale_items si JOIN sales s ON s.id = si.sale_id
            JOIN products p ON p.id = si.product_id
            WHERE s.timestamp >= ? AND s.timestamp <= ?
            GROUP BY p.id, p.name ORDER BY quantity DESC, p.name LIMIT 8
        """, (period_start, now_text)).fetchall()]

        # Daily revenue & profit trend
        daily_rows = conn.execute("""
            SELECT date(s.timestamp) AS day,
                   COALESCE(SUM(s.total), 0) AS revenue,
                   COALESCE(SUM(s.total - COALESCE(c.cost, 0)), 0) AS profit,
                   COUNT(s.id) AS orders
            FROM sales s
            LEFT JOIN (SELECT si.sale_id, SUM(si.qty * p.cost_price) AS cost
                       FROM sale_items si JOIN products p ON p.id = si.product_id
                       GROUP BY si.sale_id) c ON c.sale_id = s.id
            WHERE s.timestamp >= ? AND s.timestamp <= ?
            GROUP BY date(s.timestamp)
            ORDER BY day ASC
        """, (period_start, now_text)).fetchall()
        daily_trend = [dict(r) for r in daily_rows]

        # Payment methods distribution
        pay_rows = conn.execute("""
            SELECT COALESCE(payment_mode, 'Cash') AS mode,
                   COUNT(*) AS count,
                   COALESCE(SUM(total), 0) AS total_amount
            FROM sales
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY payment_mode
            ORDER BY total_amount DESC
        """, (period_start, now_text)).fetchall()
        payment_breakdown = [dict(r) for r in pay_rows]

        # Category sales breakdown
        cat_rows = conn.execute("""
            SELECT COALESCE(NULLIF(p.category, ''), 'General') AS category,
                   SUM(si.qty) AS quantity,
                   COALESCE(SUM(si.qty * si.unit_price), 0) AS revenue
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN products p ON p.id = si.product_id
            WHERE s.timestamp >= ? AND s.timestamp <= ?
            GROUP BY p.category
            ORDER BY revenue DESC LIMIT 8
        """, (period_start, now_text)).fetchall()
        category_sales = [dict(r) for r in cat_rows]

        # Period statistics
        period_stats = conn.execute("""
            SELECT COUNT(DISTINCT s.id) AS total_orders,
                   COALESCE(SUM(s.total), 0) AS total_revenue,
                   COALESCE(SUM(si.qty), 0) AS total_units_sold
            FROM sales s
            LEFT JOIN sale_items si ON si.sale_id = s.id
            WHERE s.timestamp >= ? AND s.timestamp <= ?
        """, (period_start, now_text)).fetchone()

        total_orders = period_stats["total_orders"] or 0
        total_rev = period_stats["total_revenue"] or 0
        avg_order_value = (total_rev / total_orders) if total_orders > 0 else 0.0

        restock_needed = [dict(row) for row in conn.execute("""
            SELECT p.id, p.name, p.stock_qty, p.low_stock_threshold, p.cost_price,
                   (p.low_stock_threshold * 2 - p.stock_qty) AS suggested_order,
                   ((p.low_stock_threshold * 2 - p.stock_qty) * p.cost_price) AS estimated_cost
            FROM products p
            WHERE p.stock_qty <= p.low_stock_threshold
            ORDER BY (p.stock_qty - p.low_stock_threshold) ASC, p.name LIMIT 10
        """).fetchall()]

        slow = [dict(row) for row in conn.execute("""
            SELECT p.id, p.name, p.stock_qty, p.low_stock_threshold,
                   COALESCE(recent.sold, 0) AS sold
            FROM products p
            LEFT JOIN (
                SELECT si.product_id, SUM(si.qty) AS sold
                FROM sale_items si JOIN sales s ON s.id = si.sale_id
                WHERE s.timestamp >= ? AND s.timestamp <= ?
                GROUP BY si.product_id
            ) recent ON recent.product_id = p.id
            WHERE p.stock_qty > 0 AND COALESCE(recent.sold, 0) = 0
            ORDER BY p.stock_qty DESC, p.name LIMIT 8
        """, (period_start, now_text)).fetchall()]

        hourly = conn.execute("""
            SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour, COUNT(*) AS sales
            FROM sales WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY strftime('%H', timestamp)
        """, (period_start, now_text)).fetchall()
        
        stock_value = conn.execute("SELECT COALESCE(SUM(stock_qty * cost_price), 0) FROM products").fetchone()[0]
        total_khata_due = conn.execute("SELECT COALESCE(SUM(balance), 0) FROM customers WHERE balance > 0").fetchone()[0]
        
        return {
            "summary": dict(summary),
            "top_products": top,
            "daily_trend": daily_trend,
            "payment_breakdown": payment_breakdown,
            "category_sales": category_sales,
            "total_orders": total_orders,
            "avg_order_value": avg_order_value,
            "total_units_sold": period_stats["total_units_sold"] or 0,
            "slow_products": slow,
            "restock_needed": restock_needed,
            "hourly_sales": {int(row["hour"]): int(row["sales"]) for row in hourly if row["hour"] is not None},
            "stock_value": float(stock_value),
            "total_khata_due": float(total_khata_due),
        }
    finally:
        conn.close()


def list_categories():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC").fetchall()
        return [r["category"] for r in rows]
    finally:
        conn.close()


def list_products(category=None, low_stock_only=False):
    conn = get_connection()
    try:
        if category and low_stock_only:
            rows = conn.execute("SELECT * FROM products WHERE category = ? AND stock_qty <= low_stock_threshold ORDER BY name ASC", (category,)).fetchall()
        elif category:
            rows = conn.execute("SELECT * FROM products WHERE category = ? ORDER BY name ASC", (category,)).fetchall()
        elif low_stock_only:
            rows = conn.execute("SELECT * FROM products WHERE stock_qty <= low_stock_threshold ORDER BY name ASC").fetchall()
        else:
            rows = conn.execute("SELECT * FROM products ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_product(pid):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_product(name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold=5):
    if not name.strip():
        raise ValueError("Product name is required.")
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO products (name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name.strip(), barcode.strip() if barcode else None, float(cost_price), float(sale_price), int(stock_qty), category.strip() if category else None, int(low_stock_threshold)),
        )
        pid = cur.lastrowid
        conn.commit()
        return pid
    finally:
        conn.close()


def update_product(pid, name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold):
    if not name.strip():
        raise ValueError("Product name is required.")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE products SET name = ?, barcode = ?, cost_price = ?, sale_price = ?, stock_qty = ?, category = ?, low_stock_threshold = ? WHERE id = ?",
            (name.strip(), barcode.strip() if barcode else None, float(cost_price), float(sale_price), int(stock_qty), category.strip() if category else None, int(low_stock_threshold), pid),
        )
        conn.commit()
    finally:
        conn.close()


def delete_product(pid):
    conn = get_connection()
    try:
        # Block deletion if the product has sales history — would orphan sale_items records
        sales_count = conn.execute(
            "SELECT COUNT(*) FROM sale_items WHERE product_id = ?", (pid,)
        ).fetchone()[0]
        if sales_count > 0:
            raise ValueError(
                f"This product has {sales_count} sale record(s) and cannot be deleted. "
                "To hide it from sales, set its stock to 0 instead."
            )
        # Also block if product has purchase history
        purchase_count = conn.execute(
            "SELECT COUNT(*) FROM purchase_items WHERE product_id = ?", (pid,)
        ).fetchone()[0]
        if purchase_count > 0:
            raise ValueError(
                f"This product has {purchase_count} purchase record(s) and cannot be deleted. "
                "Set stock to 0 to retire it."
            )
        conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
    finally:
        conn.close()


def assign_barcode_to_product(product_id: int, barcode: str) -> None:
    """Assign (or overwrite) a barcode on an existing product.

    Called from the billing screen when an unknown barcode is scanned and
    the cashier chooses to link it to an existing product entry.
    """
    barcode = barcode.strip()
    if not barcode:
        raise ValueError("Barcode cannot be empty.")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE products SET barcode = ? WHERE id = ?",
            (barcode, product_id),
        )
        conn.commit()
    finally:
        conn.close()


def _clean_number(val, default=0.0):
    if val is None:
        return default
    text = str(val).strip().replace("Rs", "").replace("PKR", "").replace("$", "").replace(",", "")
    text = re.sub(r"[^\d.-]", "", text)
    try:
        return float(text) if text else default
    except (ValueError, TypeError):
        return default


def _find_field(row_dict, candidates):
    normalized = {re.sub(r"[\s_-]+", "", k.lower()): v for k, v in row_dict.items() if k}
    for candidate in candidates:
        norm_candidate = re.sub(r"[\s_-]+", "", candidate.lower())
        if norm_candidate in normalized:
            return normalized[norm_candidate]
    return None


def import_products_csv(file_path):
    """
    Intelligent Bulk CSV product importer.
    Supports flexible column naming, currency symbols, and multi-encoding.
    """
    imported = 0
    updated = 0
    skipped = 0
    conn = get_connection()

    # Guard against extremely large files that could exhaust memory
    try:
        file_size = os.path.getsize(file_path)
    except OSError as e:
        raise ValueError(f"Cannot access CSV file: {e}")
    if file_size > 10 * 1024 * 1024:  # 10 MB limit
        raise ValueError(f"CSV file is too large ({file_size // 1024 // 1024} MB). Maximum allowed size is 10 MB.")

    # Detect encoding
    raw_bytes = open(file_path, "rb").read()
    encoding = "utf-8-sig"
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            raw_text = raw_bytes.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue

    try:
        conn.execute("BEGIN IMMEDIATE")
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            # Auto-detect delimiter (comma, tab, semicolon)
            sample = f.read(2048)
            f.seek(0)
            delimiter = ","
            if sample.count("\t") > sample.count(","):
                delimiter = "\t"
            elif sample.count(";") > sample.count(","):
                delimiter = ";"

            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                name_val = _find_field(row, [
                    "name", "product_name", "product name", "product", "item_name",
                    "item name", "item", "title", "product title", "description"
                ])
                name = str(name_val).strip() if name_val else ""
                if not name:
                    skipped += 1
                    continue

                barcode_val = _find_field(row, ["barcode", "bar code", "sku", "code", "upc", "ean", "item code"])
                barcode = str(barcode_val).strip() if barcode_val else None
                if barcode in ("", "None", "nan", "null"):
                    barcode = None

                cost_val = _find_field(row, ["cost_price", "cost price", "cost", "purchase_price", "purchase price", "buy price", "cp"])
                cost_price = _clean_number(cost_val, 0.0)

                sale_val = _find_field(row, ["sale_price", "sale price", "price", "selling_price", "selling price", "retail_price", "mrp", "rate", "sp"])
                sale_price = _clean_number(sale_val, 0.0)
                if sale_price <= 0 and cost_price > 0:
                    sale_price = cost_price * 1.15  # Fallback margin if sale price missing

                stock_val = _find_field(row, ["stock_qty", "stock qty", "stock", "qty", "quantity", "count", "inventory"])
                stock_qty = int(_clean_number(stock_val, 0.0))

                cat_val = _find_field(row, ["category", "dept", "department", "group", "type"])
                category = str(cat_val).strip() if cat_val else None
                if category in ("", "None", "nan", "null"):
                    category = None

                thresh_val = _find_field(row, ["low_stock_threshold", "low stock threshold", "low stock", "threshold", "min stock", "reorder level"])
                low_stock = int(_clean_number(thresh_val, 5.0))

                existing = None
                if barcode:
                    existing = conn.execute("SELECT id FROM products WHERE barcode = ?", (barcode,)).fetchone()
                if not existing:
                    existing = conn.execute("SELECT id FROM products WHERE name = ?", (name,)).fetchone()

                if existing:
                    conn.execute("""
                        UPDATE products
                        SET name = ?, barcode = ?, cost_price = ?, sale_price = ?, stock_qty = ?, category = ?, low_stock_threshold = ?
                        WHERE id = ?
                    """, (name, barcode, cost_price, sale_price, stock_qty, category, low_stock, existing["id"]))
                    updated += 1
                else:
                    conn.execute("""
                        INSERT INTO products (name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (name, barcode, cost_price, sale_price, stock_qty, category, low_stock))
                    imported += 1

        conn.commit()
        return {"imported": imported, "updated": updated, "skipped": skipped, "total": imported + updated}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def export_products_csv(file_path):
    conn = get_connection()
    try:
        rows = conn.execute("SELECT name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold FROM products ORDER BY name ASC").fetchall()
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Barcode", "Cost Price", "Sale Price", "Stock", "Category", "Low Stock"])
            for r in rows:
                writer.writerow([r["name"], r["barcode"] or "", r["cost_price"], r["sale_price"], r["stock_qty"], r["category"] or "", r["low_stock_threshold"]])
        return len(rows)
    finally:
        conn.close()


def generate_sample_csv(file_path):
    sample_data = [
        ["Name", "Barcode", "Cost Price", "Sale Price", "Stock", "Category", "Low Stock"],
        ["Lays Masala 50g", "896400010011", "80", "100", "48", "Snacks", "10"],
        ["Olpers Milk 1 Litre", "896400020022", "270", "320", "24", "Dairy", "5"],
        ["Tapal Danedar Tea 400g", "896400030033", "550", "640", "15", "Beverages", "3"],
        ["Surf Excel 500g", "896400040044", "220", "260", "20", "Household", "5"],
    ]
    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerows(sample_data)
    return file_path


def hash_pin(pin):
    if not pin.isdigit() or not 4 <= len(pin) <= 8:
        raise ValueError("PIN must contain 4 to 8 digits.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt.encode("utf-8"), 600_000).hex()
    return f"pbkdf2${salt}${digest}"


def authenticate_pin(pin):
    if not pin.isdigit() or not 4 <= len(pin) <= 8:
        return None
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name, role, pin_hash FROM users").fetchall()
        for row in rows:
            encoded = row["pin_hash"]
            if encoded.startswith("pbkdf2$"):
                # New PBKDF2-HMAC-SHA256 format
                try:
                    _, salt, expected = encoded.split("$", 2)
                except ValueError:
                    continue
                actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt.encode("utf-8"), 600_000).hex()
            elif encoded.startswith("sha256$"):
                # Legacy salted SHA-256 — still accepted for existing users
                try:
                    _, salt, expected = encoded.split("$", 2)
                except ValueError:
                    continue
                actual = hashlib.sha256((salt + pin).encode("utf-8")).hexdigest()
            else:
                # Raw unsalted hash — reject; account must be recreated
                continue
            if hmac.compare_digest(actual, expected):
                return {"id": row["id"], "name": row["name"], "role": row["role"]}
        return None
    finally:
        conn.close()


def user_count():
    conn = get_connection()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    finally:
        conn.close()


def create_user_with_pin(name, role, pin):
    if role not in ("admin", "cashier"):
        raise ValueError("Choose Admin or Cashier.")
    if not name.strip():
        raise ValueError("Enter the user's name.")
    pin_hash = hash_pin(pin)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in conn.execute("SELECT pin_hash FROM users").fetchall():
            encoded = row["pin_hash"]
            if encoded.startswith("pbkdf2$"):
                parts = encoded.split("$", 2)
                if len(parts) == 3 and hmac.compare_digest(
                        hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), parts[1].encode("utf-8"), 600_000).hex(),
                        parts[2]):
                    raise ValueError("That PIN is already assigned. Choose a different PIN.")
            elif encoded.startswith("sha256$"):
                parts = encoded.split("$", 2)
                if len(parts) == 3 and hmac.compare_digest(
                        hashlib.sha256((parts[1] + pin).encode("utf-8")).hexdigest(), parts[2]):
                    raise ValueError("That PIN is already assigned. Choose a different PIN.")
            # Raw/unsalted hashes are not checked — they are invalid accounts
        cursor = conn.execute("INSERT INTO users (name, role, pin_hash) VALUES (?, ?, ?)",
                              (name.strip(), role, pin_hash))
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_users():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name, role FROM users").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_user(uid):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
    finally:
        conn.close()


def update_user_pin(user_id, new_pin):
    """Update a user's PIN with PBKDF2 hashing and uniqueness validation."""
    if not new_pin.isdigit() or not 4 <= len(new_pin) <= 8:
        raise ValueError("PIN must contain 4 to 8 digits.")
    pin_hash = hash_pin(new_pin)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in conn.execute("SELECT id, pin_hash FROM users WHERE id != ?", (user_id,)).fetchall():
            encoded = row["pin_hash"]
            if encoded.startswith("pbkdf2$"):
                parts = encoded.split("$", 2)
                if len(parts) == 3 and hmac.compare_digest(
                        hashlib.pbkdf2_hmac("sha256", new_pin.encode("utf-8"), parts[1].encode("utf-8"), 600_000).hex(),
                        parts[2]):
                    raise ValueError("That PIN is already assigned to another user.")
            elif encoded.startswith("sha256$"):
                parts = encoded.split("$", 2)
                if len(parts) == 3 and hmac.compare_digest(
                        hashlib.sha256((parts[1] + new_pin).encode("utf-8")).hexdigest(), parts[2]):
                    raise ValueError("That PIN is already assigned to another user.")
        changed = conn.execute("UPDATE users SET pin_hash = ? WHERE id = ?", (pin_hash, user_id)).rowcount
        if changed != 1:
            raise ValueError("User not found.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def backup_database(folder):
    target_dir = Path(folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"ShopFlow_backup_{stamp}.db"
    source = sqlite3.connect(DB_PATH)
    destination = sqlite3.connect(str(target))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return str(target)


def start_cash_shift(cashier_id, cashier_name, opening):
    opening = float(opening)
    if opening < 0:
        raise ValueError("Opening cash cannot be negative.")
    conn = get_connection()
    try:
        if conn.execute("SELECT id FROM cash_shifts WHERE closed_at IS NULL").fetchone():
            raise ValueError("A cash shift is already open. Close it before starting another.")
        cur = conn.execute("INSERT INTO cash_shifts (cashier_id,cashier_name,opening,opened_at) VALUES (?,?,?,?)",
                           (cashier_id, cashier_name, opening, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def active_cash_shift():
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM cash_shifts WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def record_cash_expense(amount, notes="", cashier_id=None):
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Expense amount must be greater than zero.")
    if not active_cash_shift():
        raise ValueError("Open a cash shift before recording a petty cash expense.")
    conn = get_connection()
    try:
        conn.execute("INSERT INTO cash_expenses (amount,notes,cashier_id,timestamp) VALUES (?,?,?,?)",
                     (amount,notes,cashier_id,datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()


def cash_shift_summary(shift_id):
    conn = get_connection()
    try:
        shift = conn.execute("SELECT * FROM cash_shifts WHERE id=? AND closed_at IS NULL", (shift_id,)).fetchone()
        if not shift:
            raise ValueError("No open cash shift was found.")
        since = shift["opened_at"]
        sales = conn.execute("SELECT COALESCE(SUM(total-exchange_credit),0) FROM sales WHERE payment_mode='Cash' AND timestamp>=?", (since,)).fetchone()[0]
        recoveries = conn.execute("SELECT COALESCE(SUM(-amount),0) FROM customer_transactions WHERE type='payment' AND payment_method='Cash' AND timestamp>=?", (since,)).fetchone()[0]
        refunds = conn.execute("SELECT COALESCE(SUM(refund_amount),0) FROM sale_returns WHERE refund_method='Cash' AND timestamp>=?", (since,)).fetchone()[0]
        expenses = conn.execute("SELECT COALESCE(SUM(amount),0) FROM cash_expenses WHERE timestamp>=?", (since,)).fetchone()[0]
        expected = float(shift["opening"]) + float(sales) + float(recoveries) - float(refunds) - float(expenses)
        return {"shift": dict(shift), "cash_sales": float(sales), "khata_recoveries": float(recoveries),
                "cash_refunds": float(refunds), "expenses": float(expenses), "expected": expected}
    finally:
        conn.close()


def close_cash_shift(shift_id, actual, notes=""):
    summary = cash_shift_summary(shift_id)
    actual = float(actual)
    variance = actual - summary["expected"]
    shift = summary["shift"]
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("INSERT INTO cash_closings (timestamp,cashier_id,cashier_name,opening,expected,actual,discrepancy,notes) VALUES (?,?,?,?,?,?,?,?)",
                           (now, shift["cashier_id"], shift["cashier_name"], shift["opening"], summary["expected"], actual, variance, notes))
        conn.execute("UPDATE cash_shifts SET closed_at=? WHERE id=? AND closed_at IS NULL", (now, shift_id))
        conn.commit()
        return {**summary, "closing_id": cur.lastrowid, "actual": actual, "variance": variance, "timestamp": now}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_suppliers():
    conn = get_connection()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM suppliers ORDER BY name")]
    finally:
        conn.close()


def save_supplier(name, company="", phone="", address="", supplier_id=None):
    if not name.strip():
        raise ValueError("Supplier name is required.")
    conn = get_connection()
    try:
        if supplier_id:
            conn.execute("UPDATE suppliers SET name=?,company=?,phone=?,address=? WHERE id=?", (name.strip(),company,phone,address,supplier_id))
            sid = supplier_id
        else:
            cur = conn.execute("INSERT INTO suppliers (name,company,phone,address,created_at) VALUES (?,?,?,?,?)",
                               (name.strip(),company,phone,address,datetime.now().isoformat(timespec="seconds")))
            sid = cur.lastrowid
        conn.commit()
        return sid
    finally:
        conn.close()


def record_purchase(supplier_id, invoice_no, items, paid_amount=0, payment_method="Cash"):
    if not items:
        raise ValueError("Add at least one product to the purchase.")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        total, prepared = 0.0, []
        for item in items:
            qty, cost, pid = int(item["qty"]), float(item["unit_cost"]), int(item["product_id"])
            if qty <= 0 or cost < 0 or not conn.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone():
                raise ValueError("A purchase item is invalid.")
            total += qty * cost
            prepared.append((pid,qty,cost))
        paid = float(paid_amount)
        if payment_method not in ("Cash", "Bank transfer"):
            raise ValueError("Choose Cash or Bank transfer for the purchase payment.")
        if paid < 0 or paid > total:
            raise ValueError("Paid amount must be between zero and the purchase total.")
        if not conn.execute("SELECT id FROM suppliers WHERE id=?", (supplier_id,)).fetchone():
            raise ValueError("Select a valid supplier.")
        status = "Paid" if paid == total else ("Partial" if paid else "Credit")
        now = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute("INSERT INTO purchases (supplier_id,invoice_no,timestamp,total_amount,paid_amount,payment_status) VALUES (?,?,?,?,?,?)",
                           (supplier_id,invoice_no,now,total,paid,status))
        purchase_id = cur.lastrowid
        for pid,qty,cost in prepared:
            conn.execute("INSERT INTO purchase_items (purchase_id,product_id,qty,unit_cost) VALUES (?,?,?,?)", (purchase_id,pid,qty,cost))
            # Only update cost_price if the incoming cost is positive — avoids wiping historical cost
            if cost > 0:
                conn.execute("UPDATE products SET stock_qty=stock_qty+?,cost_price=? WHERE id=?", (qty,cost,pid))
            else:
                conn.execute("UPDATE products SET stock_qty=stock_qty+? WHERE id=?", (qty,pid))
            conn.execute("INSERT INTO stock_movements (product_id,type,qty,timestamp) VALUES (?,'restock',?,?)", (pid,qty,now))
        due = total-paid
        conn.execute("UPDATE suppliers SET balance_owed=balance_owed+? WHERE id=?", (due,supplier_id))
        conn.execute("INSERT INTO supplier_transactions (supplier_id,purchase_id,type,amount,notes,timestamp) VALUES (?,?,'purchase',?,?,?)",
                     (supplier_id,purchase_id,total,f"Invoice {invoice_no or ''}",now))
        if paid > 0:
            conn.execute("INSERT INTO supplier_transactions (supplier_id,purchase_id,type,amount,notes,timestamp) VALUES (?,?,'payment',?,?,?)",
                         (supplier_id,purchase_id,paid,f"Paid on purchase ({payment_method})",now))
        if paid > 0 and payment_method == "Cash":
            conn.execute("INSERT INTO cash_expenses (amount,notes,timestamp) VALUES (?,?,?)", (paid,f"Cash paid to supplier for invoice {invoice_no or purchase_id}",now))
        conn.commit()
        return {"purchase_id":purchase_id,"total":total,"paid":paid,"due":due,"status":status}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_supplier_payment(supplier_id, amount, method="Cash", notes=""):
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Payment must be greater than zero.")
    if method not in ("Cash", "Bank transfer"):
        raise ValueError("Choose Cash or Bank transfer for the supplier payment.")
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        supplier = conn.execute("SELECT balance_owed FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        if not supplier:
            raise ValueError("Supplier not found.")
        if amount > float(supplier["balance_owed"]):
            raise ValueError("Payment cannot exceed the supplier balance owed.")
        remaining = amount
        purchases = conn.execute("SELECT id,total_amount,paid_amount FROM purchases WHERE supplier_id=? AND paid_amount<total_amount ORDER BY timestamp,id", (supplier_id,)).fetchall()
        allocations = []
        for purchase in purchases:
            if remaining <= 0.005:
                break
            due = max(0.0, float(purchase["total_amount"]) - float(purchase["paid_amount"]))
            applied = min(remaining, due)
            if applied <= 0:
                continue
            new_paid = float(purchase["paid_amount"]) + applied
            status = "Paid" if new_paid >= float(purchase["total_amount"]) - 0.005 else "Partial"
            conn.execute("UPDATE purchases SET paid_amount=?,payment_status=? WHERE id=?", (new_paid,status,purchase["id"]))
            allocations.append((purchase["id"],applied))
            remaining -= applied
        if remaining > 0.005:
            raise ValueError("The supplier balance does not match its outstanding purchase invoices.")
        conn.execute("UPDATE suppliers SET balance_owed=balance_owed-? WHERE id=?", (amount,supplier_id))
        for purchase_id, applied in allocations:
            conn.execute("INSERT INTO supplier_transactions (supplier_id,purchase_id,type,amount,notes,timestamp) VALUES (?,?,'payment',?,?,?)",
                         (supplier_id,purchase_id,applied,f"{method}: {notes}".strip(),now))
        if method == "Cash":
            conn.execute("INSERT INTO cash_expenses (amount,notes,timestamp) VALUES (?,?,?)", (amount,f"Supplier payment: {notes}".strip(),now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def supplier_ledger(supplier_id):
    conn = get_connection()
    try:
        result, balance = [], 0.0
        for row in conn.execute("SELECT * FROM supplier_transactions WHERE supplier_id=? ORDER BY id", (supplier_id,)):
            entry = dict(row)
            balance += float(entry["amount"]) if entry["type"] == "purchase" else -float(entry["amount"])
            entry["running_balance"] = balance
            result.append(entry)
        return result
    finally:
        conn.close()


def export_sales_csv(path, start_date, end_date):
    from datetime import date, timedelta
    start = date.fromisoformat(start_date).isoformat() + "T00:00:00"
    end = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat() + "T00:00:00"
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT s.id AS sale_id, s.timestamp, s.total, s.discount, s.payment_mode,
                   COALESCE(c.name, 'Walk-in') AS customer,
                   COALESCE(GROUP_CONCAT(p.name || ' x' || si.qty, '; '), '') AS items
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            LEFT JOIN sale_items si ON si.sale_id = s.id
            LEFT JOIN products p ON p.id = si.product_id
            WHERE s.timestamp >= ? AND s.timestamp < ?
            GROUP BY s.id
            ORDER BY s.timestamp, s.id
        """, (start, end)).fetchall()
        with open(path, "w", newline="", encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(("Sale ID", "Date / Time", "Customer", "Items", "Discount (Rs)", "Total (Rs)", "Payment mode"))
            for row in rows:
                writer.writerow((row["sale_id"], row["timestamp"], row["customer"], row["items"],
                                 f"{float(row['discount'] or 0):.2f}", f"{float(row['total']):.2f}",
                                 row["payment_mode"] or ""))
        return len(rows)
    finally:
        conn.close()
