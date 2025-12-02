# 避免 God Object 的架構提案

**日期：** 2025-12-02
**狀態：** 提案討論
**目標：** 設計本質上避免 God Object 的架構

---

## 核心問題診斷

### 當前架構的根本缺陷

```
❌ 問題 1: 循環依賴
   Window ←→ Managers ←→ Controllers

❌ 問題 2: Window 知道太多（God Object）
   - 持有 9 個組件引用
   - 負責協調所有交互
   - 既是 View 又是 Coordinator

❌ 問題 3: 兩階段初始化
   1. 創建 Window
   2. 創建 Managers（需要 Window）
   3. 注入回 Window（wire_dependencies）

❌ 問題 4: 職責不清
   - Window: UI + 協調 + 業務邏輯
   - StateService: 狀態 + 移動 + 過渡 + 解析
   - Controllers: 分散的協調邏輯
```

---

## 解決方案：事件驅動架構 (Event-Driven Architecture)

### 核心理念

**組件不直接引用，通過事件通信**

```
Component A                    Component B
    |                              |
    | emit(EventX)                 |
    ↓                              ↓
  Event Bus  ─────────────→  listen(EventX)
    ↑                              ↓
    | emit(EventY)                 |
    |                              |
Component C                   Component D
```

**優點：**
- ✅ 零循環依賴（單向：Component → Event Bus）
- ✅ 組件獨立（不知道彼此存在）
- ✅ 易於測試（可以模擬事件）
- ✅ 易於擴展（新組件只需監聽事件）
- ✅ 沒有 God Object（沒有中央協調器）

---

## 提案架構：分層 + 事件驅動

### 架構圖

```
┌─────────────────────────────────────────────────────────┐
│                    Presentation Layer                    │
│  ┌──────────┐  ┌────────────┐  ┌────────────────────┐ │
│  │ DoroView │  │ DialogView │  │ BubbleView         │ │
│  │ (150行)   │  │            │  │                    │ │
│  └─────┬────┘  └─────┬──────┘  └──────┬─────────────┘ │
│        │ emit        │ emit             │ emit          │
└────────┼─────────────┼──────────────────┼───────────────┘
         │             │                  │
         ↓             ↓                  ↓
┌─────────────────────────────────────────────────────────┐
│                      Event Bus                           │
│            (輕量，只負責事件分發，~50行)                  │
└────────┬─────────────┬──────────────────┬───────────────┘
         ↓             ↓                  ↓
┌─────────────────────────────────────────────────────────┐
│                  Application Layer                       │
│  ┌─────────────┐ ┌──────────────┐ ┌─────────────────┐ │
│  │StateHandler │ │MovementHandler│ │ChatHandler      │ │
│  │(~200行)     │ │(~150行)       │ │(~200行)         │ │
│  └──────┬──────┘ └───────┬───────┘ └────────┬────────┘ │
│         │ use            │ use              │ use       │
└─────────┼────────────────┼──────────────────┼───────────┘
          ↓                ↓                  ↓
┌─────────────────────────────────────────────────────────┐
│                     Domain Layer                         │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ StateModel │  │ MovementModel │  │ ChatModel       │ │
│  │            │  │               │  │                 │ │
│  └──────┬─────┘  └───────┬───────┘  └────────┬────────┘ │
│         │ use            │ use              │ use       │
└─────────┼────────────────┼──────────────────┼───────────┘
          ↓                ↓                  ↓
┌─────────────────────────────────────────────────────────┐
│                Infrastructure Layer                      │
│  ┌──────────────┐ ┌───────────────┐ ┌────────────────┐ │
│  │StateRepository│ │GifRepository  │ │ConfigManager   │ │
│  │              │ │               │ │                │ │
│  └──────────────┘ └───────────────┘ └────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 依賴方向（單向，無循環）

```
Presentation ───→ Event Bus ←─── Application
                      ↓
                 (no upward deps)
                      ↓
                Application ───→ Domain ───→ Infrastructure
```

---

## 核心組件設計

### 1. Event Bus（輕量級，~50行）

```python
# doro_app/event_bus.py

class Event:
    """Base event class."""
    pass

class StateChangedEvent(Event):
    def __init__(self, old_key: str, new_key: str):
        self.old_key = old_key
        self.new_key = new_key

