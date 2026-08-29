"""Tests for StateCollection / MoveStateCollection public API and key normalization."""

from doro_app.core.state.models import (
    MoveState,
    MoveStateCollection,
    State,
    StateCollection,
    Transition,
    TransitionCollection,
    normalize_state_key,
)


def test_normalize_state_key_strips_and_lowers():
    assert normalize_state_key("  Idle ") == "idle"
    assert normalize_state_key("STAND") == "stand"


def test_state_collection_stores_lowercase_keys():
    col = StateCollection()
    col.add(State(key="Happy", label="Happy"))

    assert col.get("happy") is not None
    assert col.get("HAPPY") is not None
    assert col.get("Happy").key == "happy"
    assert "HAPPY" in col
    assert col.all_keys() == ["happy"]


def test_set_current_is_case_insensitive():
    col = StateCollection()
    col.add(State(key="idle", label="Idle"))

    assert col.set_current("IDLE") is True
    assert col.current_key() == "idle"
    assert col.current() is not None
    assert col.current().key == "idle"


def test_protected_keys_public_accessor():
    col = StateCollection()
    assert "idle" in col.protected_keys()
    col.protect("Walking")
    assert col.is_protected("walking")
    assert "walking" in col.protected_keys()
    assert col.remove("WALKING") is False


def test_hidden_keys_public_accessor():
    col = StateCollection()
    col.add(State(key="click_action", label="Click"))
    col.hide("Click_Action")
    assert col.is_hidden("click_action")
    assert "click_action" in col.hidden_keys()
    assert "click_action" not in col.visible_keys(set())


def test_constructor_normalizes_seed_states():
    col = StateCollection({"X": State(key="Stand", label="stand")})
    assert col.get("stand") is not None
    assert col.get("stand").key == "stand"


def test_move_state_collection_exposes_movement_only_keys():
    col = MoveStateCollection()
    col.add(MoveState(key="Walk", state_key="Walking", direction="any"))

    assert col.get("WALK") is not None
    assert col.get("walk").key == "walk"
    assert col.get("walk").state_key == "walking"
    assert col.is_movement_only("WALKING")
    assert col.movement_only_keys() == {"walking"}


def test_move_state_remove_clears_movement_only_when_unused():
    col = MoveStateCollection()
    col.add(MoveState(key="walk", state_key="walking", direction="any"))
    col.add(MoveState(key="run", state_key="walking", direction="any"))

    assert col.remove("walk") is True
    assert col.is_movement_only("walking")
    assert col.remove("run") is True
    assert not col.is_movement_only("walking")
    assert col.movement_only_keys() == set()


def test_items_returns_a_copy():
    states = StateCollection()
    states.add(State(key="idle", label="Idle"))
    snapshot = states.items()
    snapshot.clear()
    assert states.get("idle") is not None

    moves = MoveStateCollection()
    moves.add(MoveState(key="walk", state_key="walking"))
    move_snapshot = moves.items()
    move_snapshot.clear()
    assert moves.get("walk") is not None


def test_transition_find_normalizes_endpoints():
    col = TransitionCollection()
    col.add(Transition(key="IdleToHappy", from_state="Idle", to_state="Happy"))

    found = col.find_transition("IDLE", " happy ")
    assert found is not None
    assert found.key == "idletohappy"
    assert found.from_state == "idle"
    assert found.to_state == "happy"
