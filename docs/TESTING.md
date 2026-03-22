# Testing Guide

## Running Tests

### Quick Start

```bash
# Run all core tests (recommended)
python -m pytest tests/core/ -v

# Run all tests (109 core tests)
python -m pytest tests/core/ tests/integration/ -v

# Run specific test file
python -m pytest tests/core/state/test_service.py -v

# Run tests with coverage (after re-enabling coverage in pyproject.toml)
python -m pytest tests/core/ --cov=doro_app --cov-report=term-missing
```

### Test Environment Setup

**Dependencies:**
- pytest>=7.4.0
- pytest-cov>=4.1.0
- pytest-qt>=4.2.0 (optional, for UI tests)

**Install:**
```bash
pip install -e ".[test]"
```

**Note:** UI tests (`tests/ui/`) are currently disabled due to Qt dependency issues in headless environments.

## Test Status (2026-03-22)

### Working
- ✅ 328+ 測試案例已收集，397 passing（含覆蓋率報告）
- ✅ Core state management tests
- ✅ State service, GIF operations, persistence tests
- ✅ Exception handling tests
- ✅ CoreManager tests (99% 覆蓋率)
- ✅ ChatController tests (59% 覆蓋率)
- ✅ ChatOrchestrator tests (73% 覆蓋率)
- ✅ Integration tests (state lifecycle)
- ✅ 覆蓋率報告已啟用 (pytest-cov)

### Temporarily Disabled
- ⏸️ UI tests (require Qt GUI environment)
  - `tests/ui/test_view_model.py`
  - `tests/ui/test_layout_manager.py`
  - `tests/ui/components/test_gif_player.py`

### Known Issues
1. **UI 測試需 Qt 環境**: Qt GUI tests require X server or offscreen platform
2. **總覆蓋率 43%**: 詳見 [TEST_COVERAGE_REPORT.md](TEST_COVERAGE_REPORT.md)

## CI/CD Recommendations

For automated testing in CI:

### Option 1: Xvfb (Virtual Display)
```bash
xvfb-run -a python -m pytest tests/
```

### Option 2: Qt Offscreen Platform
```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/
```

### Option 3: Skip UI Tests
```bash
python -m pytest tests/core/ tests/integration/
```

## Test Coverage Goals

| Component | Current | Target |
|-----------|---------|--------|
| Core (state, chat, movement) | ~90% | 95% |
| UI (window, controllers) | Unknown | 60% |
| Utils | ~70% | 80% |
| **Overall** | **~85%** | **≥60%** |

## Writing New Tests

### Test Structure
```python
# tests/core/state/test_feature.py
from doro_app.core.state import StateService
import pytest

class TestFeatureName:
    """Test suite for specific feature."""

    def test_basic_behavior(self, tmp_path):
        """Test basic happy path."""
        # Arrange
        service = create_test_service(tmp_path)

        # Act
        result = service.do_something()

        # Assert
        assert result is not None
```

### Fixtures
Common fixtures are defined in `tests/conftest.py`:
- `tmp_path`: Temporary directory for file operations
- `mock_config`: Mock QSettings configuration

### Best Practices
1. ✅ Use descriptive test names (test_what_when_condition)
2. ✅ One assertion per test (or closely related assertions)
3. ✅ Use fixtures for setup/teardown
4. ✅ Mock external dependencies (file I/O, network, Qt UI)
5. ❌ Don't test Qt internals
6. ❌ Don't use time.sleep() - use mocks/fixtures

## Debugging Tests

### Run single test
```bash
python -m pytest tests/core/state/test_service.py::TestStateService::test_add_state -v
```

### Show print statements
```bash
python -m pytest tests/core/ -v -s
```

### Drop into debugger on failure
```bash
python -m pytest tests/core/ -v --pdb
```

### Show locals on failure
```bash
python -m pytest tests/core/ -v -l
```

## Manual Tests

Manual tests are located in `tests/manual/` and should be run individually:

```bash
python tests/manual/test_lmstudio_response.py
python tests/manual/test_validator.py
```

**Note:** Manual tests will be converted to automated integration tests during refactoring.

---

**Last Updated:** 2026-03-22
**Test Status:** 328+ tests collected, 397 passing (with coverage) ✅
**Coverage:** 43% (2,078 / 4,880 lines)
