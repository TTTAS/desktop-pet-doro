"""Form for faking a chat reply (「假傳伺服器回應」) without the server.

Each field maps to one field of the chat reply schema (ADR 0005), so testers
never hand-write JSON. The form validates strictly before sending: the real
reply path silently drops a malformed move or tool, which would hide a typo.
"""

from __future__ import annotations

import json

from pydantic import ValidationError
from PySide6 import QtWidgets

from ...core.chat.chat_reply import ChatMove, ChatTool
from ..components.frameless_dialog import FramelessDialog

_STYLE = """
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background: white;
    border: 2px solid #FFC4F0;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 10pt;
    color: #2D2D2D;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 2px solid #FF9BE3;
}
QLabel { color: #4a2040; font-size: 10pt; }
QLabel#errorLabel { color: #c0264f; }
QLabel#previewLabel { color: #7a5a70; font-family: monospace; font-size: 9pt; }
QPushButton#sendButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFC4F0, stop:1 #FF9BE3);
    color: white; font-weight: bold;
    border: 2px solid #FF9BE3; border-radius: 8px;
    padding: 8px 24px; font-size: 11pt;
}
"""

_DIRECTIONS = (
    ("右", "right"),
    ("左", "left"),
    ("上", "up"),
    ("下", "down"),
    ("右上", "up-right"),
    ("左上", "up-left"),
    ("右下", "down-right"),
    ("左下", "down-left"),
)
_SPEEDS = (("預設", None), ("慢", "slow"), ("中", "med"), ("快", "fast"))
_TOOLS = (
    ("不用工具", None),
    ("讀網頁 read", "read"),
    ("上網搜尋 verify", "verify"),
    ("操作網站 operate", "operate"),
    ("開站登入 login", "login"),
    ("點桌面 click", "click"),
)
# 每種工具要填哪一格；click 沒有參數，點的是「移動」給的座標。
_TOOL_FIELD = {"read": "url", "login": "url", "verify": "query", "operate": "goal"}


