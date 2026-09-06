# CLAUDE.md

## 功能地圖（改功能時先看這裡）

> 用詞約定：**功能**＝使用者會脫口而出想改的東西；**門**＝外面該從這裡進來的入口；
> **地雷**＝能動但是爛路、別照抄。畫法以「角色＋位置」為主，只有「門」和「地雷」點到精確檔案。

### 🌐 網頁（讀／搜尋／操作，分層做）
- 核心邏輯：`doro_app/core/web/`
- **第 1 層：讀** 已完成並接進聊天（貼網址→開真瀏覽器讀→交給聊天 AI 摘要／回答）。
- **第 3 層：操作** 已完成並接進聊天（點/填/翻頁；送出類先問你）。
  - 動作指令＋安全分級：`web_actions.py`（`parse_web_action`、`needs_confirmation`）。
  - 看→想→（問）→做 循環：`operator.py`（`WebOperator`，注入 session/ask_llm/confirm/emit，純邏輯好測）。
  - 觸發：**交給 LLM 判斷**——模型在一般聊天回覆吐 `[operate:目標]` 才啟動（`parse_operate_action` 在 `_on_request_succeeded` 攔）。不再用關鍵字硬觸發（避免「幫我點書籤」這種桌面動作被誤判；桌面/工具列點擊走 a11y 的 `[MOVE:to]+[mouse:click]`）。仍受**總開關**管（右鍵選單「讓 Doro 操作網頁」，`automation.web_operation_enabled`，預設關；關著時吐 [operate:] 會回友善提示）。區分規則寫在 `dia_prompt.txt`（目標在「這台電腦視窗/程式」→ mouse；在「網站/網頁裡」→ operate）。`parse_operate_command`（舊關鍵字版）保留但已不接線。
  - 確認（`needs_confirmation(action, names, page_context)`）：點到「送出/購買/刪除/登入…」名稱的按鈕、或點擊目標編號對不上 → 要問；**按 Enter 只在敏感頁（結帳/付款/登入，看 `_SENSITIVE_PAGE_MARKERS`）才問**，一般頁（搜尋/逛網頁）Enter 不問；goto/scroll/type/back 不問。回「好」才做；其餘（含模糊、300s 逾時）都當不做。中止：打「停/取消」，或關視窗。confirm 文字由 operator 組好、`_on_op_confirm` 照顯示。
  - **卡關接手續做**：碰到 CAPTCHA / 登入牆（`looks_like_captcha` / `looks_like_login_wall`）不再直接停，而是**暫停**用 confirm 問你「處理完回好我續做」→ 回「好」`continue` 重看頁面接著做、回「不要」放棄。收尾前提示詞要求誠實自檢、不准謊報成功。
  - **登入助手**：模型吐 `[login:網址]`（`parse_login_action`）→ `_begin_login` → `WebRuntime.submit_login`：只開站停著讓你本人登入（不操作），並 `_hold_open=True` 讓閒置不自動關；登入狀態存專屬設定檔。
- **共用瀏覽器 + 專屬執行緒**：`runtime.py`（`WebRuntime`）——一條專屬執行緒擁有唯一 `WebSession`，讀與操作都排隊走它（天生一次一個）；閒置 5 分鐘自動關；`op_confirm`/`provide_confirm` 用 Event 橋接「聊天打字確認」。**Playwright sync 綁執行緒，所有網頁動作都在這條執行緒**。
  - `app.py` 的 `_on_about_to_quit` 會呼叫 `orchestrator.shutdown_web()` 收掉。
  - 隔離：操作進行中 orchestrator 擋掉一般聊天/自動訊息（只收「好/不要/停」）；idle 看 `is_web_busy` 自動安靜；操作提示**不掛 a11y 前景樹**（`_operation_ask_llm` 自建 payload）。
- **第 2 層：查證** 已完成（`verify.py` 的 `VerifyPipeline`）：搜尋(Bing)→抓前幾個結果連結(`session.collect_links`+`pick_result_links`)→各讀一頁→把所有來源一起餵給 AI 比對→誠實回報（找不到就說找不到）。跳過需登入/驗證的來源。**read-only，不受操作總開關限制**。觸發＝模型吐 `[operate:]` 之外的 `[verify:問題]`（`parse_verify_action`，在 `_on_request_succeeded` 攔）。走 `WebRuntime.submit_verify`→`verify_progress`/`verify_finished` signal。查證/操作的 LLM 呼叫共用 `_web_llm(system_prompt, prompt)`（各自系統提示、不掛 a11y）。
- 兩條觸發路（都在 `doro_app/core/chat/orchestrator.py`，讀完共用 `_begin_web_read`）：
  1. **明確路**（快）：`send_message` 用 `parse_web_read_command` 抓「讀取動詞＋http 網址」，命中直接讀。
  2. **LLM 判斷路**（寬）：其它訊息照常送 LLM；模型想讀就在回覆吐 `[read:網址]`，
     `_on_request_succeeded` 用 `parse_read_action` 抓到就去讀。每輪最多自動讀一次（`_auto_read_used` 防迴圈）。
  讀完 → 背景 `WebReadWorker` → 把網頁內容＋原問題組成一則加料訊息丟回既有聊天流程作答。
