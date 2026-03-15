"""Doro-themed context menu with custom styling and avatar decoration."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from ...window import DoroWindow


class DoroMenu(QtWidgets.QMenu):
    """
    Custom context menu with Doro theme.

    Features:
    - Pink color scheme matching Doro's hair color (#FF9BE3FF)
    - Optional Doro avatar in corner
    - Smooth gradients and rounded corners
    - Custom styling for all menu elements
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None, *, avatar_position: str = "top-right"):
        """
        Initialize Doro-themed menu.

        Args:
            parent: Parent widget
            avatar_position: Where to place avatar - "top-left", "top-right", "top-center", or "none"
        """
        super().__init__(parent)
        self._avatar_position = avatar_position
        self._avatar_pixmap: QtGui.QPixmap | None = None
        self._avatar_size = 48

        # Apply Doro theme stylesheet
        self._apply_doro_stylesheet()

        # Add extra top margin only for main menu with centered avatar
        # This won't affect submenus
        if avatar_position == "top-center":
            # Add extra space at top using contentsMargins (not in stylesheet)
            current_margins = self.contentsMargins()
            self.setContentsMargins(
                current_margins.left(),
                52,  # Extra 52px top margin (60 - 8 from stylesheet)
                current_margins.right(),
                current_margins.bottom()
            )

    def set_avatar(self, pixmap: QtGui.QPixmap | None):
        """Set the avatar pixmap to display in corner."""
        self._avatar_pixmap = pixmap
        self.update()

    def _apply_doro_stylesheet(self):
        """Apply pink-themed stylesheet matching Doro's colors."""
        # Doro color palette
        doro_pink = "#FF9BE3"      # Main hair color
        doro_light_pink = "#FFC4F0"  # Lighter shade
        doro_dark_pink = "#E86BD1"   # Darker shade
        doro_accent = "#6CC1F0"      # Blue accent from gradient

        stylesheet = f"""
        QMenu {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF,
                stop:0.05 #FFF5FC,
                stop:1 #FFE8F7
            );
            border: 2px solid {doro_pink};
            border-radius: 12px;
            padding: 8px 4px 8px 4px;
            margin: 0px;
        }}

        QMenu::item {{
            background-color: transparent;
            padding: 8px 32px 8px 16px;
            margin: 2px 6px;
            border-radius: 6px;
            color: #2D2D2D;
            font-size: 11pt;
        }}

        QMenu::item:selected {{
            background-color: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {doro_light_pink},
                stop:1 {doro_pink}
            );
            color: white;
            font-weight: 600;
        }}

        QMenu::item:disabled {{
            color: #AAAAAA;
            background-color: transparent;
        }}

        QMenu::separator {{
            height: 2px;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent,
                stop:0.4 {doro_pink},
                stop:0.6 {doro_pink},
                stop:1 transparent
            );
            margin: 6px 16px;
        }}

        QMenu::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 3px;
            margin-left: 6px;
        }}

        QMenu::indicator:non-exclusive:checked {{
            background-color: {doro_pink};
            border: 2px solid {doro_dark_pink};
            image: url(none);
        }}

        QMenu::right-arrow {{
            width: 12px;
            height: 12px;
            margin-right: 8px;
        }}
        """

        self.setStyleSheet(stylesheet)

        # Note: Removed FramelessWindowHint and WA_TranslucentBackground
        # These caused "UpdateLayeredWindowIndirect failed" errors on Windows
        # The pink theme and rounded corners are preserved via stylesheet

    def paintEvent(self, event: QtGui.QPaintEvent):
        """Custom paint event to draw avatar and enhanced styling."""
        # First, let Qt draw the standard menu
        super().paintEvent(event)

        # Then draw our custom decorations
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # Draw avatar if available
        if self._avatar_pixmap and not self._avatar_pixmap.isNull() and self._avatar_position != "none":
            self._draw_avatar(painter)

        # Draw corner accent
        self._draw_corner_accent(painter)

    def _draw_avatar(self, painter: QtGui.QPainter):
        """Draw Doro avatar in the specified corner."""
        size = self._avatar_size
        margin = 8

        # Calculate position based on avatar_position
        if self._avatar_position == "top-right":
            x = self.width() - size - margin
            y = margin
        elif self._avatar_position == "top-left":
            x = margin
            y = margin
        elif self._avatar_position == "top-center":
            # Center horizontally at top
            x = (self.width() - size) / 2
            y = margin
        else:
            return

        # Create rounded rect path for avatar
        avatar_rect = QtCore.QRectF(x, y, size, size)
        path = QtGui.QPainterPath()
        path.addRoundedRect(avatar_rect, size / 2, size / 2)

        # Draw pink glow behind avatar
        painter.save()
        glow_rect = avatar_rect.adjusted(-3, -3, 3, 3)
        glow_path = QtGui.QPainterPath()
        glow_path.addRoundedRect(glow_rect, (size + 6) / 2, (size + 6) / 2)

        glow_gradient = QtGui.QRadialGradient(
            glow_rect.center(),
            size / 2 + 6
        )
        glow_gradient.setColorAt(0, QtGui.QColor(255, 155, 227, 120))
        glow_gradient.setColorAt(1, QtGui.QColor(255, 155, 227, 0))
        painter.fillPath(glow_path, glow_gradient)
        painter.restore()

        # Draw white border
        painter.save()
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 230), 3))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()

        # Draw avatar with clipping
        painter.save()
        painter.setClipPath(path)
        scaled_pixmap = self._avatar_pixmap.scaled(
            int(size), int(size),
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(int(x), int(y), scaled_pixmap)
        painter.restore()

    def _draw_corner_accent(self, painter: QtGui.QPainter):
        """Draw decorative accent in opposite corner from avatar."""
        # Determine which corner to decorate
        if self._avatar_position == "top-right":
            # Draw accent in bottom-left
            x, y = 8, self.height() - 8
            angle_start = 180
        elif self._avatar_position == "top-left":
            # Draw accent in bottom-right
            x, y = self.width() - 8, self.height() - 8
            angle_start = 0
        else:
            # No avatar, draw in top-right
            x, y = self.width() - 8, 8
            angle_start = 0

        # Draw small decorative arc
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)

        gradient = QtGui.QRadialGradient(x, y, 20)
        gradient.setColorAt(0, QtGui.QColor(255, 155, 227, 60))
        gradient.setColorAt(1, QtGui.QColor(255, 155, 227, 0))

        painter.setBrush(gradient)
        painter.drawEllipse(QtCore.QPointF(x, y), 20, 20)
        painter.restore()

    # Note: Removed showEvent with QGraphicsDropShadowEffect
    # This caused rendering conflicts with the custom paintEvent on Windows
    # The menu still looks good with just the stylesheet and avatar decoration


