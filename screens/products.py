"""Product & Inventory management screen for ShopFlow POS with Bulk CSV Import/Export, Categories, and Low-stock filters."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from db import db
from services.sound import play_error_beep, play_success_ding


class _WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(object)


class _Worker(QRunnable):
    def __init__(self, operation: Callable[[], Any]):
        super().__init__()
        self.operation = operation
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.operation())
        except Exception as error:
            self.signals.failed.emit(error)


class _ProductForm(QDialog):
    def __init__(self, product: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Product" if product else "Add New Product")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        heading = QLabel("Update product details" if product else "Enter the product details")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(heading)

        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Lays Masala 50g")
        self.barcode = QLineEdit()
        self.barcode.setPlaceholderText("Scan or type barcode (e.g. 89640001)")
        self.cost = self._money_input()
        self.sale = self._money_input()
        self.stock = QSpinBox()
        self.stock.setRange(0, 2_000_000_000)
        self.category = QLineEdit()
        self.category.setPlaceholderText("e.g. Snacks, Dairy, Beverages")
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 2_000_000_000)
        self.threshold.setToolTip("Trigger low stock alert when quantity reaches this number")

        for label, widget in (
            ("Product Name *", self.name), ("Barcode (Scan)", self.barcode),
            ("Cost Price (Purchase)", self.cost), ("Sale Price *", self.sale),
            ("Initial Stock Qty", self.stock), ("Category", self.category),
            ("Low Stock Warning At", self.threshold)
        ):
            form.addRow(label, widget)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton("Save Product")
        self.save_button.setDefault(True)
        self.save_button.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 7px 16px;")
        self.save_button.clicked.connect(self._validate_and_accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        if product:
            self.name.setText(product.get("name", ""))
            self.barcode.setText(product.get("barcode") or "")
            self.cost.setValue(float(product.get("cost_price") or 0))
            self.sale.setValue(float(product.get("sale_price") or 0))
            self.stock.setValue(int(product.get("stock_qty") or 0))
            self.category.setText(product.get("category") or "")
            self.threshold.setValue(int(product.get("low_stock_threshold") or 5))
        else:
            self.threshold.setValue(5)

    @staticmethod
    def _money_input() -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(0, 99_999_999)
        field.setDecimals(2)
        field.setPrefix("Rs ")
        field.setSingleStep(10)
        return field

    def _validate_and_accept(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Required Field", "Product name cannot be empty.")
            self.name.setFocus()
            return
        if self.sale.value() <= 0:
            QMessageBox.warning(self, "Required Field", "Sale price must be greater than zero.")
            self.sale.setFocus()
            return
        if self.cost.value() > self.sale.value():
            answer = QMessageBox.question(
                self, "Price Check", "Cost price is higher than sale price (Loss). Save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def values(self) -> tuple:
        return (
            self.name.text().strip(), self.barcode.text().strip() or None,
            self.cost.value(), self.sale.value(), self.stock.value(),
            self.category.text().strip() or None, self.threshold.value(),
        )


class ProductManagementScreen(QWidget):
    """Searchable product list with bulk CSV import/export and stock alerts."""

    HEADERS = ("Product Name", "Barcode", "Cost Price", "Sale Price", "In Stock", "Category", "Status")
    _operation_done = Signal(object, object)
    _operation_failed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._products: list[dict] = []
        self._categories: list[str] = []
        self._busy = False
        self.low_stock_filter_active = False

        self._operation_done.connect(self._finish)
        self._operation_failed.connect(self._show_error)

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Header Bar
        top_row = QHBoxLayout()
        title = QLabel("📦 Inventory & Products")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px;")
        top_row.addWidget(title)
        top_row.addStretch()

        # Bulk Actions
        sample_btn = QPushButton("📋 Sample CSV Template")
        sample_btn.clicked.connect(self._download_sample_template)
        top_row.addWidget(sample_btn)

        import_btn = QPushButton("📥 Import CSV")
        import_btn.setStyleSheet("background: #0284c7; color: white; font-weight: bold;")
        import_btn.clicked.connect(self._import_csv)
        top_row.addWidget(import_btn)

        export_btn = QPushButton("📤 Export CSV")
        export_btn.clicked.connect(self._export_csv)
        top_row.addWidget(export_btn)

        self.add_button = QPushButton("＋ Add Product")
        self.add_button.setStyleSheet("background: #16a34a; color: white; font-weight: bold; padding: 7px 14px;")
        self.add_button.clicked.connect(self._add_product)
        top_row.addWidget(self.add_button)
        root.addLayout(top_row)

        # Toolbar Card: Search + Category filter + Low Stock button
        toolbar_card = QFrame()
        toolbar_card.setProperty("visualRole", "card")
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(12, 10, 12, 10)
        toolbar.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Search products by name, barcode, or category...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._render_rows)
        toolbar.addWidget(self.search, 2)

        self.cat_filter = QComboBox()
        self.cat_filter.addItem("All Categories", "")
        self.cat_filter.currentIndexChanged.connect(self._render_rows)
        toolbar.addWidget(self.cat_filter, 1)

        self.low_stock_btn = QPushButton("⚠️ Low Stock Only (OFF)")
        self.low_stock_btn.setCheckable(True)
        self.low_stock_btn.clicked.connect(self._toggle_low_stock_filter)
        toolbar.addWidget(self.low_stock_btn)
        root.addWidget(toolbar_card)

        # Products Table
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(self.HEADERS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._edit_product)
        self.table.currentCellChanged.connect(lambda *_: self._set_actions_enabled())
        root.addWidget(self.table, 1)

        # Footer
        footer = QHBoxLayout()
        self.status = QLabel("Loading products…")
        self.status.setStyleSheet("color: #64748b; font-weight: 500;")
        footer.addWidget(self.status, 1)

        self.edit_button = QPushButton("Edit Selected")
        self.edit_button.clicked.connect(self._edit_product)
        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.clicked.connect(self._delete_product)
        footer.addWidget(self.edit_button)
        footer.addWidget(self.delete_button)
        root.addLayout(footer)

        self.setStyleSheet("""
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget { padding: 7px; font-size: 13px; }
            QPushButton { padding: 7px 13px; font-size: 13px; }
            QTableWidget { gridline-color: #e2e8f0; }
        """)

    def _start(self, operation: Callable[[], Any], on_success: Callable[[Any], None]) -> None:
        if self._busy:
            return
        self._busy = True
        self.add_button.setEnabled(False)
        self.edit_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        worker = _Worker(operation)
        worker.signals.finished.connect(lambda result: self._operation_done.emit(on_success, result))
        worker.signals.failed.connect(self._operation_failed.emit)
        self._worker = worker
        self._pool.start(worker)

    def _finish(self, callback: Callable[[Any], None], result: Any) -> None:
        self._busy = False
        self._set_actions_enabled()
        callback(result)

    def _show_error(self, error: Exception) -> None:
        self._busy = False
        self._set_actions_enabled()
        play_error_beep()
        msg = "That barcode is already registered for another item." if "UNIQUE constraint failed: products.barcode" in str(error) else f"Error: {error}"
        QMessageBox.warning(self, "Inventory Error", msg)

    def _set_actions_enabled(self) -> None:
        self.add_button.setEnabled(not self._busy)
        has_selection = self.table.currentRow() >= 0
        self.edit_button.setEnabled(not self._busy and has_selection)
        self.delete_button.setEnabled(not self._busy and has_selection)

    def refresh(self) -> None:
        self.status.setText("Loading products…")
        self._start(lambda: (db.list_products(), db.list_categories()), self._loaded)

    def _loaded(self, data: tuple) -> None:
        products, categories = data
        self._products = products
        self._categories = categories

        # Update categories combo
        current_cat = self.cat_filter.currentData()
        self.cat_filter.blockSignals(True)
        self.cat_filter.clear()
        self.cat_filter.addItem("All Categories", "")
        for cat in categories:
            if cat:
                self.cat_filter.addItem(cat, cat)
        if current_cat:
            idx = self.cat_filter.findData(current_cat)
            if idx >= 0:
                self.cat_filter.setCurrentIndex(idx)
        self.cat_filter.blockSignals(False)

        self._render_rows()

    def _toggle_low_stock_filter(self):
        self.low_stock_filter_active = self.low_stock_btn.isChecked()
        if self.low_stock_filter_active:
            self.low_stock_btn.setText("⚠️ Low Stock Only (ON)")
            self.low_stock_btn.setStyleSheet("background: #fee2e2; color: #991b1b; font-weight: bold; border: 1px solid #fca5a5;")
        else:
            self.low_stock_btn.setText("⚠️ Low Stock Only (OFF)")
            self.low_stock_btn.setStyleSheet("")
        self._render_rows()

    def _render_rows(self, *_args) -> None:
        query = self.search.text().strip().casefold() if hasattr(self, "search") else ""
        selected_cat = self.cat_filter.currentData() if hasattr(self, "cat_filter") else ""

        filtered = []
        low_count = 0
        for p in self._products:
            stock = int(p.get("stock_qty") or 0)
            thresh = int(p.get("low_stock_threshold") or 5)
            is_low = stock <= thresh
            if is_low:
                low_count += 1

            if self.low_stock_filter_active and not is_low:
                continue

            if selected_cat and (p.get("category") or "") != selected_cat:
                continue

            if query:
                combined = f"{p.get('name', '')} {p.get('barcode', '')} {p.get('category', '')}".casefold()
                if query not in combined:
                    continue

            filtered.append((p, is_low))

        self.table.setRowCount(len(filtered))
        for row, (product, low) in enumerate(filtered):
            status_str = "⚠️ Low Stock" if low else "✅ In Stock"
            values = (
                product.get("name", ""),
                product.get("barcode") or "—",
                f"Rs {float(product.get('cost_price') or 0):,.2f}",
                f"Rs {float(product.get('sale_price') or 0):,.2f}",
                str(product.get("stock_qty", 0)),
                product.get("category") or "—",
                status_str,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, product["id"])
                if column in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if low:
                    item.setForeground(QColor("#991b1b"))
                    item.setBackground(QColor("#fee2e2"))
                self.table.setItem(row, column, item)

        status_text = f"{len(filtered)} product(s) displayed"
        if low_count > 0:
            status_text += f"  ·  ⚠️ {low_count} items with Low Stock"
        self.status.setText(status_text)
        self._set_actions_enabled()

    def _selected_product(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return None
        product_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return next((p for p in self._products if p["id"] == product_id), None)

    def _add_product(self) -> None:
        if self._busy:
            return
        form = _ProductForm(parent=self)
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        values = form.values()
        self._start(lambda: db.create_product(*values), lambda _: (play_success_ding(), self.refresh()))

    def _edit_product(self, *_args) -> None:
        product = self._selected_product()
        if not product or self._busy:
            return
        form = _ProductForm(product, self)
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        values = form.values()
        self._start(lambda: db.update_product(product["id"], *values), lambda _: (play_success_ding(), self.refresh()))

    def _delete_product(self) -> None:
        product = self._selected_product()
        if not product or self._busy:
            return
        answer = QMessageBox.question(
            self, "Delete Product", f"Are you sure you want to delete ‘{product['name']}’?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start(lambda: db.delete_product(product["id"]), lambda _: self.refresh())

    def _import_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Products from CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        def _op():
            return db.import_products_csv(file_path)

        def _done(res):
            play_success_ding()
            skipped_msg = f"\n• Skipped (empty name): {res.get('skipped', 0)}" if res.get('skipped', 0) > 0 else ""
            QMessageBox.information(
                self, "Import Completed",
                f"✅ Bulk Import Finished!\n• New items added: {res['imported']}\n• Existing items updated: {res['updated']}{skipped_msg}\n• Total processed: {res['total']}"
            )
            self.refresh()

        self._start(_op, _done)

    def _export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Inventory to CSV", "inventory_export.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        def _op():
            return db.export_products_csv(file_path)

        def _done(count):
            play_success_ding()
            QMessageBox.information(self, "Export Completed", f"Successfully exported {count} products to:\n{file_path}")

        self._start(_op, _done)

    def _download_sample_template(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Sample CSV Template", "sample_products_template.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return
        try:
            db.generate_sample_csv(file_path)
            play_success_ding()
            QMessageBox.information(
                self, "Template Saved",
                f"Sample CSV template saved to:\n{file_path}\n\nYou can fill it in Excel and use 'Import CSV' to upload your products in bulk."
            )
        except Exception as error:
            play_error_beep()
            QMessageBox.warning(self, "Save Error", str(error))
