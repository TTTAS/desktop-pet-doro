# Doro 聊天系統架構說明（當前狀態）

## 📐 整體架構

```
用戶輸入
    ↓
ChatUIHelper (UI層)
    ↓
ChatOrchestrator (協調層)
    ↓
ChatController (控制層)
    ↓
ResponseValidator (驗證層)
    ↓
ChatWorker (網絡層)
    ↓
LLM API (OpenAI 相容格式)
```

---

## 🔄 完整請求流程

### 1. 用戶發送消息

```
用戶 → 右鍵菜單「Ask Doro」→ ChatUIHelper.prompt_chat()
```

**ChatUIHelper** (doro_app/ui/helpers/chat_ui_helper.py):
```python
def prompt_chat(self):
    dialog = QtWidgets.QInputDialog(self.window)
    dialog.setWindowTitle("Chat with Doro")
    dialog.setLabelText("What would you like to say?")

    if dialog.exec() == QtWidgets.QDialog.Accepted:
        message = dialog.textValue().strip()
        if message:
            self.window._chat_orchestrator.send_message(message)
```

### 2. 協調層處理

**ChatOrchestrator** (doro_app/core/chat/orchestrator.py):
```python
def send_message(self, user_message: str, *, silent: bool = False, is_auto: bool = False) -> bool:
    # 檢查是否有請求進行中
    if self._controller.is_inflight:
        return False

    # 啟動請求
    started, error_message = self._controller.start_request(user_message, is_auto=is_auto)

    # 標記用戶活動（重置閒置計時器）
    self._window._mark_user_activity()

    return started
```

**職責**:
- 檢查是否有請求進行中
- 調用 Controller 啟動請求
- 處理錯誤訊息（彈出對話框）
- 標記用戶活動

### 3. 控制層構建請求

**ChatController** (doro_app/core/chat/controller.py):
```python
def start_request(self, user_message: str, *, is_auto: bool = False) -> tuple[bool, str | None]:
    # 驗證消息非空
    # 檢查是否有請求進行中
    # 解析端點 URL

    # 保存原始消息（用於重試）
    if self._retry_count == 0:
        self._original_user_message = cleaned

    # 構建 payload
    payload = self._build_chat_payload(cleaned)

    # 創建 Worker 和 Thread
    worker = ChatRequestWorker(endpoint, payload, timeout)
    thread = QtCore.QThread()
    worker.moveToThread(thread)

    # 連接信號
    thread.started.connect(worker.run)
    worker.finished.connect(self._handle_worker_finished)
    worker.error.connect(self._handle_worker_error)

    # 啟動線程
    thread.start()
    self.request_started.emit(cleaned, is_auto)

    return True, None
```

**payload 格式**:
```python
{
    "model": "lmstudio",
    "messages": [
        {"role": "system", "content": "你是名為「doro」的桌面寵物..."},
        {"role": "user", "content": "跟我打招呼"}
    ],
    "temperature": 0.7,
    "max_tokens": -1
}
```

### 4. 網絡層發送請求

**ChatWorker** (doro_app/utils/workers.py):

使用 `urllib.request` 發送 HTTP POST 請求到 LLM 伺服器（OpenAI 相容格式），
並在獨立 QThread 中執行以避免阻塞 UI。

### 5. **驗證層檢查響應（新增）**

**ChatController._handle_worker_finished()** (controller.py:200):
```python
def _handle_worker_finished(self, assistant_text: str):
    # 驗證響應
    validation = self._validator.validate(assistant_text)

    if not validation.valid:
        logger.warning(f"Response validation failed: {validation.error_message}")

        # 檢查是否應該重試
        if self._validator.should_retry(validation) and self._retry_count < self._max_retries:
            self._retry_count += 1

            # 構建重試提示
            retry_message = self._validator.build_retry_prompt(validation, self._original_user_message)

            # ⚠️ 延遲重試（避免 QThread 錯誤）
            def _delayed_retry():
                self.start_request(retry_message, is_auto=was_auto)

            QtCore.QTimer.singleShot(150, _delayed_retry)
            return

        # 重試次數用盡
        self.request_failed.emit(f"Response validation failed: {validation.error_message}", was_auto)
        return

    # 驗證通過，添加到歷史
    self._history.append({"role": "user", "content": self._last_user_message})
    self._history.append({"role": "assistant", "content": assistant_text})

    self.request_succeeded.emit(assistant_text, was_auto)
```

**ResponseValidator.validate()** (validator.py):

驗證邏輯（當前版本）：
1. 檢查回覆是否為空
2. 解析 actions（狀態令牌和移動令牌）
3. **狀態令牌：不再驗證**（標記存在即可，無效狀態由 orchestrator fallback 處理）
4. **移動令牌：驗證方向是否合法**（left/right/up/down/upleft/upright/downleft/downright）
5. 只有**無效移動方向**會觸發重試

### 6. 協調層處理響應

