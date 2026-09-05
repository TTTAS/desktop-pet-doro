"""Chat-related helpers such as payload building and HTTP requests."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ...utils.logger import get_logger

logger = get_logger(__name__)

# 設 DORO_WEB_DEBUG=1 就把每一次 LLM 的原始回傳（含錯誤）印到終端機，方便除錯——
# 涵蓋一般聊天、讀網頁、查證、操作所有 LLM 呼叫（都經過 perform_chat_request）。
_DEBUG = os.environ.get("DORO_WEB_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def _dbg_llm(header: str, body: str) -> None:
    if _DEBUG:
        print(f"\n===== [doro LLM] {header} =====", flush=True)
        print((body or "")[:3000], flush=True)
        print("=" * 40 + "\n", flush=True)


def build_messages_for_mistral_instruct(system_prompt: str, user_text: str) -> list[dict]:
    """Fold system content into first user message for Mistral instruct-compatible backends."""
    first_user = f"<<SYS>>\n{system_prompt.strip()}\n<</SYS>>\n\n{user_text.strip()}"
    return [
        {"role": "user", "content": first_user}
    ]


def resolve_chat_endpoint(server_url: str, endpoint_path: str) -> str:
    base = (server_url or "").strip()
    if not base:
        return ""
    base = base.rstrip("/")
    path = (endpoint_path or "").strip() or "/v1/chat/completions"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def perform_chat_request(
    url: str,
    payload: dict,
    timeout_seconds: int,
    api_key: str = "",
) -> tuple[str | None, str | None]:
    """
    Perform a chat completion request to the LLM server.

    Args:
        url: Full endpoint URL (e.g., http://localhost:1234/v1/chat/completions)
        payload: JSON payload with model, messages, etc.
        timeout_seconds: Request timeout in seconds

    Returns:
        Tuple of (assistant_text, error_message). On success, returns (text, None).
        On failure, returns (None, error_message).

    Raises:
        None - All errors are caught and returned as error messages
    """
    logger.debug(f"Sending chat request to {url}")

    try:
        request_bytes = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            url,
            data=request_bytes,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            logger.debug(f"Received response: {len(raw)} bytes")
        _dbg_llm("原始回傳", raw.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read()
            if body:
                decoded = body.decode("utf-8", errors="replace").strip()
                if decoded:
                    detail = decoded
        except (OSError, AttributeError) as read_exc:
            # OSError: Network issues reading error body
            # AttributeError: exc.read() not available (shouldn't happen but defensive)
            logger.debug(f"Could not read HTTP error body: {read_exc}")
        reason = exc.reason or ""
        combined = reason
        if detail:
            snippet = detail if len(detail) <= 200 else f"{detail[:197]}..."
            combined = f"{reason} | {snippet}" if reason else snippet
        error_msg = f"HTTP error {exc.code}: {combined or 'Bad Request'}"
        logger.error(f"Chat request failed: {error_msg} (URL: {url})")
        return None, error_msg
    except urllib.error.URLError as exc:
        error_msg = f"Network error: {exc.reason}"
        logger.error(f"Chat request failed: {error_msg} (URL: {url})")
        return None, error_msg
    except (OSError, ValueError, TimeoutError) as exc:
        # OSError: Socket/connection errors not wrapped by URLError
        # ValueError: Invalid URL or request parameters
        # TimeoutError: Request timeout (rare, usually wrapped by URLError)
        error_msg = f"Request error: {exc}"
        logger.error(f"Chat request failed: {error_msg} (URL: {url})", exc_info=True)
        return None, error_msg

    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        logger.debug("Successfully parsed JSON response")
    except json.JSONDecodeError as exc:
        error_msg = f"Invalid JSON response: {exc}"
        logger.error(f"Failed to parse chat response: {error_msg}")
        return None, error_msg

    assistant_text = ChatResponseParser.extract_assistant_text(payload)
    if assistant_text:
        logger.info(f"Chat request successful, response length: {len(assistant_text)}")
        _dbg_llm("抽出的文字", assistant_text)
    else:
        logger.warning("Chat request returned no assistant text")
        _dbg_llm("抽不出文字！（上面原始回傳裡沒有可用的 content，可能被 stop token 切掉或模型回空）", "")
    return assistant_text, None


class ChatResponseParser:
    """Parse text out of heterogeneous chat completion payloads."""

    @staticmethod
    def extract_assistant_text(payload: dict) -> str | None:
        """Best-effort extraction of assistant text from assorted response schemas."""

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
                delta_content = delta.get("content")
                if isinstance(delta_content, str) and delta_content.strip():
                    return delta_content.strip()
                if isinstance(delta_content, list):
                    parts = []
                    for item in delta_content:
                        if isinstance(item, dict):
                            if item.get("type") == "text" and isinstance(item.get("text"), str):
                                parts.append(item["text"])
                            elif isinstance(item.get("content"), str):
                                parts.append(item["content"])
                    joined = "\n".join(p.strip() for p in parts if p and p.strip())
                    if joined:
                        return joined

        for key in ("content", "response", "message"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                text = _from_message_content(val)
                if text:
                    return text
        return None
