# ADR 0004：角色回覆與網站操作分開執行

- 狀態：採用
- 日期：2026-09-10

## 決策

- 讀頁、查證、操作完成與存在感共用 `ChatOrchestrator.present_character_reply`。
- 只接受已知狀態與一個方向型角色移動（left/right/up/down，1～600 px）。不接受桌面座標、滑鼠或網站命令。
- 生產環境沿用 ActionDispatcher 的 walk-and-speak：先完成走路，再發出台詞；沒有移動就直接說。內文引用括號保留。
- 開始背景工作前提供目前合法狀態清單；網頁資料的模型回覆不能再升級成另一個工具任務。
- 快照不以輸入值作元件名稱；password、current/new-password、one-time-code 標記為敏感，模型不代填。真正 fill 前再核對欄位種類，輸入失敗不記錄可能含值的 Playwright 錯誤。
- 取消在迴圈開頭、模型返回後、確認後的實際執行前檢查；已經發到瀏覽器的單次動作無法追回。
- 表單 submit/image/default button、空名稱或未知編號、送出關鍵字都需確認。只有已聚焦的 search input 且非敏感頁，普通 Enter 才直接放行；複合鍵與未知鍵需確認，Tab/Escape/方向等導覽鍵不需確認。

## 取捨

元件屬性與名稱是保守判斷，仍無法理解任意網站的自訂腳本副作用；不是所有網站不可逆行為的形式化保證。
動作已執行就不能靠取消還原。角色走路的既有故障逾時仍由 dispatcher 處理。