**ChatOrchestrator._on_request_succeeded()** (orchestrator.py:125):
```python
def _on_request_succeeded(self, assistant_text: str, _was_auto: bool):
    # 解析和處理 actions
    display_text = self._handle_actions_in_text(assistant_text)

    # 顯示對話泡泡
    if display_text:
        self._window._set_bubble_text(display_text)

    # 取消忙碌游標
    self._window._set_busy_cursor(False)
```

**_handle_actions_in_text()** (orchestrator.py:157):
```python
def _handle_actions_in_text(self, assistant_text: str) -> str:
    # 解析 actions
    cleaned_text, actions = parse_actions_from_text(assistant_text)

    for kind, token in actions:
        if kind == "bracket":  # [MOVE:dir=left;distance=80]
            self._movement.handle_move_bracket(token, move_reports)

        elif kind == "paren":  # (HAPPY)
            state_key = self._window._find_state_for_action(token)
            if state_key:
                # 切換狀態
                self._state_service.set_state(state_key)

    # 返回清理後的對話文本
    return self._clean_assistant_dialogue(cleaned_text)
```

---

## 🧩 各組件職責

### ChatUIHelper (UI層)
**文件**: `doro_app/ui/helpers/chat_ui_helper.py`

**職責**:
- 顯示輸入對話框
- 顯示/編輯系統 prompt
- 顯示/編輯 server URL
- 配置聊天設置（model, temperature, timeout）

### ChatOrchestrator (協調層)
**文件**: `doro_app/core/chat/orchestrator.py`

**職責**:
- 協調 Controller 和 UI
- 處理請求狀態變化（started/succeeded/failed）
- 解析 LLM 響應中的控制令牌
- 執行狀態切換和移動命令
- 顯示對話泡泡

**關鍵方法**:
- `send_message()` - 發送聊天消息
- `_on_request_succeeded()` - 處理成功響應
- `_handle_actions_in_text()` - 解析並執行 actions

### ChatController (控制層)
**文件**: `doro_app/core/chat/controller.py`

**職責**:
- 管理聊天配置（server URL, model, temperature, timeout）
- 構建 chat payload
- 創建和管理 Worker Thread
- **驗證 LLM 響應**（新增）
- **自動重試機制**（新增）
- 維護對話歷史

**關鍵屬性**:
- `_validator: ResponseValidator` - 響應驗證器
- `_max_retries: int = 2` - 最大重試次數
- `_retry_count: int` - 當前重試計數
- `_original_user_message: str` - 原始用戶消息（用於重試）

**關鍵方法**:
- `start_request()` - 啟動請求
- `_handle_worker_finished()` - 處理響應（含驗證）
- `_build_chat_payload()` - 構建請求 payload

### ResponseValidator (驗證層)
**文件**: `doro_app/core/chat/validator.py`

**職責**:
- 檢查回覆是否為空
- 驗證移動方向是否有效（唯一的重試觸發條件）
- 構建重試提示（包含錯誤詳情）
- **注意**：狀態令牌不再驗證（由 orchestrator fallback 處理）

**關鍵方法**:
- `validate(response)` - 驗證響應格式
- `should_retry(result)` - 判斷是否應重試
- `build_retry_prompt(result, original_message)` - 構建重試提示

### ChatWorker (網絡層)
**文件**: `doro_app/utils/workers.py`

**職責**:
- 在獨立 QThread 發送 HTTP 請求（urllib）
- 解析 OpenAI 相容格式響應
- 發送 finished/error 信號

---

## 🔁 重試邏輯流程

**注意：** 當前版本中，只有**無效移動方向**會觸發重試。無效狀態不會重試（由 orchestrator fallback 處理）。

```
用戶: "往左走"
    ↓
LLM 返回: "(idle) 好的～ [MOVE:dir=forward;distance=50]"
    ↓
Validator: 檢查 "forward" 方向
    ↓
❌ "forward" 不在合法方向列表中
    ↓
ValidationResult.failure("Invalid movement direction(s): forward. Valid directions: left, right, ...")
    ↓
should_retry? ✅ (retry_count=0 < max_retries=2)
    ↓
構建重試提示:
"往左走

[系統提示] 你上次的回應格式有誤: Invalid movement direction(s): forward.
請重新回答，確保使用正確的狀態和格式。"
    ↓
⏱️ QTimer.singleShot(150ms) - 延遲重試
    ↓
retry_count = 1
    ↓
再次發送請求
    ↓
LLM 返回: "(idle) 好的～ [MOVE:dir=left;distance=50]"
    ↓
Validator: 檢查 "left" 方向
    ↓
✅ 驗證通過
    ↓
添加到對話歷史 → emit request_succeeded → 執行移動
```

---

## ⚠️ 當前已知問題

### 已修復的問題

1. ✅ **QThread 清理競爭條件** — 使用 `QTimer.singleShot(150ms)` 延遲重試
2. ✅ **狀態驗證過於嚴格** — 無效狀態不再觸發重試，改由 orchestrator fallback 處理

---

## 📊 數據流示意圖

