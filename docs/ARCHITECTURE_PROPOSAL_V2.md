# 架構改進提案 V2（基於現實）

**日期：** 2025-12-02
**狀態：** 提案討論
**版本：** V2（務實版）

---

## 前言：承認現有架構的優點

基於對 `ARCHITECTURE.md` 和 `ARCHITECTURE_AUDIT.md` 的分析，**現有架構其實已經相當不錯**。

### 現有架構的優點 ✅

**1. 清晰的三層設計**
```
FSM 層 (StateService)     → 狀態管理
UI 層 (DoroWindow)        → 視覺呈現
LLM 層 (ChatOrchestrator) → 智能驅動
```

**2. 良好的解耦模式**
```
✅ StateController 使用 Qt Signals
✅ MovementManager 使用 Protocol 模式
✅ StateService 使用 callbacks（保持核心層無 Qt 依賴）
✅ 沒有嚴重的循環依賴
```

**3. 事件驅動**
```python
# StateService → Callback → StateController → Signal → Window
StateService.on_state_changed = callback
StateController.state_changed.emit(state_key)
Window.connect(signal, slot)
```

**4. 已經進行的改進（Phase 4.2）**
```
✅ GifManager 提取（119 行，10 測試）
✅ TransitionCoordinator 提取（181 行，18 測試）
✅ StateParser 提取（141 行，38 測試）
✅ StateService: 809 → 740 行
```

### 實際問題：類的大小，而非架構缺陷

**核心問題診斷：**
- ❌ 不是循環依賴問題（已經用 Signals/Protocol 解決）
- ❌ 不是耦合問題（組件已經很好地分離）
- ✅ **是類過大的問題**（DoroWindow 679 行，StateService 740 行）

---

## 務實改進策略

### 原則：漸進式改進，不推翻現有架構

1. **保留現有模式**：Signals、Protocols、Callbacks
2. **針對性提取**：只提取真正能減少複雜度的部分
3. **避免過度工程**：不引入不必要的抽象
4. **測試驗證**：每步改進都有測試保障

---

## 提案一：DoroWindow 輕量化

### 當前狀態分析

```
DoroWindow (679 lines, 48 methods)
├── MovementWindowPort 實現（4 個方法）✅ 合理
├── Qt 事件處理（8 個方法）✅ 必須在 Window
├── 繪製相關（6 個方法）✅ 必須在 Window
├── 氣泡相關（6 個方法）⚠️ 可部分提取
├── 過渡動畫（2 個方法）⚠️ 已有 TransitionPlayer
├── 選單處理（1 個 contextMenuEvent）⚠️ 可提取邏輯
└── 工具方法（~20 個方法）✅ 大部分合理
```

### 可提取的部分

#### A. MenuHandler（選單處理）

**現狀：contextMenuEvent 包含大量選單邏輯**

**提案：**
```python
# doro_app/ui/menu_handler.py

class MenuHandler:
    """
    Handles menu creation and action dispatch.

    Responsibilities:
    - Create context menu
    - Dispatch menu actions
    - Menu state management

    Does NOT:
    - Know about Window internals
    - Directly manipulate UI
    """

    def __init__(
        self,
        state_service: StateService,
        dialog_manager: DialogManager,
        chat_orchestrator: ChatOrchestrator,
    ):
        self._state_service = state_service
        self._dialog_manager = dialog_manager
        self._chat_orchestrator = chat_orchestrator

    def create_context_menu(
        self,
        parent: QtWidgets.QWidget,
        visible_states: list[str],
        current_state: str,
    ) -> QtWidgets.QMenu:
        """Create the context menu."""
        menu = DoroMenu(parent)

        # Add state menu items
        for state_key in visible_states:
            # ...

        # Add action menus
        # ...

        return menu

    def handle_state_selection(self, state_key: str) -> None:
        """Handle state menu selection."""
        self._state_service.set_state(state_key)

    def handle_ask_doro(self, parent_window) -> None:
        """Handle Ask Doro action."""
        # Show chat dialog
        # ...
```

**預期減少：**
- DoroWindow: ~50-80 行

---

#### B. 氣泡管理整合

**現狀：氣泡邏輯分散**
```
BubbleController (已存在) - 部分邏輯
DoroWindow - 還有一些氣泡處理方法
```

**提案：將剩餘氣泡邏輯移到 BubbleController**
```python
# doro_app/ui/components/bubble_controller.py

class BubbleController:
    """
    Complete bubble management (not just partial).
    """

    # 現有方法...

    def set_text_with_duration(
        self,
        text: str,
        duration_ms: int = 3000,
        show_close_button: bool = False,
    ) -> None:
        """Set bubble text with auto-hide."""
        # ...

    def handle_chat_notification(
        self,
        severity: str,
        message: str,
    ) -> None:
        """Handle chat notifications."""
        # ...
```

**預期減少：**
- DoroWindow: ~30-50 行

