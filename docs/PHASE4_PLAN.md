# Phase 4: Decoupling - Detailed Execution Plan

**Created:** 2025-12-01
**Status:** Planning
**Estimated Duration:** 2-3 weeks
**Risk Level:** HIGH - Architecture changes

---

## Current State Analysis

### Problem Summary
1. **God Classes:** StateService (809 lines), DoroWindow (679 lines)
2. **Circular Dependencies:** Window ↔ Controllers (two-phase initialization)
3. **Tight Coupling:** Direct method calls instead of events
4. **Mixed Responsibilities:** Classes doing too many things

### Architectural Issues

#### StateService (809 lines) - Too Many Responsibilities
- State transitions (core responsibility) ✓
- GIF operations (should be separate)
- Transition coordination (should be separate)
- Event emission (acceptable)
- State persistence via Repository (acceptable delegation)

#### DoroWindow (679 lines) - Too Many Responsibilities
- Qt window management (core responsibility) ✓
- Component coordination (should be in Mediator)
- Direct calls to managers (should use Signals)
- Business logic (should be in controllers)

#### Current Coupling Problems
```
Window ────calls───> StateController
       ────calls───> GifController
       ────calls───> MovementManager
       ────calls───> ChatOrchestrator

StateController ──calls──> Window (mark_user_activity)
GifController ────calls──> Window (update UI)
MovementManager ──calls──> Window (get position)
```

**Problem:** Everyone calls Window, Window calls everyone → Circular hell

---

## Phase 4 Strategy: Bottom-Up Approach

### Why Bottom-Up?
- **Safer:** Start with isolated components
- **Incremental:** Each step can be tested
- **Reversible:** Easy to roll back if issues arise
- **Visible progress:** See improvements after each sub-phase

### Three-Phase Approach

```
Phase 4.1: Introduce Signals (1 week)
  ↓
Phase 4.2: Extract Components from StateService (1 week)
  ↓
Phase 4.3: Create ApplicationMediator (3-5 days)
```

---

## Phase 4.1: Introduce Qt Signals (Week 1)

### Goal
Replace direct method calls with Signal/Slot pattern.

### Why Signals First?
- Foundation for decoupling
- Can be done incrementally
- Easy to test (signals can be intercepted)
- No architectural changes yet

### Tasks

#### 4.1.1: User Activity Signal (Day 1)
**Current:** Controllers call `window._mark_user_activity()` directly
**Target:** Emit signal, window listens

```python
# In StateController
class StateController(QtCore.QObject):
    user_activity_detected = QtCore.Signal()  # NEW

    def _on_state_changed(self, event):
        self.user_activity_detected.emit()  # Instead of window call

# In Window.__init__
state_controller.user_activity_detected.connect(self._mark_user_activity)
```

**Files to change:**
- state_controller.py (add signal, emit instead of call)
- window.py (connect signal)

**Tests:** Verify state changes still mark user activity

---

#### 4.1.2: Movement Completion Signal (Day 2)
**Current:** MovementManager calls window methods directly
**Target:** Emit signals

```python
# In MovementManager
class MovementManager(QtCore.QObject):
    movement_completed = QtCore.Signal(str)  # movement_id

# In Window
movement_manager.movement_completed.connect(self._on_movement_done)
```

**Files to change:**
- movement/manager.py
- window.py

---

#### 4.1.3: Expand State Change Events (Day 3)
**Current:** StateService emits minimal events
**Target:** Rich events for all state operations

```python
# New events to add:
class StateService:
    state_transition_started = Signal(str, str)  # from_state, to_state
    state_transition_failed = Signal(str, str)   # target_state, reason
    gif_loaded = Signal(str)                      # state_key
    gif_load_failed = Signal(str, str)            # state_key, reason
```

**Files to change:**
- state/service.py (add signals, emit at right places)
- window.py (connect to new signals)
- gif_controller.py (listen instead of polling)

---

#### 4.1.4: Remove Direct Controller → Window Calls (Day 4-5)
**Audit:** Find all places controllers call window
**Replace:** Use signals for all communication

```bash
# Find all direct window calls
grep -rn "self\._window\." doro_app/ui/controllers/
grep -rn "window\." doro_app/core/ --include="*.py"
```

**Expected findings:**
- StateController → Window (user activity)
- GifController → Window (UI updates)
- BubbleController → Window (geometry)

---

### Phase 4.1 Success Criteria
- [ ] Zero direct calls from controllers to window
- [ ] All communication via Signals/Slots
- [ ] All 139 tests still passing
- [ ] Manual test: App works normally

