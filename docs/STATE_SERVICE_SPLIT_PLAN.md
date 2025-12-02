# StateService Split Plan - Phase 4.2

**Created:** 2025-12-01
**Goal:** Reduce StateService from 809 lines to ~200 lines
**Method:** Extract GifManager and TransitionCoordinator

---

## Current Structure (809 lines)

```
StateService (809 lines)
├── GIF Operations (10 methods, ~60 lines)
├── State Queries (15 methods, ~60 lines)
├── Transition Queries (3 methods, ~20 lines)
├── Update Operations (5 methods, ~50 lines)
├── Initialization (2 methods, ~80 lines)
├── State Changes (1 method, ~35 lines)
├── Transition Locking (3 methods, ~50 lines)
├── State Parsing (1 method, ~80 lines)
├── State CRUD (4 methods, ~200 lines)
├── GIF Management (2 methods, ~40 lines)
└── Move State Management (8 methods, ~200 lines)
```

---

## Target Structure (~200 lines)

```
StateService (~200 lines)
├── Core state operations
├── Event coordination
└── Delegates to:
    ├── GifManager (~100 lines)
    ├── TransitionCoordinator (~100 lines)
    ├── StateRepository (exists)
    ├── MoveStateRepository (exists)
    └── GifRepository (exists)
```

---

## Phase 4.2.1: Extract GifManager

### What to Extract

**From StateService, move to GifManager:**

1. `get_gif_path(state_key)` - Get GIF path for state
2. `get_gif_path_by_id(gif_id)` - Get GIF path by ID
3. `store_gif(source_path, state_key)` - Store new GIF
4. `delete_gif(gif_id)` - Delete GIF
5. `set_gif(state_key, gif_path)` - Set GIF for state
6. `get_gif_id(state_key)` - Get GIF ID for state

**Also move:**
- `_gif_repo` reference
- GIF-related initialization logic

**Total extracted:** ~100 lines

---

### GifManager API Design

```python
# doro_app/core/state/gif_manager.py

class GifManager:
    """
    Manages GIF resources for states.

    Responsibilities:
    - Store and retrieve GIF files
    - Associate GIFs with states
    - Provide GIF paths for rendering

    Does NOT:
    - Know about Qt or UI
    - Manage state lifecycle
    - Emit events (StateService does that)
    """

    def __init__(self, gif_repo: GifRepository):
        self._gif_repo = gif_repo

    def get_path(self, state_key: str, states: StateCollection) -> Optional[Path]:
        """Get GIF path for a state."""

    def get_path_by_id(self, gif_id: str) -> Optional[Path]:
        """Get GIF path by resource ID."""

    def store(self, source_path: Path) -> Optional[str]:
        """Store a GIF file, return resource ID."""

    def delete(self, gif_id: str) -> bool:
        """Delete a GIF resource."""

    def assign_to_state(self, state: State, gif_path: Path) -> Optional[str]:
        """Store GIF and assign to state, return new GIF ID."""

    def get_state_gif_id(self, state: State) -> Optional[str]:
        """Get GIF ID from state."""
```

**Key Design Decisions:**
- GifManager doesn't store state references (StateService manages states)
- GifManager accepts StateCollection as parameter (dependency injection)
- Pure functions where possible (easier to test)

---

### StateService Changes (Phase 4.2.1)

**Add:**
```python
def __init__(self, ...):
    # ... existing code
    self._gif_manager = GifManager(gif_repo)
```

**Replace:**
```python
# Before
def get_gif_path(self, state_key: str) -> Optional[Path]:
    state = self._states.get(state_key)
    if not state or not state.gif_id:
        return None
    return self._gif_repo.get_path(state.gif_id)

# After
def get_gif_path(self, state_key: str) -> Optional[Path]:
    return self._gif_manager.get_path(state_key, self._states)
```

**Expected Reduction:** ~60 lines

---

## Phase 4.2.2: Extract TransitionCoordinator

### What to Extract

**From StateService, move to TransitionCoordinator:**

