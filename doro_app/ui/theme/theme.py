"""Application-wide theme configuration and helpers."""

from __future__ import annotations

from PySide6 import QtWidgets

APP_THEME_COLORS = {
    "background": "#fff0f6",  # Light pink background
    "surface": "#ffe4f0",  # Soft pink surface
    "card": "#ffffff",  # White card
    "card_alt": "#fff5fa",  # Very light pink alternate
    "accent": "#e8609c",  # Doro pink accent
    "accent_soft": "#f9a8d4",  # Soft pink accent
    "text_primary": "#4a2040",  # Dark plum text
    "text_muted": "#9c6b8a",  # Muted pink-gray text
    "border": "rgba(232, 96, 156, 0.30)",  # Pink border
}

APP_GLOBAL_QSS = """
QMenu {
    background-color: #fff5fa;
    color: #4a2040;
    border: 1px solid rgba(232, 96, 156, 0.40);
    border-radius: 14px;
    padding: 8px;
}
QMenu::item {
    padding: 6px 14px;
    border-radius: 8px;
}
QMenu::item:selected {
    background-color: rgba(232, 96, 156, 0.15);
    color: #c0266e;
}
QMenu::separator {
    height: 1px;
    background: rgba(232, 96, 156, 0.25);
    margin: 6px 4px;
}
QDialog, QInputDialog {
    background-color: #fff0f6;
    color: #4a2040;
    border: 1px solid rgba(232, 96, 156, 0.35);
    border-radius: 18px;
}
QLabel {
    color: #4a2040;
}
QLineEdit,
QPlainTextEdit,
QTextEdit,
QSpinBox,
QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid rgba(232, 96, 156, 0.40);
    border-radius: 10px;
    padding: 6px 10px;
    color: #4a2040;
}
QLineEdit:focus,
QPlainTextEdit:focus,
QTextEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #e8609c;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f472b6, stop:1 #e8609c);
    color: #ffffff;
    border-radius: 10px;
    padding: 7px 16px;
    font-weight: 600;
    border: none;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ec4899, stop:1 #db2777);
}
QPushButton:disabled {
    background: rgba(200, 160, 180, 0.35);
    color: rgba(100, 60, 80, 0.55);
}
QDialogButtonBox QPushButton {
    min-width: 96px;
}
QComboBox {
    background-color: #ffffff;
    border: 1px solid rgba(232, 96, 156, 0.40);
    border-radius: 10px;
    padding: 6px 10px;
    color: #4a2040;
}
QComboBox:focus {
    border-color: #e8609c;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #4a2040;
    selection-background-color: rgba(232, 96, 156, 0.15);
    selection-color: #c0266e;
    border: 1px solid rgba(232, 96, 156, 0.30);
    border-radius: 8px;
}
QGroupBox {
    color: #4a2040;
    border: 1px solid rgba(232, 96, 156, 0.30);
    border-radius: 10px;
    margin-top: 8px;
    padding-top: 14px;
}
QGroupBox::title {
    color: #e8609c;
    subcontrol-origin: margin;
    padding: 0 6px;
}
QTableWidget {
    background-color: #ffffff;
    color: #4a2040;
    gridline-color: rgba(232, 96, 156, 0.20);
}
QTableWidget::item {
    padding: 10px;
}
QTableWidget::item:selected {
    background-color: rgba(232, 96, 156, 0.15);
    color: #c0266e;
}
QHeaderView::section {
    background-color: #fff0f6;
    color: #e8609c;
    border: none;
    border-bottom: 1px solid rgba(232, 96, 156, 0.25);
    font-weight: 600;
    padding: 8px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 8px 0 8px 0;
}
QScrollBar::handle:vertical {
    background: rgba(232, 96, 156, 0.35);
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(232, 96, 156, 0.60);
}
QMessageBox {
    background-color: #fff0f6;
}
QMessageBox QLabel {
    color: #4a2040;
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
