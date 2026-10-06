# Doro 文件索引

先按任務定位，不必依序讀完整個 docs。程式碼、測試與已採用 ADR 優先於舊計畫和工作紀錄。

## 目前的工作入口

| 需要 | 先看 |
| --- | --- |
| AI 開始修改 repo | [AGENTS.md](../AGENTS.md) → [repo 地圖](REPO_MAP.md) 的相關功能列 |
| 查當前類別、函式、行號及 import | `python scripts/repo_map.py --focus 功能或符號`；[工具說明](ai/WORKFLOW.md) |
| 看功能責任與主要入口 | [功能細節導覽](ai/FEATURE_GUIDE.md)，只讀相關段落 |
| 對齊產品用詞 | [CONTEXT.md](../CONTEXT.md) |
| 安裝與啟動 | [README](../README.md) |
| 分頁陪伴配對、驗收 | [分頁陪伴設定](web-presence-setup.md) |
| 活潑節奏、休息 GIF 與腳底校正 | [活潑陪伴計畫與驗收](companion-liveliness-plan.md) |
| 執行測試 | [AGENTS.md 的測試命令](../AGENTS.md)、[pyproject.toml](../pyproject.toml)；[測試指南](TESTING.md) 作背景 |

## 架構決策（已採用）

- [0001：三個網頁表面](adr/0001-three-web-surfaces.md)
- [0002：兩層活潑](adr/0002-two-layer-liveliness.md)
- [0003：擴充與 localhost WebSocket](adr/0003-extension-localhost-websocket.md)
- [0004：角色回覆與網站操作](adr/0004-character-replies-and-operation-safety.md)
- [0005：結構化回覆與提示詞分層](adr/0005-structured-llm-replies.md)

## 按需參考

- [架構背景](ARCHITECTURE.md)：較早的整體設計說明；可能未涵蓋新模組，目前入口以 repo 地圖為準。
- [聊天視窗設計](chat_dialog_design.md)、[網路失敗台詞](network_fail_messages.md)、[日誌指南](LOGGING_GUIDE.md)。
- [最佳實踐與教訓](BEST_PRACTICES.md)：歷史經驗，不要求每次任務先讀。

## 歷史、計畫與待辦

以下記錄當時的方案或結果，不是目前實作的保證；需要理解變更背景時才讀。

- [分頁陪伴實作計畫](web-presence-plan.md)、[查證重構計畫](verify-refactor-plan.md)、[查證驗收清單](verify-stage1-checklist.md)。
- [狀態重構計畫](state-refactor-plan.md)、[架構改進待辦](architecture-deepening-backlog.md)、[Backlog](BACKLOG.md)、[Open Claw TODO](TODO_OPEN_CLAW.md)。
- [重構總結](REFACTORING_SUMMARY.md)、[改進總結](IMPROVEMENTS_SUMMARY.md)、[舊審查](review.md)、[舊覆蓋率報告](TEST_COVERAGE_REPORT.md)。
- `CHANGELOG_session_*.md`、`pr-*.md`：個別變更紀錄；用 `rg --files docs` 按日期或主題查找。

新增文件時放到適合的分類，不維護容易過時的總數或每次對話摘要。
