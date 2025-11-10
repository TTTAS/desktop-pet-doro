"""Application-wide theme configuration and helpers."""

from __future__ import annotations

from PySide6 import QtWidgets

APP_THEME_COLORS = {
    "background": "#070c16",
    "surface": "#101b2d",
    "card": "#182540",
    "card_alt": "#1f2f52",
    "accent": "#a78bfa",
    "accent_soft": "#67e8f9",
    "text_primary": "#eef2ff",
    "text_muted": "#9fb4d0",
    "border": "rgba(148, 163, 184, 0.35)",
}

APP_GLOBAL_QSS = """
QMenu {
    background-color: #0b1526;
    color: #f1f5ff;
    border: 1px solid rgba(99,122,166,0.5);
    border-radius: 14px;
    padding: 8px;
}
QMenu::item {
    padding: 6px 14px;
    border-radius: 8px;
}
QMenu::item:selected {
    background-color: rgba(167,139,250,0.18);
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: rgba(148,163,184,0.35);
    margin: 6px 4px;
}
QDialog, QInputDialog {
    background-color: #080f1d;
    color: #e5edff;
    border: 1px solid rgba(71, 85, 105, 0.6);
    border-radius: 18px;
}
QLabel {
    color: #e5edff;
}
QLineEdit,
QPlainTextEdit,
QTextEdit,
QSpinBox,
QDoubleSpinBox {
    background-color: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 10px;
    padding: 6px 10px;
    color: #f8fbff;
}
QLineEdit:focus,
QPlainTextEdit:focus,
QTextEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #a78bfa;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b5cf6, stop:1 #14b8a6);
    color: #05070f;
    border-radius: 10px;
    padding: 7px 16px;
    font-weight: 600;
    border: none;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a78bfa, stop:1 #06b6d4);
}
QPushButton:disabled {
    background: rgba(148,163,184,0.35);
    color: rgba(248,250,252,0.55);
}
QDialogButtonBox QPushButton {
    min-width: 96px;
}
QTableWidget {
    background-color: transparent;
    color: #e2e8f0;
    gridline-color: transparent;
}
QTableWidget::item {
    padding: 10px;
}
QHeaderView::section {
    background-color: rgba(148,163,184,0.12);
    color: #cbd5f5;
    border: none;
    border-bottom: 1px solid rgba(148,163,184,0.2);
    font-weight: 600;
    padding: 8px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 8px 0 8px 0;
}
QScrollBar::handle:vertical {
    background: rgba(148,163,184,0.45);
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(167,139,250,0.75);
}
"""

_APP_THEME_APPLIED = False


def ensure_application_theme() -> None:
    """Apply the shared Qt stylesheet once per QApplication."""
    global _APP_THEME_APPLIED
    if _APP_THEME_APPLIED:
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    existing = app.styleSheet() or ""
    if APP_GLOBAL_QSS.strip() not in existing:
        merged = f"{existing}\n{APP_GLOBAL_QSS}" if existing else APP_GLOBAL_QSS
        app.setStyleSheet(merged)
    _APP_THEME_APPLIED = True
