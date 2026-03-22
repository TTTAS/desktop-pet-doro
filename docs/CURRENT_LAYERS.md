# Doro 專案分層架構分析

## 📊 目前的層數結構

根據代碼分析，Doro 專案有以下幾層：

---

## 1️⃣ 資料層 (Data/Persistence Layer)

**位置：** `doro_app/core/state/repository.py`, `doro_app/utils/config_manager.py`, `doro_app/utils/config_schema.py`

**職責：**
- 資料的持久化（讀寫 JSON）
- 檔案系統操作
- 配置的儲存和讀取

**組件：**
```
doro_app/
├── core/state/
│   └── repository.py
│       ├── StateRepository          # states.json
│       ├── MoveStateRepository      # move_states.json
│       ├── TransitionRepository     # transitions.json
│       └── GifRepository            # GIF 檔案管理
│
└── utils/
    ├── config_manager.py            # 配置管理
    └── paths.py                     # 路徑定義
```

**資料格式：**
- `~/.doro/STATE/states.json` - 狀態定義
- `~/.doro/STATE/move_states.json` - 移動狀態
- `~/.doro/STATE/ACTION/TRANSITION/transitions.json` - 轉換定義
- `~/.doro/STATE/*.gif` - GIF 資源

---

## 2️⃣ 領域層 / 核心業務邏輯層 (Domain/Core Layer)

**位置：** `doro_app/core/`

**職責：**
- 業務邏輯（狀態管理、移動、轉換）
- 領域模型定義
- 業務規則執行

**子層結構：**

### 2a. 領域模型 (Domain Models)
```
doro_app/core/state/
└── models.py (392行)
    ├── State                        # 狀態實體
    ├── MoveState                    # 移動狀態實體
    ├── TransitionState              # 轉換實體
    ├── VisualConfig                 # 視覺配置值對象
    ├── StateCollection              # 狀態集合
    ├── MoveStateCollection          # 移動狀態集合
    └── TransitionStateCollection    # 轉換集合
```

### 2b. 領域服務 (Domain Services)
```
doro_app/core/
├── core_manager.py                  # CoreManager (業務邏輯協調器)
├── exceptions.py                    # 統一例外階層
│
├── state/
│   ├── service.py                   # StateService (FSM 核心, 860行)
│   ├── transition_player.py         # 轉換播放器
│   ├── transition_coordinator.py    # 轉換協調器
│   ├── gif_manager.py               # GIF 管理
│   └── state_parser.py              # 狀態解析
│
├── movement/
│   ├── manager.py                   # MovementManager (移動邏輯)
│   ├── parser.py                    # 移動指令解析
│   ├── port.py                      # Window Protocol
│   └── fakes.py                     # 測試用假對象
│
└── chat/
    ├── chat.py                      # HTTP 聊天工具 (urllib)
    ├── controller.py                # ChatController (含驗證和重試)
    ├── orchestrator.py              # ChatOrchestrator
    └── validator.py                 # 回覆驗證器
```

---

## 3️⃣ 應用層 / 協調層 (Application/Coordination Layer)

**位置：** `doro_app/app.py`, `doro_app/ui/controllers/`

**職責：**
- 協調領域層和 UI 層
- 組裝依賴關係
- 處理用戶用例（Use Cases）

**組件：**

### 3a. 應用程式組裝根
```
doro_app/
└── app.py
    └── DoroApp                      # 應用程式入口和組裝根
```

### 3b. UI Controllers (連接 UI 和領域層)
```
doro_app/ui/controllers/
├── state_controller.py              # 狀態 → ViewModel
├── gif_controller.py                # GIF → ViewModel
├── dialog_manager.py                # 對話框管理
└── click_action_controller.py      # 點擊動作處理
```

---

## 4️⃣ UI 層 / 表現層 (Presentation/UI Layer)

**位置：** `doro_app/ui/`

**職責：**
- 視覺呈現
- 用戶互動
- UI 狀態管理

**子層結構：**

### 4a. UI 主視窗
```
doro_app/ui/
└── window.py (464行)
    └── DoroWindow                   # 主視窗 (Qt Widget)
```

### 4b. ViewModel (UI 數據層)
```
doro_app/ui/viewmodels/
└── doro_viewmodel.py
    └── DoroViewModel                # UI 狀態（顏色、動畫、可見性）
```

### 4c. 渲染引擎
```
doro_app/ui/rendering/
├── rendering_engine.py              # 繪製邏輯
├── design_tokens.py                 # 設計 tokens
└── fallback_sprite.py               # 後備精靈
```

### 4d. UI 組件
```
doro_app/ui/components/
├── bubble_controller.py             # 氣泡控制器
└── gif_player.py                    # GIF 播放器
```

