# Doro 應用程式架構文檔

## 📐 整體架構概覽

```
┌─────────────────────────────────────────────────────────────────┐
│                         Doro 桌面寵物                              │
│                    (PySide6 Qt Application)                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                 ┌────────────┴────────────┐
                 │                         │
          ┌──────▼──────┐          ┌──────▼──────┐
          │   UI Layer  │          │ LLM Layer   │
          │   (視覺)     │          │ (智能)       │
          └──────┬──────┘          └──────┬──────┘
                 │                         │
                 └────────────┬────────────┘
                              │
                      ┌───────▼───────┐
                      │  FSM (核心)    │
                      │ StateService  │
                      └───────────────┘
```

---

## 🎯 核心架構：三層設計

### **第一層：狀態機 (FSM) - 核心大腦**

```
StateService (狀態服務)
    ├── StateCollection (狀態集合)
    │   ├── State (狀態實例)
    │   │   ├── key: str (唯一識別)
    │   │   ├── label: str (顯示名稱)
    │   │   ├── visual: VisualConfig (視覺配置)
    │   │   ├── primary_gif_id: str (主要 GIF)
    │   │   └── variant_gif_ids: list (變體 GIF)
    │   └── 狀態轉換邏輯
    │
    ├── MoveStateCollection (移動狀態集合)
    │   └── MoveState (移動狀態)
    │       ├── key: str
    │       ├── state_key: str (對應的視覺狀態)
    │       ├── direction: str (方向: left/right/up/down/any)
    │       ├── default_distance: float
    │       └── default_speed: str (slow/med/fast)
    │
    ├── TransitionStateCollection (狀態轉換集合) ⭐ NEW
    │   └── TransitionState (轉換狀態)
    │       ├── key: str (唯一識別)
    │       ├── from_state: str (起始狀態)
    │       ├── to_state: str (目標狀態)
    │       ├── transition_gif_id: str (過渡動畫 GIF)
    │       └── find_transition(from, to) (快速查找)
    │
    └── 事件發送
        ├── on_state_changed (狀態變更事件)
        └── on_states_modified (狀態列表修改事件)
```

**職責：**
- ✅ 管理所有狀態的生命週期
- ✅ 處理狀態轉換
- ✅ 發送狀態變更事件
- ✅ 驗證狀態合法性

**數據持久化：**
```
StateRepository
    └── states.json (所有狀態定義)

MoveStateRepository
    └── move_states.json (移動狀態定義)

TransitionStateRepository ⭐ NEW
    └── transitions.json (狀態轉換定義)

GifRepository
    └── STATE/ (GIF 檔案存儲)
        ├── {state_key}.gif (主要 GIF)
        └── {state_key}_variants/ (變體 GIF)
```

---

### **第二層：UI 層 - 視覺呈現**

```
DoroWindow (主視窗)
    │
    ├── 視覺渲染
    │   ├── paintEvent() - 繪製 Doro
    │   ├── GIF 動畫播放
    │   └── 氣泡對話框
    │
    ├── 使用者互動
    │   ├── mousePressEvent() - 拖曳
    │   ├── contextMenuEvent() - 右鍵選單
    │   └── DoroMenu (粉紅主題選單)
    │
    ├── 移動系統
    │   └── MovementManager
    │       ├── 平滑移動動畫
    │       ├── 窗口邊界檢測
    │       └── 方向解析
    │
    ├── 氣泡控制
    │   └── BubbleController
    │       ├── 顯示/隱藏
    │       ├── 自動消失
    │       └── 拖曳調整位置
    │
    └── 動作管理器 ⭐ NEW
        ├── MoveStateManagerDialog (動作管理主介面)
        │   ├── 表格顯示所有動作 (Key, Action GIF, Direction, Speed)
        │   ├── GIF 預覽動畫播放
        │   ├── 等寬可調整欄位
        │   ├── 網格線顯示
        │   └── 新增/編輯/刪除動作
        │
        └── EditMoveStateDialog (動作編輯對話框)
            ├── Action Type 選擇器 (Movement / Transition)
            ├── Movement 模式欄位:
            │   ├── Associated state (關聯狀態)
            │   ├── Direction (移動方向)
            │   └── Speed (速度)
            ├── Transition 模式欄位:
            │   ├── From state (起始狀態)
            │   └── To state (目標狀態)
            └── GIF 預覽區
```

**事件訂閱：**
```python
# Window 訂閱 StateService 事件
_state_service.on_state_changed = self._on_state_changed
_state_service.on_states_modified = self._on_states_modified

# 當狀態改變時
def _on_state_changed(self, event: StateChangeEvent):
    # 1. 更新視覺 (顏色、GIF)
    # 2. 更新氣泡
    # 3. 保存配置
```

