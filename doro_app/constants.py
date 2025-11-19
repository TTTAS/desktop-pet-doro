"""Constants for Doro application - extracted from Window to improve readability."""

from PySide6 import QtGui

# ═══════════════════════════════════════════════════════════
# Animation and Timing Constants
# ═══════════════════════════════════════════════════════════

TIMER_INTERVAL_MS = 16  # ~60 FPS (1000ms / 60 = 16.67ms)
BUBBLE_AUTO_HIDE_MS = 6000  # 6 seconds
COMPANION_IDLE_THRESHOLD_SECONDS = 10.0

# ═══════════════════════════════════════════════════════════
# Window Size Constants
# ═══════════════════════════════════════════════════════════

WINDOW_INITIAL_WIDTH = 380
WINDOW_INITIAL_HEIGHT = 230
WINDOW_MIN_WIDTH = 320
WINDOW_MIN_HEIGHT = 240

# ═══════════════════════════════════════════════════════════
# Sprite and Layout Constants
# ═══════════════════════════════════════════════════════════

SPRITE_DEFAULT_WIDTH = 200
SPRITE_DEFAULT_HEIGHT = 200
SPRITE_OFFSET_X = -110.0
SPRITE_MIN_SIZE = 20.0  # Minimum half-width/height for sprite bounds

PANEL_DEFAULT_WIDTH_HINT = 360.0
PANEL_DEFAULT_HEIGHT_HINT = 110.0

MOVEMENT_STEP_PX = 60  # Default movement step in pixels

# ═══════════════════════════════════════════════════════════
# Bubble (Text Panel) Layout Constants
# ═══════════════════════════════════════════════════════════

BUBBLE_DEFAULT_OFFSET_X = 120.0
BUBBLE_DEFAULT_OFFSET_Y = -110.0
BUBBLE_DEFAULT_SCALE = 1.0
BUBBLE_DEFAULT_ALPHA = 170.0

# Bubble positioning
BUBBLE_GAP_FROM_SPRITE = 28.0  # Gap between sprite and bubble
BUBBLE_MARGIN_TOP = 18.0
BUBBLE_MARGIN_BOTTOM = 24.0
BUBBLE_MARGIN_LEFT = 12.0

# Bubble rendering
BUBBLE_CORNER_RADIUS = 18.0
BUBBLE_INNER_PADDING_X = 28.0
BUBBLE_INNER_PADDING_Y = 22.0
BUBBLE_SHADOW_OFFSET_BELOW = 8.0
BUBBLE_SHADOW_OFFSET_ABOVE = -12.0
BUBBLE_SHADOW_BOTTOM_BELOW = 12.0
BUBBLE_SHADOW_BOTTOM_ABOVE = 4.0

# Bubble text
BUBBLE_TEXT_FONT_SIZE = 12.0
BUBBLE_MIN_TEXT_WIDTH = 60.0
BUBBLE_MIN_WIDTH = 80.0
BUBBLE_MIN_HEIGHT = 80.0

# Bubble gradient alphas (as fractions of base alpha)
BUBBLE_OUTLINE_ALPHA_FACTOR = 0.55
BUBBLE_FILL_ALPHA_FACTOR = 0.92
BUBBLE_SHADOW_ALPHA_FACTOR = 0.4
BUBBLE_SHEEN_ALPHA_FACTOR_START = 0.28
BUBBLE_SHEEN_ALPHA_FACTOR_MID = 0.12

# ═══════════════════════════════════════════════════════════
# Sprite Positioning Constants
# ═══════════════════════════════════════════════════════════

SPRITE_MARGIN_X = 12.0
SPRITE_MARGIN_BOTTOM = 24.0
SPRITE_BOB_ALLOWANCE = 20.0  # Extra space for bobbing animation
SPRITE_PANEL_RESERVE_OFFSET = 48.0

# ═══════════════════════════════════════════════════════════
# Click Detection Constants
# ═══════════════════════════════════════════════════════════

CLICK_DRAG_THRESHOLD_PX = 6  # Manhattan distance threshold for click vs drag

# ═══════════════════════════════════════════════════════════
# Default Visual Colors (Fallback Sprite)
# ═══════════════════════════════════════════════════════════

DEFAULT_GRADIENT_TOP = "#FFFFFFFF"
DEFAULT_GRADIENT_MID = "#FF9BE3FF"
DEFAULT_GRADIENT_BOTTOM = "#FF6CC1F0"
DEFAULT_BLUSH_COLOR = "#FFC0C0"
DEFAULT_EYE_COLOR = "#222222"
DEFAULT_BORDER_COLOR = "#FF5C9ED6"
DEFAULT_BORDER_WIDTH = 3

# ═══════════════════════════════════════════════════════════
# Fallback Sprite Geometry (when no GIF loaded)
# ═══════════════════════════════════════════════════════════

