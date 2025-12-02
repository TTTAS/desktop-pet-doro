"""State parser for LLM action tokens.

Extracts and normalizes state keys from LLM responses.
"""

from typing import Optional, Protocol


class StateProvider(Protocol):
    """Protocol for state lookup operations."""

    def get_state(self, key: str):
        """Get state by key."""
        ...

    def is_movement_only_state(self, key: str) -> bool:
        """Check if state is movement-only."""
        ...

    def find_state_by_label(self, label_query: str) -> Optional[str]:
        """Find state by label matching."""
        ...


class StateParser:
    """
    Parses state keys from LLM action tokens.

    Responsibilities:
    - Normalize action strings (remove prefixes, clean separators)
    - Apply action aliases (e.g., "sleep" -> "idle")
    - Try multiple normalized forms (spaces, underscores)
    - Match by label if direct lookup fails
    - Filter out movement-only states

    Does NOT:
    - Manage states or their lifecycle
    - Change application state
    - Know about Qt or UI
    """

    def __init__(self, action_aliases: Optional[dict[str, str]] = None):
        """
        Initialize parser.

        Args:
            action_aliases: Optional dict mapping action aliases to state keys.
                           If None, will import from utils.actions.
        """
        if action_aliases is None:
            from ...utils.actions import ACTION_ALIASES
            action_aliases = ACTION_ALIASES
        self._action_aliases = action_aliases

    def parse(self, action: str, state_provider: StateProvider) -> Optional[str]:
        """
        Parse state key from action token.

        Handles various formats:
            (happy) -> "happy"
            (STATE:stand) -> "stand"
            (Mode: idle) -> "idle"
            (狀態:walking) -> "walking"

        Also handles:
            - Action aliases (e.g., "sleep" -> "idle")
            - Multiple normalized forms (spaces, underscores)
            - Label matching
            - Chinese prefixes (狀態, 模式)

        Args:
            action: Raw action token string from LLM response
            state_provider: Provider for state lookup operations

        Returns:
            State key if valid non-movement state exists, None otherwise
        """
        # Normalize action token
        raw = (action or "").strip()
        if not raw:
            return None

        lowered = raw.lower()

        # Remove common prefixes: "state", "mode", "status"
        for prefix in ("state", "mode", "status"):
            if lowered.startswith(prefix):
                raw = raw[len(prefix) :]
                break
        else:
            # Handle Chinese prefixes
            if raw.startswith(("狀態", "模式")):
                raw = raw[2:]

        # Clean up separators
        raw = raw.lstrip(":：-_ ")
        normalized = raw.strip().lower()

        if not normalized:
            return None

        # Check aliases (e.g., "sleep" -> "idle")
        alias_target = self._action_aliases.get(normalized)
        if alias_target and state_provider.get_state(alias_target):
            if not state_provider.is_movement_only_state(alias_target):
                return alias_target

        # Try various normalized forms
        candidates = {
            normalized,
            normalized.replace(" ", "_"),
            normalized.replace(" ", ""),
        }

        # Sanitize: keep only alphanumeric, -, _
        sanitized = "".join(ch for ch in normalized if ch.isalnum() or ch in ("-", "_"))
        if sanitized:
            candidates.add(sanitized)

        for candidate in candidates:
            if state_provider.get_state(candidate):
                if not state_provider.is_movement_only_state(candidate):
                    return candidate

        # Try matching by label
        result = state_provider.find_state_by_label(normalized)
        if result and not state_provider.is_movement_only_state(result):
            return result

        return None
