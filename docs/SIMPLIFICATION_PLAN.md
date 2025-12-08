# Doro 簡化計畫

**目標**：在保持核心功能的前提下，大幅降低複雜度，讓代碼更容易維護和理解。

**預計時間**：1-2 個週末（12-16 小時）

**原則**：
- ✅ 保留：核心功能（顯示 GIF、狀態切換、LLM 聊天、移動）
- ✅ 保留：清晰的架構（3 層分離、事件驅動）
- ❌ 移除：過度抽象（Repository、Protocol、3 種狀態類型）
- ❌ 簡化：上帝類（StateService 740 行 → 300 行）
- ❌ 清理：文檔過多（30 份 → 5 份）

---

## Phase 0: 修復 Transition（最優先）⚠️

**問題**：TransitionPlayer 存在但從未被調用，從 idle → stand 時不會播放 standing_up.gif

**根本原因**：`window.py:331-346` 的 `_on_controller_state_changed()` 直接加載目標 GIF，跳過了檢查 transition

**預計時間**：2 小時

### TODO:

#### 1. 修改 `Window._on_controller_state_changed()` (window.py:331-346)
- [ ] 添加實例變數 `self._previous_state_key: Optional[str] = None` 到 `__init__`
- [ ] 在方法開始處保存舊狀態：`old_state_key = self._previous_state_key`
- [ ] 更新當前狀態：`self._previous_state_key = state_key`
- [ ] 跳過初始加載（沒有 previous state）：`if old_state_key is None:`
- [ ] 跳過相同狀態：`if old_state_key == state_key:`
- [ ] 檢查是否有 transition：`transition = self._state_service.find_transition(old_state_key, state_key)`
- [ ] 如果有 transition：調用 `self._transition_player.play_transition(old_state_key, state_key)`
- [ ] 如果沒有 transition：直接加載 GIF（保持現有邏輯）

#### 2. 提取 GIF 加載邏輯到 helper 方法
- [ ] 創建 `_load_state_gif(state_key: str)` 方法
- [ ] 搬移現有的 GIF 加載邏輯（lines 342-346）到這個方法
- [ ] 在 `_on_controller_state_changed()` 中調用（無 transition 時）
- [ ] 在 `_on_transition_completed()` 中調用（已經實現，line 573-577）

#### 3. 測試計畫
- [ ] **手動測試 1**：切換 idle → stand（應該看到 standing_up.gif）
- [ ] **手動測試 2**：切換 idle → HAPPY（無 transition，直接加載）
- [ ] **手動測試 3**：快速切換狀態（應該被 lock 阻止或排隊）
- [ ] **手動測試 4**：初始啟動（應該直接加載，不播放 transition）

### 預期結果：
- ✅ Transition 動畫正常播放
- ✅ 無 transition 的狀態切換仍然正常
- ✅ 初始啟動不會出錯
- ✅ 不會有併發問題

---

## Phase 1: 合併 3 種狀態成 1 種

**問題**：State、MoveState、TransitionState 三個類型增加了不必要的複雜度

**目標**：只保留一個 `State` 類，用可選欄位表示不同特性

**預計時間**：3-4 小時

### TODO:

#### 1. 設計新的統一 State 模型
- [ ] 在 `doro_app/core/state/models.py` 設計新的 `State` dataclass：
  ```python
  @dataclass(frozen=True)
  class State:
      key: str
      label: str
      visual: VisualConfig

      # 移動相關（原 MoveState）
      movement: Optional[MovementConfig] = None

      # 轉場相關（原 TransitionState）
      transitions_from: Optional[dict[str, str]] = None  # {target_state: gif_id}
  ```
- [ ] 設計 `MovementConfig` 和 `TransitionConfig` 作為嵌套配置
- [ ] 確保向後兼容（能讀取現有 JSON）

