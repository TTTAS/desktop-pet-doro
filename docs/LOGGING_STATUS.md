# 📊 日誌系統覆蓋率報告

## ✅ 已加入日誌的模組 (6/22)

| 檔案 | 重要程度 | 狀態 | 功能 |
|------|---------|------|------|
| `logger.py` | 🟢 核心 | ✅ | 日誌系統本身 |
| `window.py` | 🔴 核心 | ✅ | 主視窗、UI 事件 |
| `state_service.py` | 🔴 核心 | ✅ | 狀態管理服務 |
| `state_repository.py` | 🔴 核心 | ✅ | 檔案 I/O、GIF 管理 |
| `chat.py` | 🔴 核心 | ✅ | HTTP 請求、網路錯誤 |
| `chat_orchestrator.py` | 🔴 核心 | ✅ | 聊天協調、錯誤處理 |

---

## ❌ 還沒有日誌的重要模組 (16/22)

### 🔴 高優先級（核心功能，容易出錯）

| 檔案 | 重要程度 | 狀態 | 功能 | 為什麼需要日誌 |
|------|---------|------|------|--------------|
| `chat_controller.py` | 🔴 核心 | ❌ | 聊天控制器 | 配置錯誤、請求失敗 |
| `workers.py` | 🔴 核心 | ❌ | Qt 背景執行緒 | 執行緒錯誤、訊號問題 |
| `movement_manager.py` | 🔴 核心 | ❌ | 移動計算、路徑規劃 | 移動失敗、計算錯誤 |
| `state_dialogs.py` | 🔴 核心 | ❌ | UI 對話框 | 使用者操作、驗證錯誤 |

### 🟡 中優先級（輔助功能）

| 檔案 | 重要程度 | 狀態 | 功能 | 為什麼需要日誌 |
|------|---------|------|------|--------------|
| `bubble_controller.py` | 🟡 中 | ❌ | 對話泡泡顯示 | 顯示錯誤、文字處理 |
| `actions.py` | 🟡 中 | ❌ | 動作解析 | 解析錯誤、無效指令 |
| `cli.py` | 🟡 中 | ❌ | 命令列介面 | 啟動錯誤、參數問題 |

### 🟢 低優先級（工具函數、配置）

| 檔案 | 重要程度 | 狀態 | 功能 |
|------|---------|------|------|
| `utils.py` | 🟢 低 | ❌ | 工具函數 |
| `prompts.py` | 🟢 低 | ❌ | 提示詞管理 |
| `theme.py` | 🟢 低 | ❌ | 主題設定 |
| `themed_menu.py` | 🟢 低 | ❌ | 選單樣式 |
| `paths.py` | 🟢 低 | ❌ | 路徑常數 |
| `models.py` | 🟢 低 | ❌ | 資料模型 |
| `state_models.py` | 🟢 低 | ❌ | 狀態模型 |
| `config_defaults.py` | 🟢 低 | ❌ | 預設配置 |
| `__init__.py` | 🟢 低 | ❌ | 套件初始化 |

---

## 📈 覆蓋率統計

```
總檔案數：     22
已有日誌：     6  (27%)
缺少日誌：     16 (73%)

核心模組覆蓋率：6/10 (60%)
重要功能覆蓋：  ⚠️ 部分覆蓋
```

---

## 🎯 建議優先加入日誌的模組

### 第一優先（立即加入）
1. **`chat_controller.py`**
   - 管理聊天設定、歷史
   - 啟動請求、處理回應
   - **你遇到的問題就在這裡**

2. **`workers.py`**
   - Qt 執行緒執行 HTTP 請求
   - 訊號發送、錯誤傳遞
   - **程式關閉可能跟這個有關**

3. **`movement_manager.py`**
   - 複雜的移動計算
   - 方向解析、速度計算
   - 容易出現邏輯錯誤

### 第二優先（後續加入）
4. **`state_dialogs.py`** - UI 操作錯誤
5. **`bubble_controller.py`** - 文字顯示問題
6. **`actions.py`** - 指令解析錯誤

---

## 🔍 當前日誌覆蓋的錯誤類型

### ✅ 已覆蓋
- 📁 檔案 I/O 錯誤（state_repository）
- 🔒 路徑遍歷攻擊（state_repository）
- 🌐 HTTP 網路錯誤（chat）
- 📝 JSON 解析錯誤（state_repository, chat）
- 🎯 狀態變更事件（state_service）
- 🖼️ GIF 載入錯誤（state_repository）

### ❌ 未覆蓋
- ⚙️ 聊天控制器配置錯誤（chat_controller）
- 🧵 Qt 執行緒錯誤（workers）
- 🚶 移動計算錯誤（movement_manager）
- 🖱️ UI 操作錯誤（state_dialogs）
- 💬 對話泡泡錯誤（bubble_controller）
- 🎬 動作解析錯誤（actions）

---

## 💡 下一步行動

1. **立即加入** `chat_controller.py` 和 `workers.py` 的日誌
   - 這兩個最可能導致你遇到的「程式直接關閉」問題

2. **接著加入** `movement_manager.py`
   - 複雜邏輯，容易出錯

3. **選擇性加入** 其他模組
   - 根據實際遇到的問題決定

---

## 🎯 快速加入日誌模板

對於還沒有日誌的檔案，加入這段：

```python
# 在檔案開頭加入
from .logger import get_logger

logger = get_logger(__name__)

# 在關鍵位置加入
logger.info("操作成功訊息")
logger.warning("警告訊息")
logger.error("錯誤訊息")
logger.debug("除錯訊息")
```

---

## ✨ 總結

**現況：** 27% 的檔案有日誌，核心功能 60% 覆蓋

**建議：** 優先加入 `chat_controller.py`、`workers.py`、`movement_manager.py`

**目標：** 核心模組 100% 覆蓋，總覆蓋率 50%+

---

*最後更新：2025-11-18*
