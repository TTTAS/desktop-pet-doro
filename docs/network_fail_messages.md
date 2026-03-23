# Network Failure Messages 功能

## 概述

當 doro 連不上 LLM 伺服器時，會從 `network_fail_doro.txt` 檔案中隨機挑選一句可愛的訊息顯示給用戶。

---

## 📁 檔案位置

### 訊息檔案
```
doro_app/core/chat/network_fail_doro.txt
```

### 相關程式碼
- `doro_app/utils/paths.py` - 路徑定義
- `doro_app/core/chat/orchestrator.py` - 讀取和顯示邏輯

---

## 📝 訊息內容

檔案包含 **15 條**不同的 doro 風格錯誤訊息：

```
嗚嗚……人，doro找不到回應了……
人～訊號不見了啦，doro好困惑……
咦？網路好像在睡覺……人要等等doro喔～
唔……doro好像迷路了，找不到伺服器……
人，doro的小腦袋連不上了啦……
嘿嘿……好像有點卡住了，人再試試看好嘛？
呼啊～伺服器在休息嗎？doro也想休息了……
人，這個……doro好像聽不到回音……
哼！網路壞壞，不理doro了啦！
嗚……doro努力了，但是連不上……人別生氣喔～
咦咦？訊號跑去哪裡了？doro找不到……
人～伺服器好像在偷懶，doro也沒辦法……
唔嗯……網路好像斷掉了，doro好無助……
人，doro想說話，可是……連不上了……
嘿嘿……看來要等一下下喔，doro也在等～
```

### 訊息風格
- ✅ 符合 doro 的性格（天真、撒嬌、略帶傲嬌）
- ✅ 使用 doro 的語氣詞（「～」、「啦」、「喔」、「嘿嘿」、「嗚嗚」）
- ✅ 稱呼用戶為「人」
- ✅ 不會讓錯誤感覺太嚴重
- ✅ 保持可愛和親切感

---

## 🔧 程式碼實作

### 1. 路徑定義 (paths.py)

```python
NETWORK_FAIL_MESSAGES_PATH = CHAT_DIR / "network_fail_doro.txt"
```

### 2. 讀取隨機訊息 (orchestrator.py)

```python
def _get_random_network_fail_message(self) -> str:
    """
    Get a random network failure message from network_fail_doro.txt.

    Returns:
        Random message from file, or default message if file not found
    """
    try:
        if NETWORK_FAIL_MESSAGES_PATH.exists():
            with open(NETWORK_FAIL_MESSAGES_PATH, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            if lines:
                return random.choice(lines)
    except Exception as e:
        logger.warning(f"Failed to read network fail messages: {e}")

    # Fallback message
    return "嗚嗚……人，doro找不到回應了……"
```

### 3. 使用在錯誤處理 (orchestrator.py)

```python
def _on_request_failed(self, error_message: str, was_auto: bool):
    logger.error(f"Chat request failed (auto={was_auto}): {error_message}")

    # Show error dialog (for manual requests)
    if not was_auto:
        QtWidgets.QMessageBox.warning(
            self._window,
            "Chat",
            error_message or "Failed to reach the chat server.",
        )

    self._window._set_busy_cursor(False)

    # Use random network fail message from doro
    fallback_text = self._get_random_network_fail_message()

    if not was_auto:
        self._window._set_bubble_text(fallback_text, auto_hide=False)
```

---

## 🎯 觸發時機

### 連線失敗情況
1. **LLM 伺服器 未啟動**
   ```
   ConnectionRefusedError: [Errno 111] Connection refused
   ```

2. **網路斷線**
   ```
   requests.exceptions.ConnectionError
   ```

3. **伺服器逾時**
   ```
   requests.exceptions.Timeout
   ```

4. **URL 錯誤**
   ```
   Invalid URL / DNS resolution failed
   ```

### 顯示位置
- **對話泡泡**: 顯示 doro 的可愛錯誤訊息
- **錯誤對話框**: 顯示技術錯誤詳情（給開發者看）

---

## 📊 行為對比

### 修改前
```
錯誤發生
  ↓
顯示: "I could not reach the chat server."
  ↓
- 每次都一樣
- 英文訊息
- 沒有 doro 的性格
- 感覺冷冰冰
```

### 修改後
```
錯誤發生
  ↓
讀取 network_fail_doro.txt
  ↓
隨機選一句
  ↓
顯示: "嗚嗚……人，doro找不到回應了……"（或其他 14 條之一）
  ↓
- 每次都不同（15 種變化）
- 中文訊息
- 保持 doro 的性格
- 感覺親切可愛
```

