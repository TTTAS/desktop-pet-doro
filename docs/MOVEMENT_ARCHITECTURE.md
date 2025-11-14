# Movement 架構文檔

## 🎯 核心概念

你說得對！**Transition 就是不動的 Movement**。

```
Action (動作)
├── Transition (轉場) - 視覺變化，無位移
│   └── 範例：idle → happy (只換 GIF 和顏色)
│
└── Movement (移動) - 視覺變化 + 位移
    └── 範例：walking (換成 walking.gif + 向左移動 60px)
```

---

## 📊 當前架構總覽

### **兩種狀態類型**

```python
# 1. State (視覺狀態) - 處理 Transition
@dataclass(frozen=True)
class State:
    key: str              # "idle", "happy", "sad", etc.
    label: str            # 顯示名稱
    visual: VisualConfig  # 視覺配置（顏色、氣泡、GIF）
    primary_gif_id: str   # 主要 GIF

# 2. MoveState (移動狀態) - 處理 Movement
@dataclass(frozen=True)
class MoveState:
    key: str              # "walking", "jumping", "bouncing"
    state_key: str        # 關聯的視覺狀態（通常同名）
    direction: str        # "left", "right", "up", "down", "any"
    default_distance: float
    default_speed: str    # "slow", "med", "fast"
```

---

## 🔀 Transition (轉場) - 不動的動作

### **什麼是 Transition？**

**定義：** 只改變視覺效果，Doro 位置不變

**觸發方式：**
```python
# 方式 1：右鍵選單
States → happy  # 切換到 happy 狀態

# 方式 2：LLM 指令
"(STATE: happy)"  # 只切換狀態，不移動
```

**發生的事情：**
```
StateService.set_state("happy")
    ↓
on_state_changed 事件
    ↓
DoroWindow._on_state_changed()
    ↓ 視覺更新（無位移）
    ├─ 載入 happy.gif
    ├─ 更新顏色漸層
    ├─ 更新臉紅透明度
    ├─ 更新氣泡顯示
    └─ 觸發 repaint
```

### **Transition 範例**

| 從 | 到 | 視覺變化 | 位置變化 |
|----|----|---------|---------|
| idle | happy | GIF, 黃色漸層, 臉紅 | ❌ 無 |
| happy | sad | GIF, 藍色漸層, 無臉紅 | ❌ 無 |
| idle | sleeping | GIF, 紫色, 隱藏氣泡 | ❌ 無 |
| sad | excited | GIF, 橘色, 增大浮動 | ❌ 無 |

**所有 Transition 都是：**
```python
State → State (視覺切換，位置不變)
```

---

## 🚶 Movement (移動) - 有位移的動作

### **什麼是 Movement？**

**定義：** 改變視覺效果 **並且** 移動 Doro 的位置

**觸發方式：**
```python
# 方式 1：LLM 指令（推薦）
"[MOVE: left]"           # 向左移動
"[MOVE: right]"          # 向右移動
"[MOVE: bounce]"         # 彈跳（如果有定義）

# 方式 2：直接調用
MovementManager.apply_directional_move((1, 0))  # 向右
```

**發生的事情：**
```
ChatOrchestrator 解析 [MOVE: left]
    ↓
MovementManager.handle_move_bracket("left")
    ↓
1. 查找 MoveState
   ├─ key: "walking"
   ├─ direction: "left"
   └─ default_distance: 60px

2. 切換到對應的視覺狀態
   StateService.set_state("walking")
   ↓ 視覺更新
   └─ 載入 walking.gif

3. 執行移動動畫
   MovementManager._active_movement = MovementRequest(...)
   ↓ 在 _tick() 中每幀更新
   └─ window.move(new_x, new_y)  # 實際位移

4. 移動完成後
   └─ 恢復到之前的狀態（通常是 idle）
```

### **Movement 範例**

| 動作 | 視覺狀態 | 方向 | 距離 | 位置變化 |
|------|---------|------|------|---------|
| walking | walking.gif | left | 60px | ✅ 向左 60px |
| walking | walking.gif | right | 60px | ✅ 向右 60px |
| jumping | jumping.gif | up | 100px | ✅ 向上 100px |
| bouncing | bouncing.gif | any | 30px | ✅ 上下彈跳 |

**所有 Movement 都是：**
```python
State → MoveState → 移動動畫 → State (視覺切換 + 位移 + 恢復)
```

---

## 🔗 Transition 和 Movement 的關係

### **關鍵理解**

```
┌─────────────────────────────────────────────┐
│  所有 Action 都會觸發 State 切換              │
│                                             │
│  Transition: State A → State B (位置不變)    │
│  Movement:   State A → MoveState M → State A │
│              (位置改變，然後恢復狀態)          │
└─────────────────────────────────────────────┘
```

### **數據結構對應**

| 概念 | 數據模型 | 職責 | 位移 |
|------|---------|------|------|
| **Transition** | `State` | 視覺效果 | ❌ |
| **Movement** | `MoveState` + `State` | 視覺 + 移動 | ✅ |

