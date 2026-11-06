"""Small DB-API compatibility layer for the application's PostgreSQL mode.

The desktop application still uses SQLite by default.  The cloud API process
sets DATABASE_URL and uses this module so the existing transaction-oriented
database functions can be shared by API requests.
"""

from __future__ import annotations

import re
from typing import Any


class HybridRow(dict):
    """A mapping row which also supports SQLite-style numeric indexing."""

    def __init__(self, values: tuple[Any, ...], columns: tuple[str, ...]):
        super().__init__(zip(columns, values))
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    columns = tuple(item.name for item in cursor.description) if cursor.description else ()
    return lambda values: HybridRow(values, columns)


class Cursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, sql: str, params=()):
        sql = _translate_sql(sql)
        match = re.match(r"\s*INSERT\s+INTO\s+([a-zA-Z_][\w]*)", sql, re.I)
        table = match.group(1).lower() if match else None
        has_returning = bool(re.search(r"\bRETURNING\b", sql, re.I))
        if table and table not in {"app_migrations", "sale_items"} and not has_returning:
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        self._cursor.execute(sql, params or ())
        self.rowcount = self._cursor.rowcount
        if table and table not in {"app_migrations", "sale_items"} and not has_returning:
            row = self._cursor.fetchone()
            self.lastrowid = row[0] if row else None
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)


class Connection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql: str, params=()):
        cursor = Cursor(self._connection.cursor(row_factory=_row_factory))
        return cursor.execute(sql, params)

    def cursor(self):
        return Cursor(self._connection.cursor(row_factory=_row_factory))

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def connect(database_url: str) -> Connection:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on install profile
        raise RuntimeError("Install psycopg[binary] to use PostgreSQL mode.") from exc
    return Connection(psycopg.connect(database_url, sslmode="require"))


def _translate_sql(sql: str) -> str:
    # The application's parameterized statements use SQLite's qmark style.
    sql = re.sub(r"^\s*BEGIN\s+IMMEDIATE\s*;?\s*$", "BEGIN", sql, flags=re.I)
    sql = sql.replace("?", "%s")
    sql = re.sub(r"date\(([^()]+)\)", r"CAST(\1::timestamp AS DATE)", sql, flags=re.I)
    sql = sql.replace("MAX(0.0, balance_owed-%s)", "GREATEST(0.0, balance_owed-%s)")
    sql = sql.replace(
        "GROUP_CONCAT(p.name || ' x' || si.qty, '; ')",
        "STRING_AGG(p.name || ' x' || si.qty::text, '; ')",
    )
    sql = re.sub(
        r"CAST\(strftime\('%H',\s*timestamp\)\s+AS\s+INTEGER\)",
        "CAST(EXTRACT(HOUR FROM timestamp::timestamp) AS INTEGER)", sql, flags=re.I,
    )
    sql = re.sub(
        r"strftime\('%H',\s*timestamp\)",
        "EXTRACT(HOUR FROM timestamp::timestamp)", sql, flags=re.I,
    )
    return sql


