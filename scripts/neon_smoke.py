"""Disposable API-to-Neon verification for a new, empty production branch.

This refuses to run if users already exist and removes its uniquely marked
test user, product, sale, and stock movement when finished.
"""

from __future__ import annotations

import os
import secrets
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for _env_file in (PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env"):
    if _env_file.is_file():
        load_dotenv(_env_file, override=False)

os.environ["SHOPFLOW_API_URL"] = "http://127.0.0.1:8000"

import psycopg

from cloud_client import clear_token
from db import db


def main():
    if db.user_count() != 0:
        raise SystemExit("Refusing smoke test: the cloud database already contains users.")

    test_tag = uuid.uuid4().hex[:12].upper()
    barcode = f"SMOKE-{test_tag}"
    owner_name = f"smoke-{test_tag}"
    pin = str(secrets.randbelow(90_000_000) + 10_000_000)
    user_id = product_id = sale_id = None
    database_url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Neon DATABASE_URL was not found in .env.local or .env.")

    try:
        user_id = db.create_user_with_pin(owner_name, "admin", pin)
        if not db.authenticate_pin(pin):
            raise RuntimeError("API owner sign-in failed.")

        product_id = db.create_product(
            f"Cloud smoke {test_tag}", barcode, 1.0, 10.0, 2, "Smoke test", 20
        )
        sale = db.checkout_sale(
            [{"id": product_id, "qty": 1, "unit_price": 10.0, "discount": 0.0}],
            "Cash",
        )
        sale_id = sale["sale_id"]

        local_view = next(p for p in db.list_products() if p["id"] == product_id)
        if int(local_view["stock_qty"]) != 1:
            raise RuntimeError("Stock deduction did not appear through the API.")
        if not db.get_sale_for_return(sale_id):
            raise RuntimeError("The sale was not readable through the API.")

        # A fresh token models a second desktop machine signing in.
        clear_token()
        if not db.authenticate_pin(pin):
            raise RuntimeError("Second-client API sign-in failed.")
        second_view = next(p for p in db.list_products() if p["id"] == product_id)
        if int(second_view["stock_qty"]) != 1:
            raise RuntimeError("The second client did not see the shared stock update.")

        print("PASS: API health and Neon database startup")
        print("PASS: first-owner setup and authenticated sign-in")
        print("PASS: product creation and transactional checkout")
        print("PASS: second-client sign-in sees shared stock")
    finally:
        clear_token()
        with psycopg.connect(database_url, sslmode="require") as connection:
            with connection.cursor() as cursor:
                if sale_id is not None:
                    cursor.execute("DELETE FROM sale_items WHERE sale_id = %s", (sale_id,))
                    cursor.execute("DELETE FROM sales WHERE id = %s", (sale_id,))
                if product_id is not None:
                    cursor.execute("DELETE FROM stock_movements WHERE product_id = %s", (product_id,))
                    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
                if user_id is not None:
                    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if db.user_count() != 0:
            raise RuntimeError("Smoke-test cleanup left an unexpected user in the database.")
        print("PASS: temporary production-branch smoke data cleaned up")


if __name__ == "__main__":
    main()
