"""Unit tests for StateParser.

Tests the parsing of LLM action tokens into state keys.
"""

from typing import Optional
from unittest.mock import Mock

import pytest

from doro_app.core.state.state_parser import StateParser


class MockStateProvider:
    """Mock state provider for testing."""

    def __init__(
        self,
        states: set[str],
        movement_only: set[str],
        labels: dict[str, str],
        hidden: Optional[set[str]] = None,
    ):
        """
        Initialize mock provider.

        Args:
            states: Set of valid state keys
            movement_only: Set of movement-only state keys
            labels: Dict mapping state keys to labels (for label matching)
            hidden: Set of hidden (action-backed) state keys the LLM must
                not be able to select
        """
        self.states = states
        self.movement_only = movement_only
        self.labels = labels  # key -> label
        self.hidden = hidden or set()

    def get_state(self, key: str):
        """Get state by key (returns truthy if exists)."""
        return key if key in self.states else None

    def is_movement_only_state(self, key: str) -> bool:
        """Check if state is movement-only."""
        return key in self.movement_only

    def is_hidden_state(self, key: str) -> bool:
        """Check if state is hidden (action-backed)."""
        return key in self.hidden

    def find_state_by_label(self, label_query: str) -> Optional[str]:
        """Find state by label matching."""
        label_lower = label_query.lower()
        for key, label in self.labels.items():
            if label.lower() == label_lower:
                return key
        return None


@pytest.fixture
def state_provider():
    """Create a mock state provider."""
    return MockStateProvider(
        states={"idle", "happy", "sad", "walking", "standing", "custom_state"},
        movement_only={"walking", "standing"},
        labels={"happy": "Happy", "sad": "Sad", "custom_state": "Custom State"},
    )


@pytest.fixture
def parser():
    """Create a StateParser with test aliases."""
    return StateParser(action_aliases={"sleep": "idle", "rest": "idle"})


class TestBasicParsing:
    """Test basic state key parsing."""

    def test_simple_state_key(self, parser, state_provider):
        """Parse simple state key."""
        result = parser.parse("happy", state_provider)
        assert result == "happy"

    def test_empty_string(self, parser, state_provider):
        """Empty string returns None."""
        result = parser.parse("", state_provider)
        assert result is None

    def test_none_input(self, parser, state_provider):
        """None input returns None."""
        result = parser.parse(None, state_provider)
        assert result is None

    def test_whitespace_only(self, parser, state_provider):
        """Whitespace-only string returns None."""
        result = parser.parse("   ", state_provider)
        assert result is None

    def test_nonexistent_state(self, parser, state_provider):
        """Non-existent state returns None."""
        result = parser.parse("nonexistent", state_provider)
        assert result is None


class TestPrefixHandling:
    """Test handling of various prefixes."""

    def test_state_prefix(self, parser, state_provider):
        """Remove 'state:' prefix."""
        result = parser.parse("state:happy", state_provider)
        assert result == "happy"

    def test_mode_prefix(self, parser, state_provider):
        """Remove 'mode:' prefix."""
        result = parser.parse("mode:sad", state_provider)
        assert result == "sad"

    def test_status_prefix(self, parser, state_provider):
        """Remove 'status:' prefix."""
        result = parser.parse("status:idle", state_provider)
        assert result == "idle"

    def test_chinese_prefix_state(self, parser, state_provider):
        """Remove Chinese '狀態:' prefix."""
        result = parser.parse("狀態:happy", state_provider)
        assert result == "happy"

    def test_chinese_prefix_mode(self, parser, state_provider):
        """Remove Chinese '模式:' prefix."""
        result = parser.parse("模式:sad", state_provider)
        assert result == "sad"

    def test_uppercase_prefix(self, parser, state_provider):
        """Handle uppercase prefix."""
        result = parser.parse("STATE:happy", state_provider)
        assert result == "happy"

    def test_mixed_case_prefix(self, parser, state_provider):
        """Handle mixed case prefix."""
        result = parser.parse("State:happy", state_provider)
        assert result == "happy"


class TestSeparatorHandling:
    """Test handling of various separators."""

    def test_colon_separator(self, parser, state_provider):
        """Handle colon separator."""
        result = parser.parse("state:happy", state_provider)
        assert result == "happy"

    def test_chinese_colon(self, parser, state_provider):
        """Handle Chinese colon separator."""
        result = parser.parse("state：happy", state_provider)
        assert result == "happy"

    def test_dash_separator(self, parser, state_provider):
        """Handle dash separator."""
        result = parser.parse("state-happy", state_provider)
        assert result == "happy"

    def test_underscore_separator(self, parser, state_provider):
        """Handle underscore separator."""
        result = parser.parse("state_happy", state_provider)
        assert result == "happy"

    def test_space_separator(self, parser, state_provider):
        """Handle space separator."""
        result = parser.parse("state happy", state_provider)
        assert result == "happy"

    def test_multiple_separators(self, parser, state_provider):
        """Handle multiple separators."""
        result = parser.parse("state:  happy", state_provider)
        assert result == "happy"