#### 2. 更新 JSON 配置格式
- [ ] 修改 `states.json` 格式，加入可選的 `movement` 和 `transitions_from` 欄位
- [ ] 創建遷移腳本 `scripts/migrate_states.py`：
  - 讀取現有的 `states.json`, `move_states.json`, `transitions.json`
  - 合併成新的 `states.json` 格式
  - 備份舊文件到 `states.json.backup`
- [ ] 手動執行遷移腳本
- [ ] 驗證新格式正確

#### 3. 更新 StateService
- [ ] 移除 `_move_states: MoveStateCollection`
- [ ] 移除 `_transitions: TransitionStateCollection`
- [ ] 更新 `get_move_state(key)` → 從 `State.movement` 獲取
- [ ] 更新 `find_transition(from, to)` → 從 `State.transitions_from` 獲取
- [ ] 移除對 `MoveStateRepository` 和 `TransitionStateRepository` 的依賴
- [ ] 更新所有引用這些方法的地方

#### 4. 刪除不再需要的類
- [ ] 刪除 `MoveState` class 定義
- [ ] 刪除 `TransitionState` class 定義
- [ ] 刪除 `MoveStateCollection` class
- [ ] 刪除 `TransitionStateCollection` class
- [ ] 更新所有 import

#### 5. 更新測試
- [ ] 修改 `tests/core/state/test_models.py` 測試新的統一 State
- [ ] 刪除 MoveState 和 TransitionState 的測試
- [ ] 更新 StateService 測試
- [ ] 確保測試覆蓋率不下降

#### 6. 更新 UI 和其他引用
- [ ] 搜尋所有 `MoveState` 引用並更新
- [ ] 搜尋所有 `TransitionState` 引用並更新
- [ ] 測試 UI 對話框（AddStateDialog、StateManagerDialog）

### 預期結果：
- ✅ 只有一個 State 類
- ✅ JSON 配置合併成一個文件
- ✅ 所有功能正常運作
- ✅ 代碼更容易理解

**行數變化預估**：
- `models.py`: 392 行 → 250 行 (-142)
- `service.py`: 740 行 → 650 行 (-90)

---

## Phase 2: 移除 Repository 抽象，直接用 JSON

**問題**：Repository 模式對個人工具來說是過度設計，增加了不必要的間接層

**目標**：直接讀寫 JSON，簡化持久化邏輯

**預計時間**：3-4 小時

### TODO:

#### 1. 創建簡單的 JSON 工具
- [ ] 在 `doro_app/utils/json_store.py` 創建簡單的 JSON 讀寫函數：
  ```python
  def load_json(path: Path) -> dict:
      """Load JSON with error handling"""

  def save_json(path: Path, data: dict):
      """Save JSON with atomic write"""
  ```
- [ ] 添加基本錯誤處理（FileNotFoundError、JSONDecodeError）
- [ ] 添加原子寫入（寫到臨時文件再重命名）

#### 2. 在 StateService 中直接使用 JSON
- [ ] 移除 `state_repo: StateRepository` 依賴
- [ ] 添加 `states_json_path: Path` 參數
- [ ] 在 `__init__` 中直接加載：`self._states = self._load_states_from_json()`
- [ ] 實現 `_load_states_from_json() -> StateCollection` 方法
- [ ] 實現 `_save_states_to_json()` 方法
- [ ] 更新 `add_state()` / `remove_state()` 直接調用 `_save_states_to_json()`

#### 3. 刪除 Repository 類
- [ ] 刪除 `repository.py` 中的 `StateRepository` 類
- [ ] 刪除 `MoveStateRepository` 類（Phase 1 已不需要）
- [ ] 刪除 `TransitionStateRepository` 類（Phase 1 已不需要）
- [ ] 保留 `GifRepository`（仍然有用，處理文件系統掃描）
- [ ] 考慮重命名 `repository.py` → `gif_store.py`

