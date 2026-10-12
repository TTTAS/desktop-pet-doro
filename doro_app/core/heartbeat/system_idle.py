"""How long the whole computer has had no keyboard or mouse input."""

from __future__ import annotations

import sys


def system_idle_seconds() -> float | None:
    """Seconds since the last input anywhere on the desktop, or ``None`` if unknown.

    Only Windows exposes this cheaply (``GetLastInputInfo``). Elsewhere the
    heartbeat falls back to interactions with Doro alone.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        # Both tick counts are 32-bit and wrap every ~49 days.
        elapsed_ms = (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
        return elapsed_ms / 1000.0
    except (AttributeError, OSError):
        return None
