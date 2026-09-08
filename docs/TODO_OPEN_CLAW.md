# TODO：把 OpenClaw 讓 agent「活」的機制內化進 Doro

> 決策背景：評估過「把 OpenClaw（Node.js agent gateway）接進 Doro」，
> 否決了當依賴的做法（語言隔閡、雙大腦、要多養一個常駐服務、權限風險）。
> 改採：**把它那幾個讓 agent 活起來的機制，用 Python 內化進 Doro**，
> 保留既有安全閘與測試。相關評估：`docs/`（OpenClaw 可行性分析那次對話）。
>
> 狀態：尚未動工（VERIFY 搜尋重構只是把一個工具修穩，不屬於下列任何一根柱子）。

## 四根柱子（依「活靈活現 / 投入」CP 值）

### ② 持久記憶（檔案式）— 建議先做
- OpenClaw：`MEMORY.md` + 每日 log，純 Markdown/YAML，跨 session 記得使用者。
- Doro 現況：關掉重開基本不記得你。
- 要做：一個本機記憶層（她認識的你、今天發生的事）。純本機檔案、零資安面。
- 為什麼先做：體感升級最大、風險最低，而且 ① 和 ③ 都要靠它當地基
  （迴圈要記中間結果、心跳要記目標）。

### ① 真正的 agent 迴圈（多步）
- OpenClaw：模型 → 執行工具 → 結果餵回 → 重複到任務完成。
- Doro 現況：基本單輪；`_auto_read_used` 一輪只自動讀一次。
- 要做：在 Python 裡寫受控的多步迴圈，跑在**既有執行器 + 安全閘**之上
  （web operator / pynput / 狀態 / 移動）。
- ⚠️ 代價：能讀網頁 / 點擊的多步迴圈一樣會被 prompt injection 打到。
  **安全閘要跟迴圈一起長，不能事後補。** 守門的是自家 code，改得動、測得到。

### ③ 自主心跳
- OpenClaw：heartbeat 讀 `HEARTBEAT.md` 清單，決定要不要主動找你；也吃 cron/webhook。
- Doro 現況：**已有 `idle_behavior_manager`** 這個雛形（閒置會自己講話 / 走動）。
- 要做：把「隨機閒置行為」升級成「有目標 / 清單」的行為——閒下來能推進交代的事、
  或依時間主動做點什麼。先決定「只在前景 / 有人時跑」還是要處理無人情境。

### ④ 結構化人格 + 上下文組裝
- OpenClaw：每輪把 `SOUL.md`（她是誰）/ `TOOLS.md`（她會什麼）/ `MEMORY.md`（她記得什麼）
  組進上下文。
- Doro 現況：`dia_prompt.txt` / `companion.txt` 比較散。
- 要做：人格 / 能力 / 記憶分檔、每輪穩定組裝進提示詞 → 人格一致。

## 建議起手順序
② 記憶（地基）→ ③ 心跳（借用 idle_behavior_manager）→ ① agent 迴圈（含安全閘）→ ④ 人格組裝。

## 備忘
- 之前也提過「讓 Doro 自己當 MCP server，把能力開給別的 AI（如 Claude 桌面）用」——更後面的項目。
- 開工前先開 grill / 設計討論，把該柱子的規格釘死再寫（跟 VERIFY 那次同一套流程）。
