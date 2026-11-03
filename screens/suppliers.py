"""Supplier directory, inward stock purchases, payments, and account ledger."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from db import db


class SupplierLedgerDialog(QDialog):
    """Interactive Ledger Dialog showing full transaction history and running balance."""

    def __init__(self, supplier: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Supplier Ledger - {supplier.get('name', 'Supplier')}")
        self.setMinimumWidth(650)
        self.setMinimumHeight(450)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header card
        header = QFrame()
        header.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
        h_lay = QHBoxLayout(header)

        title_box = QVBoxLayout()
        name_lbl = QLabel(f"<b>{supplier.get('name', '')}</b>")
        name_lbl.setStyleSheet("font-size: 16px; color: #0F172A;")
        details_lbl = QLabel(f"Company: {supplier.get('company') or 'N/A'} | Phone: {supplier.get('phone') or 'N/A'}")
        details_lbl.setStyleSheet("font-size: 12px; color: #64748B;")
        title_box.addWidget(name_lbl)
        title_box.addWidget(details_lbl)
        h_lay.addLayout(title_box)

        h_lay.addStretch()

        balance_box = QVBoxLayout()
        b_title = QLabel("Current Balance Owed:")
        b_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        balance = float(supplier.get("balance_owed", 0))
        b_val = QLabel(f"Rs {balance:,.2f}")
        b_val.setStyleSheet(
            f"font-size: 18px; font-weight: 800; color: {'#DC2626' if balance > 0 else '#16A34A'};"
        )
        balance_box.addWidget(b_title)
        balance_box.addWidget(b_val)
        h_lay.addLayout(balance_box)

        layout.addWidget(header)

        # Ledger Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Date & Time", "Type", "Amount", "Balance After", "Notes"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        # Populate Ledger
        entries = db.supplier_ledger(supplier["id"])
        self.table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            ts = e.get("timestamp", "").replace("T", " ")
            self.table.setItem(row, 0, QTableWidgetItem(ts))

            t_type = e.get("type", "").title()
            type_item = QTableWidgetItem(t_type)
            type_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            if e.get("type") == "payment":
                type_item.setForeground(QColor("#16A34A"))
            else:
                type_item.setForeground(QColor("#0284C7"))
            self.table.setItem(row, 1, type_item)

            amt = float(e.get("amount", 0))
            amt_item = QTableWidgetItem(f"Rs {amt:,.2f}")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, amt_item)

            bal = float(e.get("running_balance", 0))
            bal_item = QTableWidgetItem(f"Rs {bal:,.2f}")
            bal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            bal_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            if bal > 0:
                bal_item.setForeground(QColor("#DC2626"))
            else:
                bal_item.setForeground(QColor("#16A34A"))
            self.table.setItem(row, 3, bal_item)

            self.table.setItem(row, 4, QTableWidgetItem(e.get("notes") or ""))

        # Bottom row
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close Ledger")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


class SupplierPaymentDialog(QDialog):
    """Dialog to record payment to a supplier."""

    def __init__(self, supplier: dict, parent=None):
        super().__init__(parent)
        self.supplier = supplier
        self.setWindowTitle(f"Record Payment - {supplier.get('name', 'Supplier')}")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        info = QLabel(
            f"Recording payment to <b>{supplier.get('name')}</b><br/>"
            f"Current Balance Owed: <b style='color:#DC2626;'>Rs {float(supplier.get('balance_owed', 0)):,.2f}</b>"
        )
        info.setStyleSheet("font-size: 13px; color: #334155;")
        layout.addWidget(info)

        form = QGridLayout()
        form.setSpacing(8)

        form.addWidget(QLabel("Payment Amount (Rs):"), 0, 0)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.01, 999999999)
        self.amount.setDecimals(2)
        self.amount.setPrefix("Rs ")
        balance = float(supplier.get("balance_owed", 0))
        self.amount.setValue(balance if balance > 0 else 0)
        self.amount.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        form.addWidget(self.amount, 0, 1)

        pay_full_btn = QPushButton("Pay Full Balance")
        pay_full_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        pay_full_btn.clicked.connect(lambda: self.amount.setValue(float(supplier.get("balance_owed", 0))))
        form.addWidget(pay_full_btn, 0, 2)

        form.addWidget(QLabel("Payment Method:"), 1, 0)
        self.method = QComboBox()
        self.method.addItems(["Cash", "Bank transfer"])
        form.addWidget(self.method, 1, 1, 1, 2)

        form.addWidget(QLabel("Notes:"), 2, 0)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Check #, transfer ref, etc.")
        form.addWidget(self.notes, 2, 1, 1, 2)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save Payment")
        save_btn.setStyleSheet("background: #16A34A; color: white; font-weight: bold; padding: 6px 14px;")
        save_btn.clicked.connect(self._submit)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _submit(self):
        amount = self.amount.value()
        if amount <= 0:
            QMessageBox.warning(self, "Invalid Amount", "Payment amount must be greater than zero.")
            return
        try:
            db.record_supplier_payment(
                self.supplier["id"],
                amount,
                self.method.currentText(),
                self.notes.text().strip(),
            )
            QMessageBox.information(self, "Payment Recorded", f"Payment of Rs {amount:,.2f} recorded successfully.")
            self.accept()
        except Exception as error:
            QMessageBox.warning(self, "Payment Error", str(error))


class SuppliersScreen(QWidget):
    """Supplier management, directory, and purchase inward receiving screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.suppliers = []
        self.products = []
        self._editing_supplier_id = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        # Header
        title = QLabel("Suppliers & Purchasing")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #0F172A;")
        root.addWidget(title)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { font-size: 13px; font-weight: bold; padding: 8px 18px; margin-right: 4px; }
            QTabBar::tab:selected { background: #FFFFFF; border-bottom: 3px solid #0284C7; }
        """)
        self.tabs.addTab(self._build_directory_tab(), "🏢 Supplier Directory & Balances")
        self.tabs.addTab(self._build_purchase_tab(), "📦 Receive Stock / Purchase Inward")
        root.addWidget(self.tabs, 1)

        self.refresh()

    # ── TAB 1: Supplier Directory ───────────────────────────────────────────

    def _build_directory_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Add / Edit Supplier Card
        form_card = QFrame()
        form_card.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
        f_lay = QVBoxLayout(form_card)
        f_lay.setSpacing(8)

        self.form_title = QLabel("➕ Add New Supplier")
        self.form_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        f_lay.addWidget(self.form_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Supplier / Contact Name *")
        self.company = QLineEdit()
        self.company.setPlaceholderText("Company / Business Name")
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("Phone Number")
        self.address = QLineEdit()
        self.address.setPlaceholderText("Address / City")

        for f in (self.name, self.company, self.phone, self.address):
            f.setMinimumHeight(32)

        grid.addWidget(QLabel("Supplier Name:"), 0, 0); grid.addWidget(self.name, 0, 1)
        grid.addWidget(QLabel("Company:"), 0, 2); grid.addWidget(self.company, 0, 3)
        grid.addWidget(QLabel("Phone:"), 1, 0); grid.addWidget(self.phone, 1, 1)
        grid.addWidget(QLabel("Address:"), 1, 2); grid.addWidget(self.address, 1, 3)
        grid.setColumnStretch(1, 1); grid.setColumnStretch(3, 1)
        f_lay.addLayout(grid)

        act_row = QHBoxLayout()
        act_row.addStretch()
        self.cancel_edit_btn = QPushButton("Cancel")
        self.cancel_edit_btn.setVisible(False)
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)
        act_row.addWidget(self.cancel_edit_btn)

        self.save_supplier_btn = QPushButton("Save Supplier")
        self.save_supplier_btn.setStyleSheet(
            "background: #0284C7; color: white; font-weight: bold; padding: 6px 16px; border-radius: 5px;"
        )
        self.save_supplier_btn.clicked.connect(self._save_supplier)
        act_row.addWidget(self.save_supplier_btn)
        f_lay.addLayout(act_row)

        layout.addWidget(form_card)

        # Suppliers Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Supplier Name", "Company", "Phone", "Balance Owed", "Actions"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.verticalHeader().setMinimumSectionSize(40)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        return widget

    # ── TAB 2: Receive Stock / Purchase Inward ───────────────────────────────

    def _build_purchase_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Step 1: Invoice Header Card
        header_card = QFrame()
        header_card.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
        h_lay = QGridLayout(header_card)
        h_lay.setHorizontalSpacing(10)
        h_lay.setVerticalSpacing(6)

        h_lay.addWidget(QLabel("<b>1. Select Supplier:</b>"), 0, 0)
        self.supplier = QComboBox()
        self.supplier.setMaxVisibleItems(8)
        self.supplier.setStyleSheet("min-height: 32px; padding: 4px 8px;")
        h_lay.addWidget(self.supplier, 0, 1)

        h_lay.addWidget(QLabel("<b>Invoice #:</b>"), 0, 2)
        self.invoice = QLineEdit()
        self.invoice.setPlaceholderText("Invoice or Bill # (e.g. INV-104)")
        self.invoice.setStyleSheet("min-height: 32px; padding: 4px 8px;")
        h_lay.addWidget(self.invoice, 0, 3)

        layout.addWidget(header_card)

        # Step 2: Line Items Entry Card
        item_card = QFrame()
        item_card.setStyleSheet("background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 10px;")
        i_lay = QGridLayout(item_card)
        i_lay.setHorizontalSpacing(10)
        i_lay.setVerticalSpacing(6)

        i_lay.addWidget(QLabel("<b>2. Product:</b>"), 0, 0)
        self.product = QComboBox()
        self.product.setMaxVisibleItems(8)
        self.product.setStyleSheet("min-height: 32px; padding: 4px 8px;")
        self.product.currentIndexChanged.connect(self._on_product_selected)
        i_lay.addWidget(self.product, 0, 1, 1, 3)

        i_lay.addWidget(QLabel("Quantity:"), 1, 0)
        self.qty = QSpinBox()
        self.qty.setRange(1, 100000)
        self.qty.setValue(1)
        self.qty.setStyleSheet("min-height: 30px; font-weight: bold;")
        self.qty.valueChanged.connect(self._update_line_total)
        i_lay.addWidget(self.qty, 1, 1)

        i_lay.addWidget(QLabel("Unit Cost (Rs):"), 1, 2)
        self.cost = QDoubleSpinBox()
        self.cost.setRange(0, 100000000)
        self.cost.setDecimals(2)
        self.cost.setPrefix("Rs ")
        self.cost.setStyleSheet("min-height: 30px; font-weight: bold;")
        self.cost.valueChanged.connect(self._update_line_total)
        i_lay.addWidget(self.cost, 1, 3)

        self.line_total_lbl = QLabel("Line Total: Rs 0.00")
        self.line_total_lbl.setStyleSheet("font-weight: bold; color: #0F172A; font-size: 13px;")
        i_lay.addWidget(self.line_total_lbl, 1, 4)

        add_btn = QPushButton("➕ Add Item to List")
        add_btn.setStyleSheet(
            "background: #0284C7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 5px;"
        )
        add_btn.clicked.connect(self._add_line)
        i_lay.addWidget(add_btn, 1, 5)

        layout.addWidget(item_card)

        # Step 3: Purchase Items Table
        self.purchase_table = QTableWidget(0, 5)
        self.purchase_table.setHorizontalHeaderLabels(["Product Name", "Quantity", "Unit Cost", "Line Total", "Action"])
        self.purchase_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.purchase_table.verticalHeader().setVisible(False)
        self.purchase_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.purchase_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.purchase_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.purchase_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.purchase_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.purchase_table, 1)

        # Step 4: Settlement & Submit Bar
        summary_bar = QFrame()
        summary_bar.setStyleSheet("background: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 8px; padding: 10px;")
        s_lay = QHBoxLayout(summary_bar)
        s_lay.setSpacing(12)

        self.total_inv_lbl = QLabel("Total Invoice: <b>Rs 0.00</b>")
        self.total_inv_lbl.setStyleSheet("font-size: 15px; color: #0F172A;")
        s_lay.addWidget(self.total_inv_lbl)

        s_lay.addStretch()

        s_lay.addWidget(QLabel("Amount Paid:"))
        self.paid = QDoubleSpinBox()
        self.paid.setRange(0, 100000000)
        self.paid.setDecimals(2)
        self.paid.setPrefix("Rs ")
        self.paid.setStyleSheet("min-height: 32px; font-weight: bold;")
        self.paid.valueChanged.connect(self._update_balance_due)
        s_lay.addWidget(self.paid)

        pay_full_btn = QPushButton("Pay Full")
        pay_full_btn.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        pay_full_btn.clicked.connect(self._pay_full_invoice)
        s_lay.addWidget(pay_full_btn)

        s_lay.addWidget(QLabel("Method:"))
        self.purchase_method = QComboBox()
        self.purchase_method.addItems(["Cash", "Bank transfer"])
        self.purchase_method.setStyleSheet("min-height: 32px;")
        s_lay.addWidget(self.purchase_method)

        self.due_lbl = QLabel("Due: Rs 0.00")
        self.due_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #DC2626;")
        s_lay.addWidget(self.due_lbl)

        receive_btn = QPushButton("📥 Record Purchase & Inward Stock")
        receive_btn.setStyleSheet(
            "background: #16A34A; color: white; font-weight: bold; font-size: 13px; "
            "padding: 8px 18px; border-radius: 6px;"
        )
        receive_btn.clicked.connect(self._record_purchase)
        s_lay.addWidget(receive_btn)

        layout.addWidget(summary_bar)

        return widget

    # ── Refresh & Form Handlers ──────────────────────────────────────────────

    def refresh(self):
        # 1. Refresh Suppliers
        self.suppliers = db.list_suppliers()
        self.table.setRowCount(len(self.suppliers))
        self.supplier.clear()

        for i, item in enumerate(self.suppliers):
            self.table.setItem(i, 0, QTableWidgetItem(item["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(item.get("company") or ""))
            self.table.setItem(i, 2, QTableWidgetItem(item.get("phone") or ""))

            bal = float(item["balance_owed"])
            bal_item = QTableWidgetItem(f"Rs {bal:,.2f}")
            bal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            bal_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            if bal > 0:
                bal_item.setForeground(QColor("#DC2626"))
            else:
                bal_item.setForeground(QColor("#16A34A"))
            self.table.setItem(i, 3, bal_item)

            actions = QWidget()
            row = QHBoxLayout(actions)
            row.setContentsMargins(2, 0, 2, 0)
            row.setSpacing(4)

            pay = QPushButton("Pay")
            pay.setToolTip("Record payment to supplier")
            pay.setStyleSheet("font-size: 11px; padding: 2px 8px; background: #DCFCE7; color: #166534; font-weight: bold;")
            pay.clicked.connect(lambda _, s=item: self._pay(s))

            ledger = QPushButton("Ledger")
            ledger.setToolTip("View full account ledger")
            ledger.setStyleSheet("font-size: 11px; padding: 2px 8px; background: #E0F2FE; color: #0369A1; font-weight: bold;")
            ledger.clicked.connect(lambda _, s=item: self._ledger(s))

            edit = QPushButton("Edit")
            edit.setToolTip("Edit supplier details")
            edit.setStyleSheet("font-size: 11px; padding: 2px 8px;")
            edit.clicked.connect(lambda _, s=item: self._edit_supplier(s))

            row.addWidget(pay)
            row.addWidget(ledger)
            row.addWidget(edit)
            self.table.setCellWidget(i, 4, actions)

            display_name = f"{item['name']} (Balance: Rs {bal:,.2f})"
            self.supplier.addItem(display_name, item["id"])

        # 2. Refresh Products
        self.products = db.list_products()
        self.product.clear()
        for p in self.products:
            self.product.addItem(f"{p['name']} (Cost: Rs {float(p.get('cost_price', 0)):,.2f})", p["id"])

        self._on_product_selected()

    def _on_product_selected(self):
        p_id = self.product.currentData()
        if not p_id:
            return
        p = next((prod for prod in self.products if prod["id"] == p_id), None)
        if p:
            self.cost.setValue(float(p.get("cost_price", 0)))
            self._update_line_total()

    def _update_line_total(self):
        total = self.qty.value() * self.cost.value()
        self.line_total_lbl.setText(f"Line Total: Rs {total:,.2f}")

    def _pay_full_invoice(self):
        total_inv = sum(it["qty"] * it["unit_cost"] for it in self.items)
        self.paid.setValue(total_inv)

    def _update_balance_due(self):
        total_inv = sum(it["qty"] * it["unit_cost"] for it in self.items)
        due = max(0.0, total_inv - self.paid.value())
        self.due_lbl.setText(f"Due: Rs {due:,.2f}")

    def _add_line(self):
        p_id = self.product.currentData()
        if not p_id:
            QMessageBox.warning(self, "Product Required", "Please select a product first.")
            return

        p = next((prod for prod in self.products if prod["id"] == p_id), None)
        if not p:
            return

        qty = self.qty.value()
        cost = self.cost.value()
        line_total = qty * cost

        # Check if already in items list, update qty
        existing = next((it for it in self.items if it["product_id"] == p_id), None)
        if existing:
            existing["qty"] += qty
            existing["unit_cost"] = cost
        else:
            self.items.append({
                "product_id": p_id,
                "name": p["name"],
                "qty": qty,
                "unit_cost": cost,
            })

        self._render_purchase_table()

    def _render_purchase_table(self):
        self.purchase_table.setRowCount(len(self.items))
        total_inv = 0.0

        for row, it in enumerate(self.items):
            line_total = it["qty"] * it["unit_cost"]
            total_inv += line_total

            self.purchase_table.setItem(row, 0, QTableWidgetItem(it["name"]))

            qty_item = QTableWidgetItem(str(it["qty"]))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.purchase_table.setItem(row, 1, qty_item)

            cost_item = QTableWidgetItem(f"Rs {it['unit_cost']:,.2f}")
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.purchase_table.setItem(row, 2, cost_item)

            total_item = QTableWidgetItem(f"Rs {line_total:,.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            total_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.purchase_table.setItem(row, 3, total_item)

            del_btn = QPushButton("×")
            del_btn.setFixedSize(26, 26)
            del_btn.setStyleSheet("color: #DC2626; font-weight: bold; font-size: 14px;")
            del_btn.clicked.connect(lambda _=False, idx=row: self._remove_line(idx))
            self.purchase_table.setCellWidget(row, 4, del_btn)

        self.total_inv_lbl.setText(f"Total Invoice: <b>Rs {total_inv:,.2f}</b>")
        if self.paid.value() == 0 or self.paid.value() > total_inv:
            self.paid.setValue(total_inv)
        self._update_balance_due()

    def _remove_line(self, idx: int):
        if 0 <= idx < len(self.items):
            self.items.pop(idx)
            self._render_purchase_table()

    def _record_purchase(self):
        supplier_id = self.supplier.currentData()
        if not supplier_id:
            QMessageBox.warning(self, "Supplier Required", "Please select a supplier first.")
            return

        if not self.items:
            QMessageBox.warning(self, "No Items", "Please add at least one product to the inward purchase list.")
            return

        try:
            result = db.record_purchase(
                supplier_id=supplier_id,
                invoice_no=self.invoice.text().strip(),
                items=self.items,
                paid_amount=self.paid.value(),
                payment_method=self.purchase_method.currentText(),
            )
            QMessageBox.information(
                self,
                "Purchase Recorded",
                f"✅ Stock received and inventory updated successfully!\n\n"
                f"Total Inward: Rs {result['total']:,.2f}\n"
                f"Paid:         Rs {result['paid']:,.2f}\n"
                f"Added to Due: Rs {result['due']:,.2f}\n"
                f"Status:       {result['status']}"
            )
            self.items = []
            self.purchase_table.setRowCount(0)
            self.invoice.clear()
            self.paid.setValue(0)
            self.total_inv_lbl.setText("Total Invoice: <b>Rs 0.00</b>")
            self.due_lbl.setText("Due: Rs 0.00")
            self.refresh()
        except Exception as error:
            QMessageBox.warning(self, "Purchase Error", str(error))

    # ── Supplier Directory Actions ───────────────────────────────────────────

    def _save_supplier(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required", "Supplier name is required.")
            return

        try:
            db.save_supplier(
                name=name,
                company=self.company.text().strip(),
                phone=self.phone.text().strip(),
                address=self.address.text().strip(),
                supplier_id=self._editing_supplier_id,
            )
            msg = "Supplier updated successfully." if self._editing_supplier_id else "New supplier added successfully."
            QMessageBox.information(self, "Supplier Saved", msg)
            self._cancel_edit()
            self.refresh()
        except Exception as error:
            QMessageBox.warning(self, "Error Saving Supplier", str(error))

    def _edit_supplier(self, supplier: dict):
        self._editing_supplier_id = supplier["id"]
        self.name.setText(supplier.get("name") or "")
        self.company.setText(supplier.get("company") or "")
        self.phone.setText(supplier.get("phone") or "")
        self.address.setText(supplier.get("address") or "")
        self.form_title.setText(f"✏️ Edit Supplier: {supplier.get('name')}")
        self.save_supplier_btn.setText("Update Supplier")
        self.cancel_edit_btn.setVisible(True)
        self.name.setFocus()

    def _cancel_edit(self):
        self._editing_supplier_id = None
        self.name.clear()
        self.company.clear()
        self.phone.clear()
        self.address.clear()
        self.form_title.setText("➕ Add New Supplier")
        self.save_supplier_btn.setText("Save Supplier")
        self.cancel_edit_btn.setVisible(False)

    def _pay(self, supplier: dict):
        dialog = SupplierPaymentDialog(supplier, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _ledger(self, supplier: dict):
        dialog = SupplierLedgerDialog(supplier, self)
        dialog.exec()
