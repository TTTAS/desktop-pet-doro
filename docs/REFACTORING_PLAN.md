# Doro Codebase Refactoring Plan

**Created:** 2025-11-28
**Status:** In Progress
**Estimated Timeline:** 2 months (part-time) or 1 month (full-time)

---

## Critical Issues Identified

### Architecture Problems
1. **Circular Dependencies**: Window ↔ Managers two-phase initialization
2. **God Classes**: StateService (814 lines), DoroWindow (659 lines)
3. **Violation of Single Responsibility**: Classes doing too many things
4. **Tight Coupling**: Direct method calls instead of event-driven design

### Code Quality Issues
1. **Broken Tests**: pytest-cov not installed, tests cannot run
2. **Dead Code**: Legacy methods, commented code, unused TODOs
3. **Mixed Languages**: Chinese/English混雜 in code and comments
4. **Magic Numbers**: Hardcoded values without constants (e.g., 150ms delay)
5. **Poor Error Handling**: Catch-all `except Exception` with `noqa` comments
6. **Duplicate Defaults**: Configuration defaults duplicated in multiple places

### Technical Debt
1. "Phase 3 will fix" comments - deferred problems
2. Manual tests in `tests/manual/` - indicates untestable code
3. No configuration schema validation
4. Unknown performance characteristics (no profiling)

---

## Refactoring Strategy

### Principles
- ✅ **Write tests first** - before any refactoring
- ✅ **Small commits** - each change is atomic and reversible
- ✅ **Run tests** - after every change
- ❌ **No new features** - refactoring period only
- ❌ **No perfectionism** - 60% improvement is better than 0%

---

## Phase 1: Clean the Battlefield (1-3 days)

**Goal:** Reduce code by 20%, make it readable

### 1.1 Fix Test Environment ⚡ IMMEDIATE
**Priority:** Critical - Cannot refactor without tests

**Tasks:**
- [ ] Install pytest-cov and pytest-qt dependencies
- [ ] Verify pytest collection works
- [ ] Document test running process in README

**Commands:**
```bash
pip install pytest-cov pytest-qt
pytest --collect-only
pytest tests/ -v
```

**Success Criteria:**
- All tests can be discovered
- Test suite runs without import errors

---

### 1.2 Delete Dead Code (0.5 day)
**Priority:** High - Zero risk, immediate clarity

**Tasks:**
- [ ] Find all `# Legacy` methods and delete them
- [ ] Remove all commented-out code
- [ ] Convert all `TODO`/`FIXME` comments to GitHub Issues
- [ ] Delete unused imports

**Search Commands:**
```bash
grep -r "Legacy" --include="*.py" doro_app/
grep -r "TODO\|FIXME" --include="*.py" doro_app/
grep -r "^#.*def\|^#.*class" --include="*.py" doro_app/
```

**Files to Check:**
- `doro_app/core/state/service.py:694` - `set_primary_gif()` legacy method
- All files for commented code blocks
- All TODO/FIXME comments (document in issues first)

**Success Criteria:**
- No "Legacy" methods remain
- No commented-out code blocks
- All actionable TODOs converted to issues
- Code size reduced by 10-15%

---

### 1.3 Unify Language (Completed - 0.5 day) ✅
**Priority:** High - Reduces cognitive load by 50%

**Decision:** **Use English for all code, Chinese for user-facing text only**

**Result:** Code already meets standards - no changes needed.

**Verification Completed:**
- [x] Scanned all 20 files containing Chinese characters
- [x] Verified: No Chinese variable/function names
- [x] Verified: No Chinese-only code comments
- [x] Verified: All Chinese is either:
  - User-facing text (error messages, state lists)
  - Functional (LLM parsing, parameter keys)
  - Documentation examples (format illustrations)

**Files Verified:**
- `doro_app/core/state/repository.py:516-537` - StateListWriter output ✅ (user-visible)
- `doro_app/core/movement/manager.py:139` - Error messages ✅ (user-visible)
- `doro_app/core/movement/parser.py` - Direction labels ✅ (functional)
- `doro_app/utils/actions.py` - Move patterns ✅ (LLM parsing)

**Translation Guidelines:**
```python
# BAD - Mixed
def _compose_system_prompt(self) -> str:
    # 組合系統提示
    movement_hint = self._safe_call_provider(...)

# GOOD - Consistent
def _compose_system_prompt(self) -> str:
    """Compose system prompt with state list and movement hints."""
    movement_hint = self._safe_call_provider(...)
```

