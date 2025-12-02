# Doro 應用程式依賴關係圖

**生成日期：** 2025-12-02
**版本：** 當前架構（Phase 4 完成後）

---

## 完整依賴關係圖

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                                │
│                              (UI Components)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐     │
│  │                        DoroWindow (679 lines)                     │     │
│  │                     [QWidget, 視窗主體]                            │     │
│  └───┬──────────────────────┬──────────────────┬────────────────────┘     │
│      │                      │                  │                          │
│      │ holds                │ holds            │ holds                    │
│      ↓                      ↓                  ↓                          │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐              │
│  │StateController │  │GifController │  │DialogManager    │              │
│  │  (193 lines)   │  │  (134 lines) │  │                 │              │
│  └───┬────────────┘  └──────────────┘  └─────────────────┘              │
│      │ emits Signal                                                       │
│      │                                                                    │
│      │  ┌──────────────────┐    ┌────────────────────┐                  │
│      │  │BubbleController  │    │ClickActionController│                 │
│      │  │  (159 lines)     │    │                     │                 │
│      │  └──────────────────┘    └────────────────────┘                  │
│      │                                                                    │
└──────┼────────────────────────────────────────────────────────────────────┘
       │
       │ uses (via callback)
       │
┌──────┼────────────────────────────────────────────────────────────────────┐
│      │              APPLICATION LAYER                                     │
│      │           (協調與業務邏輯)                                           │
├──────┼────────────────────────────────────────────────────────────────────┤
│      │                                                                    │
│      │  ┌──────────────────────┐      ┌──────────────────────┐          │
│      │  │  ChatOrchestrator    │      │  MovementManager     │          │
│      │  │    (156 lines)       │      │    (400 lines)       │          │
│      │  │                      │      │                      │          │
│      │  │  orchestrates:       │      │  uses: Protocol      │          │
│      │  │  - ChatController    │      │  (MovementWindowPort)│          │
│      │  │  - Movement          │      │                      │          │
│      │  │  - State changes     │      │                      │          │
│      │  └──────┬───────────────┘      └──────────┬───────────┘          │
│      │         │                                  │                      │
│      │         │ uses                             │ uses                 │
│      │         │                                  │                      │
│      │  ┌──────▼───────────────┐      ┌──────────▼───────────┐          │
│      │  │  ChatController      │      │  TransitionPlayer    │          │
│      │  │    (253 lines)       │      │    (250 lines)       │          │
│      │  │                      │      │                      │          │
│      │  │  - HTTP to LMStudio  │      │  - GIF transitions   │          │
│      │  │  - Worker threads    │      │  - Animation timing  │          │
│      │  └──────────────────────┘      └──────────────────────┘          │
│      │                                                                    │
│      │         │                                  │                      │
│      │         │ uses                             │ uses                 │
│      │         │                                  │                      │
└──────┼─────────┼──────────────────────────────────┼──────────────────────┘
       │         │                                  │
       │         └──────────────┬───────────────────┘
       │                        │
       │                        │ uses
       │                        │
┌──────┼────────────────────────┼──────────────────────────────────────────┐
│      │         DOMAIN LAYER   │                                          │
│      │        (核心業務邏輯)    │                                          │
├──────┼────────────────────────┼──────────────────────────────────────────┤
│      │                        │                                          │
│      ↓                        ↓                                          │
│  ┌───────────────────────────────────────────────────────────┐          │
│  │              StateService (740 lines)                      │          │
│  │                   [核心 FSM]                                │          │
│  │                                                             │          │
│  │  Responsibilities:                                          │          │
│  │  - State lifecycle management                               │          │
│  │  - State transition coordination                            │          │
│  │  - Event emission (callbacks)                               │          │
│  │  - Delegates to specialized managers                        │          │
│  └───┬─────────────────┬─────────────────┬────────────────────┘          │
│      │                 │                 │                               │
│      │ delegates       │ delegates       │ delegates                     │
│      ↓                 ↓                 ↓                               │
│  ┌─────────────┐  ┌──────────────────┐  ┌─────────────────┐            │
│  │ GifManager  │  │TransitionCoord.  │  │  StateParser    │            │
│  │ (119 lines) │  │  (181 lines)     │  │  (141 lines)    │            │
│  │             │  │                  │  │                 │            │
│  │ - GIF ops   │  │ - Transition     │  │ - Parse LLM     │            │
│  │ - Resource  │  │   locking        │  │   actions       │            │
│  │   mgmt      │  │ - Find trans.    │  │ - Normalize     │            │
│  └─────┬───────┘  └────────┬─────────┘  └─────────────────┘            │
│        │                   │                                            │
│        │ uses              │ uses                                       │
│        │                   │                                            │
└────────┼───────────────────┼────────────────────────────────────────────┘
         │                   │
         │                   │
