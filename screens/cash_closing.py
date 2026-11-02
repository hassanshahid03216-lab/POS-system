"""Cash drawer opening, shift reconciliation, and Day-End closing management."""

from __future__ import annotations

from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from db import db
from services.receipts import print_or_save_receipt


class CashClosingDialog(QDialog):
    """Modern Cash Drawer management supporting shift opening, live reconciliation, and Day-End history."""

    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("Day End & Cash Drawer Management")
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)
        self.shift = db.active_cash_shift()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # 1. Header with Current User & Status
        header = QHBoxLayout()
        user_info = QLabel(f"👤 Logged In: <b>{user['name']}</b> ({user['role'].title()})")
        user_info.setStyleSheet("font-size: 13px; color: #334155;")
        header.addWidget(user_info)
        header.addStretch()

        if self.shift:
            status_badge = QLabel(f"🟢 Shift #{self.shift['id']} Active")
            status_badge.setStyleSheet(
                "background: #DCFCE7; color: #166534; font-weight: bold; font-size: 11px; "
                "padding: 4px 10px; border-radius: 12px; border: 1px solid #86EFAC;"
            )
        else:
            status_badge = QLabel("⚪ Drawer Closed")
            status_badge.setStyleSheet(
                "background: #F1F5F9; color: #64748B; font-weight: bold; font-size: 11px; "
                "padding: 4px 10px; border-radius: 12px; border: 1px solid #CBD5E1;"
            )
        header.addWidget(status_badge)
        root.addLayout(header)

        # 2. Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { font-size: 12px; font-weight: bold; padding: 7px 16px; }
            QTabBar::tab:selected { background: #FFFFFF; border-bottom: 3px solid #0284C7; }
        """)
        self.tabs.addTab(self._build_register_tab(), "💵 Register Control" if self.shift else "🟢 Start Cash Shift")
        self.tabs.addTab(self._build_history_tab(), "📅 Today's Day-End History")
        root.addWidget(self.tabs, 1)

    # ── TAB 1: Register Control (Open / Close Shift) ─────────────────────────

    def _build_register_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(12)

        if not self.shift:
            # ── Case A: No Shift Active -> Prompt to Start Shift
            info_box = QFrame()
            info_box.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
            info_lay = QVBoxLayout(info_box)
            title = QLabel("🟢 Open Cash Drawer (Start New Shift)")
            title.setStyleSheet("font-size: 15px; font-weight: 750; color: #0F172A;")
            desc = QLabel("Enter the starting cash float (bills and coins) currently in the cash drawer.")
            desc.setStyleSheet("font-size: 12px; color: #64748B;")
            info_lay.addWidget(title)
            info_lay.addWidget(desc)
            layout.addWidget(info_box)

            form_grid = QGridLayout()
            form_grid.setSpacing(8)

            lbl_float = QLabel("Opening Float (Rs):")
            lbl_float.setStyleSheet("font-weight: 600; font-size: 13px; color: #334155;")
            self.open_amount = QDoubleSpinBox()
            self.open_amount.setRange(0, 999999999)
            self.open_amount.setDecimals(2)
            self.open_amount.setPrefix("Rs ")
            self.open_amount.setValue(0.0)
            self.open_amount.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            self.open_amount.setStyleSheet("padding: 6px; min-height: 36px;")

            form_grid.addWidget(lbl_float, 0, 0)
            form_grid.addWidget(self.open_amount, 0, 1)

            # Quick Preset Buttons
            preset_row = QHBoxLayout()
            for preset_val in (0, 5000, 10000, 20000):
                btn = QPushButton(f"Rs {preset_val:,.0f}" if preset_val > 0 else "Rs 0 (Empty)")
                btn.setStyleSheet("padding: 4px 10px; font-size: 11px; background: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 4px;")
                btn.clicked.connect(lambda _=False, v=preset_val: self.open_amount.setValue(float(v)))
                preset_row.addWidget(btn)
            preset_row.addStretch()
            form_grid.addLayout(preset_row, 1, 1)

            lbl_notes = QLabel("Shift Notes:")
            lbl_notes.setStyleSheet("font-weight: 600; font-size: 13px; color: #334155;")
            self.open_notes = QLineEdit()
            self.open_notes.setPlaceholderText("Optional notes (e.g. Morning Shift, Drawer #1)")
            self.open_notes.setStyleSheet("padding: 6px; min-height: 28px;")
            form_grid.addWidget(lbl_notes, 2, 0)
            form_grid.addWidget(self.open_notes, 2, 1)

            layout.addLayout(form_grid)
            layout.addStretch()

            btn_row = QHBoxLayout()
            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(self.reject)
            start_btn = QPushButton("🟢 Start Cash Shift & Open Drawer")
            start_btn.setStyleSheet(
                "background: #16A34A; color: white; font-weight: bold; font-size: 13px; "
                "padding: 10px 20px; border-radius: 6px;"
            )
            start_btn.clicked.connect(self._start_shift)
            btn_row.addWidget(cancel_btn)
            btn_row.addStretch()
            btn_row.addWidget(start_btn)
            layout.addLayout(btn_row)

        else:
            # ── Case B: Shift Active -> Display Breakdown and Reconcile / Close
            summary = db.cash_shift_summary(self.shift["id"])
            self.summary_data = summary

            # Summary Card
            summary_card = QFrame()
            summary_card.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
            s_lay = QVBoxLayout(summary_card)
            s_lay.setSpacing(6)

            title_row = QHBoxLayout()
            s_title = QLabel(f"Active Shift #{self.shift['id']} Summary")
            s_title.setStyleSheet("font-size: 14px; font-weight: 750; color: #0F172A;")
            opened_info = QLabel(f"Opened by <b>{self.shift['cashier_name']}</b> at {self.shift['opened_at'][11:16]}")
            opened_info.setStyleSheet("font-size: 12px; color: #64748B;")
            title_row.addWidget(s_title)
            title_row.addStretch()
            title_row.addWidget(opened_info)
            s_lay.addLayout(title_row)

            # Warning if different user
            if str(self.shift["cashier_id"]) != str(self.user["id"]):
                other_warn = QLabel(f"⚠️ Note: This shift was opened by <b>{self.shift['cashier_name']}</b>. Reconciling now will close their session.")
                other_warn.setStyleSheet("background: #FEF3C7; color: #92400E; padding: 5px 8px; border-radius: 4px; font-size: 11px;")
                s_lay.addWidget(other_warn)

            grid = QGridLayout()
            grid.setSpacing(6)
            grid.addWidget(QLabel("Opening Float:"), 0, 0)
            grid.addWidget(QLabel(f"Rs {float(self.shift['opening']):,.2f}"), 0, 1)

            grid.addWidget(QLabel("(+) Cash Sales:"), 0, 2)
            lbl_sales = QLabel(f"Rs {summary['cash_sales']:,.2f}")
            lbl_sales.setStyleSheet("color: #16A34A; font-weight: bold;")
            grid.addWidget(lbl_sales, 0, 3)

            grid.addWidget(QLabel("(+) Khata Cash Recoveries:"), 1, 0)
            grid.addWidget(QLabel(f"Rs {summary['khata_recoveries']:,.2f}"), 1, 1)

            grid.addWidget(QLabel("(-) Cash Refunds:"), 1, 2)
            lbl_refund = QLabel(f"Rs {summary['cash_refunds']:,.2f}")
            lbl_refund.setStyleSheet("color: #DC2626;")
            grid.addWidget(lbl_refund, 1, 3)

            grid.addWidget(QLabel("(-) Petty Cash Expenses:"), 2, 0)
            lbl_exp = QLabel(f"Rs {summary['expenses']:,.2f}")
            lbl_exp.setStyleSheet("color: #DC2626;")
            grid.addWidget(lbl_exp, 2, 1)

            s_lay.addLayout(grid)

            # Big Expected Banner
            expected_banner = QFrame()
            expected_banner.setStyleSheet("background: #EFF6FF; border: 1.5px solid #93C5FD; border-radius: 6px; padding: 8px;")
            b_lay = QHBoxLayout(expected_banner)
            b_text = QLabel("Expected Cash in Drawer:")
            b_text.setStyleSheet("font-size: 13px; font-weight: 700; color: #1E40AF;")
            self.expected_val_lbl = QLabel(f"Rs {summary['expected']:,.2f}")
            self.expected_val_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #1D4ED8;")
            b_lay.addWidget(b_text)
            b_lay.addStretch()
            b_lay.addWidget(self.expected_val_lbl)
            s_lay.addWidget(expected_banner)

            layout.addWidget(summary_card)

            # Counted Cash Input & Live Variance
            reconcile_box = QFrame()
            reconcile_box.setStyleSheet("background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 10px;")
            r_lay = QVBoxLayout(reconcile_box)
            r_lay.setSpacing(6)

            count_row = QHBoxLayout()
            c_lbl = QLabel("Physical Counted Cash (Rs):")
            c_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #0F172A;")
            
            self.counted_amount = QDoubleSpinBox()
            self.counted_amount.setRange(0, 999999999)
            self.counted_amount.setDecimals(2)
            self.counted_amount.setPrefix("Rs ")
            self.counted_amount.setValue(summary["expected"])
            self.counted_amount.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            self.counted_amount.setStyleSheet("padding: 4px 8px; min-height: 34px;")
            self.counted_amount.valueChanged.connect(self._update_variance_banner)

            match_btn = QPushButton("Match Expected")
            match_btn.setToolTip("Fill exact expected cash")
            match_btn.setStyleSheet("padding: 4px 10px; font-size: 11px;")
            match_btn.clicked.connect(lambda: self.counted_amount.setValue(self.summary_data["expected"]))

            count_row.addWidget(c_lbl)
            count_row.addWidget(self.counted_amount, 1)
            count_row.addWidget(match_btn)
            r_lay.addLayout(count_row)

            # Live Variance Banner
            self.variance_banner = QLabel()
            self.variance_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.variance_banner.setStyleSheet("font-weight: bold; font-size: 12px; padding: 6px; border-radius: 4px;")
            r_lay.addWidget(self.variance_banner)

            notes_row = QHBoxLayout()
            notes_lbl = QLabel("Closing Notes:")
            notes_lbl.setStyleSheet("font-size: 12px; color: #475569;")
            self.close_notes = QLineEdit()
            self.close_notes.setPlaceholderText("Optional closing remarks (reason for discrepancy, etc.)")
            notes_row.addWidget(notes_lbl)
            notes_row.addWidget(self.close_notes, 1)
            r_lay.addLayout(notes_row)

            layout.addWidget(reconcile_box)

            # Actions
            btn_row = QHBoxLayout()
            expense_btn = QPushButton("💸 Record Petty Cash Expense")
            expense_btn.setStyleSheet("padding: 7px 12px; font-size: 12px;")
            expense_btn.clicked.connect(self._expense)
            btn_row.addWidget(expense_btn)

            btn_row.addStretch()

            keep_open_btn = QPushButton("Cancel / Keep Open")
            keep_open_btn.clicked.connect(self.reject)
            btn_row.addWidget(keep_open_btn)

            close_btn = QPushButton("🔴 Close Shift & Print Summary")
            close_btn.setStyleSheet(
                "background: #DC2626; color: white; font-weight: bold; font-size: 13px; "
                "padding: 8px 18px; border-radius: 6px;"
            )
            close_btn.clicked.connect(self._close_shift)
            btn_row.addWidget(close_btn)

            layout.addLayout(btn_row)
            self._update_variance_banner()

        return widget

    def _update_variance_banner(self):
        if not hasattr(self, "summary_data") or not hasattr(self, "counted_amount"):
            return
        counted = self.counted_amount.value()
        expected = self.summary_data["expected"]
        variance = counted - expected

        if abs(variance) < 0.01:
            self.variance_banner.setText("✅ Exact Match (Balanced) · Variance: Rs 0.00")
            self.variance_banner.setStyleSheet("background: #DCFCE7; color: #166534; font-weight: bold; padding: 6px; border-radius: 4px;")
        elif variance < 0:
            self.variance_banner.setText(f"❌ Cash Short (Galti / Loss) · Variance: -Rs {abs(variance):,.2f}")
            self.variance_banner.setStyleSheet("background: #FEE2E2; color: #991B1B; font-weight: bold; padding: 6px; border-radius: 4px;")
        else:
            self.variance_banner.setText(f"🔵 Cash Over (Surplus) · Variance: +Rs {variance:,.2f}")
            self.variance_banner.setStyleSheet("background: #DBEAFE; color: #1E40AF; font-weight: bold; padding: 6px; border-radius: 4px;")

    # ── TAB 2: Today's Day-End Summary & Closings History ─────────────────────

    def _build_history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Quick stats header
        summary = db.get_day_end_summary()
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;")
        s_lay = QHBoxLayout(stats_frame)
        s_lay.addWidget(QLabel(f"📅 Date: <b>{summary['date']}</b>"))
        s_lay.addStretch()
        s_lay.addWidget(QLabel(f"Total Cash Collected: <b>Rs {summary['total_cash']:,.2f}</b>"))
        s_lay.addStretch()
        s_lay.addWidget(QLabel(f"Completed Shifts: <b>{summary['shift_count']}</b>"))
        s_lay.addStretch()
        
        disc = summary["total_discrepancy"]
        disc_color = "#166534" if abs(disc) < 0.01 else ("#991B1B" if disc < 0 else "#1E40AF")
        lbl_disc = QLabel(f"Net Drawer Variance: <b>Rs {disc:+,.2f}</b>")
        lbl_disc.setStyleSheet(f"color: {disc_color};")
        s_lay.addWidget(lbl_disc)
        layout.addWidget(stats_frame)

        # Table of today's shift closings
        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels([
            "Shift ID", "Cashier", "Closed Time", "Opening", "Expected", "Counted", "Variance"
        ])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in range(2, 7):
            self.history_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.history_table, 1)

        self._refresh_history_table()

        act_row = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh History")
        refresh_btn.clicked.connect(self._refresh_history_table)
        act_row.addWidget(refresh_btn)
        act_row.addStretch()
        close_dialog_btn = QPushButton("Done")
        close_dialog_btn.clicked.connect(self.accept)
        act_row.addWidget(close_dialog_btn)
        layout.addLayout(act_row)

        return widget

    def _refresh_history_table(self):
        closings = db.list_today_cash_closings()
        self.history_table.setRowCount(len(closings))
        for row, c in enumerate(closings):
            self.history_table.setItem(row, 0, QTableWidgetItem(f"#{c['id']}"))
            self.history_table.setItem(row, 1, QTableWidgetItem(c.get("cashier_name") or "Staff"))
            self.history_table.setItem(row, 2, QTableWidgetItem(c["timestamp"][11:19]))
            self.history_table.setItem(row, 3, QTableWidgetItem(f"Rs {c['opening']:,.2f}"))
            self.history_table.setItem(row, 4, QTableWidgetItem(f"Rs {c['expected']:,.2f}"))
            self.history_table.setItem(row, 5, QTableWidgetItem(f"Rs {c['actual']:,.2f}"))

            disc = c["discrepancy"]
            disc_item = QTableWidgetItem(f"Rs {disc:+,.2f}")
            disc_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            if abs(disc) < 0.01:
                disc_item.setForeground(QColor("#166534"))
            elif disc < 0:
                disc_item.setForeground(QColor("#DC2626"))
            else:
                disc_item.setForeground(QColor("#2563EB"))
            self.history_table.setItem(row, 6, disc_item)

    # ── Shift Actions ────────────────────────────────────────────────────────

    def _start_shift(self):
        opening = self.open_amount.value()
        notes = self.open_notes.text().strip()
        try:
            db.start_cash_shift(self.user["id"], self.user["name"], opening)
            QMessageBox.information(
                self,
                "Cash Shift Started",
                f"Shift started for {self.user['name']} with opening float Rs {opening:,.2f}.\n"
                "Cash drawer is now OPEN."
            )
            self.accept()
        except Exception as error:
            QMessageBox.warning(self, "Cash Shift Error", str(error))

    def _close_shift(self):
        if not self.shift:
            return
        counted = self.counted_amount.value()
        notes = self.close_notes.text().strip()
        try:
            result = db.close_cash_shift(self.shift["id"], counted, notes)
            variance = result["variance"]
            label = "Exact Match (Balanced)" if abs(variance) < 0.005 else ("Cash Short (Loss / Galti)" if variance < 0 else "Cash Over (Surplus)")
            
            QMessageBox.information(
                self,
                "Day End Cash Closing Completed",
                f"{label}\n\n"
                f"Cashier: {result['shift']['cashier_name']}\n"
                f"Expected: Rs {result['expected']:,.2f}\n"
                f"Counted:  Rs {result['actual']:,.2f}\n"
                f"Variance: Rs {variance:+,.2f}\n\n"
                "Shift closed and reconciled successfully."
            )
            print_or_save_receipt({"closing_summary": result})
            self.accept()
        except Exception as error:
            QMessageBox.warning(self, "Cash Closing Error", str(error))

    def _expense(self):
        if not self.shift:
            return
        amount, ok = QInputDialog.getDouble(self, "Petty Cash Expense", "Amount paid from drawer (Rs):", 0, 0.01, 999999999, 2)
        if not ok or amount <= 0:
            return
        note, ok = QInputDialog.getText(self, "Petty Cash Expense", "Purpose / Reason for Expense:")
        if not ok:
            return
        try:
            db.record_cash_expense(amount, note.strip(), self.user["id"])
            summary = db.cash_shift_summary(self.shift["id"])
            self.summary_data = summary
            self.expected_val_lbl.setText(f"Rs {summary['expected']:,.2f}")
            self.counted_amount.setValue(summary["expected"])
            self._update_variance_banner()
            QMessageBox.information(self, "Expense Recorded", f"Petty cash expense of Rs {amount:,.2f} recorded.")
        except Exception as error:
            QMessageBox.warning(self, "Expense Error", str(error))
