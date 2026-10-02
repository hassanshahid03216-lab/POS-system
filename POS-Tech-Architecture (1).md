# Technical Architecture — ShopFlow POS

## 1. Recommended Stack (Desktop, offline-first, low lag)

| Layer | Choice | Why |
|---|---|---|
| UI/App shell | **Python + PySide6 (Qt)** | Matches your existing Python stack; native rendering, no lag, no need to learn a new framework |
| Local DB | **SQLite** (built-in `sqlite3`) | Zero-config, instant local reads/writes, no lag, no server needed |
| ORM (optional) | SQLAlchemy or raw SQL | Raw SQL is fine and faster for a small local DB like this |
| Printing | `python-escpos` + `reportlab`/`fpdf2` for PDF fallback | Covers most cheap thermal printers used in shops |
| Barcode input | Treat scanner as keyboard (HID) input — no special driver needed | Cheapest, most compatible with shop hardware |
| Insights/analytics | Compute locally from SQLite (SQL aggregates) + `pyqtgraph` for charts | No backend needed, instant, stays inside the Qt UI |
| Licensing | Local license key + hardware fingerprint check (offline-verifiable) | No internet dependency for activation |
| Packaging | PyInstaller (`--onefile`) → Inno Setup installer | Simple .exe install for shop PCs |

**Later (Phase 2 — multi-branch/cloud):**
- FastAPI backend (matches your existing stack) + Postgres for a central dashboard
- Sync SQLite → cloud in background when internet is available (queue-based sync, not real-time dependency)

## 2. Why not Electron/web stack or Tkinter?
Electron apps are heavier (Chromium runtime) and tend to lag on the 4GB RAM / older PCs common in small shops — directly against your "no lag" requirement. PySide6 (Qt) renders natively and has a much smaller memory footprint. Tkinter would run fine too, but its UI looks dated — a weaker pitch when you're selling this in person to shop owners.

## 3. High-Level Architecture (MVP)

```
+-------------------------------------------+
|          Python (PySide6) Desktop App       |
|  ┌───────────┐ ┌────────────┐ ┌─────────┐ |
|  |  Billing  | | Inventory  | | Insights | |
|  |  Screen   | | Management | | Dashboard| |
|  └─────┬─────┘ └─────┬──────┘ └────┬─────┘ |
|        └─────────────┴─────────────┘       |
|                    │                       |
|            Local SQLite DB                  |
|      (products, sales, users, settings)     |
+-------------------------------------------+
        │ (optional, phase 2)
        ▼
   Background sync → FastAPI + Postgres (cloud dashboard)
```

## 4. Data Model (core tables)
- `products` (id, name, barcode, cost_price, sale_price, stock_qty, category, low_stock_threshold)
- `sales` (id, timestamp, cashier_id, total, discount, payment_mode)
- `sale_items` (sale_id, product_id, qty, unit_price)
- `users` (id, name, role, pin/password_hash)
- `stock_movements` (product_id, type [restock/sale/adjustment], qty, timestamp)

## 5. Build Order (matches PRD milestones)
1. SQLite schema (via Python's `sqlite3`) + product CRUD in PySide6
2. Billing screen (cart → checkout → sale_items + stock deduction, transactional)
3. Insights queries (SQL aggregates on `sales`/`sale_items`) + charts
4. Printing integration
5. Roles/login (simple PIN-based, not full auth — keep it fast for cashiers)
6. Backup/export (copy SQLite file + CSV export)
7. Installer packaging
