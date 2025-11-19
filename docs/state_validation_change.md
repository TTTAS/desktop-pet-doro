# 狀態驗證行為變更

## 問題
用戶回報：當 LLM 使用不存在的狀態時，會顯示錯誤訊息並阻止對話顯示。

```
Response validation failed: Invalid state(s): HAPPY. Available states: idle, stand
```

## 用戶需求
- 即使狀態不存在，也要讓 doro 說話
- 如果狀態不存在，就保持當前狀態（通常是 idle）
- 不要顯示錯誤訊息

## 解決方案

### 修改前的行為
```
LLM 返回: "(HAPPY) 你好呀～"
    ↓
Validator: HAPPY 不在 StateService 中 → 驗證失敗 ❌
    ↓
重試 2 次 → 仍然失敗
    ↓
顯示錯誤對話框 ❌
    ↓
對話內容不顯示 ❌
```

### 修改後的行為
```
LLM 返回: "(HAPPY) 你好呀～"
    ↓
Validator: 跳過狀態驗證 → 驗證通過 ✅
    ↓
Orchestrator 處理:
  - _find_state_for_action("HAPPY") → None（找不到）
  - 不執行狀態切換
  - 保持當前狀態
    ↓
顯示對話: "你好呀～" ✅
```

## 代碼變更

### doro_app/core/chat/validator.py

**移除**:
- 狀態存在性檢查（87-97 行）
- 無效狀態錯誤返回（116-121 行）

**保留**:
- ✅ 空響應檢查
- ✅ 移動方向驗證
- ✅ 對話內容檢查

**修改後的驗證邏輯**:
```python
def validate(self, response: str) -> ValidationResult:
    # 1. 檢查是否為空
    if not response or not response.strip():
        return ValidationResult.failure("Response is empty")

    # 2. 檢查狀態令牌是否存在（但不驗證是否有效）
    for kind, token in actions:
        if kind == "paren":
            has_state = True  # 只標記存在，不驗證

    # 3. 驗證移動方向（仍然驗證）
    if invalid_directions:
        return ValidationResult.failure(...)

    # 4. 驗證通過
    return ValidationResult.success(...)
```

## 依賴的現有邏輯

這個修改依賴於 Orchestrator 的現有行為：

**doro_app/core/chat/orchestrator.py:166**
```python
state_key = self._window._find_state_for_action(token)
if state_key:  # 只有找到狀態時才切換
    self._state_service.set_state(state_key)
# 如果找不到（None），就不切換，保持當前狀態
```

## 影響

### ✅ 正面影響
- 用戶不會再看到狀態錯誤訊息
- 對話內容總是會顯示
- 無效狀態會被靜默忽略（保持當前狀態）
- 仍然驗證移動方向（防止無效移動）

### ⚠️ 注意事項
- LLM 使用錯誤狀態不會被糾正
- 如果 prompt 和 StateService 不同步，狀態切換可能不符合預期
- 但對話內容仍然正常顯示

### 🔍 仍然驗證的項目
1. **響應非空**: 空響應仍會觸發重試
2. **移動方向**: 無效方向（如 "diagonal"）仍會觸發重試
3. **對話內容**: 確保有實際對話文本

## 測試場景

### 場景 1：LLM 使用不存在的狀態
```
輸入: "跟我打招呼"
LLM: "(HAPPY) 嗨～人你好呀～"
結果: ✅ 顯示 "嗨～人你好呀～"
狀態: 保持當前狀態（idle）
錯誤: 無
```

### 場景 2：LLM 使用存在的狀態
```
輸入: "我好累"
LLM: "(idle) 人累的話就休息一下吧～"
結果: ✅ 顯示 "人累的話就休息一下吧～"
狀態: 切換到 idle
錯誤: 無
```

### 場景 3：LLM 使用無效移動方向
```
輸入: "動一下"
LLM: "(idle) 好呀～ [MOVE:dir=diagonal;distance=50]"
結果: ❌ 驗證失敗
錯誤: "Invalid movement direction(s): diagonal"
行為: 重試（最多 2 次）
```

### 場景 4：LLM 返回空響應
```
輸入: "在嗎"
LLM: ""
結果: ❌ 驗證失敗
錯誤: "Response is empty"
行為: 重試（最多 2 次）
```

## 未來改進建議

### 選項 A：動態同步狀態到 Prompt
自動將 StateService 中的狀態列表寫入 prompt，確保 LLM 只使用存在的狀態。

### 選項 B：添加缺失的狀態
在 StateService 中創建 prompt 提到的所有狀態（HAPPY, SAD, SHY 等）。

### 選項 C：使用 JSON Schema
如果 LM Studio 支持，升級到結構化輸出，100% 保證格式正確。

## 提交信息

```
commit f10c6a9
fix: disable state validation to allow fallback behavior

取消狀態驗證，允許使用不存在的狀態（自動 fallback 到當前狀態）
```
