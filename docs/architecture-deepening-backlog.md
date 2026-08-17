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

---

## #4 — Collapse the automation port/backend forwarding — ❌ SKIPPED (premise obsolete, 2026-08-17)

**Seam check outcome:** the entry's premise no longer holds. `coordinates.py`
is **not** dead — it has four production importers today:
`app.py:849` (`compute_physical_pixel_at`), `ui/window.py:489`,
`ui/click_warning_overlay.py:65`, and
`ui/components/context_menu_controller.py:187` (all `compute_*` helpers).
Deleting it would break the build. The claim that `manager.py:399-424`
re-does the same math inline is also false — the manager reads ready-made
physical coords from the window port; the logical↔physical conversion lives
only in `coordinates.py` and its callers.

The `PynputBackend` "forwarding" (5 window-class methods) is a genuine
testability seam: `FakeInputBackend` substitutes for it, and it bridges the
manager to the deliberately pynput-free `window_class.py`. Collapsing it would
either break the port abstraction or need a larger restructure with unclear
benefit.

**Verdict:** a formerly-dead module grew real users — the healthy outcome.
Nothing to collapse. Left in place.

---

## #5 — Split the chat controller: settings store vs. retry machine

**Strength:** Worth exploring · needs a short grilling.

**Files:** `doro_app/core/chat/controller.py` (536 lines), `orchestrator.py`
(441), `validator.py`

**Problem:** `controller.py` fuses two responsibilities: a wide, shallow settings
store (~12 property/setter pairs, `controller.py:152-234`) and a genuinely deep
worker/retry state machine (`controller.py:236-433`). The settings half inflates
the interface without depth. Retry logic is split across a seam: `validator.py`
owns `should_retry`/`build_retry_prompt` (`validator.py:123-156`) but the retry
counter, max-retry gate, and delay live in `controller._handle_worker_result`
(`controller.py:326-349`) — a retry bug could hide in either file. `orchestrator`
adds 14 pass-through config methods (`orchestrator.py:91-161`).

**Direction:** Extract a `ChatSettings` module; pull the retry counter/limit/delay
together with `should_retry` into one deep request module so retry logic has
locality.

**Decisions still open (grill these):** where the settings live and who owns
persistence; whether the orchestrator's 14 forwarders go away with it; the
boundary between the request machine and the validator.

---

## #6 — Remove the speculative sprite-renderer registry

**Strength:** Speculative · needs one roadmap question (YAGNI).

**Files:** `doro_app/ui/rendering/sprite_renderer.py` (Protocol),
`doro_app/ui/controllers/sprite_controller.py:40-82`, `gif_sprite_renderer.py`,
`doro_app/ui/components/gif_player.py`

**Problem:** `sprite_renderer.py` is a Protocol with a single implementation; the
"future SpineSpriteRenderer" (`sprite_renderer.py:15`) does not exist. The
renderer registry in `SpriteController` (`:40-82`) switches between renderers that
aren't there. A GIF's lifetime is also split three ways across `GifPlayer`,
`SpriteController`, and `GifSpriteRenderer`.

**Direction:** *One adapter does not make a seam.* Remove the Protocol and
registry; use `GifSpriteRenderer` directly. Reintroduce the seam only when a real
second renderer (e.g. Spine) actually arrives.

**Decision still open (the roadmap question):** is a second renderer (Spine or
otherwise) genuinely planned for the near term? If yes, keep the seam and skip
this. If no, collapse it.

> **Status (2026-08-17):** roadmap intent is **undecided** — the owner was not
> sure whether a second renderer is coming. Left untouched pending that call.
> Do NOT collapse the registry until "no second renderer" is confirmed;
> re-open this entry once the roadmap is settled.

---

## Follow-up spun off during #1

- **(b) — StateService reaches into collection privates.** `service.py` touches
  `self._states._items` / `._protected_keys` / `._current_key` and
  `self._move_states._movement_only_keys` (e.g. `service.py:388, 649, 677, 223,
  521, 701, 227, 935`), breaking encapsulation of the collection classes in
  `models.py`. Give those collections proper public methods so `StateService`
  stops touching underscore-prefixed fields. Behaviour-preserving.

---

*Generated from an architecture review run via `/improve-codebase-architecture`.
The original visual (HTML) report is not kept in the repo; this file is the
durable record.*
