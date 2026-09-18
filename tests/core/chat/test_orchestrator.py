"""Tests for ChatOrchestrator - chat coordination layer."""

from unittest.mock import Mock

import pytest

from doro_app.core.chat.orchestrator import ChatOrchestrator


@pytest.fixture
def mock_controller():
    """Create mock ChatController."""
    controller = Mock()
    # Mock signals
    controller.request_started = Mock()
    controller.request_started.connect = Mock()
    controller.request_succeeded = Mock()
    controller.request_succeeded.connect = Mock()
    controller.request_failed = Mock()
    controller.request_failed.connect = Mock()

    # Mock properties and methods
    controller.is_inflight = False
    # Settings now live on a ChatSettings object the orchestrator exposes
    # directly (orchestrator.settings) rather than via pass-through methods.
    controller.settings = Mock()

    # Mock methods
    controller.start_request = Mock(return_value=(True, None))
    controller.clear_history = Mock()

    return controller


@pytest.fixture
def mock_movement_manager():
    """Create mock MovementManager."""
    manager = Mock()
    manager.queue_movement = Mock()
    return manager


@pytest.fixture
def mock_state_service():
    """Create mock StateService."""
    service = Mock()
    service.has_state = Mock(return_value=True)
    service.visible_state_keys.return_value = ["idle", "happy"]
    return service


@pytest.fixture
def orchestrator(mock_controller, mock_movement_manager, mock_state_service):
    """Create ChatOrchestrator with mocked dependencies."""
    return ChatOrchestrator(
        controller=mock_controller,
        movement=mock_movement_manager,
        state_service=mock_state_service,
    )


# ═══════════════════════════════════════════════════════════
# Initialization Tests
# ═══════════════════════════════════════════════════════════


class TestChatOrchestratorInitialization:
    """Test ChatOrchestrator initialization."""

    def test_initialization_succeeds(self, orchestrator):
        """ChatOrchestrator can be initialized."""
        assert orchestrator is not None

    def test_connects_to_controller_signals(self, mock_controller, orchestrator):
        """ChatOrchestrator connects to controller signals."""
        mock_controller.request_started.connect.assert_called_once()
        mock_controller.request_succeeded.connect.assert_called_once()
        mock_controller.request_failed.connect.assert_called_once()


# ═══════════════════════════════════════════════════════════
# Message Sending Tests
# ═══════════════════════════════════════════════════════════


class TestSendMessage:
    """Test message sending functionality."""

    def test_send_message_starts_request(self, orchestrator, mock_controller):
        """send_message delegates to controller.start_request."""
        result = orchestrator.send_message("Hello")

        assert result is True
        mock_controller.start_request.assert_called_once_with("Hello", is_auto=False)

    def test_send_message_with_auto_flag(self, orchestrator, mock_controller):
        """send_message passes is_auto flag to controller."""
        result = orchestrator.send_message("Auto message", is_auto=True)

        assert result is True
        mock_controller.start_request.assert_called_once_with("Auto message", is_auto=True)


# ═══════════════════════════════════════════════════════════
# Bubble dialogue cleaning (單行 vs 多行)
# ═══════════════════════════════════════════════════════════


class TestCleanAssistantDialogue:
    """`_clean_assistant_dialogue`：一般聊天取一行，讀網頁答覆保留多行。"""

    def test_default_returns_first_line_only(self, orchestrator):
        text = "(開心) 第一句\n第二句\n第三句"
        # 一般寵物聊天：維持只顯示第一句的個性
        assert orchestrator._clean_assistant_dialogue(text) == "(開心) 第一句"

    def test_multiline_keeps_all_lines(self, orchestrator):
        text = "(思考) 這頁在講 A\n重點一：B\n重點二：C"
        out = orchestrator._clean_assistant_dialogue(text, multi_line=True)
        assert out == "(思考) 這頁在講 A\n重點一：B\n重點二：C"

    def test_multiline_still_filters_user_lines(self, orchestrator):
        text = "(思考) doro的話\n使用者: 不該顯示\n第二句"
        out = orchestrator._clean_assistant_dialogue(text, multi_line=True)
        assert "不該顯示" not in out
        assert "第二句" in out


