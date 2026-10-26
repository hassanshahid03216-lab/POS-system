
# ShopFlow POS 🛒

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![UI Framework](https://img.shields.io/badge/GUI-PySide6%20(Qt6)-41CD52.svg)](https://wiki.qt.io/Qt_for_Python)
[![Web Framework](https://img.shields.io/badge/Web-Flask-black.svg)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/Database-SQLite3-003B57.svg)](https://www.sqlite.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#license)

**ShopFlow POS** is a lightning-fast, offline-first Point of Sale (POS) and inventory management system designed for retail shops, grocery stores, pharmacies, and small businesses. Built with **PySide6 (Qt6)** and **Python**, it delivers sub-second screen transitions and keyboard-driven workflows on everyday desktop PCs, completely free of subscriptions or mandatory internet connections.

---

## 🌟 Key Highlights

- **⚡ Sub-10-Second Checkout:** Designed for high-throughput counters. Supports barcode scanners (keyboard-wedge), type-ahead product lookup, and comprehensive keyboard hotkeys (`F2`, `F3`, `F12`).
- **📴 100% Offline-First:** Runs entirely locally on SQLite with atomic database transactions. No internet connection required for core billing, inventory, or ledger tracking.
- **📊 Real-Time Business Insights:** Built-in analytics dashboard featuring sales totals, profit calculation, stock valuation, peak sales hours visualization, and automated restock suggestions.
- **🧾 Thermal & Digital Receipts:** Native ESC/POS thermal printing with cash drawer pulse, PDF receipt fallback, and instant WhatsApp digital receipt sharing with clipboard integration.
- **👥 Khata (Credit Ledger) & Suppliers:** Complete credit ledger tracking for customers and inward purchasing tracking for suppliers with running balances.
- **🌐 Dual Desktop & Web Interfaces:** High-performance PySide6 desktop application for cashiers and an optional local Flask web interface for management across the local network.

---

## 🚀 Features Breakdown

### 1. Point of Sale & Billing
- **Barcode & Quick Search:** Automatic barcode detection, live scanning feedback LED, and instant search autocomplete.
- **Unknown Barcode Handling:** Register brand-new items or link scanned barcodes to existing inventory directly from the billing screen without interrupting checkout.
- **Flexible Cart & Discounts:** Line-item quantity editing with live stock limits, per-item discounts, and bill-level flat discounts.
- **Hold & Resume Bills:** Park an in-progress cart (`F2`) to serve another customer and resume it instantly (`F3`).
- **Multiple Payment Methods:** Supports Cash (with change-due calculator and quick cash notes), Card, JazzCash, EasyPaisa, and Credit / Khata.
- **Audio Feedback:** Native audio tones for barcode scans, successful checkouts, and validation errors.

### 2. Receipt Management & Hardware Integration
- **ESC/POS Thermal Printing:** Auto-detects connected thermal receipt printers with automatic cash-drawer kick.
- **PDF Fallback:** Automatically generates formatted PDF receipts in `Documents/ShopFlow POS/Receipts` if no printer is connected.
- **Digital WhatsApp Receipts:** Generates a branded PNG receipt image and copies it to the Windows clipboard while opening WhatsApp Web (`wa.me`) with pre-filled customer details.

### 3. Inventory & Stock Management
- **Product Catalog:** Manage barcodes, SKUs, cost prices, selling prices, stock quantities, categories, and low-stock alert thresholds.
- **Bulk CSV Import & Export:** Smart column-matching engine to import legacy Excel/CSV inventory files; includes a pre-formatted sample template.
- **Stock Audit Log:** Full audit trail tracking restocks, sales, returns, and manual stock corrections.

### 4. Customer Khata & Supplier Management
- **Customer Udhaar/Khata:** Dedicated credit accounts with chronological debit/credit transaction histories, balance statements, and partial repayment processing.
- **Supplier Inward Workflow:** Log purchase invoices with multiple line items, update stock and unit costs automatically, and track outstanding supplier payables.

### 5. Sales Returns & Exchanges (Wapasi)
- **Sale Lookup:** Search sales by bill number or browse recent transactions.
- **Itemized Returns:** Return specific line items and quantities back to inventory with audit logging.
- **Refund Flexibility:** Issue refunds via Cash, Khata adjustment, Store Credit voucher, or **Exchange Credit** that flows directly into the billing screen for the next purchase.

### 6. Cash Shift & Drawer Balancing
- **Day-End Closing:** Track opening float, mid-shift petty cash expenses, cash sales, Khata cash collections, and cash refunds.
- **Variance Calculation:** Reconcile expected cash vs. counted cash with automatic short/over computation and printable shift-closing reports.

### 7. Insights & Analytics
- **Live KPI Summary:** Sales and net profit for Today, This Week, and This Month.
- **Visual Analytics:** Interactive charts powered by `pyqtgraph` displaying peak traffic hours and top-selling products.
- **Smart Restock Advisor:** Highlights low-stock items, suggests reorder quantities, and estimates required restocking budgets.
- **Slow-Moving Inventory:** Identifies dead stock with zero sales in the selected period.

### 8. Security & Data Protection
- **Role-Based Access Control:** PIN-protected authentication (4–8 digits) with separate permissions for **Admin (Owner)** and **Cashier**.
- **Secure Password Hashing:** Powered by **PBKDF2-HMAC-SHA256** with per-user salt and 600,000 iterations, plus automatic rate-limiting lockout after repeated failed attempts.
- **Local SQLite Storage:** Uses transactional writes (`BEGIN IMMEDIATE`) to guard against data corruption during power loss.
- **Automated Backups:** Automatic database backups to `Documents/ShopFlow POS/AutoBackups` upon app exit, plus reminders for USB external backups.

---

## 🏗️ Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| **Desktop GUI** | [PySide6 (Qt6)](https://pypi.org/project/PySide6/) | High-performance, native desktop user interface |
| **Charts & Graphs** | [pyqtgraph](https://pypi.org/project/pyqtgraph/) | Fast real-time line and bar chart rendering |
| **Web Interface** | [Flask](https://flask.palletsprojects.com/) + Jinja2 | Lightweight local web application for network access |
| **Database** | [SQLite3](https://docs.python.org/3/library/sqlite3.html) | Zero-configuration, zero-latency relational database |
| **Thermal Printing** | [python-escpos](https://pypi.org/project/python-escpos/) | Direct ESC/POS printing and cash drawer firing |
| **PDF Generation** | [fpdf2](https://pypi.org/project/fpdf2/) | Lightweight receipt and report PDF creation |
| **Image Generation** | [Pillow](https://pypi.org/project/pillow/) | High-resolution receipt image generation for WhatsApp |
| **OS Integration** | [pywin32](https://pypi.org/project/pywin32/) | Windows clipboard and hardware integration |
| **Packaging** | [PyInstaller](https://pypi.org/project/pyinstaller/) | Standalone `.exe` packaging for Windows |

---

## 📂 Project Structure

```text
POS-system/
├── assets/                       # Sound effects and application icons
├── db/
│   └── db.py                     # SQLite database schema, queries, and business logic
├── models/                       # Data models and structures
├── screens/                      # PySide6 desktop UI screens
│   ├── billing.py                # Point of sale checkout interface
│   ├── customers.py              # Customer directory & Khata credit ledger
│   ├── insights.py               # Analytics, charts, and restock advisor
│   ├── inventory.py              # Product catalog and bulk CSV tools
│   ├── login.py                  # PIN authentication and workspace container
│   ├── returns.py                # Sales returns & exchange workflow
│   ├── settings.py               # Shop profile, hardware config & staff management
│   └── suppliers.py              # Supplier purchasing & ledger
├── services/                     # Shared application services
│   ├── receipt.py                # Thermal printing, PDF & PNG receipt generators
│   └── theme.py                  # Slate dark theme styling (QSS)
├── templates/                    # Flask HTML templates for web interface
├── app_settings.py               # JSON settings manager with atomic persistence
├── main.py                       # Desktop application entry point
├── web_app.py                    # Flask local web interface entry point
├── sample_products_template.csv  # Sample CSV for bulk product import
├── ShopFlowPOS.spec              # PyInstaller executable build specification
└── requirements.txt              # Project dependencies
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- **Operating System:** Windows 10 or Windows 11 (64-bit recommended)
- **Python:** Python 3.10, 3.11, or 3.12 installed ([Download Python](https://www.python.org/downloads/))

### 2. Clone the Repository
```bash
git clone https://github.com/hassanshahid03216-lab/POS-system.git
cd POS-system
```

### 3. Create a Virtual Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Or in Windows Command Prompt:
.venv\Scripts\activate.bat
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🖥️ Running the Application

### Launch the Desktop App
```bash
python main.py
```
> **Default Admin Account:** On the very first launch, the database (`pos.db`) will be automatically initialized with an Admin account (default PIN: `1234`). You can change this PIN or add staff accounts under **Settings > Staff Management**.

### Launch the Local Web App (Optional)
```bash
python web_app.py
```
Open your web browser and navigate to `http://localhost:5000`.

---

## 📦 Building Standalone Windows Executable

To bundle ShopFlow POS into a standalone Windows `.exe` that does not require Python to be installed:

```bash
pyinstaller ShopFlowPOS.spec
```
The compiled application will be generated in the `dist/ShopFlowPOS/` directory.

---

## ⌨️ Keyboard Shortcuts (Billing Screen)

| Shortcut | Action |
|---|---|
| `F2` | **Hold Bill:** Temporarily park the active cart |
| `F3` | **Resume Bill:** Retrieve and resume a parked cart |
| `F12` | **Checkout:** Complete transaction and print receipt |
| `Alt + N` | **New Bill:** Start a fresh transaction |
| `Tab` / `Enter` | Navigate between search field and cart items |
| `↑` / `↓` | Navigate autocomplete product suggestions |

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 👤 Author

Developed by **Hassan Shahid**  
- GitHub: [@hassanshahid03216-lab](https://github.com/hassanshahid03216-lab)
