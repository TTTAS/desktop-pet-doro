# Codebase Review Notes

- **Startup coupling remains high**: `DoroApp` still constructs the main window before controllers because managers depend on it, keeping a circular dependency that complicates testing and headless usage.
- **Orchestrator mixes orchestration with IO**: `ChatOrchestrator` performs synchronous file reads for failure text at runtime and drives UI timing directly, which can block the UI thread and hides errors behind random selection.
- **Movement manager reaches into window internals**: Movement parsing and execution rely on private window helpers and state, making layout or movement refactors fragile and hard to test without the full UI stack.
- **Shutdown/resource cleanup is best-effort only**: Window close handling ignores exceptions and calls `QSettings.sync()` on the UI thread without checking for ongoing worker threads, risking hangs or lost settings.
