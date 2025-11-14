# 專業代碼審查報告
> 以專業程序員視角進行殘酷誠實的評估

## 執行摘要

**重構進度：** 70% 完成
**架構改進：** ✅ 顯著提升
**Law of Demeter 違反：** ❌ 嚴重 (22+ 處)
**整體耦合度：** ⚠️ 中等偏高

---

## 1. Law of Demeter (迪米特法則) 違反分析

### 🔴 嚴重違反 (Critical)

#### 問題 1: 訪問內部私有成員
```python
# window.py:1240-1241 (3處類似)
self._state_service.state_repo.save_all(
    self._state_service.states._states,      # ❌ 訪問私有 _states
    self._state_service.states._protected_keys  # ❌ 訪問私有 _protected_keys
)
```

**影響：**
- 破壞封裝
- StateCollection 的內部實現變更會破壞 Window
- 違反「只和朋友說話」原則

**建議修復：**
```python
# state_service.py 添加方法
def save_current_states(self) -> bool:
    """Save all states to persistent storage."""
    return self.state_repo.save_all(
        self.states._states,
        self.states._protected_keys
    )

# window.py 改用
self._state_service.save_current_states()
```

---

#### 問題 2: 鏈式調用超過兩層
```python
# movement_manager.py:289 (8處類似)
window._state_service.states.get(self._movement_previous_state)  # ❌ 3層鏈

# chat_orchestrator.py:101
self._window._state_service.move_states.is_movement_only(state_key)  # ❌ 4層鏈
```

**影響：**
- MovementManager 知道太多關於 Window 內部結構的細節
- 難以重構 StateService 的內部 API

**建議修復：**
```python
# window.py 添加封裝方法
def has_state(self, key: str) -> bool:
    """Check if a state exists."""
    return self._state_service.states.get(key) is not None

def is_movement_only_state(self, key: str) -> bool:
    """Check if state is movement-only."""
    return self._state_service.move_states.is_movement_only(key)

def set_state(self, key: str) -> bool:
    """Change to a different state."""
    return self._state_service.set_state(key)

# movement_manager.py 改用
if window.has_state(self._movement_previous_state):
    window.set_state(self._movement_previous_state)
```

---

#### 問題 3: 訪問 Repository 的私有方法
```python
# window.py:1330-1342
self._gif_repo._sanitize_key(key)  # ❌ 私有方法
self._gif_repo._primary_path(key)  # ❌ 私有方法
self._gif_repo._variant_dir(key)   # ❌ 私有方法
self._gif_repo.storage_dir.parent  # ❌ 深層屬性訪問
```

**影響：**
- Window 依賴 GifRepository 的內部實現
- 重構 GifRepository 會破壞 Window

**建議修復：**
```python
# state_repository.py 添加公共方法
class GifRepository:
    def get_state_storage_path(self, key: str) -> Path:
        """Get primary storage path for state GIF."""
        return self._primary_path(key)

    def get_state_variants_dir(self, key: str) -> Path:
        """Get variants directory for state."""
        return self._variant_dir(key)

    def get_move_storage_path(self, key: str) -> Path:
        """Get storage path for movement GIF."""
        return self.storage_dir.parent / "ACTION" / "MOVE" / f"{self._sanitize_key(key)}.gif"

# window.py 改用公共方法
self._gif_repo.get_state_storage_path(key)
```

---

## 2. 耦合度分析

### 當前依賴關係圖

```
Window (1811行)
  ├─→ StateService (暴露 states, move_states, state_repo - 違反封裝)
  ├─→ GifRepository (暴露私有方法 - 違反封裝)
  ├─→ StateRepository (透過 StateService 訪問 - 正確)
  ├─→ BubbleController (正確)
  ├─→ MovementManager (相互依賴 - 循環耦合)
  ├─→ ChatOrchestrator (相互依賴 - 循環耦合)
  └─→ ChatController (正確)

MovementManager
  ├─→ Window (強依賴 - window._state_service.states.get())
  └─→ StateService (間接透過 Window 訪問 - LoD 違反)

ChatOrchestrator
  ├─→ Window (強依賴 - window._state_service.move_states)
  └─→ MovementManager (正確)
```

### 🟡 中等問題

#### 問題 4: 循環依賴
```python
# window.py
self._movement = MovementManager(self)  # Window → MovementManager
self._chat_orchestrator = ChatOrchestrator(self, ...)

# movement_manager.py
window._state_service.set_state()  # MovementManager → Window → StateService

# chat_orchestrator.py
self._window._state_service.move_states  # ChatOrchestrator → Window → StateService
```

**影響：**
- 難以單獨測試 MovementManager
- 測試 Window 時必須創建完整的依賴樹

**建議修復：**
```python
# 使用依賴注入，而非傳遞整個 Window
class MovementManager:
    def __init__(
        self,
        state_provider: StateProvider,  # 抽象介面
        movement_executor: MovementExecutor,
    ):
        self._state_provider = state_provider
        self._executor = movement_executor

# Window 實現介面
class DoroWindow(StateProvider):
    def has_state(self, key: str) -> bool:
        return self._state_service.states.get(key) is not None

    def set_state(self, key: str) -> bool:
        return self._state_service.set_state(key)
```

