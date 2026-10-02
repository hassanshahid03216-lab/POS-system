"""Customer Khata (Udhaar / Credit Ledger) Management screen."""

from __future__ import annotations

from typing import Any, Callable
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from db import db
from services.sound import play_success_ding, play_error_beep


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


class _CustomerForm(QDialog):
    def __init__(self, customer: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Customer" if customer else "Add New Customer")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name = QLineEdit(customer.get("name", "") if customer else "")
        self.name.setPlaceholderText("Customer full name")
        self.phone = QLineEdit(customer.get("phone", "") if customer else "")
        self.phone.setPlaceholderText("03001234567")
        self.address = QLineEdit(customer.get("address", "") if customer else "")
        self.address.setPlaceholderText("Shop/Home address")

        form.addRow("Name *", self.name)
        form.addRow("Phone", self.phone)
        form.addRow("Address", self.address)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        save = QPushButton("Save Customer")
        save.setDefault(True)
        save.clicked.connect(self._validate)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _validate(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Required", "Customer name cannot be empty.")
            self.name.setFocus()
            return
        self.accept()


class _PaymentDialog(QDialog):
    def __init__(self, customer: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Receive Payment — {customer['name']}")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)

        info = QLabel(f"Current Balance Due: <b>Rs {float(customer.get('balance', 0)):,.2f}</b>")
        info.setStyleSheet("font-size: 15px; color: #b91c1c; padding: 6px 0;")
        layout.addWidget(info)

        form = QFormLayout()
        self.amount = QDoubleSpinBox()
        self.amount.setRange(1, 999_999_999)
        self.amount.setDecimals(2)
        self.amount.setPrefix("Rs ")
        self.amount.setValue(max(1.0, float(customer.get("balance", 0))))
        self.notes = QLineEdit("Cash payment received")
        self.method = QComboBox()
        self.method.addItems(["Cash", "Bank transfer"])

        form.addRow("Amount Paid *", self.amount)
        form.addRow("Received via", self.method)
        form.addRow("Note/Remarks", self.notes)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        pay = QPushButton("Record Payment (وصولی)")
        pay.setDefault(True)
        pay.setStyleSheet("background: #15803d; color: white; font-weight: bold; padding: 8px 16px;")
        pay.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(pay)
        layout.addLayout(buttons)


class CustomerKhataScreen(QWidget):
    operation_done = Signal(object, object)
    operation_failed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self.customers: list[dict] = []
        self.selected_customer: dict | None = None
        self.busy = False

        self.operation_done.connect(self._finished)
        self.operation_failed.connect(self._failed)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Header
        top_bar = QHBoxLayout()
        title = QLabel("👥 Customer Khata (Udhaar / Credit Ledger)")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px;")
        top_bar.addWidget(title)
        top_bar.addStretch()

        self.total_due_badge = QLabel("Total Market Khata: Rs 0.00")
        self.total_due_badge.setStyleSheet(
            "background: #FEF2F2; color: #B91C1C; padding: 6px 14px; "
            "border-radius: 6px; font-weight: bold; font-size: 14px; border: 1px solid #FCA5A5;"
        )
        top_bar.addWidget(self.total_due_badge)

        add_btn = QPushButton("+ New Customer")
        add_btn.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 7px 14px;")
        add_btn.clicked.connect(self._add_customer)
        top_bar.addWidget(add_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        top_bar.addWidget(refresh_btn)
        root.addLayout(top_bar)

        # Search Bar
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search customer by name or phone...")
        self.search.textChanged.connect(self._filter_customers)
        self.search.setClearButtonEnabled(True)
        search_row.addWidget(self.search)
        root.addLayout(search_row)

        # Split: Left (Customer Table) - Right (Ledger Details)
        split = QHBoxLayout()
        split.setSpacing(16)

        # Left Column: Customer List Card
        left_card = QFrame()
        left_card.setProperty("visualRole", "card")
        left_box = QVBoxLayout(left_card)
        left_box.setContentsMargins(14, 14, 14, 14)
        left_box.setSpacing(10)

        left_label = QLabel("👥 Customer Directory")
        left_label.setStyleSheet("font-weight: 700; color: #0F172A; font-size: 14px;")
        left_box.addWidget(left_label)

        self.customer_table = QTableWidget(0, 4)
        self.customer_table.setHorizontalHeaderLabels(["Name", "Phone", "Khata Balance", "Actions"])
        self.customer_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.customer_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.customer_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.customer_table.verticalHeader().setVisible(False)
        self.customer_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.customer_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.customer_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.customer_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.customer_table.itemSelectionChanged.connect(self._customer_selected)
        left_box.addWidget(self.customer_table, 1)
        split.addWidget(left_card, 3)

        # Right Column: Customer Ledger Card
        self.right_frame = QFrame()
        self.right_frame.setProperty("visualRole", "card")
        right_box = QVBoxLayout(self.right_frame)
        right_box.setContentsMargins(16, 16, 16, 16)
        right_box.setSpacing(12)

        self.ledger_title = QLabel("Select a customer to view ledger")
        self.ledger_title.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #0F172A; padding: 4px 0;"
        )
        right_box.addWidget(self.ledger_title)

        self.ledger_balance = QLabel("Balance Due: Rs 0.00")
        self.ledger_balance.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #64748B; background: #F1F5F9; "
            "border: 1px solid #CBD5E1; border-radius: 8px; padding: 10px 14px;"
        )
        right_box.addWidget(self.ledger_balance)

        ledger_actions = QHBoxLayout()
        self.pay_btn = QPushButton("Receive Payment (وصولی)")
        self.pay_btn.setStyleSheet(
            "background: #15803D; color: white; font-weight: bold; padding: 8px 14px; border-radius: 6px;"
        )
        self.pay_btn.clicked.connect(self._receive_payment)
        self.pay_btn.setEnabled(False)
        ledger_actions.addWidget(self.pay_btn)

        self.edit_btn = QPushButton("Edit Info")
        self.edit_btn.setStyleSheet("padding: 8px 14px; border-radius: 6px;")
        self.edit_btn.clicked.connect(self._edit_customer)
        self.edit_btn.setEnabled(False)
        ledger_actions.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setStyleSheet(
            "color: #DC2626; border: 1px solid #FCA5A5; background: #FEF2F2; padding: 8px 14px; border-radius: 6px;"
        )
        self.delete_btn.clicked.connect(self._delete_customer)
        self.delete_btn.setEnabled(False)
        ledger_actions.addWidget(self.delete_btn)
        right_box.addLayout(ledger_actions)

        txn_lbl = QLabel("Transaction History (Khata Ledger):")
        txn_lbl.setStyleSheet("font-weight: 700; color: #1E293B; font-size: 13px; margin-top: 6px;")
        right_box.addWidget(txn_lbl)
        self.tx_table = QTableWidget(0, 4)
        self.tx_table.setHorizontalHeaderLabels(["Date/Time", "Type", "Amount", "Note"])
        self.tx_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tx_table.verticalHeader().setVisible(False)
        self.tx_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tx_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tx_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tx_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        right_box.addWidget(self.tx_table, 1)

        split.addWidget(self.right_frame, 4)
        root.addLayout(split, 1)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #64748b; font-weight: 500;")
        root.addWidget(self.status)

    def refresh(self):
        self._run(db.list_customers, self._customers_loaded)

    def _run(self, operation, callback):
        if self.busy:
            return
        self.busy = True
        worker = _Worker(operation)
        worker.signals.done.connect(lambda res: self.operation_done.emit(callback, res))
        worker.signals.failed.connect(self.operation_failed.emit)
        self._worker = worker
        self.pool.start(worker)

    def _finished(self, callback, result):
        self.busy = False
        callback(result)

    def _failed(self, error):
        self.busy = False
        self.status.setText(f"Error: {error}")
        play_error_beep()
        QMessageBox.warning(self, "Khata Error", str(error))

    def _reset_ledger(self):
        self.selected_customer = None
        self.ledger_title.setText("Select a customer to view ledger")
        self.ledger_balance.setText("Balance Due: Rs 0.00")
        self.ledger_balance.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #64748B; background: #F1F5F9; "
            "border: 1px solid #CBD5E1; border-radius: 8px; padding: 10px 14px;"
        )
        self.pay_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.tx_table.setRowCount(0)

    def _customers_loaded(self, customers):
        self.customers = customers
        # Only show customers with non-zero khata balance (cleared ones are hidden)
        active_khata = [c for c in customers if float(c.get("balance", 0)) != 0]
        self._render_customers(active_khata)
        if self.selected_customer:
            updated = next((c for c in active_khata if c["id"] == self.selected_customer["id"]), None)
            if updated:
                self.selected_customer = updated
                self._load_ledger(updated)
            else:
                self._reset_ledger()

    def _filter_customers(self, text):
        query = text.strip().casefold()
        # Always filter out zero-balance customers from khata view
        active = [c for c in self.customers if float(c.get("balance", 0)) != 0]
        if not query:
            self._render_customers(active)
            return
        filtered = [
            c for c in active
            if query in c["name"].casefold() or query in (c.get("phone") or "").casefold()
        ]
        self._render_customers(filtered)

    def _render_customers(self, customer_list):
        total_khata = sum(float(c.get("balance", 0)) for c in self.customers if float(c.get("balance", 0)) > 0)
        self.total_due_badge.setText(f"Total Market Khata: Rs {total_khata:,.2f}")

        self.customer_table.setRowCount(len(customer_list))
        for row, c in enumerate(customer_list):
            name_item = QTableWidgetItem(c["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.customer_table.setItem(row, 0, name_item)

            self.customer_table.setItem(row, 1, QTableWidgetItem(c.get("phone") or "—"))

            bal = float(c.get("balance", 0))
            bal_item = QTableWidgetItem(f"Rs {bal:,.2f}")
            bal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if bal > 0:
                bal_item.setForeground(Qt.GlobalColor.red)
            else:
                bal_item.setForeground(Qt.GlobalColor.darkGreen)
            self.customer_table.setItem(row, 2, bal_item)

            action_btn = QPushButton("Open")
            action_btn.setProperty("compact", True)
            action_btn.setStyleSheet(
                "min-height: 26px; max-height: 28px; padding: 2px 10px; font-size: 12px; "
                "font-weight: 600; background: #0284c7; color: white; border: none; border-radius: 4px;"
            )
            action_btn.clicked.connect(lambda _=False, cid=c["id"]: self._select_customer_by_id(cid))
            self.customer_table.setCellWidget(row, 3, action_btn)

    def _select_customer_by_id(self, cid):
        for row in range(self.customer_table.rowCount()):
            item = self.customer_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == cid:
                self.customer_table.selectRow(row)
                break

    def _customer_selected(self):
        selected = self.customer_table.selectedItems()
        if not selected:
            return
        cid = selected[0].data(Qt.ItemDataRole.UserRole)
        customer = next((c for c in self.customers if c["id"] == cid), None)
        if customer:
            self.selected_customer = customer
            self._load_ledger(customer)

    def _load_ledger(self, customer):
        self.ledger_title.setText(f"Customer: {customer['name']} ({customer.get('phone') or 'No Phone'})")
        bal = float(customer.get("balance", 0))
        self.ledger_balance.setText(f"Balance Due: Rs {bal:,.2f}")
        if bal > 0:
            self.ledger_balance.setStyleSheet(
                "font-size: 20px; font-weight: 800; color: #DC2626; background: #FEF2F2; "
                "border: 1px solid #FCA5A5; border-radius: 8px; padding: 10px 14px;"
            )
        else:
            self.ledger_balance.setStyleSheet(
                "font-size: 20px; font-weight: 800; color: #16A34A; background: #F0FDF4; "
                "border: 1px solid #86EFAC; border-radius: 8px; padding: 10px 14px;"
            )
        self.pay_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)

        self._run(lambda: db.get_customer_ledger(customer["id"]), self._ledger_loaded)

    def _ledger_loaded(self, ledger_data):
        if not ledger_data:
            return
        txs = ledger_data.get("transactions", [])
        self.tx_table.setRowCount(len(txs))
        for row, tx in enumerate(txs):
            self.tx_table.setItem(row, 0, QTableWidgetItem(tx["timestamp"]))
            
            type_item = QTableWidgetItem(tx["type"].upper())
            if tx["type"] == "sale":
                type_item.setForeground(Qt.GlobalColor.darkRed)
            elif tx["type"] == "payment":
                type_item.setForeground(Qt.GlobalColor.darkGreen)
            self.tx_table.setItem(row, 1, type_item)

            amt = float(tx["amount"])
            amt_item = QTableWidgetItem(f"Rs {abs(amt):,.2f}")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tx_table.setItem(row, 2, amt_item)

            self.tx_table.setItem(row, 3, QTableWidgetItem(tx.get("notes") or ""))

    def _add_customer(self):
        dialog = _CustomerForm(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.name.text().strip()
            phone = dialog.phone.text().strip()
            addr = dialog.address.text().strip()
            self._run(lambda: db.create_customer(name, phone, addr), lambda _: self.refresh())

    def _edit_customer(self):
        if not self.selected_customer:
            return
        dialog = _CustomerForm(customer=self.selected_customer, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.name.text().strip()
            phone = dialog.phone.text().strip()
            addr = dialog.address.text().strip()
            cid = self.selected_customer["id"]
            self._run(lambda: db.update_customer(cid, name, phone, addr), lambda _: self.refresh())

    def _delete_customer(self):
        if not self.selected_customer:
            return
        bal = float(self.selected_customer.get("balance", 0))
        if bal > 0:
            QMessageBox.warning(self, "Cannot Delete", f"Customer has an active balance of Rs {bal:,.2f}. Clear balance before deleting.")
            return
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete customer '{self.selected_customer['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            cid = self.selected_customer["id"]
            self._run(lambda: db.delete_customer(cid), lambda _: self.refresh())

    def _receive_payment(self):
        if not self.selected_customer:
            return
        dialog = _PaymentDialog(customer=self.selected_customer, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            amount = dialog.amount.value()
            notes = dialog.notes.text().strip()
            payment_method = dialog.method.currentText()
            cid = self.selected_customer["id"]
            
            def _op():
                db.record_customer_payment(cid, amount, notes, payment_method)

            def _on_done(_):
                play_success_ding()
                self.status.setText(f"Payment of Rs {amount:,.2f} recorded for {self.selected_customer['name']}.")
                self.refresh()

            self._run(_op, _on_done)
