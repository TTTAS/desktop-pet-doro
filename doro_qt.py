import argparse
import sys
import json
import copy
import random
import os
import shutil
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from PySide6 import QtCore, QtGui, QtWidgets
from doro.core.action_manager import ActionStateSettings

from doro.chat.client import (
    ChatRequestWorker,
    build_messages_for_mistral_instruct,
    perform_chat_request,
    resolve_chat_endpoint,
)
from doro.chat.parser import ACTION_PATTERN, BRACKET_PATTERN, parse_actions_from_text
from doro.config.settings import (
    DEFAULT_PROMPT_TEXT,
    load_prompt_text,
    safe_float as _safe_float,
    safe_int as _safe_int,
    write_prompt_text,
)
from doro.core.action_manager import ActionManagerMixin
from doro.core.state_manager import StateManagerMixin, StateSettings
from doro.ui.bubble import BubbleController
from doro.ui.painter import UIRenderMixin

_DEBUG_ENV = os.environ.get("DORO_DEBUG", "1")
_DEBUG_MODE = str(_DEBUG_ENV).strip().lower() not in {"", "0", "false", "off"}


APP_THEME_COLORS = {
    "background": "#070c16",
    "surface": "#101b2d",
    "card": "#182540",
    "card_alt": "#1f2f52",
    "accent": "#a78bfa",
    "accent_soft": "#67e8f9",
    "text_primary": "#eef2ff",
    "text_muted": "#9fb4d0",
    "border": "rgba(148, 163, 184, 0.35)",
}

APP_GLOBAL_QSS = """
QMenu {
    background-color: #0b1526;
    color: #f1f5ff;
    border: 1px solid rgba(99,122,166,0.5);
    border-radius: 14px;
    padding: 8px;
}
QMenu::item {
    padding: 6px 14px;
    border-radius: 8px;
}
QMenu::item:selected {
    background-color: rgba(167,139,250,0.18);
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: rgba(148,163,184,0.35);
    margin: 6px 4px;
}
QDialog, QInputDialog {
    background-color: #080f1d;
    color: #e5edff;
    border: 1px solid rgba(71, 85, 105, 0.6);
    border-radius: 18px;
}
QLabel {
    color: #e5edff;
}
QLineEdit,
QPlainTextEdit,
QTextEdit,
QSpinBox,
QDoubleSpinBox {
    background-color: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 10px;
    padding: 6px 10px;
    color: #f8fbff;
}
QLineEdit:focus,
QPlainTextEdit:focus,
QTextEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #a78bfa;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b5cf6, stop:1 #14b8a6);
    color: #05070f;
    border-radius: 10px;
    padding: 7px 16px;
    font-weight: 600;
    border: none;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a78bfa, stop:1 #06b6d4);
}
QPushButton:disabled {
    background: rgba(148,163,184,0.35);
    color: rgba(248,250,252,0.55);
}
QDialogButtonBox QPushButton {
    min-width: 96px;
}
QTableWidget {
    background-color: transparent;
    color: #e2e8f0;
    gridline-color: transparent;
}
QTableWidget::item {
    padding: 10px;
}
QHeaderView::section {
    background-color: rgba(148,163,184,0.12);
    color: #cbd5f5;
    border: none;
    border-bottom: 1px solid rgba(148,163,184,0.2);
    font-weight: 600;
    padding: 8px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 8px 0 8px 0;
}
QScrollBar::handle:vertical {
    background: rgba(148,163,184,0.45);
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(167,139,250,0.75);
}
"""

_APP_THEME_APPLIED = False
def ensure_application_theme():
    global _APP_THEME_APPLIED
    if _APP_THEME_APPLIED:
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    existing = app.styleSheet() or ""
    if APP_GLOBAL_QSS.strip() not in existing:
        merged = f"{existing}\n{APP_GLOBAL_QSS}" if existing else APP_GLOBAL_QSS
        app.setStyleSheet(merged)
    _APP_THEME_APPLIED = True


ACTION_ALIASES: dict[str, str] = {
    "idle": "idle",
    "default": "idle",
    "sleep": "idle",
    "sleepy": "idle",
    "nap": "idle",
    "rest": "idle",
    "relax": "idle",
    "chill": "idle",
    "calm": "idle",
    "excited": "idle",
    "happy": "idle",
    "dance": "idle",
    "wave": "idle",
    "party": "idle",
}

