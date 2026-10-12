# Doro 心跳 v1：改動目標與驗收紀錄

對應 [Open Claw TODO](TODO_OPEN_CLAW.md) 柱子 ③。規格由 2026-10-08 的 grill 討論（Q1～Q18）釘定；本文件分四段：**改動目標**（要做成什麼樣）、**驗收清單**（我與他人如何確認）、**修改紀錄**（實際動了什麼、驗證結果）、**後續討論與待決事項**（實作後的問答與尚未決定的方向）。

狀態：v1 已實作，自動驗證通過；人工體驗項目待使用者在 Windows 實機確認（規格基準 `034c638`）。

## 總覽（先讀這段）

**目的**：讓 Doro 像 OpenClaw 的 heartbeat 一樣，每隔一段時間自己醒來，看看時間、最近的聊天與使用者寫的心跳清單，再決定要不要主動說一句話。不接 Node.js／OpenClaw，用 Doro 自己的 Qt 計時器與既有的結構化回覆實作。

**做了什麼**

| 項目 | 內容 |
| --- | --- |
| 新模組 | `doro_app/core/heartbeat/`：排程與跳過規則（`controller.py`）、清單／日誌／提示詞（`context.py`）、Windows 系統閒置偵測（`system_idle.py`） |
| 模型請求 | `ChatOrchestrator.make_heartbeat_request`，回覆結構 `HeartbeatReply` 只有 `worth_saying`／`state`／`line`／`move`，沒有 `tool` |
| 介面 | 「陪伴設定… → 心跳」分頁（開關、間隔、編輯心跳清單）；右鍵「立刻跳一次心跳」 |
| 設定 | `heartbeat_enabled`（預設關）、`heartbeat_interval_minutes`（預設 30，1～1440） |
| 文件 | ADR 0006、README、CONTEXT 語彙、FEATURE_GUIDE、repo 地圖、INDEX、TODO_OPEN_CLAW |
| 測試 | 新增 56 個（1120 → 1176 passed），含真實 `DoroApp` 組裝測試與 5 項審查問題的回歸測試 |

**每次心跳做什麼**：檢查跳過規則 → 組「現況」（時間、互動間隔、最近聊天、清單、心跳日誌、分享頁標題）→ 模型回 `HeartbeatReply` → 不開口就只記日誌；開口就照角色回覆走路／換姿勢／說話並記日誌；期間使用者送出聊天、拖曳或切安靜模式則作廢。

**刻意不做**：上網、操作電腦、執行指令、MCP、cron、長期記憶（記在 TODO_OPEN_CLAW）。

**待你決定**：既有待機（`IdleBehaviorManager`）與心跳的分工，見第四段「待決 1」。

## 一、改動目標

### 定位

- 新增第三層「定時自主層」：每隔一段時間叫醒模型，讓 Doro 自己判斷要不要主動說話或做動作。概念借自 OpenClaw heartbeat（排程器到點送提示詞，模型沒事回 `NO_REPLY`）。
- 不取代既有兩層（ADR 0002）：
  - 基本活潑 `IdleBehaviorManager`：隨機小動作，不呼叫模型，維持原樣。
  - 分頁陪伴 `PresenceController`：分頁事件觸發、只讀，維持原樣。心跳只把目前分享頁的**標題**當參考資料。
- 不使用 Node.js 或 OpenClaw Gateway；Doro 的 Qt 事件迴圈＋`QTimer` 就是自己的排程器。

### 什麼時候跳

- 預設**關閉**；「陪伴設定」加勾選與間隔欄位，間隔預設 30 分鐘，可調。
- 下列任一情況跳過本次心跳、不呼叫模型：
  - 安靜模式或「我先忙」。
  - 正在聊天、拖曳、開選單或有尚未結束的動作。
  - 上一次心跳的模型請求還沒回來（同時最多一個）。
  - 最近 1～2 分鐘內跟 Doro 有互動（人就在旁邊，不需要主動）。
  - 系統閒置超過約 10 分鐘（人不在電腦前）。Windows 讀系統閒置時間；其他平台退回只看 Doro 互動。

### 醒來時給模型的資料

1. 現在時間與星期。
2. 距離上次和 Doro 互動多久。
3. 最近幾則聊天紀錄。
4. **心跳清單**：使用者可編輯的純文字檔，放在 Doro 使用者設定資料夾；陪伴設定加「編輯心跳清單…」按鈕以系統預設編輯器開啟；第一次使用自動寫入範例。
5. **心跳日誌**：最近幾次心跳的時間與 Doro 說過的話，跨重啟保留，只記 Doro 自己的輸出，用來避免重複。
6. 有有效分享分頁時，附目前頁面標題。

