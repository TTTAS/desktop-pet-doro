# 🧪 完整聊天日誌測試指南

## ✅ 現在有完整日誌覆蓋

你現在在整個聊天流程都有日誌：

```
使用者點擊「Ask Doro」
  ↓ chat_orchestrator.py (有日誌 ✅)
  ↓ chat_controller.py   (有日誌 ✅ NEW!)
  ↓ workers.py           (有日誌 ✅ NEW!)
  ↓ chat.py              (有日誌 ✅)
  ↓ HTTP 請求到 LMStudio
```

**之前缺少的部分已補上：chat_controller.py 和 workers.py**

---

## 🎯 測試步驟

### 測試 1：LMStudio 關閉時的完整日誌追蹤

1. **準備**
   ```bash
   # 確保 LMStudio 服務器關閉
   # 清空日誌
   echo "" > ~/.doro/doro.log

   # 開始即時監看日誌
   tail -f ~/.doro/doro.log
   ```

2. **執行測試**
   - 執行 `python doro.py`
   - 點擊「Ask Doro」
   - 輸入任何訊息（例如「你好」）

3. **預期日誌輸出**（完整流程）

   ```
   # 1. 應用程式初始化
   2025-11-18 12:00:00 - doro_app.window - INFO - Initializing Doro window
   2025-11-18 12:00:00 - doro_app.chat_controller - DEBUG - Initializing ChatController
   2025-11-18 12:00:00 - doro_app.chat_controller - INFO - ChatController initialized: server=http://localhost:1234, model=lmstudio, timeout=30s

   # 2. 使用者發送訊息
   2025-11-18 12:00:05 - doro_app.chat_orchestrator - INFO - Sending chat message (auto=False, silent=False): 你好...
   2025-11-18 12:00:05 - doro_app.chat_controller - DEBUG - Building chat payload for message: 你好...
   2025-11-18 12:00:05 - doro_app.chat_controller - DEBUG - Creating worker thread for endpoint: http://localhost:1234/v1/chat/completions
   2025-11-18 12:00:05 - doro_app.workers - DEBUG - ChatRequestWorker created for URL: http://localhost:1234/v1/chat/completions, timeout: 30s
   2025-11-18 12:00:05 - doro_app.chat_controller - INFO - Starting chat request (auto=False): 你好...

   # 3. Worker 執行緒開始
   2025-11-18 12:00:05 - doro_app.chat_orchestrator - DEBUG - Chat request started, setting busy state
   2025-11-18 12:00:05 - doro_app.workers - DEBUG - ChatRequestWorker.run() started in thread: <QThread object at 0x7f1234567890>

   # 4. HTTP 請求失敗
   2025-11-18 12:00:05 - doro_app.chat - DEBUG - Sending chat request to http://localhost:1234/v1/chat/completions
   2025-11-18 12:00:05 - doro_app.chat - ERROR - Chat request failed: Network error: [Errno 111] Connection refused (URL: http://localhost:1234/v1/chat/completions)

   # 5. Worker 發出錯誤訊號
   2025-11-18 12:00:05 - doro_app.workers - ERROR - ChatRequestWorker emitting error signal: Network error: [Errno 111] Connection refused

   # 6. Controller 處理錯誤
   2025-11-18 12:00:05 - doro_app.chat_controller - ERROR - Worker error: Network error: [Errno 111] Connection refused
   2025-11-18 12:00:05 - doro_app.chat_controller - DEBUG - Resetting worker state
   2025-11-18 12:00:05 - doro_app.chat_controller - DEBUG - Emitting request_failed signal (auto=False)
   2025-11-18 12:00:05 - doro_app.chat_controller - DEBUG - Worker thread finished

   # 7. Orchestrator 處理失敗
   2025-11-18 12:00:05 - doro_app.chat_orchestrator - ERROR - Chat request failed (auto=False): Network error: [Errno 111] Connection refused
   ```

4. **驗證**
   - ✅ 日誌記錄了完整流程（從點擊到錯誤）
   - ✅ 可以看到錯誤發生在哪一步
   - ✅ 有執行緒 ID 可以追蹤
   - ✅ 錯誤訊息清楚（Connection refused）

---

### 測試 2：正常運作時的日誌

1. **啟動 LMStudio**
   - 載入模型
   - 啟動服務器

2. **清空日誌並測試**
   ```bash
   echo "" > ~/.doro/doro.log
   tail -f ~/.doro/doro.log
   ```