┌────────┼───────────────────┼────────────────────────────────────────────┐
│        │ INFRASTRUCTURE    │                                            │
│        │    (數據持久化)    │                                            │
├────────┼───────────────────┼────────────────────────────────────────────┤
│        │                   │                                            │
│        ↓                   ↓                                            │
│  ┌──────────────┐    ┌───────────────────────┐                         │
│  │GifRepository │    │TransitionStateRepo.   │                         │
│  │              │    │                       │                         │
│  └──────────────┘    └───────────────────────┘                         │
│                                                                         │
│  ┌──────────────┐    ┌───────────────────────┐                         │
│  │StateRepo.    │    │MoveStateRepository    │                         │
│  │              │    │                       │                         │
│  └──────────────┘    └───────────────────────┘                         │
│                                                                         │
│  ┌──────────────────────────────────────────────┐                      │
│  │          ConfigManager (Type-safe)           │                      │
│  │          ↓                                    │                      │
│  │       QSettings (Qt Config)                  │                      │
│  └──────────────────────────────────────────────┘                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 依賴方向（單向，無循環）

```
Presentation Layer
    ↓
Application Layer
    ↓
Domain Layer
    ↓
Infrastructure Layer
```

**關鍵特點：**
- ✅ 單向依賴（上層依賴下層）
- ✅ 下層不知道上層的存在
- ✅ 無循環依賴

---

## 組件間通信模式

### 1. StateService → UI (Callback + Signal)

```
StateService                StateController              DoroWindow
    │                            │                          │
    │ callback: on_state_changed │                          │
    ├───────────────────────────>│                          │
    │                            │                          │
    │                            │ Signal: state_changed    │
    │                            ├─────────────────────────>│
    │                            │                          │
    │                            │                          │ update UI
```

**為什麼用 Callback 而非 Signal？**
- StateService 在 core 層（純 Python）
- 不依賴 Qt（保持框架無關）
- StateController 轉換為 Qt Signal

---

### 2. MovementManager → DoroWindow (Protocol)

```
MovementManager                DoroWindow (實現 Protocol)
    │                                  │
    │ calls: window.current_position() │
    ├─────────────────────────────────>│
    │                                  │
    │ calls: window.clamp_position()   │
    ├─────────────────────────────────>│
    │                                  │
    │ NOT direct class dependency ✅   │
    │ Uses: MovementWindowPort         │
```

**使用 Protocol 的優點：**
```python
class MovementWindowPort(Protocol):
    """Interface - 不是具體類"""
    def current_position(self) -> QPoint: ...
    def clamp_window_position(self, pos: QPoint) -> QPoint: ...

# MovementManager 只依賴 Protocol，不依賴 DoroWindow
class MovementManager:
    def __init__(self, window: MovementWindowPort):
        self._window = window  # 任何實現 Protocol 的對象
```

---

### 3. ChatOrchestrator → StateService (直接調用)

```
ChatOrchestrator
    │
    │ 解析 LLM 回覆: "(STATE: happy)"
    │
    ↓
StateService.set_state("happy")
    │
    ↓
觸發 callback → StateController → Signal → DoroWindow
```

---

## 循環依賴分析

### ❌ 不存在的循環依賴

**檢查：DoroWindow ↔ Controllers**
```
DoroWindow
    ├─> holds StateController ✅ (合成關係)
    │
StateController
    ├─> emits Signal ✅ (事件驅動)
    └─> DoroWindow listens to Signal ✅ (Observer 模式)

結論：不是循環依賴，是 Observer 模式
```

**檢查：MovementManager ↔ DoroWindow**
```
MovementManager
    ├─> depends on MovementWindowPort (Protocol) ✅
    │
DoroWindow
    └─> implements MovementWindowPort ✅

結論：依賴倒置，不是循環依賴
```

---

## 各層職責定義

### Presentation Layer (UI)

```
DoroWindow (679 lines)
├─ Qt 視窗管理 ✓
├─ 事件處理 (mouse, keyboard) ✓
├─ 繪製 (paintEvent) ✓
├─ 選單處理 ⚠️ (可提取到 MenuHandler)
└─ 組件協調 ⚠️ (部分可簡化)

StateController (193 lines)
├─ 監聽 StateService callbacks ✓
├─ 轉換為 Qt Signals ✓
└─ 管理狀態相關 UI 邏輯 ✓

GifController (134 lines)
├─ GIF 載入協調 ✓
└─ 視覺更新 ✓

DialogManager
├─ 管理對話框生命週期 ✓
└─ 提供對話框 API ✓
```

### Application Layer

```
ChatOrchestrator (156 lines)
├─ 協調 LLM 與 FSM ✓
├─ 解析 LLM 指令 ✓
└─ 驅動狀態變更 ✓

MovementManager (400 lines)
├─ 窗口移動動畫 ✓
├─ 邊界檢測 ✓
└─ 方向解析 ✓

TransitionPlayer (250 lines)
├─ 過渡動畫播放 ✓
└─ 動畫完成通知 ✓
```

### Domain Layer (Core)