---

#### C. 過渡動畫邏輯統一

**現狀：**
```python
# Window 中還有過渡相關方法
def _on_transition_movie_loaded(self, movie, size): ...
def _on_transition_completed(self, target_state_key): ...
```

**提案：這些應該完全在 TransitionPlayer 中**
```python
# doro_app/core/state/transition_player.py

class TransitionPlayer(QtCore.QObject):
    # 現有邏輯...

    # Window 只需連接 signals
    transition_completed = QtCore.Signal(str)
```

**Window 中簡化為：**
```python
# DoroWindow.__init__
self._transition_player.transition_completed.connect(self._finalize_state_change)

def _finalize_state_change(self, target_state_key: str):
    """Finalize state change after transition."""
    # Simple, just update final state
    self._update_display()
```

**預期減少：**
- DoroWindow: ~20-30 行

---

### DoroWindow 改進總計

**提取內容：**
1. MenuHandler（50-80 行）
2. 氣泡管理整合（30-50 行）
3. 過渡動畫統一（20-30 行）

**預期結果：**
```
DoroWindow: 679 → ~500-550 行 (減少 18-26%)
```

**仍保留在 Window：**
- Qt 事件處理（必須）
- 繪製邏輯（必須）
- MovementWindowPort 實現（合理）
- 基本視窗管理（合理）

---

## 提案二：StateService 進一步優化（可選）

### 當前狀態

```
StateService: 740 lines, 47 methods

已提取：
✅ GifManager
✅ TransitionCoordinator
✅ StateParser

可進一步提取：
⚠️ MoveState CRUD（~8 個方法）
⚠️ Transition CRUD（~3 個方法）
```

### 可選提取：領域管理器

**如果需要進一步減小 StateService，可以提取：**

```python
# doro_app/core/state/move_state_manager.py

class MoveStateManager:
    """Manages MoveState CRUD operations."""

    def __init__(self, move_repo: MoveStateRepository):
        self._move_states = MoveStateCollection()
        self._move_repo = move_repo

    def add(self, key: str, state_key: str, direction: str, ...) -> MoveState:
        """Add new move state."""
        # ...

    def remove(self, key: str) -> bool:
        """Remove move state."""
        # ...

    def get(self, key: str) -> Optional[MoveState]:
        """Get move state."""
        return self._move_states.get(key)
```

**預期減少：**
- StateService: ~50-80 行

**評估：**
- ✅ 優點：職責更清晰
- ⚠️ 缺點：增加類數量
- 💡 建議：**可選，非必須**（當前 740 行已可接受）

---

## 提案三：DoroApp 保持不變

### 當前狀態

```python
class DoroApp:
    """
    Composition root - assembles all components.
    """
    def __init__(self):
        # Create components
        # Wire dependencies
```

**評估：137 行，職責清晰**

**決定：不需要改動** ✅

DoroApp 是 Composition Root，它的職責就是組裝組件。這是合理的。

---

## 實施計劃

### Phase A: MenuHandler 提取（2-3 天）

**步驟：**
1. 創建 `MenuHandler` 類
2. 從 DoroWindow.contextMenuEvent 提取選單邏輯
3. Window 簡化為調用 MenuHandler
4. 測試選單功能

**風險：** 低（選單邏輯獨立）

---

### Phase B: 氣泡管理整合（1-2 天）

**步驟：**
1. 擴展 `BubbleController`
2. 移動 Window 中剩餘氣泡方法
3. Window 只保留氣泡顯示委託
4. 測試氣泡功能

**風險：** 低（氣泡邏輯相對獨立）

---

### Phase C: 過渡動畫統一（1-2 天）

**步驟：**
1. 檢查 TransitionPlayer 是否完整
2. 移動 Window 中過渡處理方法
3. Window 只連接 signals
4. 測試過渡動畫

**風險：** 中（涉及動畫時序）

---

### Phase D: 驗證與文檔（1 天）

**步驟：**
1. 運行全量測試
2. 手動測試所有功能
3. 更新架構文檔
4. 測量代碼減少量

**總時間：** 5-8 天

---

## 成功標準

### 定量指標

```
DoroWindow: 679 → 500-550 lines (減少 18-26%)
MenuHandler: ~80 lines (新)
BubbleController: +50 lines (擴展)
TransitionPlayer: +30 lines (完善)

總代碼：略有增加（~1720 → ~1760 行）
但職責更清晰，每個類更專注
```

### 定性指標

- ✅ DoroWindow 只負責 Qt 視窗基礎功能
- ✅ 選單邏輯在 MenuHandler
- ✅ 氣泡邏輯在 BubbleController
- ✅ 過渡邏輯在 TransitionPlayer
- ✅ 所有測試通過
- ✅ 沒有引入新的複雜性

---

## 與 V1 提案的對比

### V1（事件驅動重構）

