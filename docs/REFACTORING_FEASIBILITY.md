# 重構方案可行性分析

## 📋 提出的方案

### 1. DoroWindow - 不創建新組件，直接拆出去
### 2. Chat 重新組裝
### 3. 連接邏輯移到 app.py
### 4. MovementManager 和 TransitionPlayer 移到 state 資料夾
### 5. 先不動程式碼，只看可行性

---

## 🔍 現況分析

### 目前的目錄結構

```
doro_app/
├── core/
│   ├── chat/
│   │   ├── chat.py
│   │   ├── controller.py
│   │   ├── orchestrator.py
│   │   └── validator.py
│   │
│   ├── movement/
│   │   ├── manager.py          ← MovementManager 在這裡
│   │   ├── parser.py
│   │   └── fakes.py
│   │
│   ├── state/
│   │   ├── service.py
│   │   ├── repository.py
│   │   ├── models.py
│   │   ├── transition_player.py  ← TransitionPlayer 已經在這裡！
│   │   ├── transition_coordinator.py
│   │   ├── gif_manager.py
│   │   └── state_parser.py
│   │
│   └── exceptions.py
│
├── ui/
│   └── window.py
│
└── app.py
```

---

## ✅ 方案 1：DoroWindow 不創建新組件

### 現在的問題
```python
# window.py (715 行)
class DoroWindow:
    def wire_dependencies(self, ...):  # 100+ 行的連接邏輯
        # 連接 9 個組件
        # 處理所有回調
```

### 提議的改變
```python
# window.py (簡化後)
class DoroWindow:
    def __init__(self, ...):
        # 只初始化 UI 組件
        # 不再有 wire_dependencies()

# app.py
class DoroApp:
    def __init__(self):
        # 所有連接邏輯移到這裡
        self._connect_business_to_ui()
```

### ✅ 可行性：**高**
- 不需要創建新類別
- 邏輯更集中
- 符合 "DoroApp 是組裝根，DoroWindow 是 UI 組裝根" 的原則

---

## 🤔 方案 2：Chat 重新組裝

### 現在的 Chat 架構
```
ChatOrchestrator
  ├─ ChatController
  ├─ MovementManager
  └─ StateService
```

問題：
- ChatOrchestrator 混合了業務邏輯協調
- 它連接了 MovementManager（移動）和 StateService（狀態）
- 這些連接應該在哪裡做？

### 提議的改變

**選項 A：ChatOrchestrator 保持現狀，但連接移到 app.py**
```python
# app.py
class DoroApp:
    def __init__(self):
        # 創建 chat 組件
        chat_controller = ChatController(...)
        chat_orchestrator = ChatOrchestrator(
            chat_controller,
            # 不傳 movement 和 state_service？
        )

        # 在這裡連接
        chat_orchestrator.action_parsed.connect(
            lambda action: self._handle_chat_action(action)
        )
```

**選項 B：拆解 ChatOrchestrator**
```python
# ChatOrchestrator 只負責 Chat，不負責協調其他系統
# 協調邏輯移到 app.py
```

### 🤔 可行性：**中等**
- 需要仔細設計 Chat 的職責邊界
- 可能需要較大改動

### 建議
先看看 ChatOrchestrator 實際在做什麼，再決定怎麼重組。

---

## ✅ 方案 3：連接邏輯移到 app.py

### 現在
```python
# app.py
window = DoroWindow(...)
bubble = BubbleController(window, ...)
movement = MovementManager(window, ...)

# window.py
def wire_dependencies(self, bubble, movement, ...):
    # 連接所有信號
    bubble.repaint_requested.connect(self.update)
    movement.position_changed.connect(...)
```

### 提議
```python
# app.py
window = DoroWindow(...)
bubble = BubbleController(...)  # 不需要 window
movement = MovementManager(...)  # 不需要 window

# 在 app.py 中連接
bubble.repaint_requested.connect(window.update)
movement.position_changed.connect(window.move)
chat_orchestrator.bubble_text.connect(window.show_bubble)
```

### ✅ 可行性：**高**
- 完全可行
- 解決循環依賴
- DoroApp 成為唯一的組裝和連接點

### 需要改動的地方
1. BubbleController 移除 `window` 參數
2. TransitionPlayer 移除 `window` 參數
3. MovementManager 改用信號（或保持 Protocol）
4. window.py 移除 `wire_dependencies()`
5. app.py 添加所有連接邏輯

---

## ❓ 方案 4：MovementManager 和 TransitionPlayer 移到 state 資料夾