```
StateService (740 lines)
├─ 狀態生命週期管理 ✓
├─ 狀態轉換協調 ✓
├─ 事件發射 ✓
└─ 委託給專門管理器 ✓

GifManager (119 lines)
├─ GIF 資源管理 ✓
└─ GIF 操作封裝 ✓

TransitionCoordinator (181 lines)
├─ 過渡查找 ✓
├─ 過渡鎖管理 ✓
└─ 過渡狀態追蹤 ✓

StateParser (141 lines)
├─ LLM 動作解析 ✓
├─ 別名處理 ✓
└─ 狀態匹配 ✓
```

### Infrastructure Layer

```
Repositories
├─ StateRepository (持久化 states.json) ✓
├─ MoveStateRepository (持久化 move_states.json) ✓
├─ TransitionStateRepository (持久化 transitions.json) ✓
└─ GifRepository (管理 GIF 文件) ✓

ConfigManager
├─ 類型安全配置 ✓
├─ 集中配置管理 ✓
└─ 配置驗證 ✓
```

---

## 當前架構的優點

### ✅ 1. 清晰的分層

```
每層都有明確的職責邊界
上層依賴下層，下層不知道上層
```

### ✅ 2. 良好的解耦

```
Signals: UI 與業務邏輯解耦
Protocols: 依賴倒置，接口而非實現
Callbacks: 核心層保持框架無關
```

### ✅ 3. 單一職責

```
StateService: 只管狀態
GifManager: 只管 GIF
TransitionCoordinator: 只管過渡
StateParser: 只管解析
```

### ✅ 4. 可測試性

```
每個組件都可獨立測試
Protocol 可以 mock
Signals 可以攔截
```

---

## 當前架構的問題

### ⚠️ 1. 類的大小

```
DoroWindow: 679 lines (仍然偏大)
StateService: 740 lines (已改善，但仍可優化)
```

**解決方案：** 繼續提取專門組件
- MenuHandler (from DoroWindow)
- MoveStateManager (from StateService, optional)

### ⚠️ 2. DoroWindow 職責略多

```
當前 DoroWindow:
- Qt 視窗 ✓ (核心)
- 事件處理 ✓ (核心)
- 繪製 ✓ (核心)
- 選單邏輯 ⚠️ (可提取)
- 組件協調 ⚠️ (可簡化)
```

**解決方案：** 提取 MenuHandler

---

## 與「理想架構」的對比

### 理想：事件驅動 + EventBus

```
Component A ──> EventBus ──> Component B
              (central hub)

優點：完全解耦
缺點：引入不必要的抽象（Qt Signals 已足夠）
```

### 當前：Signals + Protocols + Callbacks

```
StateService ──callback──> StateController ──Signal──> Window
MovementManager ──Protocol──> Window (interface)

優點：使用現有 Qt 機制，無多餘抽象
缺點：需要理解多種模式
```

**評估：當前架構更務實 ✅**

---

## 總結

### 架構狀態評分

```
分層清晰度:    ★★★★★ (5/5)
解耦程度:      ★★★★☆ (4/5)
單一職責:      ★★★★☆ (4/5)
可測試性:      ★★★★☆ (4/5)
可維護性:      ★★★★☆ (4/5)
代碼組織:      ★★★☆☆ (3/5) - DoroWindow 仍偏大

總體評分: ★★★★☆ (4.2/5)
```

### 改進優先級

**高優先級（如果要繼續重構）：**
1. 提取 MenuHandler from DoroWindow (~80 lines)
2. 整合氣泡邏輯到 BubbleController (~50 lines)

**中優先級（可選）：**
3. 提取 MoveStateManager from StateService (~80 lines)

**低優先級（不推薦）：**
4. ApplicationMediator (會成為新的 God Object)

---

## 依賴關係總覽（簡化版）

```
┌────────────────────────────────────────────┐
│           Presentation Layer                │
│  DoroWindow, Controllers, Dialogs          │
└───────────────┬────────────────────────────┘
                │ depends on
                ↓
┌────────────────────────────────────────────┐
│          Application Layer                  │
│  ChatOrchestrator, MovementManager         │
└───────────────┬────────────────────────────┘
                │ depends on
                ↓
┌────────────────────────────────────────────┐
│            Domain Layer                     │
│  StateService, Managers, Parsers           │
└───────────────┬────────────────────────────┘
                │ depends on
                ↓
┌────────────────────────────────────────────┐
│         Infrastructure Layer                │
│  Repositories, ConfigManager                │
└────────────────────────────────────────────┘
```

**依賴流向：** ⬇️ 單向，無循環

**通信模式：**
- ⬆️ 上層 → 下層：直接調用
- ⬇️ 下層 → 上層：Signals/Callbacks (事件驅動)

---

## 結論

**當前架構評價：** 相當不錯 ✅

**主要優點：**
- 分層清晰
- 無循環依賴
- 使用成熟模式（Signals, Protocols, Callbacks）

**可改進空間：**
- DoroWindow 可進一步輕量化（679 → 500-550 行）
- 但不需要推翻重來

**建議：** 執行務實的改進（提取 MenuHandler），而非革命性重構。
