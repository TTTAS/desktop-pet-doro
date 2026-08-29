# PR B — request / commit + lock timeout

**Branch:** `refactor/state-collections-and-gif-renderer`
**Does not touch:** master, Window/MovementManager wiring, reaction timelines, renderer.

## Behaviour

- `requested_key` — last intended target. While the transition lock is held,
  new `set_state` / `request_state` calls queue here (last write wins) and
  still return `False` so existing protection tests stay green.
- `committed_key` — `StateCollection.current_key()`. This is what
  `get_current_state_key()` returns and what the sprite should show.
- `set_state` is a thin wrapper around `request_state`.
- `force=True` commits immediately and replaces any queued request.
- Lock timeout defaults to **5.0s** (`DEFAULT_LOCK_TIMEOUT_SECONDS`).
  `begin()` records a monotonic timestamp; `is_active()` / `expire_if_needed()`
  release a stale lock so a missed `end()` cannot freeze the pet.
- `end_transition()` and lock expiry both call `_apply_pending_request()`.
- `TransitionPlayer.dispose()` must call `end_transition()` so close / failed
  load / exception paths all release the lock.

## Files

| File | Change |
|---|---|
| `doro_app/core/state/transition_coordinator.py` | timeout + injectable clock |
| `doro_app/core/state/service.py` | request / commit API |
| `doro_app/core/state/transition_player.py` | `dispose()` |
| `tests/core/state/test_request_commit_lock.py` | contract tests |
| `tests/core/state/test_state_protection.py` | unchanged; still expects `set_state` False while locked |

## Verify

```bash
pytest tests/core/state/test_request_commit_lock.py tests/core/state/test_transition_coordinator.py tests/core/state/test_state_protection.py tests/core/state/test_service.py -q
```
