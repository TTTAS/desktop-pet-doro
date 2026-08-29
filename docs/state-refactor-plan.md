# State refactor plan (doro-exp-)

**Branch:** `refactor/state-collections-and-gif-renderer`  
**Does not touch:** `master` until an explicit PR  
**Desktop pet UI:** Python + PySide6. No Godot, no Live2D.
a11y / pynput / chat APIs stay; this refactor does not remove them.

Sprites are **QMovie animated images**: `.gif`, `.apng`, `.webp`.
That is one renderer backend, not a second one. WebP does not justify
keeping the `_renderers` / `switch_renderer` registry.

---

## PR A — collection encapsulation (this branch, done)

1. Restore the truncated `models.py` (collections were dropped on this branch).
2. `normalize_state_key()` = strip + lowercase; collections store only that form.
3. Public reads so `StateService` stops touching `_items` / `_current_key` /
   `_protected_keys` / `_movement_only_keys`:
   - `StateCollection.current_key()` / `items()` / `protected_keys()` / `hidden_keys()`
   - `MoveStateCollection.items()` / `movement_only_keys()`
4. `StateService` persistence and queries go through those methods.
5. Tests: `tests/core/state/test_collection_api.py`

Renderer flatten is **not** in A. Class names stay `Gif*` for now;
docs call them "QMovie animated images".

## PR B — request / commit + lock timeout (this branch, done)

- `requested_key` vs `committed_key` on `StateService` (inlined in `service.py`)
- `set_state` remains a thin wrapper around `request_state`
- Transition lock expires after 5s (injectable clock)
- `end_transition()` / lock expiry apply the last queued request
- Player success / failure / dispose all call `end()`
- Option A guard: skip stale `transition_completed` emit
- Details: `docs/pr-b-request-commit.md`

## PR C — reaction timelines (not started)

- `doro_app/core/reaction/` (`timeline`, `catalog`, `director`)
- First steps: `state` / `wait` / `speak` / optional `move`
- Click beats idle; chat maps onto short registered timelines
- No Dialogic port, no visual editor, no LLM-authored freeform timelines

---

## Sprite formats (do not regress)

`GifRepository.ANIMATED_EXTENSIONS = (".gif", ".apng", ".webp")`

- Repository lookup and `add_gif` keep the source suffix
- File dialogs: `Animated Images (*.gif *.apng *.webp)`
- Playback: `QMovie(path)` + `isValid()` — no per-suffix renderer
- Qt animated-WebP support is platform-dependent; invalid files fall back
  the same way a broken GIF does
