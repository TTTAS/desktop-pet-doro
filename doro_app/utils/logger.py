"""Centralized logging configuration for Doro application."""

import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "doro",
    log_file: Path | None = None,
    level: int = logging.DEBUG,
    console: bool = True,
) -> logging.Logger:
    """
    Set up application logger with file and console handlers.

    Args:
        name: Logger name (typically __name__ from calling module)
        log_file: Path to log file. If None, uses ~/.doro/doro.log
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console: Whether to also output to console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if logger already configured
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    if log_file is None:
        log_dir = Path.home() / ".doro"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "doro.log"

    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        # If file logging fails, at least log to console
        print(f"Warning: Could not create log file {log_file}: {e}", file=sys.stderr)

    # Console handler (optional)
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)  # Only warnings+ to console
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# Module-level convenience function
_default_logger: logging.Logger | None = None


def get_logger(name: str = "doro") -> logging.Logger:
    """
    Get or create logger instance.

    Usage:
        from .logger import get_logger
        logger = get_logger(__name__)
        logger.info("Application started")
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logger()
        _share_handlers_with_package(_default_logger)

    return logging.getLogger(name)


def _share_handlers_with_package(default: logging.Logger) -> None:
    """Send ``doro_app.*`` module loggers to the same log file.

    Modules log under their import path (``get_logger(__name__)`` or
    ``logging.getLogger(__name__)``), which is not a child of ``doro``; without
    this their INFO lines (heartbeat decisions, tab-reaction choices, chat flow)
    were silently dropped. INFO rather than DEBUG keeps per-tick debug noise out.
    """
    package = logging.getLogger("doro_app")
    if package.handlers:
        return
    package.setLevel(logging.INFO)
    for handler in default.handlers:
        package.addHandler(handler)
