# Configuration Usage Audit

**Generated:** 2025-11-28
**Updated:** 2025-12-01
**Purpose:** Phase 3.1 - Configuration Management Refactor
**Status:** ✅ **COMPLETED**

---

## ✅ Phase 3.1 Completion Summary

**Completed:** 2025-12-01

### What Was Delivered:
1. ✅ **ConfigManager created** - Centralized, type-safe configuration management
2. ✅ **Configuration schema** - ChatConfig, UIConfig, AppConfig with validation
3. ✅ **All defaults extracted** - Single source of truth in config_defaults.py
4. ✅ **All 7 files migrated** - 100% migration complete
5. ✅ **45 tests added** - 21 schema + 24 manager tests, all passing

### Migration Results:
- **Components migrated:** 7/7 (100%)
  - ✅ bootstrap.py - Creates ConfigManager
  - ✅ app.py - Passes ConfigManager to components
  - ✅ state_controller.py - App state persistence
  - ✅ cli.py - Chat test configuration
  - ✅ bubble_controller.py - UI preferences (fixed encapsulation)
  - ✅ window.py - Bubble configuration
  - ✅ chat/controller.py - Chat settings
- **Duplicate defaults:** 0 (was 3)
- **Type safety:** 100%
- **Tests:** 139/139 passing
- **Boilerplate removed:** ~150 lines (type conversion, validation)

### Benefits Achieved:
✅ Type safety (IDE autocomplete, type checking)
✅ Single source of truth (no duplicate defaults)
✅ Validation (invalid values caught early)
✅ Testability (easy to mock ConfigManager)
✅ Discoverability (config.chat.* shows all options)
✅ Reduced errors (no typos in config keys)

---

## Original Audit (2025-11-28)

### Summary

- **Total config operations:** 27 across 7 files
- **Configuration keys:** 12 distinct keys
- **Duplicate defaults:** ⚠️ 3 found (chat timeout, temperature, endpoint)
- **QSettings instances:** Multiple (not centralized)

---

## Configuration Keys

### Chat Configuration (8 keys)

| Key | Default | Files Using It | Duplicate? |
|-----|---------|----------------|------------|
| `chat/server_url` | `DEFAULT_CHAT_SERVER_URL` | cli.py, controller.py | ✅ |
| `chat/model` | `"lmstudio"` | cli.py, controller.py | ✅ |
| `chat/endpoint_path` | `"/v1/chat/completions"` | cli.py, controller.py | ✅ |
| `chat/timeout_seconds` | `30` vs `CHAT_DEFAULT_TIMEOUT_SECONDS` | cli.py, controller.py | ⚠️ **DUPLICATE** |
| `chat/temperature` | `0.7` vs `CHAT_DEFAULT_TEMPERATURE` | cli.py, controller.py | ⚠️ **DUPLICATE** |
| `chat/max_tokens` | `CHAT_DEFAULT_MAX_TOKENS` | controller.py | ✅ |
| `chat/history_turns` | `CHAT_DEFAULT_HISTORY_TURNS` | controller.py | ✅ |
| `chat/max_retries` | `2` | controller.py | ⚠️ Not a constant |

### UI Configuration (3 keys)

| Key | Default | Files Using It | Duplicate? |
|-----|---------|----------------|------------|
| `ui/bubble_offset_x` | `BUBBLE_DEFAULT_OFFSET_X` | window.py, bubble_controller.py | ✅ |
| `ui/bubble_offset_y` | `BUBBLE_DEFAULT_OFFSET_Y` | window.py, bubble_controller.py | ✅ |
| `ui/bubble_scale` | `BUBBLE_DEFAULT_SCALE` | window.py, bubble_controller.py | ✅ |

### Application State (1 key)

| Key | Default | Files Using It | Duplicate? |
|-----|---------|----------------|------------|
| `current_state` | `"idle"` | app.py, state_controller.py | ✅ |

---

## Issues Found

### 🔴 Critical: Duplicate Default Values

**Problem:** Same defaults defined in multiple places

**cli.py:32-33:**
```python
timeout_value = settings.value("chat/timeout_seconds", 30)  # Hardcoded
temp_value = settings.value("chat/temperature", 0.7)       # Hardcoded
```

