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

from ...utils.logger import get_logger
from .models import A11yElement

logger = get_logger("doro.a11y")

# Cap traversal so a pathological tree can't stall the read thread.
_MAX_NODES_VISITED = 2000

# Cap the hit-test walk inside invoke_at_physical_point. Goes deep enough
# for real UIs (Chrome → frame → content document → DOM subtree) but
# bounded so a buggy provider can't burn the 2s invoke budget on its own.
_HIT_TEST_MAX_DEPTH = 30

# Visit cap on the invoke-target DFS. Matches the read_elements walker's
# 2000-node ceiling — empirically enough to cover a maximized Chrome window
# (top chrome + tabs + bookmark bar + page DOM) without running out the
# 2s invoke budget on a pathological tree.
_INVOCABLE_VISIT_LIMIT = 2000

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

    def emit(self, x: int, y: int, hwnd: int | None, reason: str) -> None:
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


def _has_invoke_action(node) -> bool:
    """True iff ``node`` exposes InvokePattern or LegacyIAccessiblePattern.

    Both count as "clickable": Chrome's bookmark-bar items expose
    LegacyIAccessiblePattern.DoDefaultAction() but not Invoke; native
    Win32 buttons expose Invoke; UIA-aware Electron/WPF apps usually
    expose Invoke. We need either to consider an element a valid invoke
    target — which lets the DFS skip 1920×1040 overlay Panes that have
    bounds covering (x, y) but no action.
    """
    for getter_name in ("GetInvokePattern", "GetLegacyIAccessiblePattern"):
        getter = getattr(node, getter_name, None)
        if getter is None:
            continue
        try:
            p = getter()
        except Exception:
            continue
        if p is not None:
            return True
    return False


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
        self.last_error: str | None = None
        self.last_visited: int = 0
        self.last_found: int = 0

    def read_elements(self, handle: int) -> list[A11yElement] | None:
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
        self,
        x: int,
        y: int,
        hwnd: int | None = None,
    ) -> bool:
        """UIA InvokePattern fire-and-forget at the screen point.

        Used by `AutomationManager` to fire a click without moving the
        OS cursor.

        Scoping: when ``hwnd`` is supplied, the lookup is anchored at
        ``ControlFromHandle(hwnd)`` and the subtree is searched for the
        smallest-area descendant that contains (x, y) AND exposes an
        invoke-style pattern (InvokePattern or LegacyIAccessiblePattern).
        Area as tie-breaker is what fixes Chrome: ``BrowserRootView``
        has multiple sibling widgets whose ``BoundingRectangle`` covers
        the full viewport (e.g. ``TopContainerOverlayView``), and the
        old "deepest-containing-leaf" walk would pick whichever one was
        last iterated even though the real button (e.g. a 89×28
        bookmark) sits in another sibling — the size comparison now
        favours the actual leaf.

        When the scoped DFS finds nothing invocable, falls back to
        ``ControlFromPoint`` (with a self-pid guard so Doro's own
        sprite on top can't be selected as the target).
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
                    auto,
                    int(x),
                    int(y),
                    hwnd,
                    trace,
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
        self,
        auto,
        x: int,
        y: int,
        hwnd: int | None,
        trace: _Trace,
    ):
        """Pick a UIA control to Invoke at (x, y).

        With ``hwnd``: DFS the subtree rooted at ``ControlFromHandle(hwnd)``
        and return the smallest-area descendant that contains (x, y) and
        exposes an invoke-style pattern. Without ``hwnd``, or when the
        DFS turns up nothing, fall back to global ``ControlFromPoint``
        (with a self-pid guard so Doro's own sprite can't shadow).
        """
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
                best = self._find_invocable_in_subtree(root, x, y, trace)
                if best is not None:
                    return best
                trace.add(
                    "no invocable descendant under scoped subtree; "
                    "falling back to global ControlFromPoint"
                )
        try:
            fallback = auto.ControlFromPoint(int(x), int(y))
        except Exception as exc:
            logger.debug(f"UIA ControlFromPoint({x},{y}) raised: {exc}")
            trace.add(f"ControlFromPoint({x},{y}) raised: {exc}")
            return None
        if fallback is None:
            trace.add(f"ControlFromPoint({x},{y}) returned None")
            return None
        try:
            fb_pid = int(fallback.ProcessId)
        except Exception:
            fb_pid = -1
        if fb_pid == os.getpid():
            trace.add(
                f"ControlFromPoint hit own pid={fb_pid} (sprite shadow); "
                f"discarding to avoid invoking Doro's own UI"
            )
            return None
        trace.add(f"ControlFromPoint({x},{y}) → {_describe_control(fallback)}")
        return fallback

    def _find_invocable_in_subtree(
        self,
        root,
        x: int,
        y: int,
        trace: _Trace,
    ):
        """DFS ``root``'s subtree for the smallest-area descendant that
        contains (x, y) and exposes an invoke-style pattern. None if no
        candidate is found.

        Smallest-area selection is the fix for Chrome: ``BrowserRootView``
        has sibling widgets (e.g. ``TopContainerOverlayView`` vs the
        toolbar/bookmark-bar/tab-strip tree) whose bounds both cover the
        whole viewport and both contain (x, y) — picking by area lets
        the real 89×28 bookmark button win over the 1920×1040 overlay
        pane that exposes nothing actionable.
        """
        candidates: list[tuple[int, object, int]] = []
        visited = [0]

        def visit(node, depth: int) -> None:
            if depth >= _HIT_TEST_MAX_DEPTH:
                return
            visited[0] += 1
            if visited[0] > _INVOCABLE_VISIT_LIMIT:
                return
            try:
                rect = node.BoundingRectangle
            except Exception:
                return
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                return
            if not (rect.left <= x < rect.right and rect.top <= y < rect.bottom):
                return
            if _has_invoke_action(node):
                candidates.append((w * h, node, depth))
            try:
                children = node.GetChildren()
            except Exception:
                children = []
            for child in children:
                visit(child, depth + 1)

        visit(root, 0)
        trace.add(f"DFS visited={visited[0]} invocable_candidates={len(candidates)}")
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])
        area, ctrl, depth = candidates[0]
        trace.add(f"DFS picked area={area} depth={depth} → {_describe_control(ctrl)}")
        return ctrl

    def _fire_invoke(self, target, trace: _Trace) -> bool:
        """Try InvokePattern then LegacyIAccessiblePattern on ``target``.

        The DFS already guarantees ``target`` exposes one of them
        (``_has_invoke_action`` is its gate), so we don't climb
        ancestors — doing so would risk firing the wrong control if
        the leaf's Invoke happens to throw.
        """
        trace.add(
            f"fire_invoke target={_describe_control(target)} "
            f"patterns={_supported_patterns(target)}"
        )
        try:
            invoke = target.GetInvokePattern()
        except Exception as exc:
            logger.debug(f"UIA GetInvokePattern raised: {exc}")
            trace.add(f"GetInvokePattern raised: {exc}")
            invoke = None
        if invoke is not None:
            try:
                invoke.Invoke()
                return True
            except Exception as exc:
                logger.debug(f"UIA Invoke() raised: {exc}")
                trace.add(f"Invoke() raised: {exc}")
        try:
            legacy = target.GetLegacyIAccessiblePattern()
        except Exception as exc:
            logger.debug(f"UIA GetLegacyIAccessiblePattern raised: {exc}")
            trace.add(f"GetLegacyIAccessiblePattern raised: {exc}")
            legacy = None
        if legacy is not None:
            try:
                legacy.DoDefaultAction()
                trace.add("DoDefaultAction() succeeded")
                return True
            except Exception as exc:
                logger.debug(f"UIA DoDefaultAction() raised: {exc}")
                trace.add(f"DoDefaultAction() raised: {exc}")
        return False

    def _to_element(self, control, role: str) -> A11yElement | None:
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

        value: str | None = None
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