---

## Phase 4.2: Split StateService (Week 2)

### Goal
Break StateService (809 lines) into focused classes.

### Target Architecture
```
StateService (200 lines)
  └─> Focuses on: State transitions, events, coordination

GifManager (100 lines)
  └─> Focuses on: GIF loading, caching, file operations

TransitionCoordinator (100 lines)
  └─> Focuses on: Transition logic, timing, validation

StateRepository (existing)
  └─> Already exists: Persistence
```

### Why This Order?
1. **GifManager first:** Most isolated, easiest to extract
2. **TransitionCoordinator second:** Depends on GifManager
3. **StateService last:** Becomes thin coordinator

---

### 4.2.1: Extract GifManager (Day 1-2)

**What to move:**
- `set_primary_gif()`
- `set_secondary_gif()`
- `get_primary_gif_path()`
- `get_secondary_gif_path()`
- GIF caching logic
- File validation

**New file:** `doro_app/core/state/gif_manager.py`

```python
class GifManager:
    """Manages GIF loading, caching, and validation."""

    gif_loaded = QtCore.Signal(str, Path)  # state_key, path
    gif_failed = QtCore.Signal(str, str)   # state_key, error

    def load_primary_gif(self, state_key: str) -> Path | None:
        """Load and cache primary GIF for state."""

    def load_secondary_gif(self, state_key: str) -> Path | None:
        """Load and cache secondary GIF for state."""
```

**Process:**
1. Write GifManager class with tests
2. Make StateService use GifManager internally
3. Run all tests
4. Remove old methods from StateService
5. Run all tests again

---

### 4.2.2: Extract TransitionCoordinator (Day 3-4)

**What to move:**
- Transition validation logic
- Transition GIF selection
- Transition timing rules
- State history tracking

**New file:** `doro_app/core/state/transition_coordinator.py`

```python
class TransitionCoordinator:
    """Coordinates state transitions and transition animations."""

    transition_available = QtCore.Signal(str, str, Path)  # from, to, gif
    transition_required = QtCore.Signal(str, str)          # from, to

    def find_transition(self, from_state: str, to_state: str) -> Path | None:
        """Find transition GIF for state change."""
```

---

### 4.2.3: Slim Down StateService (Day 5)

**What remains in StateService:**
- State change coordination
- Event emission
- Delegating to GifManager
- Delegating to TransitionCoordinator
- Delegating to StateRepository

**Target:** ~200 lines

---

### Phase 4.2 Success Criteria
- [ ] StateService < 300 lines
- [ ] GifManager handles all GIF operations
- [ ] TransitionCoordinator handles transition logic
- [ ] All 139 tests passing
- [ ] Each class has single responsibility

---

## Phase 4.3: Create ApplicationMediator (Days 11-15)

### Goal
Break Window ↔ Controller circular dependencies.

### Target Architecture
```
ApplicationMediator (central coordinator)
  ├─> Creates all controllers
  ├─> Connects all signals
  ├─> No business logic
  └─> Pure coordination

DoroWindow (pure view)
  ├─> Only Qt UI code
  ├─> Emits signals for user actions
  ├─> Never calls controllers directly
  └─> ~300 lines
```

---

### 4.3.1: Create ApplicationMediator Skeleton (Day 1)

```python
# doro_app/mediator.py

class ApplicationMediator(QtCore.QObject):
    """
    Central coordinator for application components.

    Responsibilities:
    - Create all controllers and managers
    - Connect all Signal/Slot relationships
    - Coordinate cross-component workflows

    NOT responsible for:
    - Business logic (in controllers)
    - UI rendering (in window)
    - State management (in StateService)
    """

    def __init__(self, window: DoroWindow, state_service: StateService, ...):
        self._window = window
        self._state_service = state_service
        # ... other components

        self._connect_signals()

    def _connect_signals(self):
        """Connect all component signals."""
        # State changes -> Window updates
        self._state_service.state_changed.connect(self._window.on_state_changed)

        # User actions -> Controllers
        self._window.user_clicked.connect(self._handle_user_click)

        # ... etc
```

---

### 4.3.2: Move Component Creation (Day 2-3)

**Current:** App creates components, passes to Window
**Target:** Mediator creates and owns components

```python
# Before (in app.py)
self._state_controller = StateController(...)
self.window.wire_dependencies(state_controller=self._state_controller, ...)

# After (in mediator.py)
self._state_controller = StateController(...)
# Wire internally, window doesn't know about controllers
```

---

