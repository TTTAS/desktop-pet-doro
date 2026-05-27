"""Test fixtures for UI tests.

Force the offscreen Qt platform so pytest-qt's QApplication boots cleanly
in headless / sandboxed environments (CI, the Claude Code remote
container, etc.) where neither X11 nor Wayland is available.

Set at import time so the env var is in place before pytest-qt's
``qapp`` fixture instantiates ``QApplication``.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
