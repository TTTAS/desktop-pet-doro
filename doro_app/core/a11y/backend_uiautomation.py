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
import os
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

# Env-var gate for the UIA failure trace. Default ON during the current
# debugging window — flip to "0" / "false" to silence. The trace fires
# only when the invoke ultimately returns False, so production success
# paths stay quiet.
_DIAG_ENV_VAR = "DORO_UIA_DEBUG"
# Cap children printed per hit-test level so a tree with thousands of
# siblings (Chrome DOM occasionally) doesn't drown the log.
_TRACE_CHILDREN_PER_LEVEL = 8


def _diag_enabled() -> bool:
    raw = os.environ.get(_DIAG_ENV_VAR, "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


class _Trace:
    """Append-only diagnostic accumulator for a single invoke attempt.

    Every step that could decide an outcome appends one line. The whole
    block is printed atomically when (and only when) the invoke fails,
    so a successful click stays silent. Attribute reads on UIA controls
    can raise COMError sporadically; ``safe_attr`` swallows those and
    substitutes ``<err>`` so a single attribute hiccup doesn't kill the
    trace.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, line: str) -> None:
        self.lines.append(line)

    def emit(self, x: int, y: int, hwnd: Optional[int], reason: str) -> None:
        if not _diag_enabled():
            return
        header = f"[doro click] uia-trace ({x},{y}) hwnd={hwnd} reason={reason}"
        body = "\n".join(f"  {ln}" for ln in self.lines)
        print(f"{header}\n{body}" if body else header, flush=True)


def _safe_attr(obj, name: str, fallback: str = "<err>") -> str:
    try:
        val = getattr(obj, name)
    except Exception:
        return fallback
    if val is None:
        return "<none>"
    return str(val)


def _safe_bounds(control) -> str:
    try:
        r = control.BoundingRectangle
        return f"({int(r.left)},{int(r.top)})-({int(r.right)},{int(r.bottom)})"
    except Exception:
        return "<err>"


def _describe_control(control) -> str:
    if control is None:
        return "<none>"
    return (
        f"type={_safe_attr(control, 'ControlTypeName')} "
        f"class={_safe_attr(control, 'ClassName')} "
        f"name={_safe_attr(control, 'Name')!r} "
        f"pid={_safe_attr(control, 'ProcessId')} "
        f"bounds={_safe_bounds(control)}"
    )


def _supported_patterns(control) -> str:
    """Probe a few commonly-checked patterns by Get*Pattern() — cheap and
    enough to tell us why an element refused Invoke."""
    candidates = (
        "InvokePattern",
        "LegacyIAccessiblePattern",
        "TogglePattern",
        "SelectionItemPattern",
        "ExpandCollapsePattern",
    )
    found: list[str] = []
    for name in candidates:
        getter = getattr(control, f"Get{name}", None)
        if getter is None:
            continue
        try:
            pat = getter()
        except Exception:
            continue
        if pat is not None:
            found.append(name)
    return "[" + ", ".join(found) + "]"

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
            # Pre-import failure: no trace possible (no auto module).
            if _diag_enabled():
                print(
                    f"[doro click] uia-trace ({x},{y}) hwnd={hwnd} "
                    f"reason=uiautomation_import_failed\n  {exc}",
                    flush=True,
                )
            return False

        initializer = getattr(auto, "UIAutomationInitializerInThread", None)
        ctx = initializer() if initializer is not None else contextlib.nullcontext()
        trace = _Trace()
        trace.add(f"self_pid={os.getpid()}")
        try:
            with ctx:
                target = self._resolve_invoke_target(
                    auto, int(x), int(y), hwnd, trace,
                )
                if target is None:
                    trace.emit(int(x), int(y), hwnd, "no_target_resolved")
                    return False
                ok = self._fire_invoke(target, trace)
                if not ok:
                    trace.emit(int(x), int(y), hwnd, "no_invoke_found")
                return ok
        except Exception as exc:
            logger.debug(f"UIA invoke at ({x},{y}) raised: {exc}")
            trace.add(f"exception={type(exc).__name__}: {exc}")
            trace.emit(int(x), int(y), hwnd, "exception_in_invoke_path")
            return False

    def _resolve_invoke_target(
        self, auto, x: int, y: int, hwnd: Optional[int], trace: _Trace,
    ):
        """Find the deepest UIA control containing (x, y), scoped to hwnd
        when supplied. Returns None when nothing was hit."""
        if hwnd is not None:
            try:
                root = auto.ControlFromHandle(int(hwnd))
            except Exception as exc:
                logger.debug(f"UIA ControlFromHandle({hwnd}) raised: {exc}")
                trace.add(f"ControlFromHandle({hwnd}) raised: {exc}")
                root = None
            if root is None:
                trace.add(f"ControlFromHandle({hwnd}) returned None")
            else:
                trace.add(f"ControlFromHandle({hwnd}) → {_describe_control(root)}")
                hit = self._hit_test_subtree(root, x, y, _HIT_TEST_MAX_DEPTH, trace, 0)
                if hit is not None and hit is not root:
                    trace.add(f"subtree_hit → {_describe_control(hit)}")
                    return hit
                if hit is root:
                    trace.add("subtree_hit was root itself — treating as dead-end")
                else:
                    trace.add("subtree_hit=None (no descendant matched)")
                # hwnd resolved but no subtree element covers (x, y) —
                # likely the cached UIA bounds lag behind a scroll. Fall
                # through to the global lookup rather than dropping the
                # click outright.
        try:
            fallback = auto.ControlFromPoint(int(x), int(y))
        except Exception as exc:
            logger.debug(f"UIA ControlFromPoint({x},{y}) raised: {exc}")
            trace.add(f"ControlFromPoint({x},{y}) raised: {exc}")
            return None
        trace.add(f"ControlFromPoint({x},{y}) → {_describe_control(fallback)}")
        return fallback

    def _hit_test_subtree(
        self, root, x: int, y: int, depth_left: int, trace: _Trace, depth: int,
    ):
        """Return the deepest descendant of ``root`` whose bounding rect
        contains (x, y), or None. Depth-bounded so a pathological tree
        cannot exhaust the invoke budget."""
        if depth_left <= 0:
            trace.add(f"hit_test depth={depth} max_depth_reached — using root")
            return root
        try:
            children = root.GetChildren()
        except Exception as exc:
            trace.add(f"hit_test depth={depth} GetChildren raised: {exc}")
            children = []
        if depth <= 2:
            trace.add(
                f"hit_test depth={depth} root={_safe_attr(root, 'ControlTypeName')} "
                f"children={len(children)}"
            )
        best = None
        for idx, child in enumerate(children):
            try:
                rect = child.BoundingRectangle
            except Exception as exc:
                if depth == 0 and idx < _TRACE_CHILDREN_PER_LEVEL:
                    trace.add(
                        f"hit_test depth={depth} child#{idx} BoundingRectangle raised: {exc}"
                    )
                continue
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                continue
            contains = rect.left <= x < rect.right and rect.top <= y < rect.bottom
            if depth == 0 and idx < _TRACE_CHILDREN_PER_LEVEL:
                trace.add(
                    f"hit_test depth={depth} child#{idx} "
                    f"type={_safe_attr(child, 'ControlTypeName')} "
                    f"bounds=({int(rect.left)},{int(rect.top)})-({int(rect.right)},{int(rect.bottom)}) "
                    f"contains={contains}"
                )
            if contains:
                deeper = self._hit_test_subtree(
                    child, x, y, depth_left - 1, trace, depth + 1,
                )
                # Prefer the deepest hit. Multiple children may overlap
                # (e.g. overlapping panes in DPI-scaled layouts) — last
                # match wins, matching ControlFromPoint's z-order pick.
                best = deeper if deeper is not None else child
        if depth == 0 and len(children) > _TRACE_CHILDREN_PER_LEVEL:
            trace.add(
                f"hit_test depth={depth} … (+{len(children) - _TRACE_CHILDREN_PER_LEVEL} more children not shown)"
            )
        return best if best is not None else root

    def _fire_invoke(self, target, trace: _Trace) -> bool:
        """Try InvokePattern on ``target`` then on a few ancestors."""
        node = target
        for level in range(4):  # element + 3 ancestors covers toolbar-button wrappers
            if node is None:
                trace.add(f"fire_invoke level={level} node=None — stop")
                return False
            patterns = _supported_patterns(node)
            try:
                pattern = node.GetInvokePattern()
            except Exception as exc:
                logger.debug(f"UIA GetInvokePattern raised: {exc}")
                trace.add(
                    f"fire_invoke level={level} "
                    f"{_describe_control(node)} patterns={patterns} "
                    f"GetInvokePattern raised: {exc}"
                )
                pattern = None
            else:
                trace.add(
                    f"fire_invoke level={level} "
                    f"{_describe_control(node)} patterns={patterns} "
                    f"has_invoke={pattern is not None}"
                )
            if pattern is not None:
                try:
                    pattern.Invoke()
                    return True
                except Exception as exc:
                    logger.debug(f"UIA Invoke() raised: {exc}")
                    trace.add(f"fire_invoke level={level} Invoke() raised: {exc}")
                    return False
            try:
                node = node.GetParentControl()
            except Exception as exc:
                trace.add(f"fire_invoke level={level} GetParentControl raised: {exc}")
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