**controller.py:76-77:**
```python
timeout_value = config.value("chat/timeout_seconds", CHAT_DEFAULT_TIMEOUT_SECONDS)  # Constant
self._temperature = _safe_float(
    config.value("chat/temperature", CHAT_DEFAULT_TEMPERATURE),  # Constant
    CHAT_DEFAULT_TEMPERATURE,
)
```

**Risk:** If defaults change, must update in multiple places

---

### 🟡 Medium: Hardcoded Defaults

**controller.py:63:**
```python
self._max_retries = _safe_int(config.value("chat/max_retries", 2), 2)
```

**Should be:**
```python
CHAT_DEFAULT_MAX_RETRIES = 2
self._max_retries = _safe_int(
    config.value("chat/max_retries", CHAT_DEFAULT_MAX_RETRIES),
    CHAT_DEFAULT_MAX_RETRIES
)
```

---

### 🟡 Medium: Direct Config Access

**Problem:** Multiple components directly access `_config` object

**Files with direct access:**
- `app.py` - `self._config.value(...)`
- `window.py` - `self._config.value(...)`, `self._config.sync()`
- `controller.py` - `self._config.value(...)`, `self._config.setValue(...)`
- `bubble_controller.py` - `window._config.setValue(...)` ⚠️ Accessing another object's config!
- `state_controller.py` - `self._config.setValue(...)`

**Issue:** No validation, no type safety, scattered access

---

## Configuration Access Patterns

### Read Operations (15 occurrences)

| File | Line | Key | Pattern |
|------|------|-----|---------|
| cli.py | 29 | chat/server_url | `settings.value(key, default, str)` |
| cli.py | 30 | chat/model | `settings.value(key, default, str)` |
| cli.py | 31 | chat/endpoint_path | `settings.value(key, default, str)` |
| cli.py | 32 | chat/timeout_seconds | `settings.value(key, default)` |
| cli.py | 33 | chat/temperature | `settings.value(key, default)` |
| app.py | 123 | current_state | `_config.value(key, default)` |
| window.py | 308 | ui/bubble_offset_x | `_safe_float(_config.value(...))` |
| window.py | 309 | ui/bubble_offset_y | `_safe_float(_config.value(...))` |
| window.py | 310 | ui/bubble_scale | `_safe_float(_config.value(...))` |
| controller.py | 63 | chat/max_retries | `_safe_int(config.value(...))` |
| controller.py | 68 | chat/history_turns | `_safe_int(config.value(...))` |
| controller.py | 72 | chat/server_url | `config.value(key, default, str)` |
| controller.py | 73 | chat/model | `config.value(key, default, str)` |
| controller.py | 74 | chat/endpoint_path | `config.value(key, default, str)` |
| controller.py | 76 | chat/timeout_seconds | `config.value(key, default)` |

### Write Operations (9 occurrences)

| File | Line | Key | Pattern |
|------|------|-----|---------|
| controller.py | 415 | chat/server_url | `_config.setValue(key, value)` |
| controller.py | 416 | chat/model | `_config.setValue(key, value)` |
| controller.py | 417 | chat/endpoint_path | `_config.setValue(key, value)` |
| controller.py | 418 | chat/temperature | `_config.setValue(key, float(value))` |
| controller.py | 419 | chat/timeout_seconds | `_config.setValue(key, int(value))` |
| bubble_controller.py | 113 | ui/bubble_offset_x | `window._config.setValue(...)` ⚠️ |
| bubble_controller.py | 114 | ui/bubble_offset_y | `window._config.setValue(...)` ⚠️ |
| bubble_controller.py | 115 | ui/bubble_scale | `window._config.setValue(...)` ⚠️ |
| state_controller.py | 94 | current_state | `_config.setValue(key, value)` |

### Sync Operations (3 occurrences)

| File | Line | Pattern |
|------|------|---------|
| window.py | 660 | `_config.sync()` |
| controller.py | 421 | `_config.sync()` |
| bubble_controller.py | 116 | `window._config.sync()` ⚠️ |

---

## Recommended Actions

### Phase 3.1.1: Extract All Defaults to Constants ✅ Partial

**Status:** Some defaults already extracted (CHAT_DEFAULT_*), others hardcoded

**TODO:**
- [ ] Extract `chat/max_retries` default to constant
- [ ] Ensure cli.py uses constants instead of hardcoded values
- [ ] Verify all defaults match between files

---

