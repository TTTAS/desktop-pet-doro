"""網頁執行緒管家：一條專屬執行緒 + 一個共用瀏覽器，讀與操作都排隊走它。

為什麼需要它（隔離規則的落實）：
- Playwright sync API 綁定建立它的執行緒，**整個瀏覽器從開到關必須在同一條執行緒**。
  所以這裡用一條專屬 ``threading.Thread`` 擁有唯一的 :class:`WebSession`，所有網頁工
  作（讀 / 操作）都丟進佇列、在這條執行緒上依序執行——天生就是「一次一個」（Q1 那把
  鎖）。
- **閒置 5 分鐘自動關**（Q10 甲）：佇列等太久沒工作就把瀏覽器收掉，下次用到再開。
- **確認橋接**（送出前問你、打字回覆）：操作執行緒要問使用者時，用 signal 通知主執行緒
  顯示、然後**卡住等**一個 Event；主執行緒收到你的「好/不要」再放行。逾時（預設 120 秒）
  當「不做」。
- 結果一律用 signal 送回主執行緒（Qt 會自動用 queued connection），不直接碰 UI。
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Callable

from PySide6 import QtCore

from ...utils.logger import get_logger
from .operator import DEFAULT_MAX_STEPS, WebOperator
from .reader import WebReadResult
from .session import WebSession

logger = get_logger(__name__)

_SHUTDOWN = object()  # 丟進佇列代表「收工、關執行緒」

DEFAULT_IDLE_CLOSE_SECONDS = 300  # 閒置多久自動關瀏覽器
DEFAULT_CONFIRM_TIMEOUT_SECONDS = 300  # 確認/等你處理牆 等多久沒回當「不做」（登入要時間）

AskLLM = Callable[[str], str]


class WebRuntime(QtCore.QObject):
    """擁有共用瀏覽器的專屬執行緒；讀與操作都排隊走它。"""

    # → 主執行緒
    read_finished = QtCore.Signal(str, object)  # (request_id, WebReadResult)
    op_progress = QtCore.Signal(str)            # 操作過程/結果要顯示的話
    op_confirm = QtCore.Signal(str)             # 要使用者確認（完整泡泡文字）
    op_finished = QtCore.Signal()               # 一次操作結束（成功/中止/出錯）
    login_done = QtCore.Signal(str, bool, str)  # (request_id, ok, message) 開站給使用者登入
    verify_progress = QtCore.Signal(str)        # 查證過程的狀態一句話
    verify_finished = QtCore.Signal(str, str)   # (request_id, final_answer) 查證結束

    def __init__(
        self,
        user_data_dir: Path,
        *,
        headless: bool = False,
        idle_close_seconds: int = DEFAULT_IDLE_CLOSE_SECONDS,
        confirm_timeout_seconds: int = DEFAULT_CONFIRM_TIMEOUT_SECONDS,
        max_steps: int = DEFAULT_MAX_STEPS,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._user_data_dir = Path(user_data_dir)
        self._headless = bool(headless)
        self._idle_close_seconds = int(idle_close_seconds)
        self._confirm_timeout_seconds = int(confirm_timeout_seconds)
        self._max_steps = int(max_steps)

        self._queue: "queue.Queue" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._session: WebSession | None = None  # 只在專屬執行緒上碰

        self._confirm_event = threading.Event()
        self._confirm_result = False
        self._cancel = threading.Event()
        # 「開站給使用者登入」後，先別讓閒置計時把瀏覽器關掉（登入可能要好幾分鐘）。
        self._hold_open = False

    # ------------------------------------------------------------------ 生命週期

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="doro-web", daemon=True)
        self._thread.start()
        logger.info("WebRuntime 專屬執行緒已啟動")

    def shutdown(self) -> None:
        """收工：請執行緒關掉瀏覽器並結束。"""
        self._cancel.set()
        self._confirm_event.set()
        self._queue.put(_SHUTDOWN)

    # ------------------------------------------------------------------ 主執行緒呼叫

    def submit_read(self, request_id: str, url: str) -> None:
        self._queue.put(lambda: self._do_read(request_id, url))

    def submit_read_current(self, request_id: str) -> None:
        """讀「目前開著的那頁」（doro 剛剛操作/讀過、還開著的頁），不重新導航。"""
        self._queue.put(lambda: self._do_read_current(request_id))

    def submit_login(self, request_id: str, url: str) -> None:
        """開一個網站、停在那讓使用者本人登入（不操作），並保持開著不自動關。"""
        self._queue.put(lambda: self._do_login(request_id, url))

    def submit_operation(self, goal: str, ask_llm: AskLLM) -> None:
        self._cancel.clear()
        self._queue.put(lambda: self._do_operation(goal, ask_llm))

    def submit_verify(self, request_id: str, query: str, ask_llm: AskLLM) -> None:
        self._queue.put(lambda: self._do_verify(request_id, query, ask_llm))

    def provide_confirm(self, yes: bool) -> None:
        """使用者回覆確認（主執行緒呼叫），放行卡住的操作執行緒。"""
        self._confirm_result = bool(yes)
        self._confirm_event.set()

    def request_cancel(self) -> None:
        """中止進行中的操作（主執行緒呼叫）。"""
        self._cancel.set()
        # 若正卡在等確認，順手當「不做」放行，讓它盡快收尾。
        self._confirm_result = False
        self._confirm_event.set()

    # ------------------------------------------------------------------ 專屬執行緒內部

    def _run_loop(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=self._idle_close_seconds)
            except queue.Empty:
                if not self._hold_open:
                    self._close_session()  # 閒置太久 → 關瀏覽器
                continue
            if job is _SHUTDOWN:
                self._close_session()
                logger.info("WebRuntime 執行緒收工")
                return
            try:
                job()
            except Exception as exc:
                logger.error(f"WebRuntime 工作出錯：{exc}", exc_info=True)

    def _get_session(self) -> WebSession:
        if self._session is None:
            self._session = WebSession(self._user_data_dir, headless=self._headless)
        return self._session

    def _close_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
            logger.info("WebRuntime 已關閉共用瀏覽器")

    def _do_read(self, request_id: str, url: str) -> None:
        session = self._get_session()
        err = session.ensure_open()
        if err:
            self.read_finished.emit(request_id, WebReadResult(url=url, title="", text="", error=err))
            return
        goto_err = session.goto(url)
        if goto_err:
            self.read_finished.emit(request_id, WebReadResult(url=url, title="", text="", error=goto_err))
            return
        view = session.snapshot()
        if not view.ok:
            self.read_finished.emit(request_id, WebReadResult(url=url, title="", text="", error=view.error))
            return
        if not view.text:
            self.read_finished.emit(
                request_id,
                WebReadResult(url=view.url, title=view.title, text="",
                              error="這頁 doro 讀不到內容（可能需要登入、或整頁都是圖片/影片）。"),
            )
            return
        self.read_finished.emit(
            request_id, WebReadResult(url=view.url, title=view.title, text=view.text, error=None)
        )

    def _do_read_current(self, request_id: str) -> None:
        # 不開新頁：讀目前 session 開著的那頁。沒有開著的頁就回友善錯誤。
        if self._session is None or not self._session.is_open:
            self.read_finished.emit(
                request_id,
                WebReadResult(url="", title="", text="",
                              error="doro 現在沒有開著的網頁耶～先叫我讀某個網址、或操作一次，我才有頁可以讀喔。"),
            )
            return
        view = self._session.snapshot()
        if not view.ok:
            self.read_finished.emit(request_id, WebReadResult(url="", title="", text="", error=view.error))
            return
        if not view.text:
            self.read_finished.emit(
                request_id,
                WebReadResult(url=view.url, title=view.title, text="",
                              error="這頁 doro 讀不到內容（可能還在載入、需要登入、或整頁都是圖片/影片）。"),
            )
            return
        self.read_finished.emit(
            request_id, WebReadResult(url=view.url, title=view.title, text=view.text, error=None)
        )

    def _do_login(self, request_id: str, url: str) -> None:
        session = self._get_session()
        open_err = session.ensure_open()
        if open_err:
            self.login_done.emit(request_id, False, open_err)
            return
        goto_err = session.goto(url)
        if goto_err:
            self.login_done.emit(request_id, False, goto_err)
            return
        # 保持開著，別讓閒置計時關掉，好讓使用者慢慢登入。
        self._hold_open = True
        self.login_done.emit(request_id, True, url)

    def _do_verify(self, request_id: str, query: str, ask_llm: AskLLM) -> None:
        from .verify import VerifyPipeline
        self._hold_open = False
        session = self._get_session()
        final_holder = {"text": ""}
        pipeline = VerifyPipeline(
            session,
            ask_llm,
            self.verify_progress.emit,
            lambda text: final_holder.__setitem__("text", text),
        )
        try:
            pipeline.run(query)
        finally:
            self.verify_finished.emit(request_id, final_holder["text"])

    def _do_operation(self, goal: str, ask_llm: AskLLM) -> None:
        self._hold_open = False  # 開始正常操作 → 恢復閒置自動關
        session = self._get_session()
        operator = WebOperator(
            session,
            ask_llm,
            self._confirm_bridge,
            self.op_progress.emit,
            max_steps=self._max_steps,
            should_cancel=self._cancel.is_set,
        )
        try:
            operator.run(goal)
        finally:
            self.op_finished.emit()

    def _confirm_bridge(self, description: str) -> bool:
        """在操作執行緒上呼叫：問主執行緒、卡住等回覆（或逾時當不做）。"""
        if self._cancel.is_set():
            return False
        self._confirm_event.clear()
        self._confirm_result = False
        self.op_confirm.emit(description)
        got = self._confirm_event.wait(self._confirm_timeout_seconds)
        if not got:
            logger.info("確認逾時，當作不做")
            return False
        return self._confirm_result
