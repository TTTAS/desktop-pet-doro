"""Smoke tests for the standalone window-class reader module.

The platform-specific helpers are guarded by ``pragma: no cover`` in
production because they need a live X server or Windows desktop. These
tests instead verify the public dispatch layer: ``read_at`` selects the
right backend per platform and returns ``None`` gracefully on unknown
platforms.
"""

from __future__ import annotations

from unittest.mock import patch

from doro_app.core.automation import window_class


def test_read_at_returns_none_on_unknown_platform():
    with patch.object(window_class.sys, "platform", "freebsd"):
        assert window_class.read_at(0, 0) is None


def test_read_at_dispatches_to_x11_on_linux():
    with patch.object(window_class.sys, "platform", "linux"), \
         patch.object(window_class, "_read_window_class_x11", return_value="Chrome") as mock_x11:
        assert window_class.read_at(100, 200) == "Chrome"
        mock_x11.assert_called_once_with(100, 200)


def test_read_at_dispatches_to_win32_on_windows():
    with patch.object(window_class.sys, "platform", "win32"), \
         patch.object(window_class, "_read_window_class_win32", return_value="ChromeWidgetWin") as mock_win:
        assert window_class.read_at(50, 75) == "ChromeWidgetWin"
        mock_win.assert_called_once_with(50, 75)


def test_read_at_dispatches_to_macos_on_darwin():
    with patch.object(window_class.sys, "platform", "darwin"), \
         patch.object(window_class, "_read_window_class_macos", return_value=None) as mock_mac:
        assert window_class.read_at(0, 0) is None
        mock_mac.assert_called_once_with(0, 0)


def test_read_at_coerces_to_int():
    """Non-int inputs are still safe — the dispatch casts to int."""
    with patch.object(window_class.sys, "platform", "linux"), \
         patch.object(window_class, "_read_window_class_x11", return_value=None) as mock_x11:
        window_class.read_at(100.7, 200.3)  # type: ignore[arg-type]
        mock_x11.assert_called_once_with(100, 200)


def test_module_imports_without_pynput():
    """The window_class module must not require pynput.

    The Phase 1c hotfix relies on this for chat context injection even
    when the optional ``automation`` extra is not installed.
    """
    import doro_app.core.automation.window_class as wc  # noqa: F401
    # If the import above succeeded, the test passes.