```
優點：
- 理論上完美（零循環依賴）
- 完全解耦

缺點：
- 推翻現有架構
- 需要重寫大量代碼
- 學習曲線陡峭
- 2-3 週投資
- EventBus 是多餘的（已有 Signals）

結論：過度工程 ❌
```

### V2（務實漸進式）

```
優點：
- 保留現有良好模式
- 針對性解決實際問題
- 漸進式，風險可控
- 5-8 天即可完成
- 不引入不必要抽象

缺點：
- 不如 V1 "完美"
- DoroWindow 仍有 500+ 行

結論：務實可行 ✅
```

---

## 為什麼不需要 ApplicationMediator

### V1 提案的問題

**ApplicationMediator 會成為新的 God Object：**
```python
class ApplicationMediator:
    def __init__(self):
        self._state_controller = ...    # 知道 9 個組件
        self._gif_controller = ...
        self._dialog_manager = ...
        self._transition_player = ...
        self._bubble_controller = ...
        self._movement_manager = ...
        self._chat_controller = ...
        self._chat_orchestrator = ...
        self._menu_handler = ...

        # 連接所有 signals（上帝視角）
        self._connect_all_signals()

    def _connect_all_signals(self):
        # 100+ 行的 signal 連接
        # 這就是 God Object
```

### 為什麼現有 DoroApp 夠好

**DoroApp 是 Composition Root（合理模式）：**
```python
class DoroApp:
    """
    只負責組裝，不負責協調。
    組裝完畢後，組件自己通過 Signals 通信。
    """
    def __init__(self):
        # 創建組件
        window = DoroWindow(...)
        controllers = [...]

        # 注入依賴（一次性）
        window.wire_dependencies(**controllers)

        # 完成，組件自主運作
```

**關鍵差異：**
```
DoroApp:              ApplicationMediator:
- 組裝後即完成         - 持續參與協調
- 不持有組件引用       - 持有所有組件引用
- 137 行              - 會長到 500+ 行
- Composition Root    - God Object
```

---

## 推薦方案

### 立即執行：提案一（DoroWindow 輕量化）

**理由：**
1. 務實可行（5-8 天）
2. 針對實際問題（Window 679 行）
3. 保留現有良好架構
4. 風險可控
5. 立即見效

### 可選執行：提案二（StateService 進一步優化）

**理由：**
- 當前 740 行已可接受
- 如果需要更小，可以提取 MoveStateManager
- 但非必須

### 不建議：提案三（ApplicationMediator）

**理由：**
- 會創造新的 God Object
- 解決不存在的問題
- 過度工程

---

## 決策點

**需要你決定：**

1. **是否執行提案一（DoroWindow 輕量化）？**
   - 投資：5-8 天
   - 回報：DoroWindow 減少 18-26%
   - 風險：低

2. **是否執行提案二（StateService 進一步優化）？**
   - 投資：2-3 天
   - 回報：StateService 再減少 ~80 行
   - 風險：低
   - 必要性：可選（當前已可接受）

3. **還是維持現狀？**
   - 當前架構已經不錯
   - Phase 4.2 已完成主要改進
   - 可以暫停重構，專注功能開發

---

## 誠實評估

### 當前架構狀態

```
✅ 架構設計：良好（三層分離，Signals/Protocols）
✅ 解耦程度：良好（無嚴重循環依賴）
⚠️ 類的大小：可改進（DoroWindow 679, StateService 740）
✅ 測試覆蓋：良好（205 測試通過）
✅ 可維護性：良好（職責基本清晰）
```

### 是否需要繼續重構？

**正方觀點（支持）：**
- DoroWindow 679 行仍然偏大
- 提取 MenuHandler 等可以進一步改善
- 投資不大（5-8 天）

**反方觀點（反對）：**
- 當前架構已經夠好
- 繼續重構收益遞減
- 可以專注在功能開發上

### 我的建議

**中庸之道：**
1. 執行**提案一的 Phase A**（MenuHandler 提取）
   - 最明顯的改進點
   - 風險最低
   - 2-3 天即可完成

2. 評估效果後決定是否繼續
   - 如果效果好，繼續 Phase B、C
   - 如果收益不明顯，就此停止

3. **不執行 ApplicationMediator**
   - 確定會成為新問題

**這樣既不過度工程，也不放任不管。**

---

## 結論

基於現有架構分析：

1. ✅ **現有架構已經相當不錯**
   - Signals、Protocols、分層設計都很好

2. ⚠️ **主要問題是類的大小**
   - DoroWindow 679 行
   - StateService 740 行（已改善）

3. 💡 **務實的改進方案**
   - 提取 MenuHandler（明確）
   - 整合氣泡管理（合理）
   - 統一過渡動畫（適度）

4. ❌ **不需要推翻現有架構**
   - EventBus 是多餘的
   - ApplicationMediator 會成為新問題

**準備好開始 Phase A（MenuHandler 提取）了嗎？**