class TestOperateActionRouting:
    """模型吐 [operate:目標] → 啟動網頁操作（受總開關管）。"""

    def _make(self, mock_controller, mock_movement_manager, mock_state_service, *, enabled):
        from types import SimpleNamespace

        web_runtime = Mock()
        cfg = SimpleNamespace(automation=SimpleNamespace(web_operation_enabled=enabled))
        orch = ChatOrchestrator(
            controller=mock_controller,
            movement=mock_movement_manager,
            state_service=mock_state_service,
            web_runtime=web_runtime,
            config_manager=cfg,
        )
        return orch, web_runtime

    def test_operate_action_starts_operation_when_enabled(
        self, mock_controller, mock_movement_manager, mock_state_service
    ):
        orch, web_runtime = self._make(
            mock_controller, mock_movement_manager, mock_state_service, enabled=True
        )
        orch._last_user_text = "幫我在購物網站買耳機"
        shown = orch._on_request_succeeded("(思考) 好，doro上網幫你～ [operate:買耳機]", False)
        assert shown == ""
        assert orch._operating is True
        web_runtime.submit_operation.assert_called_once()
        assert "買耳機" in web_runtime.submit_operation.call_args.args[0]

    def test_empty_goal_falls_back_to_user_text(
        self, mock_controller, mock_movement_manager, mock_state_service
    ):
        orch, web_runtime = self._make(
            mock_controller, mock_movement_manager, mock_state_service, enabled=True
        )
        orch._last_user_text = "幫我在 pchome 訂便當"
        orch._on_request_succeeded("(思考) 好喔～ [operate:]", False)
        assert "便當" in web_runtime.submit_operation.call_args.args[0]

    def test_operate_action_blocked_when_disabled(
        self, mock_controller, mock_movement_manager, mock_state_service
    ):
        orch, web_runtime = self._make(
            mock_controller, mock_movement_manager, mock_state_service, enabled=False
        )
        bubble_spy = Mock()
        orch.bubble_text_requested.connect(bubble_spy)
        orch._on_request_succeeded("(思考) 好～ [operate:買耳機]", False)
        assert orch._operating is False
        web_runtime.submit_operation.assert_not_called()
        assert "關" in bubble_spy.call_args.args[0]


class TestVerifyActionRouting:
    """模型吐 [verify:問題] → 啟動查證（read-only，不受操作總開關限制）。"""

    def test_verify_action_starts_verify(
        self, mock_controller, mock_movement_manager, mock_state_service
    ):
        web_runtime = Mock()
        orch = ChatOrchestrator(
            controller=mock_controller,
            movement=mock_movement_manager,
            state_service=mock_state_service,
            web_runtime=web_runtime,
        )
        shown = orch._on_request_succeeded("(高) 上網幫你查～ [verify:基本工資多少]", False)
        assert shown == ""
        assert orch._operating is False
        web_runtime.submit_verify.assert_called_once()
        assert "基本工資" in web_runtime.submit_verify.call_args.args[1]

    def test_empty_query_falls_back_to_user_text(
        self, mock_controller, mock_movement_manager, mock_state_service
    ):
        web_runtime = Mock()
        orch = ChatOrchestrator(
            controller=mock_controller,
            movement=mock_movement_manager,
            state_service=mock_state_service,
            web_runtime=web_runtime,
        )
        orch._last_user_text = "台積電股價是不是真的破千了"
        orch._on_request_succeeded("(高) 我查查～ [verify:]", False)
        assert "台積電" in web_runtime.submit_verify.call_args.args[1]


class TestLoginActionRouting:
    """模型吐 [login:網址] → 開站給使用者登入（不受總開關限制、也不啟動操作）。"""

    def test_login_action_opens_site(
        self, mock_controller, mock_movement_manager, mock_state_service
    ):
        web_runtime = Mock()
        orch = ChatOrchestrator(
            controller=mock_controller,
            movement=mock_movement_manager,
            state_service=mock_state_service,
            web_runtime=web_runtime,
        )
        shown = orch._on_request_succeeded("(高) 幫你把蝦皮開好～ [login:https://shopee.tw]", False)
        assert shown == ""
        assert orch._operating is False  # 不是操作，是開站
        web_runtime.submit_login.assert_called_once()
        assert "shopee.tw" in web_runtime.submit_login.call_args.args[1]


