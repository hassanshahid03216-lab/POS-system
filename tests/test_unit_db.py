"""Comprehensive Unit Tests for ShopFlow POS Database Layer."""

import gc
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db import db


class TestDatabaseUnit(unittest.TestCase):
    """Unit tests covering all CRUD and business logic functions in db.py."""

    @classmethod
    def setUpClass(cls):
        # Patch pbkdf2 iterations for blazing fast test execution (1,000 instead of 600,000)
        orig_pbkdf2 = db.hashlib.pbkdf2_hmac

        def fast_pbkdf2(hash_name, password, salt, iterations, dklen=None):
            return orig_pbkdf2(hash_name, password, salt, min(iterations, 1000), dklen)

        cls.patcher = patch("hashlib.pbkdf2_hmac", side_effect=fast_pbkdf2)
        cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def setUp(self):
        # Create isolated temp database for each test
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = str(Path(self.temp_dir.name) / "test_pos.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.test_db_path
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ── User & Auth Unit Tests ──────────────────────────────────────────

    def test_default_admin_created(self):
        """Verify default admin is created on init_db."""
        users = db.list_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["name"], "Admin")
        self.assertEqual(users[0]["role"], "admin")

    def test_pin_hashing_and_auth(self):
        """Verify PBKDF2 PIN hashing and authentication."""
        auth = db.authenticate_pin("1234")
        self.assertIsNotNone(auth)
        self.assertEqual(auth["role"], "admin")

        # Wrong PIN should fail
        self.assertIsNone(db.authenticate_pin("9999"))
        # Invalid format should fail
        self.assertIsNone(db.authenticate_pin("abc"))
        self.assertIsNone(db.authenticate_pin("12"))

    def test_create_and_delete_user(self):
        """Verify creating cashiers and admins with valid PINs."""
        user_id = db.create_user_with_pin("Cashier John", "cashier", "5555")
        self.assertIsInstance(user_id, int)

        auth = db.authenticate_pin("5555")
        self.assertIsNotNone(auth)
        self.assertEqual(auth["name"], "Cashier John")
        self.assertEqual(auth["role"], "cashier")

        # Duplicate PIN should be rejected
        with self.assertRaises(ValueError):
            db.create_user_with_pin("Cashier Sarah", "cashier", "5555")

        # Update PIN
        db.update_user_pin(user_id, "7777")
        self.assertIsNone(db.authenticate_pin("5555"))
        self.assertIsNotNone(db.authenticate_pin("7777"))

        # Delete user
        db.delete_user(user_id)
        self.assertIsNone(db.authenticate_pin("7777"))

    # ── Product Management Unit Tests ────────────────────────────────────

    def test_product_crud_and_validation(self):
        """Verify adding, updating, searching, and deleting products."""
        pid = db.create_product(
            name="Milk 1L",
            barcode="890123456789",
            cost_price=180.0,
            sale_price=220.0,
            stock_qty=50,
            category="Dairy",
            low_stock_threshold=10,
        )
        self.assertIsInstance(pid, int)

        prod = db.get_product(pid)
        self.assertEqual(prod["name"], "Milk 1L")
        self.assertEqual(prod["sale_price"], 220.0)
        self.assertEqual(prod["stock_qty"], 50)

        # Barcode uniqueness
        with self.assertRaises(sqlite3.IntegrityError):
            db.create_product(
                name="Duplicate Milk",
                barcode="890123456789",
                cost_price=180.0,
                sale_price=220.0,
                stock_qty=10,
                category="Dairy",
            )

        # Update product
        db.update_product(
            pid,
            name="Milk 1L Fresh",
            barcode="890123456789",
            cost_price=190.0,
            sale_price=230.0,
            stock_qty=45,
            category="Dairy",
            low_stock_threshold=10,
        )
        updated = db.get_product(pid)
        self.assertEqual(updated["name"], "Milk 1L Fresh")
        self.assertEqual(updated["sale_price"], 230.0)
        self.assertEqual(updated["stock_qty"], 45)

        # Delete product
        db.delete_product(pid)
        self.assertIsNone(db.get_product(pid))

    def test_list_products_filtering_and_search(self):
        """Verify list_products category filtering and low stock filter."""
        db.create_product("Bread", "111", 50, 70, 20, "Bakery", 5)
        db.create_product("Low Stock Butter", "222", 150, 200, 3, "Dairy", 5)
        db.create_product("Eggs Dozen", "333", 180, 240, 10, "Dairy", 5)

        # Filter by category
        dairy = db.list_products(category="Dairy")
        self.assertEqual(len(dairy), 2)

        # Low stock filter
        low_stock = db.list_products(low_stock_only=True)
        self.assertEqual(len(low_stock), 1)
        self.assertEqual(low_stock[0]["name"], "Low Stock Butter")

    # ── Billing & Sales Unit Tests ───────────────────────────────────────

    def test_checkout_cash_sale(self):
        """Verify checkout deductions, total calculation, and stock updates."""
        pid1 = db.create_product("Item A", "A01", 100, 150, 20, "General", 5)
        pid2 = db.create_product("Item B", "B01", 200, 300, 10, "General", 5)

        items = [
            {"id": pid1, "qty": 2, "unit_price": 150.0, "discount": 0.0},
            {"id": pid2, "qty": 1, "unit_price": 300.0, "discount": 20.0},
        ]
        res = db.checkout_sale(items, payment_mode="Cash", bill_discount=30.0)
        self.assertIsInstance(res, dict)
        sale_id = res["sale_id"]

        # Verify stock deducted
        p1 = db.get_product(pid1)
        p2 = db.get_product(pid2)
        self.assertEqual(p1["stock_qty"], 18)
        self.assertEqual(p2["stock_qty"], 9)

        # Verify sale record
        conn = db.get_connection()
        row = conn.execute("SELECT total, discount, payment_mode FROM sales WHERE id = ?", (sale_id,)).fetchone()
        conn.close()
        self.assertEqual(row["total"], 550.0)
        self.assertEqual(row["discount"], 50.0)
        self.assertEqual(row["payment_mode"], "Cash")

    def test_checkout_stock_guard(self):
        """Verify checkout throws error when quantity exceeds available stock."""
        pid = db.create_product("Limited Item", "LIM01", 100, 150, 2, "General", 1)
        items = [{"id": pid, "qty": 5, "unit_price": 150.0, "discount": 0.0}]

        with self.assertRaises(ValueError):
            db.checkout_sale(items, payment_mode="Cash")

        # Ensure no stock was deducted due to transaction rollback
        prod = db.get_product(pid)
        self.assertEqual(prod["stock_qty"], 2)

    # ── Held Bills Unit Tests ───────────────────────────────────────────

    def test_hold_and_resume_bill(self):
        """Verify parking a cart and retrieving it."""
        pid = db.create_product("Parked Item", "P01", 50, 100, 10, "General", 2)
        cart = {"items": [{"id": pid, "name": "Parked Item", "qty": 2, "unit_price": 100.0}]}

        held_id = db.save_held_bill(cart)
        self.assertIsInstance(held_id, int)

        held_list = db.list_held_bills()
        self.assertEqual(len(held_list), 1)
        self.assertIn("Parked Item", held_list[0]["label"])

        retrieved = db.get_held_bill(held_id)
        self.assertIn("items", retrieved)
        self.assertEqual(retrieved["items"][0]["id"], pid)

    # ── Customer Khata Ledger Unit Tests ─────────────────────────────────

    def test_customer_khata_lifecycle(self):
        """Verify credit sale, ledger balance accumulation, and repayment."""
        cid = db.create_customer("Zubair Ahmed", "03001234567", "Block 4, Gulshan")
        cust = db.get_customer(cid)
        self.assertEqual(cust["balance"], 0.0)

        pid = db.create_product("Rice 5kg", "R5", 400, 600, 20, "Grains", 5)
        items = [{"id": pid, "qty": 1, "unit_price": 600.0, "discount": 0.0}]

        # Credit sale for Rs 600
        res = db.checkout_sale(items, payment_mode="Credit / Khata", customer_id=cid)
        cust_after_sale = db.get_customer(cid)
        self.assertEqual(cust_after_sale["balance"], 600.0)

        # Repayment of Rs 400
        db.record_customer_payment(cid, amount=400.0, notes="Cash paid at shop", payment_method="Cash")
        cust_after_pay = db.get_customer(cid)
        self.assertEqual(cust_after_pay["balance"], 200.0)

        # Verify ledger statements
        ledger = db.get_customer_ledger(cid)
        self.assertIn("transactions", ledger)
        self.assertEqual(len(ledger["transactions"]), 2)
        types = [t["type"] for t in ledger["transactions"]]
        self.assertIn("sale", types)
        self.assertIn("payment", types)

    # ── Returns and Exchanges Unit Tests ─────────────────────────────────

    def test_sales_return_with_restock(self):
        """Verify item return restores stock and records refund."""
        pid = db.create_product("Shampoo 200ml", "SH01", 200, 350, 10, "Cosmetics", 2)
        items = [{"id": pid, "qty": 2, "unit_price": 350.0, "discount": 0.0}]
        sale_res = db.checkout_sale(items, payment_mode="Cash")
        sale_id = sale_res["sale_id"]

        # Stock before return = 8
        self.assertEqual(db.get_product(pid)["stock_qty"], 8)

        # Return 1 bottle
        return_items = [{"product_id": pid, "qty": 1, "unit_price": 350.0}]
        res = db.process_sale_return(sale_id, return_items, notes="Wrong variant", refund_method="Cash", restock=True)
        self.assertIn("return_id", res)
        self.assertEqual(res["refund_amount"], 350.0)

        # Stock should be restored to 9
        self.assertEqual(db.get_product(pid)["stock_qty"], 9)

    # ── Cash Shifts and Closing Unit Tests ───────────────────────────────

    def test_cash_shift_and_closing_reconciliation(self):
        """Verify shift open, cash sale accumulation, cash expense, and variance calculation."""
        shift_id = db.start_cash_shift(cashier_id=1, cashier_name="Admin", opening=2000.0)
        self.assertIsInstance(shift_id, int)

        # Add a cash sale of Rs 500
        pid = db.create_product("Tea Box", "TB01", 300, 500, 10, "Beverages", 2)
        db.checkout_sale([{"id": pid, "qty": 1, "unit_price": 500.0, "discount": 0}], payment_mode="Cash")

        # Record cash expense of Rs 100 for cleaning supplies
        db.record_cash_expense(100.0, "Cleaning supplies", cashier_id=1)

        summary = db.cash_shift_summary(shift_id)
        # Expected = Opening(2000) + Cash Sales(500) - Expenses(100) = 2400
        self.assertEqual(summary["shift"]["opening"], 2000.0)
        self.assertEqual(summary["cash_sales"], 500.0)
        self.assertEqual(summary["expenses"], 100.0)
        self.assertEqual(summary["expected"], 2400.0)

        # Cashier counts actual cash in drawer: 2390 (short by 10)
        closing_res = db.close_cash_shift(
            shift_id=shift_id,
            actual=2390.0,
            notes="Missing Rs 10 change",
        )
        self.assertIsInstance(closing_res, dict)
        self.assertEqual(closing_res["variance"], -10.0)
        self.assertIsInstance(closing_res["closing_id"], int)

        # Verify active shift is closed
        self.assertIsNone(db.active_cash_shift())


if __name__ == "__main__":
    unittest.main()
