# 功能細節導覽（按任務選讀）

先用 [repo 地圖](../REPO_MAP.md) 定位。此頁保留既有功能說明；不必每次整頁載入。
所有程式路徑以 repository 根目錄為基準。

## 功能地圖（改功能時先看這裡）

### Doro 被點擊的 ACTION
- 設定入口：動作管理的 `pet_click` 卡片「Doro 被點擊時的反應」，可選擇或清除 GIF／APNG／WebP；沒有素材時保留目前外觀。
- 與 `click`（Doro 幫忙點畫面的 wind-up）獨立儲存。舊 actions.json 由 ActionRepository 自動補上 pet_click，不覆蓋既有 click 綁定。
- 實際事件：MouseEventHandler.click_detected → DoroApp._on_doro_clicked → SpriteController.start_pet_click_animation。這是暫時手勢覆蓋，不切永久狀態、不呼叫桌面自動化；原 click.txt 聊天仍可另外觸發。
- 動畫播一次後恢復最新正常／轉場素材，連續點擊重新播放，拖曳會取消。靜態圖顯示 400ms；異常播放最多 30 秒後清理。
- CoreManager.on_user_clicked／ReactionCatalog 的舊 click 時間軸不是目前 GUI 的點擊接線，不應將它與桌面 click_action 混用。
- 回歸測試：tests/ui/components/test_pet_click_animation.py，涵蓋儲存、編輯、實際手勢、動畫生命週期及缺少素材。

### 拖曳動畫
- 入口：`ui/events/mouse_event_handler.py` 以螢幕座標判斷拖曳，發出 `drag_started`／`drag_finished`。
- `app.py` 先取消移動及待執行點擊，再從 `res/drag/` 選動畫；`SpriteController` 透過暫時的 renderer movie 播放。
- 這是手勢期間的顯示覆蓋，不寫入永久狀態；放開、失去抓取、視窗停用或隱藏後，恢復最新的正常／轉場素材。
- 拖曳期間不啟動閒置動作或分頁主動回應。素材缺失時保留原角色，視窗仍可拖曳。
- 回歸測試：`tests/ui/components/test_drag_animation.py`，包含真實 WebP 影格播放。

> 用詞約定：**功能**＝使用者會脫口而出想改的東西；**門**＝外面該從這裡進來的入口；
> **地雷**＝能動但是爛路、別照抄。畫法以「角色＋位置」為主，只有「門」和「地雷」點到精確檔案。

### 🌐 指令上網與分頁陪伴
- 語彙：`CONTEXT.md`；架構與取捨：`docs/adr/`；安裝驗收：`docs/web-presence-setup.md`。
- **指令上網**：`doro_app/core/web/`，門為 `WebRuntime`（專屬執行緒及共用 Playwright session）。
  - 聊天回覆的 `tool` 欄位決定要不要上網（ADR 0005，結構在 `chat/chat_reply.py`）。
  - `read`：讀完回既有聊天流程；頁面回答的結構沒有 `tool`，只允許角色表現，不再觸發其他工具。
  - `verify`：搜尋 → 開最多三個來源頁給使用者看 → 每開一頁就讀一頁 → 比對。單頁失敗不中斷；未讀正文的搜尋文字一律帶摘要標記。Tavily / ddgs 在 `search_providers.py`。
  - `operate`：`WebOperator` 的看→想→確認→做循環，每一步是嚴格驗證的 `WebStep`；受操作總開關限制。`needs_confirmation` 根據名稱、表單屬性及焦點判斷。Enter 只有明確搜尋框才免問，複合／未知按鍵、未知按鈕、表單送出會問。
  - `login`：只開站給使用者本人登入。密碼／驗證碼不讀值、不代填。
  - 取消在模型返回後及真正執行前檢查。已送到瀏覽器的單次動作不能追回。
- **回覆與角色動作**：模型回覆都經 `core/llm` 驗證成結構（ADR 0005）。門為 `ChatOrchestrator.present_structured_reply`（純文字台詞走 `present_character_reply`）。讀頁／查證答覆與存在感的結構只有合法狀態及一個方向型 `move`，沒有 `tool`；生產環境先走再說。
- **你正在看的分頁／存在感**：`extensions/doro-presence/` → `core/presence/bridge.py` → `PresenceController`。App 是 loopback WS server，token＋精確 extension Origin 配對；擴充只讀 active＋visible＋focused 分頁。設定入口為聊天子選單的「分頁陪伴設定」。
  - 明講「你剛開的頁」讀 Doro 分頁；分享啟用後「這頁」取擴充目前頁，沒有有效來源就說明，不混用。
  - 基本活潑仍走 `IdleBehaviorManager`；情境活潑由頁面事件觸發。同內容本機去重、模型以 `worth_saying` 做開口判斷（ADR 0005），忙時保留最新頁，過時答案丟棄，失敗降級但下一事件可恢復。
  - 兩端預設停用；不分享輸入框或編輯內容，不提供擴充 click/type 入口。
- 依賴：`pip install -e ".[web]"`，指令上網另需 `playwright install chromium`。缺少可選依賴不影響一般桌寵。
- App 關閉會收掉 WebRuntime 和 PresenceController。語彙表不放這些實作細節。

### 🗨️ 聊天
- 核心邏輯：`doro_app/core/chat/`
- 門 1（GUI 用）：`ChatOrchestrator` … `doro_app/core/chat/orchestrator.py`
- 門 2（無畫面 / CLI / 背景用）：`ask_structured` … `doro_app/core/llm/structured.py`（純文字呼叫仍有 `perform_chat_request`）
- 資料夾內的房間（需要時才進去）：
  - `controller.py`：設定、對話歷史（存完整結構化回覆）、發問流程
  - `chat_reply.py`：聊天回覆結構（含 `tool`）與任務說明
  - `settings.py`：聊天設定值
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
