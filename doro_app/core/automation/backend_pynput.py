"""Real input backend, layered over pynput.

`pynput.mouse.Listener` (for the left-button-state observer used by drag
grace) and `pynput.keyboard.Listener` (for the Esc kill-switch) are
touched. Synthetic mouse clicking moved out of this backend — production
now fires via UIA InvokePattern (see `core/a11y/clicker.py`) so the
user's OS cursor does not move on every automated click.

The Listener is filtered to Esc on the very first line of its callback;
this is by design and is part of the privacy contract documented in the
plan. No other key data is logged, stored, or forwarded.

Foreground-window class lookup is platform-specific (Xlib on X11, ctypes
on Windows). Both fall back to None on error; AutomationManager treats a
missing class as "not in allowlist" and refuses to fire.
"""

from __future__ import annotations

from typing import Callable, Optional

from ...utils.logger import get_logger

logger = get_logger("doro.automation.backend")


class PynputBackend:
    """`InputBackendPort` implementation backed by pynput + platform APIs."""

    def __init__(self) -> None:
        # Defer the pynput import so importing this module on a system
        # without pynput doesn't break (Doro can run without automation).
        try:
            from pynput import mouse as _mouse
            from pynput import keyboard as _keyboard
        except ImportError as exc:  # pragma: no cover - install-time path
            raise RuntimeError(
                "pynput is required for automation; install with: pip install pynput"
            ) from exc

        # Mouse controller is no longer used for synthetic clicks (UIA
        # InvokePattern handles that) — kept import-only for the mouse
        # button-state listener installed below.
        self._Button = _mouse.Button
        self._Key = _keyboard.Key
        self._Listener = _keyboard.Listener

        self._listener: Optional[_keyboard.Listener] = None
        self._left_pressed = False
        self._mouse_listener: Optional[_mouse.Listener] = None
        self._install_mouse_state_listener(_mouse)

    # ------------------------------------------------------------------ InputBackendPort

    def read_window_class_at(self, x: int, y: int) -> Optional[str]:
        from .window_class import read_at

        return read_at(x, y)

    def read_handle_at(self, x: int, y: int) -> Optional[int]:
        from .window_class import read_handle_at

        return read_handle_at(x, y)

    def read_foreground_window_handle(self) -> Optional[int]:
        from .window_class import read_foreground_window_handle

        return read_foreground_window_handle()

    def read_pid_of_handle(self, handle: int) -> Optional[int]:
        from .window_class import pid_for_handle

        try:
            return pid_for_handle(int(handle))
        except Exception:
            return None

    def read_class_of_handle(self, handle: int) -> Optional[str]:
        from .window_class import window_class_for_handle

        try:
            return window_class_for_handle(int(handle))
        except Exception:
            return None

    def is_left_button_pressed(self) -> bool:
        return self._left_pressed

    def install_esc_listener(self, on_esc: Callable[[], None]) -> None:
        Key = self._Key

        def _on_press(key) -> None:
            # ─── Privacy contract ─────────────────────────────────────────
            # First line: reject every non-Esc key. We do NOT log, store,
            # forward, or branch on any other key's identity. Unit tests in
            # tests/core/automation/test_backend_listener.py guard this.
            if key != Key.esc:
                return
            try:
                on_esc()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Esc callback raised")

        self._listener = self._Listener(on_press=_on_press)
        self._listener.daemon = True
        self._listener.start()

    def shutdown(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # pragma: no cover
                pass
            self._listener = None
        if self._mouse_listener is not None:
            try:
                self._mouse_listener.stop()
            except Exception:  # pragma: no cover
                pass
            self._mouse_listener = None

    # ------------------------------------------------------------------ Internals

    def _install_mouse_state_listener(self, mouse_module) -> None:
        """Track the left-button state by listening to mouse events.

        pynput.mouse has no "is currently pressed" query; we maintain a
        flag from the on_click stream instead.
        """

        def _on_click(_x, _y, button, pressed) -> None:
            if button == self._Button.left:
                self._left_pressed = bool(pressed)

        try:
            self._mouse_listener = mouse_module.Listener(on_click=_on_click)
            self._mouse_listener.daemon = True
            self._mouse_listener.start()
        except Exception:  # pragma: no cover - some platforms restrict listeners
            logger.warning("Mouse state listener unavailable; drag-grace will be best-effort")
            self._mouse_listener = None


# Platform-specific window-class readers were moved to ``window_class.py``
# so they can be reused (without the pynput dependency) by the LLM context
# injection in ``DoroApp._build_doro_state_text``.
