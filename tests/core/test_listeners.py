"""Tests for `ListenerRegistry` — the shared subscribe/emit helper.

Extracted from the duplicated listener idiom that lived in both
`AutomationManager` (`_outcome_listeners`) and `MovementManager`
(`_completion_listeners`). One home for the register / unsubscribe /
snapshot-emit / swallow-exceptions behaviour.
"""

from __future__ import annotations

from doro_app.core.listeners import ListenerRegistry


class TestSubscribeEmit:
    def test_emit_delivers_to_all_listeners(self):
        reg: ListenerRegistry = ListenerRegistry()
        seen: list[int] = []
        reg.subscribe(lambda n: seen.append(n))
        reg.subscribe(lambda n: seen.append(n * 10))

        reg.emit(3)

        assert sorted(seen) == [3, 30]

    def test_emit_forwards_multiple_args(self):
        reg: ListenerRegistry = ListenerRegistry()
        captured: list[tuple] = []
        reg.subscribe(lambda *args: captured.append(args))

        reg.emit("fired", "detail-text")

        assert captured == [("fired", "detail-text")]

    def test_emit_with_no_args(self):
        reg: ListenerRegistry = ListenerRegistry()
        fired: list[None] = []
        reg.subscribe(lambda: fired.append(None))

        reg.emit()

        assert fired == [None]


class TestUnsubscribe:
    def test_unsubscribe_stops_delivery(self):
        reg: ListenerRegistry = ListenerRegistry()
        fired: list[None] = []
        unsub = reg.subscribe(lambda: fired.append(None))

        reg.emit()
        unsub()
        reg.emit()

        assert fired == [None]

    def test_double_unsubscribe_is_safe_and_leaves_others_intact(self):
        """Unsubscribing the same listener twice must not raise, and must
        not corrupt the registry — a still-subscribed listener keeps
        receiving. (A naive `remove` without the guard would raise on the
        second call; a buggy one could drop the wrong listener.)"""
        reg: ListenerRegistry = ListenerRegistry()
        b_fired: list[None] = []
        unsub_a = reg.subscribe(lambda: None)
        reg.subscribe(lambda: b_fired.append(None))

        unsub_a()
        unsub_a()  # second call must not raise

        reg.emit()
        assert b_fired == [None]  # B unaffected by A's double-unsub

    def test_listener_persists_across_emits_until_unsub(self):
        reg: ListenerRegistry = ListenerRegistry()
        fired: list[None] = []
        reg.subscribe(lambda: fired.append(None))

        reg.emit()
        reg.emit()

        assert fired == [None, None]


class TestRobustness:
    def test_listener_that_unsubscribes_during_emit_is_safe(self):
        """A listener may detach itself while being notified — the common
        one-shot wait pattern. Emit iterates a snapshot so this is safe."""
        reg: ListenerRegistry = ListenerRegistry()
        fired: list[None] = []

        unsub: list = []

        def once() -> None:
            fired.append(None)
            unsub[0]()

        unsub.append(reg.subscribe(once))

        reg.emit()
        reg.emit()  # already unsubscribed — no second fire

        assert fired == [None]

    def test_raising_listener_does_not_block_others(self):
        reg: ListenerRegistry = ListenerRegistry()
        seen: list[str] = []
        reg.subscribe(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        reg.subscribe(lambda: seen.append("ok"))

        reg.emit()  # must not propagate the RuntimeError

        assert seen == ["ok"]
