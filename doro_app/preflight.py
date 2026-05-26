"""Preflight environment checks — runs before any PySide6 import."""

from __future__ import annotations

import os
import sys
from importlib.metadata import version as pkg_version, PackageNotFoundError


_MIN_PYTHON = (3, 10)
_MIN_PYSIDE6 = "6.5.0"


def _parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split(".")[:3])


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
        if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
            warnings.append(
                "偵測到 Wayland 純會話（無 XWayland）；滑鼠自動化目前僅支援 X11 / Windows，將進入 disabled 狀態。"
            )

    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            errors.append("找不到顯示伺服器（$DISPLAY / $WAYLAND_DISPLAY 未設定）")

    return errors, warnings
