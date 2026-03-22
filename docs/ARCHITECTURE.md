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
    │   ├── ResponseValidator (回覆驗證 + 自動重試)
    │   └── ChatWorker (異步執行)
    │       └── perform_chat_request()
    │           └── HTTP POST (OpenAI 相容 API)
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
ChatWorker (異步)
    ↓
LLM API (OpenAI 相容格式)
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
- ✅ 管理與 LLM 伺服器的通信
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

## 🔗 FSM 和 LLM 的連接點

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
│                      LLM Server (OpenAI 相容)                         │
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

2. 發送到 LLM 伺服器
   ├─ ChatController.start_request()
   ├─ ChatWorker (異步線程)
   └─ HTTP POST {server_url}/v1/chat/completions

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

---

## 📂 文件結構映射

```
doro_app/
├── 【FSM 核心】 core/state/
│   ├── models.py (392行)                # State, MoveState, TransitionState, Collections
│   ├── service.py (860行)               # StateService (FSM 大腦)
│   ├── repository.py (741行)            # 數據持久化 (含 TransitionStateRepository)
│   ├── transition_player.py (257行)     # 轉換動畫播放器
│   ├── transition_coordinator.py (180行) # 轉換協調器
│   ├── gif_manager.py (189行)           # GIF 資源管理
│   └── state_parser.py (131行)          # 狀態解析
│
├── 【核心管理】 core/
│   ├── core_manager.py (237行)          # 業務邏輯層協調器
│   └── exceptions.py (206行)            # 統一例外階層
│
├── 【移動系統】 core/movement/
│   ├── manager.py (413行)               # MovementManager (移動邏輯)
│   ├── parser.py (114行)                # 移動指令解析
│   └── port.py (25行)                   # Window Protocol
│
├── 【LLM 層】 core/chat/
│   ├── orchestrator.py (283行)          # 協調器 (連接 LLM 和 FSM)
│   ├── controller.py (523行)            # 聊天控制器 (含驗證和重試)
│   ├── chat.py (176行)                  # HTTP 工具 (urllib)
│   └── validator.py (156行)             # 回覆驗證器
│
├── 【UI 層】 ui/
│   ├── window.py (464行)                # 主視窗
│   ├── components/
│   │   ├── bubble_controller.py (194行) # 氣泡控制
│   │   ├── gif_player.py (124行)        # GIF 播放器
│   │   ├── context_menu_controller.py   # 右鍵選單
│   │   └── frameless_dialog.py          # 無框對話框
│   ├── controllers/
│   │   ├── state_controller.py (193行)  # 狀態 → ViewModel
│   │   ├── gif_controller.py (142行)    # GIF → ViewModel
│   │   ├── sprite_controller.py (179行) # 精靈控制
│   │   ├── click_action_controller.py   # 點擊動作
│   │   └── dialog_manager.py            # 對話框管理
│   ├── dialogs/
│   │   ├── chat_dialog.py (310行)       # 聊天對話框
│   │   ├── chat_settings_dialog.py      # 聊天設定
│   │   ├── state/
│   │   │   ├── manager_dialog.py (365行) # 狀態管理
│   │   │   ├── add_dialog.py (116行)     # 新增狀態
│   │   │   └── gif_gallery_dialog.py     # GIF 畫廊
│   │   └── move_state/
│   │       ├── manager_dialog.py (444行) # 動作管理
│   │       └── edit_dialog.py (453行)    # 動作編輯
│   ├── viewmodels/
│   │   └── doro_viewmodel.py (271行)    # UI 狀態 ViewModel
│   ├── rendering/
│   │   ├── rendering_engine.py (302行)  # 繪製邏輯
│   │   ├── design_tokens.py (147行)     # 設計 tokens
│   │   ├── sprite_renderer.py           # 精靈渲染
│   │   ├── gif_sprite_renderer.py       # GIF 渲染
│   │   └── fallback_sprite.py           # 後備精靈
│   ├── theme/
│   │   ├── theme.py (170行)             # 主題管理
│   │   └── themed_menu.py (388行)       # 粉紅主題選單
│   ├── layout/
│   │   └── layout_manager.py (263行)    # 視窗佈局
│   ├── events/
│   │   └── mouse_event_handler.py       # 滑鼠事件
│   └── helpers/
│       └── chat_ui_helper.py (223行)    # 聊天 UI 輔助
│
├── 【工具/配置】 utils/
│   ├── actions.py (128行)               # 動作解析器
│   ├── config_manager.py (418行)        # 配置管理
│   ├── config_schema.py (190行)         # 配置結構
│   ├── config_defaults.py               # 配置預設值
│   ├── workers.py (52行)                # 異步工作器
│   ├── logger.py (83行)                 # 日誌系統
│   ├── paths.py (21行)                  # 路徑定義
│   ├── prompts.py (33行)                # Prompt 管理
│   ├── models.py (22行)                 # 通用模型
│   └── utils.py (19行)                  # 通用工具
│
├── 【入口】
│   ├── app.py (367行)                   # 應用程式入口和組裝
│   ├── bootstrap.py (79行)              # 依賴注入
│   ├── cli.py (108行)                   # CLI 入口
│   └── constants.py (165行)             # 常數定義
│
└── 【資源】 res/
    ├── click.txt                        # 點擊互動 prompt
    ├── ACTION/                          # 動作定義
    └── state/                           # 狀態資源
```

