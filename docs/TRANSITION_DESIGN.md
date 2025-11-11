# Transition 功能設計方案

## 🎯 目標

添加兩個狀態之間的轉場動畫功能。

---

## 📊 完整的 Action 分類（修正版）

```
Action (動作)
├── State (靜態狀態)
│   ├─ idle.gif        - 循環播放
│   ├─ happy.gif       - 循環播放
│   └─ sad.gif         - 循環播放
│
├── Transition (轉場動畫) ← 需要新增
│   ├─ idle_to_happy.gif    - 播放一次
│   ├─ happy_to_sad.gif     - 播放一次
│   └─ sad_to_idle.gif      - 播放一次
│
└── Movement (移動動作)
    ├─ walking.gif + 位移    - 循環播放
    └─ jumping.gif + 位移    - 播放一次或循環
```

---

## 🗂️ 數據模型設計

### **新增：TransitionState**

```python
@dataclass(frozen=True)
class TransitionState:
    """
    兩個狀態之間的轉場動畫。

    轉場 GIF 只播放一次，播放完成後進入目標狀態。
    """

    key: str                    # "idle_to_happy"
    from_state: str             # "idle"
    to_state: str               # "happy"
    transition_gif_id: str      # GIF 資源 ID
    duration_ms: Optional[int] = None  # 動畫時長（ms）

    def with_changes(self, **changes) -> TransitionState:
        """Return a new TransitionState with specified changes."""
        return replace(self, **changes)
```

### **新增：TransitionCollection**

```python
class TransitionCollection(BaseCollection[TransitionState]):
    """
    管理狀態轉場動畫。

    功能：
    - 根據 from_state → to_state 查找轉場
    - 支援雙向查找（A→B 和 B→A）
    """

    def find_transition(
        self,
        from_state: str,
        to_state: str
    ) -> Optional[TransitionState]:
        """查找兩個狀態之間的轉場動畫"""
        # 精確匹配
        key_forward = f"{from_state}_to_{to_state}"
        if key_forward in self._items:
            return self._items[key_forward]

        # 檢查是否有反向轉場（可選）
        key_reverse = f"{to_state}_to_{from_state}"
        if key_reverse in self._items:
            reverse = self._items[key_reverse]
            # 可以反向播放或使用同一個 GIF
            return reverse

        return None
```

---

## 🔄 狀態切換流程（修正版）

### **當前：瞬間切換**

```python
StateService.set_state("happy")
    ↓
立即切換到 happy.gif
```

### **新版：帶轉場動畫**

```python
StateService.transition_to("happy")
    ↓
1. 查找轉場動畫
   TransitionCollection.find_transition("idle", "happy")
   ↓
   找到 idle_to_happy.gif

2. 播放轉場動畫（一次）
   ├─ 載入 idle_to_happy.gif
   ├─ 設定 QMovie 為播放一次模式
   └─ 監聽 finished 信號

3. 轉場完成後
   QMovie.finished 信號觸發
   ↓
   切換到目標狀態
   ├─ 載入 happy.gif
   └─ 循環播放
```

---

## 🎬 QMovie 播放模式

```python
# 循環播放（State）
movie = QtGui.QMovie("idle.gif")
movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
movie.start()  # 無限循環

# 播放一次（Transition）
movie = QtGui.QMovie("idle_to_happy.gif")
movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
movie.setSpeed(100)  # 正常速度
movie.finished.connect(self._on_transition_finished)
movie.start()
# 播放到最後一幀後觸發 finished 信號
```

---

## 💾 數據存儲

### **transitions.json**

```json
{
  "idle_to_happy": {
    "from_state": "idle",
    "to_state": "happy",
    "transition_gif_id": "trans_idle_happy_v1",
    "duration_ms": 500
  },
  "happy_to_sad": {
    "from_state": "happy",
    "to_state": "sad",
    "transition_gif_id": "trans_happy_sad_v1",
    "duration_ms": 600
  },
  "any_to_idle": {
    "from_state": "*",
    "to_state": "idle",
    "transition_gif_id": "fade_to_idle_v1",
    "duration_ms": 300
  }
}
```

