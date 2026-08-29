# CLAUDE.md

## 功能地圖（改功能時先看這裡）

> 用詞約定：**功能**＝使用者會脫口而出想改的東西；**門**＝外面該從這裡進來的入口；
> **地雷**＝能動但是爛路、別照抄。畫法以「角色＋位置」為主，只有「門」和「地雷」點到精確檔案。

### 🗨️ 聊天
- 核心邏輯：`doro_app/core/chat/`
- 門 1（GUI 用）：`ChatOrchestrator` … `doro_app/core/chat/orchestrator.py`
- 門 2（無畫面 / CLI / 背景用）：`perform_chat_request` … `doro_app/core/chat/chat.py`
- 資料夾內的房間（需要時才進去）：
  - `controller.py`：設定、對話歷史、發問流程
  - `retry.py`：連線失敗重試
  - `settings.py`：聊天設定值
  - `validator.py`：AI 回覆內容檢查
- 對話視窗：`doro_app/ui/dialogs/chat_dialog.py`、`chat_settings_dialog.py`
- 背景送請求：`doro_app/utils/workers.py`
- 設定的門：`orchestrator.settings`（一個 `ChatSettings` 物件）。要改「聊天設定怎麼讀寫、
  存去哪」就找 `doro_app/core/chat/settings.py`；UI 那邊 `chat_ui_helper.py` 走的就是它的
  公開方法，是正確用法。

### 🚶 移動 / 走路
- 核心邏輯：`doro_app/core/movement/`
- 門（唯一）：`MovementManager` … `doro_app/core/movement/manager.py`
  （`app.py` 建它、`chat`／`idle_behavior_manager` 都拿它來叫 Doro 走路）
- 資料夾內的房間（需要時才進去）：
  - `repository.py`：記住目標位置、走到哪
  - `parser.py`：解析「移動到某處」的指令
  - `port.py`：對外接口定義
  - `fakes.py`：測試用替身
- 編輯移動狀態的視窗：`doro_app/ui/dialogs/move_state/`

### 🎭 換裝 / 狀態
- 核心邏輯：`doro_app/core/state/`
- 門（唯一）：`StateService` … `doro_app/core/state/service.py`
  （所有人換裝、切狀態都走它；`bootstrap.py` 負責把下面的 repository 組進它）
- 資料夾內的房間（需要時才進去）：
  - `repository.py`：狀態、GIF、轉場的存檔讀寫
  - `models.py`：狀態的資料格式
  - `state_parser.py`：解析狀態設定檔
  - `transition_coordinator.py`、`transition_player.py`：換裝動畫的排程與播放
- 換裝／GIF 管理視窗：`doro_app/ui/dialogs/state/`
- 精靈檔是 QMovie 動態圖（`.gif` / `.apng` / `.webp`），不是第二套 renderer。
- 狀態 key 統一 `normalize_state_key()`（strip + lowercase）。重構計畫：`docs/state-refactor-plan.md`。
- 小提醒：`__init__.py` 對外公開了較多名字（service＋models＋repository）。真正的「門」是
  `StateService`；models（`State`、`Transition`…）是外面 UI 真的會用到的資料型別，repository
  則是 `bootstrap.py` 組裝時要用的——所以不是亂公開，只是入口沒被特別標出來。找功能時認準
  `StateService` 就對了。

### 🖱️ 點擊互動
- 核心邏輯：`doro_app/core/action/`
- 門 1（執行時派工用）：`ActionDispatcher` … `doro_app/core/action/dispatcher.py`
  （`app.py`／`chat`／`idle_behavior_manager` 用它觸發點擊等動作）
- 門 2（開機註冊用）：`ActionService` … `doro_app/core/action/service.py`
  （`bootstrap.py` 用它把內建的 `click` 動作註冊好）
- 資料夾內的房間（需要時才進去）：
  - `click_action.py`、`movement_action.py`：各種動作的組裝
  - `phases.py`：一個動作拆成「等待／視覺／效果」幾個階段
  - `repository.py`：`actions.json` 存檔
  - `fakes.py`：測試用替身
- 點擊提示視窗：`doro_app/ui/click_warning_overlay.py`、`doro_app/ui/controllers/click_action_controller.py`

### 🤖 自動化 / 前景追蹤
- 核心邏輯：`doro_app/core/automation/`
- 門（唯一）：`AutomationManager` … `doro_app/core/automation/manager.py`
  （`app.py` 在 pynput 可用時才建它；受白名單＋安全鎖限制，見檔案開頭說明）
- 資料夾內的房間（需要時才進去）：
  - `parser.py`：解析 `[mouse:click]` 這類指令
  - `foreground_tracker.py`、`window_class.py`：追蹤目前前景視窗
  - `coordinates.py`：座標換算
  - `port.py`、`backend_pynput.py`：對外接口與實際輸入後端
  - `fakes.py`：測試用替身
