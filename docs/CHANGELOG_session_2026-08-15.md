# 改動紀錄 - 2026-08-15

## 📋 本次 Session 完成項目

### 1. ✅ 移除 Live2D 渲染支援

**背景：**

Doro 原本支援兩種精靈渲染路徑：平常顯示 GIF，切到「Live2D 模式」時透過 `live2d-py` + OpenGL 離屏 FBO 渲染 Cubism 模型（例如「拎起來」時切換）。使用者回報：Live2D 的樣子跟 GIF 版本長得不一致，而且混合兩條渲染路徑（mixed rendering）維護成本過高，這個功能實際上只有測試時用過。

**決策（經 grilling 逐一釘定）：**

- **砍除範圍：** 整包移除 Live2D 渲染，而非只關掉預覽。
- **Pickup 行為：** 移除後「拎起來」單純**繼續顯示 GIF**——不需要額外程式碼（見下方「關鍵設計點」）。
- **架構取捨：** **保留**可插拔渲染器架構（`SpriteRenderer` 基底、`_renderers` 註冊表、`switch_renderer`），只拔掉 Live2D 這一支具體渲染器。未來要不要做別的渲染器（如 Spine）另開 issue 評估，已記入 `docs/BACKLOG.md`。
- **資產：** Live2D 模型資產（`doro_app/res/Dororong_Live2D_Model_/`）**封存保留**，只砍程式碼。

**關鍵設計點（為什麼 pickup 免費 fallback 到 GIF）：**

`StateService.get_gif_path()` 原本有「Priority 0: Live2D model path」的短路——某 state 若設了 `live2d_model_path` 就優先回傳模型路徑。移除這個欄位與短路後，解析自動落到 Priority 1（多 GIF 子資料夾）／Priority 2（`gif_id` 單檔），所以每個 state（含 pickup/held）都自然退回它的 GIF，零額外邏輯。

**修法：**

- 刪整支 `doro_app/ui/rendering/live2d_sprite_renderer.py`——它是唯一的 OpenGL/Cubism 消費者，整套 GL 依賴隨之移除。
- `State` 移除 `live2d_model_path` 欄位；`StateService` 移除 Priority 0 短路；`GifStateRepository` 移除存/讀該欄位的邏輯。舊 config JSON 若殘留 `live2d_model_path` key，因 `data.get()` 會被靜默忽略，**無需 migration**。
- `SpriteController`：移除 Live2D import、`live2d_unavailable` signal、renderer 註冊、`.model3.json` 載入分支、`_load_live2d()`；`tick()` 改成通用「推進當前渲染器」hook（GIF 由 QMovie 驅動，對它是 no-op）。
- `app.py` / `window.py`：移除 `renderer_type == "live2d"` 死判斷、`_on_live2d_unavailable`、signal 接線，順修相關註解。
- `themed_menu.py` / `context_menu_controller.py`：移除「Use Live2D」選單項、`using_live2d` / `live2d_available` snapshot 欄位、`toggle_live2d` 接線與 `_toggle_live2d()`；連帶清掉只服務該 toggle 的 `reload_sprite` 參數與其 `Callable` import。
- `paths.py`：移除 `LIVE2D_MODEL_PATH` 常數。
- `README.md`：拿掉「Live2D model support」功能條目。

**修改檔案：**

- `doro_app/ui/rendering/live2d_sprite_renderer.py`（刪除，-299 行）
- `doro_app/core/state/models.py`
- `doro_app/core/state/service.py`
- `doro_app/core/state/repository.py`
- `doro_app/ui/controllers/sprite_controller.py`
- `doro_app/ui/controllers/state_controller.py`
- `doro_app/ui/components/context_menu_controller.py`
- `doro_app/ui/theme/themed_menu.py`
- `doro_app/ui/window.py`
- `doro_app/app.py`
- `doro_app/utils/paths.py`
- `README.md`

**新增測試：**

- `tests/core/state/test_live2d_removal.py` — 兩條回歸測試釘死決策：(1) `State` 不再帶 `live2d_model_path` 欄位；(2) 精靈解析 fallback 到 state 的 GIF（代表 pickup 行為）。

**Commit：**

- `ed5cfe2` — `Remove Live2D rendering support`

**驗證：**

- `compileall` + 全變更模組 import 通過。
- state 測試 194 passed（含新回歸測試）；smoke / integration / UI 測試 117 passed。

**Follow-up（已記入 `docs/BACKLOG.md`）：**

可插拔渲染器架構目前只剩 `GifSpriteRenderer` 一支。是否要新增其他渲染器（如 Spine）、或反過來收掉這層抽象，留待評估後另開 issue 決定。

---

### 2. ✅ 順修既有 Windows 路徑分隔符測試 bug

**症狀：**

`tests/core/state/test_multi_gif.py::TestGifRepositoryAddGif::test_add_gif_creates_subfolder` 在 Windows 上失敗。

**根因：**

斷言寫死正斜線：`assert "stand/" in resource_id`。`GifRepository.add_gif` 產出的 `resource_id` 使用 OS 分隔符，在 Windows 上是 `stand\stand_1.gif`（反斜線），故 `"stand/" in ...` 為 False。與 Live2D 無關，是既有跨平台測試 bug（作者應在 macOS/Linux 上撰寫）。

**修法：**

比對前先正規化分隔符：`assert "stand/" in resource_id.replace("\\", "/")`，保留原測試意圖（resource_id 指向 `stand/` 子資料夾）且跨平台成立。

**修改檔案：**

- `tests/core/state/test_multi_gif.py`

**Commit：**

- `ed5cfe2`（與項目 1 同一 commit）

**驗證：**

`test_multi_gif.py` 33 passed。

---
