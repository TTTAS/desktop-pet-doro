# 改動紀錄 - 2026-08-29

Branch: `refactor/state-collections-and-gif-renderer` (尚未合 `master`)

## PR A — collection 封裝 + key 正規化

- 修復這條分支上被截斷的 `models.py`（`StateCollection` / `MoveStateCollection` / `TransitionCollection` 曾經整段丟失）
- 新增 `normalize_state_key()`；strip + lowercase，collection 內部只存這種形式
- collection 公開 API：`current_key()` / `items()` / `protected_keys()` / `hidden_keys()` / `movement_only_keys()`
- `StateService` 不再碰 `_items` / `_current_key` / `_protected_keys` / `_movement_only_keys`
- 測試：`tests/core/state/test_collection_api.py`
- 計畫：`docs/state-refactor-plan.md`

## WebP / APNG

不是第二套 renderer。跟 GIF 一樣走 `QMovie` + `ANIMATED_EXTENSIONS = (".gif", ".apng", ".webp")`。
這輪沒有改播放管線、也沒有收 `SpriteController` registry。

## 尚未做

- PR B：request / commit + transition lock timeout
- PR C：reaction timelines
- 收掉 `_renderers` / `switch_renderer`（已決策做，留給下一個小 commit）
