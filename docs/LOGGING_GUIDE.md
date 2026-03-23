# 日誌系統使用指南

## ✅ 已完成修復

### 1. 記憶體洩漏修復
- ✅ `StateManagerDialog` - 關閉時清理 QMovie
- ✅ `MoveStateManagerDialog` - 關閉時清理 QMovie
- ✅ `EditMoveStateDialog` - 關閉時清理預覽 QMovie

### 2. 路徑遍歷漏洞修復
- ✅ `GifRepository.get_path()` - 使用 `Path.resolve()` + `relative_to()` 檢查
- ✅ 阻擋 `../../etc/passwd` 類型的攻擊
- ✅ 加入詳細日誌記錄安全事件

### 3. 日誌系統建立
- ✅ 新增 `doro_app/utils/logger.py` - 集中式日誌配置
- ✅ 日誌存放位置：`~/.doro/doro.log`
- ✅ 自動建立日誌目錄
- ✅ 同時輸出到檔案和控制台

---

## 📖 使用方式

### 在任何模組中加入日誌

```python
# 1. 匯入 logger
from doro_app.utils.logger import get_logger

# 2. 建立 logger 實例（使用模組名稱）
logger = get_logger(__name__)

# 3. 使用日誌
logger.debug("詳細的除錯資訊")
logger.info("一般資訊訊息")
logger.warning("警告訊息")
logger.error("錯誤訊息")
logger.critical("嚴重錯誤")
```

### 範例：在函數中使用

```python
def load_state(self, key: str):
    logger.info(f"Loading state: {key}")

    try:
        # 你的程式碼
        result = self._do_something(key)
        logger.debug(f"State loaded successfully: {result}")
        return result
    except FileNotFoundError as e:
        logger.error(f"State file not found: {key} - {e}")
        return None
    except Exception as e:
        logger.critical(f"Unexpected error loading state {key}: {e}", exc_info=True)
        raise
```

---

## 📊 已加入日誌的模組

### ✅ `core/state/repository.py`
- GIF 路徑解析（包含安全檢查）
- 狀態載入/儲存操作
- 錯誤處理

### ✅ `core/state/service.py`
- 狀態變更事件
- 新增/移除狀態
- GIF 管理

### ✅ `core/chat/controller.py`
- HTTP 請求/回應
- 驗證和重試

### ✅ `core/chat/orchestrator.py`
- 聊天協調流程

### ✅ `ui/window.py`
- 視窗初始化

---

## 🔍 查看日誌

### 日誌檔案位置
```bash
~/.doro/doro.log
```

### Linux/Mac 即時監看
```bash
tail -f ~/.doro/doro.log
```

### Windows 即時監看（PowerShell）
```powershell
Get-Content ~\.doro\doro.log -Wait
```

### 查看最近 50 行
```bash
tail -n 50 ~/.doro/doro.log
```

### 搜尋特定錯誤
```bash
grep "ERROR" ~/.doro/doro.log
grep "WARNING" ~/.doro/doro.log
```

---

## 🎯 日誌等級說明

| 等級 | 用途 | 範例 |
|------|------|------|
| **DEBUG** | 詳細除錯資訊 | `logger.debug(f"Variable x = {x}")` |
| **INFO** | 一般操作資訊 | `logger.info("State changed to 'happy'")` |
| **WARNING** | 警告但不影響運作 | `logger.warning("Config file not found, using defaults")` |
| **ERROR** | 錯誤但程式可繼續 | `logger.error(f"Failed to save state: {e}")` |
| **CRITICAL** | 嚴重錯誤需立即處理 | `logger.critical("Database corrupted!")` |

---

## 🛠️ 調整日誌等級

### 修改 `utils/logger.py` 中的預設等級

```python
def setup_logger(
    name: str = "doro",
    log_file: Optional[Path] = None,
    level: int = logging.INFO,  # ← 改這裡
    console: bool = True,
):
```

### 等級常數
```python
import logging

logging.DEBUG    # 10 - 最詳細
logging.INFO     # 20 - 一般資訊（預設）
logging.WARNING  # 30 - 警告
logging.ERROR    # 40 - 錯誤
logging.CRITICAL # 50 - 嚴重錯誤
```

---

## 📝 下一步建議

### 短期（繼續開發時加入）
1. ✅ 在 `core/chat/controller.py` 加入日誌（HTTP 請求/回應）
2. ✅ 在 `core/movement/manager.py` 加入日誌（移動計算）

### 中期（準備釋出前）
1. 加入日誌輪替（避免日誌檔案無限增長）
2. 加入使用者隱私保護（不記錄敏感資訊）
3. 加入遠端日誌上傳（可選，方便收集錯誤報告）

---

## 🚀 測試日誌系統

執行你的應用程式，然後檢查：
```bash
cat ~/.doro/doro.log
```

你應該會看到類似：
```
2025-11-18 04:47:23 - doro_app.window - INFO - Initializing Doro window
2025-11-18 04:47:23 - doro_app.state_repository - INFO - Loaded state config from /home/user/.doro/STATE/states.json
2025-11-18 04:47:23 - doro_app.state_repository - INFO - Loaded 5 custom states
2025-11-18 04:47:23 - doro_app.state_service - INFO - State changed: idle -> happy
```

如果看到這些，恭喜！日誌系統正常運作 🎉
