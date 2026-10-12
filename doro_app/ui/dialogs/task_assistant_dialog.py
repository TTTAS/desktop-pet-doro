"""Visible task journal and explicitly managed memory (all UI work on Qt thread)."""

from PySide6 import QtCore, QtGui, QtWidgets


class TaskAssistantDialog(QtWidgets.QDialog):
    def __init__(self, orchestrator, parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self.store = orchestrator.task_store()
        self.setWindowTitle("Doro 任務與記憶")
        self.resize(760, 620)
        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "把要處理的檔案複製到專用工作目錄，再交代目標。寫檔與指令執行前會詢問。\n"
            "任務、工具結果與你主動保存的記憶會存於本機，並送往你設定的模型。\n"
            "關閉任務助理會停止執行及使用記憶，已存紀錄可在此刪除。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        folder = QtWidgets.QPushButton("開啟專用工作目錄")
        folder.clicked.connect(self._open_workspace)
        layout.addWidget(folder)
        self.goal = QtWidgets.QLineEdit()
        self.goal.setMaxLength(4000)
        self.goal.setPlaceholderText("例如：讀 notes.txt，整理成 todo.md，最後讀回檢查")
        layout.addWidget(self.goal)
        start = QtWidgets.QPushButton("開始新任務")
        start.clicked.connect(lambda: self._send("/任務 " + self.goal.text()))
        layout.addWidget(start)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)

        tasks = QtWidgets.QWidget()
        tasks_layout = QtWidgets.QVBoxLayout(tasks)
        self.task_list = QtWidgets.QComboBox()
        self.task_list.currentIndexChanged.connect(self._show_task)
        tasks_layout.addWidget(self.task_list)
        self.journal = QtWidgets.QPlainTextEdit()
        self.journal.setReadOnly(True)
        tasks_layout.addWidget(self.journal)
        buttons = QtWidgets.QHBoxLayout()
        for label, callback in (
            ("重新整理", self.refresh),
            ("接續選取任務", self._resume),
            ("刪除選取紀錄", self._delete_task),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        tasks_layout.addLayout(buttons)
        self.tabs.addTab(tasks, "任務紀錄")

        memories = QtWidgets.QWidget()
        memory_layout = QtWidgets.QVBoxLayout(memories)
        self.memory_list = QtWidgets.QListWidget()
        memory_layout.addWidget(self.memory_list)
        self.memory_text = QtWidgets.QLineEdit()
        self.memory_text.setMaxLength(500)
        self.memory_text.setPlaceholderText("只保存你希望 Doro 長期記住的資訊（最多 500 字）")
        memory_layout.addWidget(self.memory_text)
        remember = QtWidgets.QPushButton("記住")
        remember.clicked.connect(self._remember)
        memory_layout.addWidget(remember)
        forget = QtWidgets.QPushButton("忘記選取的記憶")
        forget.clicked.connect(self._forget)
        memory_layout.addWidget(forget)
        self.tabs.addTab(memories, "記憶")
        help_text = QtWidgets.QPlainTextEdit()
        help_text.setReadOnly(True)
        help_text.setPlainText(
            f"資料位置：{orchestrator.task_directory}\n\n"
            "聊天指令：\n/任務 目標\n/任務列表\n/任務紀錄 ID\n/繼續 ID\n/刪除任務 ID\n"
            "/記住 內容\n/記憶\n/忘記 ID\n\n"
            "任務進行時：輸入『停』取消；確認時回『好』執行，其他回答會停止。\n"
            "重啟後任務不會自動重播，接續時會帶入先前紀錄。刪除紀錄不會刪除產出檔案。\n"
            "忘記資訊不會清除先前聊天或任務中的副本；請另外清除聊天／刪除任務。\n\n"
            "工具：文字檔讀寫、目錄列表、搜尋、讀頁，以及另行啟用的網站操作。\n"
            "指令為可選功能：需先自行安裝 Docker，並執行 docker pull python:3.12-slim。\n"
            "指令容器無網路、僅掛載工作目錄、最多 60 秒；程式可修改整個工作目錄。\n"
            "不會自動下載映像，也不會退回主機 shell。Docker 必須連到這台電腦。\n"
            "目前沒有排程任務、MCP、自由桌面控制或任意主機檔案操作。"
        )
        self.tabs.addTab(help_text, "使用說明")
        self.refresh()

    def _error(self, exc):
        QtWidgets.QMessageBox.warning(self, "任務助理", str(exc))

    def _open_workspace(self):
        path = self.orchestrator.task_directory / "workspace"
        path.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def _send(self, text):
        if self.orchestrator.send_message(text, silent=True):
            self.accept()
        else:
            self._error(self.orchestrator.last_send_error)

    def refresh(self):
        selected = self.task_list.currentData()
        self.task_list.blockSignals(True)
        self.task_list.clear()
        for task in self.store.tasks():
            self.task_list.addItem(
                f"{task['id']} [{task['state']}] {task['goal'][:60]}", task["id"]
            )
        index = self.task_list.findData(selected)
        if index >= 0:
            self.task_list.setCurrentIndex(index)
        self.task_list.blockSignals(False)
        self._show_task()
        self.memory_list.clear()
        for memory in self.store.memories():
            item = QtWidgets.QListWidgetItem(memory["text"])
            item.setData(QtCore.Qt.ItemDataRole.UserRole, memory["id"])
            self.memory_list.addItem(item)

    def _show_task(self):
        task_id = self.task_list.currentData()
        if not task_id:
            self.journal.clear()
            return
        self.journal.setPlainText(self.store.report(task_id))

    def _resume(self):
        if task_id := self.task_list.currentData():
            self._send("/繼續 " + task_id)

    def _delete_task(self):
        if task_id := self.task_list.currentData():
            try:
                self.store.delete(task_id)
                self.refresh()
            except ValueError as exc:
                self._error(exc)

    def _remember(self):
        try:
            self.store.remember(self.memory_text.text())
            self.memory_text.clear()
            self.refresh()
        except ValueError as exc:
            self._error(exc)

    def _forget(self):
        if item := self.memory_list.currentItem():
            self.store.forget(item.data(QtCore.Qt.ItemDataRole.UserRole))
            self.refresh()