---

## 💾 數據持久化完整規格

### **1. states.json - 狀態定義**

儲存所有自訂狀態的配置（不包含內建的 `idle` 狀態）。

**檔案路徑**: `~/.doro/STATE/states.json`

**結構範例**:
```json
{
  "happy": {
    "label": "開心",
    "name_tag": "doro",
    "bob_amplitude": 8.0,
    "bubble_visible": true,
    "gradient_mid": "#FFD700FF"
  },
  "sad": {
    "label": "難過",
    "name_tag": "doro"
  }
}
```

**說明**: 狀態配置主要用於設定 GIF 和基本屬性，大部分視覺參數使用預設值。

---

### **2. move_states.json - 移動狀態定義**

定義所有移動動作及其參數。

**檔案路徑**: `~/.doro/STATE/move_states.json`

**結構範例**:
```json
{
  "walking": {
    "state_key": "walking",
    "direction": "any",
    "default_distance": null,
    "default_speed": "med"
  },
  "running": {
    "state_key": "running",
    "direction": "left|right",
    "default_distance": 100.0,
    "default_speed": "fast"
  },
  "jump": {
    "state_key": "jumping",
    "direction": "up",
    "default_distance": 50.0,
    "default_speed": "fast"
  }
}
```

**欄位說明**:
| 欄位 | 類型 | 說明 |
|------|------|------|
| `state_key` | string | 關聯的視覺狀態 key |
| `direction` | string | 移動方向: `any`, `left`, `right`, `up`, `down`, `left\|right`, `up\|down`, `none` |
| `default_distance` | float\|null | 預設移動距離（像素），null = 由 LLM 決定 |
| `default_speed` | string | 移動速度: `slow`, `med`, `fast` |

---

### **3. transitions.json - 狀態轉換定義** ⭐ NEW

定義狀態之間的轉換動畫。

**檔案路徑**: `~/.doro/STATE/transitions.json`

**結構範例**:
```json
{
  "idle_to_happy": {
    "from_state": "idle",
    "to_state": "happy",
    "transition_gif_id": "transition_smile"
  },
  "happy_to_excited": {
    "from_state": "happy",
    "to_state": "excited",
    "transition_gif_id": null
  },
  "excited_to_tired": {
    "from_state": "excited",
    "to_state": "tired",
    "transition_gif_id": "transition_yawn"
  }
}
```

**欄位說明**:
| 欄位 | 類型 | 說明 |
|------|------|------|
| `from_state` | string | 起始狀態的 key |
| `to_state` | string | 目標狀態的 key |
| `transition_gif_id` | string\|null | GIF 資源 ID，null = 使用預設 transition.gif |

