"""Authenticated loopback WebSocket receiver. It has no browser command API."""

from __future__ import annotations

import hmac
import json
import re
import threading
import time
from http import HTTPStatus

from .models import PageEvent


class PresenceBridge:
    def __init__(self, extension_id: str, token: str, on_page, *, port: int = 19846):
        if not re.fullmatch(r"[a-p]{32}", extension_id):
            raise ValueError("擴充 ID 必須是 32 個 a-p 字元。")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
            raise ValueError("配對碼格式不正確，請重新產生。")
        self.origin = "chrome-extension://" + extension_id
        self._token = token
        self._on_page = on_page
        self.port = port
        self._server = None
        self._thread = None
        self._client = None
        self._lock = threading.Lock()
        self._page = None
        self._last_message = 0.0
        self._last_page = None
        self._last_page_time = 0.0

    def _authenticate(self, connection, request):
        protocols = [
            p.strip()
            for value in request.headers.get_all("Sec-WebSocket-Protocol")
            for p in value.split(",")
        ]
        origins = request.headers.get_all("Origin")
        authorized = any(hmac.compare_digest(p, "auth." + self._token) for p in protocols)
        if (
            request.path != "/presence"
            or origins != [self.origin]
            or "doro-v1" not in protocols
            or not authorized
        ):
            return connection.respond(HTTPStatus.FORBIDDEN, "Pairing rejected.\n")

    @property
    def current_page(self) -> PageEvent | None:
        with self._lock:
            if time.monotonic() - self._last_message > 45:
                return None
            return self._page

    def recent_page(self, max_age: float = 30.0) -> PageEvent | None:
        """The last shared page, still answerable for a short grace window.

        ``current_page`` goes None the instant the browser loses focus (the
        extension sends ``clear``), which happens whenever the user tabs to
        Doro to ask a question. This keeps that same one page for ``max_age``
        seconds so an explicit "what's on this page" question still works.
        It is only valid while the client stays connected: a disconnect or a
        new connection drops it. Still a single in-memory page, never stored.
        """
        with self._lock:
            if self._last_page is None or time.monotonic() - self._last_page_time >= max_age:
                return None
            return self._last_page

    def start(self) -> None:
        from websockets.sync.server import serve

        self._server = serve(
            self._handle,
            "127.0.0.1",
            self.port,
            origins=[self.origin],
            subprotocols=["doro-v1"],
            process_request=self._authenticate,
            max_size=65536,
            max_queue=2,
            compression=None,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=1,
        )
        self.port = self._server.socket.getsockname()[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="doro-presence"
        )
        self._thread.start()

    def _handle(self, websocket):
        from websockets.exceptions import ConnectionClosed

        with self._lock:
            previous, self._client = self._client, websocket
            self._page = None
            self._last_page = None  # a new connection carries no grace page
        if previous:
            previous.close()
        self._on_page(None)
        try:
            for raw in websocket:
                if not isinstance(raw, str):
                    websocket.close(1003, "Text messages only")
                    return
                try:
                    message = json.loads(raw)
                except ValueError:
                    websocket.close(1008, "Invalid event")
                    return
                if not isinstance(message, dict):
                    websocket.close(1008, "Invalid event")
                    return
                with self._lock:
                    if self._client is not websocket:
                        return
                    self._last_message = time.monotonic()
                if message.get("type") == "ping":
                    websocket.send('{"type":"pong"}')
                    continue
                page = PageEvent.from_message(message)
                with self._lock:
                    self._page = page
                    if page is not None:
                        self._last_page = page
                        self._last_page_time = time.monotonic()
                self._on_page(page)
        except ConnectionClosed:
            pass
        finally:
            with self._lock:
                is_current = self._client is websocket
                if is_current:
                    self._client = None
                    self._page = None
                    self._last_page = None  # disconnect drops the grace page
            if is_current:
                self._on_page(None)

    def shutdown(self) -> None:
        with self._lock:
            client, self._client = self._client, None
            self._page = None
            self._last_page = None
        if client:
            client.close()
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=2)
        self._on_page(None)
