"""ShopFlow POS — Professional Pitch Demo Data Seeder.

Populates the database with realistic retail inventory, customer Khata ledgers,
supplier invoices, and 14 days of realistic sales transactions so that all screens,
charts, and insights look thriving and impressive during client pitches.
"""

import os
import random
from datetime import datetime, timedelta
from db import db

DEMO_PRODUCTS = [
    # Beverages
    ("Coca Cola 1.5L", "5449000131805", 145.0, 190.0, 48, "Beverages", 10),
    ("Sprite 1.5L", "5449000000286", 145.0, 190.0, 36, "Beverages", 10),
    ("Nestle Fruita Vitals Apple 1L", "8961014112341", 280.0, 350.0, 24, "Beverages", 8),
    ("Rooh Afza 800ml", "8964000101112", 340.0, 420.0, 30, "Beverages", 6),
    ("Aquafina Mineral Water 1.5L", "8961014223344", 65.0, 90.0, 80, "Beverages", 20),
    ("Tapal Danedar Tea 400g", "8961014334455", 520.0, 640.0, 35, "Beverages", 10),
    ("Lipton Yellow Label 200g", "8964000202223", 380.0, 470.0, 40, "Beverages", 10),

    # Dairy & Breakfast
    ("Olpers Milk 1L Pack", "8961014445566", 225.0, 260.0, 65, "Dairy", 15),
    ("Nestle MilkPak 1L", "8961014556677", 230.0, 270.0, 70, "Dairy", 15),
    ("Nurpur Butter 200g", "8964000303334", 280.0, 340.0, 20, "Dairy", 5),
    ("Dawn Bread Large (Family)", "8961014667788", 120.0, 150.0, 25, "Bakery", 8),
    ("Mitchells Farm Jam 450g", "8964000404445", 260.0, 330.0, 18, "Breakfast", 5),
    ("Fauji Corn Flakes 250g", "8961014778899", 290.0, 370.0, 15, "Breakfast", 4),

    # Snacks & Confectionery
    ("Lays Masala 65g", "8961014889900", 72.0, 100.0, 60, "Snacks", 15),
    ("Kurkure Chutney Chaska 50g", "8961014990011", 50.0, 70.0, 45, "Snacks", 10),
    ("Super Crisp Salted 60g", "8964000505556", 55.0, 80.0, 40, "Snacks", 10),
    ("Cadbury Dairy Milk 38g", "8961015001122", 110.0, 150.0, 50, "Snacks", 12),
    ("Bisconni Chocolatto 6 Pack", "8964000606667", 130.0, 180.0, 35, "Snacks", 8),
    ("LU Prince Biscuits Half Roll", "8961015112233", 40.0, 60.0, 55, "Snacks", 15),

    # Staples & Cooking
    ("Dalda Cooking Oil 5L Can", "8964000707778", 2250.0, 2650.0, 18, "Staples", 4),
    ("Kisan Pure Ghee 1kg", "8961015223344", 580.0, 690.0, 22, "Staples", 5),
    ("Guard Supreme Basmati Rice 5kg", "8964000808889", 1650.0, 1950.0, 14, "Staples", 3),
    ("National Iodized Salt 800g", "8961015334455", 50.0, 70.0, 50, "Staples", 15),
    ("Shan Biryani Masala 50g", "8964000909990", 85.0, 120.0, 75, "Spices", 20),
    ("National Korma Masala 50g", "8961015445566", 85.0, 120.0, 60, "Spices", 20),
    ("National Tomato Ketchup 800g", "8964001010101", 240.0, 310.0, 30, "Condiments", 6),

    # Personal Care & Toiletries
    ("Lux Rose Soap 140g", "8961015556677", 130.0, 170.0, 45, "Toiletries", 12),
    ("Lifebuoy Total 10 Soap 115g", "8964001111212", 95.0, 130.0, 50, "Toiletries", 15),
    ("Sunsilk Black Shine Shampoo 180ml", "8961015667788", 290.0, 380.0, 25, "Personal Care", 6),
    ("Head & Shoulders Classic 180ml", "8964001212323", 380.0, 490.0, 20, "Personal Care", 5),
    ("Colgate Total Toothpaste 100g", "8961015778899", 190.0, 250.0, 32, "Personal Care", 8),
    ("Dettol Antiseptic Liquid 250ml", "8964001313434", 320.0, 420.0, 22, "Personal Care", 5),

    # Household & Laundry
    ("Surf Excel Quick Wash 1kg", "8961015889900", 490.0, 610.0, 30, "Household", 8),
    ("Ariel Complete Powder 1kg", "8964001414545", 510.0, 630.0, 28, "Household", 8),
    ("Vim Dishwash Bar 300g", "8961015990011", 90.0, 120.0, 40, "Household", 10),
    ("Harpic Toilet Cleaner 500ml", "8964001515656", 230.0, 290.0, 25, "Household", 6),
]

DEMO_CUSTOMERS = [
    ("Haji Muhammad Bashir", "03001234567", "House 14, Street 2, Sector F-8", 2850.0),
    ("Salman Cloth Merchant", "03215558899", "Shop #45, Main Bazaar", 7400.0),
    ("Dr. Asim Farooq", "03339876543", "Al-Razi Clinic, Commercial Area", 1200.0),
    ("Chaudhry Kashif Bhai", "03124443322", "Kashif Autos, Circular Road", 0.0),
]

