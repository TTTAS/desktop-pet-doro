"""Tests for `ChatRetryPolicy` — the retry state machine extracted from
`ChatController` (backlog #5, stage 2).

Before this extraction the retry counter, the max-retry gate, the delay,
and the "original user message" all lived in the controller while the
retry *decision* (`should_retry`) lived in the validator. Retry logic
had no single home, and a real bug hid in the split: the controller's
`_reset_worker_state()` zeroed the counter and the original message
*before* the next attempt, so the max-retry gate never tripped (unbounded
retries) and the retry prompt dropped the user's original question.

These tests pin the fixed behaviour on the one module that now owns it.
"""

from __future__ import annotations

from doro_app.core.chat.retry import ChatRetryPolicy
from doro_app.core.chat.validator import ValidationResult


def _invalid(msg: str = "Invalid movement direction(s): foo") -> ValidationResult:
    return ValidationResult.failure(msg)


class TestRetryDecision:
    def test_retries_a_retryable_failure(self):
        policy = ChatRetryPolicy(max_retries=3)
        prompt = policy.next_retry(_invalid())
        assert prompt is not None
        assert policy.attempt == 1

    def test_does_not_retry_empty_response(self):
        policy = ChatRetryPolicy(max_retries=3)
        assert policy.next_retry(ValidationResult.failure("Response is empty")) is None
        assert policy.attempt == 0

    def test_does_not_retry_valid_result(self):
        policy = ChatRetryPolicy(max_retries=3)
        assert policy.next_retry(ValidationResult.success()) is None


class TestMaxRetryGate:
    def test_stops_after_max_retries(self):
        """The bug: the counter used to reset every attempt, so this gate
        never tripped and retries were unbounded. It must stop after N."""
        policy = ChatRetryPolicy(max_retries=3)

        assert policy.next_retry(_invalid()) is not None  # attempt 1
        assert policy.next_retry(_invalid()) is not None  # attempt 2
        assert policy.next_retry(_invalid()) is not None  # attempt 3
        assert policy.next_retry(_invalid()) is None  # gate trips
        assert policy.attempt == 3

    def test_zero_max_retries_never_retries(self):
        policy = ChatRetryPolicy(max_retries=0)
        assert policy.next_retry(_invalid()) is None
        assert policy.attempt == 0


class TestOriginalMessagePreserved:
    def test_retry_prompt_keeps_original_across_attempts(self):
        """The other half of the bug: the original user message was cleared
        before the retry prompt was built, so retries lost the question."""
        policy = ChatRetryPolicy(max_retries=3)
        policy.remember_original("跟我打招呼")

        p1 = policy.next_retry(_invalid())
        p2 = policy.next_retry(_invalid())

        assert "跟我打招呼" in p1
        assert "跟我打招呼" in p2

    def test_remember_original_only_seeds_first_attempt(self):
        """Once a retry is in flight (attempt > 0) the retry message must
        not overwrite the real original — mirrors start_request being
        re-entered with the retry prompt as its argument."""
        policy = ChatRetryPolicy(max_retries=3)
        policy.remember_original("real question")
        policy.next_retry(_invalid())  # attempt -> 1

        policy.remember_original("a retry prompt")  # should be ignored

        prompt = policy.next_retry(_invalid())
        assert "real question" in prompt
        assert "a retry prompt" not in prompt

    def test_retry_prompt_includes_error_detail(self):
        policy = ChatRetryPolicy(max_retries=3)
        prompt = policy.next_retry(_invalid("Invalid movement direction(s): foo"))
        assert "Invalid movement direction(s): foo" in prompt


class TestReset:
    def test_reset_clears_counter_and_original(self):
        policy = ChatRetryPolicy(max_retries=3)
        policy.remember_original("q")
        policy.next_retry(_invalid())
        assert policy.attempt == 1

        policy.reset()
        assert policy.attempt == 0

        # After reset a fresh original can be seeded again.
        policy.remember_original("new q")
        prompt = policy.next_retry(_invalid())
        assert "new q" in prompt
