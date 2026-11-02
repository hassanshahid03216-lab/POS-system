"""Comprehensive sales and business intelligence dashboard with Smart Restock Advisor and rich analytics graphs."""

from __future__ import annotations

from typing import Any, Callable

import pyqtgraph as pg
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
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


class CurrencyAxis(pg.AxisItem):
    """Formats left Y-axis with clean comma-separated currency values (never scientific notation)."""
    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            if abs(v) < 0.01:
                strings.append("0")
            elif abs(v) >= 1000:
                strings.append(f"{v:,.0f}")
            else:
                strings.append(f"{v:.0f}")
        return strings


class IntegerAxis(pg.AxisItem):
    """Formats left Y-axis with clean whole integer counts."""
    def tickStrings(self, values, scale, spacing):
        return [f"{int(round(v))}" if abs(v - round(v)) < 0.01 and v >= 0 else "" for v in values]


class HourAxis(pg.AxisItem):
    """Clean 24-hour bottom axis for hourly traffic."""
    def __init__(self, orientation="bottom", **kwargs):
        super().__init__(orientation, **kwargs)
        self.setHeight(36)

    def tickValues(self, minVal, maxVal, size):
        hours = [h for h in range(0, 24, 3)]
        return [(3.0, hours)]

    def tickStrings(self, values, scale, spacing):
        return [f"{int(v):02d}:00" if 0 <= v <= 23 else "" for v in values]


class CategoryAxis(pg.AxisItem):
    """Custom PyQtGraph AxisItem that reliably displays string category labels on ticks."""
    def __init__(self, orientation="bottom", **kwargs):
        super().__init__(orientation, **kwargs)
        self._categories: dict[int, str] = {}
        self.setHeight(42)

    def set_categories(self, categories: dict[int, str]):
        self._categories = categories
        ticks = [[(idx, name) for idx, name in categories.items()]]
        self.setTicks(ticks)

    def tickValues(self, minVal, maxVal, size):
        if not self._categories:
            return []
        visible = [idx for idx in self._categories.keys() if (minVal - 0.5) <= idx <= (maxVal + 0.5)]
        return [(1.0, visible)]

    def tickStrings(self, values, scale, spacing):
        strings = []
        for val in values:
            idx = int(round(val))
            if abs(val - idx) < 0.25 and idx in self._categories:
                strings.append(self._categories[idx])
            else:
                strings.append("")
        return strings


def _setup_plot(plot: pg.PlotWidget, title: str, y_label: str = ""):
    """Configures a modern, clean white PyQtGraph plot with static non-distortable axes."""
    plot.setBackground("#FFFFFF")
    plot.setTitle(title, color="#0F172A", size="12pt", bold=True)
    if y_label:
        plot.setLabel("left", y_label, color="#475569", size="10pt")

    # Disable mouse drag and scroll-zoom to completely eliminate axis distortion and scientific notation
    plot.getViewBox().setMouseEnabled(x=False, y=False)
    plot.hideButtons()
    plot.setMenuEnabled(False)

    plot.getAxis("left").enableAutoSIPrefix(False)
    plot.getAxis("bottom").enableAutoSIPrefix(False)
    plot.getAxis("left").setTextPen("#475569")
    plot.getAxis("bottom").setTextPen("#475569")
    plot.showGrid(x=True, y=True, alpha=0.12)
    plot.setMinimumHeight(230)