```
┌──────────────┐
│   用戶輸入    │
└──────┬───────┘
       │
       ↓
┌─────────────────────────────────────────────────┐
│              ChatOrchestrator                    │
│  ┌──────────────────────────────────────────┐  │
│  │ send_message()                            │  │
│  │  - 檢查 is_inflight                       │  │
│  │  - 調用 controller.start_request()        │  │
│  └──────────────┬───────────────────────────┘  │
└─────────────────┼───────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────┐
│              ChatController                      │
│  ┌──────────────────────────────────────────┐  │
│  │ start_request()                           │  │
│  │  1. 構建 payload                          │  │
│  │  2. 創建 Worker + QThread                 │  │
│  │  3. 連接信號                              │  │
│  │  4. 啟動線程                              │  │
│  └──────────────┬───────────────────────────┘  │
└─────────────────┼───────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────┐
│           ChatWorker (QThread)            │
│  ┌──────────────────────────────────────────┐  │
│  │ run()                                     │  │
│  │  - requests.post(endpoint, payload)       │  │
│  │  - 解析響應                               │  │
│  │  - emit finished(assistant_text)          │  │
│  └──────────────┬───────────────────────────┘  │
└─────────────────┼───────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────┐
│              ChatController                      │
│  ┌──────────────────────────────────────────┐  │
│  │ _handle_worker_finished()                 │  │
│  │  1. validator.validate(response)          │  │
│  │     ├─ ✅ 通過 → 添加到歷史                │  │
│  │     └─ ❌ 失敗 → 檢查重試                 │  │
│  │  2. emit request_succeeded/failed         │  │
│  └──────────────┬───────────────────────────┘  │
└─────────────────┼───────────────────────────────┘
                  │
        ┌─────────┴──────────┐
        │                    │
        ↓ ✅                 ↓ ❌
┌───────────────┐    ┌──────────────┐
│  succeeded    │    │    failed    │
└───────┬───────┘    └──────┬───────┘
        │                   │
        ↓                   ↓
┌─────────────────────────────────────────────────┐
│              ChatOrchestrator                    │
│  ┌──────────────────────────────────────────┐  │
│  │ _on_request_succeeded()                   │  │
│  │  - _handle_actions_in_text()              │  │
│  │    - 解析 (STATE) → 切換狀態              │  │
│  │    - 解析 [MOVE:...] → 執行移動           │  │
│  │  - 顯示對話泡泡                           │  │
│  └───────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────┐  │
│  │ _on_request_failed()                      │  │
│  │  - 顯示錯誤訊息                           │  │
│  │  - 取消忙碌游標                           │  │
│  └───────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
        │
        ↓
┌──────────────┐
│   UI 更新     │
│ - 對話泡泡    │
│ - 狀態切換    │
│ - 位置移動    │
└──────────────┘
```

---

## 🔧 配置項

### ChatController 配置 (ConfigManager)
```python
chat/server_url = "http://localhost:1234"   # LLM 伺服器地址
chat/endpoint_path = "/v1/chat/completions" # API 端點路徑
chat/timeout_seconds = 30                   # 請求超時
chat/temperature = 0.7                      # LLM 溫度
```

### Validator 配置 (Hard-coded)
```python
self._max_retries = 2  # controller.py:55
```

可調整為:
- `0` - 只驗證，不重試
- `1` - 一次重試
- `2` - 兩次重試（默認）
- `3+` - 更多重試

---

## 📝 日誌追蹤

### 正常流程日誌
```
ChatController initialized: server=http://localhost:1234, timeout=30s
Sending chat message (auto=False, silent=False): 跟我打招呼...
Starting chat request (auto=False): 跟我打招呼...
Chat request started, setting busy state
Worker finished successfully, response length: 45
Response validation passed (state=True, movement=False, dialogue=True)
Chat request succeeded, response length: 45
```

### 驗證失敗流程日誌（移動方向錯誤）
```
Worker finished successfully, response length: 50
Response validation failed: Invalid movement direction(s): forward. Valid directions: left, right, up, down, ...
Retrying request (attempt 1/2)
...
```

### 重試用盡流程日誌
```
Response validation failed: Invalid movement direction(s): forward
Retrying request (attempt 1/2)
...
Response validation failed after 2 retries
Chat request failed (auto=False): Response validation failed: ...
```

---

## 總結

### ✅ 當前優勢
1. **清晰的分層架構**: UI → 協調 → 控制 → 驗證 → 網絡
2. **自動驗證**: 所有響應都會檢查格式
3. **自動重試**: 格式錯誤時自動修正（最多2次）
4. **線程安全**: QTimer 延遲避免競爭條件
5. **詳細日誌**: 所有操作都有記錄

### ⚠️ 需要注意
1. **重試範圍窄**: 目前只有無效移動方向會觸發重試
2. **重試延遲**: 每次重試增加 ~2-5 秒（LLM 響應時間）
3. **最大重試**: 達到 2 次後會顯示錯誤給用戶
