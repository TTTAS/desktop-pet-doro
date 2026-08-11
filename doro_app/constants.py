"""Constants for Doro application - extracted from Window to improve readability."""

# ═══════════════════════════════════════════════════════════
# Animation and Timing Constants
# ═══════════════════════════════════════════════════════════

TIMER_INTERVAL_MS = 16  # ~60 FPS (1000ms / 60 = 16.67ms)
BUBBLE_AUTO_HIDE_MS = 6000  # 6 seconds

# Idle behavior timing (seconds)
IDLE_BEHAVIOR_MIN_INTERVAL = 60.0   # 1 minute minimum between idle actions
IDLE_BEHAVIOR_MAX_INTERVAL = 180.0  # 3 minutes maximum between idle actions

# When Doro speaks on her own, how often she improvises via the LLM instead
# of using a pre-written line. Most idle chatter is free (canned lines shown
# straight in the bubble); only this fraction spends an LLM call. Set to 0.0
# to make idle speech entirely offline.
IDLE_LLM_SPEAK_CHANCE = 0.25

# ── Event-driven reactions (state mirror) ──────────────────────────
# Instead of firing on a blind random timer, Doro reacts when something
# actually happens: you switch apps, you've been glued to the chair, it's
# late, it's morning. All reactions are free (canned bubble lines).

# How often the reactor samples the world. Cheap: reads foreground class +
# idle seconds. 15s is fine-grained enough for human-scale events.
EVENT_POLL_INTERVAL_S = 15.0

# A newly-focused app must stay foreground this long before it counts as a
# real switch (not just alt-tabbing through). Doubles as the settle gate for
# the optional screen-read (proposal 7).
APP_SWITCH_SETTLE_S = 10.0

# Minimum gap between two app-switch *reactions* so hopping around apps
# doesn't make Doro chatter constantly.
APP_SWITCH_REACT_COOLDOWN_S = 5 * 60

# Idle longer than this counts as "took a break" — it resets the sitting
# timer so long-sitting only fires for genuinely continuous sessions.
SITTING_BREAK_S = 5 * 60

# Continuous active time before Doro nudges you to stretch. Fires once per
# sitting; resets after a break.
LONG_SITTING_THRESHOLD_S = 45 * 60

# Local-clock hour ranges (24h) for the time-of-day greetings. Each fires at
# most once per calendar day, and only while you're actually around.
LATE_NIGHT_HOURS = range(0, 5)   # 00:00–04:59
MORNING_HOURS = range(6, 10)     # 06:00–09:59

# ── Screen peek (proposal 7): the rare "comment on my screen" moment ──
# When you settle into a new app, Doro *may* read the foreground window's
# accessibility tree and improvise one LLM line about it. This is the only
# routinely-LLM path, so it is gated hard:
#   • opt-in — requires automation.a11y_enabled (off by default),
#   • rate-capped to at most once per this interval,
#   • paired with the app-switch settle (≥ APP_SWITCH_SETTLE_S) already done
#     by the EventReactor.
# The result: content-aware (vivid) but rare (cheap).
SCREEN_PEEK_MIN_INTERVAL_S = 12 * 60

# The (user-role) nudge sent when a peek fires. The a11y tree of the
# foreground window is attached automatically by the chat prompt builder,
# so this just tells Doro how to react to it.
SCREEN_PEEK_PROMPT = (
    "（人剛切換到新的畫面。偷看一下螢幕上有什麼，用你的語氣輕鬆講一句"
    "短短的感想或吐槽就好，不要照唸畫面上的文字。）"
)

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

# Max distance (physical px) between the cached `[move:to]` target and Doro's
# foot at click-fire time. If exceeded, `_fire_now` falls back to the foot
# rather than the stored target — guards against stale targets that survived
# a directional move, a drag, or a hallucinated LLM coordinate.
CLICK_PROXIMITY_THRESHOLD_PX = 300

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
# Automation (Phase 1c: restricted mouse click)
# ═══════════════════════════════════════════════════════════

# Wind-up duration before sending the synthetic click. Acts as the visible
# "she's about to do it" window during which the user can drag Doro elsewhere
# (redirecting the click) or press Esc (cancelling).
CLICK_WIND_UP_MS = 1500

# Minimum interval between two consecutive synthetic clicks, to defeat
# accidental LLM spam.
CLICK_RATE_LIMIT_MS = 2000

# After wind-up, if the user is still pressing the left mouse button, wait
# up to this many ms for them to release before firing (or giving up).
CLICK_DRAG_GRACE_MS = 1000

# Three Esc presses within KILL_SWITCH_ESC_WINDOW_MS disables automation
# globally.
KILL_SWITCH_ESC_COUNT = 3
KILL_SWITCH_ESC_WINDOW_MS = 800