class SimulateReplyDialog(FramelessDialog):
    """Collect one chat reply as form fields; ``reply_json()`` after ``exec()``."""

    def __init__(self, state_keys: list[str], parent: QtWidgets.QWidget | None = None):
        super().__init__("假傳伺服器回應", parent)
        self.setFixedWidth(440)
        self._content_widget.setStyleSheet(_STYLE)
        self._reply: dict | None = None
        self._build_ui(state_keys)
        self._sync_visibility()
        self._update_preview()

    # ── build ──────────────────────────────────────────────

    def _build_ui(self, state_keys: list[str]) -> None:
        form = QtWidgets.QFormLayout()
        form.setSpacing(8)

        self._state_combo = QtWidgets.QComboBox()
        self._state_combo.addItem("（不換狀態）", None)
        for key in state_keys:
            self._state_combo.addItem(key, key)
        form.addRow("狀態:", self._state_combo)

        self._line_edit = QtWidgets.QPlainTextEdit()
        self._line_edit.setPlaceholderText("Doro 要說的話")
        self._line_edit.setFixedHeight(60)
        form.addRow("台詞:", self._line_edit)

        self._move_combo = QtWidgets.QComboBox()
        self._move_combo.addItem("不移動", None)
        self._move_combo.addItem("往某方向走", "direction")
        self._move_combo.addItem("走到螢幕座標", "point")
        form.addRow("移動:", self._move_combo)

        self._dir_combo = QtWidgets.QComboBox()
        for label, value in _DIRECTIONS:
            self._dir_combo.addItem(label, value)
        self._distance_spin = QtWidgets.QSpinBox()
        self._distance_spin.setRange(1, 2000)
        self._distance_spin.setValue(80)
        self._distance_spin.setSuffix(" px")
        self._speed_combo = QtWidgets.QComboBox()
        for label, value in _SPEEDS:
            self._speed_combo.addItem(label, value)
        self._x_spin = QtWidgets.QSpinBox()
        self._x_spin.setRange(0, 20000)
        self._y_spin = QtWidgets.QSpinBox()
        self._y_spin.setRange(0, 20000)
        form.addRow("方向:", self._dir_combo)
        form.addRow("距離:", self._distance_spin)
        form.addRow("速度:", self._speed_combo)
        form.addRow("X:", self._x_spin)
        form.addRow("Y:", self._y_spin)

        self._tool_combo = QtWidgets.QComboBox()
        for label, value in _TOOLS:
            self._tool_combo.addItem(label, value)
        form.addRow("工具:", self._tool_combo)

        self._url_edit = QtWidgets.QLineEdit()
        self._url_edit.setPlaceholderText("https://…")
        self._query_edit = QtWidgets.QLineEdit()
        self._query_edit.setPlaceholderText("例：探索推薦：有趣的互動網站")
        self._goal_edit = QtWidgets.QLineEdit()
        self._goal_edit.setPlaceholderText("例：在蝦皮把藍牙耳機加入購物車")
        form.addRow("網址:", self._url_edit)
        form.addRow("搜尋任務:", self._query_edit)
        form.addRow("目標:", self._goal_edit)
        self._form = form
        self.content_layout.addLayout(form)

        self._preview = QtWidgets.QLabel()
        self._preview.setObjectName("previewLabel")
        self._preview.setWordWrap(True)
        self.content_layout.addWidget(self._preview)

        self._error = QtWidgets.QLabel()
        self._error.setObjectName("errorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        self.content_layout.addWidget(self._error)

        send = QtWidgets.QPushButton("送出")
        send.setObjectName("sendButton")
        send.clicked.connect(self._on_send)
        self.content_layout.addWidget(send)

        for combo in (self._move_combo, self._tool_combo):
            combo.currentIndexChanged.connect(self._sync_visibility)
        for combo in (self._state_combo, self._dir_combo, self._speed_combo):
            combo.currentIndexChanged.connect(self._update_preview)
        self._move_combo.currentIndexChanged.connect(self._update_preview)
        self._tool_combo.currentIndexChanged.connect(self._update_preview)
        for spin in (self._distance_spin, self._x_spin, self._y_spin):
            spin.valueChanged.connect(self._update_preview)
        for edit in (self._url_edit, self._query_edit, self._goal_edit):
            edit.textChanged.connect(self._update_preview)
        self._line_edit.textChanged.connect(self._update_preview)

    def _set_row_visible(self, widget: QtWidgets.QWidget, visible: bool) -> None:
        self._form.setRowVisible(widget, visible)

    def _sync_visibility(self) -> None:
        move = self._move_combo.currentData()
        for widget in (self._dir_combo, self._distance_spin, self._speed_combo):
            self._set_row_visible(widget, move == "direction")
        for widget in (self._x_spin, self._y_spin):
            self._set_row_visible(widget, move == "point")
        field = _TOOL_FIELD.get(self._tool_combo.currentData())
        self._set_row_visible(self._url_edit, field == "url")
        self._set_row_visible(self._query_edit, field == "query")
        self._set_row_visible(self._goal_edit, field == "goal")
        self.adjustSize()

    # ── reply ──────────────────────────────────────────────

    def build_reply(self) -> dict:
        """The chat reply the current form describes (not yet validated)."""
        move = self._move_combo.currentData()
        move_value: dict | None = None
        if move == "direction":
            move_value = {
                "dir": self._dir_combo.currentData(),
                "distance": self._distance_spin.value(),
            }
            if self._speed_combo.currentData():
                move_value["speed"] = self._speed_combo.currentData()
        elif move == "point":
            move_value = {"x": self._x_spin.value(), "y": self._y_spin.value()}

        kind = self._tool_combo.currentData()
        tool_value: dict | None = None
        if kind:
            tool_value = {"kind": kind}
            field = _TOOL_FIELD.get(kind)
            if field:
                edit = {"url": self._url_edit, "query": self._query_edit, "goal": self._goal_edit}
                tool_value[field] = edit[field].text().strip()

        return {
            "state": self._state_combo.currentData(),
            "line": self._line_edit.toPlainText().strip(),
            "move": move_value,
            "tool": tool_value,
        }

    def validate(self, reply: dict) -> str:
        """Return a problem to show, or ``""``. Stricter than the real reply
        path, which would quietly drop a bad move or tool."""
        if not reply["line"]:
            return "台詞不能是空的。"
        try:
            if reply["move"] is not None:
                ChatMove.model_validate(reply["move"])
            if reply["tool"] is not None:
                ChatTool.model_validate(reply["tool"])
        except ValidationError as exc:
            return "；".join(err["msg"].removeprefix("Value error, ") for err in exc.errors())
        return ""

    def reply_json(self) -> str | None:
        """The accepted reply as JSON, or ``None`` if the dialog was cancelled."""
        if self._reply is None:
            return None
        return json.dumps(self._reply, ensure_ascii=False)

    def _update_preview(self) -> None:
        self._preview.setText(json.dumps(self.build_reply(), ensure_ascii=False))

    def _on_send(self) -> None:
        reply = self.build_reply()
        problem = self.validate(reply)
        if problem:
            self._error.setText(problem)
            self._error.show()
            return
        self._reply = reply
        self.accept()
