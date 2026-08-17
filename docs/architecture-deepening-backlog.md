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

---

## #3 — Unify the triplicated wait-phase & listener plumbing

**Strength:** Worth exploring · needs a short grilling.

**Files:** `doro_app/core/action/phases.py`, `click_action.py`,
`movement_action.py`, `doro_app/core/automation/manager.py`,
`doro_app/core/movement/manager.py`

**Problem:** The "subscribe → fire once → timeout → unsubscribe" wait pattern is
copied three times (`WaitPhase` at `phases.py:120`, `_AwaitClickOutcomePhase` at
`click_action.py:39`, `_MovementWaitPhase` at `movement_action.py:31`), ~40 lines
each. The listener register/unsubscribe/snapshot-iterate idiom is duplicated
again across `AutomationManager` and `MovementManager`. Changing the retry/timeout
behaviour means editing three-to-five places.

**Direction:** One parameterised `WaitPhase` (takes "what to listen for" and
"timeout"); one shared listener-registry used by both managers. One interface, N
call sites → leverage; timeout/cancel bugs get a single home → locality.

**Decisions still open (grill these):** exact shape of the parameterised wait
interface; whether the listener registry is a mixin, a helper object, or a base
class; which existing tests survive vs. move.

---

## #4 — Collapse the automation port/backend forwarding

**Strength:** Worth exploring · needs one seam check.

**Files:** `doro_app/core/automation/port.py`, `backend_pynput.py`,
`window_class.py`, `coordinates.py`

**Problem:** `PynputBackend` (`backend_pynput.py:55-84`) forwards ~5 methods
one-line each to `window_class.py`; calls detour through two indirection layers to
reach the actual ctypes. `coordinates.py` exposes two pure functions that nothing
imports — `manager.py:399-424` re-does the same math inline (dead-shallow).

**Direction:** Fold `backend_pynput`'s forwarding into the port implementation
standing directly on `window_class`; delete the unused `coordinates.py`. Keep the
test fake as the second adapter that justifies the seam.

**Decision still open (the seam check):** confirm the only things behind this seam
are the real pynput path plus the test fake. *One adapter = hypothetical seam; two
= real.* If the fake is the only other adapter, decide whether the seam earns its
keep or should collapse too.

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