class TestStripMarkdown:
    """讀網頁答覆的 Markdown 清理（純文字泡泡框用）。"""

    def test_removes_bold_and_code(self, orchestrator):
        assert orchestrator._strip_markdown("**重點**是 `這個`") == "重點是 這個"

    def test_bullet_becomes_dot(self, orchestrator):
        out = orchestrator._strip_markdown("- 第一點\n* 第二點")
        assert out == "・第一點\n・第二點"

    def test_drops_dangling_asterisk_line(self, orchestrator):
        # 被截斷留下的一顆 * / ** 整行清掉
        out = orchestrator._strip_markdown("doro看完囉～\n**")
        assert out == "doro看完囉～"

    def test_strips_heading(self, orchestrator):
        assert orchestrator._strip_markdown("# 標題\n內文") == "標題\n內文"


class TestWebAnswerFlag:
    """讀完網頁後那一則答覆要被標記為「可多行」。"""

    def test_web_read_result_sets_expect_web_answer(self, orchestrator, mock_controller):
        from doro_app.core.web.reader import WebReadResult

        orchestrator._current_web_request_id = "req-1"
        orchestrator._pending_web_question = "這頁在說什麼"
        result = WebReadResult(url="https://example.com", title="標題", text="網頁內文", error=None)

        orchestrator._on_web_read_result("req-1", result)

        assert orchestrator._expect_web_answer is True
        # 有把加料訊息送去 LLM，且內容帶了網址
        assert mock_controller.start_request.called
        sent_text = mock_controller.start_request.call_args.args[0]
        assert "https://example.com" in sent_text
        # 讀網頁的答覆有給更大的 token 額度
        assert mock_controller.start_request.call_args.kwargs.get("max_tokens")

    def test_web_read_error_shows_bubble_and_no_request(self, orchestrator, mock_controller):
        from doro_app.core.web.reader import WebReadResult

        orchestrator._current_web_request_id = "req-2"
        bubble_spy = Mock()
        orchestrator.bubble_text_requested.connect(bubble_spy)
        result = WebReadResult(url="https://x.test", title="", text="", error="連不上啦")

        orchestrator._on_web_read_result("req-2", result)

        assert orchestrator._expect_web_answer is False
        mock_controller.start_request.assert_not_called()
        bubble_spy.assert_called_once()
        assert "連不上啦" in bubble_spy.call_args.args[0]

    def test_send_message_rejects_when_inflight(self, orchestrator, mock_controller):
        """send_message rejects when previous request is inflight."""
        mock_controller.is_inflight = True

        # Connect listener to notification signal
        mock_listener = Mock()
        orchestrator.notification_requested.connect(mock_listener)

        result = orchestrator.send_message("Hello")

        assert result is False
        mock_controller.start_request.assert_not_called()
        # Should emit notification (not silent)
        mock_listener.assert_called_once()
        call_args = mock_listener.call_args[0]
        assert call_args[0] == "info"  # severity
        assert "already replying" in call_args[2].lower()  # message

    def test_send_message_silent_no_notification_when_inflight(self, orchestrator, mock_controller):
        """send_message with silent=True doesn't emit notification when inflight."""
        mock_controller.is_inflight = True

        mock_listener = Mock()
        orchestrator.notification_requested.connect(mock_listener)

        result = orchestrator.send_message("Hello", silent=True)

        assert result is False
        mock_listener.assert_not_called()  # No notification when silent

    def test_send_message_handles_start_failure(self, orchestrator, mock_controller):
        """send_message handles controller start failure."""
        mock_controller.start_request.return_value = (False, "Network error")

        mock_listener = Mock()
        orchestrator.notification_requested.connect(mock_listener)

        result = orchestrator.send_message("Hello")

        assert result is False
        # Should emit notification with error
        mock_listener.assert_called_once()
        call_args = mock_listener.call_args[0]
        assert call_args[0] == "warning"  # severity
        assert "Network error" in call_args[2]  # message

    def test_send_message_silent_no_notification_on_failure(self, orchestrator, mock_controller):
        """send_message with silent=True doesn't emit notification on failure."""
        mock_controller.start_request.return_value = (False, "Error")

        mock_listener = Mock()
        orchestrator.notification_requested.connect(mock_listener)

        result = orchestrator.send_message("Hello", silent=True)

        assert result is False
        mock_listener.assert_not_called()