#### 4. 更新 DoroApp 初始化
- [ ] 修改 `doro_app/app.py` 的依賴注入
- [ ] 移除創建 Repository 的代碼
- [ ] 傳入 JSON 路徑而非 Repository 實例
- [ ] 簡化依賴圖

#### 5. 更新測試
- [ ] 刪除 `tests/core/state/test_repository.py`（不再需要）
- [ ] 更新 `tests/core/state/test_service.py`：
  - 使用 `tmp_path` 創建臨時 JSON 文件
  - 移除 Repository mock
- [ ] 簡化測試 fixtures

#### 6. 更新 GifManager
- [ ] 檢查 `gif_manager.py` 是否依賴 Repository
- [ ] 如果是，改為直接使用 `GifRepository`（重命名後的 `gif_store.py`）

### 預期結果：
- ✅ 沒有 Repository 抽象層
- ✅ 直接、清晰的 JSON 讀寫
- ✅ 更容易理解的持久化邏輯
- ✅ 測試更簡單

**行數變化預估**：
- 刪除 `repository.py`: ~480 行（StateRepository + MoveStateRepository + TransitionStateRepository）
- 新增 `json_store.py`: ~50 行
- `service.py`: 650 行 → 550 行 (-100)
- **總計減少**: ~530 行

---

## Phase 3: 精簡 StateService 到 300 行

**問題**：StateService 仍然是 740 行的上帝類，即使 Phase 1-2 完成後也還有 550 行

**目標**：進一步提取或簡化，目標 300 行以內

**預計時間**：4-5 小時

### TODO:

#### 1. 分析 StateService 職責
- [ ] 列出 StateService 所有公開方法
- [ ] 分類：
  - **核心職責**：狀態管理（add/remove/get/set state）
  - **GIF 管理**：GIF 路徑解析、加載（應該屬於 GifManager）
  - **Transition 協調**：查找 transition（應該屬於 TransitionCoordinator）
  - **回調管理**：on_state_changed 等（應該簡化）

#### 2. 將 GIF 相關邏輯全部搬到 GifManager
- [ ] 識別所有 `get_gif_*` 方法
- [ ] 搬移到 `GifManager`：
  - `get_gif_id(state_key)` → `GifManager.get_state_gif_id(state_key)`
  - `get_gif_path_by_id(gif_id)` → `GifManager.get_gif_path(gif_id)`
  - `store_gif(...)` → `GifManager.store_gif(...)`
- [ ] StateService 保留對 GifManager 的引用
- [ ] 更新所有調用處（主要是 Window）

#### 3. 將 Transition 邏輯全部搬到 TransitionCoordinator
- [ ] 確認 `find_transition(from, to)` 已經在 TransitionCoordinator
- [ ] StateService 只保留對 TransitionCoordinator 的引用
- [ ] 簡化 StateService 中的 transition 相關代碼

#### 4. 簡化回調機制
- [ ] 當前：多個回調 (`on_state_changed`, `on_state_list_updated`, etc.)
- [ ] 簡化為：單一 `on_change` 回調，傳遞 event 類型
- [ ] 或者：移除回調，直接用 Qt Signal（在 StateController 中）
- [ ] 評估哪個更簡單，選擇一個

#### 5. 內聯簡單方法
- [ ] 查找只有 1-2 行的 helper 方法
- [ ] 如果只被調用一次，內聯到調用處
- [ ] 減少不必要的方法數量

#### 6. 移除死代碼
- [ ] 用 Grep 搜尋所有 public 方法
- [ ] 檢查每個方法是否真的被使用
- [ ] 刪除未使用的方法
- [ ] 刪除相關測試

#### 7. 重新組織 StateService 文件結構
- [ ] 清晰的區塊註解：
  ```python
  class StateService:
      # ═══ Initialization ═══

      # ═══ State Management (CRUD) ═══

      # ═══ State Queries ═══

      # ═══ State Changes ═══

      # ═══ Persistence ═══
  ```
- [ ] 每個區塊不超過 50 行