---

## 3. 責任分配問題

### 問題 5: Window 類仍然太大 (1811 行)

**分析：**
- 窗口渲染：~400 行 ✓
- 狀態管理遺留代碼：~200 行 ⚠️ (應該刪除)
- 對話框管理：~150 行 ⚠️ (應該提取)
- 配置管理：~100 行 ⚠️ (應該提取)
- 聊天集成：~80 行 ✓

**建議重構：**
```python
# 提取配置管理
class WindowConfigManager:
    def __init__(self, config: QtCore.QSettings):
        self._config = config

    def get_preferred_size(self) -> tuple[int, int]: ...
    def save_bubble_config(self, config: BubbleConfig): ...

# 提取狀態對話框管理
class StateDialogManager:
    def __init__(self, state_service: StateService, parent: QWidget):
        self._service = state_service
        self._parent = parent

    def show_gif_manager(self): ...
    def show_add_state_dialog(self): ...
```

---

## 4. 資料流問題

### 問題 6: 事件回調與直接調用混用

```python
# 好的模式 (事件驅動)
self._state_service.on_state_changed = self._on_state_changed

# 不好的模式 (直接調用混雜)
def _toggle_bubble(self, checked: bool):
    # ...
    self._state_service.state_repo.save_all(...)  # ❌ 繞過 Service 層
```

**影響：**
- 一部分使用事件模式，一部分直接調用
- 狀態變更路徑不一致

**建議：**
- 所有狀態修改都應該透過 StateService 公共 API
- StateService 觸發事件，Window 響應

---

## 5. API 設計問題

### 問題 7: StateService 暴露內部結構

```python
class StateService:
    # ❌ 公開暴露內部集合
    self.states = StateCollection()
    self.move_states = MoveStateCollection()

    # ❌ 公開暴露 Repository
    self.state_repo = StateRepository(...)
    self.gif_repo = GifRepository(...)
```

**影響：**
- 外部代碼可以直接修改內部狀態
- 無法控制狀態變更的一致性

**建議修復：**
```python
class StateService:
    def __init__(self, ...):
        # ✅ 改為私有
        self._states = StateCollection()
        self._move_states = MoveStateCollection()
        self._state_repo = StateRepository(...)
        self._gif_repo = GifRepository(...)

    # ✅ 提供查詢方法
    def get_state(self, key: str) -> Optional[State]:
        return self._states.get(key)

    def has_state(self, key: str) -> bool:
        return self._states.get(key) is not None

    def is_movement_only(self, key: str) -> bool:
        return self._move_states.is_movement_only(key)

    # ✅ 提供修改方法（會觸發事件）
    def update_visual_config(self, key: str, **visual_changes) -> bool:
        state = self._states.get(key)
        if not state:
            return False

        updated = state.with_visual(**visual_changes)
        self._states.add(updated)
        self._save_states()
        self._emit_states_modified()
        return True

    def _save_states(self) -> bool:
        return self._state_repo.save_all(
            self._states._states,
            self._states._protected_keys
        )
```

---

## 6. 遺留代碼清理

### 問題 8: 死代碼和空方法仍然存在

```python
# window.py 中的死代碼
def _init_states(self):
    """Legacy method - state initialization now handled by StateService.initialize()"""
    pass  # ❌ 應該刪除

def _reset_state_overrides(self):
    # OLD: No equivalent needed - states are immutable
    pass  # ❌ 應該刪除

def _register_move_state(...):
    """Legacy method - move state registration now handled by StateService"""
    pass  # ❌ 應該刪除
```

**建議：** 立即刪除所有空方法，或者使用 `@deprecated` 裝飾器標記。

---

## 7. 改進優先級排序

### 🔴 高優先級 (必須修復)

1. **封裝 StateService 內部成員** (2-3 小時)
   - 將 `states`, `move_states`, `state_repo`, `gif_repo` 改為私有
   - 提供公共查詢/修改方法
   - 影響：22+ 處調用需要更新

2. **添加 Window 封裝方法** (1-2 小時)
   - `has_state()`, `is_movement_only_state()`, `set_state()`
   - 消除 MovementManager 和 ChatOrchestrator 中的 LoD 違反
   - 影響：8 處調用需要更新

3. **修復私有方法訪問** (1 小時)
   - GifRepository 提供公共方法
   - 影響：4 處調用需要更新

### 🟡 中優先級 (應該修復)

4. **消除循環依賴** (4-6 小時)
   - 定義 StateProvider 抽象介面
   - MovementManager 依賴介面而非 Window
   - 需要重新設計依賴注入

5. **清理死代碼** (30 分鐘)
   - 刪除所有空方法
   - 刪除註釋掉的舊代碼

6. **提取配置管理** (2-3 小時)
   - WindowConfigManager 類
   - 減少 Window 類大小

### 🟢 低優先級 (可選)

7. **統一事件模式** (3-4 小時)
   - 所有狀態修改都透過 StateService
   - 消除直接 Repository 調用

