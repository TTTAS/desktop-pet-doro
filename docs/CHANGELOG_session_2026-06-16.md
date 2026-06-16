# 改動紀錄 - 2026-06-16

## 📋 本次 Session 完成項目

### 1. ✅ 點擊紅框 silent-skip 診斷與 stdout 升級

**症狀：**

使用者確認 Chrome 點擊在 5d6b043（area-based DFS）後真的成立，但接著問：「之前點的時候有紅框、現在沒看到，是被刪了嗎？」

**調查：**

逐檔讀過整條鏈，紅框 code 完全沒被動：

- `doro_app/ui/click_warning_overlay.py` 還在，`paintEvent` 也在畫。
- `doro_app/core/automation/manager.py:292-297` wind-up 起手依然會 `self._warning_overlay.begin(bounds)`。
- `doro_app/app.py:590-595, 786-807` 還在把 `ClickWarningOverlay` 包成 `_QtClickWarningOverlayAdapter` 給 manager。
- 最近一筆動 overlay 的 commit 是 `0be4434`（2025-05 底，revert element-id）。本 session 的 5 筆 commit（`5d6b043` / `5bc254e` / `504340f` / `8501e43` / `ac6f3bf`）通通沒碰 overlay 或 bounds_provider。

**根因：**

`bounds_provider`（`_click_target_bounds`）回 `None` 時，`_QtClickWarningOverlayAdapter.begin` 走 `logger.debug` 之後 silent return：

```python
def begin(self, bounds_physical) -> None:
    if bounds_physical is None:
        logger.debug("warning-frame begin: no a11y bounds, frame hidden")
        return
```

預設 INFO level 連 terminal 都不會印出來，使用者沒線索區分以下三種狀態：

1. begin 根本沒被呼叫
2. begin 被呼叫了但 bounds=None
3. begin 被呼叫、bounds 對，但 paint 沒上去

**`bounds=None` 三條成因：**

1. `self._a11y is None`（`A11yService` 初始化失敗）
2. `self._movement.last_target_physical is None`（沒有最近的 `[MOVE:to]` target）
3. `a11y.bounds_at_physical_point(x, y)` 在 `_last_elements` 找不到包含 (x, y) 的元素（tree 沒更新 / 抓到別的視窗 / Chrome 被 session blacklist）

**修法（純 observability，零行為改動）：**

把 `_QtClickWarningOverlayAdapter.begin / end` 跟 `_click_target_bounds` 的「為什麼沒畫」全部升成 `print(..., flush=True)`，與 `[doro click]` / `[doro move]` 風格一致：

- adapter `begin(None)` → `[doro click] warning-frame skipped: bounds=None (no a11y element at the move target — _last_elements may be stale or from a different window)`
- adapter `begin(bounds)` → `[doro click] warning-frame begin: bounds=...`
- adapter `end()` → `[doro click] warning-frame end`
- `_click_target_bounds`：a11y service 缺、沒 `[MOVE:to]` target、`_last_elements` 找不到包含點，三條原因各印一行

**修改檔案：**

- `doro_app/app.py` — `_QtClickWarningOverlayAdapter.begin/end` 與 `_click_target_bounds`

**Commit：**

- `9453759` — `debug(click): mirror warning-frame begin/end/skip reasons to stdout`

**驗證：**

2026-06-16 使用者跑 build，terminal 印出 `warning-frame begin: bounds=(...)` 與 `warning-frame end` 配對、紅框視覺上正常出現，回報「正常了」。

**Follow-up（暫不動）：**

若日後 bounds=None 真的常觸發，再決定要動 `_a11y` setup 或 `ForegroundTracker` / `_last_elements` 更新時機。目前先以 observability 為止。

---

### 2. ✅ Ask Doro 對話框開啟卡頓

**症狀：**

使用者回報每次打開「Ask Doro」都會卡一下。

**調查：**

「Ask Doro」選單 → `ChatUIHelper.prompt_chat()`（`doro_app/ui/helpers/chat_ui_helper.py:59`）→ `show_chat_dialog()`（`doro_app/ui/dialogs/chat_dialog.py:294`）。git 歷史顯示這不是刻意設計，而是把原本 `QInputDialog.getText()`（一次性靜態 helper）換成自製對話框時，沿用了「每次 new 一個」的形狀。

**根因：**

`show_chat_dialog()` 每次都重建一個 `DoroChatDialog`——無邊框 + 半透明（`WA_TranslucentBackground`）+ 約 120 行 Qt stylesheet 解析，第一個畫面渲染時就卡。同專案 `ChatSettingsDialog` 早已用快取解決（`chat_ui_helper.py:48-51` 有註解），但這個輸入框漏掉。

**修法：**

- `ChatUIHelper` 新增 `_chat_dialog` 快取欄位，`prompt_chat()` 改用快取實例（比照 `_settings_dialog`）。
- `DoroChatDialog` 新增 `run()`：每次開啟前重設 `_message`、清空輸入、設定焦點，再 `exec()`。
- `show_chat_dialog()` 簡化為 `DoroChatDialog(parent).run()` 維持相容。
- 順修既有 bug：`_drag_position` 原本未在 `__init__` 初始化，快取重用後若先拖曳會 `AttributeError`；`__init__` 設為 `None` 並在 `mouseMoveEvent` 加 None 防護。

**修改檔案：**

- `doro_app/ui/dialogs/chat_dialog.py`
- `doro_app/ui/helpers/chat_ui_helper.py`

**Commit：**

- `dc932a7` — `perf(chat): cache Ask Doro input dialog to remove open lag`

**驗證：**

UI 測試 91 passed、全套測試 714 passed（offscreen）。

---

### 3. ✅ 對話內容寫入本機 log 的隱私外洩

**症狀：**

使用者問「對話紀錄會不會留在本機？」。對話 history（`controller.py:134` 的 `_history`）本身只在記憶體、關掉即清，也不會被 `_persist_chat_settings` 寫入磁碟；但調查發現 log 會留下對話內容。

**根因：**

預設 logger 寫入 `~/.doro/doro.log`（`doro_app/utils/logger.py:42-51`，DEBUG level、無上限）。其中：

- `orchestrator.py:67` 記錄每則使用者訊息前 50 字。
- `controller.py` build payload / start request 兩處記 `cleaned[:50]`。
- `controller._handle_worker_result` 有一段 debug 區塊把**伺服器完整回覆原文**同時 `print` 到終端並 `logger.debug` 寫入 log 檔——最大的內容外洩。

**修法（移除對話內容、保留結構性資訊）：**

- `orchestrator.send_message`：拿掉 `user_message[:50]`，只記 `(auto=..., silent=...)`。
- `controller`：build/start 兩處拿掉 `cleaned[:50]`。
- `controller._handle_worker_result`：整段移除 `print` 原始回傳 + `logger.debug` raw reply。
- 不含內容的 `response length: N` 等結構性 log 保留，方便除錯。

**修改檔案：**

- `doro_app/core/chat/controller.py`
- `doro_app/core/chat/orchestrator.py`

**Commit：**

- `0eace61` — `fix(chat): stop writing conversation content to local logs`

**驗證：**

chat 測試 68 passed、全套測試 714 passed（offscreen）。

**Follow-up（暫不動，已記入 `docs/BACKLOG.md`）：**

既有舊 `~/.doro/doro.log` 仍可能含 `0eace61` 之前的內容片段；日誌輪替/清理、預設等級改 INFO、api_key 改 keyring 均列入 backlog。

---