#### 8. 更新測試
- [ ] 測試搬移的 GIF 方法（在 GifManager 測試中）
- [ ] 測試搬移的 Transition 方法（在 TransitionCoordinator 測試中）
- [ ] 精簡 StateService 測試，只測核心邏輯

### 預期結果：
- ✅ StateService < 300 行
- ✅ 職責單一：只管理狀態
- ✅ GIF 邏輯在 GifManager
- ✅ Transition 邏輯在 TransitionCoordinator
- ✅ 代碼清晰易讀

**行數變化預估**：
- `service.py`: 550 行 → 280 行 (-270)
- `gif_manager.py`: +50 行（新增方法）
- `transition_coordinator.py`: +20 行（新增方法）

---

## Phase 4: 簡化 DoroWindow

**問題**：DoroWindow 還是 679 行，混合了太多職責

**目標**：提取明顯可分離的邏輯，目標 400-450 行

**預計時間**：3-4 小時

### TODO:

#### 1. 提取 Menu 處理邏輯
- [ ] 創建 `doro_app/ui/helpers/menu_builder.py`
- [ ] 實現 `MenuBuilder` 類：
  ```python
  class MenuBuilder:
      def build_context_menu(self, parent) -> QtWidgets.QMenu:
          """Build and return context menu"""
  ```
- [ ] 搬移所有 menu 相關方法：
  - `_create_menu_action()`
  - `_open_state_manager_dialog()`
  - `_open_move_state_manager_dialog()`
  - 等等
- [ ] Window 只保留：`self._menu_builder = MenuBuilder(...)` 和調用

#### 2. 提取事件分發邏輯（可選）
- [ ] 評估是否值得提取 `mousePressEvent()`, `mouseMoveEvent()` 等
- [ ] 如果這些方法很簡單（1-2 行），保持原樣
- [ ] 如果複雜，考慮創建 `EventDispatcher`

#### 3. 清理 Config 遺留代碼
- [ ] 搜尋所有 `self._config` (QSettings) 引用
- [ ] 確保都已遷移到 `self._config_manager`
- [ ] 刪除所有 QSettings fallback 代碼（lines 318-321 等）
- [ ] 刪除 `_config: QSettings` 實例變數

#### 4. 內聯簡單 helper
- [ ] 查找只有 1-2 行的 helper 方法
- [ ] 內聯到調用處（如果只調用一次）

#### 5. 重新組織文件結構
- [ ] 使用清晰的區塊註解
- [ ] 相關方法放在一起
- [ ] 減少上下跳轉

### 預期結果：
- ✅ DoroWindow: 679 行 → 450 行 (-229)
- ✅ Menu 邏輯獨立
- ✅ Config 遷移完成
- ✅ 更容易找到代碼

---

## Phase 5: 清理測試和文檔

**問題**：測試覆蓋率高但 UI 測試被禁用；文檔 30 份但沒有 README

**目標**：保持有用的測試，刪除冗餘測試；精簡文檔到 5 份核心文件

**預計時間**：2-3 小時

### TODO:

#### 1. 清理測試
- [ ] 刪除不再存在的類的測試：
  - `tests/core/state/test_repository.py`（Phase 2 已刪除 Repository）
  - MoveState / TransitionState 相關測試（Phase 1 已合併）
- [ ] 降低測試覆蓋率目標：85% → 70%（個人工具夠用了）
- [ ] 刪除 `tests/manual/` 目錄（手動測試不該提交）
- [ ] UI 測試保持禁用（加註解說明原因）

#### 2. 精簡文檔到 5 份核心文件
- [ ] **保留**：
  1. `README.md`（新建，最重要！）
  2. `ARCHITECTURE.md`（簡化版，合併 V2 內容）
  3. `DEVELOPMENT.md`（合併 TESTING.md 和開發指南）
  4. `CHANGELOG.md`（保留版本歷史）
  5. `BACKLOG.md`（未來改進項目）