### 模型能做什麼

- 只做角色表現：台詞、已知狀態、四方向移動（沿用 ADR 0004 的限制）。
- 回覆格式沿用 ADR 0005 的結構化回覆，但使用**沒有 `tool` 欄位的子集**——在格式層面就寫不出上網或操作指令。
- 沒事回 `[SILENT]`：畫面不顯示，只寫 log 與心跳日誌。
- 提示詞：既有人設（`dia_prompt.txt`）＋心跳任務說明（寧可安靜、不重複上次心跳的話、依清單判斷）。
- 有台詞時走既有角色表現入口 `present_character_reply`；換頁、使用者開始發問或進入安靜模式後，過時結果不得發言。

### 測試與手動體驗

- 單元測試用假計時器與假模型，不花 API 費用。
- 右鍵選單加「立刻跳一次心跳」；手動觸發同樣遵守跳過規則。

### 文件

- 新增 `docs/adr/0006`：記錄心跳決策與考慮過的其他選項（MCP、先做記憶、提示詞限制工具等）。
- 依 `AGENTS.md` 更新 `docs/ai/areas.json`、`python scripts/repo_map.py --write`、`docs/INDEX.md`。
- 完成後在 `TODO_OPEN_CLAW.md` 把柱子 ③ 標為 v1 完成並連到 ADR 0006。

### 這次不做（已記入 TODO）

MCP、定時提醒（cron）、長期記憶、執行腳本或指令、使用者回到電腦前主動打招呼、話量滑桿、心跳紀錄視窗。詳見 [TODO_OPEN_CLAW.md](TODO_OPEN_CLAW.md) 的「心跳 v1 延後項目」。

## 二、驗收清單

自動驗證（每項應有對應測試）：

- [x] 心跳預設關閉；開啟後依設定間隔排程，修改間隔後重新計時，取消不生效。
- [x] 安靜模式、「我先忙」、聊天／拖曳／選單／動作進行中、上次請求未回、最近互動、系統閒置過久，各自跳過且不呼叫模型。
- [x] 送給模型的內容包含時間、互動間隔、最近聊天、心跳清單、心跳日誌；有有效分享頁時含標題，沒有時不含。
- [x] 心跳回覆的結構沒有 `tool` 欄位；模型硬塞工具內容也不會觸發讀頁、查證、登入或操作。
- [x] `[SILENT]` 不顯示泡泡、不移動，只寫 log／日誌。
- [x] 有台詞時經 `present_character_reply` 顯示；狀態不合法時不換狀態。
- [x] 等待模型期間使用者開始發問或切到安靜模式，回來的結果不發言。
- [x] 心跳日誌跨重啟保留、只保留最近幾筆；清單檔不存在時自動建立範例。
- [x] 手動「立刻跳一次心跳」遵守安靜、忙碌與一次一個；略過開關、近期互動與系統閒置（見修改紀錄第 2 點）。
- [x] 完整離屏測試、Black／Ruff、`repo_map.py --check`、`git diff --check` 通過。

人工體驗（需實機，自動測試無法取代）：

- [ ] 陪伴設定能開啟心跳、改間隔、按「編輯心跳清單…」開到檔案。
- [ ] 清單寫「現在是深夜就提醒我睡覺」，深夜手動觸發時 Doro 有相應反應；白天觸發多半保持安靜。
- [ ] 連續手動觸發數次，Doro 不重複同一句話。
- [ ] 離開電腦超過 10 分鐘，log 顯示心跳因閒置跳過。

## 三、修改紀錄

實作時逐次補上：日期、基準 commit、改了哪些檔案、驗證命令與結果、未做或與目標不同之處。

### 2026-10-08：心跳 v1（基準 `1e7ed06`，規格文件 commit）

**新增檔案**

