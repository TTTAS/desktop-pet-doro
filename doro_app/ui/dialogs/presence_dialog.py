"""Pair a read-only extension and choose whether Doro reacts to page events."""

import secrets

from PySide6 import QtCore, QtWidgets

from doro_app.core.presence.controller import pairing_code


class PresenceDialog(QtWidgets.QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("分頁陪伴設定")
        self.resize(540, 390)
        self._controller = controller
        form = QtWidgets.QFormLayout(self)
        description = QtWidgets.QLabel(
            "分享目前有焦點的瀏覽器分頁，讓 Doro 理解內容。\n"
            "分頁文字會交給你設定的聊天模型；不分享輸入框內容，也不點擊網頁。\n"
            "載入 doro-presence 擴充後，按「複製配對碼」貼到擴充設定即可完成配對。"
        )
        description.setWordWrap(True)
        form.addRow(description)
        self.enabled = QtWidgets.QCheckBox("接收擴充分享的目前分頁")
        self.enabled.setChecked(bool(controller.settings["enabled"]))
        self.react = QtWidgets.QCheckBox("有值得回應的變化時，讓 Doro 主動說話與動作")
        self.react.setChecked(bool(controller.settings["react"]))
        self.port = QtWidgets.QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(controller.settings["port"]))
        self.token = QtWidgets.QLineEdit(controller.settings["token"])
        self.token.setReadOnly(True)
        self.token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        copy = QtWidgets.QPushButton("複製配對碼")
        copy.clicked.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(
                pairing_code(self.port.value(), self.token.text())
            )
        )
        rotate = QtWidgets.QPushButton("更換配對碼")
        rotate.clicked.connect(lambda: self.token.setText(secrets.token_urlsafe(32)))
        form.addRow(self.enabled)
        form.addRow(self.react)
        form.addRow("連線埠", self.port)
        form.addRow("配對碼", self.token)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(rotate)
        form.addRow(row)
        self.status = QtWidgets.QLabel(controller.status)
        self.status.setWordWrap(True)
        form.addRow(self.status)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(lambda: self.status.setText(controller.status))
        self._timer.start(1000)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save(self):
        try:
            self._controller.apply_settings(
                {
                    "enabled": self.enabled.isChecked(),
                    "react": self.react.isChecked(),
                    "port": self.port.value(),
                    "token": self.token.text(),
                }
            )
        except (ImportError, OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(
                self, "無法啟用", "請確認已安裝 doro 的 web 依賴，且埠號未被占用。\n" + str(exc)
            )
            return
        self.accept()