# ═══════════════════════════════════════════════════════════
# Configuration API Tests
# ═══════════════════════════════════════════════════════════


class TestConfigurationAPI:
    """The 14 pass-through getters/setters were replaced by one `settings`
    accessor exposing the controller's ChatSettings directly (backlog #5)."""

    def test_settings_exposes_controller_settings(self, orchestrator, mock_controller):
        """orchestrator.settings returns the controller's settings object,
        so UI code reaches settings without a forwarding layer."""
        assert orchestrator.settings is mock_controller.settings

    def test_clear_history(self, orchestrator, mock_controller):
        """clear_history delegates to controller."""
        orchestrator.clear_history()
        mock_controller.clear_history.assert_called_once()


# ═══════════════════════════════════════════════════════════
# Property Tests
# ═══════════════════════════════════════════════════════════


class TestProperties:
    """Test orchestrator properties."""

    def test_is_inflight_delegates_to_controller(self, orchestrator, mock_controller):
        """is_inflight property delegates to controller."""
        mock_controller.is_inflight = False
        assert orchestrator.is_inflight is False

        mock_controller.is_inflight = True
        assert orchestrator.is_inflight is True


# ═══════════════════════════════════════════════════════════
# Event Handler Tests
# ═══════════════════════════════════════════════════════════


class TestEventHandlers:
    """Test internal event handlers."""

    def test_on_request_started_emits_busy_cursor(self, orchestrator):
        """_on_request_started emits busy cursor signal."""
        mock_listener = Mock()
        orchestrator.busy_cursor_requested.connect(mock_listener)

        # Trigger handler directly
        orchestrator._on_request_started("Hello", False)

        mock_listener.assert_called_once_with(True)

    def test_on_request_succeeded_emits_bubble_text(self, orchestrator):
        """_on_request_succeeded emits bubble text signal."""
        mock_listener = Mock()
        orchestrator.bubble_text_requested.connect(mock_listener)

        # Trigger handler with simple response
        orchestrator._on_request_succeeded("Hello there!", False)

        # Should emit bubble text
        mock_listener.assert_called()
        call_args = mock_listener.call_args[0]
        assert "Hello there!" in call_args[0]

    def test_on_request_failed_emits_bubble_text(self, orchestrator):
        """_on_request_failed emits bubble text with fallback message."""
        mock_listener = Mock()
        orchestrator.bubble_text_requested.connect(mock_listener)

        # Trigger handler
        orchestrator._on_request_failed("Connection timeout", False)

        # Should emit bubble text (not notification)
        mock_listener.assert_called_once()
        call_args = mock_listener.call_args[0]
        # First arg is the text (should be fallback message, not the error)
        assert isinstance(call_args[0], str)
        assert len(call_args[0]) > 0  # Has some text
        # Second arg is kwargs dict
        assert isinstance(call_args[1], dict)
        assert call_args[1].get("auto_hide") is True

    def test_on_request_failed_auto_no_bubble(self, orchestrator):
        """_on_request_failed doesn't emit bubble text for auto requests."""
        mock_listener = Mock()
        orchestrator.bubble_text_requested.connect(mock_listener)

        # Trigger handler with was_auto=True
        orchestrator._on_request_failed("Error", was_auto=True)

        # Should not emit bubble text for auto requests
        mock_listener.assert_not_called()


