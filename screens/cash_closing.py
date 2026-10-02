"""Cash drawer opening and shift close workflow."""

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QLabel, QLineEdit, QMessageBox, QVBoxLayout, QPushButton, QInputDialog)
from db import db
from services.receipts import print_or_save_receipt


class CashClosingDialog(QDialog):
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("Day End / Cash Drawer")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.form = QFormLayout()
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 999999999)
        self.amount.setDecimals(2)
        self.notes = QLineEdit()
        self.form.addRow("Opening float / counted cash (Rs)", self.amount)
        self.form.addRow("Notes", self.notes)
        layout.addLayout(self.form)
        self.buttons = QDialogButtonBox()
        self.buttons.accepted.connect(self._submit)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.shift = db.active_cash_shift()
        if self.shift:
            summary = db.cash_shift_summary(self.shift["id"])
            self.amount.setValue(summary["expected"])
            self.info.setText(
                f"Shift opened by {self.shift['cashier_name']} with Rs {self.shift['opening']:,.2f}.\n"
                f"Cash sales Rs {summary['cash_sales']:,.2f}; Khata cash recoveries Rs {summary['khata_recoveries']:,.2f}; "
                f"refunds Rs {summary['cash_refunds']:,.2f}; expenses Rs {summary['expenses']:,.2f}.\n"
                f"Expected in drawer: Rs {summary['expected']:,.2f}"
            )
            self.form.labelForField(self.amount).setText("Physical counted cash (Rs)")
            self.buttons.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        else:
            self.info.setText("Start a cash shift by entering the opening float in the drawer.")
            self.form.labelForField(self.amount).setText("Opening float (Rs)")
            self.buttons.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)

        if self.shift:
            expense = QPushButton("Record petty cash expense")
            expense.clicked.connect(self._expense)
            layout.insertWidget(layout.count() - 1, expense)

    def _submit(self):
        try:
            if not self.shift:
                db.start_cash_shift(self.user["id"], self.user["name"], self.amount.value())
                QMessageBox.information(self, "Shift Started", "Opening cash float recorded.")
            else:
                result = db.close_cash_shift(self.shift["id"], self.amount.value(), self.notes.text().strip())
                variance = result["variance"]
                label = "Exact Match (Balanced)" if abs(variance) < .005 else ("Cash Short (Loss / Galti)" if variance < 0 else "Cash Over (Surplus)")
                QMessageBox.information(self, "Cash Closing", f"{label}\nExpected: Rs {result['expected']:,.2f}\nCounted: Rs {result['actual']:,.2f}\nVariance: Rs {variance:+,.2f}")
                print_or_save_receipt({"closing_summary": result})
            self.accept()
        except Exception as error:
            QMessageBox.warning(self, "Cash Drawer Error", str(error))

    def _expense(self):
        amount, ok = QInputDialog.getDouble(self, "Petty cash expense", "Amount paid from drawer (Rs)", 0, 0.01, 999999999, 2)
        if not ok:
            return
        note, ok = QInputDialog.getText(self, "Petty cash expense", "Purpose / note")
        if not ok:
            return
        try:
            db.record_cash_expense(amount, note.strip(), self.user["id"])
            summary = db.cash_shift_summary(self.shift["id"])
            self.info.setText(self.info.text().split("\nExpected in drawer:")[0] + f"\nExpected in drawer: Rs {summary['expected']:,.2f}")
            self.amount.setValue(summary["expected"])
        except Exception as error:
            QMessageBox.warning(self, "Expense error", str(error))
