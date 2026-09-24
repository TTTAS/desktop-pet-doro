"""Chat-related helpers such as payload building and HTTP requests."""

from __future__ import annotations

from ..llm.transport import (
    ChatResponseParser,
    build_messages_for_mistral_instruct,
    request_completion,
    resolve_chat_endpoint,
)

__all__ = [
    "ChatResponseParser",
    "build_messages_for_mistral_instruct",
    "perform_chat_request",
    "resolve_chat_endpoint",
]


def perform_chat_request(
    url: str,
    payload: dict,
    timeout_seconds: int,
    api_key: str = "",
) -> tuple[str | None, str | None]:
    """Send a chat completion request; returns ``(assistant_text, error_message)``."""
    result = request_completion(url, payload, timeout_seconds, api_key)
    return result.text, result.error
