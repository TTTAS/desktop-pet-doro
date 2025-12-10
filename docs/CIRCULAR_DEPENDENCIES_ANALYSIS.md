# DoroWindow 循環依賴分析報告

## 檢測日期：2024-12-08

---

## 🔴 發現的循環依賴

### 1. **DoroWindow ↔ MovementManager** (中等嚴重)

**依賴路徑：**
```
DoroWindow
  ↓ (創建時傳入)
MovementManager.__init__(window: MovementWindowPort)
  ↓ (調用 window 的方法)
MovementManager 調用：
  - window.current_position()
  - window.move_window_to()
  - window.clamp_window_position()
  - window.get_bubble_offset()
  - window.apply_bubble_offset()
  - window.reset_tick_timer()
  ↓ (通過 wire_dependencies 傳回)
DoroWindow._movement = movement_manager
  ↓ (Window 調用)
Window 調用：
  - self._movement.process_active_movement()
  - self._movement.apply_directional_move()
  - self._movement.handle_move_bracket()
```

**循環路徑：**
```
Window → MovementManager → Window (調用方法) → Window (持有引用)
```

**嚴重程度：** 🟡 中等
**原因：** MovementManager 使用了 Protocol (MovementWindowPort)，所以不是強依賴整個 Window，但還是有循環。

---

### 2. **DoroWindow ↔ BubbleController** (嚴重)

**依賴路徑：**
```
DoroWindow
  ↓ (創建時傳入)
BubbleController.__init__(window: DoroWindow)
  ↓ (持有引用並調用)
BubbleController 調用：
  - self._window.update()  # 直接調用 Window 方法
  - self._window (用於 parent)
  ↓ (通過 wire_dependencies 傳回)
DoroWindow._bubble_controller = bubble_controller
  ↓ (Window 調用)
Window 調用：
  - self._bubble_controller.set_text()
  - self._bubble_controller.clear_text()
  - self._bubble_controller.set_visible()
  - self._bubble_controller.apply_offset()
```

**循環路徑：**
```
Window → BubbleController → Window (直接調用) → Window (持有引用)
```

**嚴重程度：** 🔴 嚴重
**原因：** BubbleController 直接依賴整個 DoroWindow 類型，不是 Protocol！

---

### 3. **DoroWindow ↔ TransitionPlayer** (嚴重)

**依賴路徑：**
```
DoroWindow
  ↓ (創建時傳入)
TransitionPlayer.__init__(window: DoroWindow)
  ↓ (持有引用，用作 parent)
TransitionPlayer 使用 window 作為 QObject parent
  ↓ (發送信號)
TransitionPlayer.transition_movie_loaded.emit(movie, size)
TransitionPlayer.transition_completed.emit(state_key)
  ↓ (通過 wire_dependencies 傳回並連接)
DoroWindow._transition_player = transition_player
Window 連接信號：
  - _transition_player.transition_movie_loaded.connect(
      self._on_transition_movie_loaded
    )
  - _transition_player.transition_completed.connect(
      self._on_transition_completed
    )
  ↓ (Window 調用)
Window 調用：
  - self._transition_player.play_transition()
```

**循環路徑：**
```
Window → TransitionPlayer → Window (作為 parent 和信號目標) → Window (持有引用)
```

**嚴重程度：** 🔴 嚴重
**原因：** TransitionPlayer 直接依賴整個 DoroWindow 類型。

---

### 4. **DoroWindow ↔ MouseEventHandler** (輕微)

**依賴路徑：**
```
DoroWindow
  ↓ (在 wire_dependencies 中創建)
MouseEventHandler(bubble_controller=bubble_controller)
  ↓ (發送信號)
MouseEventHandler.window_drag_requested.emit(pos)
  ↓ (Window 連接)
_mouse_handler.window_drag_requested.connect(self.move)
  ↓ (Window 調用)
Window 在 mousePressEvent 等中調用：
  - self._mouse_handler.handle_press(e, self.frameGeometry())
  - self._mouse_handler.handle_move(e)
```

**循環路徑：**
```
Window → MouseEventHandler → Window (信號) → Window (事件調用)
```

**嚴重程度：** 🟢 輕微
**原因：** MouseEventHandler 不直接依賴 Window，只通過信號通信。這是合理的設計。

---

## 📊 循環依賴總結

| 組件 | 依賴類型 | 嚴重程度 | 需要修復 |
|------|---------|---------|---------|
| MovementManager | Protocol (MovementWindowPort) | 🟡 中等 | 是 |
| BubbleController | 整個 DoroWindow 類 | 🔴 嚴重 | **是** |
| TransitionPlayer | 整個 DoroWindow 類 | 🔴 嚴重 | **是** |
| MouseEventHandler | 無直接依賴（信號） | 🟢 輕微 | 否 |