### 4e. 對話框
```
doro_app/ui/dialogs/
├── chat_dialog.py                   # 聊天對話框
├── chat_settings_dialog.py          # 聊天設定對話框
├── state/
│   ├── manager_dialog.py            # 狀態管理對話框
│   ├── add_dialog.py                # 新增狀態對話框
│   └── gif_gallery_dialog.py        # GIF 畫廊對話框
└── move_state/
    ├── manager_dialog.py            # 動作管理對話框
    └── edit_dialog.py               # 編輯動作對話框
```

### 4f. 事件處理
```
doro_app/ui/events/
└── mouse_event_handler.py           # 滑鼠事件處理
```

### 4g. 佈局管理
```
doro_app/ui/layout/
└── layout_manager.py                # 視窗佈局管理
```

### 4h. 主題
```
doro_app/ui/theme/
├── theme.py                         # 主題管理
└── themed_menu.py                   # 主題化選單
```

---

## 5️⃣ 基礎設施層 (Infrastructure Layer)

**位置：** `doro_app/utils/`, `doro_app/constants.py`

**職責：**
- 提供通用工具
- 跨層的共用功能
- 技術性支援

**組件：**
```
doro_app/
├── utils/
│   ├── logger.py                    # 日誌系統
│   ├── paths.py                     # 路徑工具
│   ├── utils.py                     # 通用工具函數
│   ├── workers.py                   # 異步工作器
│   ├── actions.py                   # 動作解析
│   ├── prompts.py                   # Prompt 管理
│   ├── models.py                    # 通用模型
│   ├── config_manager.py            # 配置管理
│   ├── config_schema.py             # 配置結構定義
│   └── config_defaults.py           # 配置預設值
│
├── constants.py                     # 常數定義
└── core/exceptions.py               # 統一例外階層
```

---

## 📊 完整分層圖

```
┌─────────────────────────────────────────────────────────────────┐
│                    5️⃣ 基礎設施層                                 │
│                  (Logger, Paths, Utils)                         │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                              │ 被所有層使用
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     4️⃣ UI 層 / 表現層                             │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ DoroWindow (主視窗)                                     │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ ViewModel (UI 狀態)                                    │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ Components (Bubble, GifPlayer, etc.)                   │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ Dialogs (Chat, State Manager, etc.)                    │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ Rendering (Engine, Tokens)                             │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                              │ 通過 Controllers 連接
                              │
┌─────────────────────────────────────────────────────────────────┐
│                  3️⃣ 應用層 / 協調層                               │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ DoroApp (組裝根)                                        │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ UI Controllers (State, Gif, Dialog, Click)             │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                              │ 使用
                              │
┌─────────────────────────────────────────────────────────────────┐
│              2️⃣ 領域層 / 核心業務邏輯層                            │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Domain Models (State, MoveState, Transition)           │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ Domain Services                                        │    │
│  │   ├─ StateService (FSM)                               │    │
│  │   ├─ MovementManager                                  │    │
│  │   ├─ TransitionPlayer                                 │    │
│  │   └─ ChatOrchestrator                                 │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                              │ 使用
                              │
┌─────────────────────────────────────────────────────────────────┐
│                  1️⃣ 資料層 / 持久化層                             │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Repositories (State, MoveState, Transition, Gif)       │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ ConfigManager (配置管理)                               │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ File System (JSON, GIF files)                          │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 層與層之間的依賴方向

### 正確的依賴方向（由上到下）：
```
UI 層 (4)
  ↓ 依賴
應用層 (3)
  ↓ 依賴
領域層 (2)
  ↓ 依賴
資料層 (1)

基礎設施層 (5) ← 被所有層使用（橫向依賴）
```

### ⚠️ 目前的問題：
```
❌ UI 層 (Window) 直接依賴 領域層 (MovementManager, TransitionPlayer)
   → 應該通過 應用層 (Controllers/App) 連接

❌ 領域層 (TransitionPlayer) 依賴 UI 層 (DoroWindow)
   → 循環依賴！應該反轉依賴方向
```

---

## 📋 總結

### 你的專案有 **5 層**：

1. **資料層** - 持久化和檔案系統
2. **領域層** - 核心業務邏輯（State, Movement, Chat）
3. **應用層** - 協調和組裝（DoroApp, Controllers）
4. **UI 層** - 視覺呈現和互動（Window, ViewModel, Components）
5. **基礎設施層** - 通用工具（Logger, Utils）

### 目前的架構問題：

- ❌ 層與層的邊界不清晰
- ❌ Window 直接持有領域層組件（跨層依賴）
- ❌ 有循環依賴（UI ↔ 領域層）
- ❌ 應用層職責不明確

### 重構目標：

✅ 清晰的分層邊界
✅ 單向依賴（由上到下）
✅ 沒有循環依賴
✅ 每層職責明確
