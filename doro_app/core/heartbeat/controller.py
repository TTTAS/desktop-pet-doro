"""GUI-thread scheduler for the heartbeat and its one background model request.

Every few minutes Doro wakes up, looks at the time, recent chat, the user's
checklist and her own last heartbeats, and lets the model decide whether to
say something (``worth_saying``). The reply schema has no ``tool`` field, so
a heartbeat can only speak, change to a known state or take a short walk
(ADR 0004, ADR 0006).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore

from .context import (
    ChecklistUnreadable,
    HeartbeatContext,
    JournalEntry,
    append_journal,
    build_prompt,
    load_journal,
    read_checklist,
)
from .system_idle import system_idle_seconds

logger = logging.getLogger(__name__)

# The user is right here: no need for Doro to reach out on her own.
RECENT_INTERACTION_SECONDS = 90
# No keyboard/mouse input on the whole computer for this long: nobody to talk to.
AWAY_SECONDS = 600
# A scheduled beat blocked only by a short-lived activity (a walk, a menu) retries soon
# instead of waiting a whole interval.
BUSY_RETRY_SECONDS = 20
# A spoken reply waits for Doro to finish what she is doing, but not forever.
PENDING_TTL_SECONDS = 120
# A manual-beat notice ("skipped", "stayed silent", "no reply") also waits for the
# bubble to clear, but only briefly: late feedback about a click is just noise.
NOTICE_TTL_SECONDS = 15


class HeartbeatController(QtCore.QObject):
    result_ready = QtCore.Signal(int, object, bool, bool)  # epoch, answer, ok, manual

    def __init__(
        self,
        orchestrator,
        config,
        *,
        checklist_path: Path,
        journal_path: Path,
        busy: Callable[[], bool],
        quiet: Callable[[], bool],
        seconds_since_interaction: Callable[[], float],
        system_idle: Callable[[], float | None] = system_idle_seconds,
        page: Callable[[], object | None] = lambda: None,
        clock: Callable[[], datetime] = datetime.now,
        parent=None,
    ):
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._config = config
        self.checklist_path = checklist_path
        self._journal_path = journal_path
        self._busy = busy
        self._quiet = quiet
        self._since_interaction = seconds_since_interaction
        self._system_idle = system_idle
        # The currently shared page (anything with ``title``), or None.
        self._page = page
        self._clock = clock
        self._running = False
        self._closed = False
        self._epoch = 0
        self._pending = None  # (answer, epoch, page, deadline)
        self._notice = None  # (text, epoch, quiet_when_queued, deadline)
        self.last_status = "尚未跳過心跳"
        self.result_ready.connect(self._on_result, QtCore.Qt.ConnectionType.QueuedConnection)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._retry = QtCore.QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self._on_timer)
        # Only runs while a spoken reply or a notice waits for Doro to be free.
        self._pump_timer = QtCore.QTimer(self)
        self._pump_timer.setInterval(500)
        self._pump_timer.timeout.connect(self._pump)
        self.reschedule()

    # ------------------------------------------------------------------ public

    @property
    def enabled(self) -> bool:
        return bool(self._config.ui.heartbeat_enabled)

    @property
    def interval_ms(self) -> int:
        return int(self._config.ui.heartbeat_interval_minutes) * 60 * 1000

    @property
    def is_scheduled(self) -> bool:
        return self._timer.isActive()

    def reschedule(self) -> None:
        """Restart the cadence from now; call after the settings change."""
        self._timer.stop()
        self._retry.stop()
        if self._closed or not self.enabled:
            return
        self._timer.start(self.interval_ms)

    def interrupt(self) -> None:
        """The user started interacting: results asked for before now must not speak."""
        self._epoch += 1
        self._drop_pending()
        self._notice = None

    def skip_reason(self, *, manual: bool = False) -> str | None:
        """Why a heartbeat would not run right now, or ``None`` when it would.

        A manual beat skips the enabled / recent-interaction / away checks: the
        user just asked for it, so they are obviously here.
        """
        if self._closed:
            return "已關閉"
        if not manual and not self.enabled:
            return "心跳未開啟"
        if self._quiet():
            return "安靜陪伴中"
        if self._running or self._pending is not None:
            return "上一次心跳還沒結束"
        if self._busy():
            return "正在忙（聊天、拖曳、選單或動作中）"
        if manual:
            return None
        if self._since_interaction() < RECENT_INTERACTION_SECONDS:
            return "剛剛才互動過"
        idle = self._system_idle()
        if idle is not None and idle >= AWAY_SECONDS:
            return "使用者不在電腦前"
        return None

    def beat(self, *, manual: bool = False) -> str | None:
        """Run one heartbeat now; returns the skip reason, or ``None`` when started."""
        reason = self.skip_reason(manual=manual)
        if reason is not None:
            self.last_status = f"心跳跳過：{reason}"
            logger.info(self.last_status)
            return reason
        try:
            checklist = read_checklist(self.checklist_path)
        except ChecklistUnreadable as exc:
            reason = str(exc)
            self.last_status = f"心跳跳過：{reason}"
            logger.warning(self.last_status)
            return reason
        page = self._page()
        prompt = build_prompt(
            HeartbeatContext(
                now=self._clock(),
                seconds_since_interaction=self._since_interaction(),
                chat=self._orchestrator.recent_chat_lines(),
                checklist=checklist,
                journal=load_journal(self._journal_path),
                page_title=getattr(page, "title", None) if page is not None else None,
            )
        )
        try:
            ask = self._orchestrator.make_heartbeat_request(prompt)
        except Exception as exc:
            reason = "模型設定暫時無法使用"
            self.last_status = f"心跳跳過：{reason}"
            logger.warning("Heartbeat settings unavailable (%s)", type(exc).__name__)
            return reason
        epoch = self._epoch
        self._running = True
        self.last_status = "心跳中，等待模型回覆"
        logger.info("心跳開始（%s）", "手動" if manual else "排程")

        def run():
            answer, ok = None, False
            try:
                answer = ask()
                ok = answer is not None
            except Exception as exc:
                logger.warning("Heartbeat model unavailable (%s)", type(exc).__name__)
            if not self._closed:
                self.result_ready.emit(epoch, (answer, page), ok, manual)

        threading.Thread(target=run, daemon=True, name="doro-heartbeat-llm").start()
        return None

    def beat_now(self) -> None:
        """Menu entry: beat once and tell the user when nothing will happen."""
        reason = self.beat(manual=True)
        if reason is not None:
            self._notify(f"（心跳先跳過：{reason}）")

    def shutdown(self) -> None:
        self._closed = True
        self.interrupt()
        self._timer.stop()
        self._retry.stop()
        self._pump_timer.stop()

    # ------------------------------------------------------------------ internals

    def _on_timer(self) -> None:
        reason = self.beat()
        if reason is None:
            # A retried beat counts as this interval's beat: restart the cadence
            # so the regular tick does not follow right after it.
            self._retry.stop()
            self._timer.start(self.interval_ms)
        elif reason.startswith("正在忙") and not self._retry.isActive():
            self._retry.start(BUSY_RETRY_SECONDS * 1000)

    def _stale_reason(self, epoch: int, page) -> str | None:
        """Why a result asked for at ``epoch`` about ``page`` must not be shown now."""
        if self._closed:
            return "已關閉"
        if epoch != self._epoch:
            return "期間有互動"
        if self._quiet():
            return "已切到安靜陪伴"
        # A beat that saw no page may still speak when a page appears later; one
        # that saw page A must not talk about it once the user is elsewhere.
        if page is not None and self._page() != page:
            return "分頁已改變"
        return None

    @QtCore.Slot(int, object, bool, bool)
    def _on_result(self, epoch, result, ok, manual):
        self._running = False
        if self._closed:
            return
        answer, page = result
        # Check staleness before anything else: no failure or "stayed silent"
        # notice either, once the user cancelled or went quiet.
        stale = self._stale_reason(epoch, page)
        if stale is not None:
            self.last_status = f"心跳結果已過時（{stale}），不發言"
            return
        if not ok:
            self.last_status = "心跳沒有拿到可用的模型回覆"
            if manual:
                self._notify("（心跳沒有拿到模型回覆）")
            return
        # 開口判斷記進 log，方便日後檢查她怎麼決定。
        logger.info(
            "心跳判斷 worth_saying=%s state=%s line=%s",
            answer.worth_saying,
            answer.state,
            answer.line,
        )
        if not answer.worth_saying:
            self.last_status = "心跳完成：決定先不打擾"
            self._record("")
            if manual:
                self._notify("（Doro 想了想，決定先不打擾你）")
            return
        self._pending = (answer, epoch, page, time.monotonic() + PENDING_TTL_SECONDS)
        self._pump()

    def _notify(self, text: str) -> None:
        """Feedback for a manual beat; never covers a bubble that is still showing."""
        self._notice = (text, self._epoch, self._quiet(), time.monotonic() + NOTICE_TTL_SECONDS)
        self._pump()

    def _pump(self) -> None:
        self._pump_notice()
        self._pump_reply()
        if self._pending is None and self._notice is None:
            self._pump_timer.stop()
        elif not self._pump_timer.isActive():
            self._pump_timer.start()

    def _pump_notice(self) -> None:
        if self._notice is None:
            return
        text, epoch, was_quiet, deadline = self._notice
        # Unlike a reply, a notice may show in quiet mode when it was queued there
        # ("skipped: quiet"); turning quiet on afterwards still cancels it.
        if (
            self._closed
            or epoch != self._epoch
            or (self._quiet() and not was_quiet)
            or time.monotonic() > deadline
        ):
            logger.info("心跳提示未顯示（已過時或等太久）：%s", text)
            self._notice = None
            return
        if self._busy():
            return
        self._notice = None
        self._orchestrator.speak_line(text)

    def _pump_reply(self) -> None:
        if self._pending is None:
            return
        answer, epoch, page, deadline = self._pending
        stale = self._stale_reason(epoch, page)
        if stale is None and time.monotonic() > deadline:
            stale = "等太久"
        if stale is not None:
            self.last_status = f"心跳台詞已過時（{stale}），不發言"
            self._drop_pending()
            return
        if self._busy():
            return
        self._drop_pending()
        self._orchestrator.present_structured_reply(
            answer,
            should_present=lambda epoch=epoch, page=page: self._stale_reason(epoch, page) is None,
            on_present=self._on_spoken,
        )

    def _on_spoken(self, line: str) -> None:
        self.last_status = "心跳完成：Doro 主動說話了"
        self._record(line)

    def _drop_pending(self) -> None:
        self._pending = None
        if self._notice is None:
            self._pump_timer.stop()

    def _record(self, line: str) -> None:
        append_journal(
            self._journal_path,
            JournalEntry(self._clock().isoformat(timespec="seconds"), line),
        )
