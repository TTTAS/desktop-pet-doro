"""`ChatRetryPolicy` — the chat retry state machine (backlog #5, stage 2).

Retry logic used to be split across two files: the *decision*
(`should_retry` / `build_retry_prompt`) lived on `ResponseValidator`,
while the *counter*, the max-retry *gate*, the *delay*, and the *original
user message* lived on `ChatController`. A retry bug could hide in either
half — and one did: `ChatController._reset_worker_state()` zeroed the
counter and the original message before the next attempt, so the gate
never tripped (unbounded retries) and the retry prompt lost the user's
question.

Pulling all of it into one module gives retry logic a single home: the
counter, the limit, and the "should we retry / what do we send" decision
are now one testable unit, and the validator is left to do nothing but
validate.
"""

from __future__ import annotations

from typing import Optional

from .validator import ValidationResult


def _should_retry(result: ValidationResult) -> bool:
    """Whether a failed validation is worth another attempt.

    Retry on format failures (invalid states / directions). Do NOT retry
    an empty response — that's usually a model/transport error a re-ask
    won't fix.
    """
    if not result.valid:
        if result.error_message and "empty" not in result.error_message.lower():
            return True
    return False


def _build_retry_prompt(result: ValidationResult, original_message: str) -> str:
    """Compose the corrective re-ask: the user's original message plus a
    system note describing what was wrong last time."""
    error_detail = result.error_message or "Unknown error"
    return (
        f"{original_message}\n\n"
        f"[系統提示] 你上次的回應格式有誤: {error_detail}\n"
        f"請重新回答，確保使用正確的狀態和格式。"
    )


class ChatRetryPolicy:
    """Owns the retry counter, the limit, and the original user message.

    Usage from the controller:

    - ``remember_original(msg)`` on every ``start_request`` — it seeds the
      original only on the first (non-retry) call, so re-entering with a
      retry prompt does not clobber the real question.
    - ``next_retry(validation)`` on a validation failure — returns the
      retry prompt (and bumps the counter) when another attempt is
      warranted, or ``None`` when the failure isn't retryable or the limit
      is reached.
    - ``reset()`` at every terminal outcome (success, give-up, error,
      cancel) — but *not* between a retry and its follow-up request.
    """

    def __init__(self, max_retries: int) -> None:
        self._max_retries = int(max_retries)
        self._count = 0
        self._original_message = ""

    @property
    def attempt(self) -> int:
        """How many retries have been issued for the current request."""
        return self._count

    @property
    def max_retries(self) -> int:
        return self._max_retries

    def remember_original(self, message: str) -> None:
        """Record the user's original message, but only for the first
        attempt — later calls (re-entry with a retry prompt) are ignored so
        the real question survives across the whole retry chain."""
        if self._count == 0:
            self._original_message = message

    def next_retry(self, validation: ValidationResult) -> Optional[str]:
        """Return the next retry prompt, or ``None`` to stop.

        ``None`` means "don't retry": either the failure isn't retryable,
        or the max-retry gate has been reached. When a retry is warranted
        the counter is bumped and the corrective prompt (preserving the
        original message) is returned.
        """
        if not _should_retry(validation):
            return None
        if self._count >= self._max_retries:
            return None
        self._count += 1
        return _build_retry_prompt(validation, self._original_message)

    def reset(self) -> None:
        """Clear retry state for the next independent request."""
        self._count = 0
        self._original_message = ""
