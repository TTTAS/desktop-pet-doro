"""Windows UI Automation (UIA) accessibility backend (Phase 1d).

Walks the focused window's control subtree and emits :class:`A11yElement`
for each interactable control. The ``uiautomation`` package (and its
``comtypes`` dependency) is an optional extra — it is imported lazily so
the rest of the app runs fine without it. Any failure (missing package,
COM error, unreadable window) yields ``None`` = "no tree available".

Untestable on the Linux dev/CI target; covered manually on Windows.
"""

from __future__ import annotations

import contextlib
from typing import Optional

from .models import A11yElement
from ...utils.logger import get_logger

logger = get_logger("doro.a11y")

# Cap traversal so a pathological tree can't stall the read thread.
_MAX_NODES_VISITED = 2000

# Cap the hit-test walk inside invoke_at_physical_point. Goes deep enough
# for real UIs (Chrome → frame → content document → DOM subtree) but
# bounded so a buggy provider can't burn the 2s invoke budget on its own.
_HIT_TEST_MAX_DEPTH = 30

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

        # A11yService runs this on a ThreadPoolExecutor worker; comtypes'
        # implicit COM init only fires on whichever thread imports it
        # first, so other workers raise COMError on UIA calls. Wrap the
        # whole walk in `UIAutomationInitializerInThread` to apply the
        # correct CoInitializeEx / CoUninitialize per worker per call.
        # Fallback to a no-op context for older `uiautomation` versions
        # (then we accept the original implicit-init behaviour).
        initializer = getattr(auto, "UIAutomationInitializerInThread", None)
        ctx = initializer() if initializer is not None else contextlib.nullcontext()
        try:
            with ctx:
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

    def invoke_at_physical_point(
        self, x: int, y: int, hwnd: Optional[int] = None,
    ) -> bool:
        """UIA InvokePattern fire-and-forget at the screen point.

        Used by `AutomationManager` to fire a click without moving the
        OS cursor.

        Scoping: when ``hwnd`` is supplied, the lookup is anchored at
        ``ControlFromHandle(hwnd)`` and walks that subtree. The manager
        passes the hwnd it already resolved with ``CWP_SKIPTRANSPARENT``,
        so Doro's sprite — visible in the unscoped UIA tree because UIA
        ignores ``WS_EX_TRANSPARENT`` — is excluded. Without scoping,
        ``ControlFromPoint`` walks the global tree from the desktop root
        and Doro on top of the target wins the hit-test, then we burn
        the invoke budget climbing a useless subtree.

        ``GetInvokePattern`` is None for elements that don't expose
        Invoke (canvas / custom widgets); we then climb a few ancestors
        looking for one (toolbar buttons are commonly wrapped). Still
        nothing → return False so the manager surfaces NOT_INVOCABLE.
        """
        try:
            import uiautomation as auto
        except Exception as exc:
            logger.debug(f"uiautomation unavailable for invoke: {exc}")
            return False

        initializer = getattr(auto, "UIAutomationInitializerInThread", None)
        ctx = initializer() if initializer is not None else contextlib.nullcontext()
        try:
            with ctx:
                target = self._resolve_invoke_target(auto, int(x), int(y), hwnd)
                if target is None:
                    return False
                return self._fire_invoke(target)
        except Exception as exc:
            logger.debug(f"UIA invoke at ({x},{y}) raised: {exc}")
            return False

    def _resolve_invoke_target(self, auto, x: int, y: int, hwnd: Optional[int]):
        """Find the deepest UIA control containing (x, y), scoped to hwnd
        when supplied. Returns None when nothing was hit."""
        if hwnd is not None:
            try:
                root = auto.ControlFromHandle(int(hwnd))
            except Exception as exc:
                logger.debug(f"UIA ControlFromHandle({hwnd}) raised: {exc}")
                root = None
            if root is not None:
                hit = self._hit_test_subtree(root, x, y, _HIT_TEST_MAX_DEPTH)
                if hit is not None:
                    return hit
                # hwnd resolved but no subtree element covers (x, y) —
                # likely the cached UIA bounds lag behind a scroll. Fall
                # through to the global lookup rather than dropping the
                # click outright.
        try:
            return auto.ControlFromPoint(int(x), int(y))
        except Exception as exc:
            logger.debug(f"UIA ControlFromPoint({x},{y}) raised: {exc}")
            return None

    def _hit_test_subtree(self, root, x: int, y: int, depth_left: int):
        """Return the deepest descendant of ``root`` whose bounding rect
        contains (x, y), or None. Depth-bounded so a pathological tree
        cannot exhaust the invoke budget."""
        if depth_left <= 0:
            return root
        try:
            children = root.GetChildren()
        except Exception:
            children = []
        best = None
        for child in children:
            try:
                rect = child.BoundingRectangle
            except Exception:
                continue
            # Some controls report a zero-size rect — skip; they can't
            # be the target and walking into them wastes the budget.
            if (rect.right - rect.left) <= 0 or (rect.bottom - rect.top) <= 0:
                continue
            if rect.left <= x < rect.right and rect.top <= y < rect.bottom:
                deeper = self._hit_test_subtree(child, x, y, depth_left - 1)
                # Prefer the deepest hit. Multiple children may overlap
                # (e.g. overlapping panes in DPI-scaled layouts) — last
                # match wins, matching ControlFromPoint's z-order pick.
                best = deeper if deeper is not None else child
        return best if best is not None else root

    def _fire_invoke(self, target) -> bool:
        """Try InvokePattern on ``target`` then on a few ancestors."""
        node = target
        for _ in range(4):  # element + 3 ancestors covers toolbar-button wrappers
            if node is None:
                return False
            try:
                pattern = node.GetInvokePattern()
            except Exception as exc:
                logger.debug(f"UIA GetInvokePattern raised: {exc}")
                pattern = None
            if pattern is not None:
                try:
                    pattern.Invoke()
                    return True
                except Exception as exc:
                    logger.debug(f"UIA Invoke() raised: {exc}")
                    return False
            try:
                node = node.GetParentControl()
            except Exception:
                return False
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
