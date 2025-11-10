# Repository Guidelines

## Project Structure & Module Organization
`doro.py` hands off to `doro_app/cli.py`, which instantiates the PySide6 window in `window.py`. UI widgets delegate to focused modules: `chat_controller.py` stores the rolling chat history, `chat_orchestrator.py` drives prompts and actions, `state_manager.py` and `movement_manager.py` load GIF metadata, while `bubble_controller.py` and `workers.py` animate frames. Shared data structures live in `models.py` and `actions.py`, and all filesystem lookups go through `paths.py` to keep the app portable. Assets reside under `res/`: dialogue prompts (`dia_prompt.txt`), click responses, and action sprites split into `res/ACTION/MOVE` and `res/ACTION/TRANSITION`, each containing GIFs referenced by the editors.

## Build, Test, and Development Commands
- `python -m venv .venv && .venv\Scripts\activate` (PowerShell: `.\.venv\Scripts\Activate.ps1`) isolates dependencies.
- `python -m pip install -U pip wheel && pip install PySide6` installs the GUI toolkit; add any extra packages per-feature.
- `python -m doro_app.cli` launches the desktop pet; pass `--not-topmost` or `--test-chat "hi"` to exercise alternative code paths.
- `python -m doro_app.cli --dump-config` (see `cli.py`) is handy to verify resolved paths when debugging on another PC.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indents, type hints, and descriptive method names (`perform_chat_request`, `pick_random_state_for_direction`). Snake_case filenames ensure text assets (`state_list.txt`, `action_list.json`) line up with GIF stems. Keep chat- and state-related constants inside `config_defaults.py` or `paths.py`; avoid absolute Windows paths in code. UI strings belong in the corresponding Qt widget, while prompts and system text stay in `res/` so artists and writers can iterate without touching Python.

## Testing Guidelines
Unit tests should land under `tests/`, mirroring module names (`tests/test_chat_controller.py`, `tests/test_state_manager.py`). Focus first on deterministic helpers such as `ChatResponseParser.extract_assistant_text`, action parsing, and random-selection utilities using seeded RNGs. Run suites via `pytest -q`; add `PYTHONPATH=.` when invoking from shells outside the repo root. Before shipping new GIF metadata or movement logic, replay `python -m doro_app.cli --test-chat "walk right 3"` to confirm the random chooser can find direction-appropriate actions.

## Commit & Pull Request Guidelines
Use short, imperative subjects (“refine action editor grid”) followed by a concise body describing motivation and follow-up tasks. Each PR should list touched modules, asset directories (`res/ACTION/MOVE`, `res/state`), screenshots for UI tweaks, and manual test notes (`--test-chat`, drag/drop in edit dialogs). Reference issue IDs or TODO anchors so future maintainers can trace why a module split occurred.

## Configuration & Portability Notes
`config_defaults.py` provides sane fallbacks (e.g., `DEFAULT_CHAT_SERVER_URL` derived from `DORO_CHAT_SERVER_URL`). Prefer `paths.py.app_root()` plus `Path("res")` over absolute strings so the app runs unchanged on other machines. Secrets or local URLs belong in environment variables or QSettings (`chat/server_url`, `chat/model`), never in committed Python. When adding assets, keep relative paths under 120 characters to avoid Windows MAX_PATH edge cases and document any new directories here.
