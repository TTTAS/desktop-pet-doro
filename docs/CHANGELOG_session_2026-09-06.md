# 改動紀錄 - 2026-09-06

主題：解決「doro 說話泡泡太長把角色往上擠 / 衝出畫面」，以及「查證答覆開頭 `(狀態)` 被念出來」。

> 註：`state_list.txt`、`context_menu_controller.py`、`res/drag/` 是這個 session **開始前**就有的改動，不屬於本次工作，這份紀錄不涵蓋。

---

## 問題

1. AI 回覆很長時，泡泡跟 doro 住在同一個透明視窗、且泡泡固定往「下」長 → 視窗被撐高又往下長 → doro 靠螢幕底部時撞到螢幕邊被系統 clamp 往上推 →**角色被往上擠**、長文還**衝出畫面底部**被切掉。
2. 查證（verify）答覆開頭的 `(狀態)` 標記被**原樣顯示**出來（模型把佔位字「狀態」照字面吐出）。

## 使用者選定的方向

- 長文 →**分多次說話**（切成多個短泡泡輪流顯示）＋**提示詞要求簡潔**。
- 泡泡位置 →**自動：哪邊有空間放哪邊**（靠螢幕底部就翻到上方）。

---

## 改動 1：長回覆分段顯示（Doro 分多次說話）

- `doro_app/constants.py`：新增 `BUBBLE_CHUNK_MAX_CHARS=70`、`BUBBLE_CHUNK_MIN_READ_MS=2200`、`BUBBLE_CHUNK_MAX_READ_MS=9000`、`BUBBLE_CHUNK_PER_CHAR_MS=80`。
- `doro_app/ui/components/bubble_controller.py`：
  - `set_text()` 改為：長文用 `_split_into_chunks()` 依句末標點（。！？…、換行）切段、貪婪打包到 ≤70 字，單句過長就硬斷；第一段立刻顯示，其餘排進 `_chunk_queue`。
  - `_show_next_chunk()` / `_on_hide_timer_timeout()`：中途每段停留 `_reading_delay_ms()`（依長度 2.2～9 秒）後換下一段；**最後一段**才套用原本的 auto-hide 規則。
  - 來新訊息或 `clear_text()` 會取消整個序列。
  - 唯一入口（聊天 + 網頁查證/摘要都經過），所以全都自動分段。
- 測試：`tests/ui/components/test_bubble_chunking.py`（10 個：不超長、不掉字、硬斷、換段、取消、清除、閱讀時間邊界…）。

## 改動 2：泡泡自動選邊（哪邊有空間放哪邊）

- `doro_app/ui/rendering/rendering_engine.py`：
  - `calculate_sprite_center(..., reserve_above=False)`：`reserve_above=True` 時把泡泡空間預留在**上方**（角色坐在視窗下半部）。
  - `render_text_panel(..., prefer_above=False)`：`prefer_above=True` 時偏好把泡泡畫在上方（仍保有放不下就退回另一側的保底）。
- `doro_app/ui/window.py`：
  - 新增 `_bubble_above` 旗標與 `_decide_bubble_above(sprite_center_screen, panel_height_hint)`：依角色在**螢幕上的實際位置**比較上下剩餘空間，下方塞不下且上方較寬才翻上去（避免抖動）。
  - `apply_window_preferred_size()` 在 resize 前先決定旗標。
  - 把 `reserve_above=self._bubble_above` 串進全部 4 個 `calculate_sprite_center` 呼叫點，`prefer_above=self._bubble_above` 串進 `render_text_panel`。
- 效果：doro 平常在右下角，上方幾乎永遠有空間 → 視窗往上長、不頂到 doro、不蓋住 doro、不衝出畫面底部。

## 改動 3：提示詞要求簡潔

- `doro_app/core/web/verify.py`：查證回答要求新增「務必簡潔、2～4 句、約 150 字內」。
- `doro_app/core/chat/orchestrator.py` `_build_web_read_prompt`：讀網頁摘要同樣加簡潔上限。

## 改動 4：修 `(狀態)` 被念出來

- `doro_app/core/chat/orchestrator.py`：
  - 新增 `_LEADING_STATE_MARKER_RE` 與 `_apply_leading_state_marker()`：**只拆掉開頭那一個** `(狀態)` 標記（半形/全形都收，長度上限 24 字），內文括號（`(USGS)`、`(來源1, 來源2)`…）保留；開頭若是真的狀態 key 就順便切換表情，是佔位字「狀態」就只拆不換。
  - `_on_verify_finished()` 顯示前先過這個 helper。
- **坑（別踩）**：一般聊天/讀網頁走 `_on_request_succeeded` → `parse_actions_from_text`（`utils/actions.py`），那個會**無腦拆掉內文所有 `(...)`**；查證是原樣顯示，所以**不能**把整段丟進去，否則引註括號會被毀掉——只能用上面的 `_apply_leading_state_marker` 拆開頭。
- 測試：`tests/core/chat/test_verify_state_marker.py`（6 個）。

---

## 動到的檔案

程式：
- `doro_app/constants.py`
- `doro_app/ui/components/bubble_controller.py`
- `doro_app/ui/rendering/rendering_engine.py`
- `doro_app/ui/window.py`
- `doro_app/core/web/verify.py`
- `doro_app/core/chat/orchestrator.py`

新增測試：
- `tests/ui/components/test_bubble_chunking.py`
- `tests/core/chat/test_verify_state_marker.py`

## 測試狀態

`python -m pytest tests -q` → **907 passed**（原 891 + 新增 16）。

## 尚未做（交還給你）

- 實機跑一次確認手感：長查證答覆是否順順地分段講完、doro 靠底部時泡泡是否確實翻到上方、`(狀態)` 是否不再外露。
- 分段停留時間（`BUBBLE_CHUNK_*_MS`）與每段字數（`BUBBLE_CHUNK_MAX_CHARS=70`）可依實機手感再調。
- commit / 開 PR。
