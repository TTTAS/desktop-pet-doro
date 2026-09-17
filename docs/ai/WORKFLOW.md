# 如何用少量脈絡處理 Doro

## 開始一個任務

AI 的固定入口是根目錄 `AGENTS.md`。`CLAUDE.md` 只指向同一份入口，避免維護兩套規則。
看地圖後，選相關模組，不必把詳細功能說明、整個 docs 或所有原始碼都放進上下文。

```powershell
python scripts/repo_map.py
python scripts/repo_map.py --focus 分頁
python scripts/repo_map.py --focus PresenceController --max-chars 5000
python scripts/repo_map.py --focus doro_app/core/chat/orchestrator.py
rg -n 'present_character_reply' doro_app tests
```

例如「修分頁換頁後的舊回覆」，先查 presence，再讀 controller 的結果交付流程及 chat 的角色表現入口；
接著看 presence／character reply 測試。只有涉及橋接事件或擴充資料才擴大到 bridge／extension。
測試位置是導覽，不代表必須一律執行整個列出的測試資料夾。

工具只用 Python 標準庫，不安裝 aider、不呼叫 LLM、不上傳 repo，也不匯入或執行 app 模組。
在 repo 根目錄使用上述命令；腳本本身也可用絕對路徑從其他工作目錄啟動。

## 地圖分成三層

| 檔案／工具 | 用途 | 維護方式 |
| --- | --- | --- |
| `AGENTS.md`、`CLAUDE.md` | 很短的工作入口及閱讀順序 | 流程有變才人工更新 |
| `docs/REPO_MAP.md` | 各功能職責、入口、測試與跨模組路徑 | 用 `--write` 產生，不直接手改 |
| `repo_map.py --focus …` | 當前符號、簽名、行號及一層相鄰 import | 每次從本機程式碼即時計算，不存第二份符號清單 |
| `docs/ai/FEATURE_GUIDE.md` | 原 CLAUDE.md 的詳細功能地圖 | 只讀相關段落；行為改變時更新 |
| `docs/ai/areas.json` | 模組分類、中文別名、入口與測試位置 | 新增功能或搬移入口時更新 |

`CONTEXT.md` 繼續只放語彙；`docs/adr/` 記錄架構選擇及取捨。工作紀錄留在 commit／歷史文件，
不要把每次對話摘要持續塞進固定入口。程式碼與可執行測試仍是目前行為的依據。

## 更新與 CI

```powershell
python scripts/repo_map.py --write
python scripts/repo_map.py --check
python -m unittest discover -s tests/tools -p test_repo_map.py
```

- 預設掃描 `doro.py`、`doro_app` 的 Python 程式及 `extensions` 的 JS，略過 `res`、素材與符號連結。
  不讀執行期設定、API key、使用者瀏覽器 profile、聊天紀錄或測試資料。
- 公開宣告與來源路徑的指紋讓新增／刪除／搬移模組、公開簽名變更可被 `--check` 發現。
  單純函式內部實作、註解或行號改變不會要求重寫總覽；focus 的行號則永遠取自當前檔案。
- 新模組必須落在 `areas.json` 的某個 scope，列出的入口與測試路徑必須存在。
- `.github/workflows/repo-map.yml` 在 push／PR 執行一致性及工具測試，不需安裝 PySide6。
  CI 失敗時在本機更新地圖，一併提交；CI 不會自動改 repo 或推送。

## 能力與限制

思路參考 [aider 的 repository map](https://aider.chat/docs/repomap.html)：用重要符號定位需要閱讀的程式。
這裡採較簡單的「路徑／符號命中 → 功能入口 → 一層 import 鄰居」排序，沒有聲稱完整實作 aider 的圖排名。
Python 用 AST 取類別、函式與方法簽名；JS 只辨識 function 宣告，沒有完整 JS parser。
import 關係包括 TYPE_CHECKING 分支，是靜態參考，不是實際呼叫圖；Qt signal、動態 dispatch、反射仍需用 rg 和原始碼追查。

輸出預設最多 12,000 **字元**，不是精確 token 數；截斷會明示。查無結果會報錯，避免回傳看似相關的整庫資料。
沒有持續增加的索引資料庫、背景服務或額外套件。摘要省的是送給模型的上下文；本機仍需掃描文字檔才能建立最新符號索引。
工具不會強制任何 AI 客戶端自動載入地圖；不支援入口文件的客戶端，需手動提供地圖或命令輸出。
