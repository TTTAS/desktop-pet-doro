# 🔍 聊天錯誤日誌測試指南

## 問題描述
你發現：關閉 LMStudio 服務器 → 點擊 doro → 程式直接關閉 → 日誌沒有任何記錄

## ✅ 已修復
現在所有聊天錯誤都會記錄到日誌！

---

## 🧪 測試步驟

### 測試 1：LMStudio 服務器關閉時的錯誤

1. **關閉 LMStudio 服務器**
   - 打開 LMStudio
   - 停止本地服務器（如果有在跑的話）

2. **清空舊日誌**（方便查看）
   ```bash
   echo "" > ~/.doro/doro.log
   ```

3. **執行 Doro**
   ```bash
   python doro.py
   ```

4. **觸發聊天**
   - 右鍵點擊 doro
   - 選擇「Ask Doro」或「聊天」
   - 輸入任何訊息，例如：「你好」

5. **預期行為**
   - ❌ **舊版**：程式直接關閉，沒有日誌
   - ✅ **新版**：顯示錯誤對話框，日誌有詳細記錄

6. **查看日誌**
   ```bash
   cat ~/.doro/doro.log
   ```

   **預期日誌內容：**
   ```
   2025-11-18 12:34:56 - doro_app.chat_orchestrator - INFO - Sending chat message (auto=False, silent=False): 你好...
   2025-11-18 12:34:56 - doro_app.chat - DEBUG - Sending chat request to http://localhost:1234/v1/chat/completions
   2025-11-18 12:34:56 - doro_app.chat - ERROR - Chat request failed: Network error: [Errno 111] Connection refused (URL: http://localhost:1234/v1/chat/completions)
   2025-11-18 12:34:56 - doro_app.chat_orchestrator - ERROR - Chat request failed (auto=False): Network error: [Errno 111] Connection refused
   ```

---

### 測試 2：LMStudio 正常運作時

1. **啟動 LMStudio 服務器**
   - 打開 LMStudio
   - 載入一個模型
   - 啟動本地服務器

2. **清空日誌**
   ```bash
   echo "" > ~/.doro/doro.log
   ```

3. **執行 Doro 並聊天**
   - 執行程式
   - 點擊「Ask Doro」
   - 輸入訊息

4. **查看日誌**
   ```bash
   tail -f ~/.doro/doro.log
   ```

   **預期日誌內容：**
   ```
   2025-11-18 12:40:00 - doro_app.chat_orchestrator - INFO - Sending chat message (auto=False, silent=False): 你好...
   2025-11-18 12:40:00 - doro_app.chat - DEBUG - Sending chat request to http://localhost:1234/v1/chat/completions
   2025-11-18 12:40:00 - doro_app.chat - DEBUG - Successfully parsed JSON response
   2025-11-18 12:40:00 - doro_app.chat - INFO - Chat request successful, response length: 256
   2025-11-18 12:40:00 - doro_app.chat_orchestrator - INFO - Chat request succeeded, response length: 256
   ```

---

### 測試 3：無效的 URL

1. **修改聊天服務器 URL**
   - 在設定中把 URL 改成不存在的地址
   - 例如：`http://localhost:9999`

2. **觸發聊天**

3. **查看日誌**

   **預期看到：**
   ```
   2025-11-18 12:45:00 - doro_app.chat - ERROR - Chat request failed: Network error: [Errno 111] Connection refused (URL: http://localhost:9999/v1/chat/completions)
   ```

---

## 📊 日誌級別說明

| 級別 | 何時出現 | 範例 |
|------|---------|------|
| **DEBUG** | HTTP 請求細節 | `Sending chat request to ...` |
| **INFO** | 正常操作 | `Chat request successful` |
| **WARNING** | 警告但能繼續 | `Chat request rejected: previous request still in flight` |
| **ERROR** | 錯誤 | `Chat request failed: Network error` |

---

## 🔎 常見錯誤訊息

### 1. Connection Refused
```
Network error: [Errno 111] Connection refused
```
**原因：** LMStudio 服務器沒有啟動
**解決：** 啟動 LMStudio 服務器

### 2. Connection Timeout
```
Network error: <urlopen error timed out>
```
**原因：** 服務器回應太慢
**解決：** 檢查網路，或增加 timeout 設定

### 3. HTTP 404
```
HTTP error 404: Not Found
```
**原因：** Endpoint 路徑錯誤
**解決：** 檢查設定中的 endpoint path（應該是 `/v1/chat/completions`）

### 4. Invalid JSON
```
Failed to parse chat response: Invalid JSON
```
**原因：** 服務器返回的不是 JSON
**解決：** 檢查服務器是否正常運作

---

## 🐛 如果程式還是直接關閉...

如果加了日誌後，程式還是直接關閉（沒有顯示錯誤對話框），可能是：

### 檢查 1：未捕獲的異常

查看終端機輸出：
```bash
python doro.py 2>&1 | tee doro_error.log
```

如果有 Python traceback，會顯示在終端機。

### 檢查 2：Qt 訊號問題

查看日誌最後幾行：
```bash
tail -n 20 ~/.doro/doro.log
```

如果看到日誌突然中斷（在某個操作之後沒有繼續），可能是 Qt 訊號處理問題。

### 檢查 3：系統日誌

**Linux:**
```bash
journalctl -xe | grep python
```

**Mac:**
```bash
tail -f /var/log/system.log | grep doro
```

---

## 📝 回報問題時

如果問題仍然存在，請提供：

1. **日誌檔案**
   ```bash
   cat ~/.doro/doro.log
   ```

2. **終端機輸出**
   ```bash
   python doro.py 2>&1
   ```

3. **重現步驟**
   - 具體的操作步驟
   - LMStudio 的狀態（開啟/關閉）
   - 點擊了什麼

---

## ✨ 總結

現在當聊天失敗時，你會看到：

1. ✅ **錯誤對話框**（UI 提示）
2. ✅ **詳細日誌**（`~/.doro/doro.log`）
3. ✅ **錯誤原因**（Network error / HTTP error / JSON error）

不再是「程式直接關閉，什麼都不知道」的黑箱狀態！🎉