class InsightsDashboard(QWidget):
    """Business Intelligence dashboard with detailed multi-metric charts and Smart Restock Advisor."""

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
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # 1. Top Bar
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Business Insights & Analytics")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #0F172A;")
        subtitle = QLabel("Live sales trends, customer peak traffic, profit margins & intelligent inventory advisory")
        subtitle.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box)
        top.addStretch()

        period_label = QLabel("Chart Period:")
        period_label.setStyleSheet("font-weight: 600; color: #334155; font-size: 13px;")
        top.addWidget(period_label)

        self.period = QComboBox()
        self.period.addItem("Today", "today")
        self.period.addItem("This Week", "week")
        self.period.addItem("This Month", "month")
        self.period.setCurrentIndex(1)
        self.period.setStyleSheet("padding: 6px 12px; font-weight: 600; border-radius: 6px;")
        self.period.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.period)

        self.refresh_button = QPushButton("↻ Refresh Data")
        self.refresh_button.setStyleSheet(
            "background: #0284c7; color: white; font-weight: bold; padding: 7px 16px; "
            "border-radius: 6px; font-size: 13px;"
        )
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        root.addLayout(top)

        # 2. Metric Cards Grid (5 Cards)
        cards = QGridLayout()
        cards.setSpacing(10)
        accents = {"today": "#2563EB", "week": "#4F46E5", "month": "#7C3AED"}
        self.metrics = {name: _MetricCard(self.LABELS[name], accent_color=accents[name]) for name in self.PERIODS}
        for column, name in enumerate(self.PERIODS):
            cards.addWidget(self.metrics[name], 0, column)

        self.stock_card = _MetricCard("Stock Valuation (Cost)", accent_color="#0D9488")
        self.stock_card.detail.setText("Total inventory asset value")
        self.stock_card.detail.setStyleSheet("color: #64748B; font-size: 11px;")
        cards.addWidget(self.stock_card, 0, 3)

        self.khata_card = _MetricCard("Market Khata Due", accent_color="#DC2626")
        self.khata_card.value.setStyleSheet(
            "font-size: 22px; font-weight: 800; border: none; background: transparent; color: #DC2626;"
        )
        self.khata_card.detail.setText("Customer credit to collect")
        self.khata_card.detail.setStyleSheet("color: #991B1B; font-size: 11px; font-weight: bold;")
        cards.addWidget(self.khata_card, 0, 4)
        root.addLayout(cards)

        # 3. Secondary KPI Strip
        kpi_frame = QFrame()
        kpi_frame.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 12px;")
        kpi_lay = QHBoxLayout(kpi_frame)
        kpi_lay.setSpacing(16)

        self.kpi_orders = QLabel("🧾 Total Bills: 0")
        self.kpi_units = QLabel("📦 Items Sold: 0")
        self.kpi_aov = QLabel("💰 Avg Bill Value: Rs 0.00")
        self.kpi_margin = QLabel("📈 Gross Margin: 0.0%")
        self.kpi_peak = QLabel("🔥 Peak Hour: None")

        for lbl in (self.kpi_orders, self.kpi_units, self.kpi_aov, self.kpi_margin, self.kpi_peak):
            lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none; background: transparent;")
            kpi_lay.addWidget(lbl)
            kpi_lay.addStretch()

        root.addWidget(kpi_frame)

        # 4. Tabbed Analytics Sections
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { font-size: 13px; font-weight: bold; padding: 9px 18px; margin-right: 4px; }
            QTabBar::tab:selected { background: #FFFFFF; border-bottom: 3px solid #0284C7; }
        """)

        # Tab 1: Detailed Charts (Revenue & Profit Trend + Hourly Customer Volume)
        self.tabs.addTab(self._create_charts_tab(), "📈 Sales & Revenue Trends")

        # Tab 2: Best Sellers & Category Breakdown
        self.tabs.addTab(self._create_products_tab(), "🏆 Best Sellers & Categories")

        # Tab 3: Smart Restock Advisor
        self.tabs.addTab(self._create_advisor_tab(), "📦 Smart Restock Advisor")

        # Tab 4: Dead Stock Alert
        self.tabs.addTab(self._create_slow_tab(), "⚠️ Dead Stock Alert")

        root.addWidget(self.tabs, 1)

        self.status = QLabel("Loading insights…")
        self.status.setStyleSheet("color: #64748B; font-size: 12px; font-style: italic;")
        root.addWidget(self.status)

    def _create_charts_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Charts Row
        charts_row = QGridLayout()
        charts_row.setSpacing(14)

        # Chart 1: Revenue vs Net Profit Trend (Line Graph)
        trend_card = QFrame()
        trend_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        trend_lay = QVBoxLayout(trend_card)
        trend_lay.setContentsMargins(12, 12, 12, 12)

        self.trend_axis = CategoryAxis(orientation="bottom")
        self.trend_plot = pg.PlotWidget(axisItems={"bottom": self.trend_axis, "left": CurrencyAxis(orientation="left")})
        _setup_plot(self.trend_plot, "Daily Revenue & Net Profit Trend (Rs)", "Amount (Rs)")
        self.trend_legend = self.trend_plot.addLegend(offset=(10, 10))
        trend_lay.addWidget(self.trend_plot)

        # Chart 2: Peak Business Hours (Hourly Volume)
        hour_card = QFrame()
        hour_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        hour_lay = QVBoxLayout(hour_card)
        hour_lay.setContentsMargins(12, 12, 12, 12)

        self.hour_axis = HourAxis(orientation="bottom")
        self.hour_plot = pg.PlotWidget(axisItems={"bottom": self.hour_axis, "left": IntegerAxis(orientation="left")})
        _setup_plot(self.hour_plot, "Customer Volume by Hour (Peak Traffic)", "Total Bills")
        hour_lay.addWidget(self.hour_plot)

        charts_row.addWidget(trend_card, 0, 0, 1, 3)
        charts_row.addWidget(hour_card, 0, 3, 1, 2)
        layout.addLayout(charts_row, 1)

        # Bottom Row: Highlight Banner connecting cleanly to Tab 2
        highlight_card = QFrame()
        highlight_card.setStyleSheet(
            "QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; } "
            "QLabel { border: none; background: transparent; }"
        )
        h_lay = QHBoxLayout(highlight_card)
        h_lay.setContentsMargins(16, 9, 16, 9)

        self.top_seller_banner = QLabel("🏆 Top Best Seller: Calculating…")
        self.top_seller_banner.setStyleSheet("font-size: 13px; font-weight: 700; color: #1E293B;")
        h_lay.addWidget(self.top_seller_banner)
        h_lay.addStretch()

        view_sellers_btn = QPushButton("View Full Best Sellers Leaderboard ➔")
        view_sellers_btn.setStyleSheet(
            "QPushButton { background: #0284C7; color: white; font-weight: bold; font-size: 12px; "
            "padding: 6px 14px; border-radius: 6px; } "
            "QPushButton:hover { background: #0369A1; }"
        )
        view_sellers_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        h_lay.addWidget(view_sellers_btn)
        layout.addWidget(highlight_card)

        return widget

    def _create_products_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Row 0: Charts Grid
        charts_grid = QGridLayout()
        charts_grid.setSpacing(14)

        # Best Selling Products Bar Chart
        top_card = QFrame()
        top_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        top_lay = QVBoxLayout(top_card)
        top_lay.setContentsMargins(12, 12, 12, 12)

        self.top_axis = CategoryAxis(orientation="bottom")
        self.top_plot = pg.PlotWidget(axisItems={"bottom": self.top_axis, "left": IntegerAxis(orientation="left")})
        _setup_plot(self.top_plot, "Top Best Selling Products (Units Sold)", "Units")
        top_lay.addWidget(self.top_plot)

        # Category Sales Bar Chart
        cat_card = QFrame()
        cat_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        cat_lay = QVBoxLayout(cat_card)
        cat_lay.setContentsMargins(12, 12, 12, 12)

        self.cat_axis = CategoryAxis(orientation="bottom")
        self.cat_plot = pg.PlotWidget(axisItems={"bottom": self.cat_axis, "left": CurrencyAxis(orientation="left")})
        _setup_plot(self.cat_plot, "Revenue by Product Category (Rs)", "Revenue (Rs)")
        cat_lay.addWidget(self.cat_plot)

        charts_grid.addWidget(top_card, 0, 0, 1, 3)
        charts_grid.addWidget(cat_card, 0, 3, 1, 2)
        layout.addLayout(charts_grid)

        # Row 1: Tables Grid
        tables_grid = QGridLayout()
        tables_grid.setSpacing(14)

        # Product Leaderboard Table
        top_table_card = QFrame()
        top_table_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        top_table_lay = QVBoxLayout(top_table_card)
        top_table_lay.setContentsMargins(12, 12, 12, 12)
        top_table_lay.setSpacing(8)

        top_table_title = QLabel("🏆 Best Sellers Performance Ranking")
        top_table_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        top_table_lay.addWidget(top_table_title)

        self.top_table = QTableWidget(0, 5)
        self.top_table.setHorizontalHeaderLabels(["Rank", "Product Name", "Units Sold", "Total Revenue", "Avg Price / Unit"])
        self.top_table.verticalHeader().setVisible(False)
        self.top_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.top_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.top_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.top_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.top_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.top_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.top_table.setMinimumHeight(200)
        top_table_lay.addWidget(self.top_table)

        # Payment Methods Table / Card
        pay_card = QFrame()
        pay_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        pay_lay = QVBoxLayout(pay_card)
        pay_lay.setContentsMargins(12, 12, 12, 12)
        pay_lay.setSpacing(8)

        pay_title = QLabel("💳 Payment Methods Breakdown")
        pay_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        pay_lay.addWidget(pay_title)

        self.pay_table = QTableWidget(0, 3)
        self.pay_table.setHorizontalHeaderLabels(["Payment Mode", "Bills", "Total Collected"])
        self.pay_table.verticalHeader().setVisible(False)
        self.pay_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pay_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.pay_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.pay_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.pay_table.setMinimumHeight(200)
        pay_lay.addWidget(self.pay_table)

        tables_grid.addWidget(top_table_card, 0, 0, 1, 3)
        tables_grid.addWidget(pay_card, 0, 3, 1, 2)
        layout.addLayout(tables_grid)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setWidget(container)
        return scroll

    def _create_advisor_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("🤖 Smart Restock & Purchasing Advisor")
        title.setStyleSheet("font-weight: 700; font-size: 15px; color: #0F172A;")
        header.addWidget(title)
        header.addStretch()

        self.restock_budget_label = QLabel("Est. Restock Budget: Rs 0.00")
        self.restock_budget_label.setStyleSheet(
            "background: #FEF3C7; color: #92400E; padding: 6px 14px; border-radius: 6px; font-weight: bold; font-size: 13px;"
        )
        header.addWidget(self.restock_budget_label)
        layout.addLayout(header)

        self.restock_table = QTableWidget(0, 6)
        self.restock_table.setHorizontalHeaderLabels(
            ["Product Name", "Current Stock", "Threshold", "Unit Cost", "Suggested Order Qty", "Est. Cost"]
        )
        self.restock_table.verticalHeader().setVisible(False)
        self.restock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.restock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            self.restock_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.restock_table.setMinimumHeight(350)
        layout.addWidget(self.restock_table)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setWidget(container)
        return scroll

    def _create_slow_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("⚠️ Products with Zero Sales in this period (Potential Dead Capital)")
        title.setStyleSheet("font-weight: 600; font-size: 14px; color: #475569;")
        layout.addWidget(title)

        self.slow_table = QTableWidget(0, 3)
        self.slow_table.setHorizontalHeaderLabels(["Product Name", "In Stock (Unsold)", "Threshold"])
        self.slow_table.verticalHeader().setVisible(False)
        self.slow_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.slow_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 3):
            self.slow_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.slow_table.setMinimumHeight(350)
        layout.addWidget(self.slow_table)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setWidget(container)
        return scroll

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

        # 1. Update 5 Metric Cards
        for key, name in (("today", "today"), ("week", "week"), ("month", "month")):
            card = self.metrics[name]
            card.value.setText(f"Rs {summary[f'{key}_sales']:,.2f}")
            card.detail.setText(f"Profit: Rs {summary[f'{key}_profit']:,.2f}")

        self.stock_card.value.setText(f"Rs {data['stock_value']:,.2f}")
        self.khata_card.value.setText(f"Rs {data.get('total_khata_due', 0):,.2f}")

        # 2. Update Secondary KPI Bar
        orders = data.get("total_orders", 0)
        units = data.get("total_units_sold", 0)
        aov = data.get("avg_order_value", 0.0)

        # Calculate current period profit margin
        curr_period = self.period.currentData()
        period_rev = summary.get(f"{curr_period}_sales", 0.0)
        period_profit = summary.get(f"{curr_period}_profit", 0.0)
        margin = (period_profit / period_rev * 100) if period_rev > 0 else 0.0

        self.kpi_orders.setText(f"🧾 Total Bills: {orders}")
        self.kpi_units.setText(f"📦 Items Sold: {units}")
        self.kpi_aov.setText(f"💰 Avg Bill Value: Rs {aov:,.2f}")
        self.kpi_margin.setText(f"📈 Gross Margin: {margin:.1f}%")

        # 3. Update Tab 1 Best Seller Banner
        products = data.get("top_products", [])
        if products:
            top_p = products[0]
            self.top_seller_banner.setText(
                f"🏆 Top Best Seller: <b>{top_p['name']}</b> ({top_p['quantity']} units sold · Total: Rs {float(top_p.get('total_revenue', 0)):,.2f})"
            )
        else:
            self.top_seller_banner.setText("🏆 Top Best Seller: No sales recorded yet in this period")

        # 4. Draw All Rich Charts & Tables
        self._draw_charts(data)
        self._draw_top_products_table(products)
        self._draw_restock_table(data.get("restock_needed", []))
        self._draw_slow_products(data.get("slow_products", []))
        self._draw_payment_table(data.get("payment_breakdown", []))

        self.status.setText("Dashboard refreshed successfully.")

    def _draw_charts(self, data):
        # 1. Revenue & Profit Trend
        daily = data.get("daily_trend", [])
        self.trend_plot.clear()
        if hasattr(self, "trend_legend") and self.trend_legend:
            self.trend_legend.clear()

        if not daily or all(d.get("revenue", 0) == 0 for d in daily):
            self.trend_plot.setTitle("Revenue & Profit Trend · No sales recorded in this period yet", color="#64748B")
            self.trend_axis.set_categories({})
            self.trend_plot.setYRange(0, 1000, padding=0)
            self.trend_plot.setXRange(-0.5, 2.5, padding=0)
        else:
            self.trend_plot.setTitle("Daily Revenue & Net Profit Trend (Rs)", color="#0F172A")
            x = list(range(len(daily)))
            rev_y = [float(d.get("revenue", 0)) for d in daily]
            prof_y = [float(d.get("profit", 0)) for d in daily]

            day_map = {i: str(d.get("day", ""))[5:] for i, d in enumerate(daily)}
            self.trend_axis.set_categories(day_map)

            # Revenue curve (Blue)
            self.trend_plot.plot(
                x, rev_y, pen=pg.mkPen("#0284C7", width=3),
                symbol="o", symbolSize=9, symbolBrush="#0284C7",
                name="Total Revenue"
            )
            # Profit curve (Emerald Green)
            self.trend_plot.plot(
                x, prof_y, pen=pg.mkPen("#10B981", width=3, style=Qt.PenStyle.DashLine),
                symbol="t", symbolSize=9, symbolBrush="#10B981",
                name="Net Profit"
            )

            # Annotate values above points
            for i, d in enumerate(daily):
                r = rev_y[i]
                lbl = pg.TextItem(
                    html=f"<div style='text-align:center; font-family: Segoe UI, sans-serif;'>"
                         f"<b style='color:#0284C7; font-size:11px;'>Rs {r:,.0f}</b>"
                         f"</div>",
                    anchor=(0.5, 1.2)
                )
                lbl.setPos(i, r)
                self.trend_plot.addItem(lbl)

            max_val = max(max(rev_y, default=1000), 1000)
            self.trend_plot.setYRange(0, max_val * 1.35, padding=0)
            self.trend_plot.setXRange(-0.6, max(len(daily) - 0.4, 1.5), padding=0)

        # 2. Peak Business Hours Chart
        hourly = data.get("hourly_sales", {})
        x_hours = list(range(24))
        y_counts = [int(hourly.get(h, 0)) for h in x_hours]

        max_hour_count = max(y_counts) if y_counts else 0
        if max_hour_count > 0:
            peak_hr = x_hours[y_counts.index(max_hour_count)]
            ampm = "AM" if peak_hr < 12 else "PM"
            hr12 = peak_hr if (0 < peak_hr <= 12) else (12 if peak_hr == 0 else peak_hr - 12)
            self.kpi_peak.setText(f"🔥 Peak Hour: {hr12}:00 {ampm} ({max_hour_count} bills)")
        else:
            self.kpi_peak.setText("🔥 Peak Hour: None yet")

        self.hour_plot.clear()

        # Volume Bar Graph
        bars = pg.BarGraphItem(x=x_hours, height=y_counts, width=0.7, brush=QColor("#38BDF8"))
        self.hour_plot.addItem(bars)

        # Overlay trend line
        self.hour_plot.plot(
            x_hours, y_counts, pen=pg.mkPen("#0369A1", width=2.5),
            symbol="o", symbolSize=5, symbolBrush="#0369A1"
        )
        self.hour_plot.setXRange(-0.5, 23.5, padding=0)
        self.hour_plot.setYRange(0, max(max_hour_count + 1, 5), padding=0)

        # 3. Top Best Selling Products
        products = data.get("top_products", [])
        self.top_plot.clear()
        if not products:
            self.top_plot.setTitle("Top Best Sellers · No sales yet in this period", color="#64748B")
            self.top_axis.set_categories({})
            self.top_plot.setYRange(0, 5, padding=0)
        else:
            self.top_plot.setTitle("Top Best Selling Products (Units Sold)", color="#0F172A")
            cat_map = {i: (p["name"][:12] + "…" if len(p["name"]) > 12 else p["name"]) for i, p in enumerate(products)}
            self.top_axis.set_categories(cat_map)
            quantities = [p["quantity"] for p in products]
            top_bars = pg.BarGraphItem(
                x=list(range(len(products))),
                height=quantities,
                width=0.55,
                brush=QColor("#6366F1")
            )
            self.top_plot.addItem(top_bars)

            max_qty = max(quantities, default=5)
            for i, p in enumerate(products):
                qty = p["quantity"]
                p_name = p["name"]
                short_name = p_name[:11] + ("…" if len(p_name) > 11 else "")
                label = pg.TextItem(
                    html=f"<div style='text-align:center; font-family: Segoe UI, sans-serif;'>"
                         f"<b style='color:#4338CA; font-size:11px;'>{qty} sold</b><br/>"
                         f"<span style='color:#334155; font-size:10px;'>{short_name}</span>"
                         f"</div>",
                    anchor=(0.5, 1.1)
                )
                label.setPos(i, qty)
                self.top_plot.addItem(label)

            self.top_plot.setXRange(-0.5, max(len(products) - 0.5, 2.5), padding=0)
            self.top_plot.setYRange(0, max_qty * 1.35, padding=0)

        # 4. Category Breakdown
        categories = data.get("category_sales", [])
        self.cat_plot.clear()
        if not categories:
            self.cat_plot.setTitle("Revenue by Category · No data yet", color="#64748B")
            self.cat_axis.set_categories({})
            self.cat_plot.setYRange(0, 1000, padding=0)
        else:
            self.cat_plot.setTitle("Revenue by Product Category (Rs)", color="#0F172A")
            cat_map = {i: (c["category"][:12] + "…" if len(c["category"]) > 12 else c["category"]) for i, c in enumerate(categories)}
            self.cat_axis.set_categories(cat_map)
            revenues = [c["revenue"] for c in categories]
            cat_bars = pg.BarGraphItem(
                x=list(range(len(categories))),
                height=revenues,
                width=0.55,
                brush=QColor("#10B981")
            )
            self.cat_plot.addItem(cat_bars)

            max_rev = max(revenues, default=1000)
            for i, c in enumerate(categories):
                rev = c["revenue"]
                label = pg.TextItem(
                    html=f"<div style='text-align:center; font-family: Segoe UI, sans-serif;'>"
                         f"<b style='color:#059669; font-size:11px;'>Rs {rev:,.0f}</b>"
                         f"</div>",
                    anchor=(0.5, 1.1)
                )
                label.setPos(i, rev)
                self.cat_plot.addItem(label)

            self.cat_plot.setXRange(-0.5, max(len(categories) - 0.5, 2.5), padding=0)
            self.cat_plot.setYRange(0, max_rev * 1.3, padding=0)

    def _draw_top_products_table(self, products: list[dict]):
        medals = {0: "🥇 #1", 1: "🥈 #2", 2: "🥉 #3"}
        self.top_table.setRowCount(len(products))
        for row, p in enumerate(products):
            rank_str = medals.get(row, f"#{row + 1}")
            qty = int(p.get("quantity") or 0)
            rev = float(p.get("total_revenue") or 0)
            avg_price = (rev / qty) if qty > 0 else 0.0

            rank_item = QTableWidgetItem(rank_str)
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            rank_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

            name_item = QTableWidgetItem(p["name"])
            name_item.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            name_item.setForeground(QColor("#0F172A"))

            qty_item = QTableWidgetItem(f"{qty} sold")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            qty_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            qty_item.setForeground(QColor("#4338CA"))

            rev_item = QTableWidgetItem(f"Rs {rev:,.2f}")
            rev_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rev_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            rev_item.setForeground(QColor("#047857"))

            avg_item = QTableWidgetItem(f"Rs {avg_price:,.2f}")
            avg_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.top_table.setItem(row, 0, rank_item)
            self.top_table.setItem(row, 1, name_item)
            self.top_table.setItem(row, 2, qty_item)
            self.top_table.setItem(row, 3, rev_item)
            self.top_table.setItem(row, 4, avg_item)

    def _draw_payment_table(self, payments):
        self.pay_table.setRowCount(len(payments))
        total_collected = sum(p.get("total_amount", 0) for p in payments)
        for row, item in enumerate(payments):
            amt = float(item.get("total_amount", 0))
            pct = (amt / total_collected * 100) if total_collected > 0 else 0

            mode_item = QTableWidgetItem(f"💳 {item.get('mode', 'Cash')}")
            mode_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

            count_item = QTableWidgetItem(f"{item.get('count', 0)} sales")
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            amt_item = QTableWidgetItem(f"Rs {amt:,.2f} ({pct:.1f}%)")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            amt_item.setForeground(QColor("#0F172A"))
            amt_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

            self.pay_table.setItem(row, 0, mode_item)
            self.pay_table.setItem(row, 1, count_item)
            self.pay_table.setItem(row, 2, amt_item)

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
                f"Rs {cost:,.2f}",
            )
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setForeground(QColor("#991B1B"))
                item.setBackground(QColor("#FEE2E2"))
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
