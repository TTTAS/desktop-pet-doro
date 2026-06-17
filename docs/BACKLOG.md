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

## Security & Privacy

### Store API key in system keyring (instead of plaintext)

**Priority:** Medium
**Category:** Security
**Location:** `doro_app/utils/config_manager.py:463` (writes `chat/api_key` to QSettings); accessors in `doro_app/core/chat/controller.py` (`get_api_key`/`set_api_key`); UI entry `doro_app/ui/helpers/chat_ui_helper.py:200` (`configure_api_key()`)

**Current Behavior:**
- API key is stored in plaintext via QSettings (Windows registry / Linux `~/.config/doro-pet/doro.conf` / macOS plist).

**Desired Behavior:**
- Store the key in the OS keychain via the `keyring` package (Credential Manager / Keychain / Secret Service).
- On first launch, migrate the existing plaintext key into keyring and clear it from QSettings.
- When the user clears the API key field in the UI, also delete the keyring entry.

**Implementation Notes:**
- Adds a `keyring` dependency.
- On Linux without a secret service (headless server / SSH / CI), fall back to the current plaintext behavior and warn.

**Dependencies:** None

---

### Log rotation and old-log cleanup

**Priority:** Low
**Category:** Maintenance / Privacy
**Location:** `doro_app/utils/logger.py:42-51` (`~/.doro/doro.log`, plain `FileHandler`, no size cap)

**Current Behavior:**
- The log file grows without bound and is never cleaned up.
- Pre-existing logs may still contain conversation snippets written before commit `0eace61`.

**Desired Behavior:**
- Use `RotatingFileHandler` with a size/backup-count cap.
- Optional: truncate or clean up the existing log on startup.

**Implementation Notes:**
- Follow the conventions in `docs/LOGGING_GUIDE.md`.

**Dependencies:** None

---

### Default log level DEBUG -> INFO

**Priority:** Low
**Category:** Maintenance
**Location:** `doro_app/utils/logger.py:12` (`setup_logger(level=logging.DEBUG)`)

**Current Behavior:**
- File handler defaults to DEBUG, producing high write volume.

**Desired Behavior:**
- Default to INFO; enable DEBUG via an environment variable / settings toggle.

**Dependencies:** None

---

## Cleanup Completed (2025-11-28)

✅ Removed legacy `set_primary_gif()` method
✅ Removed legacy `_bubble_hide_timer` reference
✅ Migrated all inline TODOs to this backlog

---

**Note:** This backlog is maintained during refactoring. For urgent bugs, create GitHub issues directly.
