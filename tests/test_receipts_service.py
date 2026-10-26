"""Tests for Receipt Printing, PDF generation, and WhatsApp Image generation."""

import os
import unittest
from unittest.mock import patch

from services import receipts, receipt_image


class TestReceiptsService(unittest.TestCase):
    """Verify receipt formatting, ESC/POS strings, PDF generation, and Pillow image rendering."""

    def setUp(self):
        self.sample_receipt = {
            "sale_id": 1042,
            "timestamp": "2026-10-26 14:30:00",
            "cashier": "Admin",
            "customer_name": "Hamza Tariq",
            "items": [
                {"name": "Surf Excel 500g", "qty": 2, "unit_price": 260.0, "discount": 0.0},
                {"name": "Lipton Tea 200g", "qty": 1, "unit_price": 450.0, "discount": 20.0},
            ],
            "subtotal": 970.0,
            "bill_discount": 50.0,
            "exchange_credit": 0.0,
            "total": 900.0,
            "payment_mode": "Cash",
            "tendered": 1000.0,
            "change": 100.0,
        }

    def test_thermal_text_formatting(self):
        """Test formatting plain text for 58mm/80mm thermal receipt printer."""
        text = receipts.receipt_text(self.sample_receipt)
        self.assertIsInstance(text, str)
        self.assertIn("1042", text)
        self.assertIn("Surf Excel", text)
        self.assertIn("Lipton Tea", text)
        self.assertIn("900.00", text)
        self.assertIn("Hamza Tariq", text)

    def test_whatsapp_text_and_url_generation(self):
        """Test formatting WhatsApp markdown message and click-to-chat URL."""
        msg = receipts.generate_whatsapp_text(self.sample_receipt)
        self.assertIn("Bill #1042", msg)
        self.assertIn("Surf Excel", msg)
        self.assertIn("Total Amount:", msg)

        # WhatsApp URL for Pakistani number (+923001234567)
        url = receipts.generate_whatsapp_url(self.sample_receipt, phone_number="03001234567")
        self.assertIn("https://wa.me/923001234567", url)
        self.assertIn("text=", url)

    def test_pdf_receipt_generation_fallback(self):
        """Test generating offline fallback PDF receipt using fpdf2 when no printer is configured."""
        with patch("services.receipts.load_settings", return_value={"printer_name": ""}):
            res = receipts.print_or_save_receipt(self.sample_receipt)
            self.assertIsInstance(res, dict)
            self.assertEqual(res["kind"], "pdf")
            pdf_path = res["path"]
            self.assertIsNotNone(pdf_path)
            self.assertTrue(os.path.exists(pdf_path), f"PDF file does not exist at {pdf_path}")
            self.assertTrue(pdf_path.endswith(".pdf"))
            self.assertGreater(os.path.getsize(pdf_path), 1000, "PDF file is too small or empty")

    def test_branded_receipt_png_image_generation(self):
        """Test rendering high-resolution branded receipt PNG using Pillow."""
        img_path = receipt_image.generate_receipt_image(self.sample_receipt)
        self.assertIsNotNone(img_path)
        self.assertTrue(os.path.exists(img_path), f"Receipt image not found at {img_path}")
        self.assertTrue(img_path.endswith(".png"))
        self.assertGreater(os.path.getsize(img_path), 2000, "PNG image is too small or corrupt")


if __name__ == "__main__":
    unittest.main()
