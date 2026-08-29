"""PR C: reaction timeline director (Qt-free)."""

from __future__ import annotations

from doro_app.core.reaction import (
    PRIORITY_CLICK,
    PRIORITY_IDLE,
    MoveStep,
    ReactionCatalog,
    ReactionDirector,
    ReactionRunner,
    RestoreStep,
    SpeakStep,
    StateStep,
    Timeline,
    WaitStep,
    speak_timeline,
)


class ManualScheduler:
    def __init__(self) -> None:
        self.pending: list[tuple[int, object]] = []

    def __call__(self, delay_ms: int, callback) -> None:
        self.pending.append((delay_ms, callback))

    def run_next(self) -> None:
        if not self.pending:
            raise AssertionError("no scheduled callback")
        _delay, callback = self.pending.pop(0)
        callback()

    def flush(self) -> None:
        while self.pending:
            self.run_next()


class FakeState:
    def __init__(self, current: str = "idle") -> None:
        self.current = current
        self.calls: list[tuple[str, bool]] = []

    def request_state(self, key: str, *, force: bool = False) -> bool:
        self.calls.append((key, force))
        self.current = key
        return True


def _director(
    state: FakeState,
    spoken: list[str],
    schedule: ManualScheduler,
    moves=None,
    *,
    with_current_key: bool = False,
):
    return ReactionDirector(
        request_state=state.request_state,
        speak=spoken.append,
        schedule=schedule,
        move=None if moves is None else (lambda d, dist: moves.append((d, dist))),
        current_key=(lambda: state.current) if with_current_key else None,
    )


def test_state_then_speak_runs_in_order():
    state = FakeState()
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule)

    ok = director.play(
        Timeline(
            name="greet",
            steps=(StateStep("happy"), SpeakStep("hi")),
        )
    )
    assert ok is True
    assert state.calls == [("happy", False)]
    assert spoken == ["hi"]
    assert director.is_playing is False


def test_wait_yields_until_scheduler_fires():
    state = FakeState()
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule)

    director.play(
        Timeline(
            name="pause",
            steps=(StateStep("idle"), WaitStep(0.4), SpeakStep("after")),
        )
    )
    assert state.calls == [("idle", False)]
    assert spoken == []
    assert director.is_playing is True
    assert schedule.pending[0][0] == 400

    schedule.run_next()
    assert spoken == ["after"]
    assert director.is_playing is False


def test_click_preempts_idle():
    state = FakeState()
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule)

    director.play(
        Timeline(
            name="idle_speak",
            priority=PRIORITY_IDLE,
            steps=(WaitStep(1.0), SpeakStep("idle")),
        )
    )
    assert director.current_name == "idle_speak"

    ok = director.play(
        Timeline(
            name="click",
            priority=PRIORITY_CLICK,
            steps=(StateStep("click_action", force=True), SpeakStep("clicked")),
        )
    )
    assert ok is True
    assert director.current_name is None
    assert state.calls == [("click_action", True)]
    assert spoken == ["clicked"]

    schedule.flush()
    assert spoken == ["clicked"]


def test_idle_does_not_preempt_click():
    state = FakeState()
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule)

    director.play(
        Timeline(
            name="click",
            priority=PRIORITY_CLICK,
            steps=(WaitStep(1.0), SpeakStep("click")),
        )
    )
    ok = director.play(
        Timeline(
            name="idle_speak",
            priority=PRIORITY_IDLE,
            steps=(SpeakStep("idle"),),
        )
    )
    assert ok is False
    assert director.current_name == "click"
    schedule.run_next()
    assert spoken == ["click"]


def test_cancel_drops_pending_wait():
    state = FakeState()
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule)
    director.play(Timeline(name="x", steps=(WaitStep(1.0), SpeakStep("nope"))))
    director.cancel()
    schedule.flush()
    assert spoken == []
    assert director.is_playing is False


def test_move_step_uses_port_when_wired():
    state = FakeState()
    spoken: list[str] = []
    schedule = ManualScheduler()
    moves: list[tuple[str, float]] = []
    director = _director(state, spoken, schedule, moves=moves)
    director.play(Timeline(name="wander", steps=(MoveStep("left", 120.0),)))
    assert moves == [("left", 120.0)]


def test_move_step_skipped_without_port():
    state = FakeState()
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule)
    director.play(Timeline(name="wander", steps=(MoveStep("left", 120.0), SpeakStep("ok"))))
    assert spoken == ["ok"]


def test_catalog_defaults_include_click_above_idle():
    catalog = ReactionCatalog()
    catalog.register_defaults()
    click = catalog.get("click")
    idle = catalog.get("idle_speak")
    assert click is not None and idle is not None
    assert click.priority > idle.priority
    assert isinstance(click.steps[0], StateStep)
    assert click.steps[0].key == "click_action"
    assert click.steps[0].force is True
    assert isinstance(click.steps[-1], RestoreStep)


def test_speak_timeline_helper():
    tl = speak_timeline("chat_hi", "hello")
    assert tl.steps == (SpeakStep("hello"),)
    assert tl.priority > PRIORITY_IDLE


def test_restore_step_returns_to_key_captured_at_play_start():
    state = FakeState(current="happy")
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule, with_current_key=True)

    director.play(
        Timeline(
            name="click",
            priority=PRIORITY_CLICK,
            steps=(
                StateStep("click_action", force=True),
                WaitStep(0.4),
                RestoreStep(),
            ),
        )
    )
    assert state.calls == [("click_action", True)]
    assert director.is_playing is True

    schedule.run_next()
    assert state.calls == [("click_action", True), ("happy", True)]
    assert director.is_playing is False


def test_restore_step_skipped_without_current_key_port():
    state = FakeState(current="happy")
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule)

    director.play(
        Timeline(
            name="click",
            steps=(StateStep("click_action", force=True), RestoreStep()),
        )
    )
    assert state.calls == [("click_action", True)]


def test_runner_play_unknown_name_is_false():
    catalog = ReactionCatalog()
    catalog.register_defaults()
    state = FakeState()
    spoken: list[str] = []
    schedule = ManualScheduler()
    runner = ReactionRunner(catalog, _director(state, spoken, schedule))
    assert runner.play("does_not_exist") is False
    assert runner.is_playing is False


def test_runner_play_named_click_uses_catalog():
    catalog = ReactionCatalog()
    catalog.register_defaults()
    state = FakeState(current="idle")
    spoken: list[str] = []
    schedule = ManualScheduler()
    runner = ReactionRunner(
        catalog,
        _director(state, spoken, schedule, with_current_key=True),
    )
    assert runner.play("click") is True
    assert state.calls == [("click_action", True)]
    schedule.run_next()
    assert state.calls[-1] == ("idle", True)


def test_double_click_still_restores_to_original_home():
    state = FakeState(current="idle")
    spoken: list[str] = []
    schedule = ManualScheduler()
    director = _director(state, spoken, schedule, with_current_key=True)

    click = Timeline(
        name="click",
        priority=PRIORITY_CLICK,
        steps=(StateStep("click_action", force=True), WaitStep(0.4), RestoreStep()),
    )

    director.play(click)  # home captured = idle
    director.play(click)  # preempts mid-wait; home must stay idle, not click_action
    assert director._restore_key == "idle"

    schedule.flush()  # stale wait no-ops, live wait fires RestoreStep
    assert state.current == "idle"
    assert state.calls[-1] == ("idle", True)
    assert director.is_playing is False
