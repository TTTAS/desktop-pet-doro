# Architecture Audit - Current State

**Date:** 2025-12-01
**Purpose:** Assess current decoupling before starting Phase 4

---

## Executive Summary

**Good News:** The codebase is already MORE decoupled than expected!

**Key Findings:**
- ✅ StateController uses Signals (not direct calls)
- ✅ MovementManager uses Protocol/Port pattern
- ✅ Controllers don't directly reference Window
- ⚠️ Some areas still need work (StateService size, TransitionPlayer)

---

## Component Analysis

### StateController (✅ Well Decoupled)

**Location:** `doro_app/ui/controllers/state_controller.py`
**Size:** 193 lines
**Status:** ✅ GOOD

**Uses Signals:**
```python
repaint_requested = QtCore.Signal()
state_changed = QtCore.Signal(str)
state_list_updated = QtCore.Signal(str)
```

**Communication Pattern:**
```
StateService ──event──> StateController ──signal──> Window
```

**No direct Window calls found.** ✅

---

### MovementManager (✅ Uses Port Pattern)

**Location:** `doro_app/core/movement/manager.py`
**Size:** ~400 lines
**Status:** ✅ GOOD (uses Protocol)

**Uses Protocol:**
```python
class MovementWindowPort(Protocol):
    """Interface for movement-related window operations."""
    def frameGeometry(self) -> QtCore.QRect: ...
    def current_position(self) -> QtCore.QPoint: ...
    def clamp_window_position(self, pos: QtCore.QPoint) -> QtCore.QPoint: ...
    # ... etc
```

**Benefits:**
- MovementManager depends on interface, not concrete class
- Can be mocked for testing
- Clear contract for what window must provide

---

### GifController (✅ Well Decoupled)

**Location:** `doro_app/ui/controllers/gif_controller.py`
**Size:** 134 lines
**Status:** ✅ GOOD

**No window references found.**
**Uses ViewModel for state updates.**

---

### StateService (⚠️ Too Large - Main Target)

**Location:** `doro_app/core/state/service.py`
**Size:** 809 lines ⚠️
**Status:** 🔴 NEEDS WORK

**Too Many Responsibilities:**
1. State transitions ✓ (core responsibility)
2. GIF operations (should be extracted → GifManager)
3. Transition coordination (should be extracted → TransitionCoordinator)
4. Event callbacks (acceptable)
5. State persistence (acceptable - delegates to Repository)

**Plan:** Extract to ~200 lines (Phase 4.2)

---

### TransitionPlayer (⚠️ Depends on DoroWindow)

**Location:** `doro_app/core/state/transition_player.py`
**Size:** 250 lines
**Status:** ⚠️ ACCEPTABLE (but could be better)

**Issue:**
```python
from ...window import DoroWindow  # Direct import

def __init__(self, window: DoroWindow, gif_label: QtWidgets.QLabel):
    self._window = window  # Stores reference
```

**Why it's needed:**
- Needs to emit signals to window
- Needs GIF label for playback

**Possible improvement:**
- Use Protocol instead of concrete class
- Or: Make TransitionPlayer emit signals, Window listens

**Priority:** Medium (works, but not ideal)

---

### DoroWindow (⚠️ Too Large)

**Location:** `doro_app/ui/window.py`
**Size:** 679 lines ⚠️
**Status:** 🔴 NEEDS WORK

**Too Many Responsibilities:**
1. Qt window management ✓ (core)
2. Component coordination (should be in Mediator)
3. Menu handling (could be extracted to MenuManager)
4. Mouse/keyboard events ✓ (core)
5. Visual updates ✓ (core)

**Plan:** Reduce to ~300-400 lines (Phase 4.3)

---

## Circular Dependencies Check

### ✅ No Critical Circular Dependencies Found!

**Dependency Flow:**
```
Window
  ├─> StateService (via StateController)
  ├─> MovementManager (via MovementWindowPort)
  ├─> ChatOrchestrator
  └─> GifController

StateController ──signals──> Window (OK - event-driven)
MovementManager (uses Window via Protocol) (OK - interface)
GifController ──no direct calls──> Window (OK)
```

**Conclusion:** The code uses Signals and Protocols effectively!

---

## What Changed Since Original REFACTORING_PLAN?

**Original Assessment (2025-11-28):**
> "Circular Dependencies: Window ↔ Managers two-phase initialization"

**Current Reality (2025-12-01):**
- Controllers use Signals (not direct calls)
- MovementManager uses Protocol (not direct dependency)
- Much better than originally thought!

**Why the difference?**
- Previous refactoring work (before Phase 1) improved things
- Original assessment may have been pessimistic
- OR: The plan successfully guided improvements

---

## Phase 4 Revised Priority

### What Actually Needs Work?

**High Priority:**
1. ✅ **Phase 4.2: Split StateService** (809 lines → ~200 lines)
   - Extract GifManager
   - Extract TransitionCoordinator
   - This is the MAIN problem

**Medium Priority:**
2. ⚠️ **Phase 4.3: Slim Down Window** (679 lines → ~400 lines)
   - Extract MenuManager or similar
   - Consider ApplicationMediator for coordination
   - But Window is not as bad as StateService

**Low Priority:**
3. ✅ **Phase 4.1: More Signals**
   - Most communication already uses Signals
   - TransitionPlayer could use Protocol
   - But this is minor compared to size issues

---

## Recommended Phase 4 Approach

### Option A: Focus on Size (Recommended)

```
Phase 4.A: Split StateService (High Value)
  ├─> Extract GifManager
  ├─> Extract TransitionCoordinator
  └─> Result: StateService < 300 lines

Phase 4.B: Slim Window (Medium Value)
  ├─> Extract MenuManager
  ├─> Extract DialogCoordinator
  └─> Result: Window < 400 lines

Phase 4.C: Polish (Low Value)
  ├─> Convert TransitionPlayer to use Protocol
  └─> Minor signal improvements
```

**Rationale:** Size is the main problem, not coupling.

### Option B: Follow Original Plan (Conservative)

Continue with Phase 4.1 → 4.2 → 4.3 as planned.

**Rationale:** Stick to the plan, even if some steps are small.

---

## Recommendation

**Skip Phase 4.1** (already good enough) and **jump directly to Phase 4.2** (Split StateService).

**Why?**
1. StateService size (809 lines) is the real problem
2. Coupling is already well-managed (Signals + Protocols)
3. Focus effort where it matters most
4. Faster path to completion

**Alternative:**
- Do a quick audit of Phase 4.1 tasks
- Complete any trivial ones (30 min max)
- Then move to Phase 4.2

---

## Next Steps

**Immediate:**
1. User decision: Skip Phase 4.1 or quick audit?
2. If audit: Check TransitionPlayer, MovementManager signals
3. Then proceed to Phase 4.2 (main work)

**Phase 4.2 Preparation:**
1. Read StateService in detail (809 lines)
2. Identify GIF-related methods
3. Identify Transition-related methods
4. Create extraction plan
5. Write tests for extracted classes
6. Execute extraction

---

## Conclusion

The codebase is in better shape than the original refactoring plan suggested. The main issue is **class size**, not **coupling**. Focus Phase 4 on splitting large classes (StateService, Window) rather than introducing more Signals (already well-used).