### 4.3.3: Extract Window Business Logic (Day 4-5)

**Move to Mediator:**
- Click action handling
- Menu action coordination
- Cross-component workflows

**Keep in Window:**
- Pure UI code
- Qt event handling
- Visual updates

**Target:** Window < 400 lines

---

### Phase 4.3 Success Criteria
- [ ] ApplicationMediator created
- [ ] Zero circular dependencies
- [ ] Window is pure view (~300-400 lines)
- [ ] All coordination in Mediator
- [ ] All 139 tests passing
- [ ] Dependency graph is a DAG (Directed Acyclic Graph)

---

## Risk Mitigation

### High-Risk Areas
1. **Qt Signal connections:** Easy to miss a connection
2. **Two-phase initialization:** Complex bootstrapping
3. **Test coverage gaps:** Some scenarios not tested

### Mitigation Strategies
1. **Small commits:** Each change is atomic
2. **Run tests constantly:** After every file change
3. **Manual testing:** Test app after each phase
4. **Feature flags:** Can disable changes if needed
5. **Git branches:** Easy rollback if disaster

---

## Testing Strategy

### For Each Sub-Phase
1. **Unit tests:** Test new classes in isolation
2. **Integration tests:** Test signal connections
3. **Smoke tests:** App still starts and runs
4. **Manual testing:** Click through common workflows

### Critical Workflows to Test
- [ ] State changes (idle → happy → idle)
- [ ] Movement execution
- [ ] Chat requests
- [ ] Window dragging
- [ ] Bubble position saving
- [ ] App shutdown and restart

---

## Commit Strategy

### Commit After Each:
- New Signal added
- New class extracted
- Old code removed
- Tests updated

### Commit Message Format
```
Phase 4.X.Y: [Short description]

What changed:
- [Specific change 1]
- [Specific change 2]

Why:
- [Reason for change]

Tests: X/X passing ✅
Manual test: [Result]
```

---

## Rollback Plan

### If Things Go Wrong
1. **Identify:** Which commit broke it?
2. **Isolate:** Can we fix forward, or must we revert?
3. **Revert:** `git revert <commit>` (preserves history)
4. **Document:** What went wrong, lessons learned

### When to Rollback
- Tests fail and can't be fixed in 30 minutes
- App becomes unstable
- Circular dependencies worsen instead of improve

---

## Progress Tracking

### Phase 4.1: Introduce Signals
- [ ] 4.1.1: User Activity Signal
- [ ] 4.1.2: Movement Completion Signal
- [ ] 4.1.3: Expand State Change Events
- [ ] 4.1.4: Remove Direct Controller → Window Calls

### Phase 4.2: Split StateService
- [ ] 4.2.1: Extract GifManager
- [ ] 4.2.2: Extract TransitionCoordinator
- [ ] 4.2.3: Slim Down StateService

### Phase 4.3: Create ApplicationMediator
- [ ] 4.3.1: Create Mediator Skeleton
- [ ] 4.3.2: Move Component Creation
- [ ] 4.3.3: Extract Window Business Logic

---

## Success Metrics

### Code Metrics
- StateService: 809 → ~200 lines (75% reduction)
- DoroWindow: 679 → ~300 lines (56% reduction)
- Circular dependencies: ~3 → 0
- Direct method calls: Many → 0 (all via Signals)

### Quality Metrics
- Test coverage: Maintained at ~35%
- All tests passing: 139/139
- No regressions: Manual testing confirms

### Architecture Metrics
- Single Responsibility: Each class does one thing
- Dependency Direction: One-way only (no cycles)
- Coupling: Loose (via Signals)
- Cohesion: High (related code together)

---

## Timeline

### Week 1: Signals
- Day 1: User Activity Signal
- Day 2: Movement Completion Signal
- Day 3: Expand State Events
- Day 4-5: Remove Direct Calls
- **Milestone:** Zero direct controller → window calls

### Week 2: StateService Split
- Day 1-2: Extract GifManager
- Day 3-4: Extract TransitionCoordinator
- Day 5: Slim Down StateService
- **Milestone:** StateService < 300 lines

### Week 3: Mediator
- Day 1: Mediator Skeleton
- Day 2-3: Move Component Creation
- Day 4-5: Extract Window Logic
- **Milestone:** Zero circular dependencies

---

## Next Steps

1. Read current StateController code
2. Find all `window._mark_user_activity()` calls
3. Add `user_activity_detected` Signal
4. Replace calls with signal emission
5. Test thoroughly
6. Commit

**Ready to start Phase 4.1.1?**
