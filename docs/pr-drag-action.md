# 拖曳反應（drag action）+ 命名動作登記處

**分支**：`claude/doro-drag-gif-setup-cd1d6e`
**日期**：2026-09-06

## 目標

1. 抓著 Doro 拖動時，播一段專屬 GIF；放開後回到拖曳前的狀態。
2. 這個「拖曳 GIF」可以在右鍵選單的 **Edit actions**（Action Manager）裡設定／更換，跟 `click` 動作並列。

## 背景（為什麼是現在這個形狀）

- 拖曳播 GIF 之前**其實沒真的做完**：`refactor/state-collections-and-gif-renderer` 上曾用 `ReactionRunner` 接過 click＋drag（commit `c92f04a`），但整包被 `9907741` revert（點擊會閃站姿）；`doro_app/core/reaction/` 只留成地基，`catalog.py` 從沒有 `drag` timeline。現在的 `_on_doro_dragged` 只做「取消走路／點擊」。
- 既有的 `click` 動作已有一套成熟模式（`ActionService` + `actions.json` + 隱藏顯示狀態 `click_action` + fallback 鏈）。拖曳直接複製這套最省事、最一致。
- 右鍵 **Edit actions** 開的 `MoveStateManagerDialog`（標題 "Action Manager"）**本來就是**「Movement / Transition / Action」三合一卡片清單——只是 Action 那段寫死只列 `click`。所以「統一 action」構想早已實現八成，這次只把它 registry 化。

## 設計決定

- 拖曳是**命名動作** `dragged`，不是 state、不是 movement。
- 播放長度不固定（按住多久播多久）→ 用「直接切狀態」而非固定時長 timeline：`drag_started` 切到 `dragged`，`drag_ended` 還原。
- `dragged` 背後的顯示狀態**隱藏**（跟 `click_action` 一樣）→ 不進 States 選單、idle 挑不到；只以「拖曳」卡出現在 Action Manager。
- 放開後還原拖曳前狀態；若那是走路類（movement-only）或就是 `dragged`，改回 `idle`。
- `ActionEntry` 新增 `kind` 欄位當「登記處種子」（`click`/`dragged`，未來可掛 `move`/`transition`）。Action Manager 的命名動作段改成 registry 驅動（迴圈 `named_action_keys()`）。**沒有新增對話框**。

## 改動檔案

核心
- `doro_app/core/action/repository.py`：`ActionEntry` 加 `kind`；自動補 `dragged` builtin（`_ensure_builtin` 一般化）。舊 `actions.json` 無 `kind` → 預設 `click`，相容。
- `doro_app/core/action/service.py`：
  - 常數 `DRAG_ACTION_STATE_KEY="dragged"`、`_ACTION_STATE_KEYS` 對應表。
  - `bind_click_gif`/`unbind_click_gif` → 一般化成 `bind_action_gif(key, path)`/`unbind_action_gif(key)`（舊名保留為薄殼）。綁定時先清掉該狀態的多檔池，讓單一選擇勝出。
  - `bootstrap()` 註冊 `dragged` 隱藏狀態；`_seed_drag_defaults()` 首次把 `res/drag/` 的 `.webp/.gif/.apng` 種進去（冪等：已有就不覆蓋）。`drag_assets_dir` 可注入（測試用）。
  - 新查詢：`named_action_keys()`、`get_action_display_name()`、`action_state_key()`、`list_action_gif_paths()`、`drag_state_key`。
  - `resolve_action_gif_path()` 多一步：查該動作顯示狀態自己的 GIF 池（讓預覽反映種入的 webp）。
- `doro_app/core/action/fakes.py`：`FakeActionRepository` 同步補 `dragged` builtin＋保留 `kind`。

播放
- `doro_app/ui/events/mouse_event_handler.py`：新增 `drag_ended` 信號（放開且為拖曳時發，點擊不發）。
- `doro_app/app.py`：`drag_ended` 接線；`_on_doro_dragged` 記錄拖曳前狀態＋播 `dragged`；新增 `_on_drag_ended` 還原。

UI（沿用既有對話框）
- `doro_app/ui/dialogs/move_state/manager_dialog.py`：Action 段從「只列 click」→ 迴圈 `named_action_keys()`；`_ActionCard` 加 `title` 參數以顯示「拖曳」而非 key。
- `doro_app/ui/dialogs/move_state/edit_dialog.py`：action 模式的 key 與綁定改用 `self._edit_action_key`（不再寫死 `click`）；`_save_action` 走 `bind_action_gif`。

素材
- `doro_app/res/drag/H3_00384_.webp`、`H3_00385_.webp`。

## 測試

全部 904 passed。新增／更新：
- `tests/core/action/test_repository.py`：`dragged` builtin、`kind` 預設、使用者綁定保留但 builtin/kind 被重申。
- `tests/core/action/test_service.py`：`RecordingStateService` 補新方法；drag 狀態註冊、seeding（含冪等與只挑動畫副檔名）、`bind_action_gif` 清池＋綁定、未知動作拒絕、`resolve` 走狀態池、registry 查詢。
- `tests/ui/dialogs/move_state/test_edit_dialog.py`：改為斷言 `bind_action_gif(key, path)`。
- `tests/ui/events/test_mouse_event_handler.py`（新）：點擊只發 click、拖曳發 started→ended、無按下 release 為 no-op。

端到端（暫存目錄、真 repository）：2 個 webp 真的被種入 `dragged/`，`get_gif_path("dragged")` 回可播檔案，`dragged` 不在 `visible_state_keys()`。

## 額外修正：隱藏動作狀態不再洩漏給 LLM（gesture-only）

**症狀**：LLM 回覆吐出 `(click_action)` 之類的 token，就把「被拎起來／點擊」的動畫叫出來——這些動畫應該**只由真的點擊／拖曳手勢**觸發，跟 LLM 無關。

**根因**（既有 bug，`click_action`/`click_failed` 早就中，`dragged` 會一起中）：
1. `write_state_list()` 把**所有**狀態寫進 LLM 的 `state_list.txt`，只特別處理 movement-only，**沒有排除隱藏狀態** → LLM 看得到 `click_action`/`dragged` 就會用。
2. `StateParser.parse()` 只擋 movement-only，**沒擋隱藏** → 就算 LLM 亂吐 `(click_action)` 也會被接受並 `set_state`。

**修法（兩層防護）**：
- `core/state/service.py`：`write_state_list()` 先排除 `self._states.hidden_keys()`；新增 `is_hidden_state(key)`。
- `core/state/state_parser.py`：新增 `_is_selectable()`，LLM token 只有「非 movement-only 且非 hidden」才可選；`StateProvider` Protocol 加 `is_hidden_state`（以 `getattr` 防呆，最小 fake 不會壞）。

效果：`click_action`/`click_failed`/`dragged` 這些隱藏顯示狀態**不再出現在 LLM 狀態清單、也不再能被 LLM token 觸發**。它們只由點擊（`[mouse:click]` wind-up／dispatcher）與拖曳手勢驅動。

測試：`tests/core/state/test_state_parser.py`（隱藏狀態 token／label 都被拒）、`tests/core/state/test_service.py`（`write_state_list` 不含隱藏狀態）。

## 後續擴充點

`kind` 已就位。之後若要「所有反應一個清單」，可把 `move`/`transition` 也當 kind 掛進 Action Manager（用深連結指到它們現成的編輯器，不搬資料）——乾淨的一小步，不用重寫。