### **文件結構**

```
res/
├── state/              # State GIFs
│   ├── idle.gif
│   ├── happy.gif
│   └── sad.gif
│
├── ACTION/
│   ├── TRANSITION/     # Transition GIFs ← 新增
│   │   ├── idle_to_happy.gif
│   │   ├── happy_to_sad.gif
│   │   ├── sad_to_idle.gif
│   │   └── fade_to_idle.gif  # 通用轉場
│   │
│   └── MOVE/           # Movement GIFs
│       ├── walking.gif
│       └── jumping.gif
```

---

## 🔧 實現細節

### **1. StateService 添加轉場支援**

```python
class StateService:
    def __init__(self, ...):
        self._states = StateCollection()
        self._move_states = MoveStateCollection()
        self._transitions = TransitionCollection()  # 新增
        self._transition_repo = TransitionRepository(...)  # 新增

        self._is_transitioning = False  # 轉場中標誌
        self._transition_target: Optional[str] = None

    def transition_to(
        self,
        target_key: str,
        *,
        force_immediate: bool = False
    ) -> bool:
        """
        帶轉場動畫的狀態切換。

        Args:
            target_key: 目標狀態
            force_immediate: 強制瞬間切換（跳過轉場）
        """
        current_key = self._states._current_key
        if current_key == target_key:
            return True  # 已經是目標狀態

        # 查找轉場動畫
        if not force_immediate:
            transition = self._transitions.find_transition(
                current_key,
                target_key
            )
            if transition:
                return self._play_transition(transition, target_key)

        # 沒有轉場動畫，直接切換
        return self.set_state(target_key)

    def _play_transition(
        self,
        transition: TransitionState,
        target_key: str
    ) -> bool:
        """播放轉場動畫"""
        self._is_transitioning = True
        self._transition_target = target_key

        # 觸發轉場事件
        if self.on_transition_started:
            self.on_transition_started(transition)

        return True

    def _on_transition_finished(self):
        """轉場動畫播放完成"""
        if not self._is_transitioning:
            return

        self._is_transitioning = False
        target = self._transition_target
        self._transition_target = None

        # 切換到目標狀態
        if target:
            self.set_state(target)
```

### **2. DoroWindow 處理轉場動畫**

```python
class DoroWindow:
    def __init__(self):
        # ...
        self._transition_movie: QtGui.QMovie | None = None

        # 訂閱轉場事件
        self._state_service.on_transition_started = self._on_transition_started

    def _on_transition_started(self, transition: TransitionState):
        """開始播放轉場動畫"""
        # 獲取轉場 GIF 路徑
        gif_path = self._gif_repo.get_path(transition.transition_gif_id)
        if not gif_path:
            # 沒有 GIF，直接切換
            self._state_service._on_transition_finished()
            return

        # 停止當前 GIF
        if self._gif_movie:
            self._gif_movie.stop()

        # 播放轉場 GIF（一次）
        self._transition_movie = QtGui.QMovie(str(gif_path))
        self._transition_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        self._transition_movie.frameChanged.connect(self._on_movie_frame_changed)

        # 監聽播放完成
        self._transition_movie.finished.connect(
            self._state_service._on_transition_finished
        )

        # 開始播放（只播放一次）
        self._transition_movie.start()

        # 暫時使用轉場動畫
        self._gif_movie = self._transition_movie
```

---

## 🎮 使用範例

### **範例 1：有轉場動畫**

```python
# LLM 輸出
"(STATE: happy)"

# 執行流程
StateService.transition_to("happy")
    ↓
1. 查找轉場：找到 idle_to_happy.gif
2. 播放轉場：播放 idle_to_happy.gif（一次）
3. 轉場完成：切換到 happy.gif（循環）

# 視覺效果
idle.gif (循環)
    → idle_to_happy.gif (播放一次)
    → happy.gif (循環)
```

