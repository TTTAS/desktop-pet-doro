# Window 邏輯重構分析：MovementManager 和 TransitionPlayer

## 目標
把 window.py 中關於 MovementManager 和 TransitionPlayer 的邏輯移到各自的文件中。

---

## 📊 現況分析

### Window.py 中關於 MovementManager 的邏輯

#### 1. 持有引用和賦值
```python
# window.py line 139
self._movement: MovementManager | None = None

# window.py line 270 (in wire_dependencies)
self._movement = movement_manager
```

#### 2. 在 _tick 中調用
```python
# window.py line 412 (in _tick)
self._movement.process_active_movement(dt)
```

#### 3. 提供給 MovementManager 的公開 API
```python
# lines 553-582 - 這些方法實現了 MovementWindowPort Protocol
def clamp_window_position(self, pos: QtCore.QPoint) -> QtCore.QPoint
def current_position(self) -> QtCore.QPoint
def move_window_to(self, pos: QtCore.QPoint)
def resolve_move_state(self, key: str | None) -> tuple[...]
def get_bubble_offset(self) -> QtCore.QPointF
def apply_bubble_offset(self, offset: QtCore.QPointF, *, persist: bool = False)
def reset_tick_timer(self, value: float)
```

#### 4. 內部輔助方法
```python
# lines 614-635
def _resolve_move_state(self, key: str | None) -> tuple[...]
```

---

### Window.py 中關於 TransitionPlayer 的邏輯

#### 1. 持有引用和賦值
```python
# window.py line 137
self._transition_player: TransitionPlayer | None = None

# window.py line 169
self._previous_state_key: Optional[str] = None  # 追蹤前一個狀態

# window.py line 268 (in wire_dependencies)
self._transition_player = transition_player
```

#### 2. 連接信號
```python
# lines 305-306 (in wire_dependencies)
self._transition_player.transition_movie_loaded.connect(self._on_transition_movie_loaded)
self._transition_player.transition_completed.connect(self._on_transition_completed)
```

#### 3. 狀態變更時的轉換邏輯
```python
# lines 361-390 (in _on_controller_state_changed)
def _on_controller_state_changed(self, state_key: str):
    # Track previous state for transition detection
    old_state_key = self._previous_state_key
    self._previous_state_key = state_key
    self._current_state_key = state_key

    # Skip transition on initial load
    if old_state_key is None:
        self._load_state_gif(state_key)
        return

    # Skip transition if same state
    if old_state_key == state_key:
        return

    # Check if transition exists and play it
    if self._transition_player.play_transition(old_state_key, state_key):
        # Transition is playing
        pass
    else:
        # No transition, load GIF directly
        self._load_state_gif(state_key)
```

#### 4. 回調方法
```python
# lines 588-612
def _on_transition_movie_loaded(self, movie: QtGui.QMovie, sprite_size: QtCore.QSize):
    """Handle transition movie loaded signal."""
    self._gif_movie = movie
    self._view_model.set_sprite_size(sprite_size)
    self._apply_window_preferred_size()
    self.update()

def _on_transition_completed(self, target_state_key: str):
    """Handle transition completion signal."""
    self._load_state_gif(target_state_key)
```

---

## 🎯 可以移出去的邏輯

### 從 Window 移到 MovementManager

#### ❌ 不能移的
```python
# 這些是 Window 必須提供的 API (MovementWindowPort Protocol)
# MovementManager 需要調用這些方法
- clamp_window_position()
- current_position()
- move_window_to()
- get_bubble_offset()
- apply_bubble_offset()
- reset_tick_timer()
```

**為什麼不能移？**
- 這些操作直接涉及 Window 的狀態（位置、大小、氣泡）
- 只有 Window 才知道怎麼做這些事情
- MovementManager 只是調用者，不是實現者

#### ✅ 可以移的
```python
# 這個方法可以移到 MovementManager
def _resolve_move_state(self, key: str | None) -> tuple[...]:
    """Resolve movement state configuration."""
    # 這個邏輯應該在 MovementManager 內部
```

