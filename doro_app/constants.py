"""Constants for Doro application - extracted from Window to improve readability."""

# ═══════════════════════════════════════════════════════════
# Animation and Timing Constants
# ═══════════════════════════════════════════════════════════

TIMER_INTERVAL_MS = 16  # ~60 FPS (1000ms / 60 = 16.67ms)
BUBBLE_AUTO_HIDE_MS = 6000  # 6 seconds
COMPANION_IDLE_THRESHOLD_SECONDS = 10.0

# Idle behavior timing (seconds)
IDLE_BEHAVIOR_MIN_INTERVAL = 60.0   # 1 minute minimum between idle actions
IDLE_BEHAVIOR_MAX_INTERVAL = 180.0  # 3 minutes maximum between idle actions

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

# Bubble gradient alphas (as fractions of base alpha)
BUBBLE_OUTLINE_ALPHA_FACTOR = 0.55
BUBBLE_FILL_ALPHA_FACTOR = 0.92
BUBBLE_SHADOW_ALPHA_FACTOR = 0.4

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

# ═══════════════════════════════════════════════════════════
# Protected State Keys
# ═══════════════════════════════════════════════════════════

MOVEMENT_ONLY_STATE_KEYS = {"walking"}  # States that are movement-only
DEFAULT_MOVE_STATE_KEY = "walking"

# ═══════════════════════════════════════════════════════════
# Transition Wildcards
# ═══════════════════════════════════════════════════════════

TRANSITION_WILDCARD = "*"  # Wildcard for transition matching (e.g., "idle" -> "*")

# ═══════════════════════════════════════════════════════════
# Color Constants
# ═══════════════════════════════════════════════════════════

COLOR_ALPHA_MAX = 255  # Maximum alpha value for QColor (0-255)

# ═══════════════════════════════════════════════════════════
# Chat Configuration Defaults
# ═══════════════════════════════════════════════════════════

CHAT_DEFAULT_HISTORY_TURNS = 8  # Number of conversation turns to keep in memory
CHAT_DEFAULT_TIMEOUT_SECONDS = 30  # Request timeout in seconds
CHAT_DEFAULT_TEMPERATURE = 0.7  # LLM temperature (creativity level)
CHAT_DEFAULT_MAX_TOKENS = 512  # Maximum tokens per response
CHAT_CONFIG_PERSIST_DELAY_MS = 50  # Debounce delay before saving config
CHAT_THREAD_CLEANUP_DELAY_MS = 150  # Qt thread cleanup requires ~100-200ms

# ═══════════════════════════════════════════════════════════
# Movement Speed Constants
# ═══════════════════════════════════════════════════════════

MOVEMENT_SPEED_SLOW = 80.0  # pixels per second
MOVEMENT_SPEED_MEDIUM = 140.0  # pixels per second
MOVEMENT_SPEED_FAST = 220.0  # pixels per second
MOVEMENT_COMPLETION_THRESHOLD = 0.5  # pixels - movement is "done" when within this distance

# ═══════════════════════════════════════════════════════════
# Bubble Scale Limits
# ═══════════════════════════════════════════════════════════

BUBBLE_SCALE_MIN = 0.5  # Minimum scale factor for bubble
BUBBLE_SCALE_MAX = 2.0  # Maximum scale factor for bubble

# ═══════════════════════════════════════════════════════════
# UI Layout Constants
# ═══════════════════════════════════════════════════════════

PANEL_MIN_WIDTH = 160.0  # Minimum width for text panel
PANEL_MIN_HEIGHT = 80.0  # Minimum height for text panel
PANEL_PADDING = 56.0  # Internal padding for panel content
PANEL_MAX_WIDTH = 4000.0  # Maximum width to prevent excessive stretching

# ═══════════════════════════════════════════════════════════
# Screen and Window Positioning
# ═══════════════════════════════════════════════════════════

FALLBACK_SCREEN_WIDTH = 1920  # Fallback screen width if detection fails
FALLBACK_SCREEN_HEIGHT = 1080  # Fallback screen height if detection fails

WINDOW_INITIAL_POSITION_OFFSET_X = 40  # Offset from right edge on startup
WINDOW_INITIAL_POSITION_OFFSET_Y = 120  # Offset from bottom edge on startup

# ═══════════════════════════════════════════════════════════
# Helper Functions for Color Construction
# ═══════════════════════════════════════════════════════════


def get_default_fill_colors():
    """Get default gradient fill colors for fallback sprite."""
    from PySide6 import QtGui

    return (
        QtGui.QColor(DEFAULT_GRADIENT_TOP),
        QtGui.QColor(DEFAULT_GRADIENT_MID),
        QtGui.QColor(DEFAULT_GRADIENT_BOTTOM),
    )


def get_default_blush_color():
    """Get default blush color."""
    from PySide6 import QtGui

    return QtGui.QColor(DEFAULT_BLUSH_COLOR)


def get_default_eye_color():
    """Get default eye color."""
    from PySide6 import QtGui

    return QtGui.QColor(DEFAULT_EYE_COLOR)
