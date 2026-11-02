"""Supplier directory, inward stock purchases, payments, and account ledger."""

from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox,
    QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from db import db


class SuppliersScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(7)
        title = QLabel("Suppliers & Purchasing")
        title.setStyleSheet("font-size:18px;font-weight:800;color:#0F172A;")
        root.addWidget(title)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        self.name = QLineEdit()
        self.company = QLineEdit()
        self.phone = QLineEdit()
        self.address = QLineEdit()
        for field in (self.name, self.company, self.phone, self.address):
            field.setMaximumHeight(36)
            field.setStyleSheet("min-height:28px;max-height:36px;padding:2px 8px;")
        form.addWidget(QLabel("Supplier name"), 0, 0); form.addWidget(self.name, 0, 1)
        form.addWidget(QLabel("Company"), 0, 2); form.addWidget(self.company, 0, 3)
        form.addWidget(QLabel("Phone"), 1, 0); form.addWidget(self.phone, 1, 1)
        form.addWidget(QLabel("Address"), 1, 2); form.addWidget(self.address, 1, 3)
        form.setColumnStretch(1, 1); form.setColumnStretch(3, 1)
        add_supplier = QPushButton("Save Supplier")
        add_supplier.setMaximumHeight(34)
        add_supplier.setStyleSheet("min-height:28px;max-height:34px;padding:2px 10px;")
        add_supplier.clicked.connect(self._save_supplier)
        form.addWidget(add_supplier, 2, 3)
        root.addLayout(form)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Supplier", "Company", "Phone", "Balance owed", "Actions"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMaximumHeight(230)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.verticalHeader().setMinimumSectionSize(40)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table)

        purchase_title = QLabel("Receive Stock / Purchase Inward")
        purchase_title.setStyleSheet("font-size:15px;font-weight:750;color:#0F172A;")
        root.addWidget(purchase_title)
        purchase = QGridLayout()
        purchase.setHorizontalSpacing(8)
        purchase.setVerticalSpacing(6)
        self.supplier = QComboBox()
        self.invoice = QLineEdit()
        self.invoice.setPlaceholderText("Invoice #")
        self.product = QComboBox()
        self.qty = QSpinBox(); self.qty.setRange(1, 100000)
        self.cost = QDoubleSpinBox(); self.cost.setRange(0, 100000000); self.cost.setDecimals(2)
        self.paid = QDoubleSpinBox(); self.paid.setRange(0, 100000000); self.paid.setDecimals(2)
        self.purchase_method = QComboBox(); self.purchase_method.addItems(["Cash", "Bank transfer"])
        self.purchase_table = QTableWidget(0, 4)
        self.purchase_table.setHorizontalHeaderLabels(["Product", "Qty", "Unit cost", "Line total"])
        self.purchase_table.setMaximumHeight(150)
        for field in (self.supplier, self.invoice, self.product, self.qty, self.cost, self.paid, self.purchase_method):
            field.setMaximumHeight(36)
            field.setStyleSheet("min-height:28px;max-height:36px;padding:2px 8px;")
        self.supplier.setMinimumContentsLength(14)
        self.product.setMinimumContentsLength(18)
        purchase.addWidget(self.supplier, 0, 0, 1, 2)
        purchase.addWidget(self.invoice, 0, 2, 1, 2)
        purchase.addWidget(self.product, 1, 0, 1, 2)
        purchase.addWidget(self.qty, 1, 2)
        purchase.addWidget(self.cost, 1, 3)
        purchase.addWidget(self.paid, 1, 4)
        purchase.addWidget(self.purchase_method, 1, 5)
        root.addLayout(purchase)
        actions = QHBoxLayout()
        add_line = QPushButton("Add purchase item"); add_line.clicked.connect(self._add_line)
        receive = QPushButton("Record purchase and receive stock"); receive.clicked.connect(self._record_purchase)
        for button in (add_line, receive):
            button.setMaximumHeight(38)
            button.setStyleSheet("min-height:30px;max-height:38px;padding:3px 10px;")
        actions.addWidget(add_line); actions.addWidget(receive)
        root.addLayout(actions)
        self.purchase_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.purchase_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.purchase_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.purchase_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.purchase_table, 1)
        self.status = QLabel(""); root.addWidget(self.status)
        self.refresh()

    def refresh(self):
        self.suppliers = db.list_suppliers()
        self.table.setRowCount(len(self.suppliers))
        self.supplier.clear()
        for i, item in enumerate(self.suppliers):
            self.table.setItem(i, 0, QTableWidgetItem(item["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(item.get("company") or ""))
            self.table.setItem(i, 2, QTableWidgetItem(item.get("phone") or ""))
            self.table.setItem(i, 3, QTableWidgetItem(f"Rs {item['balance_owed']:,.2f}"))
            actions = QWidget(); row = QHBoxLayout(actions); row.setContentsMargins(2,0,2,0); row.setSpacing(4)
            pay = QPushButton("Pay"); pay.setToolTip("Record supplier payment")
            pay.setFixedSize(62, 30)
            pay.setStyleSheet("min-height:28px;max-height:30px;padding:1px 6px;font-size:11px;")
            pay.clicked.connect(lambda _, sid=item["id"]: self._pay(sid))
            ledger = QPushButton("Ledger"); ledger.setToolTip("View supplier ledger")
            ledger.setFixedSize(68, 30)
            ledger.setStyleSheet("min-height:28px;max-height:30px;padding:1px 6px;font-size:11px;")
            ledger.clicked.connect(lambda _, sid=item["id"]: self._ledger(sid))
            row.addWidget(pay); row.addWidget(ledger); self.table.setCellWidget(i,4,actions)
            self.supplier.addItem(item["name"], item["id"])
        self.products = db.list_products()
        self.product.clear()
        for p in self.products:
            self.product.addItem(p["name"], p["id"])

    def _save_supplier(self):
        try:
            db.save_supplier(self.name.text(), self.company.text(), self.phone.text(), self.address.text())
            self.name.clear(); self.company.clear(); self.phone.clear(); self.address.clear(); self.refresh()
        except Exception as error:
            QMessageBox.warning(self, "Supplier", str(error))

    def _add_line(self):
        p = next((p for p in self.products if p["id"] == self.product.currentData()), None)
        if p:
            self.items.append({"product_id":p["id"], "name":p["name"], "qty":self.qty.value(), "unit_cost":self.cost.value()})
            row = self.purchase_table.rowCount(); self.purchase_table.insertRow(row)
            for col, val in enumerate((p["name"], str(self.qty.value()), f"{self.cost.value():.2f}", f"{self.qty.value()*self.cost.value():.2f}")):
                self.purchase_table.setItem(row,col,QTableWidgetItem(val))

    def _record_purchase(self):
        if not self.supplier.currentData():
            QMessageBox.warning(self, "Supplier required", "Add or select a supplier first."); return
        try:
            result = db.record_purchase(self.supplier.currentData(), self.invoice.text().strip(), self.items, self.paid.value(), self.purchase_method.currentText())
            QMessageBox.information(self,"Purchase recorded",f"Stock received. Total Rs {result['total']:,.2f}; paid Rs {result['paid']:,.2f}; due Rs {result['due']:,.2f}.")
            self.items=[]; self.purchase_table.setRowCount(0); self.invoice.clear(); self.paid.setValue(0); self.refresh()
        except Exception as error:
            QMessageBox.warning(self,"Purchase error",str(error))

    def _pay(self, supplier_id):
        amount, ok = QInputDialog.getDouble(self,"Supplier payment","Amount to pay (Rs)",0,0,999999999,2)
        if not ok: return
        method, ok = QInputDialog.getItem(self,"Payment method","Method",["Cash","Bank transfer"],0,False)
        if not ok: return
        try:
            db.record_supplier_payment(supplier_id,amount,method)
            QMessageBox.information(self,"Payment recorded","Supplier balance updated."); self.refresh()
        except Exception as error:
            QMessageBox.warning(self,"Payment error",str(error))

    def _ledger(self, supplier_id):
        supplier = next((s for s in self.suppliers if s["id"]==supplier_id),{})
        entries = db.supplier_ledger(supplier_id)
        lines = [f"{e['timestamp']}  {e['type'].title()}  Rs {e['amount']:,.2f}  Balance Rs {e['running_balance']:,.2f}  {e.get('notes') or ''}" for e in entries]
        QMessageBox.information(self,f"{supplier.get('name','Supplier')} ledger", "\n".join(lines) or "No account activity.")