3. **預期日誌**（成功流程）

   ```
   2025-11-18 12:10:00 - doro_app.chat_orchestrator - INFO - Sending chat message (auto=False, silent=False): 你好...
   2025-11-18 12:10:00 - doro_app.chat_controller - INFO - Starting chat request (auto=False): 你好...
   2025-11-18 12:10:00 - doro_app.workers - DEBUG - ChatRequestWorker.run() started in thread: <QThread...>
   2025-11-18 12:10:00 - doro_app.chat - DEBUG - Sending chat request to http://localhost:1234/v1/chat/completions
   2025-11-18 12:10:01 - doro_app.chat - DEBUG - Received response: 1234 bytes
   2025-11-18 12:10:01 - doro_app.chat - DEBUG - Successfully parsed JSON response
   2025-11-18 12:10:01 - doro_app.chat - INFO - Chat request successful, response length: 256
   2025-11-18 12:10:01 - doro_app.workers - INFO - ChatRequestWorker emitting finished signal, response length: 256
   2025-11-18 12:10:01 - doro_app.chat_controller - INFO - Worker finished successfully, response length: 256
   2025-11-18 12:10:01 - doro_app.chat_controller - DEBUG - Resetting worker state
   2025-11-18 12:10:01 - doro_app.chat_orchestrator - INFO - Chat request succeeded, response length: 256
   ```

---

### 測試 3：如果程式還是直接關閉...

如果加了這些日誌後，程式還是直接關閉，日誌會告訴你**在哪一步**：

#### 情況 A：日誌停在「Worker thread started」
```
2025-11-18 12:00:05 - doro_app.workers - DEBUG - ChatRequestWorker.run() started in thread: ...
```
**→ 問題在 perform_chat_request() 裡面，有未捕獲的異常**

#### 情況 B：日誌停在「Emitting error signal」
```
2025-11-18 12:00:05 - doro_app.workers - ERROR - ChatRequestWorker emitting error signal: ...
```
**→ 問題在訊號處理，可能是 Qt 訊號連接問題**

#### 情況 C：日誌有 CRITICAL 錯誤
```
2025-11-18 12:00:05 - doro_app.workers - CRITICAL - Unexpected error in ChatRequestWorker.run(): ...
[完整 Python stack trace]
```
**→ Worker 內部發生未預期的異常，stack trace 會顯示確切位置**

#### 情況 D：完全沒有日誌
**→ 程式在初始化時就崩潰了，檢查終端機輸出**

---

## 🔍 日誌分析技巧

### 追蹤特定請求

```bash
# 找到特定訊息的完整流程
grep "你好" ~/.doro/doro.log -A 20
```

### 只看錯誤

```bash
# 只看 ERROR 和 CRITICAL
grep -E "ERROR|CRITICAL" ~/.doro/doro.log
```

### 看執行緒活動

```bash
# 看 worker 執行緒
grep "ChatRequestWorker" ~/.doro/doro.log
```

### 看訊號流程

```bash
# 追蹤訊號發送和接收
grep -E "emit|signal" ~/.doro/doro.log
```

---

## 📊 日誌級別含義

| 級別 | 顏色 | 何時出現 | 範例 |
|------|------|---------|------|
| **DEBUG** | 🔵 | 詳細流程 | `Worker thread started` |
| **INFO** | ⚪ | 重要事件 | `Starting chat request` |
| **WARNING** | 🟡 | 警告 | `Invalid timeout value` |
| **ERROR** | 🔴 | 錯誤 | `Worker error: Connection refused` |
| **CRITICAL** | 💀 | 嚴重錯誤 | `Unexpected error in run()` |

---

## ✨ 現在你可以：

### ✅ 追蹤完整請求生命週期
```
點擊 → 訊息 → Worker建立 → 執行緒 → HTTP → 回應 → 訊號 → UI更新
每一步都有日誌！
```

### ✅ 快速定位問題
- 在哪個模組？（從日誌名稱看）
- 在哪一步？（從日誌順序看）
- 什麼錯誤？（從錯誤訊息看）

### ✅ 除錯超快速
1. 重現問題
2. 查看日誌
3. 找到錯誤行
4. 5 分鐘內定位問題

---

## 🎯 立即測試

```bash
# 1. 關閉 LMStudio
# 2. 清空日誌
echo "" > ~/.doro/doro.log

# 3. 開兩個終端機
# 終端機 1：執行程式
python doro.py

# 終端機 2：監看日誌
tail -f ~/.doro/doro.log

# 4. 點擊 Ask Doro，輸入訊息
# 5. 觀察日誌，看到完整流程！
```

---

**如果程式還是直接關閉，日誌會告訴你確切原因！** 🎉