def create_doro_menu(
    parent: QtWidgets.QWidget | None = None,
    avatar_position: str = "top-right",
    gif_movie: QtGui.QMovie | None = None
) -> DoroMenu:
    """
    Create a Doro-themed menu with optional avatar.

    Args:
        parent: Parent widget
        avatar_position: "top-left", "top-right", or "none"
        gif_movie: QMovie to extract first frame as avatar

    Returns:
        Configured DoroMenu instance
    """
    menu = DoroMenu(parent, avatar_position=avatar_position)

    # Extract first frame from GIF if available
    if gif_movie and gif_movie.isValid():
        # Temporarily jump to first frame to get avatar
        current_frame = gif_movie.currentFrameNumber()
        gif_movie.jumpToFrame(0)
        first_frame_pixmap = gif_movie.currentPixmap()

        # Restore to current frame (to avoid disrupting animation)
        if current_frame >= 0:
            gif_movie.jumpToFrame(current_frame)

        if not first_frame_pixmap.isNull():
            menu.set_avatar(first_frame_pixmap)

    return menu


def build_context_menu_content(window: DoroWindow, menu: DoroMenu) -> None:
    """
    Build the content (items, submenus, actions) for the context menu.

    Args:
        window: The main DoroWindow instance
        menu: The themed menu to populate
    """
    # States submenu
    states_menu = menu.addMenu("States")
    for key in window.state_controller.visible_state_keys():
        state = window.state_service.get_state(key)
        if not state:
            continue
        label = state.label or key
        action = states_menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(key == window.current_state_key)
        action.triggered.connect(lambda checked, s=key: window.state_controller.set_state(s))

    edit_states_action = states_menu.addAction("Edit states")
    edit_states_action.triggered.connect(window.dialog_manager.show_state_manager)

    # Actions submenu
    actions_menu = menu.addMenu("Actions")
    edit_actions_action = actions_menu.addAction("Edit actions")
    edit_actions_action.triggered.connect(window.dialog_manager.show_move_state_manager)

    menu.addSeparator()

    # Stay on top toggle
    top_action = QtGui.QAction("Stay on top", window)
    top_action.setCheckable(True)
    is_top = bool(window.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint)
    top_action.setChecked(is_top)

    def toggle_top():
        f = window.windowFlags()
        if bool(f & QtCore.Qt.WindowType.WindowStaysOnTopHint):
            f &= ~QtCore.Qt.WindowType.WindowStaysOnTopHint
        else:
            f |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        window.setWindowFlags(f)
        window.show()  # re-apply flags

    top_action.triggered.connect(toggle_top)
    menu.addAction(top_action)

    # State visuals submenu
    visuals_menu = menu.addMenu("State visuals")
    bubble_action = visuals_menu.addAction("Show message panel")
    bubble_action.setCheckable(True)
    current_state = window.state_service.get_current_state()
    bubble_action.setChecked(bool(current_state and current_state.visual.bubble_visible))
    bubble_action.triggered.connect(window.toggle_bubble)

    clear_gif_action = visuals_menu.addAction("Reset GIF to default")
    clear_gif_action.setEnabled(window.default_idle_gif.is_file())
    clear_gif_action.triggered.connect(
        lambda: window.state_controller.clear_state_gif(window.current_state_key)
    )

    name_tag_action = visuals_menu.addAction("Rename pet")
    name_tag_action.triggered.connect(
        lambda: window.dialog_manager.show_rename_dialog(window.current_state_key) and window.update()
        if window.current_state_key else None
    )

    # Chat submenu
    chat_menu = menu.addMenu("Chat")
    ask_action = chat_menu.addAction("Ask Doro")
    ask_action.setEnabled(not window.core_manager.is_chat_inflight)
    ask_action.triggered.connect(window.chat_ui.prompt_chat)

    edit_prompt_action = chat_menu.addAction("Edit prompt")
    edit_prompt_action.triggered.connect(window.chat_ui.edit_chat_prompt)

    clear_history_action = chat_menu.addAction("Clear conversation history")
    clear_history_action.setEnabled(window.core_manager.has_chat_history)
    clear_history_action.triggered.connect(window.chat_ui.clear_chat_history)

    configure_menu = chat_menu.addMenu("Configure")

    from ..helpers.chat_ui_helper import _PROVIDER_PRESETS

    provider_menu = configure_menu.addMenu("Provider")
    for name in _PROVIDER_PRESETS:
        action = provider_menu.addAction(name)
        action.triggered.connect(partial(window.chat_ui.apply_provider_preset, name))
    configure_menu.addSeparator()

    server_action = configure_menu.addAction("Set server URL")
    server_action.triggered.connect(window.chat_ui.configure_chat_server)

    model_action = configure_menu.addAction("Set model name")
    model_action.triggered.connect(window.chat_ui.configure_chat_model)

    endpoint_action = configure_menu.addAction("Set endpoint path")
    endpoint_action.triggered.connect(window.chat_ui.configure_chat_endpoint)

    temperature_action = configure_menu.addAction("Set temperature")
    temperature_action.triggered.connect(window.chat_ui.configure_chat_temperature)

    timeout_action = configure_menu.addAction("Set timeout (seconds)")
    timeout_action.triggered.connect(window.chat_ui.configure_chat_timeout)

    api_key_action = configure_menu.addAction("Set API key")
    api_key_action.triggered.connect(window.chat_ui.configure_api_key)

    menu.addSeparator()

    # Exit action
    quit_action = QtGui.QAction("Exit doro", window)
    quit_action.triggered.connect(QtWidgets.QApplication.instance().quit)
    menu.addAction(quit_action)