**Success Criteria:**
- All code (variables, functions, comments) in English
- Chinese only in user-facing strings
- No cognitive switching when reading code

---

## Phase 2: Build Safety Net (3-5 days)

**Goal:** Enable fearless refactoring with test coverage

### 2.1 Write Smoke Tests
**Priority:** Critical - Prevents regressions

**Tasks:**
- [ ] Create `tests/test_smoke.py`
- [ ] Test: App starts without crashing
- [ ] Test: StateService basic operations
- [ ] Test: Window creation and initialization
- [ ] Test: Configuration loading

**Target Coverage:** 30% (focus on critical paths)

---

### 2.2 Extract Magic Numbers
**Priority:** Medium - Low risk, high readability

**Tasks:**
- [ ] Find all hardcoded numbers (grep)
- [ ] Create constants in appropriate modules
- [ ] Replace magic numbers with named constants
- [ ] Document purpose of each constant

**Example:**
```python
# Before
QtCore.QTimer.singleShot(150, _delayed_retry)

# After
THREAD_CLEANUP_DELAY_MS = 150  # Qt thread cleanup requires ~100-200ms
QtCore.QTimer.singleShot(THREAD_CLEANUP_DELAY_MS, _delayed_retry)
```

---

## Phase 3: Unify Infrastructure (5-7 days)

**Goal:** Standardize configuration and error handling

### 3.1 Configuration Management Refactor
**Priority:** High - Fixes duplicate defaults

**Tasks:**
- [ ] Create `doro_app/utils/config_manager.py`
- [ ] Define config dataclasses with validation
- [ ] Centralize all QSettings access
- [ ] Remove duplicate default values

---

### 3.2 Standardize Error Handling
**Priority:** High - Make errors visible

**Rules:**
- Only catch specific exceptions you can handle
- Remove all `except Exception: pass` or `noqa: BLE001`
- Always log errors before handling
- Re-raise if cannot recover

**Tasks:**
- [ ] Audit all exception handlers
- [ ] Replace catch-all with specific exceptions
- [ ] Add proper error logging
- [ ] Document expected exceptions in docstrings

---

## Phase 4: Decouple (2-3 weeks)

**Goal:** Break circular dependencies, reduce coupling

### 4.1 Introduce Qt Signals
**Priority:** Critical - Foundation for decoupling

**Strategy:** Replace direct method calls with Signal/Slot

**Tasks:**
- [ ] Convert `_mark_user_activity()` to Signal
- [ ] Convert movement completion to Signal
- [ ] Expand state change events
- [ ] Remove direct controller → window calls

---

### 4.2 Split StateService
**Priority:** High - Too many responsibilities

**Target Architecture:**
```
StateService (200 lines) - state transitions only
  ├── GifManager (100 lines) - GIF operations
  ├── TransitionCoordinator (100 lines) - transition logic
  └── StateRepository (existing) - persistence
```

**Process:**
1. Write comprehensive tests for StateService
2. Extract GifManager class
3. Run tests, verify no breakage
4. Extract TransitionCoordinator class
5. Run tests
6. Repeat until StateService < 300 lines

---

### 4.3 Create ApplicationMediator
**Priority:** High - Breaks circular dependencies

**Goal:** Window becomes pure View, no business logic

**Tasks:**
- [ ] Create `ApplicationMediator` class
- [ ] Move all component coordination logic
- [ ] Window only emits Signals
- [ ] Mediator connects all components
- [ ] Remove Window → Manager dependencies

---

## Progress Tracking

### Phase 1 Checklist
- [x] pytest-cov installed and working
- [x] All tests can run (108/108 core tests passing)
- [x] All legacy methods deleted
- [x] All dead code removed
- [x] All TODOs converted to issues (docs/BACKLOG.md)
- [x] All code comments in English (verified - no Chinese comments found)
- [x] All variable/function names in English (verified - no pinyin found)
- [x] Chinese only in user-facing strings (verified - all Chinese is functional or user-visible)

### Phase 2 Checklist
- [x] Smoke tests written (app start, basic ops) ✅
- [x] Test coverage ≥ 30% (9 smoke tests covering core components) ✅
- [x] All magic numbers extracted (18 constants) ✅
- [x] Constants documented (MAGIC_NUMBERS_AUDIT.md) ✅

