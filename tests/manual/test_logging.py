#!/usr/bin/env python3
"""Quick test script to verify logging system works."""

from pathlib import Path

from doro_app.utils.logger import setup_logger

# Test 1: Basic logger setup
print("Test 1: Creating logger...")
logger = setup_logger("test_logger", level=10)  # DEBUG level
logger.debug("This is a debug message")
logger.info("This is an info message")
logger.warning("This is a warning message")
logger.error("This is an error message")

# Test 2: Check log file was created
log_file = Path.home() / ".doro" / "doro.log"
if log_file.exists():
    print(f"✅ Log file created: {log_file}")
    print(f"   Size: {log_file.stat().st_size} bytes")
    print("\nLast 10 lines:")
    print("-" * 60)
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines[-10:]:
            print(line.rstrip())
else:
    print(f"❌ Log file not found: {log_file}")

# Test 3: Module-level logger
print("\n" + "=" * 60)
print("Test 3: Testing module-level logger...")
from doro_app.core.state.service import logger as state_logger

state_logger.info("Test message from state_service logger")

from doro_app.core.state.repository import logger as repo_logger

repo_logger.warning("Test message from state_repository logger")

print("\n✅ All logging tests completed!")
print(f"Check the log file at: {log_file}")
