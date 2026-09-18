"""GUI-thread coordinator for page events and one background model request."""

from __future__ import annotations

import json
import logging
import secrets
import threading
from pathlib import Path

from PySide6 import QtCore

from .bridge import PresenceBridge
from .models import EventGate, PageEvent

logger = logging.getLogger(__name__)

# The extension ships a fixed public key in its manifest, so its ID is the same
# on every machine. Knowing it here means the user never copies an ID: they only
# paste one pairing code into the extension. (A Web Store build gets a different
# store-assigned ID; update this constant then.)
EXTENSION_ID = "bjdgpompkkahbkmhekmddobhlmjjgipo"


def pairing_code(port: int, token: str) -> str:
    """One string the user copies into the extension, bundling port + token.

    Format ``doro1.<port>.<token>``. The token charset is ``[A-Za-z0-9_-]`` and
    the port is digits, so a simple dot split is unambiguous. The extension's
    options page parses the same shape.
    """
    return f"doro1.{int(port)}.{token}"


class PresenceController(QtCore.QObject):
    page_received = QtCore.Signal(object)
    result_ready = QtCore.Signal(object, int, str, bool)

    def __init__(self, orchestrator, settings_path: Path, busy, parent=None):
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._path = settings_path
        self._busy = busy
        self._bridge = None
        self._gate = EventGate()
        self._running = False
        self._closed = False
        self._epoch = 0
        self._last_reaction = ""
        self._completed = None
        self._observed_page = None
        self.status = "尚未配對"
        self.settings = {
            "enabled": False,
            "react": False,
            "port": 19846,
            "token": secrets.token_urlsafe(32),
        }
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.settings.update({k: data[k] for k in self.settings if k in data})
        except (OSError, ValueError):
            pass
        self.page_received.connect(self._on_page, QtCore.Qt.ConnectionType.QueuedConnection)
        self.result_ready.connect(self._on_result, QtCore.Qt.ConnectionType.QueuedConnection)
        # Queue pump only: it never requests a model without a new page event.
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._pump)
        self._timer.start()
        if self.settings["enabled"]:
            try:
                self._start_bridge()
            except (ImportError, OSError, ValueError) as exc:
                self.status = f"分頁連線未啟動：{type(exc).__name__}，請開啟分頁陪伴設定。"

    def _start_bridge(self):
        bridge = PresenceBridge(
            EXTENSION_ID,
            self.settings["token"],
            self.page_received.emit,
            port=int(self.settings["port"]),
        )
        bridge.start()
        self._bridge = bridge
        self.status = "等待擴充連線"

    def apply_settings(self, settings: dict) -> None:
        candidate = dict(self.settings, **settings)
        if type(candidate["port"]) is not int or not 1024 <= candidate["port"] <= 65535:
            raise ValueError("埠號請填 1024～65535。")
        if candidate["enabled"]:
            PresenceBridge(EXTENSION_ID, candidate["token"], lambda _: None)
        previous = dict(self.settings)
        if self._bridge:
            self._bridge.shutdown()
            self._bridge = None
        self.interrupt()
        self._gate = EventGate()
        self.settings = candidate
        try:
            if candidate["enabled"]:
                self._start_bridge()
            else:
                self.status = "已停用分頁分享"
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self._path)
        except Exception:
            if self._bridge:
                self._bridge.shutdown()
                self._bridge = None
            self.settings = previous
            self.status = "設定未套用，請檢查埠號與配對資料"
            if previous["enabled"]:
                try:
                    self._start_bridge()
                except (ImportError, OSError, ValueError):
                    pass
            raise

    @property
    def current_page(self) -> PageEvent | None:
        return self._bridge.current_page if self._bridge else None

    def interrupt(self) -> None:
        self._epoch += 1
        self._completed = None

    @QtCore.Slot(object)
    def _on_page(self, page):
        if self._closed:
            return
        # Receive events from the bridge but use its current authoritative page;
        # queued events from a disconnected/replaced client cannot restore it.
        current = self.current_page
        if page is not None and page != current:
            return
        if current != self._observed_page:
            self._observed_page = current
            self.interrupt()
        self.status = "已連線，正在讀取目前分頁" if current else "沒有可分享的目前分頁"
        self._gate.offer(current if self.settings["react"] else None)
        self._pump()

    def _pump(self) -> None:
        if self._closed or self._running or not self.settings["react"] or self._busy():
            return
        if self._completed is not None:
            event, epoch, answer = self._completed
            self._completed = None
            if epoch == self._epoch and event == self.current_page:
                self._orchestrator.present_character_reply(
                    answer,
                    should_present=lambda event=event, epoch=epoch: (
                        not self._closed and self.settings["react"]
                        and epoch == self._epoch and event == self.current_page
                    ),
                    on_present=self._remember_reaction,
                )
        pending = self._gate.pending
        if pending is None:
            return
        if pending != self.current_page:
            self._gate.offer(None)
            return
        event = self._gate.take()
        try:
            ask = self._orchestrator.make_presence_request(event, self._last_reaction)
        except Exception as exc:  # noqa: BLE001 - isolate optional context model failures
            self._gate.finish(False)
            logger.warning("Presence settings unavailable (%s)", type(exc).__name__)
            self.status = "模型設定暫時無法使用，基本陪伴繼續"
            return
        epoch = self._epoch
        self._running = True

        def run():
            answer, ok = "", False
            try:
                answer = ask() or ""
                ok = bool(answer.strip())
            except Exception as exc:  # noqa: BLE001 - keep basic companion alive
                # Exception messages/tracebacks can contain page or credential data.
                logger.warning("Presence model unavailable (%s)", type(exc).__name__)
            if not self._closed:
                self.result_ready.emit(event, epoch, answer, ok)

        threading.Thread(target=run, daemon=True, name="doro-presence-llm").start()

    def _remember_reaction(self, text: str) -> None:
        # Only spoken replies should suppress a later, similar reaction.
        self._last_reaction = text

    @QtCore.Slot(object, int, str, bool)
    def _on_result(self, event, epoch, answer, ok):
        self._running = False
        if self._closed:
            return
        self._gate.finish(ok)
        if not ok:
            self.status = "模型暫時無回應，基本陪伴繼續；下一個頁面事件再試"
        elif epoch == self._epoch and event == self.current_page:
            self.status = "分頁陪伴運作中"
            if answer.strip() != "[SILENT]":
                self._completed = (event, epoch, answer)
        self._pump()

    def shutdown(self):
        self._closed = True
        self.interrupt()
        self._timer.stop()
        if self._bridge:
            self._bridge.shutdown()
            self._bridge = None