8. **完善單元測試** (8-10 小時)
   - StateService 單元測試
   - Repository 層單元測試
   - MovementManager 集成測試

---

## 8. 重構後的預期架構

```
┌─────────────────────────────────────────────────────┐
│ DoroWindow (Presentation Layer)                    │
│ - 只負責 UI 渲染和用戶交互                            │
│ - 實現 StateProvider 介面                            │
│ - 不直接訪問 Repository                              │
└──────────────┬──────────────────────────────────────┘
               │
               ├─→ StateService (Business Logic)
               │   ├─ 私有: _states, _move_states
               │   ├─ 私有: _state_repo, _gif_repo
               │   ├─ 公共: get_state(), set_state()
               │   ├─ 公共: update_visual(), save_states()
               │   └─ 事件: on_state_changed, on_states_modified
               │
               ├─→ MovementManager (依賴 StateProvider 介面)
               │   └─ 不知道 StateService 的存在
               │
               ├─→ ChatOrchestrator (依賴 StateProvider 介面)
               │   └─ 不知道 StateService 的存在
               │
               └─→ WindowConfigManager (新提取)
                   └─ 管理 QSettings

Repository Layer (StateService 私有依賴)
├─ StateRepository (JSON 持久化)
├─ GifRepository (GIF 文件管理)
└─ MoveStateRepository (移動狀態持久化)
```

---

## 9. 代碼質量評分

| 指標 | 分數 | 說明 |
|------|------|------|
| **架構設計** | 7/10 | Repository 模式良好，但封裝不足 |
| **Law of Demeter** | 3/10 | 嚴重違反，22+ 處鏈式調用 |
| **單一職責** | 6/10 | Window 仍然過大，但比舊版好很多 |
| **依賴注入** | 5/10 | 部分使用，但循環依賴嚴重 |
| **封裝性** | 4/10 | 大量私有成員和方法被外部訪問 |
| **可測試性** | 5/10 | StateService 可測試，但 Window 難以測試 |
| **代碼重複** | 7/10 | 大幅減少，但仍有改進空間 |
| **命名清晰度** | 8/10 | 命名一致且描述性強 |

**總體評分：** **5.6/10** (及格但需要改進)

---

## 10. 結論與建議

### ✅ 已經做對的事情

1. **Repository 模式成功分離 I/O** - StateRepository, GifRepository 設計良好
2. **不可變數據模型** - State 使用 `@dataclass(frozen=True)` 避免意外修改
3. **事件驅動架構** - `on_state_changed` 回調解耦 UI 和業務邏輯
4. **刪除 1565 行 StateManager** - 勇敢的決定，執行得當

### ❌ 最大的問題

1. **Law of Demeter 違反泛濫** - 需要立即修復
2. **過度暴露內部結構** - StateService 應該更加封裝
3. **循環依賴未解決** - 需要介面抽象

### 🎯 下一步行動

**立即修復 (今天)：**
- [ ] StateService 內部成員改為私有
- [ ] 添加公共 API 方法
- [ ] 更新所有調用點

**本週修復：**
- [ ] Window 添加封裝方法
- [ ] 消除 MovementManager 的 LoD 違反
- [ ] 刪除死代碼

**下週改進：**
- [ ] 定義 StateProvider 介面
- [ ] 重構依賴注入
- [ ] 添加單元測試

---

## 附錄：需要修復的具體位置

### LoD 違反列表
1. `window.py:1240` - `self._state_service.states._states`
2. `window.py:1241` - `self._state_service.states._protected_keys`
3. `window.py:1267` - `self._state_service.states._states`
4. `window.py:1268` - `self._state_service.states._protected_keys`
5. `window.py:1324` - `self._state_service.states._states`
6. `window.py:1325` - `self._state_service.states._protected_keys`
7. `window.py:1330` - `self._gif_repo._sanitize_key()`
8. `window.py:1334` - `self._gif_repo._primary_path()`
9. `window.py:1338` - `self._gif_repo._variant_dir()`
10. `window.py:1342` - `self._gif_repo.storage_dir.parent`
11. `movement_manager.py:289` - `window._state_service.states.get()`
12. `movement_manager.py:291` - `window._state_service.set_state()`
13. `movement_manager.py:417` - `window._state_service.states.get()`
14. `movement_manager.py:422` - `window._state_service.states.get()`
15. `movement_manager.py:434` - `window._state_service.states.get()`
16. `movement_manager.py:435` - `window._state_service.set_state()`
17. `movement_manager.py:451` - `window._state_service.states.get()`
18. `chat_orchestrator.py:101` - `self._window._state_service.move_states.is_movement_only()`

### 死代碼列表
1. `window.py:710-712` - `_init_states()`
2. `window.py:714-716` - `_load_custom_states()`
3. `window.py:718-720` - `_init_move_states()`
4. `window.py:730-741` - `_register_move_state()`
5. `window.py:772-774` - `_restore_state_from_config()`
6. `window.py:885-887` - `_reset_state_overrides()`

---

**審查人：** Claude (專業程序員模式)
**日期：** 2025-11-11
**嚴酷程度：** 殘酷誠實 🔥
