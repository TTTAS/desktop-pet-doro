from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Tuple

from PySide6 import QtCore


def build_messages_for_mistral_instruct(system_prompt: str, user_text: str) -> list[dict]:
    """Fold system content into the first user message for Mistral instruct backends."""
    first_user = f"<<SYS>>\n{system_prompt.strip()}\n<</SYS>>\n\n{user_text.strip()}"
    return [{"role": "user", "content": first_user}]


def resolve_chat_endpoint(server_url: str, endpoint_path: str) -> str:
    base = (server_url or "").strip()
    if not base:
        return ""
    base = base.rstrip("/")
    path = (endpoint_path or "").strip() or "/v1/chat/completions"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


class ChatRequestWorker(QtCore.QObject):
    finished = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, url: str, payload: Dict, timeout_seconds: int):
        super().__init__()
        self._url = url
        self._payload = payload
        self._timeout_seconds = timeout_seconds

    @QtCore.Slot()
    def run(self):
        assistant_text, error_message = perform_chat_request(
            self._url,
            self._payload,
            int(self._timeout_seconds),
        )
        if error_message:
            self.error.emit(error_message)
            return
        if assistant_text is None:
            self.error.emit("No assistant response returned.")
            return
        self.finished.emit(assistant_text)

    @staticmethod
    def _extract_assistant_text(payload: dict) -> str | None:
        def _from_message_content(msg_obj: dict) -> str | None:
            content = msg_obj.get("content")
            if isinstance(content, str):
                return content.strip() or None
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text" and isinstance(item.get("text"), str):
                            parts.append(item["text"])
                        elif isinstance(item.get("content"), str):
                            parts.append(item["content"])
                joined = "\n".join(p.strip() for p in parts if p and p.strip())
                return joined or None
            return None

        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message") or {}
            if isinstance(message, dict):
                text = _from_message_content(message)
                if text:
                    return text
            if isinstance(first.get("text"), str) and first["text"].strip():
                return first["text"].strip()
            delta = first.get("delta") or {}
            if isinstance(delta, dict):
                dc = delta.get("content")
                if isinstance(dc, str) and dc.strip():
                    return dc.strip()
                if isinstance(dc, list):
                    parts = []
                    for item in dc:
                        if isinstance(item, dict):
                            if item.get("type") == "text" and isinstance(item.get("text"), str):
                                parts.append(item["text"])
                            elif isinstance(item.get("content"), str):
                                parts.append(item["content"])
                    joined = "\n".join(p.strip() for p in parts if p and p.strip())
                    if joined:
                        return joined
        if isinstance(payload.get("choices"), dict):
            maybe_text = payload["choices"].get("text")
            if isinstance(maybe_text, str) and maybe_text.strip():
                return maybe_text.strip()
        for key in ("content", "response", "message"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                text = _from_message_content(val)
                if text:
                    return text
        return None


def perform_chat_request(
    url: str,
    payload: Dict,
    timeout_seconds: int,
) -> Tuple[str | None, str | None]:
    try:
        request_bytes = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=request_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read()
            if body:
                decoded = body.decode("utf-8", errors="replace").strip()
                if decoded:
                    detail = decoded
        except Exception:
            pass
        reason = exc.reason or ""
        combined = reason
        if detail:
            snippet = detail if len(detail) <= 200 else f"{detail[:197]}..."
            combined = f"{reason} | {snippet}" if reason else snippet
        return None, f"HTTP error {exc.code}: {combined or 'Bad Request'}"
    except urllib.error.URLError as exc:
        return None, f"Network error: {exc.reason}"
    except Exception as exc:
        return None, str(exc)

    try:
        response_payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"Response decode error: {exc}"

    assistant_text = ChatRequestWorker._extract_assistant_text(response_payload)
    if assistant_text is None:
        return None, "No assistant response returned."
    return assistant_text, None


__all__ = [
    "ChatRequestWorker",
    "build_messages_for_mistral_instruct",
    "perform_chat_request",
    "resolve_chat_endpoint",
]