POSTGRES_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS products (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, barcode TEXT UNIQUE,
        cost_price DOUBLE PRECISION DEFAULT 0, sale_price DOUBLE PRECISION NOT NULL,
        stock_qty INTEGER DEFAULT 0, category TEXT, low_stock_threshold INTEGER DEFAULT 20)""",
    """CREATE TABLE IF NOT EXISTS sales (
        id BIGSERIAL PRIMARY KEY, timestamp TEXT NOT NULL, cashier_id BIGINT,
        customer_id BIGINT, total DOUBLE PRECISION NOT NULL DEFAULT 0,
        discount DOUBLE PRECISION DEFAULT 0, payment_mode TEXT,
        exchange_credit DOUBLE PRECISION NOT NULL DEFAULT 0, voucher_code TEXT)""",
    """CREATE TABLE IF NOT EXISTS sale_items (
        sale_id BIGINT NOT NULL, product_id BIGINT NOT NULL, qty INTEGER NOT NULL,
        unit_price DOUBLE PRECISION NOT NULL, discount DOUBLE PRECISION NOT NULL DEFAULT 0,
        PRIMARY KEY (sale_id, product_id), FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(id))""",
    """CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','cashier')), pin_hash TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS stock_movements (
        id BIGSERIAL PRIMARY KEY, product_id BIGINT NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('restock','sale','adjustment','return','damaged_return','write_off')),
        qty INTEGER NOT NULL, timestamp TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS held_bills (
        id BIGSERIAL PRIMARY KEY, label TEXT NOT NULL, payload TEXT NOT NULL, timestamp TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS customers (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, phone TEXT, address TEXT,
        balance DOUBLE PRECISION DEFAULT 0, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS customer_transactions (
        id BIGSERIAL PRIMARY KEY, customer_id BIGINT NOT NULL, sale_id BIGINT,
        type TEXT NOT NULL CHECK(type IN ('sale','payment','return')),
        amount DOUBLE PRECISION NOT NULL, notes TEXT, timestamp TEXT NOT NULL,
        payment_method TEXT NOT NULL DEFAULT 'Cash', FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS sale_returns (
        id BIGSERIAL PRIMARY KEY, sale_id BIGINT NOT NULL, timestamp TEXT NOT NULL,
        refund_amount DOUBLE PRECISION NOT NULL, notes TEXT, refund_method TEXT NOT NULL DEFAULT 'Cash',
        customer_id BIGINT, voucher_code TEXT, FOREIGN KEY(sale_id) REFERENCES sales(id))""",
    """CREATE TABLE IF NOT EXISTS sale_return_items (
        id BIGSERIAL PRIMARY KEY, return_id BIGINT NOT NULL, product_id BIGINT NOT NULL,
        qty INTEGER NOT NULL, refund_price DOUBLE PRECISION NOT NULL,
        FOREIGN KEY(return_id) REFERENCES sale_returns(id) ON DELETE CASCADE,
        FOREIGN KEY(product_id) REFERENCES products(id))""",
    """CREATE TABLE IF NOT EXISTS cash_closings (
        id BIGSERIAL PRIMARY KEY, timestamp TEXT NOT NULL, cashier_id BIGINT,
        cashier_name TEXT NOT NULL, opening DOUBLE PRECISION NOT NULL,
        expected DOUBLE PRECISION NOT NULL, actual DOUBLE PRECISION NOT NULL,
        discrepancy DOUBLE PRECISION NOT NULL, notes TEXT)""",
    """CREATE TABLE IF NOT EXISTS cash_shifts (
        id BIGSERIAL PRIMARY KEY, cashier_id BIGINT, cashier_name TEXT NOT NULL,
        opening DOUBLE PRECISION NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS cash_expenses (
        id BIGSERIAL PRIMARY KEY, amount DOUBLE PRECISION NOT NULL, notes TEXT, cashier_id BIGINT, timestamp TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS suppliers (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, company TEXT, phone TEXT,
        address TEXT, balance_owed DOUBLE PRECISION NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS purchases (
        id BIGSERIAL PRIMARY KEY, supplier_id BIGINT NOT NULL, invoice_no TEXT,
        timestamp TEXT NOT NULL, total_amount DOUBLE PRECISION NOT NULL,
        paid_amount DOUBLE PRECISION NOT NULL DEFAULT 0, payment_status TEXT NOT NULL,
        FOREIGN KEY(supplier_id) REFERENCES suppliers(id))""",
    """CREATE TABLE IF NOT EXISTS purchase_items (
        id BIGSERIAL PRIMARY KEY, purchase_id BIGINT NOT NULL, product_id BIGINT NOT NULL,
        qty INTEGER NOT NULL, unit_cost DOUBLE PRECISION NOT NULL,
        FOREIGN KEY(purchase_id) REFERENCES purchases(id), FOREIGN KEY(product_id) REFERENCES products(id))""",
    """CREATE TABLE IF NOT EXISTS supplier_transactions (
        id BIGSERIAL PRIMARY KEY, supplier_id BIGINT NOT NULL, purchase_id BIGINT,
        type TEXT NOT NULL CHECK(type IN ('purchase','payment','return')),
        amount DOUBLE PRECISION NOT NULL, notes TEXT, timestamp TEXT NOT NULL,
        FOREIGN KEY(supplier_id) REFERENCES suppliers(id))""",
    """CREATE TABLE IF NOT EXISTS return_vouchers (
        id BIGSERIAL PRIMARY KEY, return_id BIGINT NOT NULL UNIQUE, code TEXT NOT NULL UNIQUE,
        amount DOUBLE PRECISION NOT NULL, remaining DOUBLE PRECISION NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS return_stock_movements (
        id BIGSERIAL PRIMARY KEY, return_id BIGINT NOT NULL, product_id BIGINT NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('restock','damaged_return','write_off')),
        qty INTEGER NOT NULL, timestamp TEXT NOT NULL)""",
    "CREATE TABLE IF NOT EXISTS app_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)",
    "CREATE UNIQUE INDEX IF NOT EXISTS one_open_cash_shift ON cash_shifts ((true)) WHERE closed_at IS NULL",
)


def initialize(connection, seed_default_user: bool, hash_pin):
    cursor = connection.cursor()
    try:
        for statement in POSTGRES_SCHEMA:
            cursor.execute(statement)
        cursor.execute("UPDATE sales SET payment_mode='Online Payment' WHERE lower(replace(replace(replace(payment_mode,' ',''),'-',''),'_','')) IN ('jazzcash','easypaisa')")
        cursor.execute("UPDATE customer_transactions SET payment_method='Online Payment' WHERE lower(replace(replace(replace(payment_method,' ',''),'-',''),'_','')) IN ('jazzcash','easypaisa')")
        migration = "uniform_low_stock_threshold_20"
        if not cursor.execute("SELECT 1 FROM app_migrations WHERE name=?", (migration,)).fetchone():
            cursor.execute("UPDATE products SET low_stock_threshold=?", (20,))
            cursor.execute("INSERT INTO app_migrations (name, applied_at) VALUES (?, ?)", (migration, __import__('datetime').datetime.now().isoformat(timespec="seconds")))
        count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if seed_default_user and count == 0:
            cursor.execute("INSERT INTO users (name, role, pin_hash) VALUES (?, ?, ?)", ("Admin", "admin", hash_pin("1234")))
        connection.commit()
    except Exception:
        connection.rollback()
        raise

