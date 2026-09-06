"""High-level action service (Phase 1c).

Responsibilities:

1. **Bootstrap.** Ensure :data:`CLICK_ACTION_KEY` (``click``) exists in the
   :class:`ActionRepository` and a corresponding **protected, hidden**
   display state lives on the :class:`StateService` (key
   :data:`CLICK_ACTION_STATE_KEY`). The state is hidden so it does NOT
   appear in the user-facing personality state menu nor as an idle pick.

2. **GIF resolution.** :meth:`resolve_action_gif_path` returns a Path
   that is *always* playable, even when the user has not bound a GIF:

   - Step 1: the user-bound ``gif_id`` (if any) → resolved via
     :class:`GifRepository`.
   - Step 2: ``pick_random_gif("stand")`` — random GIF from the user's
     stand subfolder (matches how ``stand`` is already populated).
   - Step 3: the single-file ``stand.gif`` fallback.
   - Step 4 (last resort): :data:`default_idle_gif`, which the
     bootstrap always provisions.

3. **Binding.** :meth:`bind_click_gif` writes a user-uploaded GIF as both
   the click action's :class:`ActionEntry.gif_id` and the underlying
   display state's :attr:`State.gif_id`, so the AutomationManager state
   switch and the dialog UI agree on what to render.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...utils import paths
from ...utils.logger import get_logger
from ..state import GifRepository, StateService
from .repository import CLICK_ACTION_KEY, DRAG_ACTION_KEY, ActionRepository

logger = get_logger(__name__)


CLICK_ACTION_STATE_KEY = "click_action"
CLICK_ACTION_STATE_LABEL = "Click"

# Drag reaction — played while the user drags Doro. Modelled exactly like
# the click action: a hidden, protected display state the app flips to on
# drag-start and restores on release. Hidden so it never leaks into the
# States menu nor idle's random picker; it is surfaced to the user only as
# a card in the Action Manager.
DRAG_ACTION_STATE_KEY = "dragged"
DRAG_ACTION_STATE_LABEL = "拖曳"

# Action key -> (display state key, label). The registry of named actions
# that drive a display-state flip. Adding a reaction is one row here plus a
# builtin in ActionRepository — no new plumbing.
_ACTION_STATE_KEYS: dict[str, tuple[str, str]] = {
    CLICK_ACTION_KEY: (CLICK_ACTION_STATE_KEY, CLICK_ACTION_STATE_LABEL),
    DRAG_ACTION_KEY: (DRAG_ACTION_STATE_KEY, DRAG_ACTION_STATE_LABEL),
}

# Hidden builtin state the ActionDispatcher flips to when a click
# action fails (preflight rejection, allowlist miss, drag-grace
# exceeded, etc.). Kept distinct from `click_action` so the user can
# bind a different GIF — a sad / shrug animation — to make failures
# legible. Until a GIF is bound, the resolution chain falls back to
# the same stand/idle pool as `click_action`.
CLICK_FAILED_STATE_KEY = "click_failed"
CLICK_FAILED_STATE_LABEL = "Click Failed"


class ActionService:
    """Coordinate :class:`ActionRepository` with the display state machine."""

    def __init__(
        self,
        action_repo: ActionRepository,
        state_service: StateService,
        gif_repo: GifRepository,
        default_idle_gif: Optional[Path] = None,
        drag_assets_dir: Optional[Path] = None,
    ) -> None:
        self._actions = action_repo
        self._state_service = state_service
        self._gif_repo = gif_repo
        self._default_idle_gif = default_idle_gif
        # Where the bundled default drag GIFs live. Injectable so tests stay
        # off the real filesystem; production uses res/drag/.
        self._drag_assets_dir = (
            drag_assets_dir if drag_assets_dir is not None
            else paths.RESOURCES_DIR / "drag"
        )

    # ─── Bootstrap ─────────────────────────────────────────────────

    def bootstrap(self) -> None:
        """Register the click display state and persist any new defaults.

        Idempotent — safe to call multiple times. Should run after
        :meth:`StateService.initialize`. Resolves the click GIF to a
        bootstrap-time effective ``gif_id``:

        - Use the user-bound ``gif_id`` from :class:`ActionRepository`
          if any.
        - Otherwise probe the bundled ``res/state/`` for a stand-family
          fallback so :meth:`StateService.set_state` can render
          *something* on the very first click.
        """
        self._actions.load()

        click_entry = self._actions.get(CLICK_ACTION_KEY)
        user_gif_id = click_entry.gif_id if click_entry else None
        effective_gif_id = user_gif_id or self._select_fallback_gif_id()

        self._state_service.ensure_action_state(
            key=CLICK_ACTION_STATE_KEY,
            label=CLICK_ACTION_STATE_LABEL,
            gif_id=effective_gif_id,
        )

        # Register the failure-state too. Same fallback chain — until
        # the user binds a dedicated GIF the dispatcher's brief flip
        # will show a stand/idle frame, which is still better than the
        # hard `set_state failed` error that otherwise pollutes the log.
        self._state_service.ensure_action_state(
            key=CLICK_FAILED_STATE_KEY,
            label=CLICK_FAILED_STATE_LABEL,
            gif_id=effective_gif_id,
        )

        # Register the drag reaction's hidden display state and seed it with
        # the bundled default GIFs on first run.
        self._state_service.ensure_action_state(
            key=DRAG_ACTION_STATE_KEY,
            label=DRAG_ACTION_STATE_LABEL,
            gif_id=None,
        )
        self._seed_drag_defaults()

    def _seed_drag_defaults(self) -> None:
        """Populate the drag state's GIF pool from ``res/drag/`` on first run.

        Idempotent: only seeds when the drag state has no GIFs yet, so a user
        who later rebinds or clears the drag GIF is never overwritten. The
        bundled files are picked up as a multi-GIF pool (random pick at drag
        time); missing/empty ``res/drag/`` just leaves the fallback chain to
        show a stand pose.
        """
        if self._state_service.list_gif_paths(DRAG_ACTION_STATE_KEY):
            return  # already seeded or user-populated — leave it alone

        drag_dir = self._drag_assets_dir
        if not drag_dir.is_dir():
            return

        seeded = 0
        for asset in sorted(drag_dir.iterdir()):
            if asset.suffix.lower() in (".gif", ".webp", ".apng"):
                if self._state_service.add_gif(DRAG_ACTION_STATE_KEY, asset):
                    seeded += 1
        if seeded:
            logger.info(f"Seeded {seeded} default drag GIF(s) from {drag_dir}")

    def _select_fallback_gif_id(self) -> Optional[str]:
        """Pick a non-user-bound ``gif_id`` for the click state at bootstrap.

        Order: random pick from ``stand/`` → single-file ``stand.gif`` →
        single-file ``idle.gif``. Returns ``None`` if even the
        ``default_idle_gif`` provisioned at bootstrap is missing — in
        that case the click still works, the renderer just shows nothing
        new during wind-up.
        """
        # 1. Random pick from stand/ subfolder, expressed as a gif_id
        #    relative to GifRepository.storage_dir so get_path() resolves it.
        random_stand = self._gif_repo.pick_random_gif("stand")
        if random_stand:
            try:
                rel = random_stand.relative_to(self._gif_repo.storage_dir)
                return str(rel).replace("\\", "/")
            except ValueError:  # pragma: no cover - defensive
                pass

        # 2. Single-file stand.gif (bundled with the app).
        stand_single = self._gif_repo.get_path("stand.gif")
        if stand_single and stand_single.is_file():
            return "stand.gif"

        # 3. Idle GIF (always provisioned by bootstrap).
        idle_single = self._gif_repo.get_path("idle.gif")
        if idle_single and idle_single.is_file():
            return "idle.gif"

        return None

    # ─── Public API ────────────────────────────────────────────────

    @property
    def click_state_key(self) -> str:
        """The State key used by AutomationManager to drive the wind-up GIF."""
        return CLICK_ACTION_STATE_KEY

    @property
    def drag_state_key(self) -> str:
        """The State key the app flips to while the user drags Doro."""
        return DRAG_ACTION_STATE_KEY

    # ─── Registry queries (used by the Action Manager UI) ───────────

    def named_action_keys(self) -> list[str]:
        """All registered named-action keys, builtins first in a stable order."""
        keys = self._actions.all_keys()
        builtin_order = [k for k in _ACTION_STATE_KEYS if k in keys]
        rest = [k for k in keys if k not in _ACTION_STATE_KEYS]
        return builtin_order + rest

    def get_action_display_name(self, action_key: str) -> str:
        """Human-facing label for an action (falls back to a titled key)."""
        entry = self._actions.get(action_key)
        if entry and entry.display_name:
            return entry.display_name
        return action_key.title()

    def action_state_key(self, action_key: str) -> Optional[str]:
        """The hidden display-state key an action flips to, if known."""
        mapping = _ACTION_STATE_KEYS.get(action_key)
        return mapping[0] if mapping else None

    def list_action_gif_paths(self, action_key: str) -> list[Path]:
        """All GIFs currently bound to an action (its display-state pool).

        Used by the Action Manager to show a navigable preview. Falls back to
        the single resolved path (stand/idle) when the pool is empty so the
        card always previews what the next play will render.
        """
        state_key = self.action_state_key(action_key)
        if state_key:
            pool = self._state_service.list_gif_paths(state_key)
            if pool:
                return pool
        resolved = self.resolve_action_gif_path(action_key)
        return [resolved] if resolved else []

    def resolve_action_gif_path(self, action_key: str = CLICK_ACTION_KEY) -> Optional[Path]:
        """Return a playable GIF path for *action_key* using the fallback chain.

        Returns ``None`` only if every fallback also fails (very unusual —
        means the ``res/state/`` directory is empty).
        """
        # Step 1: user-bound gif_id on the ActionEntry.
        entry = self._actions.get(action_key)
        if entry and entry.gif_id:
            path = self._gif_repo.get_path(entry.gif_id)
            if path and path.is_file():
                return path

        # Step 1.5: the action's own display-state pool (multi-GIF subfolder
        # or synced state gif_id) — this is what the runtime actually plays,
        # e.g. the bundled drag webp that live in the drag state's subfolder.
        state_key = self.action_state_key(action_key)
        if state_key:
            state_path = self._state_service.get_gif_path(state_key)
            if state_path and state_path.is_file():
                return state_path

        # Step 2: random pick from the stand/ subfolder.
        random_stand = self._gif_repo.pick_random_gif("stand")
        if random_stand and random_stand.is_file():
            return random_stand

        # Step 3: single-file stand.gif fallback.
        stand_single = self._gif_repo.get_path("stand.gif")
        if stand_single and stand_single.is_file():
            return stand_single

        # Step 4: default idle GIF (always present after bootstrap).
        if self._default_idle_gif and self._default_idle_gif.is_file():
            return self._default_idle_gif

        return None

    def bind_action_gif(self, action_key: str, source_path: Path) -> bool:
        """Store *source_path* as *action_key*'s GIF.

        Writes to both the :class:`ActionRepository` (persistent ``gif_id``)
        and the underlying display state (so the next ``set_state`` renders
        it). Any existing multi-GIF pool for the display state (e.g. the
        bundled drag defaults) is cleared first, so after a rebind exactly
        the chosen GIF plays rather than a stale random pick.

        Returns ``True`` on success.
        """
        state_key = self.action_state_key(action_key)
        if state_key is None:
            logger.warning(f"bind_action_gif: unknown action '{action_key}'")
            return False
        if not source_path.is_file():
            logger.warning(f"bind_action_gif: source not found: {source_path}")
            return False

        # Drop any seeded/multi-GIF pool so the single chosen GIF wins the
        # get_gif_path priority chain (subfolder is checked before gif_id).
        self._state_service.delete_all_gifs(state_key)

        gif_id = self._state_service.store_gif(source_path, state_key)
        if not gif_id:
            return False

        if not self._actions.update_gif_id(action_key, gif_id):
            return False

        # Sync the display state's gif_id so set_state picks it up.
        self._state_service.update_state(state_key, gif_id=gif_id)
        return True

    def unbind_action_gif(self, action_key: str) -> bool:
        """Clear the user-bound GIF; playback falls back down the chain."""
        state_key = self.action_state_key(action_key)
        if state_key is None:
            return False
        if not self._actions.update_gif_id(action_key, None):
            return False
        self._state_service.update_state(state_key, gif_id=None)
        return True

    # Back-compat thin wrappers — existing callers bind the click action.
    def bind_click_gif(self, source_path: Path) -> bool:
        return self.bind_action_gif(CLICK_ACTION_KEY, source_path)

    def unbind_click_gif(self) -> bool:
        return self.unbind_action_gif(CLICK_ACTION_KEY)