**職責：**
- ✅ 渲染 Doro 視覺效果
- ✅ 處理用戶輸入
- ✅ 播放 GIF 動畫
- ✅ 響應狀態變更

---

### **第三層：LLM 層 - 智能驅動**

```
ChatOrchestrator (聊天協調器)
    │
    ├── ChatController (聊天控制器)
    │   ├── start_request(user_message)
    │   ├── 管理歷史記錄
    │   ├── 配置管理 (server_url, model, temperature)
    │   └── ChatRequestWorker (異步執行)
    │       └── perform_chat_request()
    │           └── HTTP POST to LMStudio
    │
    ├── 動作解析器
    │   ├── parse_actions_from_text()
    │   │   ├── (STATE: xxx) - 狀態指令
    │   │   └── [MOVE: direction] - 移動指令
    │   └── _handle_actions_in_text()
    │
    └── 狀態機驅動
        ├── _find_state_for_action(token)
        ├── _window.set_state(state_key)
        └── _movement.apply_directional_move(direction)
```

**數據流：**
```
用戶輸入
    ↓
ChatController.start_request()
    ↓
ChatRequestWorker (異步)
    ↓
LMStudio API (HTTP)
    ↓
LLM 回覆文本
    ↓
parse_actions_from_text()
    ↓
提取 (STATE: happy) 和 [MOVE: left]
    ↓
ChatOrchestrator._handle_actions_in_text()
    ↓
┌───────────────┬─────────────────┐
│               │                 │
▼               ▼                 ▼
StateService    MovementManager   BubbleController
.set_state()    .apply_move()     .set_text()
```

**職責：**
- ✅ 管理與 LMStudio 的通信
- ✅ 解析 LLM 回覆中的控制指令
- ✅ 驅動狀態機轉換
- ✅ 驅動移動系統
- ✅ 更新氣泡對話

---

## 🎬 TransitionState：狀態轉換動畫系統 ⭐ NEW

### **核心概念**

**TransitionState** 管理兩個狀態之間的過渡動畫。

```
狀態 A (idle) → 轉換動畫 (transition.gif) → 狀態 B (happy)
```

### **與 MoveState 的區別**

```
┌─────────────────┬──────────────────┬─────────────────┐
│     特性        │   MoveState      │ TransitionState │
├─────────────────┼──────────────────┼─────────────────┤
│ 用途            │ 移動動作          │ 狀態切換動畫     │
│ 觸發時機        │ LLM 指令/手動     │ 狀態轉換時       │
│ 方向            │ 有 (left/right)  │ 無 (不移動)     │
│ 距離            │ 有               │ 無              │
│ 關聯狀態        │ 單一狀態          │ 兩個狀態 (from/to)│
│ GIF 來源        │ 從關聯的 State   │ transition_gif_id│
└─────────────────┴──────────────────┴─────────────────┘
```

### **資料結構**

```python
@dataclass(frozen=True)
class TransitionState:
    key: str                          # "idle_to_happy"
    from_state: str                   # "idle"
    to_state: str                     # "happy"
    transition_gif_id: Optional[str]  # GIF 資源 ID
```

### **查找機制**

```python
# 快速查找 O(1)
transition = service.find_transition("idle", "happy")
if transition:
    play_gif(transition.transition_gif_id)
```

### **使用場景範例**

```
場景：Doro 從休息轉換到興奮

1. 當前狀態：idle (閒置)
2. LLM 指令：(STATE: excited)
3. 查找轉換：find_transition("idle", "excited")
4. 播放過渡：transition.gif (例如：伸懶腰動畫)
5. 切換狀態：excited (興奮狀態)
```

### **TransitionState vs Movement**

```
Movement (移動動作)：
  使用情境：Doro 需要物理移動
  例子："走到螢幕左邊" [MOVE: left]
  特點：有方向、有距離、改變位置

Transition (狀態轉換)：
  使用情境：狀態情緒變化的過渡
  例子："從開心變成害羞"
  特點：無方向、無距離、原地播放動畫
```

### **UI 管理介面**

在 **Action Manager** 中：

```
1. 點擊 "Add Action"
2. 選擇 "Action Type: Transition"
3. 填寫：
   - Key: idle_to_happy
   - From state: idle (下拉選單)
   - To state: happy (下拉選單)
4. 保存
```

結果儲存在 `transitions.json`：

```json
{
  "idle_to_happy": {
    "from_state": "idle",
    "to_state": "happy",
    "transition_gif_id": null
  }
}
```

---

## 🔗 FSM 和 LMStudio 的連接點

### **當前連接機制 (已實現)**

