"""Unified API settings dialog — all chat/LLM settings in one panel."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..components.frameless_dialog import FramelessDialog
from ..helpers.chat_ui_helper import _PROVIDER_PRESETS

_SETTINGS_STYLE = """
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background: white;
    border: 2px solid #FFC4F0;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 10pt;
    color: #2D2D2D;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 2px solid #FF9BE3;
}
QComboBox {
    background: white;
    border: 2px solid #FFC4F0;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 10pt;
}
QComboBox:focus { border: 2px solid #FF9BE3; }
QComboBox::drop-down { border: none; padding-right: 8px; }
QLabel { color: #4a2040; font-size: 10pt; }
QPushButton#saveButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFC4F0, stop:1 #FF9BE3);
    color: white; font-weight: bold;
    border: 2px solid #FF9BE3; border-radius: 8px;
    padding: 8px 24px; font-size: 11pt;
}
QPushButton#saveButton:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FF9BE3, stop:1 #E86BD1);
}
QPushButton#eyeButton {
    background: transparent; border: none; font-size: 14pt; padding: 0 4px;
}
QPushButton#eyeButton:hover { background: #FFC4F0; border-radius: 4px; }
"""

class ChatSettingsDialog(FramelessDialog):
    """All chat/LLM settings in a single panel."""

    def __init__(self, core_manager, parent=None):
        super().__init__("API Settings", parent)
        self._cm = core_manager.chat_orchestrator
        self._applying_preset = False
        self.setFixedWidth(480)
        self._content_widget.setStyleSheet(_SETTINGS_STYLE)
        self._build_ui()
        self._populate_from_settings()

    # ── build ──────────────────────────────────────────────

    def _build_ui(self):
        layout = self.content_layout

        # Provider combo
        self._provider_combo = QtWidgets.QComboBox()
        for name in _PROVIDER_PRESETS:
            self._provider_combo.addItem(name)
        self._provider_combo.addItem("Custom")
        layout.addWidget(self._provider_combo)

        # Form
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._server_url_edit = QtWidgets.QLineEdit()
        self._server_url_edit.setPlaceholderText("http://...")
        form.addRow("Server URL:", self._server_url_edit)

        self._model_edit = QtWidgets.QLineEdit()
        form.addRow("Model:", self._model_edit)

        self._endpoint_edit = QtWidgets.QLineEdit()
        form.addRow("Endpoint path:", self._endpoint_edit)

        # API key row with eye toggle
        key_row = QtWidgets.QHBoxLayout()
        self._api_key_edit = QtWidgets.QLineEdit()
        self._api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        key_row.addWidget(self._api_key_edit, 1)
        self._eye_btn = QtWidgets.QPushButton("\U0001F441")
        self._eye_btn.setObjectName("eyeButton")
        self._eye_btn.setFixedWidth(32)
        self._eye_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        key_row.addWidget(self._eye_btn)
        form.addRow("API Key:", key_row)

        self._temperature_spin = QtWidgets.QDoubleSpinBox()
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setSingleStep(0.05)
        self._temperature_spin.setDecimals(2)
        form.addRow("Temperature:", self._temperature_spin)

        self._timeout_spin = QtWidgets.QSpinBox()
        self._timeout_spin.setRange(1, 300)
        self._timeout_spin.setSuffix(" s")
        form.addRow("Timeout:", self._timeout_spin)

        self._stop_tokens_edit = QtWidgets.QPlainTextEdit()
        self._stop_tokens_edit.setMaximumHeight(72)
        self._stop_tokens_edit.setPlaceholderText("One token per line (use \\n for newline)")
        form.addRow("Stop tokens:", self._stop_tokens_edit)

        self._max_stop_spin = QtWidgets.QSpinBox()
        self._max_stop_spin.setRange(0, 100)
        self._max_stop_spin.setSpecialValueText("Unlimited")
        form.addRow("Max stop tokens:", self._max_stop_spin)

        layout.addLayout(form)

        # Save button
        save_btn = QtWidgets.QPushButton("儲存")
        save_btn.setObjectName("saveButton")
        save_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        layout.addWidget(save_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        # Connections
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._eye_btn.clicked.connect(self._toggle_api_key_visibility)
        save_btn.clicked.connect(self._on_save)

    # ── populate ───────────────────────────────────────────

    def _populate_from_settings(self):
        cm = self._cm
        url = cm.get_server_url()
        model = cm.get_model_name()
        endpoint = cm.get_endpoint()
        max_stop = cm.get_max_stop_tokens()

        self._server_url_edit.setText(url)
        self._model_edit.setText(model)
        self._endpoint_edit.setText(endpoint)
        self._api_key_edit.setText(cm.get_api_key())
        self._temperature_spin.setValue(cm.get_temperature())
        self._timeout_spin.setValue(cm.get_timeout())
        self._max_stop_spin.setValue(max_stop)

        tokens = cm.get_stop_tokens()
        display = "\n".join(t.replace("\n", "\\n") for t in tokens)
        self._stop_tokens_edit.setPlainText(display)

        # Detect which provider matches
        matched = "Custom"
        for name, preset in _PROVIDER_PRESETS.items():
            if (url == preset["server_url"]
                    and model == preset["model"]
                    and endpoint == preset["endpoint_path"]
                    and max_stop == preset["max_stop_tokens"]):
                matched = name
                break

        self._applying_preset = True
        self._provider_combo.setCurrentText(matched)
        self._applying_preset = False

    # ── slots ──────────────────────────────────────────────

    def _on_provider_changed(self, _index: int):
        if self._applying_preset:
            return
        name = self._provider_combo.currentText()
        if name == "Custom":
            return
        preset = _PROVIDER_PRESETS[name]
        self._applying_preset = True
        self._server_url_edit.setText(preset["server_url"])
        self._model_edit.setText(preset["model"])
        self._endpoint_edit.setText(preset["endpoint_path"])
        self._max_stop_spin.setValue(preset["max_stop_tokens"])
        self._applying_preset = False

    def _toggle_api_key_visibility(self):
        mode = self._api_key_edit.echoMode()
        if mode == QtWidgets.QLineEdit.EchoMode.Password:
            self._api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal)
        else:
            self._api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

    def _on_save(self):
        cm = self._cm
        cm.set_server_url(self._server_url_edit.text().strip())
        cm.set_model_name(self._model_edit.text().strip())
        cm.set_endpoint(self._endpoint_edit.text().strip())
        cm.set_api_key(self._api_key_edit.text().strip())
        cm.set_temperature(self._temperature_spin.value())
        cm.set_timeout(self._timeout_spin.value())
        cm.set_max_stop_tokens(self._max_stop_spin.value())

        tokens = [
            line.replace("\\n", "\n")
            for line in self._stop_tokens_edit.toPlainText().splitlines()
            if line.strip()
        ]
        cm.set_stop_tokens(tokens)

        self.accept()
