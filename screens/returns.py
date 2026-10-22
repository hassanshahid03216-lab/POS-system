"""Sale Return and Refund (Wapasi / Exchange) Management screen."""

from __future__ import annotations

import webbrowser
from typing import Any, Callable
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from db import db
from services.receipts import print_or_save_receipt, generate_whatsapp_url
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


class SaleReturnsScreen(QWidget):
    operation_done = Signal(object, object)
    operation_failed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self.current_sale_data: dict | None = None
        self.busy = False

        self.operation_done.connect(self._finished)
        self.operation_failed.connect(self._failed)

        self._build_ui()
        self.load_recent_sales()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Header
        top_bar = QHBoxLayout()
        title = QLabel("Sale Return & Refund (Wapasi / Exchange)")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        top_bar.addWidget(title)
        top_bar.addStretch()

        refresh_btn = QPushButton("Refresh Recent Sales")
        refresh_btn.clicked.connect(self.load_recent_sales)
        top_bar.addWidget(refresh_btn)
        root.addLayout(top_bar)

        # Search Sale by ID Bar
        search_box = QHBoxLayout()
        self.sale_id_input = QLineEdit()
        self.sale_id_input.setPlaceholderText("Enter Bill / Sale ID (e.g. 102) and press Enter...")
        self.sale_id_input.returnPressed.connect(self._search_by_id)
        search_box.addWidget(self.sale_id_input, 1)

        search_btn = QPushButton("Lookup Bill")
        search_btn.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 7px 16px;")
        search_btn.clicked.connect(self._search_by_id)
        search_box.addWidget(search_btn)
        root.addLayout(search_box)

        # Main Split: Left (Recent Sales) - Right (Return Items Form)
        split = QHBoxLayout()
        split.setSpacing(16)

        # Left: Recent sales list inside a Card
        left_card = QFrame()
        left_card.setProperty("visualRole", "card")
        left_box = QVBoxLayout(left_card)
        left_box.setContentsMargins(14, 14, 14, 14)
        left_box.setSpacing(10)

        left_label = QLabel("📋 Recent Completed Sales")
        left_label.setStyleSheet("font-weight: 700; color: #0F172A; font-size: 14px;")
        left_box.addWidget(left_label)

        self.sales_table = QTableWidget(0, 5)
        self.sales_table.setHorizontalHeaderLabels(["Bill #", "Time", "Customer", "Total", "Action"])
        self.sales_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sales_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sales_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sales_table.verticalHeader().setVisible(False)
        self.sales_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.sales_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.itemSelectionChanged.connect(self._sale_row_selected)
        left_box.addWidget(self.sales_table, 1)
        split.addWidget(left_card, 4)

        # Right: Return processing card
        self.return_frame = QFrame()
        self.return_frame.setProperty("visualRole", "card")
        right_box = QVBoxLayout(self.return_frame)
        right_box.setContentsMargins(16, 16, 16, 16)
        right_box.setSpacing(12)

        self.bill_info = QLabel("Select a bill from the left or search Bill ID to process return")
        self.bill_info.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1E293B; background: #F1F5F9; "
            "border: 1px solid #CBD5E1; border-radius: 6px; padding: 10px 12px;"
        )
        self.bill_info.setWordWrap(True)
        right_box.addWidget(self.bill_info)

        self.items_table = QTableWidget(0, 5)
        self.items_table.setHorizontalHeaderLabels(["Product", "Price", "Sold Qty", "Returned", "Return Qty"])
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        right_box.addWidget(self.items_table, 1)

        self.refund_total_label = QLabel("Total Refund Amount: Rs 0.00")
        self.refund_total_label.setStyleSheet(
            "font-size: 17px; font-weight: 800; color: #DC2626; background: #FEF2F2; "
            "border: 1px solid #FCA5A5; border-radius: 8px; padding: 10px 14px;"
        )
        right_box.addWidget(self.refund_total_label)

        reason_row = QHBoxLayout()
        reason_lbl = QLabel("Return Reason / Note:")
        reason_lbl.setStyleSheet("font-weight: 600; color: #334155; min-width: 140px;")
        reason_row.addWidget(reason_lbl)
        self.reason_input = QLineEdit("Customer returned item")
        reason_row.addWidget(self.reason_input, 1)
        right_box.addLayout(reason_row)

        self.restock_check = QCheckBox("Restock returned items (uncheck damaged / expired items)")
        self.restock_check.setChecked(True)
        self.restock_check.setStyleSheet("font-weight: 600; color: #334155; padding: 2px 0;")
        right_box.addWidget(self.restock_check)

        refund_row = QHBoxLayout()
        refund_lbl = QLabel("Refund Method:")
        refund_lbl.setStyleSheet("font-weight: 600; color: #334155; min-width: 140px;")
        refund_row.addWidget(refund_lbl)
        self.refund_method = QComboBox()
        self.refund_method.addItems(["Cash", "Credit / Khata Adjustment", "Store Credit Voucher", "Exchange Credit"])
        refund_row.addWidget(self.refund_method, 1)
        right_box.addLayout(refund_row)

        action_row = QHBoxLayout()
        self.process_btn = QPushButton("Process Return / Exchange")
        self.process_btn.setStyleSheet(
            "min-height: 42px; background: #DC2626; color: white; font-weight: bold; "
            "font-size: 14px; border-radius: 6px; padding: 8px 18px;"
        )
        self.process_btn.clicked.connect(self._process_return)
        self.process_btn.setEnabled(False)
        action_row.addWidget(self.process_btn)
        right_box.addLayout(action_row)

        split.addWidget(self.return_frame, 5)
        root.addLayout(split, 1)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #64748b; font-weight: 500;")
        root.addWidget(self.status)

    def load_recent_sales(self):
        self._run(lambda: db.list_recent_sales(40), self._sales_loaded)

    def refresh(self):
        self.load_recent_sales()

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
        QMessageBox.warning(self, "Return Error", str(error))

    def _sales_loaded(self, sales):
        self.sales_table.setRowCount(len(sales))
        for row, s in enumerate(sales):
            id_item = QTableWidgetItem(f"#{s['id']}")
            id_item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.sales_table.setItem(row, 0, id_item)
            self.sales_table.setItem(row, 1, QTableWidgetItem(s["timestamp"]))
            self.sales_table.setItem(row, 2, QTableWidgetItem(s["customer_name"]))

            orig_total = float(s.get("original_total", s.get("total", 0)))
            refunded = float(s.get("refunded_amount", 0))
            net_total = float(s.get("net_total", max(0.0, orig_total - refunded)))

            if refunded > 0:
                if net_total <= 0.01:
                    total_item = QTableWidgetItem("Rs 0.00 (Returned)")
                    total_item.setForeground(QColor("#DC2626"))
                else:
                    total_item = QTableWidgetItem(f"Rs {net_total:,.2f} (-Rs {refunded:,.0f})")
                    total_item.setForeground(QColor("#D97706"))
                total_item.setToolTip(
                    f"Original Total: Rs {orig_total:,.2f}\n"
                    f"Refunded: Rs {refunded:,.2f}\n"
                    f"Remaining Net: Rs {net_total:,.2f}"
                )
            else:
                total_item = QTableWidgetItem(f"Rs {net_total:,.2f}")

            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.sales_table.setItem(row, 3, total_item)

            btn = QPushButton("Select")
            btn.setProperty("compact", True)
            if refunded > 0 and net_total <= 0.01:
                btn.setText("Returned")
                btn.setStyleSheet(
                    "min-height: 26px; max-height: 28px; padding: 2px 10px; font-size: 12px; "
                    "font-weight: 600; background: #94A3B8; color: white; border: none; border-radius: 4px;"
                )
            else:
                btn.setStyleSheet(
                    "min-height: 26px; max-height: 28px; padding: 2px 10px; font-size: 12px; "
                    "font-weight: 600; background: #0284c7; color: white; border: none; border-radius: 4px;"
                )
            btn.clicked.connect(lambda _=False, sid=s["id"]: self._load_sale_details(sid))
            self.sales_table.setCellWidget(row, 4, btn)


    def _sale_row_selected(self):
        items = self.sales_table.selectedItems()
        if not items:
            return
        sid = items[0].data(Qt.ItemDataRole.UserRole)
        self._load_sale_details(sid)

    def _search_by_id(self):
        text = self.sale_id_input.text().strip().lstrip("#")
        if not text.isdigit():
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid numeric Bill / Sale ID.")
            return
        self._load_sale_details(int(text))

    def _load_sale_details(self, sale_id):
        self._run(lambda: db.get_sale_for_return(sale_id), self._sale_data_loaded)

    def _sale_data_loaded(self, data):
        if not data:
            self.status.setText("Sale ID not found.")
            play_error_beep()
            QMessageBox.information(self, "Not Found", "Could not find a sale with that ID.")
            return
        self.current_sale_data = data
        sale = data["sale"]
        items = data["items"]

        # Check if all items are fully returned already
        any_returnable = any(
            (it["qty"] - it["already_returned"]) > 0 for it in items
        )
        if not any_returnable:
            self._reset_return_form()
            self.bill_info.setText(
                f"✅ Bill #{sale['id']} — All items have been fully returned."
            )
            self.status.setText(f"Bill #{sale['id']} has no remaining items to return.")
            return

        self.bill_info.setText(
            f"Bill #{sale['id']} · {sale['timestamp']} · Customer: {sale['customer_name']} · Payment: {sale['payment_mode']}"
        )

        self.items_table.setRowCount(len(items))
        self.return_spinboxes = []

        for row, it in enumerate(items):
            self.items_table.setItem(row, 0, QTableWidgetItem(it["name"]))
            self.items_table.setItem(row, 1, QTableWidgetItem(f"Rs {float(it['unit_price']):,.2f}"))
            self.items_table.setItem(row, 2, QTableWidgetItem(str(it["qty"])))
            self.items_table.setItem(row, 3, QTableWidgetItem(str(it["already_returned"])))

            available_to_return = it["qty"] - it["already_returned"]
            spin = QSpinBox()
            spin.setRange(0, max(0, available_to_return))
            spin.setValue(0)
            spin.valueChanged.connect(self._recalc_refund)
            self.items_table.setCellWidget(row, 4, spin)
            self.return_spinboxes.append((it, spin))

        self.process_btn.setEnabled(True)
        self._recalc_refund()

    def _recalc_refund(self):
        if not self.current_sale_data:
            return
        lines = self.current_sale_data["items"]
        net_lines = {}
        subtotal_after_item_discounts = 0.0
        item_discounts = 0.0
        for item in lines:
            gross = int(item["qty"]) * float(item["unit_price"])
            discount = min(gross, float(item.get("discount") or 0))
            net_lines[item["product_id"]] = gross - discount
            subtotal_after_item_discounts += gross - discount
            item_discounts += discount
        sale_discount = float(self.current_sale_data["sale"].get("discount") or 0)
        bill_discount = min(subtotal_after_item_discounts, max(0.0, sale_discount - item_discounts))
        total_refund = 0.0
        for it, spin in self.return_spinboxes:
            qty = spin.value()
            if not qty:
                continue
            remaining_qty = int(it["qty"]) - int(it.get("already_returned", 0))
            line_net = net_lines[it["product_id"]]
            line_entitlement = line_net
            if subtotal_after_item_discounts:
                line_entitlement -= bill_discount * line_net / subtotal_after_item_discounts
            remaining_value = max(0.0, line_entitlement - float(it.get("already_refunded", 0)))
            total_refund += remaining_value * qty / max(1, remaining_qty)
        self.refund_total_label.setText(f"Total Refund Amount: Rs {total_refund:,.2f}")
        self.process_btn.setEnabled(total_refund > 0)

    def _process_return(self):
        if not self.current_sale_data:
            return
        returned_items = []
        for it, spin in self.return_spinboxes:
            qty = spin.value()
            if qty > 0:
                returned_items.append({
                    "product_id": it["product_id"],
                    "name": it["name"],
                    "qty": qty,
                    "unit_price": float(it["unit_price"])
                })

        if not returned_items:
            QMessageBox.warning(self, "No Items", "Please select at least 1 item quantity to return.")
            return

        sale_id = self.current_sale_data["sale"]["id"]
        notes = self.reason_input.text().strip()
        refund_method = self.refund_method.currentText()
        restock = self.restock_check.isChecked()

        def _op():
            res = db.process_sale_return(sale_id, returned_items, notes, refund_method, restock)
            # generate return receipt
            receipt = {
                "is_return": True,
                "sale_id": sale_id,
                "return_id": res["return_id"],
                "timestamp": res["timestamp"],
                "customer_name": self.current_sale_data["sale"]["customer_name"],
                "refund_amount": res["refund_amount"],
                "refund_method": refund_method,
                "voucher_code": res.get("voucher_code"),
                "items": returned_items
            }
            print_or_save_receipt(receipt)
            return res, receipt

        def _on_done(result_tuple):
            res, receipt = result_tuple
            play_success_ding()

            # 1. Immediately refresh the left sales table so net amounts update right away
            self.load_recent_sales()

            # 2. Immediately refresh current bill on the right side so remaining items update
            self._load_sale_details(sale_id)

            # Generate image and copy to clipboard
            self._receipt_img_path = None
            try:
                from services.receipt_image import generate_receipt_image, copy_receipt_image_to_clipboard
                self._receipt_img_path = generate_receipt_image(receipt)
                copy_receipt_image_to_clipboard(self._receipt_img_path)
            except Exception as e:
                print("Receipt image error:", e)
            
            # Dialog showing success + WhatsApp receipt option
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Return Processed ✅")
            msg_box.setText(
                f"✅  Return #{res['return_id']} processed successfully!\n"
                f"Refund Amount: Rs {res['refund_amount']:,.2f}\n"
                f"Refund method: {refund_method}\n"
                f"Inventory: {'restocked' if restock else 'recorded as damaged; stock unchanged'}\n"
                + (f"Voucher code: {res['voucher_code']}\n" if res.get("voucher_code") else "")
                + "\nDigital receipt image is ready and copied to the clipboard."
            )
            wa_btn = msg_box.addButton("📱  Send on WhatsApp", QMessageBox.ButtonRole.ActionRole)
            img_btn = msg_box.addButton("🖼️  View Image", QMessageBox.ButtonRole.ActionRole)
            fld_btn = msg_box.addButton("📁  Open Folder", QMessageBox.ButtonRole.ActionRole)
            ok_btn = msg_box.addButton(QMessageBox.StandardButton.Ok)
            exchange_btn = msg_box.addButton("Start Exchange in Billing", QMessageBox.ButtonRole.ActionRole)
            exchange_btn.setEnabled(refund_method == "Exchange Credit")
            msg_box.setDefaultButton(wa_btn)
            msg_box.exec()

            clicked = msg_box.clickedButton()

            if clicked == exchange_btn and refund_method == "Exchange Credit":
                workspace = self.parentWidget()
                if workspace and hasattr(workspace, "start_exchange"):
                    workspace.start_exchange(res["refund_amount"], res["voucher_code"])
            elif clicked == wa_btn:
                if getattr(self, "_receipt_img_path", None):
                    from services.receipt_image import copy_receipt_image_to_clipboard
                    copy_receipt_image_to_clipboard(self._receipt_img_path)

                # Get phone number safely if customer was linked
                phone = ""
                if self.current_sale_data and "sale" in self.current_sale_data:
                    phone = self.current_sale_data["sale"].get("phone", "")

                url = generate_whatsapp_url(receipt, phone_number=phone, include_full_text=False)
                webbrowser.open(url)

                self.status.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 13px;")
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
                if getattr(self, "_receipt_img_path", None):
                    import os as _os
                    _os.startfile(self._receipt_img_path)
                else:
                    self.status.setText("Receipt image not available.")
            
            elif clicked == fld_btn:
                if getattr(self, "_receipt_img_path", None):
                    import subprocess
                    subprocess.Popen(["explorer", f"/select,{self._receipt_img_path}"])
                else:
                    self.status.setText("Receipt image not available.")

            self.status.setStyleSheet("color: #15803D; font-weight: 600;")
            self.status.setText(f"✅ Return #{res['return_id']} processed — Rs {res['refund_amount']:,.2f} refunded.")
            self.load_recent_sales()

        self._run(_op, _on_done)

    def _reset_return_form(self):
        """Clear the right-side return panel after a successful return."""
        self.current_sale_data = None
        self.items_table.setRowCount(0)
        self.return_spinboxes = []
        self.bill_info.setText("Select a bill to process items for return")
        self.refund_total_label.setText("Total Refund Amount: Rs 0.00")
        self.reason_input.setText("Customer returned item")
        self.process_btn.setEnabled(False)