**改成：**
```python
# movement/manager.py
class MovementManager:
    def resolve_move_state_settings(self, key: str | None) -> tuple[...]:
        # 原本在 Window._resolve_move_state 的邏輯
```

#### ⚠️ 需要討論的
```python
# 在 _tick 中調用
self._movement.process_active_movement(dt)
```

**選項 1：保持在 Window（推薦）**
- Window 擁有主 tick timer
- Window 負責協調所有需要 tick 的組件
- 清晰的控制流

**選項 2：移到 app.py**
- app.py 創建一個全局 tick timer
- 但這會讓 app.py 變複雜

---

### 從 Window 移到 TransitionPlayer

#### ✅ 可以移的

##### 1. 狀態追蹤邏輯
```python
# Window 現在
self._previous_state_key: Optional[str] = None

old_state_key = self._previous_state_key
self._previous_state_key = state_key
```

**改成：**
```python
# TransitionPlayer 內部管理
class TransitionPlayer:
    def __init__(self, ...):
        self._previous_state: Optional[str] = None

    def on_state_changed(self, new_state_key: str):
        old_state = self._previous_state
        self._previous_state = new_state_key

        # 內部決定是否播放轉換
        if old_state and old_state != new_state_key:
            return self.play_transition(old_state, new_state_key)
        return False
```

##### 2. 轉換決策邏輯
```python
# Window 現在
if old_state_key is None:
    self._load_state_gif(state_key)
    return

if old_state_key == state_key:
    return

if self._transition_player.play_transition(old_state_key, state_key):
    pass
else:
    self._load_state_gif(state_key)
```

**改成：**
```python
# TransitionPlayer 內部
class TransitionPlayer:
    def on_state_changed(self, new_state_key: str) -> bool:
        """
        Handle state change and decide whether to play transition.

        Returns:
            True if transition is playing, False if should load GIF directly
        """
        old_state = self._previous_state
        self._previous_state = new_state_key

        # Skip on initial load
        if old_state is None:
            return False

        # Skip if same state
        if old_state == new_state_key:
            return False

        # Try to play transition
        return self.play_transition(old_state, new_state_key)
```

**Window 變成：**
```python
# window.py
def _on_controller_state_changed(self, state_key: str):
    # 簡化！只需要通知 TransitionPlayer
    if self._transition_player.on_state_changed(state_key):
        # Transition is playing, wait for completion
        pass
    else:
        # No transition, load GIF directly
        self._load_state_gif(state_key)
```

#### ❌ 不能移的
```python
# 回調方法必須留在 Window
def _on_transition_movie_loaded(self, movie, sprite_size):
    self._gif_movie = movie  # Window 的狀態
    self._view_model.set_sprite_size(sprite_size)  # Window 的 ViewModel
    self.update()  # Window 的重繪

def _on_transition_completed(self, target_state_key):
    self._load_state_gif(target_state_key)  # Window 的方法
```

**為什麼不能移？**
- 這些操作直接涉及 Window 的狀態
- 需要訪問 Window 的私有成員

**但可以簡化連接邏輯：**
- 這些連接應該在 app.py 中做，不在 window.py

---

## 📋 重構後的架構

### MovementManager (core/movement/manager.py)
```python
class MovementManager:
    """完全獨立的移動管理器，不依賴 Window。"""

    # ✅ 新增：從 Window 移過來的方法
    def resolve_move_state_settings(self, key: str | None) -> MoveStateSettings:
        """Resolve movement state configuration."""
        # 原本在 Window._resolve_move_state 的邏輯

    # 保持現有方法
    def process_active_movement(self, dt: float):
        """Process movement animation (Window 在 tick 中調用)."""

    def apply_directional_move(self, direction: str):
        """Apply directional movement."""
```