class DoroWindow(QtWidgets.QWidget, StateManagerMixin, ActionManagerMixin, UIRenderMixin):
    def __init__(self, not_topmost: bool = False, *, compat_window: bool | None = None):
        super().__init__()
        ensure_application_theme()
        self._not_topmost = bool(not_topmost)
        self._forced_compat_window = compat_window
        self._compat_window_enabled = False
        self._visibility_healthcheck_done = False
        self.resize(380, 230)
        self.setMinimumSize(320, 240)

        # Animation clock
        self._t = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 FPS

        # Appearance/animation parameters (populated in _init_states)
        self._state_defs: dict[str, StateSettings] = {}
        self._protected_state_keys: set[str] = set()
        self._state_settings: StateSettings | None = None
        self._active_gif_path: str | None = None
        self._current_state_key: str = ""
        self._state_list_text: str = ""
        self._amplitude = 0.0
        self._scale_amp = 0.0
        self._fill_colors: tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor] = (
            QtGui.QColor("#FFFFFFFF"),
            QtGui.QColor("#FF9BE3FF"),
            QtGui.QColor("#FF6CC1F0"),
        )
        self._cheek_alpha = 0.0
        self._blush_base = QtGui.QColor("#FFC0C0")
        self._eye_color = QtGui.QColor("#222222")
        self._bubble = BubbleController(self)
        self._name_tag = "doro"
        self._gif_movie: QtGui.QMovie | None = None
        self._companion_prompts: list[str] = []
        self._companion_prompt_index = 0
        self._last_user_activity = time.monotonic()
        self._companion_idle_threshold = 10.0
        self._sprite_size = QtCore.QSize(200, 200)
        self._sprite_offset_x = -110.0
        self._sprite_anchor_top: float | None = None
        self._chat_history: list[dict[str, str]] = []
        self._chat_thread: QtCore.QThread | None = None
        self._chat_worker: QtCore.QObject | None = None
        self._chat_inflight = False
        self._chat_last_user_message = ""
        self._chat_cursor_overridden = False
        self._chat_request_is_auto = False
        self._sizing_in_progress = False
        self._last_tick_time = time.monotonic()
        self._visibility_healthcheck_attempts = 0

        base_dir = Path(__file__).resolve().parent

        # QSettings must exist before mixin initialization
        self._config = QtCore.QSettings("doro-pet", "doro")
        self._compat_window_enabled = self._determine_initial_compat_mode()
        if self._forced_compat_window is not None:
            self._persist_compat_pref(self._compat_window_enabled)
        self._apply_window_chrome()
        self._bubble.attach_config(self._config)
        self._debug_capture_dir = base_dir

        # Prime action defaults so _init_states can register walking state safely
        self._action_step_px = getattr(self, "_action_step_px", 60)
        self._default_action_state_key = getattr(self, "_default_action_state_key", "walking")
        if not hasattr(self, "_action_state_defs"):
            self._action_state_defs: dict[str, ActionStateSettings] = {}
        if not hasattr(self, "_action_only_state_keys"):
            self._action_only_state_keys: set[str] = {"walking"}

        self._init_state_manager(base_dir)
        self._init_states()
        self._init_action_system()
        self._prompt_file_path = base_dir / "res" / "dia_prompt.txt"
        self._click_actions_path = base_dir / "res" / "click.txt"
        self._companion_prompts_path = base_dir / "res" / "companion.txt"
        self._click_press_pos: QtCore.QPointF | None = None
        self._click_was_dragging = False

        # Write default idle.gif once (if user hasn't set any)
        if not self._config.contains("state/idle/gif_path") and self._default_idle_gif.is_file():
            self._config.setValue("state/idle/gif_path", str(self._default_idle_gif))

        self._chat_server_url = self._config.value(
            "chat/server_url", "http://192.168.1.103:1234", str
        )
        self._chat_model = self._config.value("chat/model", "lmstudio", str)
        timeout_value = self._config.value("chat/timeout_seconds", 30)
        try:
            self._chat_timeout_seconds = int(timeout_value)
        except (TypeError, ValueError):
            self._chat_timeout_seconds = 30
        self._chat_endpoint_path = self._config.value(
            "chat/endpoint_path", "/v1/chat/completions", str
        )
        temp_value = self._config.value("chat/temperature", 0.7)
        try:
            self._chat_temperature = float(temp_value)
        except (TypeError, ValueError):
            self._chat_temperature = 0.7

        offset_x = _safe_float(self._config.value("ui/bubble_offset_x", 120.0), 120.0)
        offset_y = _safe_float(self._config.value("ui/bubble_offset_y", -110.0), -110.0)
        scale_pref = _safe_float(self._config.value("ui/bubble_scale", 1.0), 1.0)
        self._apply_bubble_offset(QtCore.QPointF(offset_x, offset_y))
        self._bubble.set_scale(scale_pref)
        self._apply_window_preferred_size()

        self._chat_system_prompt = self._load_prompt_text()
        self._companion_prompts = self._load_companion_prompts()

        


        self._drag_pos: QtCore.QPoint | None = None

        # Context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.DefaultContextMenu)

        # Place at screen center to avoid being off-screen
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            center_x = g.left() + g.width() // 2 - self.width() // 2
            center_y = g.top() + g.height() // 2 - self.height() // 2
            self.move(center_x, center_y)
        self._debug(f"Window geometry after init: {self.geometry()}")
        QtCore.QTimer.singleShot(
            500,
            lambda: self._debug(
                f"Post-show check: visible={self.isVisible()} active={self.isActiveWindow()} geometry={self.geometry()}"
            ),
        )

        self.setWindowTitle("doro")
        QtCore.QTimer.singleShot(1500, self._run_visibility_healthcheck)
        QtCore.QTimer.singleShot(2500, self._capture_debug_snapshot)
        QtCore.QTimer.singleShot(0, self.update)

    # --- Animation -------------------------------------------------------
    @staticmethod
    def _truthy_flag(value) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if not text:
            return False
        return text in {"1", "true", "yes", "on"}

    def _determine_initial_compat_mode(self) -> bool:
        if self._forced_compat_window is not None:
            return bool(self._forced_compat_window)
        env_pref = os.environ.get("DORO_COMPAT_WINDOW", "")
        if self._truthy_flag(env_pref):
            return True
        stored_pref = self._config.value("ui/compat_window", False)
        return self._truthy_flag(stored_pref)

    def _apply_window_chrome(self):
        base_flag = QtCore.Qt.WindowType.Window if self._compat_window_enabled else QtCore.Qt.WindowType.Tool
        if self._compat_window_enabled:
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, False)
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            self.setAutoFillBackground(True)
            palette = self.palette()
            palette.setColor(
                QtGui.QPalette.ColorRole.Window,
                QtGui.QColor(APP_THEME_COLORS.get("background", "#070c16")),
            )
            self.setPalette(palette)
        else:
            self.setAutoFillBackground(False)
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        flags = QtCore.Qt.WindowType.FramelessWindowHint | base_flag
        if not self._not_topmost:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _enable_compat_window_mode(self):
        if self._compat_window_enabled:
            return
        self._debug("Enabling compatibility window mode: forcing opaque window.")
        self._compat_window_enabled = True
        self._persist_compat_pref(True)
        prev_geometry = self.geometry()
        was_visible = self.isVisible()
        if was_visible:
            self.hide()
        self._apply_window_chrome()
        if prev_geometry.isValid():
            self.setGeometry(prev_geometry)
        if was_visible:
            self.show()
            self.raise_()
            self.activateWindow()
        self.update()

    def _run_visibility_healthcheck(self):
        if self._compat_window_enabled:
            return
        if not self.isVisible():
            QtCore.QTimer.singleShot(800, self._run_visibility_healthcheck)
            return
        if self._visibility_healthcheck_done:
            return
        self._visibility_healthcheck_attempts += 1
        try:
            pixmap = self.grab()
        except RuntimeError:
            pixmap = QtGui.QPixmap()
        if pixmap.isNull():
            if self._visibility_healthcheck_attempts < 3:
                QtCore.QTimer.singleShot(800, self._run_visibility_healthcheck)
            return
        image = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
        width = image.width()
        height = image.height()
        if width <= 0 or height <= 0:
            if self._visibility_healthcheck_attempts < 3:
                QtCore.QTimer.singleShot(800, self._run_visibility_healthcheck)
            return
        has_visible_pixel = False
        for y in range(height):
            if has_visible_pixel:
                break
            for x in range(width):
                if QtGui.QColor(image.pixel(x, y)).alpha() > 8:
                    has_visible_pixel = True
                    break
        self._visibility_healthcheck_done = True
        if not has_visible_pixel:
            self._debug("Visibility check detected a fully transparent frame; switching to compatibility window mode.")
            self._enable_compat_window_mode()
        else:
            self._debug("Visibility check found opaque content; keeping current mode.")

    def _capture_debug_snapshot(self):
        if getattr(self, "_debug_window_capture_done", False):
            return
        try:
            pixmap = self.grab()
        except RuntimeError:
            return
        if pixmap.isNull():
            return
        self._debug_window_capture_done = True
        capture_dir = getattr(self, "_debug_capture_dir", Path(__file__).resolve().parent)
        try:
            capture_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        target = capture_dir / "debug_window_capture.png"
        try:
            pixmap.save(str(target))
            self._debug(f"Saved debug window capture to {target}")
        except Exception:
            pass

    def _tick(self):
        now = time.monotonic()
        dt = now - getattr(self, "_last_tick_time", now)
        self._last_tick_time = now
        if dt < 0.0:
            dt = 0.0
        dt = min(dt, 0.1)
        self._process_active_action(dt)
        self._t += dt
        self.update()

    # --- Interaction -----------------------------------------------------
    def mousePressEvent(self, e: QtGui.QMouseEvent):
        self._mark_user_activity()
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._begin_bubble_transform(e.position()):
                self._update_bubble_cursor(e.position())
                e.accept()
                return
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._click_press_pos = e.position()
            self._click_was_dragging = False
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if e.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self._mark_user_activity()
        if self._update_bubble_transform(e.position()):
            self._update_bubble_cursor(e.position())
            e.accept()
            return
        bubble = self._bubble
        if not bubble.dragging and not bubble.resizing:
            self._update_bubble_cursor(e.position())
        if self._drag_pos is not None and e.buttons() & QtCore.Qt.MouseButton.LeftButton:
            if (
                self._click_press_pos is not None
                and not self._click_was_dragging
                and (e.position() - self._click_press_pos).manhattanLength() > 6
            ):
                self._click_was_dragging = True
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        self._mark_user_activity()
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._end_bubble_transform():
                self._update_bubble_cursor(e.position())
                e.accept()
                return
            was_click = (
                not self._click_was_dragging
                and self._click_press_pos is not None
                and (e.position() - self._click_press_pos).manhattanLength() <= 6
            )
            self._drag_pos = None
            self._click_press_pos = None
            self._click_was_dragging = False
            super().mouseReleaseEvent(e)
            if was_click:
                self._trigger_click_action()
            return
        self._drag_pos = None
        self._click_press_pos = None
        self._click_was_dragging = False
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e: QtCore.QEvent):
        self._update_bubble_cursor(None)
        super().leaveEvent(e)

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        self._mark_user_activity()
        super().keyPressEvent(e)

    def _mark_user_activity(self):
        self._last_user_activity = time.monotonic()

    def _load_prompt_text(self) -> str:
        """Load the system prompt from disk, falling back to the default text."""
        path = getattr(self, "_prompt_file_path", None)
        if not isinstance(path, Path):
            base_dir = Path(__file__).resolve().parent
            path = base_dir / "res" / "dia_prompt.txt"
            self._prompt_file_path = path
        try:
            prompt = load_prompt_text(path)
        except OSError:
            prompt = DEFAULT_PROMPT_TEXT
        prompt = (prompt or "").strip()
        return prompt or DEFAULT_PROMPT_TEXT

    def _load_companion_prompts(self) -> list[str]:
        """
        Load idle-companion prompts from disk.

        Each non-empty, non-comment line becomes a prompt. If the file is missing
        we seed it with a couple of defaults so the UI still has something to use.
        """
        path = getattr(self, "_companion_prompts_path", None)
        if not isinstance(path, Path):
            base_dir = Path(__file__).resolve().parent
            path = base_dir / "res" / "companion.txt"
            self._companion_prompts_path = path

        prompts: list[str] = []
        try:
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        prompts.append(stripped)
        except OSError:
            prompts = []

        if prompts:
            return prompts

        fallback = [
            "該起身活動一下囉！",
            "補充水份也要記得喔～",
            "辛苦了，深呼吸放鬆一下吧。",
        ]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(fallback) + "\n", encoding="utf-8")
        except OSError:
            pass
        return fallback

    def _trigger_click_action(self):
        """
        Display a short reaction when the pet is clicked.

        The reactions are sourced from res/click.txt; when the file is empty we fall
        back to a few built-in strings so user clicks always feel responsive.
        """
        path = getattr(self, "_click_actions_path", None)
        if not isinstance(path, Path):
            base_dir = Path(__file__).resolve().parent
            path = base_dir / "res" / "click.txt"
            self._click_actions_path = path

        lines: list[str] = []
        try:
            if path.is_file():
                lines = [
                    line.strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
        except OSError:
            lines = []

        if not lines:
            lines = ["嘿嘿，別戳太用力啦！", "在呢～有什麼事嗎？", "摸摸頭，今天也要加油！"]

        raw = random.choice(lines).strip()
        if raw.startswith("(") and raw.endswith(")"):
            raw = raw[1:-1].strip()
        if not raw:
            return
        self._bubble.show_text(raw, override_visibility=True, auto_hide=True)

    def _classify_action_token(self, token: str, *, strict: bool = True):
        """
        解析括號指令：
        - (state: <key>) -> ("state", <key>)
        - (move:  <dir>) -> ("move",  <normalized_direction_tuple>)
        嚴格模式(strict=True)僅接受有命名空間的格式；鬆綁時會回退到舊有容錯（移動優先，再嘗試狀態）。
        """
        raw = (token or "").strip()
        if not raw:
            return None

        # 1) 明確命名空間
        if ":" in raw:
            head, tail = raw.split(":", 1)
            ns = head.strip().lower()
            arg = tail.strip()
            if ns == "move":
                direction = self._parse_action_token(arg)
                return ("move", direction) if direction else None
            if ns == "state":
                state_key = self._find_state_for_action(arg)
                return ("state", state_key) if state_key else None
            # 未知命名空間直接忽略
            return None

        # 2) 嚴格模式：沒有命名空間就直接忽略，避免誤判
        if strict:
            return None

        # 3) 寬鬆容錯（跟你現有邏輯一致）：先當「移動」試，失敗再當「狀態」
        direction = self._parse_action_token(raw)
        if direction:
            return ("move", direction)
        state_key = self._find_state_for_action(raw)
        if state_key:
            return ("state", state_key)
        return None

    def _apply_state_settings(self):
        state = getattr(self, "_state_settings", None)
        if not state:
            return

        self._amplitude = _safe_float(getattr(state, "bob_amplitude", 6.0), 0.0)
        self._scale_amp = _safe_float(getattr(state, "scale_amplitude", 0.04), 0.0)
        top = getattr(state, "gradient_top", "#FFFFFFFF") or "#FFFFFFFF"
        mid = getattr(state, "gradient_mid", "#FF9BE3FF") or "#FF9BE3FF"
        bottom = getattr(state, "gradient_bottom", "#FF6CC1F0") or "#FF6CC1F0"
        self._fill_colors = (
            QtGui.QColor(top),
            QtGui.QColor(mid),
            QtGui.QColor(bottom),
        )
        self._cheek_alpha = _safe_float(getattr(state, "cheeks_alpha", 204.0), 0.0)
        self._blush_base = QtGui.QColor(getattr(state, "blush_color", "#FFC0C0") or "#FFC0C0")
        self._eye_color = QtGui.QColor(getattr(state, "eye_color", "#222222") or "#222222")
        self._name_tag = (getattr(state, "name_tag", "doro") or "doro").strip() or "doro"

        bubble_visible = bool(getattr(state, "bubble_visible", True))
        bubble_alpha = _safe_float(getattr(state, "bubble_alpha", 170.0), 0.0)
        bubble = getattr(self, "_bubble", None)
        if bubble:
            bubble.visible = bubble_visible
            bubble.alpha = bubble_alpha
        else:
            self._bubble_visible = bubble_visible  # legacy fallback
            self._bubble_alpha = bubble_alpha

        gif_path = getattr(self, "_active_gif_path", None) or getattr(state, "gif_path", None)
        if not gif_path and self._default_idle_gif.is_file():
            gif_path = str(self._default_idle_gif)
        self._debug(f"Applying state '{self._current_state_key}' with GIF: {gif_path}")
        self._load_gif(gif_path)
        self.update()
        self._apply_window_preferred_size()

    def _debug(self, message: str):
        if _DEBUG_MODE:
            print(f"[doro] {message}")

    def _set_busy_cursor(self, active: bool):
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if active:
            if not getattr(self, "_chat_cursor_overridden", False):
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.BusyCursor)
                self._chat_cursor_overridden = True
        else:
            if getattr(self, "_chat_cursor_overridden", False):
                try:
                    QtWidgets.QApplication.restoreOverrideCursor()
                finally:
                    self._chat_cursor_overridden = False

    def _persist_compat_pref(self, enabled: bool):
        config = getattr(self, "_config", None)
        if not config:
            return
        try:
            config.setValue("ui/compat_window", bool(enabled))
            config.sync()
        except Exception:
            pass
        
    def _draw_mouth(self, p: QtGui.QPainter):
        pen = QtGui.QPen(QtGui.QColor(51, 51, 51))
        pen.setWidthF(2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)

        mouth = QtGui.QPainterPath()
        mouth.moveTo(80, 95)
        mouth.cubicTo(90, 105, 100, 105, 110, 95)
        p.drawPath(mouth)
    def _release_single_instance_locks_safely(self):
        """Release possible single-instance locks safely."""
        # QLockFile 常見做法
        for attr in ("_lock_file", "_instance_lock", "lock_file", "instance_lock"):
            lf = getattr(self, attr, None)
            # QLockFile: has isLocked()/unlock()
            try:
                if lf and hasattr(lf, "isLocked") and lf.isLocked() and hasattr(lf, "unlock"):
                    lf.unlock()
            except Exception:
                pass

        # QSharedMemory 常見做法
        for attr in ("_shared_mem", "shared_mem", "single_instance_shm"):
            shm = getattr(self, attr, None)
            try:
                if shm and hasattr(shm, "isAttached") and shm.isAttached() and hasattr(shm, "detach"):
                    shm.detach()
            except Exception:
                pass

        # 也可順手把參考清掉，避免之後誤用
        for attr in ("_lock_file", "_instance_lock", "lock_file", "instance_lock", "_shared_mem", "shared_mem", "single_instance_shm"):
            if hasattr(self, attr):
                try:
                    setattr(self, attr, None)
                except Exception:
                    pass

    def closeEvent(self, event: QtGui.QCloseEvent):
        self._set_busy_cursor(False)
        timer = getattr(self, "_companion_timer", None)
        if isinstance(timer, QtCore.QTimer):
            timer.stop()
        super().closeEvent(event)
    def _restart_app(self):
        """Restart doro *without* external helper script."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return

        # 1) 儘量清理資源（避免檔案/鎖佔用）
        try:
            if getattr(self, "_gif_movie", None):
                try:
                    self._gif_movie.stop()
                except Exception:
                    pass
                self._gif_movie = None
            if hasattr(self, "_timer") and self._timer:
                try:
                    self._timer.stop()
                except Exception:
                    pass
            if getattr(self, "_config", None):
                self._config.sync()
        except Exception:
            pass

        # 2) 釋放可能的「單實例鎖」
        self._release_single_instance_locks_safely()

        # 3) 構造重新啟動命令列
        relaunch_cmd = self._build_self_launch_command()
        if not relaunch_cmd:
            QtWidgets.QMessageBox.warning(self, "Restart", "Unable to determine relaunch command.")
            return
        if "--restarted" not in relaunch_cmd:
            relaunch_cmd.append("--restarted")

        # 4) Debugger 下優先改用 execv，避免 IDE 把新行程一起停止
        debugger_attached = bool(getattr(sys, "gettrace", lambda: None)())
        if debugger_attached:
            try:
                os.execv(relaunch_cmd[0], relaunch_cmd)
                return  # pragma: no cover - execv 不會返回
            except Exception:
                debugger_attached = False  # 失敗時 fallback 至舊流程

        # 5) 以分離行程啟動自己
        cwd = str(Path(__file__).resolve().parent)
        ok, _pid = QtCore.QProcess.startDetached(relaunch_cmd[0], relaunch_cmd[1:], cwd)

        if ok:
            # 6) 啟動成功就關閉目前實例
            QtCore.QTimer.singleShot(50, app.quit)
        else:
            QtWidgets.QMessageBox.warning(self, "Restart", "Failed to relaunch doro. Please restart manually.")

    def _build_self_launch_command(self) -> list[str] | None:
        """Return argv for relaunching this app."""
        try:
            if getattr(sys, "frozen", False):  # PyInstaller 等
                exe = sys.executable or sys.argv[0]
                return [exe, *sys.argv[1:]] if exe else None

            python_exe = sys.executable or "python"

            # ★ Windows：若是 python.exe，優先改用 pythonw.exe（避免新行程被 console 關掉）
            if os.name == "nt":
                try:
                    base = os.path.dirname(python_exe)
                    name = os.path.basename(python_exe).lower()
                    if name == "python.exe":
                        cand = os.path.join(base, "pythonw.exe")
                        if os.path.isfile(cand):
                            python_exe = cand
                except Exception:
                    pass

            script_path = Path(sys.argv[0]).resolve()
            if not script_path.exists():
                script_path = Path(__file__).resolve()
            if not script_path.exists():
                return None
            return [python_exe, str(script_path), *sys.argv[1:]]
        except Exception:
            return None



def run_chat_test(message: str | None) -> int:
    test_message = (message or "Hello from Doro test!").strip()
    if not test_message:
        print("Chat test aborted: message is empty.")
        return 1

    base_dir = Path(__file__).resolve().parent
    prompt_path = base_dir / "res" / "dia_prompt.txt"
    system_prompt = load_prompt_text(prompt_path)

    settings = QtCore.QSettings("doro-pet", "doro")
    server_url = settings.value("chat/server_url", "http://192.168.1.103:1234", str)
    model = settings.value("chat/model", "lmstudio", str)
    endpoint_path = settings.value("chat/endpoint_path", "/v1/chat/completions", str)
    timeout_value = settings.value("chat/timeout_seconds", 30)
    temp_value = settings.value("chat/temperature", 0.7)

    try:
        timeout_seconds = int(timeout_value)
    except (TypeError, ValueError):
        timeout_seconds = 30

    try:
        temperature = float(temp_value)
    except (TypeError, ValueError):
        temperature = 0.7

    endpoint_url = resolve_chat_endpoint(server_url, endpoint_path)
    if not endpoint_url:
        print("Chat test failed: chat server URL is not configured.")
        return 1

    messages: list[dict[str, str]] = []
    system_prompt = (system_prompt or "").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": test_message})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    assistant_text, error_message = perform_chat_request(
        endpoint_url,
        payload,
        timeout_seconds,
    )
    if error_message:
        print(f"Chat test failed: {error_message}")
        return 1

    print("Chat test succeeded.")
    if assistant_text:
        display_text, actions = parse_actions_from_text(assistant_text)
        if actions:
            printable = [f"{kind}:{token}" for kind, token in actions]
            print(f"Recognized actions: {', '.join(printable)}")
        if display_text:
            print(f"Assistant: {display_text}")
        else:
            print("Assistant response contained only action trigger(s).")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run the Doro desktop companion.")
    parser.add_argument(
        "--not-topmost",
        action="store_true",
        help="Do not keep the window always on top.",
    )
    parser.add_argument(
        "--compat-window",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Force the classic opaque window. Use --no-compat-window to disable compatibility mode even if auto-detected.",
    )
    parser.add_argument(
        "--test-chat",
        nargs="?",
        const="",
        metavar="MESSAGE",
        help="Send a test chat request (optionally provide a MESSAGE) and exit.",
    )
    parser.add_argument(
        "--restarted",
        action="store_true",
        help="(internal) Flag indicating the app was relaunched",
    )
    args = parser.parse_args()

    if args.test_chat is not None:
        sys.exit(run_chat_test(args.test_chat))

    app = QtWidgets.QApplication(sys.argv)
    w = DoroWindow(not_topmost=args.not_topmost, compat_window=args.compat_window)
    w.show()
    w.raise_()
    w.activateWindow()
    w.setFocus(QtCore.Qt.FocusReason.ActiveWindowFocusReason)
    w._debug(f"show() called: visible={w.isVisible()} handle={bool(w.windowHandle())}")
    exit_code = app.exec()
    print(f"[doro] app.exec() exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
