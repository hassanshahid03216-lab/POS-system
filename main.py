"""ShopFlow POS application entry point."""

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app_settings import load_settings
from db import db
from screens.login import ShopFlowWindow
from services.theme import DEFAULT_THEME, stylesheet_for


def main():
    db.init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("ShopFlow POS")

    theme_name = load_settings().get("theme", DEFAULT_THEME)
    app.setStyleSheet(stylesheet_for(theme_name))
    app.setFont(QFont("Segoe UI", 10))

    window = ShopFlowWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