### **為什麼說 Transition 是「不動的 Movement」？**

因為從結構上看：

```python
# Transition (簡化版)
class Transition:
    from_state: State
    to_state: State
    duration: float = 0  # 瞬間切換
    displacement: (0, 0)  # 無位移 ← 關鍵！

# Movement (完整版)
class Movement:
    from_state: State
    move_state: MoveState
    to_state: State
    duration: float = 2.0  # 移動需要時間
    displacement: (60, 0)  # 有位移 ← 關鍵！
```

**本質上都是狀態切換，只是 displacement 不同！**

---

## 🗂️ 當前實現方式

### **1. StateService (狀態機核心)**

```python
class StateService:
    _states: StateCollection        # 所有視覺狀態（Transition 用）
    _move_states: MoveStateCollection  # 所有移動狀態（Movement 用）

    def set_state(key: str):
        """Transition - 只切換狀態，不移動"""
        # 1. 驗證狀態存在
        # 2. 觸發 on_state_changed 事件
        # 3. UI 更新視覺
        # 4. 位置不變 ✓
```

### **2. MovementManager (移動管理器)**

```python
class MovementManager:
    _active_movement: MovementRequest | None
    _movement_remaining: float
    _movement_velocity: QPointF

    def handle_move_bracket(token: str):
        """Movement - 切換狀態並移動"""
        # 1. 解析方向（left, right, up, down）
        # 2. 查找對應的 MoveState
        # 3. 切換到 move_state.state_key
        # 4. 創建 MovementRequest
        # 5. 在 _tick() 中執行移動
        # 6. 完成後恢復原狀態
```

### **3. DoroWindow (視覺層)**

```python
class DoroWindow:
    def _on_state_changed(event: StateChangeEvent):
        """響應 Transition"""
        # 1. 載入新的 GIF
        # 2. 更新顏色
        # 3. 更新氣泡
        # 4. 不移動窗口位置

    def _tick():
        """每幀調用"""
        # 1. 處理 GIF 動畫
        # 2. 處理移動動畫 ← Movement 在這裡執行
        # 3. 重繪
```

---

## 📁 數據存儲

### **states.json - 視覺狀態 (Transition)**

```json
{
  "idle": {
    "label": "閒置",
    "visual": {
      "gradient_top": "#FFFFFF",
      "gradient_mid": "#FF9BE3",
      "bubble_visible": true
    },
    "primary_gif_id": "idle_v1"
  },
  "happy": {
    "label": "開心",
    "visual": {
      "gradient_top": "#FFEB3B",
      "gradient_mid": "#FFC107",
      "cheeks_alpha": 255
    },
    "primary_gif_id": "happy_v1"
  }
}
```

### **move_states.json - 移動狀態 (Movement)**

```json
{
  "walking": {
    "state_key": "walking",  // 關聯的視覺狀態
    "direction": "any",       // 支援所有方向
    "default_distance": 60.0,
    "default_speed": "med"
  },
  "jumping": {
    "state_key": "jumping",
    "direction": "up",        // 只能向上
    "default_distance": 100.0,
    "default_speed": "fast"
  }
}
```

---

## 🎮 使用範例

### **範例 1：純 Transition（不動）**

```python
# LLM 輸出
"(STATE: happy) 我今天很開心！"

# 解析結果
ChatOrchestrator._handle_actions_in_text()
    ↓
StateService.set_state("happy")
    ↓
DoroWindow 更新視覺
    ├─ 載入 happy.gif
    ├─ 切換到黃色漸層
    ├─ 顯示臉紅
    └─ 位置不變 ✓

# 結果：Doro 開心了，但沒有移動
```

### **範例 2：Transition + Movement（視覺 + 移動）**

```python
# LLM 輸出
"(STATE: excited) 讓我去那邊看看！[MOVE: left]"

# 解析結果
ChatOrchestrator._handle_actions_in_text()
    ↓
1. Transition
   StateService.set_state("excited")
   ↓ 載入 excited.gif, 橘色漸層

2. Movement
   MovementManager.handle_move_bracket("left")
   ↓
   a. 查找 walking MoveState (direction="any")
   b. 切換到 walking 狀態
   c. 向左移動 60px (2秒動畫)
   d. 恢復到 excited 狀態

# 結果：Doro 變興奮，然後走到左邊
```

### **範例 3：純 Movement（只移動）**

```python
# LLM 輸出
"我往右邊走走～ [MOVE: right]"

# 解析結果
ChatOrchestrator._handle_actions_in_text()
    ↓
MovementManager.handle_move_bracket("right")
    ↓
1. 保存當前狀態 (idle)
2. 切換到 walking 狀態
3. 向右移動 60px
4. 恢復到 idle 狀態

# 結果：Doro 移動了，狀態自動恢復
```

---

## 🏗️ 架構優勢

