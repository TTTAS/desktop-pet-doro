# PR：狀態封裝 + request/commit + 反應劇本

**Branch:** `refactor/state-collections-and-gif-renderer` → `master`  
**Stack:** Python + PySide6。沒有 Godot、沒有 Live2D。  
**Sprites:** 同一套 `QMovie`（`.gif` / `.apng` / `.webp`），不是第二套 renderer。

這條分支做三件事：狀態資料不要再摸私有欄位、轉場時狀態要排隊、點 Doro 的短反應改走劇本。

---

## 為什麼改

舊程式裡狀態 key 大小寫不一致、轉場播放中途又被下一筆 `set_state` 蓋掉，點一下的動畫也沒有「播完回家」的保證。

這次把這三層分開：

1. **Collection** 管「有哪些狀態」
2. **request / commit** 管「想切到哪」vs「畫面已經切到哪」
3. **Reaction timeline** 管「一小段表演怎麼照順序演」

---

## PR A — collection 封裝

- 修好這條分支上曾被截斷的 `models.py`
- `normalize_state_key()`：strip + lowercase，collection 只存這種形式
- `StateService` 改走公開 API：`current_key()` / `items()` / `protected_keys()` / `hidden_keys()` / `movement_only_keys()`
- 測試：`tests/core/state/test_collection_api.py`

## PR B — request / commit + lock 逾時

- `requested_key`：最後想去的狀態
- `committed_key`：現在真正的狀態（sprite 應對齊這個）
- 轉場 lock 期間非 `force` 的 `set_state` 會排隊（最後一筆贏），回傳 `False`（舊 protection tests 仍綠）
- lock 預設 5 秒逾時；`end_transition()` / 逾時都會套用排隊中的請求
- Option A：排隊已經改走別的狀態後，不再 emit 過期的 `transition_completed`
- `TransitionPlayer.dispose()` 掛在 `aboutToQuit`
- request/commit 已內聯進 `StateService`（沒有 import-time monkeypatch）
- 測試：`test_request_commit_lock.py`、`test_transition_complete_guard.py`、`test_transition_player_guard.py`

## PR C — 反應劇本 + 接到 DoroApp

- `Timeline` / `Catalog` / `Director` / `Runner`（Qt-free）
- 步驟：`state` / `wait` / `speak` / 可選 `move` / `restore`
- 優先權：click (20) > chat (10) > idle (0)；被打斷的 wait 不會再跑
- 預設 `click`：`click_action`（force）→ 等 0.4 秒 → 回到 play 當下的 committed key
- `DoroApp` 用 `build_default_runner(...)` 組 runner，丟進 `CoreManager`
- 滑鼠 click：先 `on_user_clicked()` 播劇本，再走原本的 `ClickActionController` 聊天句
- 拖曳時 `runner.cancel()`
- **沒有**改 `IdleBehaviorManager`、`ActionDispatcher` 內部

---

## 行為對照（點 Doro）

| 之前 | 現在 |
|---|---|
| 只丟一句 click 聊天 | 先播 click 動畫，再丟聊天句 |
| 沒有保證回到原狀態 | `RestoreStep` 回到點之前的狀態 |
| 閒置講到一半被點可能打架 | click 優先，閒置 wait 會被丟掉 |

桌面自動化點擊（`AutomationManager` / `[mouse:click]`）不是這條路徑，沒動。

---

## 刻意沒做

- 合進 master 之前請人工看一眼實際點擊
- 閒置行為改走 catalog
- 收掉 `_renderers` / `switch_renderer`（已決策，下一個小 PR）
- Dialogic、視覺編輯器、LLM 寫劇本
- Godot / Live2D

---

## 驗證

```powershell
pytest tests/core/reaction/test_director.py tests/core/test_core_manager_click.py tests/core/test_core_manager.py tests/core/state/test_request_commit_lock.py tests/core/state/test_transition_complete_guard.py tests/core/state/test_state_protection.py tests/core/state/test_collection_api.py -q --no-cov
```

手動：啟動 Doro → 點一下角色 → 應看到 `click_action` 閃一下，約 0.4 秒後回到原圖；若有 click 台詞檔，氣泡仍會出句。

---

## 主要檔案

| 區塊 | 路徑 |
|---|---|
| A | `doro_app/core/state/models.py`, `service.py` |
| B | `service.py`, `transition_player.py`, `transition_complete.py`, `transition_coordinator.py` |
| C | `doro_app/core/reaction/*`, `core_manager.py`, `app.py` |
| 說明 | `docs/state-refactor-plan.md`, `docs/pr-b-request-commit.md`, `docs/pr-c-reaction-timelines.md`, `docs/CHANGELOG_session_2026-08-29.md`, `docs/pr-state-reaction.md` |
