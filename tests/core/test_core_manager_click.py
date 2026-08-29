"""PR C slice 2: CoreManager click hook talks to ReactionRunner."""

from unittest.mock import Mock

from PySide6.QtCore import QObject

from doro_app.core.core_manager import CoreManager


def _manager(reaction_runner=None) -> CoreManager:
    orchestrator = Mock(spec=QObject)
    orchestrator.bubble_text_requested = Mock()
    orchestrator.bubble_text_requested.connect = Mock()
    orchestrator.busy_cursor_requested = Mock()
    orchestrator.busy_cursor_requested.connect = Mock()
    orchestrator.notification_requested = Mock()
    orchestrator.notification_requested.connect = Mock()
    orchestrator.is_inflight = False

    player = Mock(spec=QObject)
    player.transition_completed = Mock()
    player.transition_completed.connect = Mock()

    return CoreManager(
        state_service=Mock(),
        chat_controller=Mock(spec=QObject),
        chat_orchestrator=orchestrator,
        movement_manager=Mock(),
        transition_player=player,
        config_manager=Mock(),
        reaction_runner=reaction_runner,
    )


def test_on_user_clicked_without_runner_is_false():
    manager = _manager()
    assert manager.on_user_clicked() is False


def test_on_user_clicked_plays_click_timeline():
    runner = Mock()
    runner.play.return_value = True
    manager = _manager(reaction_runner=runner)
    assert manager.on_user_clicked() is True
    runner.play.assert_called_once_with("click")
