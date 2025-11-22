# State Dialogs 重構追蹤表

## 當前狀態
- ❌ 所有對話框都在 `state_dialogs.py` (1,074行)
- ❌ 測試檔案散落各處

## 目標結構

```
doro_app/ui/dialogs/
├── state/
│   ├── __init__.py           ← 匯出：show_state_manager, show_add_state_dialog
│   ├── manager_dialog.py     ← StateManagerDialog (原 21-271行)
│   └── add_dialog.py          ← AddStateDialog (原 273-374行)
└── move_state/
    ├── __init__.py            ← 匯出：show_move_state_manager
    ├── manager_dialog.py      ← MoveStateManagerDialog (原 376-661行)
    └── edit_dialog.py         ← EditMoveStateDialog (原 663-1074行)

tests/ui/dialogs/
├── state/
│   ├── __init__.py
│   ├── test_manager_dialog.py
│   └── test_add_dialog.py
└── move_state/
    ├── __init__.py
    ├── test_manager_dialog.py
    └── test_edit_dialog.py
```

## 外部依賴（誰在用這些函式？）

| 函式 | 呼叫者 | 檔案位置 |
|------|--------|----------|
| `show_state_manager()` | `DoroWindow._show_state_manager()` | window.py:676 |
| | `themed_menu.py` | themed_menu.py:303 |
| `show_add_state_dialog()` | `DoroWindow._add_state()` | window.py:760 |
| `show_move_state_manager()` | `DoroWindow._show_move_gif_manager()` | window.py:681 |

## 重構進度

### ✅ Phase 0: 準備工作
- [x] 建立此追蹤表
- [x] Git commit (clean state)

### Phase 1: 建立新目錄結構
- [ ] 建立 `ui/dialogs/state/` 目錄
- [ ] 建立 `ui/dialogs/move_state/` 目錄
- [ ] 建立 `tests/ui/dialogs/state/` 目錄
- [ ] 建立 `tests/ui/dialogs/move_state/` 目錄

### Phase 2: 搬移 StateManagerDialog
- [ ] 建立 `state/manager_dialog.py`
- [ ] 複製 StateManagerDialog 類別
- [ ] 複製 show_state_manager() 函式
- [ ] 建立 `state/__init__.py` 並匯出
- [ ] 測試執行

### Phase 3: 搬移 AddStateDialog
- [ ] 建立 `state/add_dialog.py`
- [ ] 複製 AddStateDialog 類別
- [ ] 複製 show_add_state_dialog() 函式
- [ ] 更新 `state/__init__.py`
- [ ] 測試執行

### Phase 4: 搬移 MoveStateManagerDialog
- [ ] 建立 `move_state/manager_dialog.py`
- [ ] 複製 MoveStateManagerDialog 類別
- [ ] 複製 show_move_state_manager() 函式
- [ ] 建立 `move_state/__init__.py` 並匯出
- [ ] 測試執行

### Phase 5: 搬移 EditMoveStateDialog
- [ ] 建立 `move_state/edit_dialog.py`
- [ ] 複製 EditMoveStateDialog 類別
- [ ] 更新 `move_state/__init__.py`
- [ ] 測試執行

### Phase 6: 更新導入路徑
- [ ] 更新 window.py 的 import (3處)
- [ ] 更新 themed_menu.py 的 import
- [ ] 測試完整應用程式

### Phase 7: 整理測試
- [ ] 建立基礎測試結構
- [ ] 為每個對話框建立測試檔案
- [ ] 驗證測試可執行

### Phase 8: 清理
- [ ] 刪除舊的 `state_dialogs.py`
- [ ] 最終測試
- [ ] Git commit

## 回滾指令（萬一出錯）

```bash
# 回到上一個 commit
git reset --hard HEAD~1

# 查看所有重構 commits
git log --oneline --grep="refactor"

# 回到特定 commit
git reset --hard <commit-hash>
```

## 快速導航

**狀態相關 (State)** - 關於外觀、顏色、GIF
- `ui/dialogs/state/manager_dialog.py` → 管理所有狀態（列表、編輯、刪除）
- `ui/dialogs/state/add_dialog.py` → 新增狀態對話框

**動作相關 (MoveState)** - 關於移動、方向、過渡
- `ui/dialogs/move_state/manager_dialog.py` → 管理所有動作（列表、類型）
- `ui/dialogs/move_state/edit_dialog.py` → 編輯/新增動作（支援 Movement 和 Transition）

**記住**：
- State = 外觀 (GIF, 顏色, 氣泡設定)
- MoveState = 行為 (方向, 速度, 移動邏輯)
- TransitionState = 狀態切換動畫
