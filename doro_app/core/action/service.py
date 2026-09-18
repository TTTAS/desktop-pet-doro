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

from ...utils.logger import get_logger
from ..state import GifRepository, StateService
from .repository import CLICK_ACTION_KEY, PET_CLICK_ACTION_KEY, ActionRepository

logger = get_logger(__name__)


CLICK_ACTION_STATE_KEY = "click_action"
CLICK_ACTION_STATE_LABEL = "Click"

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
        default_idle_gif: Path | None = None,
    ) -> None:
        self._actions = action_repo
        self._state_service = state_service
        self._gif_repo = gif_repo
        self._default_idle_gif = default_idle_gif

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

    def _select_fallback_gif_id(self) -> str | None:
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

    def resolve_action_gif_path(self, action_key: str = CLICK_ACTION_KEY) -> Path | None:
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

        # Being clicked is an optional gesture, independent of desktop-click
        # wind-up. Without its own asset, retain the current sprite.
        if action_key == PET_CLICK_ACTION_KEY:
            return None

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

    def bind_pet_click_gif(self, source_path: Path) -> bool:
        """Persist the pet-click gesture asset without changing display state."""
        if not source_path.is_file():
            return False
        gif_id = self._state_service.store_gif(source_path, "pet_click_action")
        if not gif_id:
            return False
        return self._actions.update_gif_id(PET_CLICK_ACTION_KEY, gif_id)

    def unbind_pet_click_gif(self) -> bool:
        """Remove the optional gesture binding; keep the current sprite on click."""
        return self._actions.update_gif_id(PET_CLICK_ACTION_KEY, None)

    def bind_click_gif(self, source_path: Path) -> bool:
        """Store *source_path* as the click action's GIF.

        Writes to both the :class:`ActionRepository` (persistent
        ``gif_id``) and the underlying display state (so the next
        ``set_state(click_action)`` renders it).

        Returns ``True`` on success.
        """
        if not source_path.is_file():
            logger.warning(f"bind_click_gif: source not found: {source_path}")
            return False

        gif_id = self._state_service.store_gif(source_path, CLICK_ACTION_STATE_KEY)
        if not gif_id:
            return False

        if not self._actions.update_gif_id(CLICK_ACTION_KEY, gif_id):
            return False

        # Sync the display state's gif_id so set_state picks it up.
        self._state_service.update_state(CLICK_ACTION_STATE_KEY, gif_id=gif_id)
        return True

    def unbind_click_gif(self) -> bool:
        """Clear the user-bound GIF; subsequent clicks fall back to stand."""
        if not self._actions.update_gif_id(CLICK_ACTION_KEY, None):
            return False
        self._state_service.update_state(CLICK_ACTION_STATE_KEY, gif_id=None)
        return True
