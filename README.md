# Doro - Desktop Pet Companion

A desktop pet (shimeji-style) application built with PySide6. Doro is a cute chibi companion that lives on your desktop, responds to clicks, chats with you via LLM, and acts on her own when you're away.

![Doro idle animation](doro_app/res/state/idle.gif)

## Features

- **Animated GIF sprites** with idle bobbing, state transitions, and walking animations
- **LLM-powered chat** via configurable endpoint (LM Studio, OpenAI-compatible APIs, etc.)
- **Idle behavior** - Doro speaks, moves, and changes poses autonomously when you're away
- **State system** - multiple visual states with animated transitions between them
- **Directional movement** - Doro can walk around your screen
- **Always-on-top** transparent window with click-through support
- **Speech bubble** overlay for dialogue display
- **Preflight checks** - validates Python version, PySide6, and display server before launch

## Requirements

- Python 3.10+
- PySide6 6.5.0+
- A display server (X11 or Wayland on Linux)

Optional:
- A local OpenAI-compatible LLM server (e.g. LM Studio at `http://127.0.0.1:1234`) for chat functionality

## Installation

```bash
git clone https://github.com/TTTAS/doro-exp-.git
cd doro-exp-
pip install -e .
```

## Usage

```bash
python doro.py
```

### Command-line options

| Flag | Description |
|------|-------------|
| `--not-topmost` | Don't keep the window always on top |
| `--test-chat [MESSAGE]` | Send a test chat request and exit |

### 素材工廠（整合 DORO2）

右鍵 Doro →「素材工廠（影片去背）…」，可直接製作及匯入桌寵動畫。

先在 doro 的 Python 環境安裝素材套件：

```bash
python -m pip install -e ".[factory]"
# 需要 AI 去背時（包含上述素材套件）：
python -m pip install -e ".[factory-ai]"
```

- 多選 MP4，以清單切換影片、滑桿挑影格，對照原圖與透明棋盤格預覽。
- 支援 isnet-anime AI 去背、AI 邊緣柔化、點圖取色、顏色容差與邊緣內縮。
- 全部影片使用同一組設定，輸出透明 WebP／APNG；也可把目前影格存成 PNG。
- 在原尺寸去背後才縮小（預設長邊 200 像素）；記住輸出資料夾、格式及尺寸，沿用 DORO2 的 `.gif_factory.json`。
- 輸出同名時自動加編號，不覆蓋之前的成品。取消批次會保留已完成的檔案；取消或關閉時需等目前影格／編碼完成。
- 選取成品後，可匯入既有姿勢或建立新姿勢，再從 States 切換。PNG 作為單張圖片儲存，不匯入動畫姿勢。
- 處理都在本機；第一次 AI 去背會下載模型，圖片與影片不會上傳。未裝 AI 套件仍可使用顏色去背。

命令列功能也已移入 doro，不需要另外保留 DORO2 才能使用：

```bash
python -m doro_app.core.gif_factory input.mp4 output.webp --size 200
python -m doro_app.core.gif_factory a.mp4 b.mp4 --out-dir output --fmt apng
python -m doro_app.core.gif_factory input.mp4 frame.png --frame 40
```

命令列沿用 AI 預設去背；調色、柔化及內縮請使用素材工廠視窗。
快速驗證：`python -m pytest tests/gif_factory tests/ui/dialogs/test_asset_factory_dialog.py -m "not slow" -o addopts= -q`。

### Chat setup

Doro connects to an OpenAI-compatible chat endpoint. Configure the server URL, model, and other settings through the in-app chat settings dialog.

### 懸浮聊天窗

啟動後會直接顯示粉紅色置頂輸入列，可以立即打字，不用先點浮鈕或開選單。