---

## ✨ 優點

### 用戶體驗
- ✅ **減少挫折感**: 可愛的訊息讓錯誤不那麼煩人
- ✅ **保持沉浸感**: 即使出錯，doro 還是 doro
- ✅ **增加變化性**: 15 種不同訊息，不會感覺重複
- ✅ **情感連結**: 讓用戶覺得 doro 也在努力，不會責怪她

### 開發優勢
- ✅ **易於維護**: 訊息都在文字檔，修改不需要改程式碼
- ✅ **易於擴展**: 可以輕鬆添加更多訊息
- ✅ **容錯處理**: 如果檔案不存在，有預設訊息

---

## 🔄 如何修改訊息

### 添加新訊息
直接編輯 `doro_app/core/chat/network_fail_doro.txt`：

```bash
# 每行一句訊息
nano doro_app/core/chat/network_fail_doro.txt
```

### 訊息格式規範
1. **每行一句訊息**
2. **使用 doro 的語氣**
3. **稱呼用戶為「人」**
4. **保持簡短** (1-2 句話)
5. **避免太嚴肅或負面的詞彙**

### 範例：好的訊息
```
✅ 嗚嗚……人，doro找不到回應了……
✅ 人～訊號不見了啦，doro好困惑……
✅ 哼！網路壞壞，不理doro了啦！
```

### 範例：不好的訊息
```
❌ 連線失敗，請檢查網路設定。（太技術性）
❌ 伺服器錯誤 500（沒有性格）
❌ 完蛋了，什麼都連不上！（太負面）
```

---

## 🧪 測試方法

### 方法 1：關閉 LLM 伺服器
1. 關閉 LLM 伺服器
2. 在 doro 中點擊 Ask Doro
3. 輸入訊息並發送
4. 觀察顯示的錯誤訊息

### 方法 2：錯誤的 URL
1. 右鍵選單 → Chat → Configure Server
2. 輸入錯誤的 URL（如 `http://localhost:99999`）
3. 嘗試發送訊息
4. 觀察錯誤訊息

### 方法 3：程式測試
```python
from doro_app.core.chat.orchestrator import ChatOrchestrator

# 模擬 orchestrator
orchestrator = ChatOrchestrator(...)

# 測試隨機訊息
for i in range(5):
    msg = orchestrator._get_random_network_fail_message()
    print(f"{i+1}. {msg}")
```

---

## 📈 未來擴展

### 可能的改進

#### 1. 按錯誤類型分類
```
network_fail_doro.txt        # 網路錯誤
timeout_doro.txt             # 逾時錯誤
validation_fail_doro.txt     # 驗證錯誤
```

#### 2. 添加狀態切換
連線失敗時切換到 SAD 或 CONFUSED 狀態

#### 3. 添加動作
```python
fallback_text = self._get_random_network_fail_message()
self._state_service.set_state("sad")  # 切換到難過狀態
```

#### 4. 連續失敗累積
```python
if self._consecutive_failures > 3:
    # 使用更無奈的訊息
    return "嗚嗚……人，doro真的找不到了……要放棄了……"
```

---

## 🐛 故障排除

### 問題：每次都顯示相同訊息
**原因**: `random.choice()` 可能碰巧選到相同的
**解決**: 這是正常的，多試幾次就會看到不同的

### 問題：顯示預設訊息而非檔案中的
**檢查**:
1. 檔案是否存在
   ```python
   from doro_app.utils.paths import NETWORK_FAIL_MESSAGES_PATH
   print(NETWORK_FAIL_MESSAGES_PATH.exists())
   ```

2. 檔案是否有內容
   ```bash
   cat doro_app/core/chat/network_fail_doro.txt
   ```

3. 編碼是否正確（應該是 UTF-8）

### 問題：訊息顯示亂碼
**原因**: 編碼問題
**解決**: 確保檔案以 UTF-8 編碼儲存

---

## 📦 提交資訊

```
commit 79fae67
feat: add random network failure messages from doro

當連線失敗時，doro 會從檔案中隨機挑選一句可愛的訊息說出來
```

---

## 總結

這個功能讓 doro 在出錯時也能保持她的性格，把冷冰冰的技術錯誤變成可愛的互動。用戶不會因為連線失敗而感到沮喪，反而會覺得 doro 也在努力嘗試，增強了情感連結。

**核心價值**：
- 🎀 保持角色一致性
- 💝 提升用戶體驗
- 🔄 增加變化性
- 😊 減少負面情緒
