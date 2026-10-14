"""Command-line entry points for running Doro."""

from __future__ import annotations

import argparse
import sys


def run_chat_test(message: str | None) -> int:
    """Send one chat request through the same structured path the app uses."""
    from .core.chat.chat_reply import CHAT_TASK, chat_reply_model
    from .core.llm import LlmTarget, ask_structured, compose_system
    from .core.llm.transport import resolve_chat_endpoint
    from .utils.config_manager import ConfigManager
    from .utils.paths import PROMPT_PATH
    from .utils.prompts import load_prompt_text

    test_message = (message or "Hello from Doro test!").strip()
    if not test_message:
        print("Chat test aborted: message is empty.")
        return 1

    chat = ConfigManager().chat
    endpoint_url = resolve_chat_endpoint(chat.server_url, chat.endpoint_path)
    if not endpoint_url:
        print("Chat test failed: chat server URL is not configured.")
        return 1

    target = LlmTarget(
        endpoint=endpoint_url,
        model=chat.model,
        api_key=chat.api_key,
        timeout_seconds=chat.timeout_seconds,
        temperature=chat.temperature,
        max_tokens=chat.max_tokens,
        mode=chat.structured_mode,
    )
    # No state service here, so the schema accepts any state text.
    reply_model = chat_reply_model([])
    system = compose_system(load_prompt_text(PROMPT_PATH), CHAT_TASK, reply_model)
    result = ask_structured(target, system, test_message, reply_model, retries=chat.max_retries)
    if result.error:
        print(f"Chat test failed: {result.error}")
        if result.raw:
            print(f"Raw reply: {result.raw}")
        return 1

    reply = result.value
    print("Chat test succeeded.")
    print(f"Assistant: {reply.line}")
    if reply.state:
        print(f"State: {reply.state}")
    if reply.move is not None:
        print(f"Move: {reply.move.movement_token()}")
    if reply.tool is not None:
        print(f"Tool: {reply.tool.model_dump(exclude_none=True)}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run the Doro desktop companion.")
    parser.add_argument(
        "--not-topmost",
        action="store_true",
        help="Do not keep the window always on top.",
    )
    parser.add_argument(
        "--test-chat",
        nargs="?",
        const="",
        metavar="MESSAGE",
        help="Send a test chat request (optionally provide a MESSAGE) and exit.",
    )
    parser.add_argument(
        "--restarted",
        action="store_true",
        help="(internal) Flag indicating the app was relaunched",
    )
    args = parser.parse_args()

    if args.test_chat is not None:
        sys.exit(run_chat_test(args.test_chat))

    from .preflight import preflight_check

    errors, warnings = preflight_check()
    for w in warnings:
        print(f"  ⚠ {w}")
    if errors:
        print("Doro 無法啟動：")
        for e in errors:
            print(f"  ✗ {e}")
        print("\n請確認已在虛擬環境中安裝所有依賴：pip install -e .")
        sys.exit(1)

    from PySide6 import QtWidgets

    from .app import DoroApp
    from .bootstrap import BootstrapError, bootstrap_environment

    qt_app = QtWidgets.QApplication(sys.argv)
    try:
        deps = bootstrap_environment()
        doro_app = DoroApp(not_topmost=args.not_topmost, deps=deps)
    except BootstrapError as exc:
        QtWidgets.QMessageBox.critical(None, "Doro 啟動失敗", str(exc))
        sys.exit(1)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(
            None,
            "Doro 啟動失敗",
            f"未預期的錯誤：{exc}",
        )
        sys.exit(1)

    install_quit_policy(qt_app, doro_app.window)
    from .utils import exit_diagnostics

    diagnostics = exit_diagnostics.install(qt_app, doro_app.window)
    from .ui import topmost_guard

    _guard = topmost_guard.install(qt_app, log=diagnostics.log if diagnostics is not None else None)
    doro_app.run()
    code = qt_app.exec()
    if diagnostics is not None:
        diagnostics.event_loop_ended(code)
    sys.exit(code)


def install_quit_policy(qt_app, window) -> None:
    """Quit only via "Exit doro" or by closing Doro's own main window.

    The main window is a Qt.Tool window (kept off the taskbar), and Qt does not
    count Tool windows as primary windows. With Qt's default
    quitOnLastWindowClosed, closing any ordinary dialog (state manager, asset
    factory, ...) therefore looked like "the last window closed" and quit Doro.
    """
    from PySide6 import QtWidgets

    qt_app.setQuitOnLastWindowClosed(False)
    window.closed.connect(QtWidgets.QApplication.quit)