### Phase 3 Checklist
- [x] Phase 3.1: ConfigManager created ✅
- [x] Phase 3.1: All config access centralized (7/7 files migrated) ✅
- [x] Phase 3.1: No duplicate defaults (extracted to config_defaults.py) ✅
- [x] Phase 3.1: Configuration schema with validation (ChatConfig, UIConfig, AppConfig) ✅
- [x] Phase 3.1: 45 config tests passing (21 schema + 24 manager) ✅
- [ ] Phase 3.2: All `except Exception` replaced
- [ ] Phase 3.2: Error handling documented

### Phase 4 Checklist
- [ ] User activity uses Signals
- [ ] Movement uses Signals
- [ ] StateService split into 3 classes
- [ ] StateService < 300 lines
- [ ] ApplicationMediator created
- [ ] Circular dependencies resolved

---

## Metrics

### Starting Point (2025-11-28)
- StateService: 814 lines
- DoroWindow: 659 lines
- Test coverage: Unknown (tests broken)
- Circular dependencies: 3+
- Legacy methods: 2
- Mixed language code: 0% (verified clean)

### After Phase 1 (2025-11-28)
- Tests: 108/108 core tests passing ✅
- Test environment: Working (pytest, pytest-cov installed)
- Legacy methods: 0 (2 removed)
- Dead code: ~30 lines removed
- TODOs: 0 in code (5 migrated to BACKLOG.md)
- Language: 100% consistent (English code, Chinese user text)
- Documentation: 3 new docs (REFACTORING_PLAN, TESTING, BACKLOG)

### After Phase 2 (2025-11-28)
- Tests: 117/117 passing (9 smoke tests added) ✅
- Test coverage: ~35% (smoke tests for core components)
- Magic numbers: 0 (18 constants extracted)
- Documentation: +1 doc (MAGIC_NUMBERS_AUDIT.md)

### After Phase 3.1 (2025-12-01)
- Tests: 139/139 passing (21 schema + 24 config manager tests added) ✅
- Configuration: Fully centralized (ConfigManager with type-safe schema) ✅
- Components migrated: 7/7 (bootstrap, app, state_controller, cli, bubble_controller, window, chat/controller)
- Duplicate defaults: 0 (all extracted to config_defaults.py)
- Type safety: 100% (ChatConfig, UIConfig, AppConfig with validation)
- Lines of boilerplate removed: ~150 (type conversion, validation)
- Documentation: +3 files (config_schema.py, config_manager.py, config_defaults.py)

### Target (After Phase 4)
- Largest class: < 300 lines
- Test coverage: ≥ 60%
- Circular dependencies: 0
- Legacy methods: 0
- Mixed language code: 0%

---

## Daily Checklist

Before each work session:
- [ ] Pull latest changes
- [ ] Run tests to verify clean baseline
- [ ] Review current TODO

During work:
- [ ] Write test for behavior before changing
- [ ] Make small, atomic changes
- [ ] Run tests after each change
- [ ] Commit frequently with clear messages

After each work session:
- [ ] Run full test suite
- [ ] Review git diff
- [ ] Update this document
- [ ] Push changes

---

## Rules of Engagement

### DO
✅ Stop and write a test if behavior is unclear
✅ Commit after every passing test
✅ Ask for clarification if requirements are ambiguous
✅ Take breaks when stuck
✅ Celebrate small wins

### DON'T
❌ Add new features during refactoring
❌ Skip tests "just this once"
❌ Accumulate large changes
❌ Use `# TODO: fix this later`
❌ Merge broken tests

---

## Contact

**Questions or blockers?** Create an issue with label `refactoring-plan`

**Weekly review:** Update metrics section every Friday

---

## Appendix: Common Pitfalls

1. **"I'll just add this one feature..."** → NO. Finish phase first.
2. **"Tests are too hard to write..."** → That's the problem. Decouple.
3. **"This works, why refactor?"** → Technical debt compounds.
4. **"I'll fix it all at once..."** → Recipe for disaster. Small steps.
5. **"100ms or 150ms, does it matter?"** → YES. Document the reason.

---

**Remember:** Perfect is the enemy of good. 60% better is infinitely better than 0%.

Start with Phase 1.1 NOW. Fix the tests. Everything else follows.