class EventBus:
    """
    Lightweight event bus for component communication.

    Components emit events, other components listen.
    No component knows about other components.
    """

    def __init__(self):
        self._listeners: dict[type, list[Callable]] = {}

    def emit(self, event: Event) -> None:
        """Emit an event to all registered listeners."""
        event_type = type(event)
        for listener in self._listeners.get(event_type, []):
            listener(event)

    def on(self, event_type: type[Event], handler: Callable) -> None:
        """Register a listener for an event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(handler)
```

**優點：**
- ✅ 非常簡單（~50行）
- ✅ 不是 God Object（只負責分發）
- ✅ 無業務邏輯
- ✅ 易於測試

---

### 2. DoroView（純 UI，~150行）

```python
# doro_app/ui/view.py

class DoroView(QtWidgets.QWidget):
    """
    Pure view layer - only handles Qt UI.

    Responsibilities:
    - Render UI
    - Emit events for user actions
    - Update UI in response to events

    Does NOT:
    - Hold business logic
    - Know about other components
    - Coordinate workflows
    """

    def __init__(self, event_bus: EventBus):
        super().__init__()
        self._event_bus = event_bus

        # Listen to events
        event_bus.on(StateChangedEvent, self._on_state_changed)
        event_bus.on(GifLoadedEvent, self._on_gif_loaded)

        self._setup_ui()

    def _on_user_click(self):
        """User clicked the window - emit event."""
        self._event_bus.emit(UserClickedEvent())

    def _on_state_changed(self, event: StateChangedEvent):
        """Update UI in response to state change."""
        self._update_display(event.new_key)
```

**特點：**
- ✅ 只有 UI 代碼
- ✅ 不持有其他組件引用
- ✅ 通過事件與世界通信
- ✅ ~150 行（從 679 減少 78%）

---

### 3. StateHandler（應用層，~200行）

```python
# doro_app/handlers/state_handler.py

class StateHandler:
    """
    Handles state-related events and coordinates state operations.

    Responsibilities:
    - Listen to state change requests
    - Coordinate with StateModel
    - Emit state change events

    Does NOT:
    - Know about UI
    - Hold UI references
    - Manage other domains (movement, chat)
    """

    def __init__(self, event_bus: EventBus, state_model: StateModel):
        self._event_bus = event_bus
        self._state_model = state_model

        # Listen to events
        event_bus.on(ChangeStateRequestEvent, self._handle_change_state)
        event_bus.on(AddStateRequestEvent, self._handle_add_state)

    def _handle_change_state(self, event: ChangeStateRequestEvent):
        """Handle state change request."""
        success = self._state_model.set_state(event.state_key)
        if success:
            # Emit success event
            self._event_bus.emit(StateChangedEvent(
                old_key=self._state_model.previous_state,
                new_key=event.state_key,
            ))
        else:
            # Emit failure event
            self._event_bus.emit(StateChangeFailedEvent(
                requested_key=event.state_key,
                reason="State not found",
            ))
```

**特點：**
- ✅ 單一領域（狀態）
- ✅ 不知道 UI 存在
- ✅ 通過事件通信
- ✅ ~200 行（專注）

---

## 組件對比

### Before（當前）

```python
# DoroWindow (679 lines)
class DoroWindow:
    def __init__(self):
        self._state_controller = None  # 等待注入
        self._gif_controller = None
        self._dialog_manager = None
        self._click_action_controller = None
        self._transition_player = None
        self._bubble_controller = None
        self._movement_manager = None
        self._chat_controller = None
        self._chat_orchestrator = None
        # ... 9 個組件

    def wire_dependencies(self, **components):
        """兩階段初始化 - 反模式"""
        self._state_controller = components['state_controller']
        # ... 注入 9 個組件

    # 679 lines of mixed UI + coordination + business logic
```

### After（提案）

```python
# DoroView (150 lines)
class DoroView(QtWidgets.QWidget):
    def __init__(self, event_bus: EventBus):
        super().__init__()
        self._event_bus = event_bus  # 只依賴事件總線

        # Register event listeners
        event_bus.on(StateChangedEvent, self._on_state_changed)
        event_bus.on(GifLoadedEvent, self._on_gif_loaded)
        # ...

        self._setup_ui()

    # Only UI code, ~150 lines
```

---

## 事件流示例

### 用戶點擊觸發狀態切換

```
1. User clicks window
   DoroView._on_click()
   │
   ├─ emit(UserClickedEvent())
   │
   ↓

2. Event Bus dispatches
   EventBus.emit(UserClickedEvent)
   │
   ├─ notify all listeners
   │
   ↓

3. ClickHandler receives event
   ClickHandler._on_user_clicked(event)
   │
   ├─ determine action
   ├─ emit(ChangeStateRequestEvent("happy"))
   │
   ↓

4. StateHandler receives event
   StateHandler._handle_change_state(event)
   │
   ├─ state_model.set_state("happy")
   ├─ emit(StateChangedEvent("idle", "happy"))
   │
   ↓

5. View updates
   DoroView._on_state_changed(event)
   │
   └─ update_display("happy")
```

**關鍵：** 沒有直接調用，全通過事件

---

## 優勢分析

### 1. 零循環依賴

```
Before:
Window ←→ Managers ←→ Controllers
   (循環地獄)

After:
View → EventBus ← Handler → Model → Repository
   (單向依賴)
```

### 2. 組件解耦

```
Before:
- Window 知道 9 個組件
- Managers 知道 Window
- Controllers 知道 Window

After:
- View 只知道 EventBus
- Handler 只知道 EventBus + Model
- 沒有組件知道 View 存在
```

### 3. 易於測試

```python
# Before: 需要 mock 9 個依賴
def test_window():
    mock_state = Mock()
    mock_gif = Mock()
    mock_dialog = Mock()
    # ... 9 個 mocks
    window = DoroWindow(...)
    window.wire_dependencies(state=mock_state, ...)

# After: 只需 mock EventBus
def test_view():
    event_bus = Mock()
    view = DoroView(event_bus)
    # Easy to test
```

### 4. 易於擴展

```python
# 添加新功能：只需創建新 Handler
class NotificationHandler:
    def __init__(self, event_bus: EventBus):
        event_bus.on(StateChangedEvent, self._notify)

    def _notify(self, event: StateChangedEvent):
        # Show notification
        pass

# 無需修改任何現有代碼
```

---

## 實施計劃

### Phase A: 建立事件基礎設施（1-2天）

1. 創建 `EventBus` 類（~50行）
2. 定義核心事件類
   - StateChangedEvent
   - GifLoadedEvent
   - UserClickedEvent
   - MovementCompletedEvent
3. 寫測試驗證事件分發

### Phase B: 提取 DoroView（3-4天）

1. 創建純 UI 的 DoroView
2. 將 UI 代碼從 DoroWindow 移到 DoroView
3. 用事件替代直接方法調用
4. 測試 UI 更新

### Phase C: 創建 Handlers（5-7天）

1. StateHandler（狀態相關事件）
2. MovementHandler（移動相關事件）
3. ChatHandler（聊天相關事件）
4. GifHandler（GIF 相關事件）
5. 每個 Handler 獨立測試

### Phase D: 整合與遷移（3-5天）

1. 在 DoroApp 中連接 EventBus
2. 逐步替換舊的直接調用
3. 運行全量測試
4. 刪除舊的 wire_dependencies

### Phase E: 清理（1-2天）

1. 刪除舊的 DoroWindow
2. 更新文檔
3. 最終測試

**總時間：** 2-3 週

---

## 風險與緩解

### 風險 1: 事件過多，難以追蹤

**緩解：**
- 清晰的事件命名約定
- 事件文檔（列出所有事件及其用途）
- Event tracing 工具（開發時可啟用）

### 風險 2: 性能問題（事件分發開銷）

**緩解：**
- 事件分發是 O(n)，n 是監聽器數量（通常 < 10）
- 可以實測，通常不是瓶頸
- 如有需要，可優化為基於類型的快速查找

### 風險 3: 異步事件順序問題

**緩解：**
- 事件分發是同步的（按註冊順序）
- 如需異步，可在 Handler 內部處理
- 保持事件處理簡單、快速

### 風險 4: 過度使用事件

**緩解：**
- **只在跨層/跨組件時用事件**
- 同一組件內部：直接方法調用
- 明確哪些交互用事件，哪些用方法

---

## 決策點

### 問題：是否實施這個架構？

**優點：**
- ✅ 徹底解決循環依賴
- ✅ 消除 God Object
- ✅ 清晰分層
- ✅ 易於測試和擴展

**缺點：**
- ⚠️ 需要 2-3 週重構
- ⚠️ 學習曲線（事件驅動模式）
- ⚠️ 需要重寫測試

### 替代方案

**方案 1：維持現狀**
- 風險：God Object 持續惡化
- 未來更難重構

**方案 2：小修小補**
- 繼續提取小組件
- 不改變整體架構
- 風險：治標不治本

**方案 3：實施事件驅動**
- 徹底解決架構問題
- 一勞永逸
- 未來擴展容易

---

## 建議

**我的建議：實施事件驅動架構（方案 3）**

**理由：**
1. 當前架構已經出現 God Object 徵兆
2. 小修小補無法解決根本問題（ApplicationMediator 也會變成 God Object）
3. 投資 2-3 週，換來長期的可維護性
4. 事件驅動是成熟模式，風險可控

**但需要你決定：**
- 是否願意投資 2-3 週？
- 是否認同事件驅動模式？
- 是否現在就重構，還是繼續現狀？

---

## 附錄：事件清單（初步）

```python
# State Events
StateChangedEvent(old_key, new_key)
StateChangeRequestEvent(state_key)
StateChangeFailedEvent(state_key, reason)
StateAddedEvent(state_key)
StateRemovedEvent(state_key)

# GIF Events
GifLoadedEvent(state_key, gif_path)
GifLoadFailedEvent(state_key, reason)

# Movement Events
MovementStartedEvent(direction)
MovementCompletedEvent(final_position)
MovementCancelledEvent(reason)

# Chat Events
ChatMessageReceivedEvent(message)
ChatResponseReadyEvent(response)
ChatErrorEvent(error)

# UI Events
UserClickedEvent(position)
WindowMovedEvent(position)
WindowFocusedEvent()
WindowBlurredEvent()
```

**總計：** ~20 個核心事件（可以漸進增加）

---

## 結論

這個架構提案：
1. ✅ **本質上避免 God Object**（沒有中央協調器）
2. ✅ **零循環依賴**（單向依賴鏈）
3. ✅ **清晰分層**（Presentation → Application → Domain → Infrastructure）
4. ✅ **易於測試**（組件獨立）
5. ✅ **易於擴展**（添加新功能不影響現有代碼）

**需要你決定是否實施。**
