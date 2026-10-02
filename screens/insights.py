"""Comprehensive sales and business intelligence dashboard with Smart Restock Advisor."""

from __future__ import annotations

from typing import Any, Callable

import pyqtgraph as pg
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from db import db


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


class _MetricCard(QFrame):
    def __init__(self, title, accent_color="#2563EB", border_color="#CBD5E1"):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ "
            f"background-color: #FFFFFF; "
            f"border: 1px solid {border_color}; "
            f"border-top: 4px solid {accent_color}; "
            f"border-radius: 8px; "
            f"}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self.title = QLabel(title)
        self.title.setStyleSheet(
            "color: #475569; font-size: 11px; font-weight: 700; border: none; "
            "background: transparent; text-transform: uppercase; letter-spacing: 0.5px;"
        )
        self.value = QLabel("Rs 0.00")
        self.value.setStyleSheet(
            "font-size: 22px; font-weight: 800; border: none; background: transparent; color: #0F172A;"
        )
        self.detail = QLabel("Profit: Rs 0.00")
        self.detail.setStyleSheet(
            "color: #15803D; font-size: 12px; font-weight: 700; border: none; background: transparent;"
        )
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)


class InsightsDashboard(QWidget):
    """Business Intelligence dashboard with SQL aggregates, Reorder Advisor, and pyqtgraph charts."""

    operation_done = Signal(object, object)
    operation_failed = Signal(object)
    PERIODS = ("today", "week", "month")
    LABELS = {"today": "Today's Performance", "week": "This Week", "month": "This Month"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self.busy = False
        self._latest = None
        self.operation_done.connect(self._finished)
        self.operation_failed.connect(self._failed)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # Top Bar
        top = QHBoxLayout()
        title = QLabel("Business Insights & Analytics")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #0F172A;")
        top.addWidget(title)
        top.addStretch()

        top.addWidget(QLabel("Chart Period:"))
        self.period = QComboBox()
        self.period.addItem("Today", "today")
        self.period.addItem("This Week", "week")
        self.period.addItem("This Month", "month")
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.period)

        self.refresh_button = QPushButton("Refresh Data")
        self.refresh_button.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 6px 14px;")
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        root.addLayout(top)

        # 5 Metric Cards Grid
        cards = QGridLayout()
        cards.setSpacing(12)
        accents = {
            "today": "#2563EB",
            "week": "#4F46E5",
            "month": "#7C3AED",
        }
        self.metrics = {name: _MetricCard(self.LABELS[name], accent_color=accents[name]) for name in self.PERIODS}
        for column, name in enumerate(self.PERIODS):
            cards.addWidget(self.metrics[name], 0, column)

        self.stock_card = _MetricCard("Stock Valuation (Cost)", accent_color="#0D9488")
        self.stock_card.detail.setText("Total inventory asset value")
        self.stock_card.detail.setStyleSheet("color: #64748B; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        cards.addWidget(self.stock_card, 0, 3)

        self.khata_card = _MetricCard("Market Khata Due", accent_color="#DC2626", border_color="#FCA5A5")
        self.khata_card.value.setStyleSheet("font-size: 22px; font-weight: 800; border: none; background: transparent; color: #B91C1C;")
        self.khata_card.detail.setText("Customer credit to collect")
        self.khata_card.detail.setStyleSheet("color: #DC2626; font-size: 12px; font-weight: 700; border: none; background: transparent;")
        cards.addWidget(self.khata_card, 0, 4)
        root.addLayout(cards)

        # Tabs: 1. Sales & Peak Hours  2. Smart Restock Advisor & Dead Stock
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { font-size: 13px; font-weight: bold; padding: 8px 18px; }")

        # Tab 1: Charts
        charts_widget = QWidget()
        charts_layout = QGridLayout(charts_widget)
        charts_layout.setContentsMargins(12, 12, 12, 12)
        charts_layout.setSpacing(14)

        top_plot_card = QFrame()
        top_plot_card.setProperty("visualRole", "card")
        top_card_lay = QVBoxLayout(top_plot_card)
        top_card_lay.setContentsMargins(8, 8, 8, 8)
        self.top_plot = pg.PlotWidget()
        self.top_plot.setBackground("w")
        self.top_plot.setTitle("Top Best Selling Products")
        self.top_plot.setLabel("left", "Units Sold")
        self.top_plot.showGrid(y=True, alpha=0.2)
        self.top_plot.setMinimumHeight(240)
        top_card_lay.addWidget(self.top_plot)

        hour_plot_card = QFrame()
        hour_plot_card.setProperty("visualRole", "card")
        hour_card_lay = QVBoxLayout(hour_plot_card)
        hour_card_lay.setContentsMargins(8, 8, 8, 8)
        self.hour_axis = pg.AxisItem(orientation="bottom")
        self.hour_plot = pg.PlotWidget(axisItems={"bottom": self.hour_axis})
        self.hour_plot.setBackground("w")
        self.hour_plot.setTitle("Peak Business Hours (Hourly Customer Volume)")
        self.hour_plot.setLabel("left", "Total Bills")
        self.hour_plot.showGrid(x=True, y=True, alpha=0.2)
        self.hour_plot.setMinimumHeight(240)
        hour_card_lay.addWidget(self.hour_plot)

        charts_layout.addWidget(top_plot_card, 0, 0, 1, 3)
        charts_layout.addWidget(hour_plot_card, 0, 3, 1, 2)
        self.tabs.addTab(charts_widget, "📊 Sales & Peak Hours Charts")

        # Tab 2: Smart Restock Advisor
        advisor_widget = QWidget()
        advisor_layout = QVBoxLayout(advisor_widget)
        advisor_layout.setContentsMargins(10, 10, 10, 10)

        adv_header = QHBoxLayout()
        adv_title = QLabel("🤖 Smart Restock & Purchasing Advisor")
        adv_title.setStyleSheet("font-weight: 700; font-size: 15px; color: #0f172a;")
        adv_header.addWidget(adv_title)
        adv_header.addStretch()
        self.restock_budget_label = QLabel("Est. Restock Budget: Rs 0.00")
        self.restock_budget_label.setStyleSheet("background: #fef3c7; color: #92400e; padding: 5px 12px; border-radius: 6px; font-weight: bold;")
        adv_header.addWidget(self.restock_budget_label)
        advisor_layout.addLayout(adv_header)

        self.restock_table = QTableWidget(0, 6)
        self.restock_table.setHorizontalHeaderLabels(["Product Name", "Current Stock", "Threshold", "Unit Cost", "Suggested Order Qty", "Est. Cost"])
        self.restock_table.verticalHeader().setVisible(False)
        self.restock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.restock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            self.restock_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        advisor_layout.addWidget(self.restock_table)
        self.tabs.addTab(advisor_widget, "📦 Smart Restock Advisor")

        # Tab 3: Dead / Slow Moving Stock
        slow_widget = QWidget()
        slow_layout = QVBoxLayout(slow_widget)
        slow_layout.setContentsMargins(10, 10, 10, 10)
        slow_title = QLabel("Products with Zero Sales in this period (Potential Dead Capital)")
        slow_title.setStyleSheet("font-weight: 600; font-size: 14px; color: #475569;")
        slow_layout.addWidget(slow_title)

        self.slow_table = QTableWidget(0, 3)
        self.slow_table.setHorizontalHeaderLabels(["Product Name", "In Stock (Unsold)", "Threshold"])
        self.slow_table.verticalHeader().setVisible(False)
        self.slow_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.slow_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 3):
            self.slow_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        slow_layout.addWidget(self.slow_table)
        self.tabs.addTab(slow_widget, "⚠️ Dead Stock Alert")

        root.addWidget(self.tabs, 1)

        self.status = QLabel("Loading insights…")
        self.status.setStyleSheet("color: #64748b; font-size: 12px;")
        root.addWidget(self.status)

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.setEnabled(False)
        self.period.setEnabled(False)
        period = self.period.currentData()
        worker = _Worker(lambda: db.get_dashboard_insights(period))
        worker.signals.done.connect(lambda result: self.operation_done.emit(self._loaded, result))
        worker.signals.failed.connect(self.operation_failed.emit)
        self._worker = worker
        self.pool.start(worker)

    def _finished(self, callback, result):
        self.busy = False
        self.refresh_button.setEnabled(True)
        self.period.setEnabled(True)
        callback(result)

    def _failed(self, error):
        self.busy = False
        self.refresh_button.setEnabled(True)
        self.period.setEnabled(True)
        self.status.setText(f"Could not load dashboard data: {error}")

    def _loaded(self, data):
        self._latest = data
        summary = data["summary"]
        for key, name in (("today", "today"), ("week", "week"), ("month", "month")):
            card = self.metrics[name]
            card.value.setText(f"Rs {summary[f'{key}_sales']:,.2f}")
            card.detail.setText(f"Profit: Rs {summary[f'{key}_profit']:,.2f}")

        self.stock_card.value.setText(f"Rs {data['stock_value']:,.2f}")
        self.khata_card.value.setText(f"Rs {data.get('total_khata_due', 0):,.2f}")

        self._draw_selected_period()
        self.status.setText("Dashboard refreshed successfully.")

    def _draw_selected_period(self):
        if self._latest is None:
            return
        self._draw_top_products(self._latest.get("top_products", []))

        hourly = self._latest.get("hourly_sales", {})
        x = list(range(24))
        y = [hourly.get(hour, 0) for hour in x]
        ticks = [(hour, f"{hour:02d}:00") for hour in range(0, 24, 3)]
        self.hour_axis.setTicks([ticks])
        self.hour_plot.clear()
        self.hour_plot.plot(
            x, y, pen=pg.mkPen("#0284c7", width=2.5),
            symbol="o", symbolSize=6, symbolBrush="#0284c7"
        )
        self.hour_plot.setXRange(-0.5, 23.5, padding=0)

        self._draw_restock_table(self._latest.get("restock_needed", []))
        self._draw_slow_products(self._latest.get("slow_products", []))

    def _draw_top_products(self, products):
        self.top_plot.clear()
        if not products:
            self.top_plot.setTitle("Top Best Sellers · No sales yet in this period")
            return
        self.top_plot.setTitle("Top Best Selling Products")
        axis = self.top_plot.getAxis("bottom")
        axis.setTicks([[(index, row["name"][:16]) for index, row in enumerate(products)]])
        bars = pg.BarGraphItem(
            x=list(range(len(products))),
            height=[row["quantity"] for row in products],
            width=0.6, brush=QColor("#0ea5e9")
        )
        self.top_plot.addItem(bars)
        self.top_plot.setXRange(-0.6, max(0.6, len(products) - 0.4), padding=0)

    def _draw_restock_table(self, restock_items):
        self.restock_table.setRowCount(len(restock_items))
        total_budget = 0.0
        for row, it in enumerate(restock_items):
            cost = float(it.get("estimated_cost") or 0)
            total_budget += cost
            values = (
                it["name"],
                str(it["stock_qty"]),
                str(it["low_stock_threshold"]),
                f"Rs {float(it['cost_price']):,.2f}",
                str(it["suggested_order"]),
                f"Rs {cost:,.2f}"
            )
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setForeground(QColor("#991b1b"))
                item.setBackground(QColor("#fee2e2"))
                if col > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.restock_table.setItem(row, col, item)
        self.restock_budget_label.setText(f"Est. Restock Budget: Rs {total_budget:,.2f}")

    def _draw_slow_products(self, products):
        self.slow_table.setRowCount(len(products))
        for row, product in enumerate(products):
            values = (product["name"], str(product["stock_qty"]), str(product["low_stock_threshold"]))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.slow_table.setItem(row, column, item)
