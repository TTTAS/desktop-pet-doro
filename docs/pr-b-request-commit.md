# PR B — request / commit + lock timeout

**Branch:** `refactor/state-collections-and-gif-renderer`
**Does not touch:** master, MovementManager wiring, reaction timelines, renderer flatten.

## Behaviour

- `requested_key` — last intended target. While the transition lock is held,
  new `set_state` / `request_state` calls queue here (last write wins) and
  still return `False` so existing protection tests stay green.
- `committed_key` — `StateCollection.current_key()`. This is what
  `get_current_state_key()` returns.
- `set_state` is a thin wrapper around `request_state`.
- `force=True` commits immediately and replaces any queued request.
- Lock timeout defaults to **5.0s** (`DEFAULT_LOCK_TIMEOUT_SECONDS`).
- `end_transition()` and lock expiry both call `_apply_pending_request()`.
- `TransitionPlayer.dispose()` releases the lock on teardown.
- **Option A:** after `end_transition()`, emit `transition_completed` only
  when `committed_key == original target`. A queued request that moved
  committed off the clip target must not reload the stale sprite.
  `_is_playing` is cleared *before* `end()` so the queued target can start
  a new transition.

## Files

| File | Status |
|---|---|
| `doro_app/core/state/transition_coordinator.py` | done (timeout + clock) |
| `doro_app/core/state/transition_complete.py` | done (Qt-free emit guard) |
| `doro_app/core/state/transition_player.py` | done (dispose + guard + flag-before-end) |
| `doro_app/core/state/service.py` | done — request/commit inlined on the class |
| `doro_app/core/state/request_commit.py` | removed (was import-time monkeypatch) |
| `tests/core/state/test_request_commit_lock.py` | done |
| `tests/core/state/test_transition_complete_guard.py` | done |
| `tests/core/state/test_transition_player_guard.py` | done (player wiring) |

## Verify

```powershell
pytest tests/core/state/test_request_commit_lock.py tests/core/state/test_transition_complete_guard.py tests/core/state/test_transition_player_guard.py tests/core/state/test_transition_coordinator.py tests/core/state/test_state_protection.py tests/core/state/test_service.py -q --no-cov
```
