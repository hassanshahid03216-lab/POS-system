"""Admin settings: Shop configuration, WhatsApp receipt details, Hardware/Printer, Sound, Auto-Backup, and Staff management."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QDate, QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtCore import QStorageInfo
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from app_settings import load_settings, save_settings
from db import db
from services.receipts import available_printers, kick_cash_drawer, test_printer
from services.sound import play_error_beep, play_success_ding


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Worker(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            self.signals.done.emit(self.operation())
        except Exception as error:
            self.signals.failed.emit(error)


class _AddUserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Staff User")
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Staff Name")
        self.role = QComboBox()
        self.role.addItem("Cashier", "cashier")
        self.role.addItem("Admin", "admin")
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setMaxLength(8)
        self.pin.setPlaceholderText("4–8 numeric digits")
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm.setMaxLength(8)
        form.addRow("Name *", self.name)
        form.addRow("Role *", self.role)
        form.addRow("PIN *", self.pin)
        form.addRow("Confirm PIN *", self.confirm)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate(self):
        pin = self.pin.text()
        if not self.name.text().strip():
            QMessageBox.warning(self, "Name needed", "Enter the user's name.")
            return
        if not pin.isdigit() or not 4 <= len(pin) <= 8:
            QMessageBox.warning(self, "PIN not valid", "PIN must be 4 to 8 digits.")
            return
        if pin != self.confirm.text():
            QMessageBox.warning(self, "PINs do not match", "Enter the same PIN in both fields.")
            return
        self.accept()


class AdminSettingsPage(QWidget):
    operation_done = Signal(object, object)
    operation_failed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self.busy = False
        self.operation_done.connect(self._finished)
        self.operation_failed.connect(self._failed)
        self._build_ui()
        self._load_current_settings()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        heading = QLabel("Shop Settings & Administration")
        heading.setStyleSheet("font-size: 22px; font-weight: 700; color: #0f172a;")
        root.addWidget(heading)

        grid = QGridLayout()
        grid.setSpacing(12)

        # 1. Shop & Receipt Profile
        shop_box = QGroupBox("🏪 Shop Details && Receipt Branding")
        shop_lay = QFormLayout(shop_box)
        self.shop_name = QLineEdit()
        self.shop_phone = QLineEdit()
        self.shop_phone.setPlaceholderText("+92 300 1234567 (Used for WhatsApp Receipts)")
        self.shop_address = QLineEdit()
        self.shop_address.setPlaceholderText("Shop address")
        self.receipt_footer = QTextEdit()
        self.receipt_footer.setMaximumHeight(65)
        self.receipt_footer.setPlaceholderText("Return policy or thank you message...")

        shop_lay.addRow("Shop Name:", self.shop_name)
        shop_lay.addRow("Phone / WhatsApp:", self.shop_phone)
        shop_lay.addRow("Address:", self.shop_address)
        shop_lay.addRow("Receipt Policy / Footer:", self.receipt_footer)

        save_shop_btn = QPushButton("Save Shop Profile")
        save_shop_btn.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 6px 14px;")
        save_shop_btn.clicked.connect(self._save_shop_profile)
        shop_lay.addRow("", save_shop_btn)
        grid.addWidget(shop_box, 0, 0)

        # 2. Hardware & Thermal Printer & Sound
        hardware_box = QGroupBox("🖨️ Hardware, Printer && Sound")
        hw_lay = QFormLayout(hardware_box)
        self.printer = QComboBox()
        self.printer.setMinimumWidth(220)
        hw_row = QHBoxLayout()
        hw_row.addWidget(self.printer, 1)
        refresh_p_btn = QPushButton("Refresh")
        refresh_p_btn.clicked.connect(self._refresh_printers)
        hw_row.addWidget(refresh_p_btn)
        hw_lay.addRow("Thermal Printer:", hw_row)

        test_btns = QHBoxLayout()
        save_hw_btn = QPushButton("Save Printer")
        save_hw_btn.clicked.connect(self._save_printer_settings)
        test_p_btn = QPushButton("Test Print")
        test_p_btn.clicked.connect(self._test_printer)
        test_drawer_btn = QPushButton("Pop Cash Drawer")
        test_drawer_btn.clicked.connect(self._test_drawer)
        test_btns.addWidget(save_hw_btn)
        test_btns.addWidget(test_p_btn)
        test_btns.addWidget(test_drawer_btn)
        hw_lay.addRow("", test_btns)

        self.sound_check = QCheckBox("Enable Audio Effects (Scan Beep, Cash Ding)")
        self.sound_check.stateChanged.connect(self._save_toggles)
        hw_lay.addRow("Sound Effects:", self.sound_check)

        self.backup_check = QCheckBox("Auto-backup database upon closing application")
        self.backup_check.stateChanged.connect(self._save_toggles)
        hw_lay.addRow("Data Safety:", self.backup_check)
        grid.addWidget(hardware_box, 0, 1)

        # 3. Staff & User Management
        users_box = QGroupBox("👥 Staff && User Accounts")
        users_layout = QVBoxLayout(users_box)
        u_top = QHBoxLayout()
        u_top.addWidget(QLabel("Secure PIN login accounts."), 1)
        add_user = QPushButton("+ Add Staff")
        add_user.setStyleSheet("background: #16a34a; color: white; font-weight: bold;")
        add_user.clicked.connect(self._add_user)
        u_top.addWidget(add_user)
        users_layout.addLayout(u_top)

        self.users_table = QTableWidget(0, 3)
        self.users_table.setHorizontalHeaderLabels(["Name", "Role", "Action"])
        self.users_table.verticalHeader().setVisible(False)
        self.users_table.verticalHeader().setDefaultSectionSize(38)
        self.users_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.users_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.users_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.users_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.users_table.setMaximumHeight(160)
        users_layout.addWidget(self.users_table)
        grid.addWidget(users_box, 1, 0)

        # 4. Backup & CSV Export
        data_box = QGroupBox("💾 Data Backup && Sales Export")
        data_lay = QVBoxLayout(data_box)
        
        backup_row = QHBoxLayout()
        backup_row.addWidget(QLabel("Create full SQLite DB backup on USB/Disk:"), 1)
        backup_btn = QPushButton("💾 Backup Database")
        backup_btn.clicked.connect(self._backup)
        backup_row.addWidget(backup_btn)
        data_lay.addLayout(backup_row)

        export_form = QFormLayout()
        self.start_date = QDateEdit(QDate.currentDate().addDays(-7))
        self.start_date.setCalendarPopup(True)
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        
        date_row = QHBoxLayout()
        date_row.addWidget(self.start_date)
        date_row.addWidget(QLabel("to"))
        date_row.addWidget(self.end_date)
        export_form.addRow("Sales Range:", date_row)
        
        export_btn = QPushButton("Export Sales CSV")
        export_btn.clicked.connect(self._export_sales)
        export_form.addRow("", export_btn)
        data_lay.addLayout(export_form)
        grid.addWidget(data_box, 1, 1)

        root.addLayout(grid)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #64748b; font-weight: 500;")
        root.addWidget(self.status)

    def _run(self, operation: Callable[[], Any], callback: Callable[[Any], None]):
        if self.busy:
            return
        self.busy = True
        worker = _Worker(operation)
        worker.signals.done.connect(lambda result: self.operation_done.emit(callback, result))
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
        QMessageBox.warning(self, "Settings Error", str(error))

    def _load_current_settings(self):
        settings = load_settings()
        self.shop_name.setText(settings.get("shop_name", "ShopFlow POS"))
        self.shop_phone.setText(settings.get("shop_phone", ""))
        self.shop_address.setText(settings.get("shop_address", ""))
        self.receipt_footer.setText(settings.get("receipt_footer", "Thank you for shopping with us!"))
        self.sound_check.setChecked(settings.get("sound_enabled", True))
        self.backup_check.setChecked(settings.get("auto_backup", True))

        self._refresh_printers()
        self._load_users()

    def refresh(self):
        self._load_current_settings()

    def _refresh_printers(self):
        self.printer.clear()
        self.printer.addItem("PDF Fallback (No physical printer)", "")
        current = load_settings().get("printer_name", "")
        printers = available_printers()
        for p in printers:
            self.printer.addItem(p, p)
        if current:
            idx = self.printer.findData(current)
            if idx >= 0:
                self.printer.setCurrentIndex(idx)

    def _save_shop_profile(self):
        save_settings({
            "shop_name": self.shop_name.text().strip() or "ShopFlow POS",
            "shop_phone": self.shop_phone.text().strip(),
            "shop_address": self.shop_address.text().strip(),
            "receipt_footer": self.receipt_footer.toPlainText().strip(),
        })
        play_success_ding()
        self.status.setText("✅ Shop details saved.")
        QMessageBox.information(self, "Saved", "Shop profile and receipt settings updated successfully.")

    def _save_printer_settings(self):
        selected = self.printer.currentData()
        save_settings({"printer_name": selected or ""})
        play_success_ding()
        self.status.setText(f"Printer updated: {selected or 'PDF Fallback'}")
        QMessageBox.information(self, "Saved", "Printer settings updated.")

    def _save_toggles(self):
        save_settings({
            "sound_enabled": self.sound_check.isChecked(),
            "auto_backup": self.backup_check.isChecked(),
        })

    def _test_printer(self):
        printer_name = self.printer.currentData()
        if not printer_name:
            QMessageBox.information(self, "PDF Mode", "No thermal printer selected (in PDF Fallback mode).")
            return
        try:
            test_printer(printer_name)
            play_success_ding()
            QMessageBox.information(self, "Test Print Sent", "Test slip sent to the thermal printer.")
        except Exception as error:
            play_error_beep()
            QMessageBox.warning(self, "Printer Test Failed", str(error))

    def _test_drawer(self):
        printer_name = self.printer.currentData()
        if not printer_name:
            QMessageBox.warning(self, "No Printer", "Select a thermal printer configured with cash drawer RJ11 cable.")
            return
        success = kick_cash_drawer(printer_name)
        if success:
            play_success_ding()
            self.status.setText("Cash drawer pulse sent.")
        else:
            play_error_beep()
            QMessageBox.warning(self, "Cash Drawer Error", "Could not send pulse to cash drawer.")

    def _load_users(self):
        self._run(db.list_users, self._show_users)

    def _show_users(self, users):
        self.users_table.setRowCount(len(users))
        for row, u in enumerate(users):
            self.users_table.setItem(row, 0, QTableWidgetItem(u["name"]))
            self.users_table.setItem(row, 1, QTableWidgetItem(u["role"].title()))

            del_btn = QPushButton("Delete")
            del_btn.setProperty("compact", True)
            del_btn.setStyleSheet(
                "min-height: 24px; max-height: 28px; padding: 2px 10px; color: #DC2626; "
                "border: 1px solid #FCA5A5; background: #FEF2F2; border-radius: 4px; "
                "font-size: 12px; font-weight: 600;"
            )
            del_btn.clicked.connect(lambda _=False, uid=u["id"]: self._delete_user(uid))
            self.users_table.setCellWidget(row, 2, del_btn)

    def _add_user(self):
        dialog = _AddUserDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.name.text().strip()
            role = dialog.role.currentData()
            pin = dialog.pin.text()
            self._run(lambda: db.create_user_with_pin(name, role, pin), lambda _: (play_success_ding(), self._load_users()))

    def _delete_user(self, uid):
        if len(db.list_users()) <= 1:
            QMessageBox.warning(self, "Cannot Delete", "At least one user account must remain.")
            return
        confirm = QMessageBox.question(
            self, "Confirm Delete", "Are you sure you want to delete this staff user?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._run(lambda: db.delete_user(uid), lambda _: (play_success_ding(), self._load_users()))

    def _backup(self):
        removable = [v.rootPath() for v in QStorageInfo.mountedVolumes() if v.isValid() and v.isReady() and v.isRemovable()]
        folder = QFileDialog.getExistingDirectory(self, "Select Backup Target Folder", removable[0] if removable else "")
        if not folder:
            return

        def _op():
            return db.backup_database(folder)

        def _done(path):
            play_success_ding()
            normalized_folder = folder.replace("/", "\\").casefold().rstrip("\\")
            if any(normalized_folder == root.replace("/", "\\").casefold().rstrip("\\") or
                   normalized_folder.startswith(root.replace("/", "\\").casefold().rstrip("\\") + "\\")
                   for root in removable):
                from datetime import date
                save_settings({"last_external_backup_date": date.today().isoformat()})
            QMessageBox.information(self, "Backup Successful", f"Database backed up successfully to:\n{path}")

        self._run(_op, _done)

    def _export_sales(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Sales CSV", "sales_report.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return
        start = self.start_date.date().toString(Qt.DateFormat.ISODate)
        end = self.end_date.date().toString(Qt.DateFormat.ISODate)

        def _op():
            return db.export_sales_csv(file_path, start, end)

        def _done(count):
            play_success_ding()
            QMessageBox.information(self, "Export Complete", f"Exported {count} sales transactions to:\n{file_path}")

        self._run(_op, _done)
