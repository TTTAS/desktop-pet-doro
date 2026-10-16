# 對話泡泡拆成獨立視窗（計畫）

狀態：2026-10-16 草案，待使用者確認後實作。基準 `5f609bf`，分支 `claude/relaxed-sagan-wgumxk`。

## 問題

泡泡與 Doro 本體畫在同一個視窗（`DoroWindow.paintEvent` 先畫 GIF，再用
`RenderingEngine.render_text_panel` 畫泡泡）。泡泡出現時視窗從角色大小（約 200×200）
放大到約 640×460，消失時縮回；每次都要「resize → 依腳底重新 move」兩步。
Windows 可能在兩步之間重畫，使用者看到 Doro 閃到別處再閃回來。

`5f609bf` 已在 resize＋move 期間暫停重畫，降低機率，但視窗仍會反覆變大小，
屬於治標；這類時序問題也很難在使用者端穩定重現。

## 目標

- Doro 主視窗**永遠只有角色大小**；說話、泡泡出現或消失都不改變主視窗大小與位置。
- 泡泡外觀、分段播放、自動隱藏、靠近螢幕底部時改到上方等現有行為不變。
- 泡泡跟著 Doro 走路、被拖曳、換姿勢移動。

不做：泡泡的新互動（點擊、拖曳）、新外觀、聊天輸入列（`FloatingChatWindow`）的改動。

## 現況重點（決定設計的事實）

| 項目 | 位置 | 說明 |
| --- | --- | --- |
| 泡泡邏輯 | `ui/components/bubble_controller.py` | 文字、分段、計時隱藏；用訊號通知畫面，本身不畫圖 → **可原樣保留** |
| 泡泡繪製 | `ui/rendering/rendering_engine.py` `render_text_panel` | 依角色中心與可用範圍畫圓角框與文字，決定上／下方 |
| 為泡泡預留空間 | `rendering_engine.calculate_sprite_center`、`layout_manager.compute_preferred_window_size` | 非 compact 模式在角色上或下方預留泡泡高度 |
| 放大／縮小視窗 | `window.apply_window_preferred_size`、`_should_collapse_to_sprite`、`_decide_bubble_above` | 本次閃現的來源 |
| 泡泡透明度 | `view_model.bubble_alpha`（每個狀態可設定） | 需沿用 |
| 泡泡位移 `bubble_offset` | `bubble_controller`、`movement.manager`（face 左右） | 目前只被儲存，繪製時沒用到 → 行為不變，照樣儲存 |
| 參考做法 | `ui/dialogs/floating_chat.py` | 已是 Tool＋無框＋置頂＋透明背景＋不搶焦點的獨立視窗 |

## 設計

### 新元件 `SpeechBubbleWindow`（`ui/components/speech_bubble_window.py`）

- 視窗旗標比照聊天輸入列：`Tool | FramelessWindowHint | WindowStaysOnTopHint`，
  `WA_TranslucentBackground`、`WA_ShowWithoutActivating`。
- 另加 `WindowTransparentForInput`：泡泡**不攔截滑鼠**，點到泡泡等於點到後面的視窗
  （目前泡泡也沒有任何點擊功能）。
- `paintEvent` 直接重用 `RenderingEngine.render_text_panel`，畫布就是泡泡本身大小。
- 透明度沿用 `view_model.bubble_alpha`。

### 位置計算（純函式，可單元測試）

`bubble_geometry(sprite_rect_on_screen, panel_size, screen_work_area) -> (QRect, above: bool)`

- 預設在角色下方、水平置中；下方放不下且上方空間較大時改到上方
  （搬用現有 `_decide_bubble_above` 的規則）。
- 夾在角色所在螢幕的工作區內（多螢幕、負座標、工作列都沿用既有工作區計算）。

### 跟隨

- `DoroWindow` 在 `moveEvent`／`resizeEvent` 送出新訊號 `sprite_geometry_changed(QRect)`
  （角色在螢幕上的範圍）。