# Face outline path control points (cubic bezier)
FACE_CENTER_X = 90
FACE_CENTER_Y_TOP = 20
FACE_CENTER_Y_BOTTOM = 160
FACE_LEFT_X = 30
FACE_RIGHT_X = 150
FACE_CONTROL_X_LEFT = 50
FACE_CONTROL_X_RIGHT = 130

# Blush (cheeks) positions and size
BLUSH_LEFT_X = 55
BLUSH_RIGHT_X = 107
BLUSH_Y = 85
BLUSH_WIDTH = 18
BLUSH_HEIGHT = 10

# Eyes positions and size
EYE_LEFT_X = 70
EYE_RIGHT_X = 100
EYE_Y = 70
EYE_WIDTH = 10
EYE_HEIGHT = 14

# Mouth path control points (smile curve)
MOUTH_START_X = 80
MOUTH_START_Y = 95
MOUTH_CONTROL1_X = 90
MOUTH_CONTROL1_Y = 105
MOUTH_CONTROL2_X = 100
MOUTH_CONTROL2_Y = 105
MOUTH_END_X = 110
MOUTH_END_Y = 95
MOUTH_PEN_WIDTH = 2

# ═══════════════════════════════════════════════════════════
# Bubble Gradient Colors
# ═══════════════════════════════════════════════════════════

BUBBLE_FILL_TOP_COLOR = (255, 255, 255)  # RGB
BUBBLE_FILL_BOTTOM_COLOR = (236, 240, 255)  # RGB

BUBBLE_OUTLINE_START_COLOR = (134, 180, 255)  # RGB
BUBBLE_OUTLINE_END_COLOR = (255, 255, 255)  # RGB

BUBBLE_SHEEN_COLOR = (255, 255, 255)  # RGB (alpha varies)
BUBBLE_SHADOW_COLOR = (4, 8, 20)  # RGB (alpha varies)

BUBBLE_TEXT_COLOR = (0, 0, 0, 255)  # RGBA

# ═══════════════════════════════════════════════════════════
# Shadow Effect Constants (for dialogs)
# ═══════════════════════════════════════════════════════════

CARD_SHADOW_BLUR_RADIUS = 28.0
CARD_SHADOW_Y_OFFSET = 10.0
CARD_SHADOW_OPACITY = 150
CARD_SHADOW_COLOR = (4, 7, 20)  # RGB

# ═══════════════════════════════════════════════════════════
# Protected State Keys
# ═══════════════════════════════════════════════════════════

MOVEMENT_ONLY_STATE_KEYS = {"walking"}  # States that are movement-only
DEFAULT_MOVE_STATE_KEY = "walking"

# ═══════════════════════════════════════════════════════════
# Helper Functions for Color Construction
# ═══════════════════════════════════════════════════════════

def get_default_fill_colors() -> tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor]:
    """Get default gradient fill colors for fallback sprite."""
    return (
        QtGui.QColor(DEFAULT_GRADIENT_TOP),
        QtGui.QColor(DEFAULT_GRADIENT_MID),
        QtGui.QColor(DEFAULT_GRADIENT_BOTTOM),
    )

def get_default_blush_color() -> QtGui.QColor:
    """Get default blush color."""
    return QtGui.QColor(DEFAULT_BLUSH_COLOR)

def get_default_eye_color() -> QtGui.QColor:
    """Get default eye color."""
    return QtGui.QColor(DEFAULT_EYE_COLOR)

def get_bubble_fill_gradient_colors(alpha: int) -> tuple[QtGui.QColor, QtGui.QColor]:
    """Get bubble fill gradient colors with specified alpha."""
    fill_alpha = int(alpha * BUBBLE_FILL_ALPHA_FACTOR)
    top = QtGui.QColor(*BUBBLE_FILL_TOP_COLOR, fill_alpha)
    bottom = QtGui.QColor(*BUBBLE_FILL_BOTTOM_COLOR, fill_alpha)
    return top, bottom

def get_bubble_outline_gradient_colors(alpha: int) -> tuple[QtGui.QColor, QtGui.QColor]:
    """Get bubble outline gradient colors with specified alpha."""
    outline_alpha = int(alpha * BUBBLE_OUTLINE_ALPHA_FACTOR)
    start = QtGui.QColor(*BUBBLE_OUTLINE_START_COLOR, outline_alpha)
    end = QtGui.QColor(*BUBBLE_OUTLINE_END_COLOR, outline_alpha)
    return start, end

def get_bubble_shadow_color(alpha: int) -> QtGui.QColor:
    """Get bubble shadow color with specified alpha."""
    shadow_alpha = int(alpha * BUBBLE_SHADOW_ALPHA_FACTOR)
    return QtGui.QColor(*BUBBLE_SHADOW_COLOR, shadow_alpha)

def get_bubble_text_color() -> QtGui.QColor:
    """Get bubble text color."""
    return QtGui.QColor(*BUBBLE_TEXT_COLOR)