| 檔案 | 內容 |
| --- | --- |
| `doro_app/core/heartbeat/controller.py` | `HeartbeatController`：`QTimer` 排程、跳過規則、背景模型請求（一次一個）、忙碌時等待發言、過時失效、手動觸發 `beat_now`。 |
| `doro_app/core/heartbeat/context.py` | 心跳清單（建立範例、去掉 `#` 說明行、2000 字上限）、心跳日誌（最近 8 筆、原子寫入）、組提示詞。純函式，不依賴 Qt。 |
| `doro_app/core/heartbeat/system_idle.py` | Windows `GetLastInputInfo` 讀系統閒置秒數；其他平台回 `None`。 |
| `docs/adr/0006-timed-heartbeat.md` | 心跳決策、考慮過的選項與限制。 |
| `tests/core/heartbeat/test_heartbeat_context.py`、`test_heartbeat_controller.py` | 清單、日誌、提示詞、排程、各跳過規則、沉默、發言、過時、等待、逾期、失敗、手動觸發。 |
| `tests/core/chat/test_heartbeat_request.py` | 結構沒有 `tool`、硬塞的 `tool` 被丟掉、沉默回覆合法、聊天紀錄只取 Doro 的台詞。 |
| `tests/ui/test_heartbeat_app.py` | 在真實 `DoroApp` 組裝中驗證選單項目、設定重排程、失效接線與手動心跳發言＋日誌。 |

**修改檔案**

| 檔案 | 改了什麼 |
| --- | --- |
| `doro_app/core/chat/orchestrator.py` | 新增 `_HEARTBEAT_TASK`、`make_heartbeat_request`（`HeartbeatReply`，無 `tool`）、`recent_chat_lines`。 |
| `doro_app/core/chat/controller.py` | 新增 `recent_history(limit)`（回傳複本）。 |
| `doro_app/utils/config_schema.py`、`config_manager.py` | `UIConfig.heartbeat_enabled`（預設 False）、`heartbeat_interval_minutes`（預設 30，1～1440）；讀寫與無效值回預設。 |
| `doro_app/ui/dialogs/companion_dialog.py` | 「陪伴設定」新增「心跳」分頁：開關、間隔、「編輯心跳清單…」。 |
| `doro_app/ui/theme/themed_menu.py`、`ui/components/context_menu_controller.py` | 右鍵「立刻跳一次心跳」（等選單關閉後才觸發）。 |
| `doro_app/app.py` | 組裝 `HeartbeatController`；接上失效、設定重排程、關閉。 |
| `README.md`、`CONTEXT.md`、`docs/ai/FEATURE_GUIDE.md`、`docs/ai/areas.json`、`docs/REPO_MAP.md`、`docs/INDEX.md`、`docs/TODO_OPEN_CLAW.md` | 使用說明、語彙、功能導覽、地圖、索引與 TODO 狀態。 |

**與目標不同之處（請驗收時特別看）**

1. **沉默不是 `[SILENT]` 字串**：沿用現有結構化格式的 `worth_saying=false`（分頁陪伴已在用）。效果相同，但不用另外解析字串。
2. **手動觸發會略過三項檢查**：目標寫「手動觸發同樣遵守跳過規則」，但按選單的當下一定「剛剛互動過」，照規則會永遠跳過。因此手動觸發略過「心跳開關」「90 秒內互動」「系統閒置」，仍遵守安靜陪伴、忙碌與一次一個。跳過或沉默時用泡泡說明原因。
3. **聊天輸入列取得焦點不讓心跳失效**：實機測試發現選單關閉後焦點回到輸入列，心跳結果就被當成「有互動」丟掉。改成輸入列焦點只算忙碌（延後），真的送出聊天才失效。已加回歸測試。
4. **補上的細節數值**：「最近互動」為 90 秒、「人不在」為系統閒置 600 秒、聊天取最近 6 則、日誌保留 8 筆、忙碌造成的跳過 20 秒後重試、等待發言最多 120 秒。都寫在 `controller.py`／`context.py` 開頭的常數，可直接調整。
5. **檔案位置**：`heartbeat.md` 和 `heartbeat_journal.json` 放在 `presence.json` 同一個 Doro 使用者資料夾（Windows 通常是 `%APPDATA%` 底下的 Doro 資料夾）。

**驗證**

- `QT_QPA_PLATFORM=offscreen python -m pytest tests --ignore=tests/manual -o addopts= -q`：**1164 passed、3 skipped**（實作前為 1120 passed）。
- `black --check doro_app tests`、`ruff check doro_app tests`、`python scripts/repo_map.py --check`、`git diff --check`：通過。
- 離屏實際啟動 `DoroApp`（假模型伺服器）：預設不排程；手動心跳送出 `HeartbeatReply` 結構、提示詞含清單、Doro 說出台詞並寫入日誌；安靜模式時泡泡顯示「心跳先跳過：安靜陪伴中」；開啟並設 5 分鐘後計時器為 300000 ms。

