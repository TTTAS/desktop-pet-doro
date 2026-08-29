# 改動紀錄 - 2026-08-29

Branch: `refactor/state-collections-and-gif-renderer`（開 PR 進 `master` 用這份當摘要）

## PR A — collection 封裝 + key 正規化

- 修復這條分支上被截斷的 `models.py`
- `normalize_state_key()`：strip + lowercase
- collection 公開 API：`current_key()` / `items()` / `protected_keys()` / `hidden_keys()` / `movement_only_keys()`
- `StateService` 不再碰私有欄位
- 測試：`tests/core/state/test_collection_api.py`

## PR B — request / commit + lock timeout

- lock 期間 queue 最後一次請求，`set_state` 仍回 `False`
- `force=True` 立刻 commit
- `end_transition()` 與 5s 逾時都會套 pending
- Option A：過期的 `transition_completed` 不再載入舊圖
- `dispose()` 掛 `aboutToQuit`
- request/commit 內聯進 `StateService`
- 測試：`test_request_commit_lock.py`、`test_transition_complete_guard.py`、`test_transition_player_guard.py`

## PR C — 反應劇本 + 接到 DoroApp

- slice 1：`Timeline` / `Catalog` / `Director`
- slice 2：`RestoreStep`、`ReactionRunner.play(name)`、`build_default_runner`
- slice 3：`DoroApp` 組 runner，丟進 `CoreManager`；滑鼠 click 先 `on_user_clicked()` 再走聊天句
- 拖曳 Doro 時 `runner.cancel()`，避免 click 動畫卡著
- 預設 click：`click_action` → wait 0.4s → 回原狀態
- **沒有**改 `IdleBehaviorManager` / `ActionDispatcher` 內部
- 測試：`tests/core/reaction/test_director.py`、`tests/core/test_core_manager_click.py`

## WebP / APNG

同一套 `QMovie`。這輪沒有收 `_renderers` / `switch_renderer`。

## 尚未做（下一個小 PR）

- 閒置行為改走 catalog
- 收掉 `_renderers` / `switch_renderer`
