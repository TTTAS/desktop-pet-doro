# Development Backlog

**Created:** 2025-11-28 (migrated from inline TODOs)

This document tracks feature requests and known gaps extracted from code comments during refactoring.

---

## UI Testing

### Test Coverage Needed for Dialogs

**Priority:** Medium
**Category:** Testing

Missing test coverage for UI dialogs:

1. **MoveStateManagerDialog** (`tests/ui/dialogs/move_state/test_manager_dialog.py`)
   - Test dialog initialization
   - Test movement and transition display
   - Test add/edit/remove operations
   - Test GIF preview for both types
   - Test QMovie cleanup on close

2. **AddStateDialog** (`tests/ui/dialogs/state/test_add_dialog.py`)
   - Test dialog initialization
   - Test state creation flow
   - Test input validation
   - Test GIF selection

3. **StateManagerDialog** (`tests/ui/dialogs/state/test_manager_dialog.py`)
   - Test state list display
   - Test add/remove operations
   - Test state selection
   - Test GIF preview

4. **EditMoveStateDialog** (`tests/ui/dialogs/move_state/test_edit_dialog.py`)
   - Test editing movement states
   - Test direction configuration
   - Test distance/speed parameters

**Blocker:** Qt UI testing requires X server or offscreen platform (see `docs/TESTING.md`)

**Next Steps:**
1. Set up Qt offscreen testing environment
2. Create test fixtures for dialog testing
3. Implement basic smoke tests
4. Add comprehensive interaction tests

---

## Features

### Edit State Dialog

**Priority:** Low
**Category:** Feature
**Location:** `doro_app/ui/dialogs/state/manager_dialog.py:218`

**Current Behavior:**
- "Edit" button shows placeholder message
- No actual edit functionality

**Desired Behavior:**
- Open edit dialog when user clicks "Edit"
- Allow modifying state properties:
  - Label
  - Visual configuration
  - GIF selection
- Save changes to StateService

**Implementation Notes:**
- Similar to AddStateDialog but pre-populated
- Need to handle state update events
- Consider impact on current state if editing active state

**Dependencies:**
- None (can be implemented independently)

---

## Refactoring Opportunities

### Extract Dialog Test Utilities

**Priority:** Low
**Category:** Refactoring

Once dialog tests are implemented, extract common test utilities:
- Dialog fixture creation
- Mock event handling
- QMovie cleanup verification
- State service mocking patterns

---

## Cleanup Completed (2025-11-28)

✅ Removed legacy `set_primary_gif()` method
✅ Removed legacy `_bubble_hide_timer` reference
✅ Migrated all inline TODOs to this backlog

---

**Note:** This backlog is maintained during refactoring. For urgent bugs, create GitHub issues directly.
