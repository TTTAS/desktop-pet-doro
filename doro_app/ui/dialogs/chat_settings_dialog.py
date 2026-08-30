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
QCheckBox { color: #4a2040; font-size: 10pt; spacing: 6px; }
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
        self._core = core_manager
        self._cm = core_manager.chat_orchestrator
        self._applying_preset = False
        self.setFixedWidth(480)
        self._content_widget.setStyleSheet(_SETTINGS_STYLE)
        self._build_ui()
        self._populate_from_settings()

    def refresh(self) -> None:
        """Re-read settings into the form (use when re-showing a cached dialog)."""
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
        self._eye_btn = QtWidgets.QPushButton("\U0001f441")
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

        # ── Accessibility tree reading (Phase 1d) ──────────────
        self._a11y_checkbox = QtWidgets.QCheckBox("讓 Doro 讀取前景視窗的可點元素（無障礙樹）")
        layout.addWidget(self._a11y_checkbox)
        a11y_hint = QtWidgets.QLabel(
            "開啟後，目前前景視窗的按鈕／連結／輸入框與座標會加進提示詞，"
            "讓 Doro 能「點某個按鈕」。預設關閉；目前僅 Windows 有真實後端；"
            "密碼欄位會自動遮蔽；每次讀取會記到本機稽核檔 ~/.doro/share_audit.log。"
        )
        a11y_hint.setObjectName("instructionLabel")
        a11y_hint.setWordWrap(True)
        layout.addWidget(a11y_hint)

        # Secondary opt-in: forward the *content* of input fields too.
        # Off by default — Doro sees that an input exists at (x, y) named
        # "網址列" without seeing what the user typed there.
        self._a11y_share_values_checkbox = QtWidgets.QCheckBox(
            "也把輸入框現在的內容傳給 AI（網址列、搜尋框、打到一半的文字；預設關閉）"
        )
        self._a11y_share_values_checkbox.setEnabled(False)
        layout.addWidget(self._a11y_share_values_checkbox)
        self._a11y_checkbox.toggled.connect(self._a11y_share_values_checkbox.setEnabled)

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
        st = self._cm.settings
        url = st.server_url
        model = st.model
        endpoint = st.endpoint_path
        max_stop = st.max_stop_tokens

        self._server_url_edit.setText(url)
        self._model_edit.setText(model)
        self._endpoint_edit.setText(endpoint)
        self._api_key_edit.setText(st.api_key)
        self._temperature_spin.setValue(st.temperature)
        self._timeout_spin.setValue(st.timeout_seconds)
        self._max_stop_spin.setValue(max_stop)

        tokens = st.stop_tokens
        display = "\n".join(t.replace("\n", "\\n") for t in tokens)
        self._stop_tokens_edit.setPlainText(display)

        a11y_enabled = self._core.config_manager.automation.a11y_enabled
        self._a11y_checkbox.setChecked(a11y_enabled)
        self._a11y_share_values_checkbox.setChecked(
            self._core.config_manager.automation.a11y_share_input_values
        )
        self._a11y_share_values_checkbox.setEnabled(a11y_enabled)

        # Detect which provider matches
        matched = "Custom"
        for name, preset in _PROVIDER_PRESETS.items():
            if (
                url == preset["server_url"]
                and model == preset["model"]
                and endpoint == preset["endpoint_path"]
                and max_stop == preset["max_stop_tokens"]
            ):
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
        st = self._cm.settings
        st.set_server_url(self._server_url_edit.text().strip())
        st.set_model(self._model_edit.text().strip())
        st.set_endpoint_path(self._endpoint_edit.text().strip())
        st.set_api_key(self._api_key_edit.text().strip())
        st.set_temperature(self._temperature_spin.value())
        st.set_timeout_seconds(self._timeout_spin.value())
        st.set_max_stop_tokens(self._max_stop_spin.value())

        tokens = [
            line.replace("\\n", "\n")
            for line in self._stop_tokens_edit.toPlainText().splitlines()
            if line.strip()
        ]
        st.set_stop_tokens(tokens)

        config = self._core.config_manager
        a11y_enabled = self._a11y_checkbox.isChecked()
        a11y_share_input_values = a11y_enabled and self._a11y_share_values_checkbox.isChecked()

        config.update_automation(
            a11y_enabled=a11y_enabled,
            a11y_share_input_values=a11y_share_input_values,
        )
        config.save()

        if a11y_enabled and self._core.a11y_service is not None:
            self._core.a11y_service.clear_session_blacklist()

        self.accept()
