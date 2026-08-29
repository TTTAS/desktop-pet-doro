# PR C — reaction timelines

**Branch:** `refactor/state-collections-and-gif-renderer`
**Does not rewrite:** ActionDispatcher internals, IdleBehaviorManager internals.

## Slice 1 — sequencer

Qt-free steps: `state` / `wait` / `speak` / optional `move` / `restore`.
One director at a time. Click (20) beats chat (10) beats idle (0).

## Slice 2 — play-by-name + CoreManager hook

- `ReactionRunner.play(name)`
- Default `click`: `click_action` (force) → wait 0.4s → `RestoreStep`
- `CoreManager.on_user_clicked()` plays `"click"` when a runner is injected

## Slice 3 — DoroApp wiring

`DoroApp` builds the runner with:

- `request_state` → `StateService.request_state`
- `speak` → `ChatOrchestrator.speak_line`
- `schedule` → existing `QTimer.singleShot` helper
- `move` → `MovementManager.apply_directional_walk`
- `current_key` → `StateService.get_committed_state_key`

Then:

- passes `reaction_runner` into `CoreManager`
- mouse `click_detected` calls `core_manager.on_user_clicked()` **before** `ClickActionController.trigger_random_action()`
- drag calls `runner.cancel()` so a click flash does not outlive the drag

Chat-on-click and idle wander stay as they were.

## Verify

```powershell
pytest tests/core/reaction/test_director.py tests/core/test_core_manager_click.py tests/core/test_core_manager.py tests/core/state/test_request_commit_lock.py tests/core/state/test_state_protection.py -q --no-cov
```

Manual: click Doro → click GIF for ~0.4s → back to the previous state; click-action chat line still fires if configured.