**觸發機制**:
```python
# 當狀態改變時
old_state = "idle"
new_state = "happy"

# 系統自動查找轉換
transition = service.find_transition(old_state, new_state)
if transition and transition.transition_gif_id:
    # 播放過渡動畫
    play_transition_gif(transition.transition_gif_id)
else:
    # 直接切換狀態
    switch_to_state(new_state)
```

---

### **4. GIF 資源目錄結構**

**根目錄**: `~/.doro/STATE/`

```
STATE/
├── idle.gif                    # 內建 idle 狀態的 GIF
├── happy.gif                   # happy 狀態的主要 GIF
├── happy_variants/             # happy 狀態的變體 GIF 資料夾
│   ├── happy_1.gif
│   ├── happy_2.gif
│   └── happy_jump.gif
├── sad.gif
├── walking.gif
└── transitions/                # 轉換動畫 GIF（可選）
    ├── transition_smile.gif    # idle -> happy
    ├── transition_yawn.gif     # excited -> tired
    └── default_transition.gif  # 預設轉換動畫
```

**GIF 資源 ID 格式**:
- 主要 GIF: `{state_key}.gif` → resource_id: `"{state_key}.gif"`
- 變體 GIF: `{state_key}_variants/{filename}.gif` → resource_id: `"{state_key}_variants/{filename}.gif"`
- 轉換 GIF: `transitions/{filename}.gif` → resource_id: `"transitions/{filename}.gif"`

---

### **5. 數據載入流程**

```
應用程式啟動
    ↓
StateService.initialize()
    ↓
┌─────────────────────────────────┐
│ 1. 創建內建 idle 狀態             │
│    └─ 載入 idle.gif              │
├─────────────────────────────────┤
│ 2. StateRepository.load_all()   │
│    └─ 從 states.json 載入狀態    │
├─────────────────────────────────┤
│ 3. MoveStateRepository.load_all()│
│    └─ 從 move_states.json 載入   │
├─────────────────────────────────┤
│ 4. TransitionStateRepository     │
│    .load_all() ⭐ NEW            │
│    └─ 從 transitions.json 載入   │
├─────────────────────────────────┤
│ 5. 設定當前狀態為 idle            │
└─────────────────────────────────┘
    ↓
應用程式就緒
```

---

### **6. 數據保存流程**

**觸發時機**:
- 新增/編輯/刪除狀態
- 新增/編輯/刪除 MoveState
- 新增/編輯/刪除 TransitionState
- 修改狀態的 GIF
- 修改狀態的視覺配置

**保存流程**:
```python
# 使用者在 UI 中修改狀態
user_edits_state("happy", bob_amplitude=10.0)
    ↓
StateService.update_state("happy", bob_amplitude=10.0)
    ↓
StateRepository.save_all(states, protected_keys={"idle"})
    ↓
寫入 states.json
    ↓
觸發 on_states_modified 事件
    ↓
UI 更新反映變更
```

---

### **7. 資料完整性檢查**

系統在載入時會進行以下檢查：

1. **JSON 格式驗證**: 確保 JSON 格式正確
2. **必要欄位檢查**: 確保必要欄位存在
3. **類型驗證**: 確保欄位類型正確
4. **GIF 檔案存在性**: 檢查 GIF 檔案是否存在
5. **狀態引用完整性**:
   - MoveState 的 `state_key` 是否指向存在的狀態
   - TransitionState 的 `from_state` 和 `to_state` 是否存在

**錯誤處理**:
- 格式錯誤 → 跳過該項目，記錄警告
- 缺少 GIF → 不影響狀態載入，UI 顯示佔位圖
- 引用錯誤 → 跳過該項目，記錄警告

---

## 🎯 總結：FSM 與 LLM 連接的清晰定義

### **連接接口：ChatOrchestrator**

```python
class ChatOrchestrator:
    """
    LLM 和 FSM 之間的橋樑

    職責：
    1. 接收用戶輸入 → 發送到 LLM 伺服器
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

FSM 架構清晰，LLM 連接通過 ChatOrchestrator 解析文本指令來驅動狀態機。
