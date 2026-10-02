"""Shared color tokens, application stylesheet, and contrast checks for ShopFlow POS."""

from __future__ import annotations

from typing import Mapping

DEFAULT_THEME = "light"
MINIMUM_CONTRAST_RATIO = 4.5

# The semantic foreground values make the text/background relationship explicit.
THEME_TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "background": "#F1F5F9",
        "surface": "#FFFFFF",
        "text_primary": "#0F172A",
        "text_secondary": "#475569",
        "border": "#CBD5E1",
        "primary": "#1D4ED8",
        "primary_text": "#FFFFFF",
        "primary_hover": "#1E40AF",
        "success": "#15803D",
        "success_text": "#FFFFFF",
        "success_hover": "#166534",
        "warning": "#B45309",
        "warning_text": "#FFFFFF",
        "warning_hover": "#92400E",
        "danger": "#B91C1C",
        "danger_text": "#FFFFFF",
        "danger_hover": "#991B1B",
        "focus": "#1D4ED8",
        "selection": "#E0EDFF",
        "selection_text": "#0F172A",
        "alternate": "#F8FAFC",
        "disabled_background": "#E2E8F0",
        "disabled_text": "#475569",
        "button_hover": "#F1F5F9",
        "button_pressed": "#E2E8F0",
    },
    "dark": {
        "background": "#0F172A",
        "surface": "#1E293B",
        "text_primary": "#F1F5F9",
        "text_secondary": "#CBD5E1",
        "border": "#475569",
        "primary": "#60A5FA",
        "primary_text": "#0F172A",
        "primary_hover": "#93C5FD",
        "success": "#22C55E",
        "success_text": "#052E16",
        "success_hover": "#4ADE80",
        "warning": "#FBBF24",
        "warning_text": "#422006",
        "warning_hover": "#FCD34D",
        "danger": "#F87171",
        "danger_text": "#450A0A",
        "danger_hover": "#FCA5A5",
        "focus": "#93C5FD",
        "selection": "#334155",
        "selection_text": "#F1F5F9",
        "alternate": "#243247",
        "disabled_background": "#334155",
        "disabled_text": "#CBD5E1",
        "button_hover": "#334155",
        "button_pressed": "#0F172A",
    },
}


def get_theme_tokens(theme: str = DEFAULT_THEME) -> dict[str, str]:
    """Return a copy of the requested theme tokens (unknown names use light)."""
    return dict(THEME_TOKENS.get(theme.lower(), THEME_TOKENS[DEFAULT_THEME]))


