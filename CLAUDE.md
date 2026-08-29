# CLAUDE.md

## 功能地圖（改功能時先看這裡）

> 用詞約定：**功能**＝使用者會脫口而出想改的東西；**門**＝外面該從這裡進來的入口；
> **地雷**＝能動但是爛路、別照抄。畫法以「角色＋位置」為主，只有「門」和「地雷」點到精確檔案。

### 🗨️ 聊天
- 核心邏輯：`doro_app/core/chat/`
- 門 1（GUI 用）：`ChatOrchestrator` … `doro_app/core/chat/orchestrator.py`
- 門 2（無畫面 / CLI / 背景用）：`perform_chat_request` … `doro_app/core/chat/chat.py`
- 設定的門：`orchestrator.settings`（一個 `ChatSettings` 物件）。

### 🚶 移動 / 走路
- 核心邏輯：`doro_app/core/movement/`
- 門（唯一）：`MovementManager` … `doro_app/core/movement/manager.py`

### 🎭 換裝 / 狀態
- 核心邏輯：`doro_app/core/state/`
- 門（唯一）：`StateService` … `doro_app/core/state/service.py`
- 資料型別：`models.py`（`State` / `MoveState` / `Transition` / collections）
- 轉場：`transition_coordinator.py`、`transition_player.py`
- 精靈檔是 **QMovie 動態圖**：`.gif` / `.apng` / `.webp`。WebP 不是第二套 renderer。
- 狀態 key 統一走 `normalize_state_key()`（strip + lowercase）。
- 重構計畫：`docs/state-refactor-plan.md`

### 🖱️ 點擊互動
- 門 1：`ActionDispatcher` … `doro_app/core/action/dispatcher.py`
- 門 2：`ActionService` … `doro_app/core/action/service.py`

### 🤖 自動化 / 前景追蹤
- 門（唯一）：`AutomationManager` … `doro_app/core/automation/manager.py`
