# 測試覆蓋率報告

> **生成日期：** 2024-12-11
> **總體覆蓋率：** 30% (1,390 / 4,577 行)
> **測試狀態：** 294 passed, 2 failed

---

## 📊 總覽

```
總代碼行數：4,577 行
已覆蓋行數：1,390 行
未覆蓋行數：3,187 行
覆蓋率：30%
```

### 評級：🔴 需要改進

對於即將進行重構的專案來說，**30% 的覆蓋率非常危險**。

---

## 🎯 分層覆蓋率分析

### UI 層：0-5% 🔴

| 組件 | 行數 | 覆蓋 | 原因 |
|------|------|------|------|
| DoroWindow | 286 | 0% | UI 組件難以測試 |
| BubbleController | 123 | 0% | Qt 組件 |
| StateController | 87 | 0% | Qt 組件 |
| GifController | 76 | 0% | Qt 組件 |
| DialogManager | 38 | 0% | Qt 組件 |
| ClickActionController | 48 | 0% | Qt 組件 |
| ChatDialog | 93 | 0% | Qt 組件 |
| StateManagerDialog | 148 | 0% | Qt 組件 |
| MoveStateManagerDialog | 181 | 0% | Qt 組件 |
| ThemeManager | 16 | 0% | Qt 組件 |

**小計：1,096 行，0% 覆蓋**

---

### 業務邏輯層：混合 🟡🔴

#### 🔴 未覆蓋（關鍵問題）

| 組件 | 行數 | 覆蓋 | 優先級 |
|------|------|------|--------|
| **CoreManager** | 101 | **0%** | 🔴 高 |
| **ChatController** | 293 | **0%** | 🔴 高 |
| **ChatOrchestrator** | 155 | **0%** | 🔴 高 |
| **TransitionPlayer** | 98 | **0%** | 🔴 高 |
| chat.py | 117 | 0% | 🟡 中 |
| MovementManager | 248 | 19% | 🟡 中 |

**問題：** 核心業務邏輯未測試，重構風險極高！

#### 🟢 良好覆蓋

| 組件 | 行數 | 覆蓋 |
|------|------|------|
| GifManager | 24 | 100% ✅ |
| TransitionCoordinator | 47 | 100% ✅ |
| StateService | 283 | 84% ✅ |
| StateParser | 45 | 91% ✅ |
| Models | 171 | 95% ✅ |

---

### 基礎設施層：混合 🟢🔴

#### 🟢 良好覆蓋

| 組件 | 行數 | 覆蓋 |
|------|------|------|
| DoroViewModel | 122 | 100% ✅ |
| DesignTokens | 73 | 100% ✅ |
| Actions | 25 | 100% ✅ |
| ConfigDefaults | 9 | 100% ✅ |
| Paths | 17 | 100% ✅ |
| Models (utils) | 15 | 100% ✅ |
| ConfigManager | 108 | 90% ✅ |
| ConfigSchema | 58 | 97% ✅ |
| Logger | 32 | 91% ✅ |
| Constants | 64 | 91% ✅ |
| Exceptions | 72 | 96% ✅ |
| Validator | 53 | 98% ✅ |

#### 🔴 未覆蓋

| 組件 | 行數 | 覆蓋 |
|------|------|------|
| App | 82 | 0% |
| Bootstrap | 40 | 0% |
| CLI | 65 | 0% |
| Workers | 34 | 0% |

---

## ⚠️ 關鍵風險

### 風險 1：核心業務邏輯未測試

```
CoreManager (0%) → 協調所有業務邏輯
ChatController (0%) → 聊天核心功能
ChatOrchestrator (0%) → 聊天協調
TransitionPlayer (0%) → 狀態轉換動畫
```

**影響：** 如果重構這些組件，無法保證功能不被破壞。

---

### 風險 2：MovementManager 覆蓋率低

```
MovementManager: 19% (48/248 行)
```

**已覆蓋：** 基本初始化
**未覆蓋：** 移動解析、執行、方向計算（200+ 行）

---

### 風險 3：UI 層完全未測試

雖然 UI 層測試困難，但至少應該測試：
- Controller 的邏輯（不需要真實 Qt Widget）
- ViewModel 的狀態管理（已測試 ✅）

---

## ✅ 做得好的地方

### 1. 數據層測試完善

```
GifManager: 100%
TransitionCoordinator: 100%
StateService: 84%
Repository: 54% (部分)
```

**評價：** 數據層測試相對完善，這是好的基礎。

---

### 2. 工具類測試完善

```
Actions: 100%
ConfigManager: 90%
ConfigSchema: 97%
Logger: 91%
Validator: 98%
```

**評價：** 基礎設施測試良好。

---

### 3. Models 測試良好

```
Core Models: 95%
Utils Models: 100%
ViewModel: 100%
```

**評價：** 數據模型測試充分。

---

## 📋 改進建議

### 立即執行（重構前必須）

#### 1. 為 CoreManager 添加測試（優先級：🔴 最高）

```python
# tests/core/test_core_manager.py
def test_core_manager_initialization():
    # 測試 CoreManager 創建

def test_state_changed_signal_emitted():
    # 測試狀態變更信號

def test_chat_message_delegation():
    # 測試聊天消息委託
```

