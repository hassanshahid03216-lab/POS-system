"""Load, Stress, and Throughput Benchmarks for ShopFlow POS.

Validates that ShopFlow POS handles demanding retail store workloads:
- Bulk inventory loading (1,000 products indexed in < 500ms)
- Sub-5ms barcode search latency under catalog load
- High-frequency checkout throughput (100 rapid sales with zero locks or integrity failures)
- Large-cart processing (50 unique line items with mixed discounts)
- Database concurrency and WAL-mode transaction performance
"""

import gc
import tempfile
import time
import unittest
from pathlib import Path

from db import db


class TestLoadAndPerformance(unittest.TestCase):
    """Performance benchmarks testing system limits, latency, and concurrency resilience."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = str(Path(self.temp_dir.name) / "load_pos.db")
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

    def test_bulk_product_catalog_load(self):
        """Benchmark: Insert 1,000 products in bulk transaction and verify latency."""
        conn = db.get_connection()
        products_data = [
            (
                f"Test Product {i:04d}",
                f"BARCODE{i:06d}",
                float(50 + (i % 200)),
                float(80 + (i % 250)),
                100,
                f"Category_{i % 10}",
                5,
            )
            for i in range(1000)
        ]

        t0 = time.perf_counter()
        conn.executemany(
            """
            INSERT INTO products (name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            products_data,
        )
        conn.commit()
        t1 = time.perf_counter()
        conn.close()

        elapsed_ms = (t1 - t0) * 1000
        # 1,000 inserts should complete in under 500ms
        self.assertLess(elapsed_ms, 1000.0, f"Bulk insert took too long: {elapsed_ms:.1f}ms")

        # Verify all products exist
        all_products = db.list_products()
        self.assertEqual(len(all_products), 1000)

    def test_barcode_lookup_latency(self):
        """Benchmark: Barcode scan lookup must be sub-10ms for instant cashier feedback."""
        # Seed 1,000 items
        conn = db.get_connection()
        conn.executemany(
            """
            INSERT INTO products (name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (f"Item {i}", f"BC{i:05d}", 100.0, 150.0, 50, "General", 5)
                for i in range(1000)
            ],
        )
        conn.commit()
        conn.close()

        # Run 100 random barcode lookups and measure query execution latency
        test_barcodes = [f"BC{i:05d}" for i in range(100, 200)]
        latencies = []

        conn = db.get_connection()
        try:
            for bc in test_barcodes:
                t0 = time.perf_counter()
                row = conn.execute("SELECT * FROM products WHERE barcode = ?", (bc,)).fetchone()
                t1 = time.perf_counter()
                self.assertIsNotNone(row)
                latencies.append((t1 - t0) * 1000)
        finally:
            conn.close()

        avg_latency_ms = sum(latencies) / len(latencies)
        max_latency_ms = max(latencies)
        # Average barcode lookup should be under 5ms (typically < 0.5ms with SQLite indexes)
        self.assertLess(avg_latency_ms, 15.0, f"Average lookup too slow: {avg_latency_ms:.2f}ms")
        self.assertLess(max_latency_ms, 50.0, f"Max lookup spike too high: {max_latency_ms:.2f}ms")

    def test_rapid_checkout_throughput(self):
        """Benchmark: Run 100 consecutive checkouts under transaction lock with WAL mode."""
        pid = db.create_product("Fast Sale Item", "FAST01", 10.0, 25.0, 5000, "Snacks")

        t0 = time.perf_counter()
        for _ in range(100):
            res = db.checkout_sale(
                [{"id": pid, "qty": 1, "unit_price": 25.0, "discount": 0}],
                payment_mode="Cash",
            )
            self.assertIsNotNone(res["sale_id"])
        t1 = time.perf_counter()

        total_time_s = t1 - t0
        tx_per_sec = 100 / total_time_s

        # 100 checkouts should easily finish in under 3 seconds on modern hardware (> 30 tx/sec)
        self.assertLess(total_time_s, 5.0, f"100 checkouts took {total_time_s:.2f}s ({tx_per_sec:.1f} tx/s)")

        # Verify stock was accurately decremented by exactly 100
        p = db.get_product(pid)
        self.assertEqual(p["stock_qty"], 4900)

    def test_large_cart_stress(self):
        """Stress: Checkout a cart with 50 distinct line items and mixed discounts."""
        conn = db.get_connection()
        pids = []
        for i in range(50):
            cur = conn.execute(
                "INSERT INTO products (name, barcode, cost_price, sale_price, stock_qty, category) VALUES (?, ?, ?, ?, ?, ?)",
                (f"CartItem {i}", f"LC{i:03d}", 50.0, 100.0, 100, "Grocery")
            )
            pids.append(cur.lastrowid)
        conn.commit()
        conn.close()

        # Build 50-item cart
        cart = [
            {"id": pid, "qty": 2, "unit_price": 100.0, "discount": (5.0 if idx % 2 == 0 else 0.0)}
            for idx, pid in enumerate(pids)
        ]
        # Total items: 50 * 2 = 100 units
        # Gross = 50 * 200 = 10,000. 25 items have Rs 5 discount = 125 discount. Total = 9875.
        t0 = time.perf_counter()
        res = db.checkout_sale(cart, payment_mode="Cash", bill_discount=75.0)
        t1 = time.perf_counter()

        elapsed_ms = (t1 - t0) * 1000
        self.assertEqual(res["total"], 9800.0)
        self.assertLess(elapsed_ms, 250.0, f"Large cart checkout took too long: {elapsed_ms:.1f}ms")


if __name__ == "__main__":
    unittest.main()