1. `find_transition(from_state, to_state)` - Find transition GIF
2. `begin_transition()` - Lock state changes
3. `end_transition()` - Unlock state changes
4. `is_transitioning()` - Check transition status
5. `get_transition(key)` - Get transition by key
6. `all_transition_keys()` - List all transitions

**Also move:**
- `_is_transitioning` flag
- `_transition_repo` reference
- `_transitions` collection

**Total extracted:** ~100 lines

---

### TransitionCoordinator API Design

```python
# doro_app/core/state/transition_coordinator.py

class TransitionCoordinator:
    """
    Coordinates state transitions and animations.

    Responsibilities:
    - Find appropriate transition animations
    - Manage transition lock (prevent concurrent state changes)
    - Track transition state

    Does NOT:
    - Play animations (TransitionPlayer does that)
    - Change states (StateService does that)
    - Know about Qt or UI
    """

    def __init__(self, transition_repo: Optional[TransitionStateRepository]):
        self._transition_repo = transition_repo
        self._transitions = TransitionStateCollection()
        self._is_transitioning = False

    def find(self, from_state: str, to_state: str) -> Optional[TransitionState]:
        """Find transition for state change."""

    def begin(self) -> bool:
        """Begin transition, lock state changes."""

    def end(self) -> bool:
        """End transition, unlock state changes."""

    def is_active(self) -> bool:
        """Check if transition is in progress."""

    def get(self, key: str) -> Optional[TransitionState]:
        """Get transition by key."""

    def all_keys(self) -> list[str]:
        """List all transition keys."""

    def load_from_repo(self) -> None:
        """Load transitions from repository."""
```

**Key Design Decisions:**
- TransitionCoordinator owns the transition lock
- Pure state management (no UI knowledge)
- Can be tested independently

---

### StateService Changes (Phase 4.2.2)

**Add:**
```python
def __init__(self, ...):
    # ... existing code
    self._transition_coordinator = TransitionCoordinator(transition_repo)
```

**Replace:**
```python
# Before
def find_transition(self, from_state: str, to_state: str) -> Optional[TransitionState]:
    return self._transitions.find_match(from_state, to_state)

# After
def find_transition(self, from_state: str, to_state: str) -> Optional[TransitionState]:
    return self._transition_coordinator.find(from_state, to_state)
```

**Expected Reduction:** ~70 lines

---

## Phase 4.2.3: Slim Down StateService

### What Remains (~200 lines)

**StateService keeps:**
1. State CRUD operations (add/remove/update states)
2. Move state management (delegates to MoveStateRepository)
3. State change coordination (set_state)
4. Event emission (callbacks)
5. State queries (get_state, visible_state_keys, etc.)
6. Initialization (delegates to managers)
7. State parsing (parse_state_from_action)
8. State persistence (delegates to repositories)

**StateService becomes a coordinator:**
```python
class StateService:
    """
    Coordinates state operations and delegates to specialized managers.

    Manages:
    - State lifecycle (add/remove/update)
    - State changes and events
    - Coordination between GifManager, TransitionCoordinator, and Repositories

    Delegates:
    - GIF operations → GifManager
    - Transitions → TransitionCoordinator
    - Persistence → Repositories
    """
```

---

## Implementation Steps

### Step 1: Create GifManager (2-3 hours)

1. Create `doro_app/core/state/gif_manager.py`
2. Write GifManager class with all methods
3. Write tests for GifManager (20 tests)
4. Ensure all tests pass in isolation

**Tests to write:**
- `test_get_path_with_valid_state`
- `test_get_path_with_no_gif`
- `test_store_gif_success`
- `test_store_gif_failure`
- `test_delete_gif_success`
- `test_assign_to_state`
- etc.

---

### Step 2: Integrate GifManager into StateService (1-2 hours)

1. Add GifManager to StateService.__init__
2. Replace GIF method implementations with delegation
3. Remove old GIF code
4. Run full test suite (139 tests must pass)
5. Manual test: Verify GIF loading works

**Verify:**
- All 139 tests pass
- App starts normally
- State GIFs load correctly

---

### Step 3: Create TransitionCoordinator (2-3 hours)

