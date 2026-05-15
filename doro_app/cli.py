"""Command-line entry points for running Doro."""

from __future__ import annotations

import argparse
import sys


def run_chat_test(message: str | None) -> int:
    from .utils.actions import parse_actions_from_text
    from .core.chat.chat import perform_chat_request, resolve_chat_endpoint
    from .utils.config_manager import ConfigManager
    from .utils.paths import PROMPT_PATH
    from .utils.prompts import load_prompt_text

    test_message = (message or "Hello from Doro test!").strip()
    if not test_message:
        print("Chat test aborted: message is empty.")
        return 1

    prompt_path = PROMPT_PATH
    system_prompt = load_prompt_text(prompt_path)

    config_manager = ConfigManager()
    server_url = config_manager.chat.server_url
    model = config_manager.chat.model
    endpoint_path = config_manager.chat.endpoint_path
    timeout_seconds = config_manager.chat.timeout_seconds
    temperature = config_manager.chat.temperature

    endpoint_url = resolve_chat_endpoint(server_url, endpoint_path)
    if not endpoint_url:
        print("Chat test failed: chat server URL is not configured.")
        return 1

    messages: list[dict[str, str]] = []
    system_prompt = (system_prompt or "").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": test_message})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    assistant_text, error_message = perform_chat_request(
        endpoint_url,
        payload,
        timeout_seconds,
    )
    if error_message:
        print(f"Chat test failed: {error_message}")
        return 1

    print("Chat test succeeded.")
    if assistant_text:
        display_text, actions = parse_actions_from_text(assistant_text)
        if actions:
            printable = [f"{kind}:{token}" for kind, token in actions]
            print(f"Recognized actions: {', '.join(printable)}")
        if display_text:
            print(f"Assistant: {display_text}")
        else:
            print("Assistant response contained only action trigger(s).")
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

    # --- Preflight: check environment before importing PySide6 ---
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

    # --- Safe to import PySide6 now ---
    from PySide6 import QtWidgets

    from .bootstrap import BootstrapError, bootstrap_environment
    from .app import DoroApp

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

    doro_app.run()
    sys.exit(qt_app.exec())
