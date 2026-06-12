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
        # Foreground-verification hooks (M2). Defaults to None on both
        # sides — the manager treats "any None" as "can't check" and
        # skips the gate. Existing tests therefore see no behaviour
        # change; tests that want to exercise the gate set both fields.
        self.handle_at_default: Optional[int] = None
        self.handle_at_map: dict[tuple[int, int], int] = {}
        self.foreground_handle: Optional[int] = None

    # InputBackendPort ---------------------------------------------------

    def read_window_class_at(self, x: int, y: int) -> Optional[str]:
        key = (int(x), int(y))
        if key in self.window_class_at:
            return self.window_class_at[key]
        return self.window_class_default

    def read_handle_at(self, x: int, y: int) -> Optional[int]:
        key = (int(x), int(y))
        if key in self.handle_at_map:
            return self.handle_at_map[key]
        return self.handle_at_default

    def read_foreground_window_handle(self) -> Optional[int]:
        return self.foreground_handle

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
        screen_origin: tuple[int, int] = (0, 0),
        dpr: float = 1.0,
    ) -> None:
        self._foot_logical = foot_logical
        self._foot_physical = foot_physical or foot_logical
        self._screen_size = screen_size
        self._screen_origin = screen_origin
        self._dpr = dpr
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

    def screen_geometry_physical(self) -> tuple[int, int, int, int]:
        return (
            self._screen_origin[0],
            self._screen_origin[1],
            self._screen_size[0],
            self._screen_size[1],
        )

    def device_pixel_ratio(self) -> float:
        return self._dpr

    # Test conveniences --------------------------------------------------

    def move_foot_to(self, logical: tuple[int, int], physical: Optional[tuple[int, int]] = None) -> None:
        """Simulate the user dragging Doro to a new position during wind-up."""
        self._foot_logical = logical
        self._foot_physical = physical or logical
