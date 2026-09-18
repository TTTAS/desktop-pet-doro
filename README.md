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
