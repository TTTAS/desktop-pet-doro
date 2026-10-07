# PR #63：桌面陪伴與懸浮聊天交接紀錄

記錄日期：2026-10-07。程式基準：`d06c4c9`（聊天拒收與錯誤回報修正）。先前基準為 `333a9da`。
PR：[TTTAS/doro-exp- #63](https://github.com/TTTAS/doro-exp-/pull/63)。
分支：`codex/quiet-companion-grounding`，目標分支：`master`。

這是該版本的 review 交接快照。後續程式若修改，請更新此處的基準、驗證與待修狀態；目前行為仍以程式、測試和 README 為準。

## 目的與最終範圍

讓 Doro 在使用者想互動時活潑、忙碌時能安靜陪伴，修正透明留白造成的角色邊界問題，並讓聊天可以直接從畫面上的輸入列開始。

| 範圍 | 本 PR 的結果 | 主要 review 入口 |
| --- | --- | --- |
| 安靜陪伴與休息點 | 停止主動漫遊、發話與分頁評論；休息點保存水平與垂直比例，未設時原地陪伴 | `core/companion.py`、`app.py`、`core/presence/` |
| 自主活動與摸摸 | 本機散步、允許的姿勢、小動作與台詞；點擊短暫愛心；使用者工作可打斷背景動作 | `core/idle_behavior_manager.py`、`core/action/phases.py`、`ui/rendering/pet_expression.py` |
| 陪伴設定 | 活動間隔直接輸入 1–3600 整數秒，預設 9 秒；休息 GIF 匯入、預覽、自主姿勢清單 | `ui/dialogs/companion_dialog.py`、`utils/config_schema.py`、`utils/config_manager.py` |
| 邊界與 GIF 校正 | 分開計算角色本體與泡泡邊界，版面變化保持腳底；可依 GIF 校正腳底線 | `ui/window.py`、`ui/layout/layout_manager.py`、`ui/rendering/`、`core/movement/manager.py` |
| 懸浮聊天 | 粉色置頂輸入列常駐，紀錄向上展開，× 隱藏；右鍵「與 Doro 說話…」叫回 | `ui/dialogs/floating_chat.py`、`ui/helpers/chat_ui_helper.py`、`ui/theme/themed_menu.py` |

表內程式路徑均相對於 `doro_app/`。本 PR 另保留先前 `recent_page(0)` 到期比較修正與少量 import 排序。

## 舊計畫與目前決策

初版 `doro-companion-plan.pdf` 是歷史提案，不能再作為本 PR 完整驗收規格。這次選擇補齊文件與 PR 說明，保留現有分支歷史，未拆出聊天 PR。

- **底邊不是窩。** 休息點是座標記錄，沒有新增床或窩的圖片；可放在任意高度。底部下落與輕蹲已依使用者要求移除，螢幕底部只參與邊界判斷。
- **活潑程度由秒數控制。** 最新介面已移除活潑／適中／悠閒選項，先前文件中的 6–12 秒等範圍是歷史設定。指定秒數是嘗試活動的間隔；聊天、拖曳、選單或動作未結束會延後，不強制打斷。
- **聊天入口是常駐輸入列。** 初版浮鈕設計已被取代。聊天框目前是獨立位置，不跟著 Doro 散步；啟動時顯示並置頂，× 只隱藏本次執行。重複的 Chat → Ask Doro 已移除。
- **沿用現有素材與動作系統。** 沒有新增角色 GIF。自主短姿勢使用 Action／VisualPhase，走路使用 MovementManager；只取消背景自己擁有的動作，不清掉使用者佇列。

兩份詳細計畫保留設計歷程：[陪伴計畫](companion-liveliness-plan.md)、[聊天計畫](floating-chat-plan.md)。最新使用方式見 [README](../README.md)。

## 設定相容性

- `companion_interval_seconds` 儲存自訂秒數。未有新鍵時，舊 `companion_activity` 的 lively／balanced／calm 分別轉為 9／60／120 秒；新值優先，無效值回到 9 秒而不重設其他偏好，存檔移除舊鍵。
- 只有水平休息點的舊設定，升級後視為未設定完整休息點；需要自動返回時重新設定位置。舊 `companion_floor_interaction` 不再使用，存檔清除。
- GIF 腳底校正按完整檔案路徑保存，搬移或重新匯入後可能需重設。點擊／拖曳暫時 GIF 沿用目前姿勢的校正。
- 聊天顯示紀錄最多 200 則，只在本次執行的記憶體內；隱藏保留草稿與紀錄，重啟不保存這份顯示紀錄。

## 聊天審查修正與限制

先前依使用者要求只改秒數與選單，保留以下兩項問題；本輪已於 `d06c4c9` 修正並加回歸測試。下表保留原問題與修正結果供追溯。

| 項目 | 原問題重現／影響 | 已完成修正與驗收 |
| --- | --- | --- |
| 網頁操作中誤判普通聊天已送出 | Doro 操作網頁且不在等待確認時，送出普通訊息。操作處理回傳 True，但只提示稍等，輸入列因此清掉草稿並留下使用者訊息 | `core/chat/orchestrator.py` 的 `_handle_message_while_operating`、`floating_chat.py` 的 `send`；現在回傳拒收並保留草稿，不新增假紀錄、不自動重送；實際 app 接線測試覆蓋此路徑。停止與確認指令仍可接受 |
| 失敗原因被通用文案遮住 | 未設定伺服器或請求失敗時，輸入列只顯示通用提示；`request_failed` 未呈現收到的錯誤原因 | 協調層拒收結果、`ui/helpers/chat_ui_helper.py`、`floating_chat.py`；現在把同步拒收原因傳入狀態區，非同步失敗呈現原始錯誤文字；保留草稿、不覆蓋新輸入，重試成功清除舊提示。測試涵蓋缺少伺服器、忙碌、非同步失敗與自動請求隔離 |

其他限制：聊天框不跟隨角色、隱藏狀態不跨重啟保存；目前沒有自動偵測其他程式是否正在打字或工作。這些是現況紀錄，本輪未另加功能。Windows 原生輸入法候選窗、跨程式置頂、混合 DPI、多螢幕與工作列自動隱藏仍待實機驗收。

## 驗證紀錄

下列結果來自程式基準 `d06c4c9` 的本機驗證，不是 GitHub CI 結果。本輪修正前先重現草稿清空與錯誤原因遺失，修正後重跑完整測試。後續交接文件提交僅更新紀錄。

| 檢查 | 結果 |
| --- | --- |
| 完整 pytest（Qt offscreen，排除 manual） | **1120 passed、3 skipped**；3 項為未啟用的瀏覽器驗收 |
| Black 26.3.1、Ruff 0.16.8 | `doro_app`、`tests` 通過；不包含根目錄與工具腳本的既有格式問題 |
| repo_map、diff | `python scripts/repo_map.py --check`、`git diff --check` 通過 |
| Qt 畫面 | 查看 450 × 499 的最新設定頁；先前已查看 460 × 72 輸入列與 460 × 352 展開紀錄。皆為離屏預覽 |

在安裝專案測試依賴的環境，從 repo 根目錄重跑：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest tests --ignore=tests/manual -o addopts= -q --tb=short
python -m black --check doro_app tests
python -m ruff check doro_app tests
python scripts/repo_map.py --check
git diff --check
```

建議 reviewer 依序查看：設定保存與舊值轉換 → 背景動作中斷／所有權 → GIF 邊界 → 聊天 UI 接線。關鍵測試在 `tests/test_config_manager.py`、`tests/core/test_companion.py`、`tests/core/test_idle_behavior.py`、`tests/ui/test_grounding.py`、`tests/ui/test_companion_preferences.py`、`tests/ui/test_companion_app.py`、`tests/ui/test_floating_chat.py`。

實機驗收仍需確認：自訂 23 秒後儲存與重啟；切換安靜並在散步中拖曳／聊天；螢幕四角切換不同 GIF 與泡泡；中文組字、聊天紀錄展開、隱藏再叫回。網頁操作期間送普通聊天應保留草稿並顯示拒收原因；等待操作確認時仍沿用原本的肯定／否定處理。

## 提交里程碑

| 提交 | 內容 |
| --- | --- |
| `8942708`、`fbbc06e` | 初版安靜陪伴、腳底定位及回窩動作所有權修正 |
| `99b716a`、`cced513` | 自由休息點，之後停用底部互動與移除選單 |
| `f578f43`、`c586a89` | 活潑節奏、摸摸與設定；修正校正、休息恢復及邊緣到達 |
| `bbbc8e6`、`535d738` | 懸浮聊天，接著依使用者要求改為常駐輸入列與向上紀錄 |
| `a80100c` | 非安靜模式更活潑、切換後快速恢復 |
| `333a9da` | 自訂活動秒數與舊設定轉換，移除 Chat → Ask Doro |
| `d06c4c9` | 網頁操作中普通聊天拒收保留草稿；聊天框顯示真正拒收／失敗原因，補回歸測試 |
