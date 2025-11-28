"""Command-line entry points for running Doro."""

from __future__ import annotations

import argparse
import sys

from PySide6 import QtCore, QtWidgets

from .utils.actions import parse_actions_from_text
from .core.chat.chat import perform_chat_request, resolve_chat_endpoint
from .utils.config_defaults import (
    DEFAULT_CHAT_SERVER_URL,
    DEFAULT_CHAT_MODEL,
    DEFAULT_CHAT_ENDPOINT_PATH,
)
from .constants import CHAT_DEFAULT_TIMEOUT_SECONDS, CHAT_DEFAULT_TEMPERATURE
from .utils.paths import PROMPT_PATH
from .utils.prompts import load_prompt_text
from .bootstrap import BootstrapError, bootstrap_environment
from .app import DoroApp


def run_chat_test(message: str | None) -> int:
    test_message = (message or "Hello from Doro test!").strip()
    if not test_message:
        print("Chat test aborted: message is empty.")
        return 1

    prompt_path = PROMPT_PATH
    system_prompt = load_prompt_text(prompt_path)

    settings = QtCore.QSettings("doro-pet", "doro")
    server_url = settings.value("chat/server_url", DEFAULT_CHAT_SERVER_URL, str)
    model = settings.value("chat/model", DEFAULT_CHAT_MODEL, str)
    endpoint_path = settings.value("chat/endpoint_path", DEFAULT_CHAT_ENDPOINT_PATH, str)
    timeout_value = settings.value("chat/timeout_seconds", CHAT_DEFAULT_TIMEOUT_SECONDS)
    temp_value = settings.value("chat/temperature", CHAT_DEFAULT_TEMPERATURE)

    try:
        timeout_seconds = int(timeout_value)
    except (TypeError, ValueError):
        timeout_seconds = CHAT_DEFAULT_TIMEOUT_SECONDS

    try:
        temperature = float(temp_value)
    except (TypeError, ValueError):
        temperature = CHAT_DEFAULT_TEMPERATURE

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

    qt_app = QtWidgets.QApplication(sys.argv)
    try:
        deps = bootstrap_environment()
    except BootstrapError as exc:
        print(f"Failed to start Doro: {exc}")
        sys.exit(1)

    doro_app = DoroApp(not_topmost=args.not_topmost, deps=deps)
    doro_app.run()
    sys.exit(qt_app.exec())
