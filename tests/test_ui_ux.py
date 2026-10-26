"""Automated UI & UX Testing Suite for ShopFlow POS (PySide6 Headless).

Runs in offscreen mode to test:
- Staff PIN Login keypad interactions, backspace, clear, and rate-limiting lockout UX
- Billing screen cart management, barcode entry, quantity updates, and discount calculations
- Theme switching engine across all themes without CSS rendering glitches
"""

import os
import sys
import unittest
from unittest.mock import patch

# Force offscreen headless mode for GUI testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMessageBox

# Ensure singleton QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

from screens.login import LoginScreen
from screens.billing import BillingScreen
from services import theme


class TestLoginScreenUI(unittest.TestCase):
    """UI/UX tests for staff authentication keypad and lockout safety."""

    def setUp(self):
        self.screen = LoginScreen()

    def tearDown(self):
        self.screen.pool.waitForDone(100)
        self.screen.deleteLater()

    def test_keypad_number_entry_and_clear(self):
        """Test clicking on-screen numeric keypad buttons."""
        btn_1 = next(b for b in self.screen._buttons if b.text() == "1")
        btn_2 = next(b for b in self.screen._buttons if b.text() == "2")
        btn_3 = next(b for b in self.screen._buttons if b.text() == "3")
        btn_4 = next(b for b in self.screen._buttons if b.text() == "4")
        btn_clear = next(b for b in self.screen._buttons if b.text() == "Clear")
        btn_back = next(b for b in self.screen._buttons if b.text() == "⌫")

        # Click 1, 2, 3, 4
        btn_1.click()
        btn_2.click()
        btn_3.click()
        btn_4.click()
        self.assertEqual(self.screen.pin.text(), "1234")

        # Test backspace
        btn_back.click()
        self.assertEqual(self.screen.pin.text(), "123")

        # Test clear
        btn_clear.click()
        self.assertEqual(self.screen.pin.text(), "")

    def test_lockout_rate_limiting_ux(self):
        """Test that repeated invalid PIN attempts trigger visual lockout UX."""
        with patch("services.sound.play_error_beep"):
            for _ in range(5):
                self.screen._auth_result(None)

        # Should be locked out
        self.assertTrue(self.screen._lockout_remaining > 0)
        self.assertFalse(self.screen.pin.isEnabled())
        self.assertIn("Locked", self.screen.status.text())

        # Simulate lockout tick countdown
        prev = self.screen._lockout_remaining
        self.screen._lockout_tick()
        self.assertEqual(self.screen._lockout_remaining, prev - 1)


class TestBillingScreenUI(unittest.TestCase):
    """UI/UX tests for point-of-sale checkout counter screen."""

    def setUp(self):
        self.screen = BillingScreen()
        # Seed mock products for UI testing
        self.screen.products = [
            {"id": 101, "name": "Tapal Danedar 400g", "barcode": "896101", "sale_price": 550.0, "stock_qty": 20},
            {"id": 102, "name": "Olpers Milk 1L", "barcode": "896102", "sale_price": 260.0, "stock_qty": 50},
        ]

    def tearDown(self):
        self.screen.pool.waitForDone(100)
        self.screen.deleteLater()

    def test_search_input_properties(self):
        """Verify search input field is properly styled and placeholder is clear."""
        self.assertEqual(self.screen.search.objectName(), "barcode_input")
        self.assertTrue(self.screen.search.isClearButtonEnabled())
        self.assertIn("Scan barcode", self.screen.search.placeholderText())

    def test_add_product_to_cart_and_total_calculation(self):
        """Test adding item to cart updates table rows and bottom totals."""
        product = self.screen.products[0]  # Tapal Danedar (550.0)

        with patch("services.sound.play_scan_beep"):
            # Add to cart
            self.screen._add_product(product)
            self.assertEqual(len(self.screen.cart), 1)
            self.assertEqual(self.screen.cart[0]["id"], 101)
            self.assertEqual(self.screen.cart[0]["qty"], 1)

            # Add second unit of same product -> should increment qty to 2
            self.screen._add_product(product)
            self.assertEqual(len(self.screen.cart), 1)
            self.assertEqual(self.screen.cart[0]["qty"], 2)

        # Verify summary total (2 * 550 = 1100)
        self.assertIn("1,100", self.screen.total_label.text())

    def test_bill_discount_updates_final_total(self):
        """Test entering flat discount correctly recalculates total payable."""
        p1 = self.screen.products[0]  # 550.0
        p2 = self.screen.products[1]  # 260.0

        with patch("services.sound.play_scan_beep"):
            self.screen._add_product(p1)
            self.screen._add_product(p2)

        # Subtotal = 550 + 260 = 810. Set discount 60 -> net 750
        self.screen.bill_discount.setValue(60.0)
        self.screen._update_totals()
        self.assertIn("750", self.screen.total_label.text())

    def test_clear_cart_resets_state(self):
        """Test clearing cart resets table and zero out balances."""
        with patch("services.sound.play_scan_beep"):
            self.screen._add_product(self.screen.products[0])
        self.assertEqual(len(self.screen.cart), 1)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.screen._new_bill()

        self.assertEqual(len(self.screen.cart), 0)
        self.assertIn("0.00", self.screen.total_label.text())


class TestThemeEngine(unittest.TestCase):
    """UI Design Aesthetics test: Verify all color palettes and stylesheets."""

    def test_all_theme_stylesheets_generate_valid_css(self):
        """Ensure all themes generate comprehensive, non-empty QSS stylesheets."""
        themes = ["Midnight Navy", "Emerald Fresh", "Slate Modern", "Classic Light"]
        for theme_name in themes:
            css = theme.stylesheet_for(theme_name)
            self.assertIsInstance(css, str)
            self.assertGreater(len(css), 500, f"Theme {theme_name} stylesheet is empty or too short!")
            self.assertIn("QMainWindow", css)
            self.assertIn("QPushButton", css)
            self.assertIn("QTableWidget", css)
            self.assertIn("QLineEdit", css)

    def test_unknown_theme_fallback(self):
        """Verify unknown theme name safely falls back to default stylesheet without crashing."""
        fallback_css = theme.stylesheet_for("NonExistentTheme")
        self.assertIsInstance(fallback_css, str)
        self.assertGreater(len(fallback_css), 500)


if __name__ == "__main__":
    unittest.main()