1. Create `doro_app/core/state/transition_coordinator.py`
2. Write TransitionCoordinator class
3. Write tests for TransitionCoordinator (15 tests)
4. Ensure all tests pass in isolation

**Tests to write:**
- `test_find_transition_exists`
- `test_find_transition_not_found`
- `test_begin_transition_locks`
- `test_end_transition_unlocks`
- `test_cannot_double_lock`
- etc.

---

### Step 4: Integrate TransitionCoordinator (1-2 hours)

1. Add TransitionCoordinator to StateService.__init__
2. Replace transition method implementations
3. Remove old transition code
4. Run full test suite (139 tests must pass)
5. Manual test: Verify transitions work

**Verify:**
- All 139 tests pass
- App starts normally
- State transitions work (with animations)

---

### Step 5: Final Cleanup & Verification (1 hour)

1. Verify StateService is < 300 lines (target: ~200)
2. Verify no functionality broken
3. Update documentation
4. Create final commit

**Success Criteria:**
- StateService: 809 → ~200 lines (75% reduction)
- All tests passing (139/139)
- App fully functional
- Code more maintainable

---

## Testing Strategy

### Unit Tests (New)

**GifManager tests (20 tests):**
- GIF storage and retrieval
- Path resolution
- Error handling
- Edge cases (missing files, invalid paths)

**TransitionCoordinator tests (15 tests):**
- Transition finding
- Lock/unlock mechanics
- Concurrent transition prevention
- Edge cases

**Total new tests:** ~35

---

### Integration Tests (Existing)

**StateService tests (existing ~50 tests):**
- Should all continue to pass
- No changes needed (public API unchanged)

**State lifecycle tests:**
- State changes
- GIF loading
- Transitions

---

### Manual Testing

**Critical workflows:**
1. App startup (loads default state with GIF)
2. State change (idle → happy → idle)
3. Transition animation (state → transition GIF → state)
4. GIF assignment (right-click → set GIF)
5. State creation (add new state)

---

## Risk Mitigation

### Risks

1. **Breaking existing functionality**
   - Mitigation: Public API unchanged, tests verify behavior

2. **Test failures**
   - Mitigation: Small commits, run tests after each change

3. **Missed edge cases**
   - Mitigation: Comprehensive unit tests for new classes

4. **Integration issues**
   - Mitigation: Manual testing after each phase

---

## Commit Strategy

**Commit after each:**

1. ✅ GifManager class created + tests
2. ✅ GifManager integrated into StateService
3. ✅ TransitionCoordinator class created + tests
4. ✅ TransitionCoordinator integrated into StateService
5. ✅ Final cleanup

**Commit message format:**
```
Phase 4.2.X: [Action]

What:
- [Changes made]

Why:
- [Reason]

Tests: X/X passing
Lines: StateService 809 → X lines
```

---

## Timeline

**Estimated: 1 week (8-12 hours total)**

| Phase | Task | Time | Tests |
|-------|------|------|-------|
| 4.2.1a | Create GifManager | 2-3h | 20 new |
| 4.2.1b | Integrate GifManager | 1-2h | 139 pass |
| 4.2.2a | Create TransitionCoordinator | 2-3h | 15 new |
| 4.2.2b | Integrate TransitionCoordinator | 1-2h | 139 pass |
| 4.2.3 | Final cleanup | 1h | 174 pass |

**Total:** 8-12 hours, 35 new tests

---

## Success Metrics

### Code Metrics
- StateService: 809 → ~200 lines (75% reduction) ✅
- New classes: GifManager (~100 lines), TransitionCoordinator (~100 lines)
- Total lines: Similar (refactor, not reduction of total code)

### Quality Metrics
- Tests: 139 → 174 (35 new tests)
- All tests passing
- No regressions in manual testing

### Architecture Metrics
- Single Responsibility: Each class has one focus ✅
- Testability: Managers can be tested in isolation ✅
- Maintainability: Smaller, focused classes ✅

---

## Next Step

Begin Phase 4.2.1a: Create GifManager class with tests

**Ready to proceed?**