- [ ] **刪除**（共 25 份）：
  - `PHASE*.md`（所有 Phase 文檔，已完成）
  - `REFACTORING_PLAN.md`（已完成）
  - `STATE_SERVICE_SPLIT_PLAN.md`（已完成）
  - `ARCHITECTURE_AUDIT.md`（已過時）
  - `ARCHITECTURE_PROPOSAL_V2.md`（合併到 ARCHITECTURE.md）
  - `CONFIG_AUDIT.md`（已完成遷移）
  - `ERROR_HANDLING_AUDIT.md`（已過時）
  - `CHANGELOG_session_*.md`（所有 session 記錄）
  - `TODO_*.md`（所有 TODO 文檔）
  - `chat_request_execution_todo.md`（優先級低）

#### 3. 寫 README.md（最重要！）
- [ ] **What is it?**
  - 1-2 句話描述
  - 截圖（如果有的話）

- [ ] **Installation**
  ```bash
  # 克隆
  git clone ...
  cd doro-exp-

  # 安裝依賴
  pip install -e ".[dev]"

  # 配置 LLM endpoint（重要！）
  # 編輯 config.json 或通過 UI 設定
  ```

- [ ] **Quick Start**
  ```bash
  # 運行
  python -m doro_app

  # 右鍵菜單可以：
  # - 切換狀態
  # - 管理狀態
  # - 聊天
  ```

- [ ] **Configuration**
  - LLM server URL
  - GIF 資源位置
  - 狀態配置文件

- [ ] **Development**
  ```bash
  # 運行測試
  pytest

  # 代碼格式化
  black .
  ruff check .
  ```

- [ ] **Architecture**
  - 簡單的架構圖或說明
  - 連結到 ARCHITECTURE.md

#### 4. 更新 ARCHITECTURE.md
- [ ] 合併 ARCHITECTURE_PROPOSAL_V2.md 的好內容
- [ ] 刪除過時的內容
- [ ] 保持簡潔（< 300 行）
- [ ] 重點：
  - 3 層架構
  - 事件驅動
  - 核心類職責
  - 依賴關係圖

#### 5. 創建 DEVELOPMENT.md
- [ ] 合併 TESTING.md 內容
- [ ] 開發環境設置
- [ ] 測試指南
- [ ] 代碼風格
- [ ] 如何貢獻（如果開源的話）

### 預期結果：
- ✅ 文檔從 30 份 → 5 份
- ✅ 有清晰的 README.md
- ✅ 測試保持 70% 覆蓋率（足夠）
- ✅ 刪除冗餘測試

---

## Phase 6: 最終驗證和清理

**目標**：確保所有改動都正常工作，沒有破壞功能

**預計時間**：1-2 小時

### TODO:

#### 1. 運行完整測試套件
- [ ] `pytest` - 確保所有測試通過
- [ ] `black --check .` - 確保格式正確
- [ ] `ruff check .` - 確保沒有 linting 錯誤

#### 2. 手動功能測試
- [ ] 啟動應用
- [ ] 測試狀態切換（有 transition 和無 transition）
- [ ] 測試 LLM 聊天
- [ ] 測試移動功能
- [ ] 測試添加/刪除狀態
- [ ] 測試配置保存和加載

#### 3. 代碼質量檢查
- [ ] 運行 `cloc` 統計代碼行數
- [ ] 確認達到目標：
  - StateService < 300 行
  - DoroWindow < 450 行
  - 總行數減少 > 1000 行
- [ ] 檢查是否有死代碼（未使用的 import、方法）

#### 4. 提交和文檔
- [ ] 每個 Phase 創建單獨的 commit
- [ ] Commit message 清晰描述改動
- [ ] 更新 CHANGELOG.md
- [ ] 添加簡化前後的對比數據

#### 5. 創建 Release Tag
- [ ] 如果所有測試通過，創建 `v0.2-simplified` tag
- [ ] 推送到遠端
- [ ] 慶祝！🎉

