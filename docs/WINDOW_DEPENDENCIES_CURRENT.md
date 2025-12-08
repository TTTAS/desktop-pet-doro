# DoroWindow 當前依賴關係圖

## 當前架構（715 行）

```
┌─────────────────────────────────────────────────────────────────┐
│                         DoroWindow                              │
│                        (715 行)                                  │
│                                                                 │
│  職責太多：                                                      │
│  ✓ Qt Widget 生命週期管理                                       │
│  ✓ 事件處理 (mouse, key, context menu)                         │
│  ✓ 繪製 (paintEvent)                                           │
│  ✓ 動畫 tick                                                   │
│  ✓ 依賴注入和連接 (wire_dependencies)                          │
│  ✓ 處理所有 controller/manager 的回調                          │
│  ✓ 協調組件之間的互動                                           │
│  ✓ 配置管理和應用                                               │
│  ✓ 視窗位置和大小計算                                           │
│  ✓ 狀態變更處理                                                 │
└─────────────────────────────────────────────────────────────────┘
           │
           │ 依賴 (直接創建或注入)
           │
           ├─────────────────┬─────────────────┬─────────────────┐
           ↓                 ↓                 ↓                 ↓
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ViewModel     │  │RenderingEngine│ │MouseEventHandler│ │GifPlayer     │
    └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘

           │ wire_dependencies() 注入 9 個依賴
           │
           ├────┬────┬────┬────┬────┬────┬────┬────┬────┐
           ↓    ↓    ↓    ↓    ↓    ↓    ↓    ↓    ↓    ↓
    ┌──────────────────────────────────────────────────────────────┐
    │  StateController                                             │
    │  GifController                                               │
    │  DialogManager                                               │
    │  ClickActionController                                       │
    │  TransitionPlayer                                            │
    │  BubbleController                                            │
    │  MovementManager                                             │
    │  ChatController                                              │
    │  ChatOrchestrator                                            │
    └──────────────────────────────────────────────────────────────┘

           │ DoroWindow 連接所有信號並處理回調
           │
           ↓
    ┌──────────────────────────────────────────────────────────────┐
    │  DoroWindow 中的回調方法（約 150 行）：                        │
    │                                                              │
    │  • _on_controller_state_changed()                            │
    │  • _on_state_list_updated()                                  │
    │  • _on_gif_loaded()                                          │
    │  • _on_sprite_size_changed()                                 │
    │  • _on_transition_movie_loaded()                             │
    │  • _on_transition_completed()                                │
    │  • _on_bubble_text_requested()                               │
    │  • _on_chat_notification()                                   │
    │  • _set_bubble_text()                                        │
    │  • _clear_bubble_text()                                      │
    │  • _set_busy_cursor()                                        │
    │  • _toggle_bubble()                                          │
    │  • ... 還有更多                                               │
    └──────────────────────────────────────────────────────────────┘
```

## 問題分析

### 🔴 問題 1：職責過多
DoroWindow 同時負責：
- Qt 視窗管理
- 事件協調
- 配置管理
- 回調處理

### 🔴 問題 2：依賴爆炸
- 直接依賴 4 個組件（ViewModel, RenderingEngine, etc.）
- 通過 wire_dependencies 依賴 9 個組件
- 總共 13 個依賴

### 🔴 問題 3：難以測試
- 太多依賴，mock 困難
- 回調邏輯散落在類別中
- 難以單獨測試某個功能

### 🔴 問題 4：wire_dependencies 的循環依賴問題
```python
# app.py 中
self.window = DoroWindow(...)  # 先創建 window

# 然後創建 managers，它們需要 window 引用
self._movement = MovementManager(self.window, ...)

# 最後 wire 回去
self.window.wire_dependencies(
    movement_manager=self._movement,
    ...
)
```

這個循環依賴是架構問題的根源。
