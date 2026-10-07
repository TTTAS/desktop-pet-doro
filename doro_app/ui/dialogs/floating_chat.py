"""A persistent, collapsible conversation window beside the desktop pet."""

from html import escape

from PySide6 import QtCore, QtWidgets

from ..components.frameless_dialog import FramelessDialog


class ChatInput(QtWidgets.QPlainTextEdit):
    send_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._composing = False

    def inputMethodEvent(self, event):
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            if self._composing:
                event.accept()
                return
            if not event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.send_requested.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class ChatLauncher(QtWidgets.QPushButton):
    """A click opens chat; a drag only moves the floating launcher."""

    def __init__(self, window):
        super().__init__("聊聊 · Doro", window)
        self._window = window
        self._press = None
        self._dragged = False
        self.setToolTip("點一下與 Doro 說話；拖曳可移動")
        self.setAccessibleName("開啟 Doro 聊天窗")

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._origin = self._window.pos()
            self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._press
            if delta.manhattanLength() > QtWidgets.QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self._window.move(self._origin + delta)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        if self._dragged:
            self._dragged = False
            self.setDown(False)
            self._window.keep_on_screen()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FloatingChatWindow(FramelessDialog):
    interaction = QtCore.Signal()
    expanded_changed = QtCore.Signal(bool)
    settings_requested = QtCore.Signal()

    def __init__(self, send_message, parent=None):
        super().__init__("Doro · 陪你聊聊", parent)
        self.setWindowTitle("Doro · 陪你聊聊")
        self.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(False)
        close = self._title_bar.findChild(QtWidgets.QPushButton)
        close.setText("×")
        close.setToolTip("收起聊天窗")
        close.setAccessibleName("收起聊天窗")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._send_message = send_message
        self._expanded = False
        self._sending = False
        self._processing = False
        self._last_sent = ""
        self._messages: list[tuple[str, str]] = []
        self._full_size = QtCore.QSize(410, 520)
        self.setStyleSheet("""
            QLabel { color: #683e52; background: transparent; }
            QTextBrowser, QPlainTextEdit {
                background: #fffafd; color: #422837; border: 1px solid #e9bfd0;
                border-radius: 12px; padding: 9px; font-size: 14px;
                selection-background-color: #edb0c8; selection-color: #422837;
            }
            QPlainTextEdit:focus { border: 2px solid #cf789b; }
            QPushButton {
                background: #e7a0bc; color: #432536; border: 1px solid #cf789b;
                border-radius: 12px; padding: 8px 14px; font-weight: bold;
            }
            QPushButton:hover { background: #f1bad0; }
            QPushButton:pressed { background: #d88caa; }
            QPushButton:disabled { color: #977c87; background: #f4e5ec; border-color: #ead4dd; }
        """)
        self.transcript = QtWidgets.QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setAccessibleName("本次對話紀錄")
        self.content_layout.addWidget(self.transcript, 1)
        self.status = QtWidgets.QLabel("想說什麼都可以，我在這裡。")
        self.status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.content_layout.addWidget(self.status)
        self.input = ChatInput()
        self.input.setPlaceholderText("跟 Doro 說點什麼…")
        self.input.setAccessibleName("給 Doro 的訊息")
        self.input.setFixedHeight(94)
        self.input.textChanged.connect(self._input_changed)
        self.input.send_requested.connect(self.send)
        self.content_layout.addWidget(self.input)
        row = QtWidgets.QHBoxLayout()
        settings = QtWidgets.QPushButton("連線設定")
        settings.clicked.connect(self.settings_requested)
        row.addWidget(settings)
        row.addStretch()
        self.send_button = QtWidgets.QPushButton("送出")
        self.send_button.setEnabled(False)
        self.send_button.setAutoDefault(False)
        self.send_button.clicked.connect(self.send)
        row.addWidget(self.send_button)
        self.content_layout.addLayout(row)
        hint = QtWidgets.QLabel("Enter 送出 · Shift+Enter 換行 · Esc 收起")
        hint.setWordWrap(True)
        self.content_layout.addWidget(hint)
        self.launcher = ChatLauncher(self)
        self.launcher.clicked.connect(self.expand)
        self._outer_layout.addWidget(self.launcher)
        self._card.hide()
        self.setFixedSize(142, 64)
        self._render_messages()

    @property
    def expanded(self) -> bool:
        return self.isVisible() and self._expanded

    def keep_on_screen(self):
        screen = QtWidgets.QApplication.screenAt(self.pos()) or self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(
            max(area.left(), min(self.x(), area.right() - self.width() + 1)),
            max(area.top(), min(self.y(), area.bottom() - self.height() + 1)),
        )

    def show_launcher(self, anchor: QtCore.QPoint):
        self.move(anchor)
        self.keep_on_screen()
        self.show()

    def expand(self):
        self.interaction.emit()
        self._expanded = True
        self.launcher.hide()
        self._card.show()
        self.setMinimumSize(320, 430)
        self.setMaximumSize(16777215, 16777215)
        self.resize(self._full_size)
        self.keep_on_screen()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.expanded_changed.emit(True)

    def collapse(self):
        if self._expanded:
            self._full_size = self.size()
        self._expanded = False
        self._card.hide()
        self.launcher.show()
        self.setFixedSize(142, 64)
        self.keep_on_screen()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.expanded_changed.emit(False)

    def reject(self):
        self.collapse()

    def closeEvent(self, event):
        event.ignore()
        self.collapse()

    def paintEvent(self, event):
        if self._expanded:
            super().paintEvent(event)

    def _input_changed(self):
        self.send_button.setEnabled(bool(self.input.toPlainText().strip()) and not self._sending)
        self.interaction.emit()

    def _render_messages(self):
        self._messages = self._messages[-200:]
        if not self._messages:
            self.transcript.setHtml(
                '<p style="color:#906c7d">今天過得怎麼樣？<br>點下面，跟我說說吧。</p>'
            )
            return
        parts = []
        for role, message in self._messages:
            color = "#f5d7e5" if role == "你" else "#fbeaf1"
            content = escape(message).replace("\n", "<br>")
            parts.append(
                f'<table width="100%" cellpadding="9" bgcolor="{color}"><tr><td>'
                f"<b>{role}</b><br>{content}</td></tr></table><br>"
            )
        self.transcript.setHtml("".join(parts))
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

    def receive_reply(self, text: str, options: dict):
        if not text.strip():
            return
        if options.get("auto_hide") is False:
            self._processing = True
            self.status.setText("Doro 正在想…" if text == "Thinking..." else text)
            return
        self._messages.append(("Doro", text))
        self._processing = False
        self._render_messages()
        self.status.setText("我在，繼續說吧。")

    def finish_processing(self):
        if self._processing:
            self._processing = False
            self.status.setText("處理完成，可以繼續聊。")

    def send(self):
        text = self.input.toPlainText().strip()
        if not text or self._sending:
            return
        self.interaction.emit()
        self._sending = True
        self.send_button.setEnabled(False)
        # Add first: local commands can reply synchronously inside send_message.
        entry = ("你", text)
        self._messages.append(entry)
        try:
            accepted = self._send_message(text)
        finally:
            self._sending = False
        if accepted:
            self._last_sent = text
            self.input.clear()
        else:
            # No new entry for a rejected send; the input remains available.
            self._messages = [message for message in self._messages if message is not entry]
            self.status.setText("這次未送出，草稿已保留。請等 Doro 忙完，或檢查連線設定。")
        self._render_messages()
        self.send_button.setEnabled(bool(self.input.toPlainText().strip()))

    def request_failed(self, _error: str, was_auto: bool):
        if was_auto:
            return
        if not self.input.toPlainText().strip() and self._last_sent:
            self.input.setPlainText(self._last_sent)
        self.status.setText("暫時沒收到回覆，請檢查連線後再試；草稿已保留。")

    def clear_history(self):
        self._messages.clear()
        self._last_sent = ""
        self._processing = False
        self._render_messages()
        self.status.setText("對話紀錄已清除。")