**總計：3 個需要修復的循環依賴**

---

## 🔧 問題根源

### 根本原因：兩階段初始化模式

```python
# app.py
# 階段 1：創建 Window
window = DoroWindow(...)

# 階段 2：創建需要 Window 引用的組件
movement = MovementManager(window, ...)
bubble = BubbleController(window, ...)
transition = TransitionPlayer(window, ...)

# 階段 3：通過 wire_dependencies 傳回 Window
window.wire_dependencies(
    movement_manager=movement,
    bubble_controller=bubble,
    transition_player=transition,
    ...
)
```

這導致：
1. Window 需要這些組件來工作
2. 這些組件需要 Window 引用來工作
3. 形成循環

---

## ✅ 解決方案

### 方案 1：使用 Protocol (部分解決)

**MovementManager 已經這樣做了：**
```python
class MovementManager:
    def __init__(self, window: MovementWindowPort, ...):
        # 只依賴接口，不依賴具體類
```

**應該對其他組件也這樣做：**
```python
class BubbleWindowPort(Protocol):
    """Interface for bubble-related window operations."""
    def update(self): ...
    # 只暴露必要的方法

class BubbleController:
    def __init__(self, window: BubbleWindowPort, ...):
        # 依賴接口，不依賴整個 Window
```

**優點：** 減少耦合，但循環依賴還在
**缺點：** 沒有完全解決循環依賴問題

---

### 方案 2：使用信號/槽模式（推薦）✨

**完全消除循環依賴：**

```python
# TransitionPlayer 不需要 Window 引用
class TransitionPlayer(QtCore.QObject):
    transition_movie_loaded = Signal(object, QtCore.QSize)
    transition_completed = Signal(str)

    def __init__(self, state_service: StateService):
        # 不需要 window 參數！
        super().__init__()  # 沒有 parent
        self._state_service = state_service

# BubbleController 不需要 Window 引用
class BubbleController(QtCore.QObject):
    repaint_requested = Signal()  # 發送信號，不直接調用 window.update()

    def __init__(self, config_manager: ConfigManager):
        # 不需要 window 參數！
        super().__init__()  # 沒有 parent

# DoroApp 中連接
class DoroApp:
    def __init__(self):
        window = DoroWindow(...)

        # 創建組件（不需要 window）
        transition = TransitionPlayer(state_service)
        bubble = BubbleController(config_manager)

        # 在這裡連接信號
        transition.transition_movie_loaded.connect(window.on_transition_movie_loaded)
        bubble.repaint_requested.connect(window.update)

        # Window 也可以調用組件
        # window._transition_player = transition
        # window._bubble_controller = bubble
```

**優點：**
- ✅ 完全消除循環依賴
- ✅ 組件可以獨立測試
- ✅ 符合 Qt 的信號/槽模式
- ✅ Window 不需要 wire_dependencies()

**缺點：**
- ⚠️ 需要較大的重構
- ⚠️ 需要修改很多地方

---

### 方案 3：反轉依賴方向

**讓 Window 提供服務，而不是被依賴：**

```python
# 現在：組件依賴 Window
BubbleController(window: DoroWindow)
  └─ 調用 window.update()

# 改成：組件提供服務，Window 使用
BubbleController()
  └─ 發送 repaint_requested 信號
Window 訂閱信號
  └─ bubble.repaint_requested.connect(self.update)
```

這就是方案 2 的信號/槽模式。

---

## 🎯 推薦的修復優先順序

### 優先級 1（高）：BubbleController
- **問題最嚴重**：直接依賴整個 DoroWindow
- **修復方式**：改用信號
- **預計工作量**：2-3 小時

### 優先級 2（高）：TransitionPlayer
- **問題嚴重**：直接依賴整個 DoroWindow
- **修復方式**：改用信號（已經有信號了，只需移除 window 依賴）
- **預計工作量**：1-2 小時

### 優先級 3（中）：MovementManager
- **問題較輕**：已經用了 Protocol
- **修復方式**：考慮改用信號，或保持現狀
- **預計工作量**：3-4 小時（如果要改）

---

## 📝 修復後的預期結果

```
# 修復前（3 個循環依賴）
Window ↔ BubbleController
Window ↔ TransitionPlayer
Window ↔ MovementManager

# 修復後（0 個循環依賴）
Window → BubbleController (單向，通過信號)
Window → TransitionPlayer (單向，通過信號)
Window → MovementManager (可選：改用信號或保留 Protocol)
```

**依賴方向變成：**
```
DoroApp (組裝根)
  ├─ 創建 Window
  ├─ 創建 Controllers/Managers
  └─ 連接它們（單向依賴）

不再有循環！
```