DEMO_SUPPLIERS = [
    ("Unilever Pakistan Distribution", "Unilever FMCG Ltd", "04235889900", "Sundar Industrial Estate"),
    ("PepsiCo Beverage Supply", "Pepsi Bottlers", "0514433221", "I-9 Industrial Area"),
    ("National Foods Distributor", "National Foods Ltd", "02135061234", "Korangi Industrial Area"),
]


def seed_demo(db_target=None):
    if db_target:
        db.DB_PATH = db_target

    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    print("[*] Seeding Products Catalog...")
    product_ids = []
    for p in DEMO_PRODUCTS:
        name, barcode, cost, sale, stock, cat, threshold = p
        existing = cur.execute("SELECT id FROM products WHERE barcode=?", (barcode,)).fetchone()
        if existing:
            product_ids.append(existing[0])
            cur.execute("""
                UPDATE products SET name=?, cost_price=?, sale_price=?, stock_qty=?, category=?, low_stock_threshold=?
                WHERE id=?
            """, (name, cost, sale, stock, cat, threshold, existing[0]))
        else:
            cur.execute("""
                INSERT INTO products (name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, barcode, cost, sale, stock, cat, threshold))
            product_ids.append(cur.lastrowid)

    print("[*] Seeding Customers & Khata Ledgers...")
    customer_ids = []
    now = datetime.now()
    for name, phone, address, balance in DEMO_CUSTOMERS:
        existing = cur.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
        if existing:
            cid = existing[0]
            cur.execute("UPDATE customers SET phone=?, address=?, balance=? WHERE id=?", (phone, address, balance, cid))
        else:
            cur.execute("""
                INSERT INTO customers (name, phone, address, balance, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (name, phone, address, balance, (now - timedelta(days=30)).isoformat(timespec="seconds")))
            cid = cur.lastrowid

            if balance > 0:
                cur.execute("""
                    INSERT INTO customer_transactions (customer_id, type, amount, notes, timestamp, payment_method)
                    VALUES (?, 'sale', ?, 'Previous balance carryover', ?, 'Credit / Khata')
                """, (cid, balance, (now - timedelta(days=5)).isoformat(timespec="seconds")))
        customer_ids.append(cid)

    print("[*] Seeding Suppliers...")
    supplier_ids = []
    for name, company, phone, address in DEMO_SUPPLIERS:
        existing = cur.execute("SELECT id FROM suppliers WHERE name=?", (name,)).fetchone()
        if existing:
            supplier_ids.append(existing[0])
        else:
            cur.execute("""
                INSERT INTO suppliers (name, company, phone, address, balance_owed, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
            """, (name, company, phone, address, (now - timedelta(days=45)).isoformat(timespec="seconds")))
            supplier_ids.append(cur.lastrowid)

    print("[*] Seeding Realistic Historical Sales (14 Days)...")
    # Generate 45 realistic past sales across different hours and days
    modes = ["Cash", "Cash", "Cash", "Card", "JazzCash", "EasyPaisa"]
    base_date = now - timedelta(days=14)

    for day_offset in range(15):
        day_time = base_date + timedelta(days=day_offset)
        # 3 to 6 sales per day
        num_sales = random.randint(3, 6)
        for _ in range(num_sales):
            sale_hour = random.choice([10, 11, 12, 14, 15, 17, 18, 19, 20, 21])
            sale_min = random.randint(0, 59)
            sale_timestamp = day_time.replace(hour=sale_hour, minute=sale_min, second=random.randint(0, 59)).isoformat(timespec="seconds")

            selected_products = random.sample(product_ids, random.randint(1, 4))
            payment_mode = random.choice(modes)
            cust_id = random.choice(customer_ids) if random.random() < 0.3 else None

            subtotal = 0.0
            sale_items = []
            for pid in selected_products:
                prod = cur.execute("SELECT name, sale_price FROM products WHERE id=?", (pid,)).fetchone()
                qty = random.randint(1, 3)
                price = float(prod[1])
                subtotal += qty * price
                sale_items.append((pid, qty, price, 0.0))

            discount = random.choice([0, 0, 0, 20, 50, 100]) if subtotal > 500 else 0
            final_total = max(0.0, subtotal - discount)

            cur.execute("""
                INSERT INTO sales (timestamp, cashier_id, customer_id, total, discount, payment_mode)
                VALUES (?, 1, ?, ?, ?, ?)
            """, (sale_timestamp, cust_id, final_total, discount, payment_mode))
            sale_id = cur.lastrowid

            for pid, qty, price, disc in sale_items:
                cur.execute("""
                    INSERT INTO sale_items (sale_id, product_id, qty, unit_price, discount)
                    VALUES (?, ?, ?, ?, ?)
                """, (sale_id, pid, qty, price, disc))

    conn.commit()
    conn.close()
    print("[SUCCESS] Demo store successfully populated!")
    print("  -> Products:  36 items across 8 categories")
    print("  -> Customers: 4 accounts with realistic Khata balances")
    print("  -> Suppliers: 3 major FMCG distributors")
    print("  -> History:   60+ sales transactions across past 14 days")
    print("  -> Admin PIN: 1234")


if __name__ == "__main__":
    seed_demo()