**未驗證**：Windows 實機的系統閒置偵測、真實模型的開口品質、「編輯心跳清單…」在 Windows 開啟記事本。請依上方「人工體驗」清單確認。

### 2026-10-10：審查修正（基準 `f8bb4ab`）

外部審查以額外測試重現 5 個問題，主要是「心跳回覆過時後仍發言」。全部修正，每項各有回歸測試。

| # | 問題 | 修正 | 回歸測試 |
| --- | --- | --- | --- |
| 1 | 只聽 `ChatController.request_started`；分頁提問等提前返回的路徑不發此訊號，舊心跳仍會蓋掉泡泡 | `ChatOrchestrator` 新增 `user_message_accepted`，在使用者訊息被接受的共同入口發出（一般聊天、分頁提問、網頁指令、操作中的確認），心跳改接這個訊號；自動訊息與被拒絕的訊息不發 | `test_page_question_announces_accepted_user_message`、`test_auto_and_rejected_messages_are_not_announced`、`test_heartbeat_app.py`（真的送出分頁提問） |
| 2 | 只比對互動版本，換頁後仍會評論上一個分頁 | 心跳記下送出時的分頁；結果回來、等待忙碌期間、真正發言前都比對目前分頁，不同（含已無分頁）就丟棄。送出時沒有分頁的心跳，之後出現分頁仍可發言 | `test_page_change_while_waiting_drops_reply`（換到 B／無分頁）、`test_page_change_while_reply_waits_for_busy_drops_it`、`test_beat_without_page_is_not_dropped_when_a_page_appears` |
| 3 | 忙碌判斷沒含泡泡，會蓋掉待機或分頁陪伴的台詞 | `app.py` 的心跳忙碌條件加上 `bubble_controller.text`；沿用 120 秒等待期限，逾時丟棄 | `test_heartbeat_app.py`（顯示待機台詞時心跳為忙碌） |
| 4 | 先顯示失敗訊息才檢查過時，切到安靜模式後仍冒出「沒有拿到模型回覆」 | `_on_result` 先統一檢查過時（關閉／互動／安靜／換頁），再處理成功、沉默或失敗 | `test_failed_manual_beat_respects_cancel_and_quiet`（安靜／中斷）、`test_silent_manual_beat_after_quiet_says_nothing` |
| 5 | 清單固定 UTF-8 且只捕捉 `OSError`，Big5／ANSI 存檔會拋出 `UnicodeDecodeError` 離開 Qt 回呼 | 以 `utf-8-sig` 讀取（接受記事本 BOM）；解碼失敗拋 `ChecklistUnreadable`，心跳視為跳過原因「心跳清單不是 UTF-8 編碼，請用 UTF-8 重新存檔」，手動觸發時以泡泡提示 | `test_checklist_saved_as_big5_raises_a_clear_error`、`test_checklist_with_utf8_bom_is_read`、`test_non_utf8_checklist_skips_instead_of_raising` |

**其他改動**：`HeartbeatController` 的 `page_title` 參數改為 `page`（目前分享頁物件，標題取自其 `title`）；`tests/core/chat/test_presence_ask_path.py` 的半初始化 orchestrator 補上 `QObject.__init__`，因為 `send_message` 現在會發訊號。ADR 0006、FEATURE_GUIDE、README 同步更新。

**驗證**：完整離屏測試 **1176 passed、3 skipped**；Black、Ruff、repo map、`git diff --check` 通過。把 `doro_app/` 改動暫存後用舊程式跑新測試，#1 的三個測試失敗（含 App 組裝測試 `assert 0 == (0 + 1)`），還原後通過。#2、#4、#5 的測試使用新介面（`page=`、`ChecklistUnreadable`），無法直接在舊程式上執行。離屏實際啟動 `DoroApp` 再跑一次手動心跳流程，結果與先前相同。

**仍未處理**（審查也提到）：待機與心跳的發話冷卻未共享，見第四段「待決 1」。Windows 閒置偵測、實機開啟清單與真實模型品質仍待人工驗證。

### 2026-10-10：合併 master（PR #64 素材工廠）

- 衝突三處，皆為兩邊在同一位置各加一行：`MenuCallbacks` 與 `ContextMenuController` 同時保留 `heartbeat_now` 與 `show_asset_factory`；`docs/REPO_MAP.md` 由 `repo_map.py --write` 重新產生（`areas.json` 自動合併出 `heartbeat` 與 `factory` 兩區）。
- 驗證：安裝 `.[dev,web,factory,factory-ai]` 後完整離屏測試 **1233 passed、3 skipped**；Black、Ruff、repo map 通過。
- 備註：只裝 `factory` 而未裝 `factory-ai`（`rembg`）時，`tests/gif_factory` 有 3 個測試因 `ModuleNotFoundError: rembg` 失敗；在未合併的 master 上同樣失敗，與本分支無關。

