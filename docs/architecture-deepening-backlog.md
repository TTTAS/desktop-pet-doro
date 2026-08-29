# Architecture Deepening Backlog

Remaining **deepening opportunities** from an architecture review of the `doro_app`
core. The theme across all of them: the hexagonal `port / adapter / service /
manager / repository` ceremony, applied to every module, produced a number of
**shallow modules** — a stack of files whose interface is nearly as wide as the
implementation, mostly forwarding calls to the next layer down.

Vocabulary here is the `/codebase-design` glossary: **module, interface, depth,
deep, shallow, seam, adapter, leverage, locality**. Each candidate is a chance to
fold a shallow forwarding layer into a deep module.

**How to use this file:** pick one candidate, open a fresh session, and work it
through `/grilling` (for the ones that need decisions) before building. Do one at
a time and commit between them. Delete an entry once it's done.

---

## Done

- **#1 — Collapse the GIF access stack** — `refactor(state): collapse GIF access
  stack, remove GifManager`. `GifManager` removed; `StateService` talks to
  `GifRepository` directly.
- **#2 — Delete dead code + de-duplicate StateController** — `refactor(ui):
  delete dead GifController, de-duplicate StateController`. `GifController`
  deleted; `StateController`'s duplicated visual-config block extracted.
- **#3 — Unify the triplicated wait-phase & listener plumbing** — the three
  wait phases collapsed into one parameterised `WaitPhase` (`resolve` /
  `timeout_reason` / `precondition` hooks); `_AwaitClickOutcomePhase` and
  `_MovementWaitPhase` deleted. The duplicated listener idiom in both managers
  now uses one shared `ListenerRegistry` (helper object, composition) in
  `doro_app/core/listeners.py`.
- **#5 — Split the chat controller** — done in two stages. Stage 1:
  `ChatSettings` (`core/chat/settings.py`) owns the settings store +
  persistence; `ChatController` exposes it via `.settings`; the orchestrator's
  14 pass-through config forwarders collapsed to one `settings` accessor.
  Stage 2: `ChatRetryPolicy` (`core/chat/retry.py`) owns the retry counter,
  limit, original-message, and decision (`should_retry`/`build_retry_prompt`
  moved off `ResponseValidator`, which is now pure validation).
- **(b) — StateService reaches into collection privates.** Done on
  `refactor/state-collections-and-gif-renderer` (2026-08-29). Collections expose
  `current_key()` / `items()` / `protected_keys()` / `hidden_keys()` /
  `movement_only_keys()`; keys go through `normalize_state_key()`; `StateService`
  no longer reads underscore fields.

---

## #4 — Collapse the automation port/backend forwarding — ❌ SKIPPED (premise obsolete, 2026-08-17)

Left in place. See previous status note.

---

## #6 — Remove the speculative sprite-renderer registry

**Decision (2026-08-29):** no second renderer is planned (Live2D already gone,
Spine not on the roadmap). **WebP / APNG are not a second renderer** — they share
the QMovie path with GIF via `ANIMATED_EXTENSIONS`.

**Status:** collapse is approved but **deferred** so PR A stays a collection-only
diff. Next small commit on this branch should flatten `SpriteController`
(`_renderers`, `switch_renderer`, `tick`) down to one `GifSpriteRenderer`,
keeping `.gif` / `.apng` / `.webp` loading unchanged.

---

*Generated from an architecture review. This file is the durable record.*
