"""網頁執行緒管家：一條專屬執行緒 + 一個共用瀏覽器，讀與操作都排隊走它。"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6 import QtCore

from ...utils.logger import get_logger
from .operator import DEFAULT_MAX_STEPS, WebOperator
from .reader import WebReadResult
from .session import WebSession

logger = get_logger(__name__)

_SHUTDOWN = object()

DEFAULT_IDLE_CLOSE_SECONDS = 300
DEFAULT_CONFIRM_TIMEOUT_SECONDS = 300

# 驗證過的回覆或 None（ADR 0005）：操作拿 WebStep，查證拿角色回覆。
AskLLM = Callable[[str], object]


class WebRuntime(QtCore.QObject):
    read_finished = QtCore.Signal(str, object)
    op_progress = QtCore.Signal(str)
    op_reply = QtCore.Signal(str)
    op_confirm = QtCore.Signal(str)
    op_finished = QtCore.Signal()
    login_done = QtCore.Signal(str, bool, str)
    verify_progress = QtCore.Signal(str)
    verify_finished = QtCore.Signal(str, object)  # request_id, 字串或角色回覆

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

        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._session: WebSession | None = None

        self._confirm_event = threading.Event()
        self._confirm_result = False
        self._cancel = threading.Event()
        self._hold_open = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="doro-web", daemon=True)
        self._thread.start()
        logger.info("WebRuntime 專屬執行緒已啟動")

    def shutdown(self) -> None:
        self._cancel.set()
        self._confirm_event.set()
        self._queue.put(_SHUTDOWN)
        # A daemon worker must get time to remove an active command container
        # before the Qt application exits. A pending LLM cannot act after cancel.
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=30)

    def submit_read(self, request_id: str, url: str) -> None:
        self._queue.put(lambda: self._do_read(request_id, url))

    def submit_read_current(self, request_id: str) -> None:
        self._queue.put(lambda: self._do_read_current(request_id))

    def submit_login(self, request_id: str, url: str) -> None:
        self._queue.put(lambda: self._do_login(request_id, url))

    def submit_operation(self, goal: str, ask_llm: AskLLM) -> None:
        self._cancel.clear()
        self._queue.put(lambda: self._do_operation(goal, ask_llm))

    def submit_task(
        self, task_id, store, workspace, ask_llm, *, ask_web=None, search_provider=None
    ):
        """Local and web tools share one queue; browser objects never cross threads."""
        self._cancel.clear()
        self._queue.put(
            lambda: self._do_task(task_id, store, workspace, ask_llm, ask_web, search_provider)
        )

    def _do_task(self, task_id, store, workspace, ask_llm, ask_web, search_provider):
        from ..agent.engine import TaskRunner
        from ..agent.tools import Workspace, local_tools
        from ..agent.web_tools import add_web_tools

        try:
            registry = local_tools(Workspace(workspace), self._cancel.is_set)
            add_web_tools(
                registry,
                self._get_session,
                search_provider,
                ask_web,
                self._confirm_bridge,
                self.op_progress.emit,
                self._cancel.is_set,
            )
            TaskRunner(
                store,
                registry,
                ask_llm,
                self._confirm_bridge,
                self.op_progress.emit,
                self._cancel.is_set,
            ).run(task_id)
        except Exception:
            store.update(task_id, "failed", "任務無法啟動，請檢查工作目錄與設定。")
            self.op_progress.emit("任務無法啟動，進度已保留。")
        finally:
            self.op_finished.emit()

    def submit_verify(self, request_id: str, query: str, ask_llm: AskLLM, search_provider) -> None:
        self._queue.put(lambda: self._do_verify(request_id, query, ask_llm, search_provider))

    def provide_confirm(self, yes: bool) -> None:
        self._confirm_result = bool(yes)
        self._confirm_event.set()

    def request_cancel(self) -> None:
        self._cancel.set()
        self._confirm_result = False
        self._confirm_event.set()

    def _run_loop(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=self._idle_close_seconds)
            except queue.Empty:
                if not self._hold_open:
                    self._close_session()
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
            self.read_finished.emit(
                request_id, WebReadResult(url=url, title="", text="", error=err)
            )
            return
        goto_err = session.goto(url)
        if goto_err:
            self.read_finished.emit(
                request_id, WebReadResult(url=url, title="", text="", error=goto_err)
            )
            return
        view = session.snapshot()
        if not view.ok:
            self.read_finished.emit(
                request_id, WebReadResult(url=url, title="", text="", error=view.error)
            )
            return
        if not view.text:
            self.read_finished.emit(
                request_id,
                WebReadResult(
                    url=view.url,
                    title=view.title,
                    text="",
                    error="這頁 doro 讀不到內容（可能需要登入、或整頁都是圖片/影片）。",
                ),
            )
            return
        self.read_finished.emit(
            request_id, WebReadResult(url=view.url, title=view.title, text=view.text, error=None)
        )

    def _do_read_current(self, request_id: str) -> None:
        if self._session is None or not self._session.is_open:
            self.read_finished.emit(
                request_id,
                WebReadResult(
                    url="",
                    title="",
                    text="",
                    error="doro 現在沒有開著的網頁耶～先叫我讀某個網址、或操作一次，我才有頁可以讀喔。",
                ),
            )
            return
        views = []
        snap_all = getattr(self._session, "snapshot_open_pages", None)
        if callable(snap_all):
            try:
                views = list(snap_all(wait_idle=False) or [])
            except TypeError:
                views = list(snap_all() or [])
        if not views:
            views = [self._session.snapshot()]
        chunks: list[str] = []
        urls: list[str] = []
        titles: list[str] = []
        for i, view in enumerate(views, 1):
            if not getattr(view, "ok", False):
                continue
            body = (getattr(view, "text", None) or "").strip()
            if not body:
                continue
            url = getattr(view, "url", "") or ""
            title = getattr(view, "title", "") or ""
            urls.append(url)
            titles.append(title)
            chunks.append(f"【分頁{i}】{title or '(無標題)'}\n網址：{url}\n{body}")
        if not chunks:
            self.read_finished.emit(
                request_id,
                WebReadResult(
                    url="",
                    title="",
                    text="",
                    error="開著的分頁 doro 都讀不到內容（可能還在載入、要登入、或整頁都是圖片/影片）。",
                ),
            )
            return
        print(f"[doro web] read current: {len(chunks)} tab(s)", flush=True)
        self.read_finished.emit(
            request_id,
            WebReadResult(
                url=" | ".join(urls),
                title="、".join(t for t in titles if t) or f"{len(chunks)} 個分頁",
                text="\n\n".join(chunks),
                error=None,
            ),
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
        self._hold_open = True
        self.login_done.emit(request_id, True, url)

    def _do_verify(self, request_id: str, query: str, ask_llm: AskLLM, search_provider) -> None:
        from .verify import VerifyPipeline

        self._hold_open = False
        final_holder = {"text": ""}
        pipeline = VerifyPipeline(
            search_provider,
            self._get_session,
            ask_llm,
            self.verify_progress.emit,
            lambda text: final_holder.__setitem__("text", text),
        )
        try:
            pipeline.run(query)
        finally:
            self.verify_finished.emit(request_id, final_holder["text"])
            if pipeline.keep_browser:
                pass
            else:
                self._close_session()

    def _do_operation(self, goal: str, ask_llm: AskLLM) -> None:
        self._hold_open = False
        session = self._get_session()
        operator = WebOperator(
            session,
            ask_llm,
            self._confirm_bridge,
            self.op_progress.emit,
            max_steps=self._max_steps,
            should_cancel=self._cancel.is_set,
            emit_reply=self.op_reply.emit,
        )
        try:
            operator.run(goal)
        except Exception:
            logger.warning("網頁操作發生未預期錯誤，停止任務")
            self.op_progress.emit("操作遇到未預期的錯誤，doro已停下來，請重新交代任務。")
        finally:
            self.op_finished.emit()

    def _confirm_bridge(self, description: str) -> bool:
        if self._cancel.is_set():
            return False
        self._confirm_event.clear()
        self._confirm_result = False
        if self._cancel.is_set():
            return False
        self.op_confirm.emit(description)
        got = self._confirm_event.wait(self._confirm_timeout_seconds)
        if not got:
            logger.info("確認逾時，當作不做")
            return False
        return self._confirm_result and not self._cancel.is_set()