### Phase 3.1.2: Create Configuration Schema

**Goal:** Type-safe configuration with validation

**Proposed Structure:**
```python
# doro_app/utils/config_schema.py

from dataclasses import dataclass
from pathlib import Path

@dataclass
class ChatConfig:
    """Chat/LLM configuration."""
    server_url: str = DEFAULT_CHAT_SERVER_URL
    model: str = "lmstudio"
    endpoint_path: str = "/v1/chat/completions"
    timeout_seconds: int = CHAT_DEFAULT_TIMEOUT_SECONDS
    temperature: float = CHAT_DEFAULT_TEMPERATURE
    max_tokens: int = CHAT_DEFAULT_MAX_TOKENS
    history_turns: int = CHAT_DEFAULT_HISTORY_TURNS
    max_retries: int = 2

@dataclass
class UIConfig:
    """UI appearance configuration."""
    bubble_offset_x: float = BUBBLE_DEFAULT_OFFSET_X
    bubble_offset_y: float = BUBBLE_DEFAULT_OFFSET_Y
    bubble_scale: float = BUBBLE_DEFAULT_SCALE

@dataclass
class AppConfig:
    """Application-level configuration."""
    current_state: str = "idle"
```

---

### Phase 3.1.3: Create ConfigManager

**Goal:** Centralized, type-safe config access

**Proposed API:**
```python
# doro_app/utils/config_manager.py

class ConfigManager:
    """Centralized configuration management with validation."""

    def __init__(self, settings_path: Path):
        self._settings = QtCore.QSettings(str(settings_path), ...)
        self._chat = ChatConfig()
        self._ui = UIConfig()
        self._app = AppConfig()
        self.load()

    @property
    def chat(self) -> ChatConfig:
        """Get chat configuration (read-only)."""
        return self._chat

    def update_chat(self, **kwargs) -> None:
        """Update chat config with validation."""
        # Validate, update, persist
        ...

    def load(self) -> None:
        """Load all config from QSettings."""
        ...

    def save(self) -> None:
        """Save all config to QSettings."""
        ...
```

**Usage:**
```python
# Before
timeout = _safe_int(config.value("chat/timeout_seconds", 30), 30)

# After
timeout = config_manager.chat.timeout_seconds  # Type-safe!
```

---

### Phase 3.1.4: Centralize Config Access

**Goal:** Remove direct `_config` access from all components

**Strategy:**
1. Pass `ConfigManager` to components instead of raw `QSettings`
2. Replace all `config.value(...)` with `config_manager.section.property`
3. Replace all `config.setValue(...)` with `config_manager.update_section(...)`
4. Remove `_config` instance variables from components

**Files to update:** 7 files (cli.py, app.py, window.py, etc.)

---

## Benefits of Refactor

✅ **Type Safety:** IDE autocomplete, type checking
✅ **Single Source of Truth:** Defaults defined once
✅ **Validation:** Invalid values caught early
✅ **Testability:** Easy to mock ConfigManager
✅ **Discoverability:** `config.chat.` shows all chat options
✅ **Reduced Errors:** No typos in config key strings

---

## Risk Assessment

### Low Risk
- Extracting remaining defaults to constants (no behavior change)

### Medium Risk
- Creating ConfigManager (new abstraction, but can be introduced gradually)
- Type conversion centralized (easier to debug than scattered `_safe_int` calls)

### High Risk
- Replacing all config access points (27 locations, must not break behavior)
- **Mitigation:** Update one component at a time, run smoke tests after each

---

## Implementation Plan

### Week 1: Foundation
1. ✅ Audit complete (this document)
2. Extract remaining hardcoded defaults
3. Create `config_schema.py` with dataclasses
4. Create `config_manager.py` with ConfigManager class
5. Write unit tests for ConfigManager

### Week 2: Migration
6. Update `cli.py` to use ConfigManager
7. Update `app.py` to use ConfigManager
8. Update `window.py` to use ConfigManager
9. Update controllers to use ConfigManager
10. Remove all direct QSettings access

### Week 3: Cleanup
11. Run full smoke test suite
12. Remove `_safe_int`/`_safe_float` helpers (no longer needed)
13. Update documentation
14. Final commit and push

---

**Status:** Phase 3.1.1 ready to start
**Next Step:** Extract `chat/max_retries` default to constant