```python
# 1. LLM 回覆包含控制指令
assistant_text = "(STATE: happy) 我今天很開心！[MOVE: right]"

# 2. ChatOrchestrator 解析指令
cleaned_text, actions = parse_actions_from_text(assistant_text)
# actions = [("paren", "STATE: happy"), ("bracket", "MOVE: right")]

# 3. 執行狀態轉換
for kind, token in actions:
    if kind == "paren":  # (STATE: xxx)
        state_key = self._window._find_state_for_action(token)
        if state_key:
            self._window._set_state(state_key)  # ← FSM 狀態轉換

    elif kind == "bracket":  # [MOVE: direction]
        if self._movement.handle_move_bracket(token):
            # ← 觸發移動
            continue

# 4. 狀態改變觸發視覺更新
StateService.set_state(state_key)
    ↓
on_state_changed 事件
    ↓
DoroWindow._on_state_changed()
    ↓
更新 GIF、顏色、氣泡
```

### **連接流程圖**

```
┌─────────────────────────────────────────────────────────────┐
│                      LMStudio (LLM)                         │
│  輸入: "講個笑話給我聽"                                        │
│  輸出: "(STATE: happy) 好的！[MOVE: left] 為什麼企鵝不會飛..."  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  ChatOrchestrator      │
        │  解析控制指令           │
        └───┬────────────────┬───┘
            │                │
   ┌────────▼─────┐   ┌─────▼────────┐
   │  (STATE:     │   │  [MOVE:      │
   │   happy)     │   │   left]      │
   └────┬─────────┘   └─────┬────────┘
        │                   │
        ▼                   ▼
┌───────────────┐   ┌──────────────┐
│ StateService  │   │ Movement     │
│ .set_state()  │   │ Manager      │
└───────┬───────┘   └──────┬───────┘
        │                   │
        └────────┬──────────┘
                 │
                 ▼
        ┌────────────────┐
        │  DoroWindow    │
        │  視覺更新       │
        └────────────────┘
```

---

## 🎨 完整數據流範例

### 場景：用戶說 "講個笑話"

```
1. 用戶輸入
   ├─ DoroWindow.contextMenu → "Ask Doro"
   └─ ChatOrchestrator.send_message("講個笑話")

2. 發送到 LMStudio
   ├─ ChatController.start_request()
   ├─ ChatRequestWorker (異步線程)
   └─ HTTP POST http://localhost:1234/v1/chat/completions

3. LLM 思考並回覆
   └─ "(STATE: happy) 好的！[MOVE: bounce] 為什麼企鵝不會飛？因為太短了！"

4. 解析回覆
   └─ ChatOrchestrator._on_request_succeeded()
       ├─ parse_actions_from_text()
       │   ├─ 提取: (STATE: happy)
       │   └─ 提取: [MOVE: bounce]
       └─ _handle_actions_in_text()

5. 執行動作
   ├─ (STATE: happy) → StateService.set_state("happy")
   │   └─ 觸發 on_state_changed 事件
   │       └─ DoroWindow._on_state_changed()
   │           ├─ 載入 happy.gif
   │           ├─ 更新顏色漸層
   │           └─ 更新氣泡可見性
   │
   ├─ [MOVE: bounce] → MovementManager.handle_move_bracket("bounce")
   │   └─ 查找 move_states.json
   │       └─ 執行彈跳動畫
   │
   └─ 清理後的文本 → BubbleController.set_text()
       └─ 顯示 "為什麼企鵝不會飛？因為太短了！"

6. 視覺結果
   ├─ Doro 變成開心表情 (happy.gif)
   ├─ 執行彈跳動作 (上下移動)
   └─ 氣泡顯示笑話內容
```

---

## 🔧 當前架構的優點

### ✅ **1. 清晰的關注點分離**
```
StateService (FSM)     → 只管狀態，不管 UI
DoroWindow (UI)        → 只管渲染，不管狀態邏輯
ChatOrchestrator (LLM) → 只管協調，不管實現細節
```

### ✅ **2. 事件驅動架構**
```python
# UI 不需要輪詢狀態
StateService.on_state_changed = lambda event: update_ui(event.new_state)
```

### ✅ **3. 可擴展的動作系統**
```python
# 容易添加新指令
"(STATE: sleeping)"   # 狀態切換
"[MOVE: jump]"        # 移動動作
"(COLOR: pink)"       # 未來可擴展
"(EMOTION: shy)"      # 未來可擴展
```

### ✅ **4. LLM 與狀態機解耦**
- LLM 只需輸出簡單的文本指令
- ChatOrchestrator 負責解析和路由
- StateService 不知道 LLM 的存在

---

## 🚀 改進建議

### **問題 1：LLM 不知道當前狀態**

**現狀：**
```python
# LLM 收到的 prompt 沒有包含當前狀態
system_prompt = "你是 Doro，一個可愛的桌面寵物..."
```