### 2026-10-12：再次合併 master（PR #67、#68 動作控制與點擊／拖曳 GIF）

- 程式碼自動合併，沒有衝突；只有自動產生的 `docs/REPO_MAP.md` 衝突，以 `repo_map.py --write` 重新產生。
- 驗證：完整離屏測試 **1257 passed、3 skipped**（含心跳的 App 組裝測試，確認右鍵選單仍有「立刻跳一次心跳」）；Black、Ruff、repo map、`git diff --check` 通過。

## 四、後續討論與待決事項

v1 完成後的問答整理（2026-10-10）。這段記錄理解與方向，不代表已實作。

### 心跳和 OpenClaw 的差別

- OpenClaw 的心跳本身也只是「排程器到點送提示詞給模型」；它看起來「每次都在做事」，是因為醒來後手上有工具（`exec`、讀寫檔案、瀏覽器、MCP、新增排程、寫記憶）並能多步執行（agent 迴圈），結果推播到聊天軟體。其預設提示詞同樣保守，沒事回 `NO_REPLY`。
- Doro v1 只做了「定時叫醒＋開口判斷」這一半；「醒來動手做事」需要工具與 agent 迴圈（TODO 柱子 ①），依 grill Q2 刻意延後。
- 若往那個方向走，建議順序：① 唯讀工具（行事曆、天氣、讀網頁；心跳專屬白名單）→ ② agent 迴圈（安全閘同步建立）→ ③ 會改東西的動作（需核准與沙箱）。

### 會自己做事時仍保持結構化

- 會。沿用 ADR 0005 的兩種回覆：**角色回覆**寬容（壞欄位丟掉、照樣說話），**工具決策**嚴格（不合格重問一次，仍不合格就停止、不執行）。既有的網站操作 `operate` 就是每一步嚴格驗證 `WebStep` 的多步迴圈，可作範本。
- 結構化保證「程式看得懂、白名單外的工具寫不出來、格式壞了會停」；不保證「判斷正確」與「不被 prompt injection 誘導」，危險動作仍須白名單與先問使用者。

### 心跳與既有待機的關係（目前行為）

- 待機 `IdleBehaviorManager` 未修改：約每 9 秒散步、換自主姿勢、小動作、說 `companion.txt` 預寫台詞（至少隔 90 秒），不呼叫模型。
- 互相避讓：待機動作中，心跳算忙碌而延後；心跳泡泡顯示時，待機暫停；安靜模式兩者都停；待機的自主活動不算「使用者互動」。
- **已知缺口**：待機的 90 秒發話冷卻不知道心跳剛說過話，心跳泡泡消失後待機可能很快接一句不相干的預寫台詞。

### 待決 1：待機與心跳的分工

使用者提出「讓待機消失、由心跳取代活潑」。評估：

| 選項 | 內容 | 評估 |
| --- | --- | --- |
| A | 兩者都留，只修上述搶話缺口（心跳開口時重設待機的發話冷卻） | 改動最小；待機仍說隨機台詞 |
| **B（建議）** | 待機只負責「動」（散步、姿勢、小動作），不再說預寫台詞；「說」交給心跳。心跳未開或模型不可用時，待機恢復預寫台詞作為後備 | 說話都有情境，成本與現在相近，不用網路也照樣會動 |
| C | 心跳當「大腦」：每次決定接下來的狀態（例如想睡／有精神），待機當「身體」照該狀態調整活動 | 最有生命感，需另開 grill 定義狀態與介面 |
| D | 完全移除待機 | 不建議：心跳間隔內角色靜止；調快心跳等於每幾秒一次模型請求（每 9 秒約每小時 400 次），延遲數秒，斷網即全停；也違反 ADR 0002「兩層不能互相取代」 |

狀態：**尚未決定**。選 B 時的預定改動：待機加「心跳開啟且模型可用時不說預寫台詞」條件、補測試、更新 ADR 0006／README 與本文件修改紀錄。

### 待決 2：下一個能力

若要讓心跳「醒來做事」，先決定最希望它**看**什麼（行事曆、信箱、網站、天氣…），再開 grill 定唯讀工具的規格。
