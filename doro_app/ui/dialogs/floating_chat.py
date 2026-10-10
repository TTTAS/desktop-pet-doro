"""A persistent conversation input with adjustable, remembered geometry."""

from html import escape

from PySide6 import QtCore, QtGui, QtWidgets

from ...utils.config_defaults import (
    DEFAULT_CHAT_WINDOW_WIDTH,
    MAX_CHAT_WINDOW_WIDTH,
    MIN_CHAT_WINDOW_WIDTH,
)


class ChatInput(QtWidgets.QPlainTextEdit):
    send_requested = QtCore.Signal()
    focus_entered = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._composing = False

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focus_entered.emit()

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


class ChatDragHandle(QtWidgets.QWidget):
    """Move the input bar without interfering with text selection."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._press = None
        self.setFixedWidth(14)
        self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        self.setToolTip("拖曳移動輸入框")
        self.setAccessibleName("移動聊天輸入框")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#be819b"))
        for y in (-6, 0, 6):
            painter.drawEllipse(QtCore.QPointF(7, self.height() / 2 + y), 1.5, 1.5)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._origin = self._window.pos()
            self._window.interaction.emit()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self._window.move(self._origin + event.globalPosition().toPoint() - self._press)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._press is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press = None
            self._window.commit_geometry()


class ChatResizeHandle(QtWidgets.QWidget):
    """A narrow edge hit area, separate from editing and moving the chat input."""

    def __init__(self, window, *, left: bool):
        super().__init__(window)
        self._window = window
        self.left = left
        self._press = None
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.setToolTip("拖曳調整聊天框寬度，放開自動儲存")
        self.setAccessibleName("聊天框左側拉伸邊緣" if left else "聊天框右側拉伸邊緣")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(QtGui.QColor("#d995b4"), 2))
        y = self.height() - self._window.BAR_HEIGHT // 2
        painter.drawLine(self.width() // 2, y - 8, self.width() // 2, y + 8)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint().x()
            self._origin = self._window.geometry()
            self._area = self._window._available_area()
            self._window.interaction.emit()
            event.accept()

    def _resize_to(self, event):
        self._window._resize_from_edge(
            self._origin, self._area, self.left, event.globalPosition().toPoint().x() - self._press
        )

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self._resize_to(event)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._press is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._resize_to(event)
            self._press = None
            self._window.commit_geometry()
            event.accept()


class FloatingChatWindow(QtWidgets.QDialog):
    interaction = QtCore.Signal()
    expanded_changed = QtCore.Signal(bool)
    settings_requested = QtCore.Signal()
    geometry_committed = QtCore.Signal(int, int, int)  # input x, input y, preferred width
    BAR_HEIGHT = 72
    HISTORY_HEIGHT = 280

    def __init__(self, send_message, parent=None, *, rejection_reason=None):
        super().__init__(parent)
        self.setWindowTitle("Doro · 說點什麼")
        self.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._send_message = send_message
        self._rejection_reason = rejection_reason or (lambda: "")
        self._resize_handles = []
        self._bar_position = None
        self._preferred_width = DEFAULT_CHAT_WINDOW_WIDTH
        self._expanded = False
        self._sending = False
        self._processing = False
        self._last_sent = ""
        self._messages: list[tuple[str, str]] = []
        self.setStyleSheet("""
            QFrame#inputBar, QFrame#historyPanel {
                background: #fff0f6; border: 1px solid #d995b4; border-radius: 14px;
            }
            QLabel { color: #683e52; background: transparent; }
            QTextBrowser, QPlainTextEdit {
                background: #fffafd; color: #422837; border: 1px solid #e9bfd0;
                border-radius: 10px; padding: 6px; font-size: 14px;
                selection-background-color: #edb0c8; selection-color: #422837;
            }
            QPlainTextEdit:focus { border: 1px solid #bf638b; }
            QPushButton, QToolButton {
                background: #edb0c8; color: #432536; border: none;
                border-radius: 9px; padding: 5px; font-weight: bold;
            }
            QPushButton:hover, QToolButton:hover { background: #f6c6da; }
            QPushButton:pressed, QToolButton:pressed { background: #d88caa; }
            QPushButton:disabled { color: #977c87; background: #f4e5ec; }
        """)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)
        self.history_panel = QtWidgets.QFrame()
        self.history_panel.setObjectName("historyPanel")
        history = QtWidgets.QVBoxLayout(self.history_panel)
        history.setContentsMargins(12, 10, 12, 10)
        history.setSpacing(6)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(QtWidgets.QLabel("Doro · 聊天紀錄"))
        header.addStretch()
        settings = QtWidgets.QPushButton("連線設定")
        settings.setAutoDefault(False)
        settings.clicked.connect(self.settings_requested)
        header.addWidget(settings)
        history.addLayout(header)
        self.transcript = QtWidgets.QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setAccessibleName("本次對話紀錄")
        history.addWidget(self.transcript, 1)
        self.status = QtWidgets.QLabel("想說什麼都可以，我在這裡。")
        self.status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setMaximumHeight(40)
        history.addWidget(self.status)
        root.addWidget(self.history_panel, 1)
        self.history_panel.hide()
        self.bar = QtWidgets.QFrame()
        self.bar.setObjectName("inputBar")
        self.bar.setFixedHeight(self.BAR_HEIGHT - 8)
        row = QtWidgets.QHBoxLayout(self.bar)
        row.setContentsMargins(6, 8, 8, 8)
        row.setSpacing(6)
        self.drag_handle = ChatDragHandle(self)
        row.addWidget(self.drag_handle)
        self.input = ChatInput()
        self.input.setPlaceholderText("跟 Doro 說點什麼…")
        self.input.setAccessibleName("給 Doro 的訊息")
        self.input.setToolTip("Enter 送出；Shift+Enter 換行")
        self.input.setFixedHeight(46)
        self.input.textChanged.connect(self._input_changed)
        self.input.send_requested.connect(self.send)
        self.input.focus_entered.connect(self.interaction)
        row.addWidget(self.input, 1)
        self.send_button = QtWidgets.QPushButton("送出")
        self.send_button.setFixedSize(48, 34)
        self.send_button.setEnabled(False)
        self.send_button.setAutoDefault(False)
        self.send_button.clicked.connect(self.send)
        row.addWidget(self.send_button)
        self.history_button = QtWidgets.QToolButton()
        self.history_button.setText("↑")
        self.history_button.setToolTip("向上展開聊天紀錄")
        self.history_button.setAccessibleName("展開或收起聊天紀錄")
        self.history_button.setFixedSize(28, 34)
        self.history_button.clicked.connect(
            lambda: self.collapse() if self._expanded else self.expand()
        )
        row.addWidget(self.history_button)
        self.hide_button = QtWidgets.QToolButton()
        self.hide_button.setText("×")
        self.hide_button.setToolTip("隱藏輸入框；右鍵 Doro 可重新開啟")
        self.hide_button.setAccessibleName("隱藏聊天輸入框")
        self.hide_button.setFixedSize(28, 34)
        self.hide_button.clicked.connect(self.close)
        row.addWidget(self.hide_button)
        root.addWidget(self.bar)
        self._resize_handles = [
            ChatResizeHandle(self, left=True),
            ChatResizeHandle(self, left=False),
        ]
        self.setFixedSize(self._preferred_width, self.BAR_HEIGHT)
        self._render_messages()

    @property
    def expanded(self) -> bool:
        return self.isVisible() and self._expanded

    @property
    def interacting(self) -> bool:
        return self.isVisible() and (self._expanded or self.isActiveWindow())

    def _available_area(self, point=None):
        if point is None:
            point = QtCore.QPoint(self.geometry().center().x(), self.geometry().bottom())
        screen = QtWidgets.QApplication.screenAt(point) or self.screen()
        return screen.availableGeometry()

    def restore_layout(
        self, width: int, position: QtCore.QPoint | None, default_area: QtCore.QRect
    ):
        """Restore the collapsed input geometry, or place it lower-center on first use."""
        self._preferred_width = max(MIN_CHAT_WINDOW_WIDTH, min(MAX_CHAT_WINDOW_WIDTH, width))
        area = (
            self._available_area(position + QtCore.QPoint(width // 2, self.BAR_HEIGHT // 2))
            if position is not None
            else default_area
        )
        self.setFixedSize(min(self._preferred_width, area.width()), self.BAR_HEIGHT)
        anchor = (
            position
            if position is not None
            else QtCore.QPoint(
                area.left() + (area.width() - self.width()) // 2,
                area.top() + round(area.height() * 0.78) - self.BAR_HEIGHT // 2,
            )
        )
        self.move(anchor)
        self._fit_area(area)
        self._bar_position = self.pos()

    def _fit_area(self, area):
        extra = (
            min(self.HISTORY_HEIGHT, max(0, area.height() - self.BAR_HEIGHT))
            if self._expanded
            else 0
        )
        self.setFixedSize(min(self._preferred_width, area.width()), self.BAR_HEIGHT + extra)
        self.move(
            max(area.left(), min(self.x(), area.right() - self.width() + 1)),
            max(area.top(), min(self.y(), area.bottom() - self.height() + 1)),
        )

    def keep_on_screen(self):
        self._fit_area(self._available_area())

    def commit_geometry(self):
        """Persist only a finished user move/resize, never history expansion."""
        self.keep_on_screen()
        self._bar_position = QtCore.QPoint(self.x(), self.y() + self.height() - self.BAR_HEIGHT)
        self.geometry_committed.emit(
            self._bar_position.x(), self._bar_position.y(), self._preferred_width
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for handle in self._resize_handles:
            handle.setGeometry(0 if handle.left else self.width() - 7, 0, 7, self.height())
            handle.raise_()

    def _resize_from_edge(self, origin: QtCore.QRect, area: QtCore.QRect, left: bool, delta: int):
        # Keep the opposite edge fixed; don't quantize the mouse's movement.
        fixed_edge = origin.x() + origin.width() if left else origin.x()
        available = fixed_edge - area.left() if left else area.right() + 1 - fixed_edge
        maximum = max(1, min(MAX_CHAT_WINDOW_WIDTH, available))
        minimum = min(MIN_CHAT_WINDOW_WIDTH, maximum)
        width = max(minimum, min(maximum, origin.width() + (-delta if left else delta)))
        self._preferred_width = max(MIN_CHAT_WINDOW_WIDTH, width)
        self.setFixedSize(width, origin.height())
        self.move(fixed_edge - width if left else fixed_edge, origin.y())
        self.layout().activate()

    def show_input(self, anchor: QtCore.QPoint | None = None, *, focus: bool = False):
        if anchor is not None:
            self._bar_position = QtCore.QPoint(anchor)
        if self._bar_position is not None:
            self.move(
                self._bar_position.x(), self._bar_position.y() - self.height() + self.BAR_HEIGHT
            )
        self.keep_on_screen()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, not focus)
        self.show()
        if focus:
            self.interaction.emit()
            self.raise_()
            self.activateWindow()
            self.input.setFocus()

    def _set_history(self, visible: bool):
        if self._expanded == visible:
            return
        if self._bar_position is None:
            self._bar_position = QtCore.QPoint(self.x(), self.y() + self.height() - self.BAR_HEIGHT)
        area = self._available_area()
        extra = min(self.HISTORY_HEIGHT, max(0, area.height() - self.BAR_HEIGHT)) if visible else 0
        self._expanded = visible
        self.history_panel.setVisible(visible)
        self.history_button.setText("↓" if visible else "↑")
        self.history_button.setToolTip("收起聊天紀錄" if visible else "向上展開聊天紀錄")
        self.setFixedSize(self.width(), self.BAR_HEIGHT + extra)
        self.move(self._bar_position.x(), self._bar_position.y() - extra)
        self.keep_on_screen()
        self.layout().activate()
        self.expanded_changed.emit(visible)

    def expand(self):
        self.interaction.emit()
        self._set_history(True)

    def collapse(self):
        self._set_history(False)

    def reject(self):
        if self._expanded:
            self.collapse()
        else:
            self.close()

    def closeEvent(self, event):
        self.collapse()
        event.accept()
        self.expanded_changed.emit(False)

    def _input_changed(self):
        self.send_button.setEnabled(bool(self.input.toPlainText().strip()) and not self._sending)
        self.interaction.emit()

    def _set_status(self, text: str, *, attention: bool = False):
        self.status.setText(text)
        self.history_button.setText("!" if attention else ("↓" if self._expanded else "↑"))
        self.history_button.setToolTip(text + "\n點此展開／收起紀錄")

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
            self._set_status("Doro 正在想…" if text == "Thinking..." else text)
            return
        self._messages.append(("Doro", text))
        self._processing = False
        self._render_messages()
        self._set_status("我在，繼續說吧。")

    def finish_processing(self):
        if self._processing:
            self._processing = False
            self._set_status("處理完成，可以繼續聊。")

    def send(self):
        text = self.input.toPlainText().strip()
        if not text or self._sending:
            return
        self.interaction.emit()
        self._sending = True
        self.send_button.setEnabled(False)
        self._set_status("正在送出…")
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
            if self.status.text() == "正在送出…":
                self._set_status("已送出，等 Doro 回覆。")
        else:
            # No new entry for a rejected send; the input remains available.
            self._messages = [message for message in self._messages if message is not entry]
            reason = self._rejection_reason() or "未提供拒收原因，請稍後再試。"
            self._set_status(f"這次未送出，草稿已保留。原因：{reason}", attention=True)
        self._render_messages()
        self.send_button.setEnabled(bool(self.input.toPlainText().strip()))

    def request_failed(self, error: str, was_auto: bool):
        if was_auto:
            return
        if not self.input.toPlainText().strip() and self._last_sent:
            self.input.setPlainText(self._last_sent)
        self._processing = False
        reason = error.strip() or "未提供錯誤原因，請稍後再試。"
        self._set_status(f"暫時沒收到回覆，草稿已保留。原因：{reason}", attention=True)

    def clear_history(self):
        self._messages.clear()
        self._last_sent = ""
        self._processing = False
        self._render_messages()
        self._set_status("對話紀錄已清除。")
