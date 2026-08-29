# PR C — reaction timelines

**Branch:** `refactor/state-collections-and-gif-renderer`
**Does not touch:** master, ActionDispatcher internals, IdleBehaviorManager internals.

## Slice 1 — sequencer (landed)

A Qt-free sequencer for short, *registered* reactions:

- `state` — `request_state`
- `wait` — injected `schedule(ms, cb)`
- `speak` — injected speak port (finished line, no LLM)
- `move` — optional; skipped if no move port
- `restore` — return to the committed key captured at play start

One director, one timeline at a time. Higher priority preempts.
Click (`20`) beats chat (`10`) beats idle (`0`).

Not in this PR: Dialogic, visual editor, JSON/LLM-authored timelines.

## Slice 2 — play-by-name + click hook (landed)

- `ReactionRunner.play(name)` looks up the catalog and starts the director
- Default `click` timeline: `click_action` (force) → wait 0.4s → `RestoreStep`
- `CoreManager.on_user_clicked()` plays `"click"` when a runner is injected
- `ClickActionController` (chat line on click) and `IdleBehaviorManager`
  stay as they are; idle is still not a timeline consumer
- `DoroApp` composition (build runner + hook mouse click) is the next small wiring

## Files

| File | Role |
|---|---|
| `doro_app/core/reaction/timeline.py` | Step + Timeline data |
| `doro_app/core/reaction/catalog.py` | Named registry + default click/idle stubs |
| `doro_app/core/reaction/director.py` | Play / cancel / preemption / restore |
| `doro_app/core/reaction/runner.py` | `play(name)` facade |
| `doro_app/core/reaction/factory.py` | `build_default_runner` |
| `doro_app/core/core_manager.py` | optional runner; `on_user_clicked` |
| `tests/core/reaction/test_director.py` | Contract tests |
| `tests/core/test_core_manager_click.py` | click hook when runner present / absent |

## Verify

```powershell
pytest tests/core/reaction/test_director.py tests/core/test_core_manager_click.py tests/core/test_core_manager.py tests/core/state/test_request_commit_lock.py tests/core/state/test_state_protection.py -q --no-cov
```
