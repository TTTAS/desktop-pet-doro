"""Core Doro application package."""

# Lazy import to avoid loading PySide6 when importing other modules
def __getattr__(name: str):
    """Lazy import for CLI main to avoid PySide6 dependency in tests."""
    if name == "main":
        from .cli import main
        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["main"]
