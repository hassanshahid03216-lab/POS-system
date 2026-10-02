"""Supplier directory, inward stock purchases, payments, and account ledger."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from db import db


class SuppliersScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Suppliers & Purchasing"))
        form = QFormLayout()
        self.name = QLineEdit()
        self.company = QLineEdit()
        self.phone = QLineEdit()
        self.address = QLineEdit()
        form.addRow("Supplier name", self.name)
        form.addRow("Company", self.company)
        form.addRow("Phone", self.phone)
        form.addRow("Address", self.address)
        add_supplier = QPushButton("Save Supplier")
        add_supplier.clicked.connect(self._save_supplier)
        form.addRow("", add_supplier)
        root.addLayout(form)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Supplier", "Company", "Phone", "Balance owed", "Actions"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        root.addWidget(QLabel("Receive Stock / Purchase Inward"))
        purchase = QHBoxLayout()
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
        self.purchase_table.setMaximumHeight(130)
        purchase.addWidget(self.supplier, 2); purchase.addWidget(self.invoice, 1)
        purchase.addWidget(self.product, 2); purchase.addWidget(self.qty)
        purchase.addWidget(self.cost); purchase.addWidget(self.paid); purchase.addWidget(self.purchase_method)
        root.addLayout(purchase)
        actions = QHBoxLayout()
        add_line = QPushButton("Add purchase item"); add_line.clicked.connect(self._add_line)
        receive = QPushButton("Record purchase and receive stock"); receive.clicked.connect(self._record_purchase)
        actions.addWidget(add_line); actions.addWidget(receive)
        root.addLayout(actions)
        root.addWidget(self.purchase_table)
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
            actions = QWidget(); row = QHBoxLayout(actions); row.setContentsMargins(0,0,0,0)
            pay = QPushButton("Record payment"); pay.clicked.connect(lambda _, sid=item["id"]: self._pay(sid))
            ledger = QPushButton("View ledger"); ledger.clicked.connect(lambda _, sid=item["id"]: self._ledger(sid))
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