- **讀「目前這頁」**（doro 自己操作/讀後還開著的頁，無網址）：`parse_read_current_command`（有「這頁/你剛開的頁」等 referent＋讀取意圖、且沒網址才算）→ `_begin_web_read_current` → `WebRuntime.submit_read_current`（不重新導航，直接 snapshot 目前頁）→ 一樣走 `_on_web_read_result`。
- 門（判斷指令 / 抓 [read:] 標記）：`parse_web_read_command`、`parse_read_current_command`、`parse_read_action` … `doro_app/core/web/intent.py`
- 門（實際開瀏覽器讀）：`WebPageReader` … `doro_app/core/web/reader.py`
- `[read:網址]` 標記要讓模型會用：指令寫在 `doro_app/core/chat/dia_prompt.txt`（跟 `[MOVE:]`/`[mouse:click]` 同一套動作標記慣例）。
- 需要 Playwright：`pip install playwright` + `playwright install chromium`（見 pyproject `web` extra）。
  沒裝也不會壞，只有真的叫它讀網頁時回安裝指引。
- doro 專屬瀏覽器設定檔（登入狀態留這、跟你平常 Chrome 分開）：`AppDataLocation/web_profile`。
- 規則：只有「明確讀取動詞＋http 網址」才攔截；純聊天不動。上網用你**當下設定的聊天模型**。

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
  （`bootstrap.py` 用它把內建的 `click`＋`dragged` 動作註冊好）
- **命名動作是一套「登記處」**：每個動作是 `actions.json` 裡一筆 `ActionEntry`（`key`＋`display_name`＋`gif_id`＋`is_builtin`＋`kind`）。`kind` 是分類種子（現有 `click`/`dragged`，未來可掛 `move`/`transition`）。每個動作背後掛一個**隱藏、受保護的顯示狀態**當「播放載體」（`click`→`click_action`、`dragged`→`dragged`；隱藏＝不進 States 選單、idle 也挑不到），對應表寫在 `service.py` 的 `_ACTION_STATE_KEYS`。綁 GIF 走 `bind_action_gif(key, path)`（`bind_click_gif` 是相容薄殼）。加一個新反應＝`repository.py` 補一個 builtin＋`_ACTION_STATE_KEYS` 加一列，不用新 UI。
- 資料夾內的房間（需要時才進去）：
  - `click_action.py`、`movement_action.py`：各種動作的組裝
  - `phases.py`：一個動作拆成「等待／視覺／效果」幾個階段
  - `repository.py`：`actions.json` 存檔＋內建動作（`click`/`dragged`）
  - `fakes.py`：測試用替身
- 點擊提示視窗：`doro_app/ui/click_warning_overlay.py`、`doro_app/ui/controllers/click_action_controller.py`
- **設定介面（門）**：右鍵選單 **Actions → Edit actions** 開的是 `MoveStateManagerDialog`（標題其實叫 "Action Manager"）… `doro_app/ui/dialogs/move_state/manager_dialog.py`。它是一個**卡片清單**，同時列 Movement／Transition／命名動作（click、拖曳），命名動作那段是 **registry 驅動**（迴圈 `ActionService.named_action_keys()`，不再寫死 click）。換 GIF 走 `edit_dialog.py` 的 action 模式（`bind_action_gif`）。

### 🫳 拖曳反應（被拖曳時播的 GIF）
- **功能**：抓著 Doro 拖動時播一段專屬 GIF，放開回原狀態。
- 它是一個**命名動作** `dragged`（不是 state、不是 movement），走上面「點擊互動」的登記處那套；素材預設放 `doro_app/res/drag/`，開機首次 `ActionService._seed_drag_defaults()` 把裡面的 `.webp/.gif/.apng` 種進 `dragged` 狀態的 GIF 池（多檔＝隨機播；使用者改過就不覆蓋）。
- **觸發／收尾（門）**：`doro_app/ui/events/mouse_event_handler.py` 的 `drag_started`／`drag_ended` 兩個信號 → `app.py` 的 `_on_doro_dragged`（記下拖曳前狀態＋`request_state("dragged", force=True)`）與 `_on_drag_ended`（還原；拖曳前是走路類或就是 dragged→回 `idle`）。`drag_ended` 只在真的拖曳後發、單純點擊不發。
- **設定**：右鍵 Actions → Edit actions → 「拖曳」卡換 GIF（跟 click 同一個 Action Manager）。
- 地雷：`app.py` 的 `_on_doro_dragged` 除了播 GIF 還負責**取消進行中的走路／排隊點擊**（拖動時原有行為），別把那段刪掉。

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
