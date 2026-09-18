"""Unit tests for transition matching with wildcard support."""

import pytest

from doro_app.core.state.models import Transition, TransitionCollection

# Wildcard constant for transitions (matches doro_app.constants.TRANSITION_WILDCARD)
WILDCARD = "*"


class TestTransitionPriorityMatching:
    """Test priority-based transition matching."""

    @pytest.fixture
    def collection(self):
        """Create a collection with various transition patterns."""
        coll = TransitionCollection()

        # Priority 1: Exact matches
        coll.add(
            Transition(
                key="idle_to_happy",
                from_state="idle",
                to_state="happy",
                transition_gif_id="idle_happy.gif",
            )
        )
        coll.add(
            Transition(
                key="idle_to_sad",
                from_state="idle",
                to_state="sad",
                transition_gif_id="idle_sad.gif",
            )
        )

        # Priority 2a: from specific -> any
        coll.add(
            Transition(
                key="excited_to_any",
                from_state="excited",
                to_state=WILDCARD,
                transition_gif_id="excited_exit.gif",
            )
        )

        # Priority 2b: from any -> specific
        coll.add(
            Transition(
                key="any_to_sleeping",
                from_state=WILDCARD,
                to_state="sleeping",
                transition_gif_id="enter_sleeping.gif",
            )
        )

        # Priority 3: Universal
        coll.add(
            Transition(
                key="universal",
                from_state=WILDCARD,
                to_state=WILDCARD,
                transition_gif_id="generic_transition.gif",
            )
        )

        return coll

    def test_exact_match_highest_priority(self, collection):
        """Exact match should have highest priority."""
        result = collection.find_transition("idle", "happy")
        assert result is not None
        assert result.key == "idle_to_happy"
        assert result.transition_gif_id == "idle_happy.gif"

    def test_from_specific_to_wildcard(self, collection):
        """Match from specific state to any state when no exact match."""
        # "excited" -> "angry" has no exact match, should use "excited" -> "*"
        result = collection.find_transition("excited", "angry")
        assert result is not None
        assert result.key == "excited_to_any"
        assert result.transition_gif_id == "excited_exit.gif"

    def test_from_wildcard_to_specific(self, collection):
        """Match from any state to specific state when no exact or from->* match."""
        # "angry" -> "sleeping" has no exact match and no "angry" -> "*", should use "*" -> "sleeping"
        result = collection.find_transition("angry", "sleeping")
        assert result is not None
        assert result.key == "any_to_sleeping"
        assert result.transition_gif_id == "enter_sleeping.gif"

    def test_universal_wildcard_lowest_priority(self, collection):
        """Universal wildcard should be used only when no other matches."""
        # "walking" -> "running" has no specific matches, should use "*" -> "*"
        result = collection.find_transition("walking", "running")
        assert result is not None
        assert result.key == "universal"
        assert result.transition_gif_id == "generic_transition.gif"

    def test_no_match_returns_none(self):
        """Return None when no transition matches (even wildcards)."""
        coll = TransitionCollection()
        # Only add one specific transition
        coll.add(
            Transition(
                key="idle_to_happy",
                from_state="idle",
                to_state="happy",
                transition_gif_id="idle_happy.gif",
            )
        )

        # Different states should return None
        result = coll.find_transition("sad", "angry")
        assert result is None

    def test_priority_2a_over_2b(self, collection):
        """from->wildcard should take priority over wildcard->to."""
        # Both "excited" -> "*" and "*" -> "sleeping" exist
        # But "excited" -> "sleeping" should match "excited" -> "*" first
        result = collection.find_transition("excited", "sleeping")
        assert result is not None
        assert result.key == "excited_to_any"
        assert result.transition_gif_id == "excited_exit.gif"


class TestTransitionWildcardEdgeCases:
    """Test edge cases and special scenarios."""

    def test_same_state_transition(self):
        """Test transition from state to itself."""
        coll = TransitionCollection()
        coll.add(
            Transition(
                key="idle_to_idle",
                from_state="idle",
                to_state="idle",
                transition_gif_id="idle_loop.gif",
            )
        )

        result = coll.find_transition("idle", "idle")
        assert result is not None
        assert result.key == "idle_to_idle"

    def test_wildcard_only_collection(self):
        """Collection with only wildcard transitions."""
        coll = TransitionCollection()
        coll.add(
            Transition(
                key="any_to_any",
                from_state=WILDCARD,
                to_state=WILDCARD,
                transition_gif_id="universal.gif",
            )
        )

        # Any transition should match
        result = coll.find_transition("any_state", "other_state")
        assert result is not None
        assert result.key == "any_to_any"

    def test_multiple_exact_matches_use_first_added(self):
        """If multiple exact matches exist (shouldn't happen), use first added."""
        coll = TransitionCollection()
        coll.add(
            Transition(
                key="idle_happy_1",
                from_state="idle",
                to_state="happy",
                transition_gif_id="first.gif",
            )
        )
        # This should overwrite the first one due to same key pair
        coll.add(
            Transition(
                key="idle_happy_2",
                from_state="idle",
                to_state="happy",
                transition_gif_id="second.gif",
            )
        )

        result = coll.find_transition("idle", "happy")
        assert result is not None
        # Should get the second one (overwrite behavior)
        assert result.key == "idle_happy_2"

    def test_empty_collection(self):
        """Empty collection returns None."""
        coll = TransitionCollection()
        result = coll.find_transition("idle", "happy")
        assert result is None


class TestTransitionCollectionOperations:
    """Test collection operations with wildcards."""

    def test_add_and_find_wildcard_transition(self):
        """Add and find wildcard transitions."""
        coll = TransitionCollection()
        coll.add(
            Transition(
                key="exit_any",
                from_state="exiting",
                to_state=WILDCARD,
                transition_gif_id="exit.gif",
            )
        )

        result = coll.find_transition("exiting", "anywhere")
        assert result is not None
        assert result.from_state == "exiting"
        assert result.to_state == WILDCARD

    def test_remove_wildcard_transition(self):
        """Remove wildcard transition."""
        coll = TransitionCollection()
        coll.add(
            Transition(
                key="any_enter",
                from_state=WILDCARD,
                to_state="entering",
                transition_gif_id="enter.gif",
            )
        )

        # Verify it exists
        assert coll.find_transition("anywhere", "entering") is not None

        # Remove it
        removed = coll.remove("any_enter")
        assert removed is True

        # Verify it's gone
        assert coll.find_transition("anywhere", "entering") is None

    def test_overwrite_transition_updates_index(self):
        """Overwriting a transition should update the index correctly."""
        coll = TransitionCollection()

        # Add initial transition
        coll.add(
            Transition(key="t1", from_state="idle", to_state="happy", transition_gif_id="v1.gif")
        )

        # Overwrite with different from/to but same key
        coll.add(
            Transition(key="t1", from_state="sad", to_state="angry", transition_gif_id="v2.gif")
        )

        # Old mapping should not work
        assert coll.find_transition("idle", "happy") is None

        # New mapping should work
        result = coll.find_transition("sad", "angry")
        assert result is not None
        assert result.transition_gif_id == "v2.gif"
