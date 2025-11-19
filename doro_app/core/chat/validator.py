"""Response validator for LLM chat outputs - ensures reliable parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...utils.actions import BRACKET_PATTERN, MOVE_DIRECTIONS, parse_actions_from_text

if TYPE_CHECKING:
    from ..state import StateService


@dataclass
class ValidationResult:
    """Result of validating an LLM response."""

    valid: bool
    error_message: str | None = None
    has_state: bool = False
    has_movement: bool = False
    has_dialogue: bool = False

    @staticmethod
    def success(*, has_state: bool = False, has_movement: bool = False, has_dialogue: bool = False) -> ValidationResult:
        """Create a successful validation result."""
        return ValidationResult(
            valid=True,
            has_state=has_state,
            has_movement=has_movement,
            has_dialogue=has_dialogue,
        )

    @staticmethod
    def failure(error: str) -> ValidationResult:
        """Create a failed validation result."""
        return ValidationResult(valid=False, error_message=error)


class ResponseValidator:
    """Validates LLM responses to ensure they follow the expected format."""

    # Movement token pattern from actions.py
    _MOVE_BRACKET_PATTERN = re.compile(
        r"MOVE\s*:\s*dir\s*=\s*([a-z]+|[上下左右]{1,2})(?:\s*;\s*distance\s*=\s*(\d+))?",
        re.IGNORECASE,
    )

    def __init__(self, state_service: StateService):
        """
        Initialize validator.

        Args:
            state_service: StateService instance to validate states against
        """
        self._state_service = state_service

    def validate(self, response: str) -> ValidationResult:
        """
        Validate an LLM response for correct format.

        Checks:
        1. Response is not empty
        2. If movement tokens are present, they must have valid directions
        3. Response should contain dialogue (not just control tokens)

        Note: State validation is disabled - invalid states will be handled by
        the orchestrator (falling back to current state if not found).

        Args:
            response: Raw LLM response text

        Returns:
            ValidationResult with success/failure and details
        """
        if not response or not response.strip():
            return ValidationResult.failure("Response is empty")

        # Parse actions
        cleaned_text, actions = parse_actions_from_text(response)

        has_state = False
        has_movement = False
        invalid_directions: list[str] = []

        # Check for state tokens (but don't validate - orchestrator will handle)
        for kind, token in actions:
            if kind == "paren":
                has_state = True  # Just mark that state token exists

        # Validate movement tokens (brackets)
        for kind, token in actions:
            if kind == "bracket":
                # Extract direction from MOVE token
                match = self._MOVE_BRACKET_PATTERN.search(token)
                if match:
                    direction = match.group(1).lower()
                    # Validate direction
                    if direction not in MOVE_DIRECTIONS:
                        invalid_directions.append(direction)
                    else:
                        has_movement = True

        # Check for dialogue content
        has_dialogue = bool(cleaned_text.strip())

        # Only fail on invalid directions (not invalid states)
        if invalid_directions:
            valid_dirs = ["left", "right", "up", "down", "upleft", "upright", "downleft", "downright"]
            return ValidationResult.failure(
                f"Invalid movement direction(s): {', '.join(invalid_directions)}. "
                f"Valid directions: {', '.join(valid_dirs)}"
            )

        # Success
        return ValidationResult.success(
            has_state=has_state,
            has_movement=has_movement,
            has_dialogue=has_dialogue,
        )

    def should_retry(self, result: ValidationResult) -> bool:
        """
        Determine if a failed validation should trigger a retry.

        Args:
            result: ValidationResult from validate()

        Returns:
            True if should retry, False otherwise
        """
        # Retry on validation failures (invalid states/directions)
        # Don't retry on empty responses (likely model error)
        if not result.valid:
            if result.error_message and "empty" not in result.error_message.lower():
                return True
        return False

    def build_retry_prompt(self, result: ValidationResult, original_message: str) -> str:
        """
        Build a retry prompt that includes the validation error.

        Args:
            result: Failed ValidationResult
            original_message: Original user message

        Returns:
            Retry prompt text
        """
        error_detail = result.error_message or "Unknown error"
        return (
            f"{original_message}\n\n"
            f"[系統提示] 你上次的回應格式有誤: {error_detail}\n"
            f"請重新回答，確保使用正確的狀態和格式。"
        )