**目標覆蓋率：** 0% → 60%+

---

#### 2. 為 ChatController/Orchestrator 添加測試（優先級：🔴 高）

```python
# tests/core/chat/test_controller.py
def test_start_request_with_valid_message():
def test_start_request_rejects_when_inflight():
def test_system_prompt_updates():
```

**目標覆蓋率：** 0% → 70%+

---

#### 3. 為 TransitionPlayer 添加測試（優先級：🔴 高）

```python
# tests/core/state/test_transition_player.py
def test_play_transition_success():
def test_transition_signals_emitted():
def test_transition_lock_prevents_concurrent():
```

**目標覆蓋率：** 0% → 70%+

---

### 短期改進（重構中）

#### 4. 提升 MovementManager 覆蓋率（優先級：🟡 中）

**當前：** 19%
**目標：** 60%+

```python
# tests/core/movement/test_manager.py
def test_parse_movement_token():
def test_handle_move_bracket():
def test_process_active_movement():
def test_direction_inference():
```

---

#### 5. StateService 剩餘部分（優先級：🟡 中）

**當前：** 84%
**目標：** 90%+

**未覆蓋：**
- 部分邊界情況
- 錯誤處理路徑

---

### 長期改進（重構後）

#### 6. UI Controller 邏輯測試

雖然完整的 UI 測試困難，但可以測試 Controller 的邏輯：

```python
# tests/ui/controllers/test_state_controller_logic.py
def test_state_controller_updates_viewmodel():
    # 使用 Mock ViewModel 測試
```

---

## 📈 覆蓋率目標

### 階段性目標

| 階段 | 目標 | 時間 | 關鍵組件 |
|------|------|------|----------|
| **當前** | 30% | - | StateService, Models, Utils |
| **階段 1** | 50% | 1 週 | + CoreManager, ChatController |
| **階段 2** | 60% | 2 週 | + TransitionPlayer, MovementManager |
| **階段 3** | 70% | 1 月 | + Controller 邏輯 |

### 最終目標

```
核心業務邏輯：70%+
數據層：80%+
工具類：90%+
UI 層：20%+ (僅邏輯部分)

總體：60%+
```

---

## 🚨 重構風險評估

### 當前風險等級：🔴 高

**原因：**
1. CoreManager (0%) — 重構會破壞整個架構
2. ChatController/Orchestrator (0%) — 聊天功能無保護
3. TransitionPlayer (0%) — 狀態轉換可能失效
4. MovementManager (19%) — 移動邏輯不可靠

### 建議

**🛑 暫緩大型重構**

在達到以下覆蓋率之前，**不應該進行大規模重構**：
- CoreManager: 60%+
- ChatController: 70%+
- StateService: 保持 80%+

**✅ 可以進行的重構**

1. 配置系統遷移（ConfigManager: 90%）
2. StateService 拆分（當前 84%，但需先提升到 90%）
3. 工具類優化（覆蓋率 90%+）

---

## 📝 測試失敗分析

### 失敗的測試（2 個）

```
FAILED tests/test_smoke.py::TestChatControllerSmoke::test_chat_controller_can_be_created
FAILED tests/test_smoke.py::TestChatControllerSmoke::test_chat_controller_has_basic_properties
```

**錯誤：** `ModuleNotFoundError: No module named 'doro_app.core.chat.controller'`

**原因：** 測試文件導入路徑錯誤或文件結構問題

**修復：** 檢查 `doro_app/core/chat/controller.py` 是否存在

---

## 🎓 教訓

### 1. 測試應該與代碼同步增長

**問題：** 先寫了大量代碼（4577 行），後補測試（30%）

**正確做法：** TDD 或至少在功能完成時立即寫測試

---

### 2. 核心邏輯必須優先測試

**問題：** StateService (84%) 測試良好，但 CoreManager (0%) 完全未測試

**正確做法：** 越核心的組件，越應該優先測試

---

### 3. UI 測試困難不是借口

**問題：** UI 層 0% 覆蓋

**正確做法：**
- 分離 UI 邏輯和視圖邏輯
- 測試 Controller 的邏輯部分
- 使用 Mock 替代真實 Widget

---

## 🔄 下一步行動

### 立即（本週）

1. ✅ 啟用測試覆蓋率報告（已完成）
2. ⏭️ **修復失敗的測試** （ChatController 導入）
3. ⏭️ **為 CoreManager 編寫測試** （目標：60%）
4. ⏭️ **為 ChatController 編寫測試** （目標：70%）

### 短期（2 週內）

5. 為 TransitionPlayer 編寫測試（目標：70%）
6. 提升 MovementManager 覆蓋率（目標：60%）
7. StateService 補充邊界測試（目標：90%）

### 中期（1 月內）

8. 達到總體覆蓋率 60%+
9. 開始安全重構（有測試保護）

---

## 📊 附錄：完整覆蓋率清單

詳見生成的 HTML 報告：`htmlcov/index.html`

---

**報告生成：** 2024-12-11
**下次更新：** 每次測試運行後自動更新