### **範例 2：沒有轉場動畫**

```python
# LLM 輸出
"(STATE: excited)"

# 執行流程
StateService.transition_to("excited")
    ↓
1. 查找轉場：沒有找到 idle_to_excited.gif
2. 直接切換：立即切換到 excited.gif

# 視覺效果
idle.gif → excited.gif (瞬間切換)
```

### **範例 3：強制瞬間切換**

```python
# 緊急情況（如錯誤處理）
StateService.transition_to("idle", force_immediate=True)
# 跳過轉場動畫，直接切換
```

---

## 📋 實現步驟

### **階段 1：數據模型**

```markdown
1. [ ] 創建 TransitionState 類別
2. [ ] 創建 TransitionCollection 類別
3. [ ] 創建 TransitionRepository 類別
4. [ ] 添加 transitions.json 支援
```

### **階段 2：核心邏輯**

```markdown
1. [ ] StateService 添加 transition_to() 方法
2. [ ] StateService 添加轉場事件回調
3. [ ] DoroWindow 處理轉場動畫播放
4. [ ] GIF 播放模式切換（循環 vs 一次）
```

### **階段 3：UI 整合**

```markdown
1. [ ] State Manager Dialog 添加轉場管理
2. [ ] 支援上傳轉場 GIF
3. [ ] 顯示轉場列表
4. [ ] 測試轉場播放
```

### **階段 4：LLM 整合**

```markdown
1. [ ] ChatOrchestrator 使用 transition_to() 替代 set_state()
2. [ ] 更新 prompt 說明轉場功能
3. [ ] 測試完整流程
```

---

## ⚠️ 注意事項

### **1. GIF 播放模式**

```python
# 問題：QMovie 默認無限循環
movie.start()  # 會一直循環播放

# 解決：監聽 frameChanged，到最後一幀時停止
def _on_transition_frame_changed(self, frame_number: int):
    if self._transition_movie:
        total_frames = self._transition_movie.frameCount()
        if total_frames > 0 and frame_number >= total_frames - 1:
            # 最後一幀
            self._transition_movie.stop()
            self._state_service._on_transition_finished()
```

### **2. 轉場 GIF 生成建議**

```markdown
在 ComfyUI 生成轉場 GIF 時：

□ 時長：0.5-1 秒（15-30 幀）
□ 起始幀：應接近 from_state 的最後一幀
□ 結束幀：應接近 to_state 的第一幀
□ 幀率：30 FPS
□ 尺寸：與 State GIF 相同
```

### **3. 可選優化**

```python
# 智能轉場選擇
class TransitionCollection:
    def find_transition(self, from_state, to_state):
        # 1. 精確匹配：idle_to_happy
        # 2. 通用轉場：any_to_happy
        # 3. 反向轉場：happy_to_idle (reversed)
        # 4. 默認淡入淡出：fade_transition
```

---

## 🎯 總結

### **完整的 Action 體系**

```
State       → 靜態循環 GIF (idle.gif)
Transition  → 一次性轉場 GIF (idle_to_happy.gif)
Movement    → 移動循環 GIF + 位移 (walking.gif)
```

### **優先級**

1. **高優先級** - 先完成 State 系統（添加基本情緒狀態）
2. **中優先級** - 添加 Transition 功能（可選，視覺更流暢）
3. **高優先級** - 完成 Movement 系統（已實現，需添加更多動作）

### **是否立即實現？**

**建議：暫緩**

原因：
- State 系統還缺少基本情緒狀態
- Transition 是錦上添花（視覺優化）
- 可以先用瞬間切換測試 FSM 功能

**何時實現？**

等以下完成後再考慮：
1. 基本 State 狀態完整（5-10 個情緒）
2. FSM + UI 測試通過
3. LLM 連接正常工作
4. 有時間優化視覺效果