### ✅ **1. 關注點分離**

```
State        → 只管視覺
MoveState    → 只管移動參數
StateService → 協調狀態切換
MovementManager → 執行移動動畫
```

### ✅ **2. 可組合性**

```python
# 可以單獨使用
Transition only: (STATE: happy)
Movement only:   [MOVE: left]

# 也可以組合
Both: (STATE: excited) 文字 [MOVE: bounce]
```

### ✅ **3. 易於擴展**

```python
# 添加新的 Transition
states.json + {
    "sleepy": {"visual": {...}}
}

# 添加新的 Movement
move_states.json + {
    "floating": {
        "state_key": "floating",
        "direction": "up",
        "default_speed": "slow"
    }
}
```

---

## 🎯 當前狀態總結

### **已實現的功能**

| 功能 | 狀態 | 數據模型 |
|------|------|---------|
| **Transition** | ✅ 完整實現 | State, StateCollection, StateService |
| **Movement** | ✅ 完整實現 | MoveState, MoveStateCollection, MovementManager |
| **Transition + Movement** | ✅ 可組合 | ChatOrchestrator 協調 |

### **當前定義的狀態**

```
Transition States:
- idle     (閒置)
- walking  (movement-only 標記)

Movement States:
- walking  (any direction, 60px, med speed)
```

### **缺少的狀態**

```
建議添加的 Transition States:
- happy    (開心)
- sad      (難過)
- excited  (興奮)
- sleeping (睡覺)
- thinking (思考)
- shy      (害羞)
- angry    (生氣)

建議添加的 Movement States:
- jumping  (跳躍, up, 100px, fast)
- bouncing (彈跳, up, 30px, med)
- running  (快跑, any, 120px, fast)
- sneaking (潛行, any, 40px, slow)
```

---

## 🔧 需要優化的地方

### **問題 1：Movement 和 Transition 的命名混淆**

**當前：**
```python
StateService.set_state("walking")  # 這是 Transition 還是 Movement？
```

**建議：**
```python
# 明確區分
StateService.transition_to("happy")      # Transition
MovementManager.move_with("walking")     # Movement
```

### **問題 2：MoveState 需要對應的 State**

**當前：**
```json
// move_states.json
{"walking": {"state_key": "walking"}}

// states.json 也需要有 walking
{"walking": {"label": "Walking", ...}}
```

這造成重複定義。

**建議方案：**
```python
# MoveState 可以自動創建對應的 State
MoveState.state_key 如果不存在，自動創建一個 movement-only State
```

### **問題 3：缺少 Transition 時長控制**

**當前：**
```python
StateService.set_state("happy")  # 瞬間切換
```

**未來可添加：**
```python
StateService.transition_to("happy", duration=0.5)  # 漸變切換
```

---

## 📋 測試清單

### **Transition 測試（FSM + UI）**

```markdown
□ idle → happy (檢查 GIF, 顏色)
□ happy → sad (檢查視覺變化)
□ idle → sleeping (檢查氣泡隱藏)
□ 快速連續切換 (idle → happy → sad)
□ 切換到當前狀態 (idle → idle, 應該重新隨機選 GIF 變體)
```

### **Movement 測試（需要 LLM 或手動測試）**

```markdown
□ [MOVE: left] (檢查向左移動 60px)
□ [MOVE: right] (檢查向右移動 60px)
□ [MOVE: up] (檢查向上移動)
□ [MOVE: down] (檢查向下移動)
□ 邊界檢測 (不能移出螢幕)
□ 移動完成後恢復狀態
```

### **組合測試**

```markdown
□ (STATE: excited) [MOVE: bounce]
□ (STATE: happy) 文字內容 [MOVE: right]
□ [MOVE: left] (STATE: thinking) 思考中...
```

---

## 🚀 總結

### **回答你的問題**

**Q: 我的 action 應該是分為 transition 和 movement 對嗎？**

**A: 完全正確！** 你的理解非常準確。

```
Action (動作)
├── Transition (State → State)        視覺切換，無位移
└── Movement   (State → Move → State)  視覺切換 + 位移
```

### **當前架構已經支持這個概念**

- ✅ **Transition** 通過 `StateService.set_state()` 實現
- ✅ **Movement** 通過 `MovementManager.handle_move_bracket()` 實現
- ✅ **兩者可組合** 通過 `ChatOrchestrator` 協調

### **你說的「Transition 是不動的 Movement」**

**100% 正確！**

```python
Transition = Movement(displacement=0)
```

從概念上，它們都是狀態轉換，只是：
- Transition: Δposition = (0, 0)
- Movement: Δposition ≠ (0, 0)

---

## 📖 延伸閱讀

- **ARCHITECTURE.md** - 整體架構說明
- **FSM_UI_TEST_PLAN.md** - FSM + UI 測試計劃
- **state_models.py** - State 和 MoveState 定義
- **movement_manager.py** - 移動邏輯實現