def _qss(theme: str) -> str:
    colors = get_theme_tokens(theme)
    return """
/* Application-wide base */
QWidget {
    background-color: %(background)s;
    color: %(text_primary)s;
    font-family: "Segoe UI", sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog { background-color: %(background)s; }
QWidget#navigationBar {
    background-color: %(surface)s;
    border-bottom: 1px solid %(border)s;
}
QLabel { background: transparent; color: %(text_primary)s; }
QLabel[visualRole="secondary"] { color: %(text_secondary)s; }
QLabel[visualRole="primary"] { color: %(primary)s; }
QLabel[visualRole="success"] { color: %(success)s; }
QLabel[visualRole="warning"] { color: %(warning)s; }
QLabel[visualRole="danger"] { color: %(danger)s; }
QLabel[visualRole="total"] {
    color: %(text_primary)s;
    font-size: 32px;
    font-weight: 800;
}
QFrame[visualRole="card"] {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
}
QFrame[visualRole="inset"] {
    background-color: %(alternate)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
}

/* Neutral controls; semantic action variants are opt-in via a Qt property. */
QPushButton {
    min-height: 40px;
    padding: 8px 16px;
    background-color: %(surface)s;
    color: %(text_primary)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    font-weight: 600;
}
QPushButton:hover { background-color: %(button_hover)s; }
QPushButton:pressed { background-color: %(button_pressed)s; }
QPushButton:focus { border: 2px solid %(focus)s; }
QPushButton:disabled {
    background-color: %(disabled_background)s;
    color: %(disabled_text)s;
    border-color: %(border)s;
}
QPushButton[variant="primary"] {
    background-color: %(primary)s;
    color: %(primary_text)s;
    border-color: %(primary)s;
}
QPushButton[variant="primary"]:hover { background-color: %(primary_hover)s; }
QPushButton[variant="success"] {
    background-color: %(success)s;
    color: %(success_text)s;
    border-color: %(success)s;
}
QPushButton[variant="success"]:hover { background-color: %(success_hover)s; }
QPushButton[variant="warning"] {
    background-color: %(warning)s;
    color: %(warning_text)s;
    border-color: %(warning)s;
}
QPushButton[variant="warning"]:hover { background-color: %(warning_hover)s; }
QPushButton[variant="danger"] {
    background-color: %(danger)s;
    color: %(danger_text)s;
    border-color: %(danger)s;
}
QPushButton[variant="danger"]:hover { background-color: %(danger_hover)s; }
QPushButton[variant]:focus { border: 2px solid %(focus)s; }
QPushButton[variant]:disabled {
    background-color: %(disabled_background)s;
    color: %(disabled_text)s;
    border-color: %(border)s;
}
QPushButton[variant]:pressed { border-width: 3px; }
QPushButton[navActive="true"] {
    background-color: %(selection)s;
    color: %(primary)s;
    border: 1px solid %(primary)s;
    font-weight: 700;
}
QPushButton[compact="true"], QTableWidget QPushButton {
    min-height: 28px;
    max-height: 32px;
    padding: 3px 10px;
    font-size: 12px;
    border-radius: 5px;
    font-weight: 600;
}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {
    min-height: 34px;
    padding: 6px 10px;
    background-color: %(surface)s;
    color: %(text_primary)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    selection-background-color: %(selection)s;
    selection-color: %(selection_text)s;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {
    border: 2px solid %(focus)s;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QDateEdit:disabled, QComboBox:disabled {
    background-color: %(disabled_background)s;
    color: %(disabled_text)s;
}

QGroupBox {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
    margin-top: 20px;
    padding: 20px 16px 16px 16px;
    font-weight: 700;
    font-size: 13px;
    color: %(text_primary)s;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 3px 10px;
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    color: %(text_primary)s;
    font-weight: 700;
}

QTableWidget, QTableView, QListWidget {
    background-color: %(surface)s;
    color: %(text_primary)s;
    gridline-color: %(border)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    alternate-background-color: %(alternate)s;
    selection-background-color: %(selection)s;
    selection-color: %(selection_text)s;
}
QTableWidget::item, QTableView::item { min-height: 34px; padding: 4px; }
QTableWidget::item:selected, QTableView::item:selected,
QListWidget::item:selected {
    background-color: %(selection)s;
    color: %(selection_text)s;
}
QHeaderView::section {
    background-color: %(alternate)s;
    color: %(text_primary)s;
    border: none;
    border-bottom: 2px solid %(border)s;
    padding: 8px 10px;
    font-weight: 700;
}
QTabWidget::pane {
    border: 1px solid %(border)s;
    border-radius: 8px;
    background: %(surface)s;
}
QTabBar::tab {
    background-color: %(background)s;
    color: %(text_secondary)s;
    min-height: 38px;
    padding: 6px 16px;
    border: 1px solid %(border)s;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: %(surface)s;
    color: %(primary)s;
    font-weight: 700;
    border-color: %(border)s;
}
QTabBar::tab:focus { border: 2px solid %(focus)s; }
QToolTip {
    background-color: %(surface)s;
    color: %(text_primary)s;
    border: 1px solid %(border)s;
    padding: 6px;
}
""" % colors


def stylesheet_for(theme: str = DEFAULT_THEME) -> str:
    """Build the application-level Qt stylesheet for light or dark mode."""
    normalized = theme.lower()
    if normalized not in THEME_TOKENS:
        normalized = DEFAULT_THEME
    return _qss(normalized)


THEME_STYLESHEET = stylesheet_for(DEFAULT_THEME)


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two #RRGGBB colors."""
    def luminance(color: str) -> float:
        value = color.removeprefix("#")
        if len(value) != 6:
            raise ValueError(f"Expected #RRGGBB color, got {color!r}")
        channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def failing_contrast_pairs(
    themes: Mapping[str, Mapping[str, str]] = THEME_TOKENS,
    minimum: float = MINIMUM_CONTRAST_RATIO,
) -> list[tuple[str, str, str, float]]:
    """List semantic foreground/background pairs below the WCAG AA threshold."""
    pairs = (
        ("text_primary", "background"),
        ("text_primary", "surface"),
        ("text_secondary", "background"),
        ("text_secondary", "surface"),
        ("primary_text", "primary"),
        ("primary_text", "primary_hover"),
        ("success_text", "success"),
        ("success_text", "success_hover"),
        ("warning_text", "warning"),
        ("warning_text", "warning_hover"),
        ("danger_text", "danger"),
        ("danger_text", "danger_hover"),
        ("selection_text", "selection"),
        ("disabled_text", "disabled_background"),
    )
    failures = []
    for theme_name, colors in themes.items():
        for foreground_key, background_key in pairs:
            ratio = contrast_ratio(colors[foreground_key], colors[background_key])
            if ratio < minimum:
                failures.append((theme_name, foreground_key, background_key, ratio))
    return failures


def print_contrast_failures(minimum: float = MINIMUM_CONTRAST_RATIO) -> list[tuple[str, str, str, float]]:
    """Print failing semantic pairs and return them for callers that need the list."""
    failures = failing_contrast_pairs(minimum=minimum)
    if not failures:
        print(f"Theme contrast check passed: all checked pairs meet {minimum:.1f}:1.")
        return failures
    for theme_name, foreground, background, ratio in failures:
        print(f"Contrast failure [{theme_name}]: {foreground} on {background} = {ratio:.2f}:1 (minimum {minimum:.1f}:1)")
    return failures
