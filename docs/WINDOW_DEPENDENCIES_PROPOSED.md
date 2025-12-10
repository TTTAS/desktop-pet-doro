# DoroWindow 拆解後的依賴關係圖

## 拆解後架構（約 400-450 行）

```
┌─────────────────────────────────────────────────────────────────┐
│                   DoroWindow (簡化版)                            │
│                     (400-450 行)                                 │
│                                                                 │
│  職責精簡到核心：                                                │
│  ✓ Qt Widget 生命週期 (show, close)                            │
│  ✓ Qt 事件分發 (mousePressEvent → MouseEventHandler)          │
│  ✓ 繪製 (paintEvent → RenderingEngine)                        │
│  ✓ 動畫 tick                                                   │
│  ✓ 右鍵選單顯示                                                 │
│                                                                 │
│  不再負責：                                                      │
│  ✗ 回調處理 → WindowEventCoordinator                           │
│  ✗ 配置管理 → WindowConfigurationManager                       │
│  ✗ 複雜的連接邏輯 → 簡化的 wire_dependencies                    │
└─────────────────────────────────────────────────────────────────┘
           │
           │ 依賴 (簡化)
           │
           ├────────────┬────────────┬────────────┐
           ↓            ↓            ↓            ↓
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ ViewModel   │ │ Rendering   │ │ MouseEvent  │ │ Event       │
    │             │ │ Engine      │ │ Handler     │ │ Coordinator │ (新)
    └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
                                                            │
                                                            │
                                                            ↓
┌───────────────────────────────────────────────────────────────────┐
│           WindowEventCoordinator (新類別)                         │
│                   (約 200 行)                                     │
│                                                                   │
│  職責：協調所有組件之間的互動                                      │
│  ✓ 連接所有 controller/manager 的信號                            │
│  ✓ 處理所有回調                                                   │
│  ✓ 協調狀態變更                                                   │
│  ✓ 協調 transition 播放                                          │
│  ✓ 協調聊天回應                                                   │
└───────────────────────────────────────────────────────────────────┘
           │
           │ 依賴所有 Controllers 和 Managers
           │
           ├────┬────┬────┬────┬────┬────┬────┬────┬────┐
           ↓    ↓    ↓    ↓    ↓    ↓    ↓    ↓    ↓    ↓
    ┌──────────────────────────────────────────────────────────────┐
    │  StateController          (處理狀態)                          │
    │  GifController            (處理 GIF)                          │
    │  DialogManager            (管理對話框)                        │
    │  ClickActionController    (處理點擊)                          │
    │  TransitionPlayer         (播放轉換)                          │
    │  BubbleController         (管理氣泡)                          │
    │  MovementManager          (管理移動)                          │
    │  ChatController           (聊天控制)                          │
    │  ChatOrchestrator         (聊天協調)                          │
    └──────────────────────────────────────────────────────────────┘
           │
           │ 這些組件通過信號與 EventCoordinator 溝通
           │ 不再需要直接訪問 Window
           ↓

┌───────────────────────────────────────────────────────────────────┐
│     WindowConfigurationManager (新類別)                           │
│                   (約 80 行)                                      │
│                                                                   │
│  職責：統一管理所有配置                                            │
│  ✓ 讀取 ConfigManager / QSettings                                │
│  ✓ 應用配置到 BubbleController                                   │
│  ✓ 應用配置到 ViewModel                                          │
│  ✓ 處理配置保存                                                   │
└───────────────────────────────────────────────────────────────────┘
           │
           │ 依賴
           │
           ├────────────┬────────────┐
           ↓            ↓            ↓
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ConfigManager│ │QSettings    │ │Bubble       │
    │             │ │(legacy)     │ │Controller   │
    └─────────────┘ └─────────────┘ └─────────────┘
```

## 改進後的優點

### ✅ 優點 1：職責單一
- **DoroWindow**: 只管 Qt 視窗生命週期和事件分發
- **WindowEventCoordinator**: 只管組件之間的協調
- **WindowConfigurationManager**: 只管配置

### ✅ 優點 2：依賴清晰
```
DoroWindow 依賴:
  ├─ ViewModel
  ├─ RenderingEngine
  ├─ MouseEventHandler
  └─ WindowEventCoordinator (新)
      └─ (EventCoordinator 依賴所有 controllers)
```

DoroWindow 不再直接依賴 9 個 controllers，而是通過 EventCoordinator 間接依賴。

### ✅ 優點 3：易於測試
- 可以單獨測試 WindowEventCoordinator 的協調邏輯
- 可以 mock EventCoordinator 來測試 DoroWindow
- 配置邏輯獨立，可以單獨測試

### ✅ 優點 4：解決循環依賴
```python
# app.py (新架構)

# 1. 創建 window
self.window = DoroWindow(...)

# 2. 創建 managers (還是需要 window 引用，但這是暫時的)
self._movement = MovementManager(self.window, ...)

# 3. 創建 EventCoordinator (接收所有 controllers)
self._event_coordinator = WindowEventCoordinator(
    window=self.window,
    state_controller=self._state_controller,
    gif_controller=self._gif_controller,
    # ... 其他 controllers
)

# 4. 簡化的 wire
self.window.wire_dependencies(
    event_coordinator=self._event_coordinator,  # 只需要這一個！
    view_model=self._view_model,
)
```

### ✅ 優點 5：更容易理解
- 要找回調邏輯？→ 看 WindowEventCoordinator
- 要找配置邏輯？→ 看 WindowConfigurationManager
- 要找繪製邏輯？→ 看 DoroWindow.paintEvent + RenderingEngine

## 行數對比

| 組件 | 拆解前 | 拆解後 | 變化 |
|-----|--------|--------|------|
| DoroWindow | 715 行 | 400-450 行 | -265 到 -315 行 |
| WindowEventCoordinator | - | ~200 行 | +200 行 (新) |
| WindowConfigurationManager | - | ~80 行 | +80 行 (新) |
| **總計** | **715 行** | **680-730 行** | **-35 到 +15 行** |

> **注意**: 總行數可能略微增加，但這是值得的，因為：
> - 職責更清晰
> - 更容易維護
> - 更容易測試
> - 更容易理解

## 未來還可以做的（Phase 2）

如果效果好，未來還可以：

### Phase 2A: 解決循環依賴的根源
```
不要讓 MovementManager 依賴整個 Window，
而是讓它依賴一個 Protocol (MovementWindowPort)
```

### Phase 2B: 用 Qt Signals 替代直接方法調用
```python
# 現在
self._window.update()  # 直接調用

# Phase 2B
self.repaint_requested.emit()  # 發送信號
```

這樣可以完全解耦，但需要更大的重構。

---

**這個方案如何？要我開始執行嗎？**
