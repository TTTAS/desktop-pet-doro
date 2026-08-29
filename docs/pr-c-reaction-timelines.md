# PR C — reaction timelines (slice 1)

**Branch:** `refactor/state-collections-and-gif-renderer`
**Does not touch:** master, ActionDispatcher internals, IdleBehaviorManager wiring.

## What this slice is

A Qt-free sequencer for short, *registered* reactions:

- `state` — `request_state`
- `wait` — injected `schedule(ms, cb)`
- `speak` — injected speak port (finished line, no LLM)
- `move` — optional; skipped if no move port

One director, one timeline at a time. Higher priority preempts.
Click (`20`) beats chat (`10`) beats idle (`0`).

Not in this slice: Dialogic, visual editor, JSON/LLM-authored timelines,
rewiring `IdleBehaviorManager` or click handling.

## Files

| File | Role |
|---|---|
| `doro_app/core/reaction/timeline.py` | Step + Timeline data |
| `doro_app/core/reaction/catalog.py` | Named registry + default click/idle stubs |
| `doro_app/core/reaction/director.py` | Play / cancel / preemption |
| `tests/core/reaction/test_director.py` | Contract tests |

## Verify

```powershell
pytest tests/core/reaction/test_director.py tests/core/state/test_request_commit_lock.py tests/core/state/test_state_protection.py -q --no-cov
```
