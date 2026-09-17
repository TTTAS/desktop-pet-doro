# Doro：按需取得 repo 脈絡

PySide6 桌面寵物，Python >=3.10；含聊天、角色動作、指令上網與只讀分頁分享。

## 每次工作先定位

1. 看 `git status --short` 與本次目標；保留既有未提交修改。
2. 讀 `docs/REPO_MAP.md` 的相關功能列，不必預先通讀所有原始碼、docs 或資源。
3. 執行 `python scripts/repo_map.py --focus presence` 取得入口、符號、內部 import 與測試位置。
   focus 也接受中文別名、路徑或符號，例如 `分頁`、`PresenceController`、`doro_app/core/chat/orchestrator.py`。
4. 用 `rg -n '符號' 路徑` 與局部讀取查看目標函式、直接呼叫者及相關測試。跨模組修改才擴大範圍。
   地圖是定位提示，不代替實作與驗證，也不限制完成任務所需的檢查。

## 文件分工

- `CONTEXT.md`：產品語彙；`docs/adr/`：已採用的架構決策。
- `docs/ai/FEATURE_GUIDE.md`：按功能選讀的詳細說明。
- `docs/ai/WORKFLOW.md`：地圖工具、維護與限制。
- `docs/INDEX.md`：文件索引。舊計畫、CHANGELOG、review、覆蓋率報告是歷史參考，不能當成目前行為。
- `doro_app/res/` 與影像資源只在素材、設定格式或資源載入任務中讀取。

## 修改邊界

- 組裝在 `app.py`／`bootstrap.py`；切狀態走 `StateService`，走路走 `MovementManager`，串接動作走 `ActionDispatcher`。
- GUI 更新留在 Qt 主執行緒；Playwright session 留在 `WebRuntime` 的專屬執行緒。
- 一般瀏覽器分享與 Doro 操作瀏覽器分開；頁面回答只走角色表現入口，不升級成桌面或網站操作。

## 驗證與維護

- 單元測試：`python -m pytest tests/相關路徑 -o addopts= -q`。
- 完整測試：`python -m pytest tests --ignore=tests/manual -o addopts= -q`；無畫面環境設 `QT_QPA_PLATFORM=offscreen`。
- 瀏覽器測試：安裝 `.[test,web]` 和 Chromium，設 `DORO_BROWSER_TESTS=1`，跑 `tests/browser`；只用隔離設定檔與假資料。
- 新增／搬移模組、變更公開介面後跑 `python scripts/repo_map.py --write`，將更新的地圖一起提交。
- 功能職責或入口改變時，同步編輯 `docs/ai/areas.json`；`python scripts/repo_map.py --check` 檢查路徑及生成內容是否一致。
