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

    def read_elements(self, handle: int) -> Optional[list[A11yElement]]:
        try:
            import uiautomation as auto
        except Exception as exc:
            logger.debug(f"uiautomation unavailable: {exc}")
            return None

        try:
            root = auto.ControlFromHandle(int(handle))
            if root is None:
                return None
            elements: list[A11yElement] = []
            self._walk(root, elements, [0])
            return elements
        except Exception as exc:
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