# Default allowlist of foreground-window class names where automation is
# permitted to click. Entries are matched as case-insensitive *prefixes*
# of the foreground class (see AutomationManager._is_allowlisted), so
# `Chrome` covers Windows-side `Chrome_WidgetWin_1`, `Chrome_RenderWidget
# HostHWND`, etc. without one entry per variant.
DEFAULT_MOUSE_TARGET_ALLOWLIST: tuple[str, ...] = (
    "Firefox",             # Linux / older builds
    "MozillaWindowClass",  # Firefox on Windows
    "Chromium",
    "Chrome",              # Windows Chrome / Edge / Brave family → Chrome_WidgetWin_*
    "Navigator",
    "Google-chrome",
)

# ═══════════════════════════════════════════════════════════
# Accessibility tree reading (Phase 1d)
# ═══════════════════════════════════════════════════════════

# Foreground-window class fragments that suppress a11y tree reading entirely
# (case-insensitive substring match). Password managers, mail clients, and
# banking apps must never have their element trees serialized into a prompt.
DEFAULT_A11Y_APP_BLACKLIST: tuple[str, ...] = (
    "KeePassXC",
    "KeePass",
    "Bitwarden",
    "1Password",
    "thunderbird",
    "evolution",
)

# Hard ceiling on the serialized element block. Past this the serializer
# truncates and appends a "still N more" marker so the prompt can't blow up.
A11Y_MAX_SERIALIZED_BYTES = 4096

# Per-field caps applied during serialization. Foreground-window content
# is untrusted (a malicious web page can put anything in an element name
# or value); capping the per-field length keeps a single huge field from
# either dominating the prompt budget or being used to dodge the byte
# ceiling. Lengths are in *characters*, not bytes, so multi-byte text
# (Chinese, emoji) gets the same room as ASCII.
A11Y_NAME_MAX_CHARS = 80
A11Y_VALUE_MAX_CHARS = 120

# A single live tree read must return within this budget; UIA/AT-SPI can hang
# on some app states, so the read runs on a worker and is abandoned past this.
# This blocks the chat-send (main) thread, so it doubles as the max UI stall
# per message — keep it modest. Walking a browser subtree via COM is slow, so
# 0.1s was effectively "never succeeds".
A11Y_READ_TIMEOUT_SECONDS = 0.8

# The manual "preview what Doro sees" read is a one-off user action (not on the
# chat path), so it can wait long enough to actually finish a large tree walk.
A11Y_PREVIEW_TIMEOUT_SECONDS = 3.0

# UIA `Invoke()` can block until the target action completes (e.g. the
# clicked button opens a modal); without a timeout that would freeze
# the Qt main thread. The invoke is dispatched to the same executor
# the reads use, so an over-budget invoke is dropped as NOT_INVOCABLE
# rather than hanging the UI.
A11Y_INVOKE_TIMEOUT_SECONDS = 2.0

# Consecutive read timeouts for one window class before it is added to the
# session-local blacklist (so the LLM stops stalling every turn).
A11Y_TIMEOUT_BLACKLIST_THRESHOLD = 3

# ═══════════════════════════════════════════════════════════
# Mood / Affection (dual-axis emotion model)
# ═══════════════════════════════════════════════════════════

# Two persistent axes give Doro a sense of "being someone" rather than a
# GIF that moves (see design notes):
#   • mood       — how she feels *right now*; swings on events, drifts back
#                  to neutral. Range [-1, 1], 0 = neutral.
#   • affection  — the long-term bond; grows when the user interacts, fades
#                  slowly when ignored. Range [0, 1], 0 = distant/lonely.
MOOD_MIN = -1.0
MOOD_MAX = 1.0
AFFECTION_MIN = 0.0
AFFECTION_MAX = 1.0

# Exponential decay half-lives (seconds). Mood forgets a bad/good moment
# fairly quickly (~20 min to halve toward neutral); affection is a slow
# burn — a neglected Doro loses half her warmth over roughly a day, so
# regular attention is what keeps the bond up.
MOOD_DECAY_HALFLIFE_S = 20 * 60
AFFECTION_DECAY_HALFLIFE_S = 24 * 60 * 60

# Per-event nudges applied on top of decay. Deltas are deliberately small
# so a single interaction shifts the needle a little and the state is the
# accumulation of a relationship, not one click.
MOOD_EVENT_DELTAS: dict[str, tuple[float, float]] = {
    # event name        (mood_delta, affection_delta)
    "chat": (0.15, 0.05),   # user talked to Doro
    "pet": (0.12, 0.04),    # clicked / stroked
    "play": (0.08, 0.02),   # dragged around, took her for a walk
    "return": (0.10, 0.03),  # user came back after being away
    "ignored": (-0.06, -0.02),  # explicit "still nobody here" beat
}

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
