# Doro 專案文檔索引

> **最後更新：** 2024-12-11
> **文檔總數：** 14

---

## 📋 核心文檔

### 🎯 必讀文檔

1. **[最佳實踐與教訓總結](BEST_PRACTICES.md)** ⭐ **NEW**
   - 過度工程化的教訓
   - 規模與複雜度對照
   - 架構設計原則
   - 重構檢查清單
   - 技術債管理
   - **適合：** 所有開發者，尤其是新加入專案的人

2. **[架構說明](ARCHITECTURE.md)**
   - 系統架構概覽
   - 模組職責說明
   - 依賴關係圖
   - **適合：** 理解整體架構

3. **[當前分層架構](CURRENT_LAYERS.md)**
   - 5 層架構詳解（資料層、領域層、應用層、UI 層、基礎設施層）
   - 層與層之間的依賴方向
   - 目前的架構問題
   - **適合：** 深入了解分層設計

---

## 📝 歷史記錄

### 重構與改進

4. **[重構總結](REFACTORING_SUMMARY.md)**
   - 2024-12-09 重構成果
   - CoreManager 創建
   - 循環依賴消除
   - 分層架構建立
   - **適合：** 了解重構歷史

5. **[改進總結](IMPROVEMENTS_SUMMARY.md)**
   - 歷次改進記錄
   - 已解決的問題
   - **適合：** 查看專案演進

6. **[變更日誌](CHANGELOG_session_2025-11-27.md)**
   - 2025-11-27 會話的變更記錄
   - **適合：** 追蹤具體變更

---

## 🏗️ 功能設計

### Chat 功能

7. **[Chat 架構](chat_architecture_current.md)**
   - ChatController 設計
   - ChatOrchestrator 職責
   - 聊天流程說明
   - **適合：** 開發聊天功能

8. **[Chat 對話框設計](chat_dialog_design.md)**
   - UI 設計
   - 互動流程
   - **適合：** UI 開發

9. **[網絡失敗訊息](network_fail_messages.md)**
   - 錯誤訊息設計
   - 用戶體驗考慮
   - **適合：** 錯誤處理

---

## 📚 開發指南

10. **[測試指南](TESTING.md)**
    - 測試策略
    - 測試工具使用
    - **適合：** 編寫測試

11. **[日誌使用指南](LOGGING_GUIDE.md)**
    - 日誌等級使用
    - 如何在新模組添加日誌
    - 日誌檔案位置
    - **適合：** 日常開發

---

## 📋 待辦與計劃

12. **[Backlog](BACKLOG.md)**
    - 待完成的功能
    - 已知問題
    - **適合：** 查看待辦事項

13. **[審查筆記](review.md)**
    - 代碼審查記錄
    - **適合：** Code Review

---

## 🎯 快速導航

### 我想...

| 需求 | 推薦文檔 |
|------|---------|
| **了解專案教訓和最佳實踐** | [最佳實踐](BEST_PRACTICES.md) |
| **理解系統架構** | [架構說明](ARCHITECTURE.md) → [分層架構](CURRENT_LAYERS.md) |
| **查看重構歷史** | [重構總結](REFACTORING_SUMMARY.md) |
| **開發聊天功能** | [Chat 架構](chat_architecture_current.md) |
| **編寫測試** | [測試指南](TESTING.md) |
| **添加日誌** | [日誌指南](LOGGING_GUIDE.md) |
| **查看待辦事項** | [Backlog](BACKLOG.md) |

---

## 📊 文檔分類統計

| 類別 | 文件數 | 文檔 |
|------|--------|------|
| **核心文檔** | 3 | BEST_PRACTICES, ARCHITECTURE, CURRENT_LAYERS |
| **歷史記錄** | 3 | REFACTORING_SUMMARY, IMPROVEMENTS_SUMMARY, CHANGELOG |
| **功能設計** | 3 | chat_architecture, chat_dialog_design, network_fail_messages |
| **開發指南** | 2 | TESTING, LOGGING_GUIDE |
| **待辦計劃** | 2 | BACKLOG, review |
| **本索引** | 1 | INDEX.md |
| **總計** | **14** | |

---

## 🗑️ 已清理的文檔（2024-12-11）

為了減少認知負擔和避免過時信息誤導，已刪除以下 24 個文檔：

**審計報告（已過時）：**
- ARCHITECTURE_AUDIT.md
- CONFIG_AUDIT.md
- ERROR_HANDLING_AUDIT.md
- MAGIC_NUMBERS_AUDIT.md
- CIRCULAR_DEPENDENCIES_ANALYSIS.md
- PHASE4_1_AUDIT.md

**階段計劃（已完成）：**
- PHASE1_COMPLETION_REPORT.md
- PHASE4_COMPLETE.md
- PHASE4_PLAN.md
- PHASE4_SUMMARY.md
- REFACTORING_PLAN.md
- SIMPLIFICATION_PLAN.md
- STATE_SERVICE_SPLIT_PLAN.md

**提案文檔（已實施或過時）：**
- ARCHITECTURE_PROPOSAL_V2.md
- REFACTORING_FEASIBILITY.md
- function_calling_proposal.md
- parsing_with_retry_proposal.md
- structured_output_proposal.md

**依賴分析（已解決）：**
- WINDOW_DEPENDENCIES_CURRENT.md
- WINDOW_DEPENDENCIES_PROPOSED.md
- WINDOW_LOGIC_EXTRACTION.md

**TODO（已完成或過時）：**
- TODO_transition_player.md
- chat_request_execution_todo.md
- enhanced_parsing_implementation.md

**清理原則：** 代碼是真相，過時的文檔比沒有文檔更糟糕。

---

## 📖 閱讀建議

### 新加入專案的開發者

1. 先讀 [最佳實踐](BEST_PRACTICES.md) — 了解專案的教訓和原則
2. 再讀 [架構說明](ARCHITECTURE.md) — 理解系統結構
3. 根據工作內容選讀相關文檔

### 參與重構的開發者

1. [最佳實踐](BEST_PRACTICES.md) — 重構原則和檢查清單
2. [重構總結](REFACTORING_SUMMARY.md) — 歷史重構經驗
3. [分層架構](CURRENT_LAYERS.md) — 當前架構問題

### 功能開發者

1. [相關功能設計文檔](chat_architecture_current.md)
2. [測試指南](TESTING.md) — 如何編寫測試
3. [日誌指南](LOGGING_GUIDE.md) — 如何添加日誌

---

**維護者：** Doro 開發團隊
**更新頻率：** 每次新增/刪除文檔時更新
