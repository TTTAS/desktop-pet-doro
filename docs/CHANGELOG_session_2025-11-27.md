# 改動紀錄 - 2025-11-27

## 📋 本次 Session 完成項目

### 1. ✅ 修復 Pytest 錯誤（3 個 import 錯誤）

**問題：**
- `test_logging.py`: ModuleNotFoundError for `doro_app.logger`
- `test_validator.py`: FileNotFoundError for validator.py path
- `test_design_tokens.py`: ModuleNotFoundError for `doro_app.ui.design_tokens`

**修復：**
- 更新 import 路徑至正確位置：
  - `doro_app.logger` → `doro_app.utils.logger`
  - `doro_app.ui.design_tokens` → `doro_app.ui.rendering.design_tokens`
  - `doro_app.state_service` → `doro_app.core.state.service`

**修改檔案：**
- `tests/manual/test_logging.py`
- `tests/manual/test_validator.py`
- `tests/ui/test_design_tokens.py`

---

### 2. ✅ 修復集成測試失敗（9/10 測試失敗）

**問題：**
- Repository 初始化使用目錄而非檔案路徑
- 重複創建 walking state
- 使用不存在的欄位名 `bob_frequency`
- 測試斷言未考慮 `direction="any"` 的情況

**修復：**
```python
# Before (錯誤):
state_repo = StateRepository(temp_state_dir)

# After (正確):
state_repo = StateRepository(temp_state_dir / "states.json")
```

**關鍵修改：**
- StateRepository、MoveStateRepository、TransitionStateRepository 必須傳入檔案路徑，不是目錄
- 修正測試使用正確的欄位名 `scale_amplitude`
- 修正 direction 匹配邏輯測試

**修改檔案：**
- `tests/integration/test_state_lifecycle.py`

---

### 3. ✅ 修復 Validator 測試

**問題：**
- 測試使用無效 state name，但 validator 已不再檢查 state name（設計變更）
- Module loading 觸發 PySide6 import 導致錯誤

**修復：**
- 改用無效 movement direction 測試 validator
- 使用 `importlib.util` 直接載入模組，避免觸發 `__init__.py` 的 PySide6 imports

**修改檔案：**
- `tests/manual/test_validator.py`

---

### 4. ✅ 外部化 Movement Instruction Text

**問題：**
- `MovementManager.instruction_text()` 有 22 行硬編碼的指令文字
- 每次修改需要編輯程式碼

**解決方案：**
- 創建 `movement_instruction.txt` 檔案
- 使用 `{{STEP}}` placeholder 動態替換步數值
- 簡化 `instruction_text()` 為 3 行載入邏輯

**新增檔案：**
- `doro_app/core/chat/movement_instruction.txt`

**修改檔案：**
- `doro_app/utils/paths.py` - 新增 `MOVEMENT_INSTRUCTION_PATH`
- `doro_app/core/movement/manager.py` - 從檔案載入指令

**實作：**
```python
def instruction_text(self) -> str:
    """Load movement instruction text from file and replace {{STEP}} placeholder."""
    step = max(12, self._movement_step_px)
    template = load_prompt_text(MOVEMENT_INSTRUCTION_PATH)
    return template.replace("{{STEP}}", str(step))
```

---

### 5. ✅ TransitionPlayer 整合調查

**發現問題：**
- TransitionPlayer 類別已完整實現
- `transitions.json` 已定義 `idle → stand` transition
- `standing_up.gif` 檔案存在
- **但 `Window._on_controller_state_changed()` 從未調用 TransitionPlayer！**

**根本原因：**
`window.py:315-330` 直接載入目標 GIF，跳過 transition 檢查

**文檔產出：**
- `docs/TODO_transition_player.md` - 實作清單

---

## 📊 測試結果

### Before
- ❌ 3 個 collection errors
- ❌ 9/10 集成測試失敗
- ❌ 1 個 validator 測試失敗

### After
- ✅ 所有 import errors 解決
- ✅ 10/10 集成測試通過
- ✅ Validator 測試通過

---

## 🔍 技術發現

### 1. Repository Pattern
所有 Repository 類別期望**檔案路徑**而非目錄：
```python
StateRepository(config_path: Path)  # 必須是 .json 檔案
```

### 2. Transition Matching 優先級
已在 `doro_app/core/state/models.py:333-382` 實現：
1. **專屬→專屬** (exact match) - 最高優先級
2. **專屬→any** (from_state → "*")
3. **any→專屬** ("*" → to_state)
4. **any→any** ("*" → "*") - 最低優先級

測試位置：`tests/core/state/test_transition_matching.py`

### 3. LLM API Pattern
- LLM APIs 是 stateless，每次請求必須發送完整上下文
- 包含：system prompt + history + 當前訊息
- 本地 LMStudio 免費，不需擔心 token 成本

### 4. Placeholder Pattern
專案使用 `{{PLACEHOLDER}}` 模式動態替換內容：
- `{{STEP}}` - movement step 像素值
- `{{STATE_LIST}}` - 可用 state 列表

---

## 📝 Commits

1. `16f731b` - Refactor: Move movement instruction text to external file
2. `4c754b2` - Fix test_retry_prompt_building in manual validator tests
3. `f7804d1` - Fix all 9 failing integration tests in test_state_lifecycle.py
4. `e3e6712` - Fix pytest import errors in test files
5. `bdc93a0` - Add concise TODO for TransitionPlayer integration

---

## 🎯 待辦事項

見 `docs/TODO_transition_player.md` - 需要實作 TransitionPlayer 在 Window 的整合

---

## 📚 相關檔案

### 測試檔案
- `tests/manual/test_logging.py`
- `tests/manual/test_validator.py`
- `tests/ui/test_design_tokens.py`
- `tests/integration/test_state_lifecycle.py`
- `tests/core/state/test_transition_matching.py`

### 核心檔案
- `doro_app/utils/paths.py`
- `doro_app/core/movement/manager.py`
- `doro_app/core/chat/movement_instruction.txt` (新增)
- `doro_app/core/state/models.py` (transition matching)
- `doro_app/core/state/transition_player.py` (待整合)
- `doro_app/ui/window.py` (待修改)

### 配置檔案
- `doro_app/res/ACTION/TRANSITION/transitions.json`
- `doro_app/res/ACTION/TRANSITION/standing_up.gif`

### 文檔
- `docs/TODO_transition_player.md` (新增)
- `docs/ARCHITECTURE.md` (參考)