---

## 總結：簡化前後對比

### 代碼行數（預估）

| 文件 | 簡化前 | 簡化後 | 變化 |
|-----|--------|--------|------|
| `core/state/models.py` | 392 | 250 | -142 |
| `core/state/service.py` | 740 | 280 | -460 |
| `core/state/repository.py` | 568 | 刪除 | -568 |
| `ui/window.py` | 679 | 450 | -229 |
| `utils/json_store.py` | 0 | 50 | +50 |
| **總計** | **~2,379** | **~1,030** | **-1,349 (-57%)** |

### 文件數量

| 類別 | 簡化前 | 簡化後 | 變化 |
|-----|--------|--------|------|
| 核心代碼 | ~30 | ~25 | -5 |
| 測試 | ~40 | ~30 | -10 |
| 文檔 | 30 | 5 | -25 |
| **總計** | **~100** | **~60** | **-40 (-40%)** |

### 複雜度

| 指標 | 簡化前 | 簡化後 |
|-----|--------|--------|
| 狀態類型 | 3 種 | 1 種 |
| JSON 配置文件 | 3 個 | 1 個 |
| Repository 類 | 3 個 | 0 個 |
| 上帝類（>500 行）| 2 個 | 0 個 |

### 可維護性

| 方面 | 簡化前 | 簡化後 |
|-----|--------|--------|
| 新手友好度 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 3 個月後還看得懂 | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 修改一個功能需要改幾個文件 | 5-7 | 2-3 |
| 有 README | ❌ | ✅ |

---

## 執行建議

### 執行順序
1. **Phase 0** - 先修好 transition（2 小時）
2. **測試** - 確保 transition 正常
3. **Phase 1** - 合併狀態類型（3-4 小時）
4. **測試** - 確保功能正常
5. **Phase 2** - 移除 Repository（3-4 小時）
6. **測試** - 確保持久化正常
7. **Phase 3** - 精簡 StateService（4-5 小時）
8. **測試** - 完整功能測試
9. **Phase 4** - 簡化 DoroWindow（3-4 小時）
10. **Phase 5** - 清理文檔和測試（2-3 小時）
11. **Phase 6** - 最終驗證（1-2 小時）

### 時間安排（建議）
- **週末 1 (週六)**：Phase 0 + 1 + 2（8 小時）
- **週末 1 (週日)**：Phase 3 + 4（8 小時）
- **週末 2 (週六)**：Phase 5 + 6（4 小時）+ 休息

### 檢查點
- 每個 Phase 完成後運行測試
- 每個 Phase 提交一次 Git commit
- 如果測試失敗，回退到上一個 commit
- **不要跳過測試！**

### 如果時間不夠
優先級排序：
1. **必做**：Phase 0（修復 bug）
2. **必做**：Phase 5.3（寫 README）
3. **高優先級**：Phase 1、2（簡化架構）
4. **中優先級**：Phase 3、4（精簡代碼）
5. **低優先級**：Phase 5.1、5.2（清理文檔測試）

---

## 風險和注意事項

### 可能的問題
1. **Transition 修復失敗**
   - 風險：可能影響現有的狀態切換
   - 緩解：仔細測試，保留回滾點

2. **JSON 格式遷移失敗**
   - 風險：可能丟失現有狀態配置
   - 緩解：先備份所有 JSON 文件

3. **測試大量失敗**
   - 風險：重構破壞了功能
   - 緩解：每個 Phase 都要確保測試通過

4. **花費時間超出預期**
   - 風險：沒有完成所有 Phase
   - 緩解：按優先級執行，可以分多個週末

### 備份計畫
- 開始前創建新分支：`git checkout -b simplification`
- 每個 Phase commit 一次
- 如果失敗，可以回退：`git reset --hard HEAD~1`
- 完成後合併到主分支

---

**準備好了嗎？從 Phase 0 開始吧！🚀**