### 現況
```
core/
├── movement/
│   └── manager.py        ← MovementManager
└── state/
    └── transition_player.py  ← TransitionPlayer (已經在這裡！)
```

### 提議
```
core/
└── state/
    ├── service.py
    ├── transition_player.py  ✅ 已經在這裡
    └── movement_manager.py   ❓ 要移到這裡？
```

### 🤔 分析

#### TransitionPlayer
- ✅ **已經在 state/ 下了**
- ✅ 職責：狀態轉換動畫
- ✅ 完全屬於 state 系統
- **結論：不需要移動，已經在正確位置**

#### MovementManager
**它負責什麼？**
- 解析移動指令 `[MOVE: left]`
- 執行移動動畫（改變 window 位置）
- 切換到移動狀態（如 "walking"）

**它屬於 state 嗎？**

贊成移到 state/ 的理由：
- ✅ 移動時會切換狀態（walking, running 等）
- ✅ 和 StateService 緊密耦合
- ✅ 移動本質上是一種「狀態+動作」

反對移到 state/ 的理由：
- ❌ 移動是物理位置變化，不是狀態變化
- ❌ 有自己的領域邏輯（方向解析、速度計算等）
- ❌ 獨立的 movement/ 資料夾更清晰

### 🎯 建議

**選項 A：保持現狀** ⭐ 推薦
```
core/
├── movement/     ← MovementManager 保持在這裡
├── state/        ← TransitionPlayer 已經在這裡
└── chat/
```

**理由：**
- Movement 是獨立的領域概念
- 目前的分層已經很清晰
- 沒有必要強行合併

**選項 B：移到 state/**
```
core/
├── state/
│   ├── service.py
│   ├── transition_player.py
│   └── movement_manager.py  ← 移到這裡
└── chat/
```

**理由：**
- 如果你認為移動本質上是狀態的一部分
- 可以簡化 core/ 的結構

---

## 📊 整體可行性評估

| 方案 | 可行性 | 工作量 | 推薦度 | 備註 |
|-----|--------|--------|--------|------|
| 1. Window 不創建新組件 | ✅ 高 | 中 | ⭐⭐⭐⭐⭐ | 推薦 |
| 2. Chat 重新組裝 | 🤔 中 | 高 | ⭐⭐⭐ | 需要詳細設計 |
| 3. 連接邏輯移到 app.py | ✅ 高 | 中 | ⭐⭐⭐⭐⭐ | 強烈推薦 |
| 4a. TransitionPlayer 移到 state | ✅ 高 | 無 | ⭐⭐⭐⭐⭐ | 已經在那裡 |
| 4b. MovementManager 移到 state | 🤔 中 | 低 | ⭐⭐⭐ | 可選，不必要 |

---

## 🎯 推薦的執行順序

### Phase 1：連接邏輯移到 app.py（優先）
1. 修改 BubbleController - 移除 window 參數
2. 修改 TransitionPlayer - 移除 window 參數（改用純信號）
3. 在 app.py 中添加所有連接邏輯
4. 移除 window.py 的 `wire_dependencies()`

**預期結果：**
- ✅ 消除循環依賴
- ✅ Window 變簡單（715 行 → 500 行左右）
- ✅ DoroApp 成為唯一的組裝根

### Phase 2：Chat 重新組裝（可選）
- 需要先詳細分析 ChatOrchestrator 的職責
- 決定是保持現狀還是拆解

### Phase 3：目錄重組（可選）
- MovementManager 是否移到 state/
- 根據 Phase 1 完成後的實際情況決定

---

## ❓ 待確認的問題

### Q1: MovementManager 要移到 state/ 嗎？
**我的建議：** 不用移，保持在 `core/movement/` 更清晰

**但如果你堅持要移，也可以。** 理由是什麼？

### Q2: Chat 要怎麼重新組裝？
需要先看看 ChatOrchestrator 的實際職責，再決定。

要我先分析 ChatOrchestrator 嗎？

### Q3: 執行順序
你同意從 Phase 1 開始嗎（連接邏輯移到 app.py）？

---

## 📝 總結

### ✅ 可行的部分
- Window 不創建新組件 ✅
- 連接邏輯移到 app.py ✅ **強烈推薦**
- TransitionPlayer 移到 state ✅ **已經在那裡**

### 🤔 需要討論的部分
- Chat 重新組裝 - 需要詳細設計
- MovementManager 移到 state - 可選，不必要

### 🎯 下一步
**你確認這個方案後，我們可以：**
1. 先執行 Phase 1（連接邏輯移到 app.py）
2. 看看效果
3. 再決定 Phase 2 和 3

**這個方案可行嗎？你有什麼調整或問題？**
