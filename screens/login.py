"""PIN login, role-based navigation, and main application shell with Auto-Backup."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QRegularExpression, Qt, Signal, Slot, QTimer, QStorageInfo
from PySide6.QtGui import QFont, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget, QFileDialog,
)

from app_settings import load_settings
from db import db
from .billing import BillingScreen
from .customers import CustomerKhataScreen
from .insights import InsightsDashboard
from .products import ProductManagementScreen
from .returns import SaleReturnsScreen
from .settings import AdminSettingsPage
from .suppliers import SuppliersScreen
from .cash_closing import CashClosingDialog
from services.sound import play_error_beep, play_success_ding


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


class LoginScreen(QWidget):
    authenticated = Signal(object)
    operation_done = Signal(object, object)
    operation_failed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self.busy = False
        self._failed_attempts = 0
        self._lockout_remaining = 0
        self._lockout_timer = QTimer(self)
        self._lockout_timer.setInterval(1000)
        self._lockout_timer.timeout.connect(self._lockout_tick)
        self.operation_done.connect(self._finished)
        self.operation_failed.connect(self._failed)
        self._buttons = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.addStretch()

        brand_card = QLabel("⚡ ShopFlow POS")
        brand_card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_card.setFont(QFont("Segoe UI", 27, QFont.Weight.Black))
        root.addWidget(brand_card)

        sub = QLabel("Smart Offline Point of Sale System")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Segoe UI", 10))
        root.addWidget(sub)

        prompt = QLabel("Enter your 4-digit Staff PIN")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt.setFont(QFont("Segoe UI", 10))
        root.addWidget(prompt)

        self.pin = QLineEdit()
        self.pin.setMaxLength(8)
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin.setPlaceholderText("••••")
        self.pin.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]{0,8}"), self.pin))
        self.pin.returnPressed.connect(self._login)
        self.pin.setMinimumWidth(240)
        self.pin.setMaximumWidth(280)
        self.pin.setFont(QFont("Segoe UI", 21, QFont.Weight.Black))

        pin_row = QHBoxLayout()
        pin_row.addStretch()
        pin_row.addWidget(self.pin)
        pin_row.addStretch()
        root.addLayout(pin_row)

        pad = QGridLayout()
        pad.setSpacing(8)
        for number in range(1, 10):
            button = QPushButton(str(number))
            button.setMinimumSize(78, 60)
            button.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
            button.clicked.connect(lambda _=False, digit=str(number): self.pin.insert(digit))
            pad.addWidget(button, (number - 1) // 3, (number - 1) % 3)
            self._buttons.append(button)

        clear = QPushButton("Clear")
        clear.setFont(QFont("Segoe UI", 10))
        clear.clicked.connect(self.pin.clear)
        pad.addWidget(clear, 3, 0)

        zero = QPushButton("0")
        zero.setMinimumSize(78, 60)
        zero.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        zero.clicked.connect(lambda: self.pin.insert("0"))
        pad.addWidget(zero, 3, 1)

        back = QPushButton("⌫")
        back.setFont(QFont("Segoe UI", 12))
        back.clicked.connect(lambda: self.pin.backspace())
        pad.addWidget(back, 3, 2)
        self._buttons.extend((clear, zero, back))

        row = QHBoxLayout()
        row.addStretch()
        row.addLayout(pad)
        row.addStretch()
        root.addLayout(row)

        self.login_button = QPushButton("🔐  Sign In")
        self.login_button.setMinimumHeight(48)
        self.login_button.setMinimumWidth(240)
        self.login_button.setProperty("variant", "primary")
        self.login_button.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.login_button.clicked.connect(self._login)
        self._buttons.append(self.login_button)

        submit = QHBoxLayout()
        submit.addStretch()
        submit.addWidget(self.login_button)
        submit.addStretch()
        root.addLayout(submit)

        self.setup_button = QPushButton("Set up first shop owner account")
        self.setup_button.clicked.connect(self._setup_first_admin)
        self.setup_button.hide()
        setup_row = QHBoxLayout()
        setup_row.addStretch()
        setup_row.addWidget(self.setup_button)
        setup_row.addStretch()
        root.addLayout(setup_row)

        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setFont(QFont("Segoe UI", 10))
        root.addWidget(self.status)
        root.addStretch()

        check = _Worker(db.user_count)
        check.signals.done.connect(lambda count: self.operation_done.emit(self._users_checked, count))
        check.signals.failed.connect(self.operation_failed.emit)
        self._worker = check
        self.pool.start(check)

    def _users_checked(self, count):
        self.setup_button.setVisible(count == 0)

    def _setup_first_admin(self):
        from .settings import _AddUserDialog
        dialog = _AddUserDialog(self)
        dialog.setWindowTitle("Set up Shop Owner")
        dialog.role.setCurrentIndex(dialog.role.findData("admin"))
        dialog.role.setEnabled(False)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, pin = dialog.name.text().strip(), dialog.pin.text()
        self.status.setText("Creating owner account…")
        for button in self._buttons:
            button.setEnabled(False)
        worker = _Worker(lambda: db.create_user_with_pin(name, "admin", pin))
        worker.signals.done.connect(lambda _uid: self.operation_done.emit(self._first_admin_created, None))
        worker.signals.failed.connect(self.operation_failed.emit)
        self._worker = worker
        self.pool.start(worker)

    def _first_admin_created(self, _result):
        self.setup_button.hide()
        play_success_ding()
        self.status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status.setText("Owner account created. Enter your PIN to sign in.")
        self.pin.setFocus()

    def _login(self):
        if self._lockout_remaining > 0:
            play_error_beep()
            self.status.setText(f"Too many failed attempts. Try again in {self._lockout_remaining}s.")
            return
        pin = self.pin.text()
        if not pin.isdigit() or not 4 <= len(pin) <= 8:
            play_error_beep()
            self.status.setText("Enter your 4 to 8 digit PIN.")
            return
        if self.busy:
            return
        self.busy = True
        self.status.setText("Signing in…")
        for button in self._buttons:
            button.setEnabled(False)
        self.pin.setEnabled(False)
        worker = _Worker(lambda: db.authenticate_pin(pin))
        worker.signals.done.connect(lambda user: self.operation_done.emit(self._auth_result, user))
        worker.signals.failed.connect(self.operation_failed.emit)
        self._worker = worker
        self.pool.start(worker)

    def _finished(self, callback, value):
        self.busy = False
        if self._lockout_remaining <= 0:
            for button in self._buttons:
                button.setEnabled(True)
            self.pin.setEnabled(True)
        callback(value)

    def _auth_result(self, user):
        if not user:
            self._failed_attempts += 1
            play_error_beep()
            self.pin.clear()
            if self._failed_attempts >= 5:
                self._lockout_remaining = 30
                self._lockout_timer.start()
                self.pin.setEnabled(False)
                for button in self._buttons:
                    button.setEnabled(False)
                self.status.setText(f"Too many failed attempts. Locked for 30s.")
            else:
                remaining = 5 - self._failed_attempts
                self.pin.setFocus()
                self.status.setText(f"PIN not recognized. {remaining} attempt(s) remaining.")
            return
        # Success: reset lockout counters
        self._failed_attempts = 0
        self._lockout_remaining = 0
        self._lockout_timer.stop()
        play_success_ding()
        self.pin.clear()
        self.status.clear()
        self.authenticated.emit(user)

    def _lockout_tick(self):
        self._lockout_remaining -= 1
        if self._lockout_remaining <= 0:
            self._lockout_timer.stop()
            self._failed_attempts = 0
            self.pin.setEnabled(True)
            for button in self._buttons:
                button.setEnabled(True)
            self.status.setText("Lockout expired. Please enter your PIN.")
            self.pin.setFocus()
        else:
            self.status.setText(f"Too many failed attempts. Locked for {self._lockout_remaining}s.")

    def _failed(self, error):
        self.busy = False
        for button in self._buttons:
            button.setEnabled(True)
        play_error_beep()
        details = f"{type(error).__name__}: {error}"
        self.status.setText("Database sign-in failed.")
        QMessageBox.warning(self, "Sign-in database error", details)


class _Workspace(QWidget):
    logged_out = Signal()

    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.user = user
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top Navigation Bar
        nav = QHBoxLayout()
        nav.setContentsMargins(14, 8, 14, 8)

        brand = QLabel("ShopFlow POS")
        brand.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        nav.addWidget(brand)

        self.pages = QStackedWidget()
        self.page_index = {}
        self.nav_buttons = {}

        # Core Pages
        self.billing_screen = BillingScreen(self)
        self._add_page("⚡ Billing", self.billing_screen)
        self._add_page("🔄 Returns & Refund", SaleReturnsScreen(self))
        self._add_page("👥 Khata (Credit)", CustomerKhataScreen(self))

        if user["role"] == "admin":
            self._add_page("📦 Inventory", ProductManagementScreen(self))
            self._add_page("📊 Insights", InsightsDashboard(self))
            self._add_page("⚙️ Settings", AdminSettingsPage(self))

        if user["role"] == "admin":
            self._add_page("Suppliers & Purchasing", SuppliersScreen(self))

        for name in self.page_index:
            button = QPushButton(name.replace("&", "&&"))
            button.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            button.clicked.connect(lambda _=False, page=name: self._show_page(page))
            self.nav_buttons[name] = button
            nav.addWidget(button)

        nav.addStretch()
        close_cash = QPushButton("Day End / Cash Drawer")
        close_cash.clicked.connect(self._cash_closing)
        nav.addWidget(close_cash)

        who = QLabel(f"👤 {user['name']} ({user['role'].title()})")
        who.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        who.setStyleSheet("color: #334155; padding: 0 8px;")
        nav.addWidget(who)

        logout = QPushButton("Log out")
        logout.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        logout.setStyleSheet("color: #DC2626; border: 1px solid #FCA5A5; background: #FEF2F2;")
        logout.clicked.connect(self.logged_out.emit)
        nav.addWidget(logout)

        nav_container = QWidget()
        nav_container.setLayout(nav)
        nav_container.setObjectName("navigationBar")
        root.addWidget(nav_container)

        root.addWidget(self.pages, 1)
        self._show_page("⚡ Billing")

    def _add_page(self, name, page):
        self.page_index[name] = self.pages.addWidget(page)

    def _cash_closing(self):
        CashClosingDialog(self.user, self).exec()

    def start_exchange(self, amount, voucher_code):
        self._show_page("⚡ Billing")
        self.billing_screen.apply_exchange_credit(amount, voucher_code)

    def _show_page(self, name):
        self.pages.setCurrentIndex(self.page_index[name])
        for btn_name, btn in self.nav_buttons.items():
            if btn_name == name:
                btn.setProperty("navActive", True)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            else:
                btn.setProperty("navActive", False)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        # Auto refresh screens when navigating
        current_widget = self.pages.currentWidget()
        if hasattr(current_widget, "refresh"):
            current_widget.refresh()
        elif hasattr(current_widget, "reload_data"):
            current_widget.reload_data()


class ShopFlowWindow(QMainWindow):
    """Main POS Application window with automatic background backup on exit."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ShopFlow POS — Professional Offline Retail POS")
        self.setMinimumSize(1024, 700)
        self.stack = QStackedWidget()
        self.login = LoginScreen(self)
        self.login.authenticated.connect(self._open_workspace)
        self.stack.addWidget(self.login)
        self.setCentralWidget(self.stack)

    def _open_workspace(self, user):
        workspace = _Workspace(user, self)
        workspace.logged_out.connect(lambda: self._show_login(workspace))
        self.stack.addWidget(workspace)
        self.stack.setCurrentWidget(workspace)
        QTimer.singleShot(400, self._external_backup_reminder)

    def _external_backup_reminder(self, force=False):
        from datetime import date
        from app_settings import save_settings
        settings = load_settings()
        today = date.today().isoformat()
        last = settings.get("last_external_backup_date")
        try:
            age = (date.today() - date.fromisoformat(last)).days if last else 999
        except ValueError:
            age = 999
        if age < 7 or (not force and settings.get("backup_reminder_date") == today):
            return
        save_settings({"backup_reminder_date": today})
        box = QMessageBox(self)
        box.setWindowTitle("Database Backup Reminder")
        box.setText(f"Your last external backup was taken {age} days ago. To prevent data loss if your computer hard drive fails, please insert a USB flash drive and backup now.")
        backup = box.addButton("Backup to USB Now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Remind me later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == backup:
            self._backup_external()

    def _backup_external(self):
        from datetime import date
        from app_settings import save_settings
        volumes = [v.rootPath() for v in QStorageInfo.mountedVolumes() if v.isValid() and v.isReady() and v.isRemovable()]
        if not volumes:
            QMessageBox.warning(self, "USB drive not detected", "Insert a removable USB drive before creating an external backup.")
            return
        initial = volumes[0]
        folder = QFileDialog.getExistingDirectory(self, "Choose USB backup folder", initial)
        if not folder:
            return
        target = folder.replace("/", "\\").casefold().rstrip("\\")
        if not any(target == root.replace("/", "\\").casefold().rstrip("\\") or
                   target.startswith(root.replace("/", "\\").casefold().rstrip("\\") + "\\")
                   for root in volumes):
            QMessageBox.warning(self, "Choose a USB drive", "External backups must be saved on a detected removable drive.")
            return
        try:
            path = db.backup_database(folder)
            save_settings({"last_external_backup_date": date.today().isoformat()})
            QMessageBox.information(self, "Backup complete", f"External database backup saved:\n{path}")
        except Exception as error:
            QMessageBox.warning(self, "Backup failed", str(error))

    def _show_login(self, workspace):
        self.stack.removeWidget(workspace)
        workspace.deleteLater()
        self.stack.setCurrentWidget(self.login)
        self.login.pin.setFocus()

    def closeEvent(self, event):
        self._external_backup_reminder(force=True)
        # Auto-backup database on close if enabled
        if load_settings().get("auto_backup", True):
            try:
                backup_folder = Path.home() / "Documents" / "ShopFlow POS" / "AutoBackups"
                db.backup_database(backup_folder)
            except Exception:
                pass
        event.accept()
