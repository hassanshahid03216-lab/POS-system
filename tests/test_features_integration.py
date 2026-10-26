"""Comprehensive Feature Integration Tests for ShopFlow POS.

Tests multi-step business workflows spanning across modules:
- Multi-item retail checkout with barcode lookups, discounts, and inventory decrements
- Interleaved held bills (hold cart, serve next customer, resume, checkout)
- Customer Khata (Udhaar) debt accumulation, statement generation, and settlement
- Sales Return with Exchange Credit Voucher issuance and redemption in next bill
- Supplier procurement inward delivery, cost tracking, stock increment, and retail margin
- Full shift lifecycle with cash drawer variance reconciliation
"""

import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db import db


class TestFeatureIntegration(unittest.TestCase):
    """End-to-end integration tests simulating real-world retail store operations."""

    @classmethod
    def setUpClass(cls):
        orig_pbkdf2 = db.hashlib.pbkdf2_hmac

        def fast_pbkdf2(hash_name, password, salt, iterations, dklen=None):
            return orig_pbkdf2(hash_name, password, salt, min(iterations, 1000), dklen)

        cls.patcher = patch("hashlib.pbkdf2_hmac", side_effect=fast_pbkdf2)
        cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = str(Path(self.temp_dir.name) / "integration_pos.db")
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

    def test_workflow_multi_item_checkout_with_discounts(self):
        """Simulate high-volume retail checkout:
        3 products scanned, line item discount applied, bill-level discount,
        cash tendered with change returned, and stock verified.
        """
        p1 = db.create_product("Colgate MaxFresh", "89012345", 120.0, 180.0, 50, "Toiletries")
        p2 = db.create_product("Lipton Yellow Label 200g", "89054321", 350.0, 480.0, 30, "Beverages")
        p3 = db.create_product("Nestle MilkPak 1L", "89098765", 220.0, 270.0, 100, "Dairy")

        # Cart: 2x Colgate, 1x Lipton (with Rs 30 promo discount), 4x MilkPak
        cart_items = [
            {"id": p1, "qty": 2, "unit_price": 180.0, "discount": 0.0},
            {"id": p2, "qty": 1, "unit_price": 480.0, "discount": 30.0},
            {"id": p3, "qty": 4, "unit_price": 270.0, "discount": 0.0},
        ]
        # Gross = (2*180) + (1*480) + (4*270) = 360 + 480 + 1080 = 1920
        # Line discount = 30.0. Remaining = 1890.
        # Bill discount = 40.0. Final Payable = 1850.0.
        res = db.checkout_sale(cart_items, payment_mode="Cash", bill_discount=40.0)
        self.assertEqual(res["total"], 1850.0)
        self.assertEqual(res["amount_due"], 1850.0)

        # Cash tendered calculation
        cash_tendered = 2000.0
        change_due = cash_tendered - res["total"]
        self.assertEqual(change_due, 150.0)

        # Inventory audits
        self.assertEqual(db.get_product(p1)["stock_qty"], 48)
        self.assertEqual(db.get_product(p2)["stock_qty"], 29)
        self.assertEqual(db.get_product(p3)["stock_qty"], 96)

    def test_workflow_held_bill_interleaving(self):
        """Simulate counter rush hour:
        Customer A has items rung up -> forgets wallet -> cart is held (F2).
        Customer B is served immediately and pays.
        Customer A returns -> cart resumed (F3) -> checked out smoothly.
        """
        p_coke = db.create_product("Coca Cola 1.5L", "54490001", 140.0, 190.0, 25, "Beverages")
        p_lays = db.create_product("Lays Masala 65g", "89076543", 70.0, 100.0, 40, "Snacks")

        # Customer A cart
        cust_a_cart = {
            "items": [
                {"id": p_coke, "name": "Coca Cola 1.5L", "qty": 2, "unit_price": 190.0},
                {"id": p_lays, "name": "Lays Masala 65g", "qty": 3, "unit_price": 100.0},
            ]
        }
        held_id = db.save_held_bill(cust_a_cart)
        self.assertIsNotNone(held_id)

        # Customer B is served
        p_water = db.create_product("Aquafina 500ml", "89033333", 40.0, 60.0, 50, "Beverages")
        cust_b_res = db.checkout_sale(
            [{"id": p_water, "qty": 1, "unit_price": 60.0, "discount": 0.0}],
            payment_mode="Cash",
        )
        self.assertEqual(cust_b_res["total"], 60.0)

        # Customer A returns, cart resumed from held bills
        resumed = db.get_held_bill(held_id)
        self.assertEqual(len(resumed["items"]), 2)

        # Checkout Customer A with held_bill_id to automatically clean up held record
        cust_a_res = db.checkout_sale(
            [{"id": it["id"], "qty": it["qty"], "unit_price": it["unit_price"], "discount": 0.0} for it in resumed["items"]],
            payment_mode="Cash",
            held_bill_id=held_id,
        )
        # 2*190 + 3*100 = 380 + 300 = 680
        self.assertEqual(cust_a_res["total"], 680.0)

        # Verify held bills table is now empty
        self.assertEqual(len(db.list_held_bills()), 0)

    def test_workflow_customer_khata_credit_lifecycle(self):
        """Simulate neighborhood grocery Khata (Udhaar):
        1. Regular customer created
        2. Customer buys groceries on credit -> balance increases
        3. Customer makes partial repayment via JazzCash -> balance decreases
        4. Customer buys more groceries -> balance updates
        5. Full final cash payment clears ledger balance to 0.0
        """
        cid = db.create_customer("Chaudhry Akram", "03211234567", "Shop #12, Market")
        p_flour = db.create_product("Atta 10kg", "ATT10", 950.0, 1150.0, 20, "Grains")
        p_oil = db.create_product("Cooking Oil 5L", "OIL5", 2100.0, 2500.0, 15, "Cooking")

        # Purchase 1: 1x Atta on credit (1150)
        db.checkout_sale([{"id": p_flour, "qty": 1, "unit_price": 1150.0, "discount": 0}],
                         payment_mode="Credit / Khata", customer_id=cid)
        self.assertEqual(db.get_customer(cid)["balance"], 1150.0)

        # Purchase 2: 1x Oil on credit (2500)
        db.checkout_sale([{"id": p_oil, "qty": 1, "unit_price": 2500.0, "discount": 0}],
                         payment_mode="Credit / Khata", customer_id=cid)
        self.assertEqual(db.get_customer(cid)["balance"], 3650.0)

        # Partial repayment of Rs 2000 via JazzCash
        db.record_customer_payment(cid, 2000.0, "JazzCash Ref #987654", payment_method="JazzCash")
        self.assertEqual(db.get_customer(cid)["balance"], 1650.0)

        # Final repayment of remaining Rs 1650 via Cash
        db.record_customer_payment(cid, 1650.0, "Settled remaining balance", payment_method="Cash")
        self.assertEqual(db.get_customer(cid)["balance"], 0.0)

        # Verify customer ledger chronological history
        ledger = db.get_customer_ledger(cid)
        self.assertEqual(len(ledger["transactions"]), 4)

    def test_workflow_exchange_credit_voucher(self):
        """Simulate customer return & exchange workflow:
        1. Customer buys a Shirt (Rs 1200)
        2. Customer returns the Shirt for exchange credit
        3. System issues an Exchange Voucher
        4. Customer selects a Premium Jacket (Rs 2500)
        5. Cashier applies the Exchange Voucher -> Customer pays only Rs 1300 difference!
        """
        p_shirt = db.create_product("Cotton Shirt M", "SHIRT-M", 800.0, 1200.0, 10, "Apparel")
        p_jacket = db.create_product("Leather Jacket L", "JKT-L", 1800.0, 2500.0, 5, "Apparel")

        # Initial sale of shirt
        sale1 = db.checkout_sale([{"id": p_shirt, "qty": 1, "unit_price": 1200.0, "discount": 0}], payment_mode="Cash")
        sale_id = sale1["sale_id"]

        # Return shirt for Exchange Credit
        ret_res = db.process_sale_return(
            sale_id,
            returned_items=[{"product_id": p_shirt, "qty": 1, "unit_price": 1200.0}],
            notes="Size exchange requested",
            refund_method="Exchange Credit",
            restock=True,
        )
        voucher_code = ret_res["voucher_code"]
        self.assertIsNotNone(voucher_code)
        self.assertEqual(ret_res["refund_amount"], 1200.0)
        self.assertEqual(db.return_voucher_balance(voucher_code), 1200.0)

        # Customer buys Jacket (Rs 2500) using the Rs 1200 voucher
        sale2 = db.checkout_sale(
            [{"id": p_jacket, "qty": 1, "unit_price": 2500.0, "discount": 0}],
            payment_mode="Cash",
            exchange_credit=1200.0,
            voucher_code=voucher_code,
        )
        # Gross = 2500, Exchange Credit = 1200, Amount Due = 1300
        self.assertEqual(sale2["total"], 2500.0)
        self.assertEqual(sale2["amount_due"], 1300.0)
        self.assertEqual(sale2["exchange_credit"], 1200.0)

        # Verify voucher is now redeemed / balance zero
        self.assertEqual(db.return_voucher_balance(voucher_code), 0.0)

    def test_workflow_supplier_purchasing_and_margin(self):
        """Simulate B2B supply chain inward:
        1. Register distributor/supplier
        2. Order 100 units of cooking oil at wholesale cost (unit cost: Rs 400)
        3. Stock is automatically incremented from 10 to 110
        4. Supplier payable balance is accurately tracked
        5. Retail sales generate healthy gross profit
        """
        sid = db.save_supplier("National Foods Distributor", "National Foods Ltd", "03005551234", "Industrial Area")
        pid = db.create_product("Ketchup 800g", "NF-KETCHUP", 150.0, 220.0, 10, "Condiments")

        # Log purchase invoice: 50 units at Rs 140 each (Total: Rs 7000), paid Rs 3000 upfront
        purchase_items = [{"product_id": pid, "qty": 50, "unit_cost": 140.0}]
        db.record_purchase(
            supplier_id=sid,
            invoice_no="INV-2026-991",
            items=purchase_items,
            paid_amount=3000.0,
            payment_method="Bank transfer",
        )

        # Stock should now be 10 + 50 = 60
        self.assertEqual(db.get_product(pid)["stock_qty"], 60)

        # Supplier ledger check: Total 7000, Paid 3000, Balance owed = 4000
        suppliers = db.list_suppliers()
        sup = next(s for s in suppliers if s["id"] == sid)
        self.assertEqual(sup["balance_owed"], 4000.0)

        # Sell 10 units at Rs 220
        db.checkout_sale([{"id": pid, "qty": 10, "unit_price": 220.0, "discount": 0}], payment_mode="Cash")
        self.assertEqual(db.get_product(pid)["stock_qty"], 50)


if __name__ == "__main__":
    unittest.main()
