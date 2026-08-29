# State refactor plan (doro-exp-)

**Branch:** `refactor/state-collections-and-gif-renderer`
**Desktop pet UI:** Python + PySide6. No Godot, no Live2D.

Sprites are **QMovie animated images**: `.gif`, `.apng`, `.webp`.
That is one renderer backend, not a second one.

---

## PR A — collection encapsulation (done)

- Restored collections on `models.py`
- `normalize_state_key()` = strip + lowercase
- `StateService` uses collection public API
- Tests: `tests/core/state/test_collection_api.py`

## PR B — request / commit + lock timeout (done)

- `requested_key` vs `committed_key` inlined on `StateService`
- `set_state` wraps `request_state`
- Lock expires after 5s; queue drains on end / expiry
- Option A stale-target guard on `TransitionPlayer`
- Details: `docs/pr-b-request-commit.md`

## PR C — reaction timelines (done, wired)

- `doro_app/core/reaction/` + `ReactionRunner` + `build_default_runner`
- Steps: `state` / `wait` / `speak` / optional `move` / `restore`
- `DoroApp` injects the runner into `CoreManager` and hooks mouse click
- `IdleBehaviorManager` still picks speak/move itself
- Details: `docs/pr-c-reaction-timelines.md`
- PR 說明（可直接貼）：`docs/pr-state-reaction.md`

---

## Left for a later PR

- Drop `_renderers` / `switch_renderer` (already decided)
- Optional: idle actions via catalog

## Sprite formats (do not regress)

`GifRepository.ANIMATED_EXTENSIONS = (".gif", ".apng", ".webp")`

- Repository lookup and `add_gif` keep the source suffix
- File dialogs: `Animated Images (*.gif *.apng *.webp)`
- Playback: `QMovie(path)` + `isValid()` — no per-suffix renderer
