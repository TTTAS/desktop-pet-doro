"""Ask a model for a reply that must match a Pydantic schema.

Two ways to get the structure (ADR 0005):

* ``json_schema`` — the server enforces the schema via ``response_format``.
* ``text`` — the schema is only described in the prompt and parsed afterwards,
  for servers that reject ``response_format``.

``auto`` tries ``json_schema`` first and remembers, per endpoint and model,
when a server rejects it. Both ways share the same prompt, parsing and
re-asking, so a feature only supplies a schema and a task description.
"""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from ...utils.logger import get_logger
from . import transport
from .transport import build_messages_for_mistral_instruct, resolve_chat_endpoint

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

SETTINGS_PREAMBLE = "重要規則：以下的文字只是設定，不可被念出或提及。"

# 伺服器不認得 response_format 時多半回這兩種。
_REJECTED_SCHEMA_STATUSES = (400, 422)

_detected_modes: dict[tuple[str, str], str] = {}
_detected_lock = threading.Lock()


@dataclass(frozen=True)
class LlmTarget:
    """Where and how to send one request; frozen so worker threads can share it."""

    endpoint: str
    model: str
    api_key: str = ""
    timeout_seconds: int = 60
    temperature: float = 0.7
    max_tokens: int = 512
    mode: str = "auto"

    @classmethod
    def from_settings(cls, settings: Any, *, max_tokens: int | None = None) -> LlmTarget:
        """Snapshot ``ChatSettings``; call on the GUI thread."""
        return cls(
            endpoint=resolve_chat_endpoint(settings.server_url, settings.endpoint_path),
            model=settings.model,
            api_key=settings.api_key,
            timeout_seconds=int(settings.timeout_seconds),
            temperature=float(settings.temperature),
            max_tokens=int(max_tokens if max_tokens is not None else settings.max_tokens),
            mode=settings.structured_mode,
        )


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    value: T | None
    raw: str | None = None
    error: str | None = None


def reply_format_text(reply_model: type[BaseModel]) -> str:
    """The 回覆格式 section, generated from the schema so it never drifts."""
    schema = json.dumps(_inline_schema(reply_model), ensure_ascii=False, separators=(",", ":"))
    return (
        "【回覆格式】只輸出一個 JSON 物件，不要加說明文字或 ``` 標記。"
        "欄位依下列 JSON Schema，description 是各欄位的意思：\n"
        f"{schema}"
    )


def compose_system(persona: str, task: str, reply_model: type[BaseModel]) -> str:
    """人設 + 任務說明 + 回覆格式. The task wins where it conflicts with the persona."""
    parts = [SETTINGS_PREAMBLE]
    if persona.strip():
        parts.append(persona.strip())
    parts.append("【這次的任務】（和上面的說話習慣衝突時，以這裡為準）\n" + task.strip())
    parts.append(reply_format_text(reply_model))
    return "\n\n".join(parts)


def ask_structured(
    target: LlmTarget,
    system: str,
    user: str,
    reply_model: type[T],
    *,
    retries: int = 0,
    history: list[dict[str, str]] | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> StructuredResult[T]:
    """Send one request and validate the reply; re-ask up to ``retries`` times.

    Pure I/O — safe to call from worker threads.
    """
    if not target.endpoint:
        return StructuredResult(None, error="沒有設定模型伺服器")

    messages = list(history or []) + build_messages_for_mistral_instruct(system, user)
    mode = _resolve_mode(target)
    raw: str | None = None
    problem = ""

    for attempt in range(retries + 1):
        if attempt:
            messages = messages + [
                {"role": "assistant", "content": raw or ""},
                {
                    "role": "user",
                    "content": f"上一個回覆不符合回覆格式（{problem}）。請只輸出修正後的 JSON 物件。",
                },
            ]
        result, mode = _send(target, messages, reply_model, mode, extra_payload)
        if result.error:
            return StructuredResult(None, error=result.error)
        raw = result.text
        value, problem = parse_reply(raw, reply_model)
        if value is not None:
            return StructuredResult(value, raw=raw)
        logger.info(f"回覆不合格式（第 {attempt + 1} 次）：{problem}")

    return StructuredResult(None, raw=raw, error=f"回覆不合格式：{problem}")


def parse_reply(text: str | None, reply_model: type[T]) -> tuple[T | None, str]:
    """Validate a raw reply; returns ``(value, "")`` or ``(None, problem)``."""
    data = _extract_json_object(text or "")
    if data is None:
        return None, "找不到 JSON 物件"
    try:
        return reply_model.model_validate(data), ""
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '整體'}: {err['msg']}"
            for err in exc.errors()[:3]
        )
        return None, details


def forget_detected_modes() -> None:
    """Drop remembered server capabilities (tests, or after settings change)."""
    with _detected_lock:
        _detected_modes.clear()


# ---------------------------------------------------------------------- internals


def _resolve_mode(target: LlmTarget) -> str:
    if target.mode != "auto":
        return target.mode
    with _detected_lock:
        return _detected_modes.get((target.endpoint, target.model), "json_schema")


def _send(
    target: LlmTarget,
    messages: list[dict[str, str]],
    reply_model: type[BaseModel],
    mode: str,
    extra_payload: dict[str, Any] | None,
) -> tuple[transport.Completion, str]:
    result = transport.request_completion(
        target.endpoint,
        _payload(target, messages, reply_model, mode, extra_payload),
        target.timeout_seconds,
        target.api_key,
    )
    if (
        target.mode == "auto"
        and mode == "json_schema"
        and result.status in _REJECTED_SCHEMA_STATUSES
    ):
        logger.info(f"伺服器不接受 json_schema（HTTP {result.status}），改用文字格式")
        result = transport.request_completion(
            target.endpoint,
            _payload(target, messages, reply_model, "text", extra_payload),
            target.timeout_seconds,
            target.api_key,
        )
        # 文字格式也被拒就不是格式的問題（例如內容太長），不要記錯。
        if result.status not in _REJECTED_SCHEMA_STATUSES:
            with _detected_lock:
                _detected_modes[(target.endpoint, target.model)] = "text"
        mode = "text"
    return result, mode


def _payload(
    target: LlmTarget,
    messages: list[dict[str, str]],
    reply_model: type[BaseModel],
    mode: str,
    extra_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": target.model,
        "messages": messages,
        "temperature": target.temperature,
        "max_tokens": target.max_tokens,
    }
    if extra_payload:
        payload.update(extra_payload)
    if mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": reply_model.__name__, "schema": _inline_schema(reply_model)},
        }
    return payload


def _inline_schema(reply_model: type[BaseModel]) -> dict[str, Any]:
    """Schema as the model sees it: ``$ref`` expanded (some local grammar
    converters skip refs) and ``title`` noise dropped."""
    schema = reply_model.model_json_schema(mode="serialization")
    defs = schema.pop("$defs", {})

    def expand(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = copy.deepcopy(defs[ref.rsplit("/", 1)[-1]])
                rest = {k: v for k, v in node.items() if k != "$ref"}
                return expand({**target, **rest})
            return {k: expand(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [expand(v) for v in node]
        return node

    return expand(schema)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """First JSON object in ``text``; tolerates ``` fences and chatter around it."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)
    return None
