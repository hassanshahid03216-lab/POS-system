"""ShopFlow POS — Factory Reset & Clean Production Database Initializer.

Clears all test/demo sales, returns, vouchers, customers, suppliers, and held bills,
leaving a pristine, factory-fresh database with default Admin user (PIN: 1234),
ready for real live store billing.
"""

import sys
from pathlib import Path
from db import db

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def reset_to_clean(keep_products=False):
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    print("[*] Performing database sanitization...")

    # Clear transaction tables
    cur.execute("DELETE FROM sale_return_items")
    cur.execute("DELETE FROM sale_returns")
    cur.execute("DELETE FROM return_vouchers")
    cur.execute("DELETE FROM return_stock_movements")
    cur.execute("DELETE FROM sale_items")
    cur.execute("DELETE FROM sales")
    cur.execute("DELETE FROM held_bills")
    cur.execute("DELETE FROM cash_closings")
    cur.execute("DELETE FROM cash_shifts")
    cur.execute("DELETE FROM cash_expenses")
    cur.execute("DELETE FROM customer_transactions")
    cur.execute("DELETE FROM customers")
    cur.execute("DELETE FROM purchase_items")
    cur.execute("DELETE FROM purchases")
    cur.execute("DELETE FROM supplier_transactions")
    cur.execute("DELETE FROM suppliers")
    cur.execute("DELETE FROM stock_movements")

    if not keep_products:
        cur.execute("DELETE FROM products")
        print("[*] Products catalog cleared.")
    else:
        # Reset product stocks to 0 if keeping catalog
        cur.execute("UPDATE products SET stock_qty = 0")
        print("[*] Products preserved, stock quantities reset to 0.")

    # Reset SQLite autoincrement sequences
    cur.execute("DELETE FROM sqlite_sequence WHERE name != 'users'")

    conn.commit()
    conn.close()

    print("[SUCCESS] Database is now factory clean and ready for real production!")
    print("  -> Default Login: Staff PIN 1234 (Admin)")
    print("  -> Transactions: 0")
    print("  -> Customers: 0")
    print("  -> Ready to import client's own product catalog CSV.")


if __name__ == "__main__":
    confirm = input("⚠️  WARNING: This will erase all sales, customers, and data. Type 'CLEAN' to confirm: ")
    if confirm.strip().upper() == "CLEAN":
        reset_to_clean(keep_products=False)
    else:
        print("Operation cancelled.")
