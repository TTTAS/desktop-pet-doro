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

### Chat setup

Doro connects to an OpenAI-compatible chat endpoint. Configure the server URL, model, and other settings through the in-app chat settings dialog.

### 安靜陪伴與自由休息點

- 右鍵選「我先忙（安靜陪伴）」：暫停自主說話、漫遊與分頁主動評論。沒設定休息點時，Doro 就留在原處陪伴；仍可點她或主動聊天。取消勾選可恢復原有自主行為。
- 拖到喜歡的位置，右鍵選「把這裡設為休息點」。同時記住左右位置與高度，可以設在螢幕中央，不必貼底。安靜模式會回到該處；互動結束、泡泡消失並安靜 8 秒後再次返回。選「清除休息點（原地陪伴）」可取消自動返回。
- 休息點以目前螢幕可用區域的水平／垂直比例儲存；切換螢幕或解析度時，套用到目前螢幕並遵守角色本體邊界。休息點是位置記錄，沒有床或窩的圖片。
- 先從 States 選擇喜歡的姿勢，再選「用目前姿勢休息」。未設定或素材狀態已刪除時使用 idle，無需新增 GIF 或呼叫模型。
- 底部互動目前停用，選單不再提供開關；即使舊設定曾開啟，也不會自動下落或輕蹲。放手只校正角色本體的螢幕邊界，保留自由擺放。
- 泡泡與角色邊界分開計算：開關泡泡、不同尺寸 GIF 與轉場都保留腳底位置，泡泡在底部改放上方。GIF 接地点採載入時首個有效畫面的非透明範圍並固定，避免逐幀追蹤造成抖動；自帶浮空動作或不透明背景的素材仍可能看起來離地。

模式、休息點與休息姿勢都會儲存。螢幕可用區域底部（通常為工作列上緣）只作邊界判斷，不是強制休息位置。從只有水平位置的舊版設定升級時，休息點視為尚未設定，保留原有其他設定；需要自動返回時，重新選一次「把這裡設為休息點」。

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