class TestControlTagLeak:
    """Movement/control-only replies must never show raw tags in the bubble."""

    def test_movement_only_response_clears_bubble_without_tag(self, orchestrator):
        text_listener = Mock()
        clear_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)
        orchestrator.bubble_clear_requested.connect(clear_listener)

        orchestrator._on_request_succeeded("[MOVE:dir=right]", False)

        clear_listener.assert_called_once()
        # The raw tag must never reach the bubble via any emit.
        for emitted in text_listener.call_args_list:
            assert "MOVE" not in emitted[0][0]
            assert "[" not in emitted[0][0]

    def test_lowercase_move_only_response_clears_bubble(self, orchestrator):
        text_listener = Mock()
        clear_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)
        orchestrator.bubble_clear_requested.connect(clear_listener)

        orchestrator._on_request_succeeded("[move:left]", False)

        clear_listener.assert_called_once()
        text_listener.assert_not_called()

    def test_state_and_mouse_only_response_clears_bubble(self, orchestrator):
        text_listener = Mock()
        clear_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)
        orchestrator.bubble_clear_requested.connect(clear_listener)

        orchestrator._on_request_succeeded("[STATE:walk_right][mouse:click]", False)

        clear_listener.assert_called_once()
        for emitted in text_listener.call_args_list:
            assert "[" not in emitted[0][0]

    def test_dialogue_with_trailing_move_tag_strips_tag(self, orchestrator):
        text_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)

        orchestrator._on_request_succeeded("早安！ [MOVE:dir=right]", False)

        text_listener.assert_called()
        emitted = text_listener.call_args[0][0]
        assert "早安" in emitted
        assert "[" not in emitted and "]" not in emitted


class TestMouseBracketDeferred:
    """Mouse brackets must be enqueued behind move brackets in the dispatcher
    queue, regardless of text order — otherwise a click written before a
    move bracket would fire immediately, bypassing the wait."""

    def _make_orch_with_dispatcher(
        self,
        mock_controller,
        mock_movement_manager,
        mock_state_service,
    ):
        """Wire a fresh orchestrator with mock action_dispatcher/automation
        so we can observe the order in which actions land on the queue."""
        dispatcher = Mock()
        dispatcher.dispatch = Mock()
        automation = Mock()
        schedule = Mock()
        orch = ChatOrchestrator(
            controller=mock_controller,
            movement=mock_movement_manager,
            state_service=mock_state_service,
            automation=automation,
            action_dispatcher=dispatcher,
            schedule=schedule,
        )
        return orch, dispatcher

    def test_click_after_move_keeps_order(
        self,
        mock_controller,
        mock_movement_manager,
        mock_state_service,
    ):
        orch, dispatcher = self._make_orch_with_dispatcher(
            mock_controller,
            mock_movement_manager,
            mock_state_service,
        )
        orch._on_request_succeeded(
            "好！[MOVE:to;x=200;y=100] [mouse:click]",
            False,
        )
        kinds = [c.args[0].kind for c in dispatcher.dispatch.call_args_list]
        assert kinds == ["movement", "click"]

    def test_click_before_move_in_text_still_dispatches_after_move(
        self,
        mock_controller,
        mock_movement_manager,
        mock_state_service,
    ):
        """The defence in depth: even when the LLM puts `[mouse:click]`
        textually before `[move:to;...]`, the orchestrator defers the click
        so the dispatcher receives the movement action first. Without this,
        the click would fire immediately (movement never starts because the
        action queue head is the click action)."""
        orch, dispatcher = self._make_orch_with_dispatcher(
            mock_controller,
            mock_movement_manager,
            mock_state_service,
        )
        orch._on_request_succeeded(
            "好！[mouse:click] [MOVE:to;x=200;y=100]",
            False,
        )
        kinds = [c.args[0].kind for c in dispatcher.dispatch.call_args_list]
        assert kinds == ["movement", "click"]


class TestSimulateResponse:
    """simulate_response injects text through the real reply pipeline."""

    def test_simulate_shows_cleaned_dialogue_and_returns_it(self, orchestrator):
        text_listener = Mock()
        orchestrator.bubble_text_requested.connect(text_listener)

        shown = orchestrator.simulate_response("早安！ [MOVE:dir=right]")

        assert "早安" in shown
        assert "[" not in shown
        text_listener.assert_called()
        assert "[" not in text_listener.call_args[0][0]

    def test_simulate_actions_only_clears_bubble_returns_empty(self, orchestrator):
        clear_listener = Mock()
        orchestrator.bubble_clear_requested.connect(clear_listener)

        shown = orchestrator.simulate_response("[MOVE:dir=right]")

        assert shown == ""
        clear_listener.assert_called_once()