- 泡泡視窗收到就重新定位。走路時每一步主視窗移動後，泡泡在**同一個事件處理中**跟著移動。

### 主視窗簡化

- `DoroWindow.paintEvent` 不再畫泡泡。
- 主視窗固定為 compact（角色大小）；移除為泡泡預留空間的計算：
  `calculate_sprite_center` 的 panel reserve、`compute_preferred_window_size` 的非 compact 分支、
  `_should_collapse_to_sprite`、`_bubble_above`。
- `apply_window_preferred_size` 只在**角色 GIF 尺寸改變**時才調整視窗（保留腳底不動的邏輯與
  `5f609bf` 的暫停重畫）。

### 接線（`app.py`）

- 建立 `SpeechBubbleWindow`，接上 `BubbleController.text_changed`／`visibility_changed`
  （有文字就顯示、清空就隱藏）與 `DoroWindow.sprite_geometry_changed`。
- 結束時一併關閉；置頂守護（`topmost_guard`）會自動涵蓋這個新視窗。

## 實作步驟

1. **純函式與新視窗**：`bubble_geometry` ＋ `SpeechBubbleWindow`，先加測試（上下翻轉、螢幕邊界夾住、多螢幕）。
2. **接線並停用舊畫法**：`app.py` 建立泡泡視窗；`DoroWindow` 停止畫泡泡、說話時不再改大小。
3. **調整測試**：`tests/ui/test_grounding.py`（7 個）、`tests/ui/test_layout_manager.py`（20 個）、
   `tests/core/movement/test_anchor_drift.py`（4 個）中假設「視窗包含泡泡」的部分改為新行為；
   新增「說話前後主視窗大小與位置完全不變」「走路時泡泡跟著角色」測試。
4. **清掉死碼**：移除預留空間相關常數與分支；更新 `docs/REPO_MAP.md`、`docs/ai/areas.json`、README。
5. **Windows 實機驗收**（下節）。

每一步各自提交，跑完整測試後再推。

## 風險與取捨

| 風險 | 影響 | 對策 |
| --- | --- | --- |
| 走路或拖曳時泡泡晚一幀跟上 | 快速移動時泡泡可能有輕微拖尾 | 同一事件內同步移動；若仍明顯，再評估改用一次性 `setGeometry` |
| 兩個置頂視窗的前後順序 | 泡泡可能被 Doro 本體蓋住一角 | 泡泡顯示時 `raise_()` 一次；兩者通常不重疊 |
| 多螢幕／DPI 縮放 | 泡泡出現在錯的螢幕或位置偏移 | 以角色所在螢幕的工作區計算，沿用既有邏輯並加測試 |
| 測試改動量 | 約 30 個版面相關測試需要檢視 | 分步提交；只改「預期視窗包含泡泡」的斷言，不放寬其他檢查 |
| 舊設定 | 無 | 設定檔欄位不變（`bubble_offset` 照樣儲存） |

## 驗收

- 自動：完整測試通過；新增測試確認說話前後主視窗 geometry 完全相同。
- Windows 實機（請使用者確認）：
  1. 讓 Doro 說幾句話：本體不再閃動；泡泡在下方（靠近螢幕底部時在上方）。
  2. 說話時拖曳 Doro、讓她走路：泡泡跟著，沒有明顯拖尾。
  3. 泡泡蓋住其他程式時，點泡泡的位置會點到後面的程式。
  4. 多螢幕（如有）：泡泡跟著 Doro 換螢幕。

## 需要你決定

1. 泡泡**不攔截滑鼠**（點泡泡等於點後面的視窗），可以嗎？目前泡泡本來就沒有點擊功能。
2. 說話中**拖曳 Doro 時泡泡要跟著**，還是拖曳期間先隱藏、放開後再出現？（計畫預設：跟著）
