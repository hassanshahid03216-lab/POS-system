# ShopFlow POS — Feature List

A complete inventory of the features implemented in this codebase, derived directly from the source (`main.py`, `web_app.py`, `screens/`, `services/`, `db/db.py`). Two front-ends share the same SQLite database and business logic: a **PySide6 desktop app** (`main.py`) and a **Flask local web app** (`web_app.py`).

---

## 1. Authentication & Roles
- PIN-based login (4–8 digit numeric PIN), no usernames/passwords to type at the counter.
- Two roles: **Admin** (owner — full access) and **Cashier** (billing screen only).
- PINs stored hashed (`sha256$salt$digest`) with legacy-hash migration support.
- First-run "owner account setup" flow in the web app when no users exist yet.
- Staff management: add staff (name, role, PIN + confirm), list staff, delete staff (blocked if it's the last remaining account).
- Session-based auth for the web app (Flask session, CSRF token on every POST, admin-only route guard).

## 2. Billing / Point of Sale (core screen)
- Barcode scan input (keyboard-wedge scanner support) with a live scan indicator LED.
- Type-ahead product search with an autocomplete suggestions dropdown (keyboard navigable: ↑/↓/Tab/Esc).
- Automatic detection of "barcode-looking" input vs. name search.
- **Unknown barcode workflow**: when a scanned code isn't registered, a dialog lets the cashier either
  - link the barcode to an existing product, or
  - register a brand-new product pre-filled with that barcode.
- Cart table with per-line quantity (spinbox), unit price, per-item discount, and computed line total.
- Quantity adjustment directly from the cart (spinbox) with live stock-availability validation.
- Remove single line item from cart.
- Stock-limit guard — cannot add/increase quantity beyond available stock.
- Bill-level discount field (Rs) in addition to per-item discounts.
- Live subtotal / discount / total labels, recalculated on every change.
- **Payment modes**: Cash, Card, JazzCash, EasyPaisa, Credit / Khata.
- Cash-tendered calculator with automatic change-due computation, and quick "exact amount" note buttons.
- Credit/Khata checkout requires selecting a registered customer.
- **Hold Bill (F2)** — park the current cart (with bill discount) for later and start a new sale.
- **Resume Bill (F3)** — pull back a previously held bill, restoring cart lines and discount (guards against overwriting an active cart).
- **New Bill** — clears the cart, offering to hold the current one first if it's non-empty.
- **Checkout (F12)** — atomic transaction: validates stock, decrements inventory, records `sale_items` + `stock_movements`, updates customer balance for Khata sales, deletes the held-bill row if resuming.
- Keyboard shortcuts throughout (search ↔ cart navigation, hold/resume/checkout hotkeys).
- Audio feedback: scan beep, success ding (double chime), error beep — via Windows `winsound`.
- **Receipts after checkout**:
  - Auto-print to configured ESC/POS thermal printer, or fallback to a generated PDF receipt saved under `Documents/ShopFlow POS/Receipts`.
  - Auto-open the cash drawer (ESC/POS pulse command) on successful print.
  - Generate a branded PNG receipt image (dark themed) for digital sharing.
  - One-click **WhatsApp receipt**: copies the receipt image to the Windows clipboard and opens `wa.me` with the customer's number so the cashier just pastes (Ctrl+V) and sends.
  - Open the saved receipt file or reveal it in Explorer.
- **Exchange Credit flow**: refunds issued as "Exchange Credit" from Returns can be pushed straight into the Billing screen and auto-applied as a discount on the next/current sale.

## 3. Inventory / Product Management
- Product catalogue: name, barcode (unique), cost price, sale price, stock quantity, category, low-stock threshold.
- Add / Edit / Delete product dialogs with validation.
- Searchable/filterable product table (by category, by low-stock-only).
- Low-stock highlighting/alerts driven by each product's configurable threshold.
- Category list derived dynamically from existing products.
- **Bulk CSV import** — flexible column matching (`_find_field`) so varied spreadsheet headers still map correctly; reports imported / updated / skipped counts.
- **Bulk CSV export** of the full inventory.
- **Sample CSV template generator** so shop owners can fill it in Excel before importing.
- Barcode auto-assignment from the billing screen's "unknown barcode" dialog.

## 4. Customers / Khata (Credit Ledger)
- Customer directory: name, phone, address, running balance.
- Add / Edit / Delete customer (delete blocked while an outstanding balance exists).
- Per-customer ledger view: chronological list of `sale` (debit) and `payment` (credit) transactions with notes and running balance.
- **Receive Payment** dialog — record a cash or bank-transfer payment against a customer's Khata balance, with the current balance pre-filled as the suggested amount.
- Dashboard-wide "Total Khata Due" rollup across all customers.

## 5. Suppliers & Purchasing
- Supplier directory: name, company, phone, address, running balance owed.
- **Purchase inward workflow**: pick supplier, invoice number, add multiple product lines (product, qty, unit cost) into a purchase cart, then record the purchase — which increases stock and updates the supplier's balance.
- Partial-payment support at time of purchase (amount paid vs. amount due), payment method (Cash / Bank transfer).
- **Record supplier payment** later against outstanding dues.
- **Supplier ledger** — full purchase & payment history with running balance, shown in a summary dialog.

## 6. Sales Returns & Refunds (Wapasi / Exchange)
- Look up any past sale by Bill/Sale ID, or browse a "recent completed sales" table.
- Select which items (and quantities) from that sale are being returned.
- Multiple **refund methods**: Cash, Credit / Khata Adjustment, Store Credit Voucher, Exchange Credit.
- Automatic restocking of returned items back into inventory (`stock_movements` type `return`).
- Refund receipt generation (text, PDF/print, and PNG image) marked as a return document.
- WhatsApp sharing of the refund receipt, same clipboard-image flow as sales receipts.
- "Start Exchange in Billing" shortcut — jumps straight to the Billing screen and pre-loads the refund amount as usable Exchange Credit.

## 7. Cash Drawer / Day-End Closing
- **Open a cash shift**: cashier enters the opening float; shift is tied to the cashier's name/ID.
- Live shift summary while active: cash sales, Khata cash recoveries, cash refunds, petty-cash expenses, and the resulting **expected cash in drawer**.
- **Record petty-cash expense** mid-shift (amount + purpose note), instantly reflected in the expected-cash figure.
- **Close shift**: cashier counts physical cash, enters it, and the system computes the **variance** (short / over / balanced) versus expected.
- Auto-printed/PDF "Day End Cash Closing" receipt summarizing the whole shift.
- Manual cash-drawer "kick" (ESC/POS pulse) button independent of a sale, for testing/opening the drawer on demand.

## 8. Insights & Business Intelligence Dashboard
- Period switcher: **Today / This Week / This Month**.
- KPI cards: sales total and profit for Today, Week, and Month simultaneously.
- Stock value on hand (sum of `stock_qty × cost_price`).
- Total outstanding Khata (customer credit) due.
- **Top-selling products** bar chart for the selected period (via `pyqtgraph`).
- **Peak sale hours** line/point chart — hourly sale-count distribution across a 24-hour axis, useful for staffing decisions.
- **Smart Restock Advisor** table — products at/under their low-stock threshold, with a suggested reorder quantity and an estimated restock cost per item, plus a total estimated restock budget.
- **Slow-moving stock** table — items in stock with zero sales in the selected period.
- Manual "Refresh" button plus automatic refresh on period change.

## 9. Admin Settings
- **Shop profile**: shop name, phone, address, receipt footer text, currency symbol.
- **Hardware/printer settings**: detect available printers, select one, send a test print, and pulse the cash drawer independently.
- **Toggles**: enable/disable UI sound effects, enable/disable automatic database backup on app close.
- **Staff management** (see Auth & Roles) surfaced here for Admins.
- **Manual backup** — copy the live SQLite DB to a chosen folder (prioritizing detected removable/USB drives), stamped with date/time.
- **CSV sales export** for a chosen date range.

## 10. Data Safety, Backup & Reliability
- All data stored locally in SQLite (`pos.db`) — zero network dependency for core operation.
- Schema managed via `init_db()` with `CREATE TABLE IF NOT EXISTS` for products, sales, sale_items, users, stock_movements, held_bills, customers, customer_transactions, suppliers, supplier ledger/purchases, cash shifts/expenses, etc.
- Transactional writes (`BEGIN IMMEDIATE` / `commit` / `rollback`) for checkout, returns, purchases, and user creation to avoid partial/corrupt state.
- **Automatic backup on app close** (desktop app) to `Documents/ShopFlow POS/AutoBackups`, controlled by a settings toggle.
- **External/USB backup reminder** — nags the user (at most once/day, and only after 7+ days since the last external backup) to back up to a removable drive; detects mounted removable volumes automatically.
- One-click backup-to-folder (`db.backup_database`) using SQLite's native `backup()` API for a safe, consistent copy even while the app is running.
- Stock movement audit trail (`stock_movements`) for every sale, return, restock, or manual adjustment.

## 11. Receipts & Printing
- ESC/POS thermal printer support via `python-escpos` (`Win32Raw`), with automatic printer detection.
- Graceful **PDF fallback** (via `fpdf2`) whenever no printer is configured or printing fails — saved to `Documents/ShopFlow POS/Receipts`.
- Branded **PNG receipt image generator** (Pillow) with a dark themed layout, shop header, itemized lines, totals box, and footer — sized dynamically to content.
- Native Windows clipboard image copy (`win32clipboard` CF_DIB) plus a Qt-clipboard fallback, so the receipt image can be pasted directly into WhatsApp/any app.
- WhatsApp deep-link generation (`wa.me`) with the customer's phone number and either a short caption or full receipt text.
- Cash-drawer kick command bundled into both explicit "print receipt" and "test printer" flows.

## 12. Local Web App (Flask, `web_app.py`)
A secondary, browser-based interface over the same database/services:
- PIN login screen + first-run admin setup.
- Session-based auth with role-gated (`admin_only`) routes and CSRF-protected forms.
- Billing page — list products, checkout, hold/resume bills via HTTP routes.
- Product management — list, add, edit, delete products.
- Insights page — dashboard summary by period.
- Admin settings page — add users, configure shop/printer settings, test printer, trigger backup, export sales CSV as a file download.
- Consistent error pages for 403 (forbidden) and 400 (bad/expired form).

## 13. UI/UX Polish
- Global dark "Slate" theme applied consistently across every widget type (buttons, inputs, tables, dialogs, tabs, scrollbars, checkboxes, tooltips) via a shared Qt stylesheet (`services/theme.py`, mirrored in `main.py`).
- Bilingual (English/Urdu) hints and labels in places tuned for the Pakistani retail context (e.g. "Wapasi / Exchange", "Bika hua maal…" footer default, Khata/Udhaar terminology).
- Consistent color-coded status messaging (blue = info, green = success, amber = warning, red = error) across screens.
- Responsive multi-pane workspace shell (`_Workspace` in `screens/login.py`) that swaps between Billing, Inventory, Customers, Suppliers, Returns, Insights, and Settings, refreshing each screen's data on navigation.

---

### Tech Stack Reference
| Layer | Choice |
|---|---|

| Desktop UI | PySide6 (Qt) |
| Local web UI | Flask + Jinja templates |
| Database | SQLite (`sqlite3`, raw SQL) |
| Charts | `pyqtgraph` |
| Printing | `python-escpos` (ESC/POS) + `fpdf2` (PDF fallback) |
| Receipt images | Pillow |
| Clipboard | `pywin32` (`win32clipboard`) + Qt clipboard |
| Packaging | PyInstaller |

*(See `POS-PRD.md` and `POS-Tech-Architecture (1).md` for the original product/technical planning documents this app was built from.)*
