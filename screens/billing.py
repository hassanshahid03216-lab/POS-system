"""Fast, modern billing screen for ShopFlow POS with Barcode scanning, Cash Tendered calculator, Khata, and WhatsApp receipts."""

from __future__ import annotations

import webbrowser
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from db import db
from services.receipt_image import copy_receipt_image_to_clipboard, generate_receipt_image
from services.receipts import generate_whatsapp_url, print_or_save_receipt
from services.sound import play_error_beep, play_scan_beep, play_success_ding


def _set_visual_role(widget, role: str):
    """Apply a semantic theme role and refresh Qt's stylesheet match."""
    widget.setProperty("visualRole", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Worker(QRunnable):
    def __init__(self, operation: Callable[[], Any]):
        super().__init__()
        self.operation = operation
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            self.signals.done.emit(self.operation())
        except Exception as error:
            self.signals.failed.emit(error)


class _UnknownBarcodeDialog(QDialog):
    """Shown when a scanned barcode is not found in the product database.

    The cashier can:
      1. Link the barcode to an existing product (most common — fixes the
         mismatch between what the supplier/manufacturer printed vs what
         was entered manually).
      2. Register it as a completely new product.
      3. Dismiss / ignore.
    """

    # Result codes returned via self.result_action after exec()
    ACTION_LINK   = "link"    # link to existing product
    ACTION_NEW    = "new"     # add a new product with this barcode
    ACTION_CANCEL = "cancel"

    def __init__(self, barcode: str, products: list[dict], parent=None):
        super().__init__(parent)
        self.barcode = barcode
        self.products = products
        self.result_action = self.ACTION_CANCEL
        self.selected_product_id: int | None = None

        self.setWindowTitle("Unknown Barcode — پہچان نہیں ہوئی")
        self.setMinimumWidth(500)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(20, 20, 20, 20)

        # ── Header ────────────────────────────────────────────────
        icon_lbl = QLabel("🔍  Barcode Not Registered")
        root.addWidget(icon_lbl)

        bc_frame = QFrame()
        _set_visual_role(bc_frame, "inset")
        bc_lay = QVBoxLayout(bc_frame)
        bc_lay.setContentsMargins(14, 10, 14, 10)
        bc_caption = QLabel("Scanned Barcode (اسکین کیا گیا کوڈ):")
        bc_value = QLabel(barcode)
        bc_value.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        bc_lay.addWidget(bc_caption)
        bc_lay.addWidget(bc_value)
        root.addWidget(bc_frame)

        hint = QLabel(
            "یہ barcode ابھی کسی product سے linked نہیں ہے۔\n"
            "Option A: کسی existing product سے link کریں (صرف barcode update ہو گا)\n"
            "Option B: نیا product add کریں اس barcode کے ساتھ"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ── Option A: Link to existing ────────────────────────────
        sep_a = QLabel("─  Option A: Link to an Existing Product  ─")
        root.addWidget(sep_a)

        self.product_combo = QComboBox()
        self.product_combo.setPlaceholderText("Select product from list…")
        self.product_combo.addItem("— Select Product —", None)
        for p in sorted(products, key=lambda x: x.get("name", "")):
            current_bc = p.get("barcode") or "No barcode"
            self.product_combo.addItem(
                f"{p['name']}  (current barcode: {current_bc})",
                p["id"]
            )
        root.addWidget(self.product_combo)

        link_btn = QPushButton("🔗  Link Barcode to Selected Product")
        link_btn.setProperty('variant', 'primary')
        link_btn.clicked.connect(self._do_link)
        root.addWidget(link_btn)

        # ── Option B: Register new ────────────────────────────────
        sep_b = QLabel("─  Option B: Register as a New Product  ─")
        root.addWidget(sep_b)

        new_btn = QPushButton("➕  Add New Product with this Barcode")
        new_btn.clicked.connect(self._do_new)
        root.addWidget(new_btn)

        # ── Cancel ───────────────────────────────────────────────
        cancel_btn = QPushButton("Cancel — Continue Without Adding")
        cancel_btn.clicked.connect(self.reject)
        root.addWidget(cancel_btn)

    def _do_link(self):
        pid = self.product_combo.currentData()
        if pid is None:
            QMessageBox.warning(self, "Select a Product", "Please select a product from the list first.")
            return
        self.selected_product_id = pid
        self.result_action = self.ACTION_LINK
        self.accept()

    def _do_new(self):
        self.result_action = self.ACTION_NEW
        self.accept()


class _CheckoutDialog(QDialog):
    """Interactive checkout modal with Cash Tendered change calculator and Khata support."""

    def __init__(self, total_due: float, customers: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Checkout & Payment")
        self.setMinimumWidth(460)
        self.total_due = total_due
        self.customers = customers
        self.tendered_amount = total_due
        self.change_amount = 0.0

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Big Total Banner
        banner = QFrame()
        _set_visual_role(banner, "card")
        banner_lay = QVBoxLayout(banner)
        banner_lay.setContentsMargins(16, 14, 16, 14)
        due_lbl = QLabel("TOTAL PAYABLE AMOUNT")
        due_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_display = QLabel(f"Rs {total_due:,.2f}")
        _set_visual_role(self.total_display, "total")
        self.total_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner_lay.addWidget(due_lbl)
        banner_lay.addWidget(self.total_display)
        layout.addWidget(banner)

        form = QFormLayout()
        form.setSpacing(10)

        # Payment Mode
        self.payment_mode = QComboBox()
        self.payment_mode.addItems(["Cash", "Credit / Khata (خاتہ)", "Card", "JazzCash", "EasyPaisa"])
        self.payment_mode.currentTextChanged.connect(self._payment_mode_changed)
        form.addRow("Payment Mode:", self.payment_mode)

        # Customer selection
        self.customer_combo = QComboBox()
        self.customer_combo.addItem("Walk-in Customer (General)", None)
        for c in customers:
            bal = float(c.get("balance", 0))
            bal_str = f" [Khata: Rs {bal:,.0f}]" if bal > 0 else ""
            self.customer_combo.addItem(f"{c['name']} ({c.get('phone') or 'No Phone'}){bal_str}", c["id"])
        form.addRow("Customer:", self.customer_combo)

        # Cash Received & Change Box
        self.cash_frame = QFrame()
        _set_visual_role(self.cash_frame, "card")
        cash_box = QVBoxLayout(self.cash_frame)
        cash_box.setContentsMargins(12, 10, 12, 10)
        cash_box.setSpacing(8)

        cash_row = QHBoxLayout()
        cash_lbl = QLabel("💵  Cash Received:")
        cash_row.addWidget(cash_lbl)
        self.tendered_input = QDoubleSpinBox()
        self.tendered_input.setRange(0, 999_999_999)
        self.tendered_input.setDecimals(2)
        self.tendered_input.setPrefix("Rs ")
        self.tendered_input.setSpecialValueText(" ")
        self.tendered_input.setValue(0.0)
        self.tendered_input.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.tendered_input.valueChanged.connect(self._recalc_change)
        cash_row.addWidget(self.tendered_input, 1)
        cash_box.addLayout(cash_row)

        # Quick Note Presets
        quick_notes = QHBoxLayout()
        ql = QLabel("Quick:")
        quick_notes.addWidget(ql)
        exact_btn = QPushButton("Exact")
        exact_btn.setProperty("compact", True)
        exact_btn.clicked.connect(lambda: self.tendered_input.setValue(self.total_due))
        quick_notes.addWidget(exact_btn)
        for note in (500, 1000, 2000, 5000):
            btn = QPushButton(f"Rs {note:,}")
            btn.setProperty("compact", True)
            btn.clicked.connect(lambda _=False, val=note: self._quick_note_pressed(val))
            quick_notes.addWidget(btn)
        cash_box.addLayout(quick_notes)

        self.change_label = QLabel("Change Due (بقایا): Rs 0.00")
        _set_visual_role(self.change_label, 'secondary')
        cash_box.addWidget(self.change_label)
        layout.addWidget(self.cash_frame)

        layout.addLayout(form)

        # Buttons
        btn_box = QHBoxLayout()
        self.confirm_btn = QPushButton("Complete Sale & Print")
        self.confirm_btn.setProperty("variant", "primary")
        self.confirm_btn.setDefault(True)
        self.confirm_btn.clicked.connect(self._validate_and_accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.confirm_btn)
        layout.addLayout(btn_box)

        self._recalc_change()
        self.tendered_input.setFocus()
        self.tendered_input.selectAll()

    def _quick_note_pressed(self, val):
        current = self.tendered_input.value()
        # If current is 0 or less than total, set to note
        if current <= 0 or current < self.total_due:
            self.tendered_input.setValue(float(val))
        else:
            self.tendered_input.setValue(current + float(val))

    def _payment_mode_changed(self, mode):
        is_cash = mode == "Cash"
        self.cash_frame.setVisible(is_cash)
        if mode.startswith("Credit"):
            if self.customer_combo.currentIndex() == 0:
                # Prompt user to select a registered customer for credit
                if self.customer_combo.count() > 1:
                    self.customer_combo.setCurrentIndex(1)

    def _recalc_change(self):
        tendered = self.tendered_input.value()
        if tendered <= 0:
            self.change_amount = 0.0
            self.tendered_amount = self.total_due
            self.change_label.setText("Change Due (بقایا): Rs 0.00")
            _set_visual_role(self.change_label, 'secondary')
            return

        change = max(0.0, tendered - self.total_due)
        self.change_amount = change
        self.tendered_amount = tendered
        if tendered < self.total_due:
            remaining = self.total_due - tendered
            self.change_label.setText(f"⚠️  Short by (کم رقم): Rs {remaining:,.2f}")
            _set_visual_role(self.change_label, 'warning')
        else:
            self.change_label.setText(f"✅  Return Change (بقایا): Rs {change:,.2f}")
            _set_visual_role(self.change_label, 'success')

    def _validate_and_accept(self):
        mode = self.payment_mode.currentText()
        if mode.startswith("Credit") and self.customer_combo.currentData() is None:
            QMessageBox.warning(self, "Customer Required", "Credit / Khata sale requires selecting a registered Customer.")
            self.customer_combo.setFocus()
            return
        if mode == "Cash":
            tendered = self.tendered_input.value()
            if tendered <= 0:
                self.tendered_amount = self.total_due
                self.change_amount = 0.0
            elif tendered < self.total_due:
                confirm = QMessageBox.question(
                    self, "Insufficient Cash",
                    f"Cash received (Rs {tendered:,.2f}) is less than the total bill (Rs {self.total_due:,.2f}). Proceed anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if confirm != QMessageBox.StandardButton.Yes:
                    return
        self.accept()


class BillingScreen(QWidget):
    """Billing UI. Fast barcode scanning, customer Khata, cash change calculator, and WhatsApp receipts."""

    operation_done = Signal(object, object)
    operation_failed = Signal(object)
    receipt_done = Signal(object)
    columns = ("Product", "Qty", "Unit price", "Item discount", "Line total", "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self.products: list[dict] = []
        self.customers: list[dict] = []
        self.cart: list[dict] = []
        self.pending_exchange_credit = 0.0
        self.pending_voucher_code: str | None = None
        self.exchange_credit_applied = 0.0
        self.held_bill_id: int | None = None
        self.busy = False
        self._rendering = False

        self.operation_done.connect(self._finished)
        self.operation_failed.connect(self._failed)
        self.receipt_done.connect(self._receipt_result)

        self._build_ui()
        self._setup_shortcuts()
        self.reload_data()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Header Bar
        header = QHBoxLayout()
        title = QLabel("⚡ ShopFlow POS — Fast Billing")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #0F172A;")
        header.addWidget(title)

        # Hotkeys hint badge
        hotkeys_hint = QLabel("💡 F1=Search · ↑/↓=Select Item · +/-=Change Qty · Del=Remove · F12=Checkout")
        hotkeys_hint.setStyleSheet(
            "background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; "
            "border-radius: 6px; padding: 5px 12px; font-size: 12px; font-weight: 600;"
        )
        header.addStretch()
        header.addWidget(hotkeys_hint)
        voucher_btn = QPushButton("Redeem Store Voucher")
        voucher_btn.clicked.connect(self._redeem_voucher)
        header.addWidget(voucher_btn)
        root.addLayout(header)

        # Barcode & Search Input
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("📷  Scan barcode OR type product name → press Enter")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self._add_search_result)
        self.search.textChanged.connect(self._show_suggestions)
        self.search.setObjectName("barcode_input")
        self.search.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        self.search.setStyleSheet(
            "min-height: 42px; border: 2px solid #3B82F6; border-radius: 8px; "
            "padding: 6px 14px; font-size: 14px; background: #FFFFFF;"
        )
        self.search.installEventFilter(self)
        search_row.addWidget(self.search, 1)

        # Barcode scan indicator light
        self.scan_led = QLabel("●")
        _set_visual_role(self.scan_led, 'secondary')
        self.scan_led.setToolTip("Scan indicator — flashes green when a barcode is added")
        search_row.addWidget(self.scan_led)
        root.addLayout(search_row)

        self.suggestions = QListWidget()
        self.suggestions.setMaximumHeight(160)
        self.suggestions.itemActivated.connect(self._choose_suggestion)
        self.suggestions.installEventFilter(self)
        self.suggestions.hide()
        root.addWidget(self.suggestions)

        # Cart Items Table
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setFont(QFont("Segoe UI", 12))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.installEventFilter(self)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(self.columns)):
            header_view.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)

        # Checkout Summary & Action Card
        checkout_card = QFrame()
        checkout_card.setProperty("visualRole", "card")
        card_layout = QVBoxLayout(checkout_card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(10)

        # Bill Discount & Summary Bar
        summary_row = QHBoxLayout()
        disc_lbl = QLabel("Bill Discount:")
        disc_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        summary_row.addWidget(disc_lbl)
        self.bill_discount = QDoubleSpinBox()
        self.bill_discount.setRange(0, 99_999_999)
        self.bill_discount.setDecimals(2)
        self.bill_discount.setPrefix("Rs ")
        self.bill_discount.valueChanged.connect(self._update_totals)
        summary_row.addWidget(self.bill_discount)

        summary_row.addStretch()
        self.subtotal_label = QLabel("Subtotal: Rs 0.00")
        self.subtotal_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #64748B; padding-right: 12px;")
        self.discount_label = QLabel("Discount: Rs 0.00")
        self.discount_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #DC2626; padding-right: 12px;")
        self.total_label = QLabel("Total: Rs 0.00")
        self.total_label.setStyleSheet("font-size: 28px; font-weight: 900; color: #0F172A;")

        summary_row.addWidget(self.subtotal_label)
        summary_row.addWidget(self.discount_label)
        summary_row.addWidget(self.total_label)
        card_layout.addLayout(summary_row)

        # Action Buttons
        actions = QHBoxLayout()
        self.status = QLabel("Loading system…")
        self.status.setStyleSheet("color: #64748B; font-weight: 500;")
        actions.addWidget(self.status, 1)

        self.resume_button = QPushButton("📂 Resume (F3)")
        self.resume_button.clicked.connect(self._resume_bill)
        actions.addWidget(self.resume_button)

        self.new_button = QPushButton("🆕 New Bill (F4)")
        self.new_button.clicked.connect(self._new_bill)
        actions.addWidget(self.new_button)

        self.hold_button = QPushButton("⏸ Hold (F2)")
        self.hold_button.clicked.connect(self._hold_bill)
        actions.addWidget(self.hold_button)

        self.checkout_button = QPushButton("⚡  Checkout & Pay  (F12)")
        self.checkout_button.setDefault(True)
        self.checkout_button.setProperty('variant', 'primary')
        self.checkout_button.setStyleSheet("min-height: 44px; font-size: 15px; font-weight: bold; padding: 8px 24px;")
        self.checkout_button.clicked.connect(self._checkout)
        actions.addWidget(self.checkout_button)
        card_layout.addLayout(actions)

        root.addWidget(checkout_card)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("F1"), self, lambda: self.search.setFocus())
        QShortcut(QKeySequence("F2"), self, self._hold_bill)
        QShortcut(QKeySequence("F3"), self, self._resume_bill)
        QShortcut(QKeySequence("F4"), self, self._new_bill)
        QShortcut(QKeySequence("F12"), self, self._checkout)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._checkout)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self._checkout)
        # Quantity & item shortcuts
        QShortcut(QKeySequence("Ctrl+Up"), self, lambda: self._adjust_qty_for_current_row(1))
        QShortcut(QKeySequence("Ctrl+Down"), self, lambda: self._adjust_qty_for_current_row(-1))
        QShortcut(QKeySequence("Ctrl++"), self, lambda: self._adjust_qty_for_current_row(1))
        QShortcut(QKeySequence("Ctrl+-"), self, lambda: self._adjust_qty_for_current_row(-1))
        QShortcut(QKeySequence("Ctrl+Delete"), self, self._remove_current_item)

    def _flash_scan_led(self):
        """Flash the green scan indicator dot for 400 ms."""
        _set_visual_role(self.scan_led, 'success')
        QTimer.singleShot(400, self._reset_scan_led)

    def _reset_scan_led(self):
        _set_visual_role(self.scan_led, 'secondary')

    def reload_data(self):
        self._run(lambda: (db.list_products(), db.list_customers()), self._data_loaded)

    def _data_loaded(self, data):
        self.products, self.customers = data
        self.status.setText(f"{len(self.products)} products loaded — ready to scan or search")
        self.search.setFocus()

    def _run(self, operation, callback):
        if self.busy:
            return
        self.busy = True
        self._set_busy(True)
        worker = _Worker(operation)
        worker.signals.done.connect(lambda result: self.operation_done.emit(callback, result))
        worker.signals.failed.connect(self.operation_failed.emit)
        self._worker = worker
        self.pool.start(worker)

    def _finished(self, callback, result):
        self.busy = False
        self._set_busy(False)
        callback(result)

    def _failed(self, error):
        self.busy = False
        self._set_busy(False)
        self.status.setText(f"Operation failed: {error}")
        play_error_beep()
        QMessageBox.warning(self, "Billing Error", str(error))

    def _set_busy(self, busy):
        self.checkout_button.setEnabled(not busy)
        self.hold_button.setEnabled(not busy)
        self.resume_button.setEnabled(not busy)
        self.new_button.setEnabled(not busy)

    def _matches(self, text):
        query = text.strip().casefold()
        if not query:
            return []
        exact = [p for p in self.products if (p.get("barcode") or "").casefold() == query]
        if exact:
            return exact
        return [
            p for p in self.products
            if query in str(p.get("name", "")).casefold() or query in str(p.get("barcode") or "").casefold()
        ][:8]

    def _show_suggestions(self, text):
        matches = self._matches(text)
        self.suggestions.clear()
        for product in matches:
            stock = int(product.get("stock_qty") or 0)
            self.suggestions.addItem(f"{product['name']}  ·  Rs {float(product['sale_price']):,.2f}  ·  Stock: {stock}")
            self.suggestions.item(self.suggestions.count() - 1).setData(Qt.ItemDataRole.UserRole, product["id"])
        self.suggestions.setVisible(bool(matches))
        if matches:
            self.suggestions.setCurrentRow(0)

    @staticmethod
    def _looks_like_barcode(text: str) -> bool:
        """Return True if the input looks like a scanned barcode (digits-only, 4+ chars).

        A barcode reader always sends the digits then 'Enter'. A human typing
        a product name would normally include letters or be very short.
        """
        stripped = text.strip()
        return stripped.isdigit() and len(stripped) >= 4

    def _add_search_result(self):
        query = self.search.text().strip()
        if not query:
            return
        if self.suggestions.isVisible() and self.suggestions.currentItem():
            self._choose_suggestion(self.suggestions.currentItem())
            return
        matches = self._matches(query)
        if not matches:
            play_error_beep()
            # ── Smart check: does this look like a barcode scan? ──────────
            if self._looks_like_barcode(query):
                # Show the "Unknown Barcode" registration dialog
                self.search.clear()
                self.suggestions.hide()
                _set_visual_role(self.status, 'warning')
                self.status.setText(f"⚠️  Unknown barcode: {query} — opening registration…")
                self._handle_unknown_barcode(query)
            else:
                _set_visual_role(self.status, 'danger')
                self.status.setText(f"❌  No product found for: \"{query}\"")
            return
        exact = next((p for p in matches if (p.get("barcode") or "").casefold() == query.casefold()), None)
        self._add_product(exact or matches[0])

    def _handle_unknown_barcode(self, barcode: str):
        """Show the Unknown Barcode dialog and act on the user's choice."""
        dialog = _UnknownBarcodeDialog(barcode, self.products, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            _set_visual_role(self.status, 'secondary')
            self.status.setText(f"Barcode {barcode} skipped — add it to Inventory first.")
            self.search.setFocus()
            return

        if dialog.result_action == _UnknownBarcodeDialog.ACTION_LINK:
            # ── Link barcode to existing product ─────────────────────────
            pid = dialog.selected_product_id
            product_name = next(
                (p["name"] for p in self.products if p["id"] == pid), "?"
            )
            self.status.setText(f"Linking barcode {barcode} → {product_name}…")
            self._run(
                lambda: db.assign_barcode_to_product(pid, barcode),
                lambda _: self._barcode_linked(barcode, pid),
            )

        elif dialog.result_action == _UnknownBarcodeDialog.ACTION_NEW:
            # ── Open new product form pre-filled with barcode ─────────────
            from .products import _ProductForm
            form = _ProductForm(parent=self)
            form.barcode.setText(barcode)
            form.barcode.setReadOnly(True)       # barcode is already known
            if form.exec() == QDialog.DialogCode.Accepted:
                values = form.values()          # (name, barcode, cost, sale, stock, cat, threshold)
                self.status.setText(f"Registering new product…")
                self._run(
                    lambda: db.create_product(*values),
                    lambda _: self._new_product_registered(barcode),
                )
            else:
                _set_visual_role(self.status, 'secondary')
                self.status.setText("New product cancelled.")
                self.search.setFocus()

    def _barcode_linked(self, barcode: str, product_id: int):
        """Called after barcode is successfully saved to DB — reload data & add to cart."""
        play_success_ding()
        # Reload products so the updated barcode is in memory
        self._run(
            lambda: (db.list_products(), db.list_customers()),
            lambda data: self._after_link_data_loaded(data, barcode),
        )

    def _after_link_data_loaded(self, data, barcode: str):
        self.products, self.customers = data
        product = next((p for p in self.products if (p.get("barcode") or "") == barcode), None)
        if product:
            _set_visual_role(self.status, 'success')
            self.status.setText(f"✅  Barcode linked! Adding {product['name']} to cart…")
            self._add_product(product)
        else:
            _set_visual_role(self.status, 'secondary')
            self.status.setText("Barcode linked. Scan again to add to cart.")
        self.search.setFocus()

    def _new_product_registered(self, barcode: str):
        """Called after a new product is saved — reload and add to cart."""
        play_success_ding()
        self._run(
            lambda: (db.list_products(), db.list_customers()),
            lambda data: self._after_link_data_loaded(data, barcode),
        )


    def _choose_suggestion(self, item):
        if not item:
            return
        product_id = item.data(Qt.ItemDataRole.UserRole)
        product = next((p for p in self.products if p["id"] == product_id), None)
        if product:
            self._add_product(product)

    def _add_product(self, product):
        row = next((entry for entry in self.cart if entry["id"] == product["id"]), None)
        new_qty = (row["qty"] if row else 0) + 1
        stock_available = int(product.get("stock_qty") or 0)

        if new_qty > stock_available:
            play_error_beep()
            self.status.setText(f"Only {stock_available} in stock for {product['name']}")
            QMessageBox.warning(self, "Low Stock", f"Only {stock_available} items left in stock for '{product['name']}'.")
            return

        play_scan_beep()
        self._flash_scan_led()

        target_row = 0
        if row:
            row["qty"] = new_qty
            target_row = self.cart.index(row)
        else:
            self.cart.append({
                "id": product["id"],
                "name": product["name"],
                "barcode": product.get("barcode"),
                "qty": 1,
                "unit_price": float(product["sale_price"]),
                "discount": 0.0,
                "stock_qty": stock_available,
            })
            target_row = len(self.cart) - 1

        self.search.clear()
        self.suggestions.hide()
        self._render_cart(keep_row=target_row)
        _set_visual_role(self.status, 'success')
        self.status.setText(f"✅  Added: {product['name']} — Rs {float(product['sale_price']):,.2f}  [Press +/- to change qty]")
        self.search.setFocus()

    def _render_cart(self, keep_row: int | None = None):
        self._rendering = True
        prev_row = self.table.currentRow() if keep_row is None else keep_row
        self.table.setRowCount(len(self.cart))
        for row, entry in enumerate(self.cart):
            name = QTableWidgetItem(entry["name"])
            name.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.table.setItem(row, 0, name)

            qty = QSpinBox()
            qty.setRange(1, max(1, entry["stock_qty"]))
            qty.setValue(entry["qty"])
            qty.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
            qty.valueChanged.connect(lambda value, pid=entry["id"]: self._set_qty(pid, value))
            self.table.setCellWidget(row, 1, qty)

            price = QTableWidgetItem(f"Rs {entry['unit_price']:,.2f}")
            price.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, price)

            discount = QDoubleSpinBox()
            discount.setRange(0, entry["qty"] * entry["unit_price"])
            discount.setDecimals(2)
            discount.setPrefix("Rs ")
            discount.setValue(entry["discount"])
            discount.setFont(QFont("Segoe UI", 12))
            discount.valueChanged.connect(lambda value, pid=entry["id"]: self._set_item_discount(pid, value))
            self.table.setCellWidget(row, 3, discount)

            total = QTableWidgetItem(f"Rs {entry['qty'] * entry['unit_price'] - entry['discount']:,.2f}")
            total.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, total)

            remove = QPushButton("✕ Remove")
            remove.setProperty("compact", True)
            remove.setProperty('variant', 'danger')
            remove.clicked.connect(lambda _=False, pid=entry["id"]: self._remove_item(pid))
            self.table.setCellWidget(row, 5, remove)

        self._rendering = False
        self._update_totals()

        if self.cart:
            target = prev_row if (prev_row is not None and 0 <= prev_row < len(self.cart)) else (len(self.cart) - 1)
            self.table.selectRow(target)

    def _set_qty(self, product_id, qty):
        if self._rendering:
            return
        row_idx = next((i for i, item in enumerate(self.cart) if item["id"] == product_id), -1)
        if row_idx >= 0:
            entry = self.cart[row_idx]
            entry["qty"] = qty
            entry["discount"] = min(entry["discount"], qty * entry["unit_price"])
            tot_item = self.table.item(row_idx, 4)
            if tot_item:
                tot_item.setText(f"Rs {entry['qty'] * entry['unit_price'] - entry['discount']:,.2f}")
            disc_box = self.table.cellWidget(row_idx, 3)
            if isinstance(disc_box, QDoubleSpinBox):
                disc_box.setRange(0, entry["qty"] * entry["unit_price"])
            self._update_totals()

    def _set_item_discount(self, product_id, amount):
        if self._rendering:
            return
        row_idx = next((i for i, item in enumerate(self.cart) if item["id"] == product_id), -1)
        if row_idx >= 0:
            entry = self.cart[row_idx]
            entry["discount"] = amount
            tot_item = self.table.item(row_idx, 4)
            if tot_item:
                tot_item.setText(f"Rs {entry['qty'] * entry['unit_price'] - entry['discount']:,.2f}")
            self._update_totals()

    def _adjust_qty_for_current_row(self, delta: int):
        """Increase or decrease quantity of currently selected item (or latest item)."""
        if not self.cart:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.cart):
            row = len(self.cart) - 1

        self.table.selectRow(row)
        entry = self.cart[row]
        current_qty = entry["qty"]
        new_qty = current_qty + delta
        stock_available = int(entry.get("stock_qty") or 999999)

        if new_qty <= 0:
            item_name = entry["name"]
            self._remove_item(entry["id"])
            _set_visual_role(self.status, 'danger')
            self.status.setText(f"❌ Removed: {item_name}")
            return

        if new_qty > stock_available:
            play_error_beep()
            _set_visual_role(self.status, 'warning')
            self.status.setText(f"⚠️ Stock limit: only {stock_available} available for {entry['name']}")
            return

        # Update via the spinbox widget directly so visual number changes and signal fires
        spin = self.table.cellWidget(row, 1)
        if isinstance(spin, QSpinBox):
            spin.setValue(new_qty)
        else:
            self._set_qty(entry["id"], new_qty)

        play_scan_beep()
        line_tot = new_qty * entry["unit_price"] - entry["discount"]
        _set_visual_role(self.status, 'primary')
        self.status.setText(f"📦 {entry['name']}  ·  Qty: {new_qty}  (Rs {line_tot:,.2f})")

    def _remove_current_item(self):
        """Remove the currently selected item (or latest item) from cart."""
        if not self.cart:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.cart):
            row = len(self.cart) - 1
        entry = self.cart[row]
        self._remove_item(entry["id"])
        _set_visual_role(self.status, 'danger')
        self.status.setText(f"❌ Removed: {entry['name']} from cart")

    def _remove_item(self, product_id):
        self.cart = [item for item in self.cart if item["id"] != product_id]
        self._render_cart()
        self.search.setFocus()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            # ── 1. Search Bar Key Handling ──────────────────────────────────
            if obj == self.search:
                if self.suggestions.isVisible() and self.suggestions.count() > 0:
                    if event.key() == Qt.Key.Key_Down:
                        curr = self.suggestions.currentRow()
                        next_row = (curr + 1) if curr < self.suggestions.count() - 1 else 0
                        self.suggestions.setCurrentRow(next_row)
                        return True
                    elif event.key() == Qt.Key.Key_Up:
                        curr = self.suggestions.currentRow()
                        prev_row = (curr - 1) if curr > 0 else (self.suggestions.count() - 1)
                        self.suggestions.setCurrentRow(prev_row)
                        return True
                    elif event.key() == Qt.Key.Key_Escape:
                        self.suggestions.hide()
                        return True
                else:
                    # Suggestions are not visible
                    # When search box is empty, let user jump to cart or adjust qty
                    if not self.search.text().strip():
                        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Tab):
                            if self.cart:
                                self.table.setFocus()
                                target = self.table.currentRow()
                                if target < 0 or target >= len(self.cart):
                                    target = 0
                                self.table.selectRow(target)
                                return True
                        elif event.key() == Qt.Key.Key_Up:
                            if self.cart:
                                self.table.setFocus()
                                self.table.selectRow(len(self.cart) - 1)
                                return True
                        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal) or event.text() == "+":
                            self._adjust_qty_for_current_row(1)
                            return True
                        elif event.key() in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore) or event.text() == "-":
                            self._adjust_qty_for_current_row(-1)
                            return True
                        elif event.key() == Qt.Key.Key_Delete:
                            self._remove_current_item()
                            return True

            # ── 2. Suggestions List Key Handling ────────────────────────────
            elif obj == self.suggestions:
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    item = self.suggestions.currentItem()
                    if item:
                        self._choose_suggestion(item)
                    return True
                elif event.key() == Qt.Key.Key_Escape:
                    self.suggestions.hide()
                    self.search.setFocus()
                    return True
                elif event.key() == Qt.Key.Key_Up and self.suggestions.currentRow() == 0:
                    self.search.setFocus()
                    return True

            # ── 3. Cart Table Key Handling ──────────────────────────────────
            elif obj == self.table:
                if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Right) or event.text() == "+":
                    self._adjust_qty_for_current_row(1)
                    return True
                elif event.key() in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore, Qt.Key.Key_Left) or event.text() == "-":
                    self._adjust_qty_for_current_row(-1)
                    return True
                elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                    self._remove_current_item()
                    return True
                elif event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F1):
                    self.search.setFocus()
                    return True

        return super().eventFilter(obj, event)

    def _update_totals(self, *_):
        subtotal = sum(item["qty"] * item["unit_price"] for item in self.cart)
        item_discount = sum(item["discount"] for item in self.cart)
        bill_discount = min(self.bill_discount.value(), max(0, subtotal - item_discount))
        if bill_discount != self.bill_discount.value():
            self.bill_discount.blockSignals(True)
            self.bill_discount.setValue(bill_discount)
            self.bill_discount.blockSignals(False)
        self.subtotal_label.setText(f"Subtotal: Rs {subtotal:,.2f}")
        self.discount_label.setText(f"Discount: Rs {item_discount + bill_discount:,.2f}")
        total_before_voucher = max(0.0, subtotal - item_discount - bill_discount)
        self.exchange_credit_applied = min(self.pending_exchange_credit, total_before_voucher)
        self.total_label.setText(f"Total: Rs {total_before_voucher - self.exchange_credit_applied:,.2f}")

    def apply_exchange_credit(self, amount, voucher_code):
        if self.pending_voucher_code and self.pending_voucher_code != voucher_code and self.pending_exchange_credit > 0:
            QMessageBox.warning(self, "Voucher already selected", "Use or clear the current voucher before selecting another.")
            return
        self.pending_voucher_code = voucher_code
        self.pending_exchange_credit = db.return_voucher_balance(voucher_code)
        self._update_totals()
        self.status.setText(f"Voucher {voucher_code} selected with Rs {self.pending_exchange_credit:,.2f} available.")

    def _redeem_voucher(self):
        if self.pending_voucher_code and self.pending_exchange_credit > 0:
            QMessageBox.information(self, "Voucher selected", f"Voucher {self.pending_voucher_code} has Rs {self.pending_exchange_credit:,.2f} available and will apply to this or your next bill.")
            return
        code, ok = QInputDialog.getText(self, "Redeem store voucher", "Enter voucher code:")
        if not ok or not code.strip():
            return
        balance = db.return_voucher_balance(code)
        if balance <= 0:
            QMessageBox.warning(self, "Voucher not found", "This voucher is invalid or has no remaining balance.")
            return
        self.apply_exchange_credit(balance, code.strip().upper())

    def _hold_bill(self):
        if not self.cart or self.busy:
            self.status.setText("Add a product before holding this bill")
            return
        payload = {
            "items": [{k: item[k] for k in ("id", "name", "barcode", "qty", "unit_price", "discount")} for item in self.cart],
            "bill_discount": self.bill_discount.value(),
        }
        self.status.setText("Saving held bill…")
        self._run(lambda: db.save_held_bill(payload, self.held_bill_id), self._held)

    def _held(self, _held_id):
        self.held_bill_id = None
        self.cart = []
        self.bill_discount.setValue(0)
        self._render_cart()
        self.status.setText("Bill held successfully. You can start another sale or resume later (F3).")
        self.search.setFocus()

    def _resume_bill(self):
        if self.cart:
            QMessageBox.information(self, "Active Bill", "Please hold (F2) or checkout (F12) the current bill before resuming another.")
            return
        self._run(db.list_held_bills, self._choose_held_bill)

    def _choose_held_bill(self, held_bills):
        if not held_bills:
            self.status.setText("There are no held bills")
            return
        labels = [f"#{row['id']}: {row['label']} ({row['timestamp']})" for row in held_bills]
        label, ok = QInputDialog.getItem(self, "Resume Held Bill", "Choose a bill to resume:", labels, 0, False)
        if ok and label:
            held_id = held_bills[labels.index(label)]["id"]
            self._run(lambda: (held_id, db.get_held_bill(held_id)), self._restore_held_bill)

    def _restore_held_bill(self, result):
        held_id, payload = result
        if not payload:
            self.status.setText("That held bill is no longer available")
            return
        self.held_bill_id = held_id
        self.cart = []
        for old in payload.get("items", []):
            product = next((p for p in self.products if p["id"] == old["id"]), None)
            if product:
                self.cart.append({**old, "stock_qty": int(product.get("stock_qty") or 0)})
        self.bill_discount.setValue(float(payload.get("bill_discount", 0)))
        self._render_cart()
        self.status.setText("Held bill resumed.")
        self.search.setFocus()

    def _new_bill(self):
        if self.cart:
            answer = QMessageBox.question(
                self, "Start New Bill?", "Hold current bill before starting a new one?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._hold_bill()
                return
            elif answer == QMessageBox.StandardButton.Cancel:
                return
        self.cart = []
        self.held_bill_id = None
        self.bill_discount.setValue(0)
        self._render_cart()
        self.status.setText("Ready for next sale")
        self.search.setFocus()

    def _checkout(self):
        if not self.cart or self.busy:
            play_error_beep()
            self.status.setText("Cart is empty! Scan items first.")
            return

        subtotal = sum(item["qty"] * item["unit_price"] for item in self.cart)
        item_discount = sum(item["discount"] for item in self.cart)
        total_before_voucher = max(0.0, subtotal - item_discount - self.bill_discount.value())
        exchange_credit = min(self.pending_exchange_credit, total_before_voucher)
        total_due = total_before_voucher - exchange_credit

        # Open Interactive Checkout Dialog
        dialog = _CheckoutDialog(total_due=total_due, customers=self.customers, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        payment_mode = dialog.payment_mode.currentText()
        customer_id = dialog.customer_combo.currentData()
        customer_name = dialog.customer_combo.currentText().split(" (")[0] if customer_id else "Walk-in"
        tendered = dialog.tendered_amount
        change = dialog.change_amount

        items_payload = [{k: item[k] for k in ("id", "name", "barcode", "qty", "unit_price", "discount")} for item in self.cart]
        bill_discount = self.bill_discount.value()

        receipt_data = {
            "items": items_payload,
            "subtotal": subtotal,
            "discount": item_discount + bill_discount,
            "total": total_before_voucher,
            "amount_due": total_due,
            "payment_mode": payment_mode,
            "customer_id": customer_id,
            "customer_name": customer_name if customer_id else "",
            "tendered": tendered,
            "change": change,
            "voucher_credit": exchange_credit,
            "voucher_code": self.pending_voucher_code,
        }

        self.status.setText("Processing checkout…")
        self._run(
            lambda: db.checkout_sale(
                items=items_payload,
                payment_mode=payment_mode.split(" (")[0],
                bill_discount=bill_discount,
                held_bill_id=self.held_bill_id,
                customer_id=customer_id,
                exchange_credit=exchange_credit,
                voucher_code=self.pending_voucher_code if exchange_credit > 0 else None,
            ),
            lambda sale: self._sale_complete(sale, receipt_data),
        )

    def _sale_complete(self, sale, receipt):
        play_success_ding()
        used_credit = float(sale.get("exchange_credit", 0))
        self.pending_exchange_credit = max(0.0, self.pending_exchange_credit - used_credit)
        if self.pending_exchange_credit <= 0.005:
            self.pending_exchange_credit = 0.0
            self.pending_voucher_code = None
        receipt.update({
            "sale_id":   sale["sale_id"],
            "total":     sale["total"],
            "amount_due": sale["amount_due"],
            "discount":  sale["discount"],
            "voucher_credit": used_credit,
            "voucher_code": sale.get("voucher_code"),
            "timestamp": datetime.now().strftime("%d %b %Y  %I:%M %p"),
        })

        self.cart = []
        self.held_bill_id = None
        self.bill_discount.setValue(0)
        self._render_cart()
        _set_visual_role(self.status, 'success')
        self.status.setText(f"\u2705 Sale #{sale['sale_id']} complete \u2014 Rs {sale['amount_due']:,.2f}")

        # Generate image receipt immediately (~150ms)
        self._receipt_img_path: str | None = None
        try:
            self._receipt_img_path = generate_receipt_image(receipt)
            copy_receipt_image_to_clipboard(self._receipt_img_path)
        except Exception as e:
            print("Receipt image error:", e)

        # Background thermal print / PDF
        pr_worker = _Worker(lambda: print_or_save_receipt(receipt))
        pr_worker.signals.done.connect(self.receipt_done.emit)
        pr_worker.signals.failed.connect(
            lambda error: self.receipt_done.emit({"kind": "error", "message": str(error)})
        )
        self._worker = pr_worker
        self.pool.start(pr_worker)

        # ── Post-sale dialog ─────────────────────────────────────────────────
        change_val = float(receipt.get("change", 0))
        change_text = f"\n💵  Return Change: Rs {change_val:,.2f}" if change_val > 0 else ""

        msg = QMessageBox(self)
        msg.setWindowTitle("Sale Completed ✅")
        msg.setText(
            f"✅  Sale #{sale['sale_id']} recorded successfully!\n"
            f"Total: Rs {sale['total']:,.2f}{change_text}\n\n"
            f"📋 Digital Receipt Image is ready & COPIED to Clipboard!\n"
            f"Click 'Send on WhatsApp' → Press Ctrl+V in WhatsApp chat to paste the image."
        )
        wa_btn   = msg.addButton("📱  Send on WhatsApp", QMessageBox.ButtonRole.ActionRole)
        img_btn  = msg.addButton("🖼️  View Image", QMessageBox.ButtonRole.ActionRole)
        fld_btn  = msg.addButton("📁  Open Folder", QMessageBox.ButtonRole.ActionRole)
        ok_btn   = msg.addButton(QMessageBox.StandardButton.Ok)
        msg.setDefaultButton(wa_btn)
        msg.exec()

        clicked = msg.clickedButton()

        if clicked == wa_btn:
            # Re-copy to clipboard to guarantee it's active
            if self._receipt_img_path:
                copy_receipt_image_to_clipboard(self._receipt_img_path)

            customer_obj = next(
                (c for c in self.customers if c["id"] == receipt.get("customer_id")), None
            )
            phone = customer_obj.get("phone", "") if customer_obj else ""
            url = generate_whatsapp_url(receipt, phone_number=phone, include_full_text=False)
            webbrowser.open(url)

            _set_visual_role(self.status, 'primary')
            self.status.setText("📋 Receipt image copied! WhatsApp chat mein jaa kar Ctrl + V dabayein.")

            QMessageBox.information(
                self,
                "Paste Receipt Image 🖼️ (Ctrl + V)",
                "✅  WhatsApp khul gaya hai!\n\n"
                "📋 Receipt ki Image Clipboard mein copy ho chuki hai:\n\n"
                "👉 WhatsApp chat mein ja kar keyboard se [ Ctrl + V ] dabayein!\n"
                "👉 Image khud attach ho jayegi, phir Send (Enter) daba dein.\n\n"
                "(Aap 'Open Folder' se bhi image ko drag-and-drop kar sakte hain)"
            )

        elif clicked == img_btn:
            if self._receipt_img_path:
                import os as _os
                _os.startfile(self._receipt_img_path)
            else:
                self.status.setText("Receipt image not available.")

        elif clicked == fld_btn:
            if self._receipt_img_path:
                import subprocess
                subprocess.Popen(["explorer", f"/select,{self._receipt_img_path}"])

        self.reload_data()
        self.search.setFocus()

    def _receipt_image_ready(self, path: str):
        """Called when the PNG receipt has been saved."""
        self._receipt_img_path = path
        _set_visual_role(self.status, 'success')
        self.status.setText(f"\ud83d\uddbc\ufe0f  Receipt image saved: {path}")

    def _receipt_result(self, result):
        if result["kind"] == "error":
            self.status.setText(f"Sale complete. Receipt note: {result['message']}")
        else:
            self.status.setText(result["message"])
