"""Test doubles for the automation subsystem.

These let `AutomationManager` be exercised without pynput, without a
display server, and without spawning background threads. Tests can drive
the foreground-window class string, mouse-button state, and Esc callbacks
deterministically.
"""

from __future__ import annotations

from typing import Callable, Optional


class FakeInputBackend:
    """In-memory recorder for the :class:`InputBackendPort` protocol.

    Synthetic clicking is no longer the input backend's responsibility —
    see :class:`FakeA11yClicker` (records ``invoke_calls``) for the
    cursor-free UIA InvokePattern path that replaced ``click_left``.
    """

    def __init__(self) -> None:
        self.window_class_at: dict[tuple[int, int], str] = {}
        self.window_class_default: Optional[str] = None
        self.left_button_pressed: bool = False
        self.esc_callback: Optional[Callable[[], None]] = None
        self.shutdown_called: bool = False

    # InputBackendPort ---------------------------------------------------

    def read_window_class_at(self, x: int, y: int) -> Optional[str]:
        key = (int(x), int(y))
        if key in self.window_class_at:
            return self.window_class_at[key]
        return self.window_class_default

    def is_left_button_pressed(self) -> bool:
        return self.left_button_pressed

    def install_esc_listener(self, on_esc: Callable[[], None]) -> None:
        self.esc_callback = on_esc

    def shutdown(self) -> None:
        self.shutdown_called = True

    # Test conveniences --------------------------------------------------

    def set_window_class(self, class_name: Optional[str]) -> None:
        """Set the class returned for any point not otherwise mapped."""
        self.window_class_default = class_name

    def press_esc(self) -> None:
        if self.esc_callback is not None:
            self.esc_callback()


class FakeA11yClicker:
    """In-memory recorder for the :class:`A11yClickerPort` protocol.

    Replaces the legacy ``FakeInputBackend.click_calls`` assertion path —
    tests now assert against ``invoke_calls`` to verify the cursor-free
    click fired at the expected coordinate. Set ``should_succeed=False``
    to simulate "no InvokePattern" (canvas / custom widget) and exercise
    the :data:`ClickOutcome.NOT_INVOCABLE` path.
    """

    def __init__(self, *, should_succeed: bool = True) -> None:
        self.invoke_calls: list[tuple[int, int]] = []
        self.should_succeed = bool(should_succeed)

    def try_invoke_at(self, x: int, y: int) -> bool:
        self.invoke_calls.append((int(x), int(y)))
        return self.should_succeed


class FakeAutomationWindow:
    """Stand-in for the Doro window in automation tests."""

    def __init__(
        self,
        *,
        foot_logical: tuple[int, int] = (100, 100),
        foot_physical: Optional[tuple[int, int]] = None,
        screen_size: tuple[int, int] = (1920, 1080),
    ) -> None:
        self._foot_logical = foot_logical
        self._foot_physical = foot_physical or foot_logical
        self._screen_size = screen_size
        self.mouse_transparent: bool = False
        self.transparent_toggles: list[bool] = []

    def foot_position_logical(self) -> tuple[int, int]:
        return self._foot_logical

    def foot_position_physical(self) -> tuple[int, int]:
        return self._foot_physical

    def set_mouse_transparent(self, transparent: bool) -> None:
        self.mouse_transparent = transparent
        self.transparent_toggles.append(transparent)

    def screen_size_logical(self) -> tuple[int, int]:
        return self._screen_size

    def screen_size_physical(self) -> tuple[int, int]:
        return self._screen_size

    # Test conveniences --------------------------------------------------

    def move_foot_to(self, logical: tuple[int, int], physical: Optional[tuple[int, int]] = None) -> None:
        """Simulate the user dragging Doro to a new position during wind-up."""
        self._foot_logical = logical
        self._foot_physical = physical or logical