### TransitionPlayer (core/state/transition_player.py)
```python
class TransitionPlayer:
    """獨立的轉換播放器，內部管理狀態追蹤。"""

    def __init__(self, state_service: StateService):
        # ❌ 不需要 window 參數
        self._state_service = state_service
        self._previous_state: Optional[str] = None  # ✅ 內部追蹤

    # ✅ 新增：從 Window 移過來的邏輯
    def on_state_changed(self, new_state_key: str) -> bool:
        """
        Handle state change and decide whether to play transition.

        Returns:
            True if transition is playing, False otherwise
        """
        old_state = self._previous_state
        self._previous_state = new_state_key

        if old_state is None or old_state == new_state_key:
            return False

        return self.play_transition(old_state, new_state_key)
```

### DoroWindow (ui/window.py)
```python
class DoroWindow:
    """簡化的 Window，只負責 UI 協調。"""

    def __init__(self, ...):
        # ❌ 不再在這裡創建或持有這些引用
        # 由 app.py 創建並連接

    # ✅ 簡化的狀態變更處理
    def _on_controller_state_changed(self, state_key: str):
        # 由 app.py 通過信號連接到 TransitionPlayer
        # Window 只負責接收結果
        pass

    # ✅ 保留必要的 API (MovementWindowPort)
    def move_window_to(self, pos: QtCore.QPoint):
        """Window 必須提供的移動 API。"""

    # ✅ 保留必要的回調（由 app.py 連接）
    def _on_transition_movie_loaded(self, movie, sprite_size):
        """Update window state when transition loads."""
```

### DoroApp (app.py)
```python
class DoroApp:
    """組裝根，負責創建和連接所有組件。"""

    def __init__(self):
        # 創建組件（無循環依賴）
        window = DoroWindow(...)

        movement = MovementManager(
            window_port=window,  # 只依賴 Protocol
            state_service=state_service,
        )

        transition = TransitionPlayer(
            state_service=state_service,  # ❌ 不需要 window
        )

        # ✅ 在這裡連接所有邏輯

        # StateController 通知狀態變更
        state_controller.state_changed.connect(
            lambda state_key: self._on_state_changed(state_key, transition, window)
        )

        # TransitionPlayer 發送信號給 Window
        transition.transition_movie_loaded.connect(window._on_transition_movie_loaded)
        transition.transition_completed.connect(window._on_transition_completed)

        # Movement tick
        window._tick_signal.connect(
            lambda dt: movement.process_active_movement(dt)
        )

    def _on_state_changed(self, state_key: str, transition: TransitionPlayer, window: DoroWindow):
        """Coordinate state change between TransitionPlayer and Window."""
        if transition.on_state_changed(state_key):
            # Transition is playing
            pass
        else:
            # No transition, tell window to load GIF
            window._load_state_gif(state_key)
```

---

## ✅ 優點

1. **消除循環依賴**
   - TransitionPlayer 不需要 Window
   - MovementManager 只依賴 Protocol

2. **邏輯集中**
   - 轉換邏輯在 TransitionPlayer 內部
   - 移動邏輯在 MovementManager 內部

3. **Window 變簡單**
   - 從 715 行 → 預估 500 行左右
   - 只負責 UI 協調

4. **符合單一職責**
   - 每個組件只做自己的事
   - app.py 負責組裝和連接

---

## ⚠️ 需要注意的

1. **信號連接移到 app.py**
   - 所有跨組件的連接都在 app.py
   - Window 不再有 wire_dependencies()

2. **MovementWindowPort 保持不變**
   - Window 必須實現這個 Protocol
   - MovementManager 依賴 Protocol，不是具體類

3. **測試需要更新**
   - TransitionPlayer 測試不再需要 mock Window
   - 更容易單獨測試

---

## 🎯 結論

**可以移的：**
- ✅ Window._resolve_move_state → MovementManager.resolve_move_state_settings
- ✅ Window._previous_state_key → TransitionPlayer._previous_state
- ✅ Window 中的轉換決策邏輯 → TransitionPlayer.on_state_changed

**不能移的（必須留在 Window）：**
- ❌ MovementWindowPort 的實現方法（Window 的核心 API）
- ❌ _on_transition_movie_loaded, _on_transition_completed（訪問 Window 私有成員）

**需要移到 app.py：**
- ✅ 所有 wire_dependencies 的連接邏輯
- ✅ 跨組件的協調邏輯

**這個方案可行嗎？**
