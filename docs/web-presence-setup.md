# Doro 分頁陪伴：安裝與驗收

## 安裝 App

在本分支根目錄、現有 Python 環境中執行：

```powershell
python -m pip install -e ".[web]"
python -m playwright install chromium
python doro.py
```

如果只用擴充讀頁，WS 依賴仍需要安裝；Playwright 用於 Doro 自己的指令上網。

Windows 使用者直接跑 `run_doro.bat`（或 `run_doro_debug.bat`）即可，它會建立 `.venv` 並安裝 `[web,automation,a11y]`。安裝與執行務必用**同一個** Python（腳本已用 `python -m pip` 確保）；否則 App 端會出現 `No module named 'websockets'`。腳本會記錄 `pyproject.toml` 的雜湊，**依賴清單有變動時自動重裝**；若仍缺套件，刪掉 `.venv\.doro_setup_done`（或整個 `.venv`）再跑一次即可強制重裝。

## 配對一般瀏覽器

1. Chrome／Edge 的擴充管理頁開啟開發人員模式，選「載入未封裝項目」，選 `extensions/doro-presence`。擴充內建固定金鑰，ID 每台機器都相同，App 已內建，不需複製 ID。
2. 右鍵 Doro → 聊天子選單 →「分頁陪伴設定…」，勾選接收分頁；若要主動回應，再勾選主動說話與動作。按「複製配對碼」（已含埠號），儲存 App 設定。
3. 點擴充圖示開設定頁，把整段配對碼貼到「配對碼」欄按儲存。貼上有效配對碼即自動開始分享，不需另外勾選。
4. 重新整理原本已開的網頁，將焦點切回一般 HTTP(S) 分頁。工具列 `ON` 表示已連線；`!` 表示等待／配對失敗。

配對碼格式為 `doro1.<埠號>.<配對碼>`，一段涵蓋埠號與密鑰。兩端預設關閉；取消擴充的分享勾選可立即停止分享，App 可以單獨停止主動反應、保留讀取能力。
更換配對碼後在擴充重貼一次即可。埠號已被占用時，在 App 改埠號後重新複製配對碼再貼到擴充。

## 來源與限制

- 「你剛開的頁」指 Doro 專屬瀏覽器；啟用擴充後的「這頁」指目前有效分享頁。
- 瀏覽器失去焦點、切內部頁、無痕頁、關閉或斷線時，不提供目前頁；主動反應不以旧頁假裝目前頁。
- 你主動問「這頁…」時，因為要切到 Doro 而讓瀏覽器失焦，仍可讀到你**剛剛看的那頁**（寬限約 30 秒，仍只留記憶體中的單一頁，斷線即失效）；主動反應維持嚴格，只對真正當前焦點頁反應。
- 只讀主文件可見文字，最多 6000 字元；沒有 iframe／圖片／影片／封閉 shadow DOM 辨識。
- 密碼、輸入欄位、編輯器文字不分享；一般正文仍可能有私人資訊，會送給 App 設定的聊天模型。
- 雜湊能去掉相同內容；不同措辭但同義的判斷依賴模型的開口判斷；`worth_saying` 為 false 表示這次不發言。

## 自動測試

```powershell
python -m pip install -e ".[test,web]"
python -m pytest tests --ignore=tests/manual -o addopts= -q
$env:DORO_BROWSER_TESTS='1'
python -m pytest tests/browser -o addopts= -q
```

browser 測試依照 [Playwright 官方擴充測試方式](https://playwright.dev/python/docs/chrome-extensions)，使用獨立 Chromium 設定檔與本機假網頁，不接觸個人瀏覽器或真實模型。

## 使用者模型實機驗收

- 讀公開文章：回答有根據，合法表情生效，可選走路後發言。
- 查證：某來源受阻仍能讀下一個；只有摘要時誠實交代。
- 在無副作用的測試網站操作：等待模型時說停，不再執行下一步。
- 開啟主動分頁反應：同頁不反覆說，換頁後不冒出前頁答案；模型不可用時基本陪伴繼續。