class TestAliasHandling:
    """Test action alias resolution."""

    def test_alias_sleep_to_idle(self, parser, state_provider):
        """Resolve 'sleep' alias to 'idle'."""
        result = parser.parse("sleep", state_provider)
        assert result == "idle"

    def test_alias_rest_to_idle(self, parser, state_provider):
        """Resolve 'rest' alias to 'idle'."""
        result = parser.parse("rest", state_provider)
        assert result == "idle"

    def test_alias_with_prefix(self, parser, state_provider):
        """Resolve alias even with prefix."""
        result = parser.parse("state:sleep", state_provider)
        assert result == "idle"

    def test_alias_case_insensitive(self, parser, state_provider):
        """Aliases are case-insensitive."""
        result = parser.parse("SLEEP", state_provider)
        assert result == "idle"


class TestNormalization:
    """Test various normalization strategies."""

    def test_space_to_underscore(self, parser, state_provider):
        """Spaces converted to underscores."""
        result = parser.parse("custom state", state_provider)
        assert result == "custom_state"

    def test_space_removal(self, parser, state_provider):
        """Try removing spaces if underscore doesn't work."""
        provider = MockStateProvider(
            states={"customstate"}, movement_only=set(), labels={}
        )
        result = parser.parse("custom state", provider)
        assert result == "customstate"

    def test_special_char_sanitization(self, parser, state_provider):
        """Remove special characters."""
        provider = MockStateProvider(states={"happy"}, movement_only=set(), labels={})
        result = parser.parse("hap!py@", provider)
        assert result == "happy"


class TestLabelMatching:
    """Test matching by label."""

    def test_match_by_label(self, parser, state_provider):
        """Match state by label when key doesn't match."""
        result = parser.parse("Custom State", state_provider)
        assert result == "custom_state"

    def test_label_case_insensitive(self, parser, state_provider):
        """Label matching is case-insensitive."""
        result = parser.parse("HAPPY", state_provider)
        assert result == "happy"

    def test_direct_key_takes_precedence(self, parser, state_provider):
        """Direct key match takes precedence over label."""
        # If both "happy" key and "Happy" label exist, key wins
        result = parser.parse("happy", state_provider)
        assert result == "happy"


class TestMovementOnlyFiltering:
    """Test filtering of movement-only states."""

    def test_reject_movement_only_state(self, parser, state_provider):
        """Movement-only states are rejected."""
        result = parser.parse("walking", state_provider)
        assert result is None

    def test_reject_standing_state(self, parser, state_provider):
        """Standing (movement-only) is rejected."""
        result = parser.parse("standing", state_provider)
        assert result is None

    def test_accept_non_movement_state(self, parser, state_provider):
        """Non-movement states are accepted."""
        result = parser.parse("happy", state_provider)
        assert result == "happy"

    def test_alias_to_movement_only_rejected(self, parser):
        """Alias targeting movement-only state is rejected."""
        provider = MockStateProvider(
            states={"walking"}, movement_only={"walking"}, labels={}
        )
        parser_with_alias = StateParser(action_aliases={"move": "walking"})
        result = parser_with_alias.parse("move", provider)
        assert result is None


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_prefix_only_no_state(self, parser, state_provider):
        """Prefix without state returns None."""
        result = parser.parse("state:", state_provider)
        assert result is None

    def test_multiple_prefixes(self, parser, state_provider):
        """Only first prefix is removed."""
        # "state mode:happy" -> "mode:happy" (doesn't match any state)
        # This is an edge case - malformed input doesn't match
        result = parser.parse("state mode:happy", state_provider)
        assert result is None

    def test_unicode_characters(self, parser, state_provider):
        """Handle unicode characters in state names."""
        provider = MockStateProvider(states={"你好"}, movement_only=set(), labels={})
        result = parser.parse("你好", provider)
        assert result == "你好"

    def test_numbers_in_state_key(self, parser, state_provider):
        """Handle numbers in state keys."""
        # Note: "state123" has "state" prefix removed, leaving "123"
        # Use a state key without reserved prefix to test numbers
        provider = MockStateProvider(states={"happy123"}, movement_only=set(), labels={})
        result = parser.parse("happy123", provider)
        assert result == "happy123"


class TestDefaultAliases:
    """Test using default aliases from utils.actions."""

    def test_default_aliases_loaded(self):
        """Parser loads default aliases if none provided."""
        parser = StateParser()  # No aliases provided
        # Verify parser has _action_aliases loaded
        assert parser._action_aliases is not None
        assert isinstance(parser._action_aliases, dict)

    def test_custom_aliases_override(self):
        """Custom aliases override default."""
        custom_aliases = {"test": "custom"}
        parser = StateParser(action_aliases=custom_aliases)
        assert parser._action_aliases == custom_aliases


class TestHiddenStatesRejected:
    """LLM tokens must never select hidden, gesture-only action states."""

    def _parser(self):
        return StateParser(action_aliases={})

    def test_hidden_state_token_is_rejected(self):
        provider = MockStateProvider(
            states={"idle", "click_action", "dragged"},
            movement_only=set(),
            labels={"dragged": "拖曳"},
            hidden={"click_action", "dragged"},
        )
        parser = self._parser()
        assert parser.parse("(click_action)", provider) is None
        assert parser.parse("dragged", provider) is None
        # A normal state right next to them still resolves.
        assert parser.parse("idle", provider) == "idle"

    def test_hidden_state_rejected_via_label_match(self):
        provider = MockStateProvider(
            states={"idle", "dragged"},
            movement_only=set(),
            labels={"dragged": "拖曳"},
            hidden={"dragged"},
        )
        parser = self._parser()
        # Even by its display label, a hidden state must not be selectable.
        assert parser.parse("拖曳", provider) is None
