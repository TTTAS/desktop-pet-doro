"""Regression tests pinning the removal of Live2D support.

Live2D rendering (and the mixed GIF/Live2D pipeline) was removed because
combining the two render paths proved not worth the complexity. These tests
lock in the two guarantees that removal was supposed to deliver:

1. The ``State`` model no longer carries any Live2D concept.
2. Sprite resolution always falls back to a state's GIF — including the
   pick-up / held state that used to switch into Live2D mode.

If someone reintroduces a Live2D model path field or short-circuit, these
tests should fail and force a deliberate decision rather than a silent revert.
"""

from pathlib import Path

from doro_app.core.state import State, StateService


class TestLive2DFieldRemoved:
    """The State model must not expose a Live2D model path anymore."""

    def test_state_has_no_live2d_model_path_attribute(self):
        state = State(key="idle", label="Idle")
        assert not hasattr(state, "live2d_model_path")

    def test_state_cannot_be_constructed_with_live2d_model_path(self):
        try:
            State(key="idle", label="Idle", live2d_model_path="whatever.model3.json")
        except TypeError:
            return  # Expected: the field no longer exists.
        raise AssertionError(
            "State accepted a live2d_model_path argument — the field was reintroduced."
        )


class TestPickupFallsBackToGif:
    """Sprite resolution must resolve to a state's GIF, with no Live2D path."""

    def test_get_gif_path_returns_state_gif(
        self, state_service_with_mocks: StateService, mock_gif_repo
    ):
        # A "held" state stands in for the pick-up interaction that formerly
        # switched into Live2D mode; it must now resolve to its GIF.
        held_gif = Path("/fake/held.gif")
        mock_gif_repo.pick_random_gif.return_value = held_gif

        state_service_with_mocks.add_state("held", "Held")

        resolved = state_service_with_mocks.get_gif_path("held")

        assert resolved == held_gif
