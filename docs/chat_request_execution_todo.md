# Chat Request Execution Model - TODO

This list captures follow-up tasks to decouple chat request execution from the UI thread and make the flow testable and cancellable.

- **Adopt a reusable worker pool**: Replace per-request `QThread` creation in `ChatController` with a shared pool or Qt Concurrent, allowing bounded concurrency and reuse to avoid thread leaks.
- **Introduce explicit request lifecycle objects**: Model a chat request with states (pending, running, cancelled, failed, succeeded) and identifiers so callers can cancel or await specific requests instead of relying on implicit thread lifetimes.
- **Add cancellation and timeout controls**: Support user-initiated cancel, automatic timeout, and cleanup callbacks that ensure workers stop emitting signals after cancellation.
- **Move persistence off the UI thread**: Buffer history or setting writes and flush asynchronously or on a timer instead of calling `QSettings.sync()` synchronously from the UI thread after every request.
- **Parameterize history limits and retry policy**: Make history truncation length, retry counts/backoff configurable (from settings or injected strategy) instead of hard-coded values inside `ChatController`.
- **Separate orchestration from presentation**: Emit signals or events for UI feedback (dialogs, bubbles, timers) rather than invoking UI methods directly inside orchestration or failure handling paths.
- **Establish structured error propagation**: Normalize errors into typed results (e.g., network, validation, cancellation) and surface them through signals; avoid random file reads on failure paths within the orchestration layer.
- **Harden shutdown and cleanup**: Ensure outstanding requests are cancelled and worker pool shuts down cleanly when the window closes to prevent "QThread destroyed while thread is still running" issues.
- **Cover with targeted tests**: Add unit tests around the lifecycle model and cancellation behavior using fakes/mocks, plus integration tests with `pytest-qt` to verify UI signals and teardown are handled without stray threads.
