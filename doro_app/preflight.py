"""Preflight environment checks — runs before any PySide6 import."""

from __future__ import annotations

import os
import re
import sys
from importlib.metadata import version as pkg_version, PackageNotFoundError

_MIN_PYTHON = (3, 10)
_MIN_PYSIDE6 = "6.5.0"


def _parse_version(v: str) -> tuple[int, ...]:
    # Take leading digits from each of the first 3 dot-separated parts so
    # prerelease/dev/post suffixes (e.g. "6.7.0a1", "6.5.0.dev2") don't crash.
    parts: list[int] = []
    for chunk in v.split(".")[:3]:
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group()) if m else 0)
    return tuple(parts)


def preflight_check() -> tuple[list[str], list[str]]:
    """Return (errors, warnings).  Errors are fatal; warnings are informational."""
    errors: list[str] = []
    warnings: list[str] = []

    if sys.version_info < _MIN_PYTHON:
        cur = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        need = f"{_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}"
        errors.append(f"Python {need}+ 必要，目前版本為 {cur}")

    try:
        pyside_ver = pkg_version("PySide6")
        if _parse_version(pyside_ver) < _parse_version(_MIN_PYSIDE6):
            errors.append(f"PySide6 {_MIN_PYSIDE6}+ 必要，目前版本為 {pyside_ver}")
    except (ImportError, PackageNotFoundError):
        errors.append("PySide6 未安裝 — pip install PySide6")

    try:
        import anthropic  # noqa: F401
    except ImportError:
        warnings.append("anthropic 未安裝，聊天功能將無法使用 — pip install anthropic")

    # Phase 1c automation: pynput is only required when DORO_MOUSE=true (or
    # the user enabled mouse_enabled in settings). Don't penalize default users.
    if os.environ.get("DORO_MOUSE", "").strip().lower() in ("1", "true", "yes", "on"):
        try:
            import pynput  # noqa: F401
        except ImportError:
            warnings.append(
                "DORO_MOUSE 已設為 true 但 pynput 未安裝；滑鼠自動化將被停用 — "
                "pip install 'doro[automation]'"
            )
        if (
            sys.platform.startswith("linux")
            and os.environ.get("WAYLAND_DISPLAY")
            and not os.environ.get("DISPLAY")
        ):
            warnings.append(
                "偵測到 Wayland 純會話（無 XWayland）；滑鼠自動化目前僅支援 X11 / Windows，將進入 disabled 狀態。"
            )

    # Phase 1d a11y: the Windows backend needs the optional `uiautomation`
    # package. Warn (don't fail) when a11y is requested via env but it's
    # missing, so the tree-read doesn't silently return nothing.
    if os.environ.get("DORO_A11Y", "").strip().lower() in ("1", "true", "yes", "on"):
        if sys.platform == "win32":
            import importlib.util

            if importlib.util.find_spec("uiautomation") is None:
                warnings.append(
                    "DORO_A11Y 已設為 true 但 uiautomation 未安裝；無障礙樹讀取將回傳空白 — "
                    "pip install 'doro[a11y]'"
                )

    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            errors.append("找不到顯示伺服器（$DISPLAY / $WAYLAND_DISPLAY 未設定）")

    return errors, warnings
