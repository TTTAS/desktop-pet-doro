"""Windows UI Automation (UIA) accessibility backend (Phase 1d).

Walks the focused window's control subtree and emits :class:`A11yElement`
for each interactable control. The ``uiautomation`` package (and its
``comtypes`` dependency) is an optional extra — it is imported lazily so
the rest of the app runs fine without it. Any failure (missing package,
COM error, unreadable window) yields ``None`` = "no tree available".

Untestable on the Linux dev/CI target; covered manually on Windows.
"""

from __future__ import annotations

from typing import Optional

from .models import A11yElement
from ...utils.logger import get_logger

logger = get_logger("doro.a11y")

# Cap traversal so a pathological tree can't stall the read thread.
_MAX_NODES_VISITED = 2000

# UIA ControlTypeName -> our normalized role vocabulary.
_ROLE_MAP = {
    "ButtonControl": "button",
    "HyperlinkControl": "link",
    "EditControl": "input",
    "MenuItemControl": "menuitem",
    "ComboBoxControl": "combobox",
    "CheckBoxControl": "checkbox",
    "RadioButtonControl": "radiobutton",
    "TabItemControl": "tab",
}


class UIAutomationBackend:  # pragma: no cover - needs Windows + uiautomation
    """Reads the focused window subtree via Windows UI Automation."""

    def __init__(self) -> None:
        # Populated on every read_elements() call so the preview/diagnostic can
        # explain *why* a read came back empty instead of a vague message.
        self.last_error: Optional[str] = None
        self.last_visited: int = 0
        self.last_found: int = 0

    def read_elements(self, handle: int) -> Optional[list[A11yElement]]:
        self.last_error = None
        self.last_visited = 0
        self.last_found = 0
        try:
            import uiautomation as auto
        except Exception as exc:
            self.last_error = f"uiautomation 無法載入：{exc}"
            logger.debug(f"uiautomation unavailable: {exc}")
            return None

        try:
            root = auto.ControlFromHandle(int(handle))
            if root is None:
                self.last_error = f"ControlFromHandle 取不到視窗根節點（handle={handle}）"
                return None
            elements: list[A11yElement] = []
            counter = [0]
            self._walk(root, elements, counter)
            self.last_visited = counter[0]
            self.last_found = len(elements)
            return elements
        except Exception as exc:
            self.last_error = f"UIA 讀取例外：{type(exc).__name__}: {exc}"
            logger.debug(f"UIA read failed: {exc}")
            return None

    def _walk(self, control, out: list[A11yElement], counter: list[int]) -> None:
        if counter[0] >= _MAX_NODES_VISITED:
            return
        counter[0] += 1

        try:
            role = _ROLE_MAP.get(control.ControlTypeName)
        except Exception:
            role = None

        if role is not None:
            element = self._to_element(control, role)
            if element is not None:
                out.append(element)

        try:
            children = control.GetChildren()
        except Exception:
            children = []
        for child in children:
            self._walk(child, out, counter)

    def invoke_at_physical_point(self, x: int, y: int) -> bool:
        """UIA InvokePattern fire-and-forget at the screen point.

        Used by `AutomationManager` to fire a click without moving the
        OS cursor. ``ControlFromPoint`` walks the UIA tree to find the
        leaf at (x, y); ``GetInvokePattern`` is None for elements that
        don't expose Invoke (canvas / custom widgets) — in that case we
        return False so the manager surfaces NOT_INVOCABLE rather than
        silently doing nothing.
        """
        try:
            import uiautomation as auto
        except Exception as exc:
            logger.debug(f"uiautomation unavailable for invoke: {exc}")
            return False
        try:
            control = auto.ControlFromPoint(int(x), int(y))
        except Exception as exc:
            logger.debug(f"UIA ControlFromPoint({x},{y}) raised: {exc}")
            return False
        if control is None:
            return False
        try:
            pattern = control.GetInvokePattern()
        except Exception as exc:
            logger.debug(f"UIA GetInvokePattern raised: {exc}")
            return False
        if pattern is None:
            return False
        try:
            pattern.Invoke()
            return True
        except Exception as exc:
            logger.debug(f"UIA Invoke() raised: {exc}")
            return False

    def _to_element(self, control, role: str) -> Optional[A11yElement]:
        try:
            rect = control.BoundingRectangle
            x, y = int(rect.left), int(rect.top)
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
        except Exception:
            return None

        # Off-screen / zero-size controls aren't clickable — skip them.
        if width <= 0 or height <= 0:
            return None

        try:
            name = (control.Name or "").strip()
        except Exception:
            name = ""

        is_password = False
        try:
            is_password = bool(getattr(control, "IsPassword", False))
        except Exception:
            is_password = False

        value: Optional[str] = None
        if role == "input":
            try:
                pattern = control.GetValuePattern()
                value = (pattern.Value or "").strip() or None
            except Exception:
                value = None

        return A11yElement(
            role=role,
            name=name,
            x=x,
            y=y,
            width=width,
            height=height,
            value=value,
            is_password=is_password,
        )
