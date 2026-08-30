"""Doro-themed chat dialog for conversation interface."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class DoroChatDialog(QtWidgets.QDialog):
    """
    Custom chat dialog with Doro theme colors.

    Features:
    - Pink color scheme matching Doro's hair color (#FF9BE3FF)
    - Multi-line text input
    - Send button
    - Clear button
    - Smooth gradients and rounded corners
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        """
        Initialize Doro-themed chat dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Dialog properties
        self.setWindowTitle("與 Doro 對話")
        self.setMinimumWidth(400)
        self.setMinimumHeight(200)

        # Remove window frame for custom styling
        self.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.FramelessWindowHint)

        # Make dialog semi-transparent background
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        # Result storage
        self._message = ""

        # Drag state — initialized here so mouseMoveEvent never hits an
        # AttributeError when the user drags before any mousePressEvent
        # (matters now that the dialog is cached and reused across opens).
        self._drag_position = None

        # Setup UI
        self._setup_ui()
        self._apply_doro_stylesheet()

    def _setup_ui(self):
        """Create and layout all UI elements."""
        # Main container widget (for border and background)
        container = QtWidgets.QWidget(self)
        container.setObjectName("chatContainer")

        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        # Container layout
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title label
        title_label = QtWidgets.QLabel("💬 與 Doro 說話")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Instruction label
        instruction_label = QtWidgets.QLabel("輸入你想對 doro 說的話：")
        instruction_label.setObjectName("instructionLabel")
        layout.addWidget(instruction_label)

        # Text input area
        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setObjectName("messageInput")
        self.text_edit.setPlaceholderText("在這裡輸入訊息...")
        self.text_edit.setMaximumHeight(120)
        self.text_edit.setAcceptRichText(False)  # Plain text only
        layout.addWidget(self.text_edit)

        # Character count label
        self.char_count_label = QtWidgets.QLabel("0 字元")
        self.char_count_label.setObjectName("charCountLabel")
        self.char_count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.char_count_label)

        # Connect text change to update counter
        self.text_edit.textChanged.connect(self._update_char_count)

        # Button layout
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(8)

        # Clear button
        clear_btn = QtWidgets.QPushButton("清除")
        clear_btn.setObjectName("clearButton")
        clear_btn.clicked.connect(self.text_edit.clear)
        clear_btn.setMinimumHeight(36)
        button_layout.addWidget(clear_btn)

        # Cancel button
        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setMinimumHeight(36)
        button_layout.addWidget(cancel_btn)

        # Send button
        send_btn = QtWidgets.QPushButton("發送 ✉")
        send_btn.setObjectName("sendButton")
        send_btn.clicked.connect(self._on_send)
        send_btn.setMinimumHeight(36)
        send_btn.setDefault(True)  # Enter key triggers this
        button_layout.addWidget(send_btn)

        layout.addLayout(button_layout)

        # Set focus to text input
        self.text_edit.setFocus()

    def _apply_doro_stylesheet(self):
        """Apply pink-themed stylesheet matching Doro's colors."""
        # Doro color palette (matching themed_menu.py)
        doro_pink = "#FF9BE3"
        doro_light_pink = "#FFC4F0"
        doro_dark_pink = "#E86BD1"

        stylesheet = f"""
        QDialog {{
            background-color: transparent;
        }}

        #chatContainer {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF,
                stop:0.05 #FFF5FC,
                stop:1 #FFE8F7
            );
            border: 3px solid {doro_pink};
            border-radius: 16px;
        }}

        #titleLabel {{
            color: {doro_dark_pink};
            font-size: 16pt;
            font-weight: bold;
            padding: 4px;
        }}

        #instructionLabel {{
            color: #2D2D2D;
            font-size: 10pt;
            padding: 2px;
        }}

        #charCountLabel {{
            color: #666666;
            font-size: 9pt;
            padding: 2px;
        }}

        #messageInput {{
            background-color: white;
            border: 2px solid {doro_light_pink};
            border-radius: 8px;
            padding: 8px;
            font-size: 11pt;
            color: #2D2D2D;
        }}

        #messageInput:focus {{
            border: 2px solid {doro_pink};
            background-color: #FFFCFE;
        }}

        QPushButton {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 white,
                stop:1 {doro_light_pink}
            );
            border: 2px solid {doro_pink};
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 11pt;
            font-weight: 600;
            color: #2D2D2D;
        }}

        QPushButton:hover {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {doro_light_pink},
                stop:1 {doro_pink}
            );
            color: white;
        }}

        QPushButton:pressed {{
            background-color: {doro_dark_pink};
            color: white;
        }}

        #sendButton {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {doro_light_pink},
                stop:1 {doro_pink}
            );
            color: white;
            font-weight: bold;
        }}

        #sendButton:hover {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {doro_pink},
                stop:1 {doro_dark_pink}
            );
        }}

        #clearButton {{
            background-color: white;
            color: #666666;
        }}

        #clearButton:hover {{
            background-color: #F0F0F0;
            color: #333333;
        }}

        #cancelButton {{
            background-color: white;
            color: #666666;
        }}

        #cancelButton:hover {{
            background-color: #F0F0F0;
            color: #333333;
        }}
        """

        self.setStyleSheet(stylesheet)

    def _update_char_count(self):
        """Update character count label."""
        text = self.text_edit.toPlainText()
        count = len(text)
        self.char_count_label.setText(f"{count} 字元")

    def _on_send(self):
        """Handle send button click."""
        text = self.text_edit.toPlainText().strip()
        if not text:
            # Show warning if empty
            QtWidgets.QMessageBox.warning(self, "訊息為空", "請輸入一些文字後再發送。")
            return

        self._message = text
        self.accept()

    def get_message(self) -> str:
        """
        Get the message text entered by user.

        Returns:
            The message text, or empty string if canceled
        """
        return self._message

    def run(self) -> tuple[str, bool]:
        """Reset transient state, show the dialog modally, and return the result.

        Centralizes the per-open reset so the dialog can be cached and reused
        without leaking the previous message or leaving the input unfocused.

        Returns:
            Tuple of (message_text, accepted)
        """
        self._message = ""
        self.text_edit.clear()  # char count auto-resets via textChanged signal
        self.text_edit.setFocus()
        if self.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return self._message, True
        return "", False

    # Enable dragging the dialog
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Handle mouse press for dragging."""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Handle mouse move for dragging."""
        if event.buttons() == QtCore.Qt.MouseButton.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()


def show_chat_dialog(parent: QtWidgets.QWidget | None = None) -> tuple[str, bool]:
    """
    Show Doro-themed chat dialog and return the result.

    Args:
        parent: Parent widget

    Returns:
        Tuple of (message_text, accepted)
    """
    return DoroChatDialog(parent).run()