- Enter 送出，Shift+Enter 換行；中文輸入法組字中的 Enter 不送出。送出後保留輸入列，可繼續聊天。
- ↑ 從輸入列上方向上展開聊天紀錄，↓ 收回；通常保持輸入列位置不變，上方空間不足才移入螢幕內。
- × 真正隱藏整個聊天介面，保留草稿與本次紀錄；右鍵「與 Doro 說話…」可重新叫出。Esc 先收起紀錄，再按一次隱藏。回覆不會自動展開或搶焦點。
- 拖曳輸入列左邊的三點把手可移動位置。
- 訊息與 Doro 的泡泡回覆顯示在窗內，處理中的訊息顯示在狀態區。網頁操作中暫不接收普通聊天時，保留輸入且不新增送出紀錄，也不自動重送；連線失敗時，若未開始寫下一句，會恢復剛送出的內容。網頁操作中的確認／取消仍沿用原流程。
- 操作輸入列或展開紀錄時暫停自主散步與回休息點；只把未使用的輸入列留在畫面上不會停止 Doro 的活動。聊天窗獨立於角色視窗，不影響腳底位置。
- 顯示紀錄限最近 200 則，只保留於本次執行記憶體。Chat → Clear conversation history 同步清除模型紀錄與視窗紀錄；連線設定在展開紀錄區內。傳送失敗時 ↑ 會改成 !，滑鼠移上可看提示，點擊可查看完整狀態與實際拒收／失敗原因（例如正在操作網頁、未設定伺服器或連線錯誤）。

設計與驗收見 [懸浮聊天窗計畫](docs/floating-chat-plan.md)。

### 安靜陪伴與自由休息點

- 右鍵「陪伴設定…」直接輸入活動間隔（1–3600 整數秒，預設 9 秒），儲存後重新計時。舊的活潑／適中／悠閒設定會轉成 9／60／120 秒。每次散步約 100–240 邏輯像素，交替可用姿勢、原地小動作與本機台詞；說話仍至少間隔 90 秒。聊天、輸入、泡泡、拖曳、選單、設定視窗、移動或轉場忙碌時延後動作；非安靜模式使用者互動後至少等 4 秒。
- 關掉安靜陪伴後，約 4 秒先嘗試走走，不再等上一輪安靜計時。若仍忙碌，非安靜模式每 2–3 秒檢查能否恢復。安靜模式保留原節奏與 8 秒互動緩衝。
- 點一下會有短暫摸摸愛心，仍可搭配 Actions 的點擊 GIF。拖曳不觸發愛心；小動作只改繪製，不推動視窗或腳底。設定中的「小動作與摸摸愛心」可一次關閉這些效果。
- 「陪伴設定… → 自主姿勢」可勾選允許她自行播放的姿勢，預設僅 happy。生氣、失敗與新匯入姿勢不會自動加入；沒有可用候選時改做原地小動作，關閉小動作則略過。
- 右鍵選「我先忙（安靜陪伴）」：暫停自主說話、漫遊與分頁主動評論。沒設定休息點時，Doro 就留在原處陪伴；仍可點她或主動聊天。取消勾選可恢復原有自主行為。
- 安靜時每 45–90 秒嘗試一次原地伸展，沒有文字、不更換休息姿勢；忙碌時不播放。關閉小動作後則完全保留 GIF 本身的動畫。
- 拖到喜歡的位置，右鍵選「把這裡設為休息點」。同時記住左右位置與高度，可以設在螢幕中央，不必貼底。安靜模式會回到該處；互動結束、泡泡消失並安靜 8 秒後再次返回。選「清除休息點（原地陪伴）」可取消自動返回。
- 休息點以目前螢幕可用區域的水平／垂直比例儲存；切換螢幕或解析度時，套用到目前螢幕並遵守角色本體邊界。休息點是位置記錄，沒有床或窩的圖片。
- 休息點靠近邊界而走路 GIF 較寬時，會停在實際可達的位置，不在最後瞬移貼齊，也不反覆原地走。
- 在「陪伴設定…」直接選休息姿勢並預覽，也能「匯入休息 GIF…」建立新姿勢；按儲存才匯入，取消不改設定。原本「States → 用目前姿勢休息」仍可使用；素材狀態已刪除時使用 idle。
- 安靜時儲存休息姿勢會立即在原地套用；聊天／動作忙碌時等到結束。沒設休息點也會在互動後恢復休息姿勢。手動選 States 則保留該姿勢到下次互動，方便慢慢挑選再儲存。
- 底部互動目前停用，選單不再提供開關；即使舊設定曾開啟，也不會自動下落或輕蹲。放手只校正角色本體的螢幕邊界，保留自由擺放。
- 泡泡與角色邊界分開計算：開關泡泡、不同尺寸 GIF 與轉場都保留腳底位置，泡泡在底部改放上方。GIF 接地点採載入時首個有效畫面的非透明範圍並固定，避免逐幀追蹤造成抖動；自帶浮空動作或不透明背景的素材仍可能看起來離地。
- 若個別 GIF 看起來浮起，可在「陪伴設定… → 腳底校正」點預覽圖上的腳掌位置或調整百分比，儲存後只套用到該 GIF；也可還原自動估計。校正以目前 GIF 檔案路徑保存，移動／重新匯入檔案後需重新校正；若顯示的是無 GIF 的備用角色，不提供這個分頁。
- 點擊／拖曳的暫時 GIF 沿用目前姿勢的接觸邊界與校正值；校正預覽也顯示該姿勢，不會因暫時動畫開關而跳動。