**建議改進：**
```python
# 在 prompt 中包含當前狀態
state = self._state_service.get_current_state()
context = f"""
你是 Doro，一個可愛的桌面寵物。

當前狀態：{state.label}
可用狀態：{', '.join(self._state_service.visible_state_keys())}
可用動作：{', '.join(self._state_service.all_move_state_keys())}

請在回覆中使用 (STATE: xxx) 切換狀態，使用 [MOVE: direction] 移動。
"""
```

### **問題 2：狀態轉換缺乏驗證**

**現狀：**
```python
# 任何狀態都可以轉換到任何狀態
self._window._set_state(state_key)
```

**建議改進：**
```python
# StateService 中添加狀態機規則
class StateService:
    def can_transition(self, from_state: str, to_state: str) -> bool:
        """檢查是否允許狀態轉換"""
        # 例：睡覺狀態不能直接跳到興奮狀態
        if from_state == "sleeping" and to_state == "excited":
            return False
        return True
```

### **問題 3：缺少狀態持續時間**

**建議添加：**
```python
@dataclass
class State:
    key: str
    label: str
    min_duration_ms: int = 0  # 最小持續時間
    auto_transition_to: str | None = None  # 自動轉換到哪個狀態
```

---

## 📂 文件結構映射

```
doro_app/
├── 【FSM 核心】⭐ UPDATED
│   ├── state_models.py (327行)          # State, MoveState, TransitionState, Collections
│   ├── state_service.py (560行)         # StateService (FSM 大腦)
│   └── state_repository.py (500行)      # 數據持久化 (含 TransitionStateRepository)
│
├── 【UI 層】⭐ UPDATED
│   ├── window.py (1778行)               # 主視窗
│   ├── bubble_controller.py (159行)     # 氣泡控制
│   ├── movement_manager.py (462行)      # 移動管理
│   ├── themed_menu.py (258行)           # 粉紅主題選單
│   └── state_dialogs.py (886行)         # 狀態管理對話框 (新增動作類型選擇)
│       ├── StateGifManagerDialog        # 狀態 GIF 管理
│       ├── GifVariantDialog             # GIF 變體管理
│       ├── AddStateDialog               # 新增狀態
│       ├── MoveStateManagerDialog ⭐    # 動作管理主介面 (含 GIF 預覽表格)
│       └── EditMoveStateDialog ⭐       # 動作編輯 (支援 Movement/Transition)
│
├── 【LLM 層】
│   ├── chat_orchestrator.py (156行)     # 協調器 (連接 LLM 和 FSM)
│   ├── chat_controller.py (253行)       # 聊天控制器
│   ├── chat.py (132行)                  # HTTP 工具
│   └── workers.py (33行)                # 異步執行
│
├── 【工具/配置】
│   ├── actions.py (100行)               # 動作解析器
│   ├── models.py (40行)                 # 舊模型 (待清理)
│   └── theme.py (130行)                 # 主題管理
│
└── 【入口】
    └── cli.py (110行)                   # 應用程式啟動
```

---

## 🎯 總結：FSM 與 LMStudio 連接的清晰定義

### **連接接口：ChatOrchestrator**

```python
class ChatOrchestrator:
    """
    LLM 和 FSM 之間的橋樑

    職責：
    1. 接收用戶輸入 → 發送到 LMStudio
    2. 接收 LLM 回覆 → 解析控制指令
    3. 執行指令 → 驅動 StateService (FSM)
    4. 更新 UI → 顯示結果
    """
```

### **數據協議：文本指令**

```
LLM 輸出格式：
    (STATE: 狀態名) - 切換狀態
    [MOVE: 方向]    - 執行移動
    普通文本        - 顯示在氣泡
```

### **核心方法：_handle_actions_in_text()**

```python
# 這是 FSM 和 LLM 連接的核心
def _handle_actions_in_text(self, assistant_text: str) -> str:
    # 1. 解析指令
    cleaned_text, actions = parse_actions_from_text(assistant_text)

    # 2. 執行每個指令
    for kind, token in actions:
        if kind == "paren":  # (STATE: xxx)
            state_key = self._window._find_state_for_action(token)
            self._window._set_state(state_key)  # ← 驅動 FSM

        elif kind == "bracket":  # [MOVE: xxx]
            self._movement.handle_move_bracket(token)  # ← 驅動移動

    # 3. 返回清理後的文本
    return cleaned_text
```

---

**你的 FSM 已經非常清晰了！LMStudio 連接也很明確，就是通過 ChatOrchestrator 解析文本指令來驅動狀態機。**

需要我幫你優化某個特定部分嗎？比如：
1. 讓 LLM 知道當前狀態？
2. 添加狀態轉換規則？
3. 改進指令解析系統？
4. 其他想法？