模式、休息點與休息姿勢都會儲存。螢幕可用區域底部（通常為工作列上緣）只作邊界判斷，不是強制休息位置。從只有水平位置的舊版設定升級時，休息點視為尚未設定，保留原有其他設定；需要自動返回時，重新選一次「把這裡設為休息點」。

本次設計與驗收項目見 [活潑陪伴計畫](docs/companion-liveliness-plan.md)。

## Project Structure

For AI-assisted work, start with [AGENTS.md](AGENTS.md) and the compact
[repository map](docs/REPO_MAP.md). Retrieve only the relevant symbols with
`python scripts/repo_map.py --focus presence` (Chinese aliases such as `分頁` also work).
See [map usage and maintenance](docs/ai/WORKFLOW.md) for details.

```
doro_app/
  app.py                  # Application assembly (5-phase bootstrap)
  bootstrap.py            # Environment bootstrap and dependency injection
  cli.py                  # CLI entry points and argument parsing
  constants.py            # All application constants
  preflight.py            # Pre-launch environment validation
  core/
    core_manager.py       # Central tick loop and coordination
    idle_behavior_manager.py  # Autonomous idle actions
    chat/
      orchestrator.py     # Chat request lifecycle
      chat.py             # HTTP request handling
      controller.py       # UI-facing chat controller
      validator.py        # Response validation
    movement/
      manager.py          # Movement state and animation
      parser.py           # Movement instruction parsing
      repository.py       # Movement data loading
    state/
      service.py          # State machine logic
      transition_coordinator.py  # State transition orchestration
      transition_player.py       # Transition animation player
  ui/
    window.py             # Main transparent overlay window
    dialogs/
      chat_dialog.py      # Chat conversation window
      chat_settings_dialog.py  # Chat configuration UI
  utils/
    actions.py            # Action parsing (move, transition, etc.)
    config_manager.py     # Persistent configuration
    paths.py              # Resource path constants
    prompts.py            # Prompt file loading
  res/
    state/                # State GIF sprites and config
    ACTION/MOVE/          # Walking animation and movement data
    ACTION/TRANSITION/    # Transition animations and config
    companion.txt         # Idle dialogue lines
    click.txt             # Click response lines
```

## Testing

```bash
pytest
```

## License

See [LICENSE](LICENSE) for details.
# 分頁陪伴與上網角色動作

此分支加入上網結果的表情／走路整合，以及只讀分享目前分頁的 Chromium 擴充。
安裝與配對見 [分頁陪伴設定](docs/web-presence-setup.md)，六項修正與驗收見 [實作計畫](docs/web-presence-plan.md)。
