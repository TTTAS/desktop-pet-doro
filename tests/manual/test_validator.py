#!/usr/bin/env python3
"""Test the response validator without requiring PySide6."""

import importlib.util
import sys
from pathlib import Path

# Load validator module directly from file without triggering parent __init__.py
# Import dependencies first (these don't require PySide6)
actions_module = importlib.import_module("doro_app.utils.actions")

# Create minimal parent package modules to support relative imports
# Only create dummy packages if they don't exist already (avoid interfering with real imports)
_needs_dummy_packages = "doro_app.core.chat" not in sys.modules

if _needs_dummy_packages:
    # Check if real packages can be imported (without triggering PySide6)
    try:
        # Try importing just the doro_app package itself
        if "doro_app" not in sys.modules:
            doro_app_pkg = importlib.import_module("doro_app")
    except ImportError:
        # Create dummy if import fails
        doro_app_pkg = type(sys)("doro_app")
        doro_app_pkg.__path__ = []
        sys.modules["doro_app"] = doro_app_pkg

    # For nested packages, create minimal stubs
    if "doro_app.core" not in sys.modules:
        core_pkg = type(sys)("doro_app.core")
        core_pkg.__path__ = []
        sys.modules["doro_app.core"] = core_pkg

    if "doro_app.core.chat" not in sys.modules:
        chat_pkg = type(sys)("doro_app.core.chat")
        chat_pkg.__path__ = []
        sys.modules["doro_app.core.chat"] = chat_pkg

# Now load validator directly
project_root = Path(__file__).parent.parent.parent
validator_path = project_root / "doro_app" / "core" / "chat" / "validator.py"
spec = importlib.util.spec_from_file_location(
    "doro_app.core.chat.validator", validator_path
)
validator = importlib.util.module_from_spec(spec)
validator.__package__ = "doro_app.core.chat"
sys.modules["doro_app.core.chat.validator"] = validator
spec.loader.exec_module(validator)

ResponseValidator = validator.ResponseValidator
ValidationResult = validator.ValidationResult


class MockStateService:
    """Mock StateService for testing."""

    def __init__(self, valid_states: list[str]):
        self._states = valid_states

    def has_state(self, key: str) -> bool:
        return key in self._states

    def find_state_by_label(self, label: str) -> str | None:
        label_lower = label.lower()
        for state in self._states:
            if state.lower() == label_lower:
                return state
        return None

    def visible_state_keys(self) -> list[str]:
        return self._states


def test_valid_response():
    """Test a valid response with state and dialogue."""
    mock_service = MockStateService(["HAPPY", "SAD", "EXCITED", "idle", "walking"])
    validator = ResponseValidator(mock_service)

    # Valid response
    response = "(HAPPY) 你好呀～doro很開心見到你！"
    result = validator.validate(response)

    print(f"Test 1 - Valid response with state and dialogue")
    print(f"  Input: {response}")
    print(f"  Result: valid={result.valid}, has_state={result.has_state}, has_dialogue={result.has_dialogue}")
    print(f"  ✅ PASS" if result.valid and result.has_state and result.has_dialogue else f"  ❌ FAIL")
    print()


def test_valid_response_with_movement():
    """Test a valid response with state, dialogue, and movement."""
    mock_service = MockStateService(["HAPPY", "SAD", "EXCITED", "idle", "walking"])
    validator = ResponseValidator(mock_service)

    response = "(HAPPY) 來追我呀～ [MOVE:dir=right;distance=80]"
    result = validator.validate(response)

    print(f"Test 2 - Valid response with state, dialogue, and movement")
    print(f"  Input: {response}")
    print(f"  Result: valid={result.valid}, has_state={result.has_state}, has_movement={result.has_movement}, has_dialogue={result.has_dialogue}")
    print(f"  ✅ PASS" if result.valid and result.has_state and result.has_movement and result.has_dialogue else f"  ❌ FAIL")
    print()


def test_invalid_state():
    """Test a response with invalid state."""
    mock_service = MockStateService(["HAPPY", "SAD", "EXCITED", "idle", "walking"])
    validator = ResponseValidator(mock_service)

    response = "(CONFUSED) 我不知道該說什麼..."
    result = validator.validate(response)

    print(f"Test 3 - Invalid state")
    print(f"  Input: {response}")
    print(f"  Result: valid={result.valid}, error={result.error_message}")
    print(f"  ✅ PASS" if not result.valid and "Invalid state" in (result.error_message or "") else f"  ❌ FAIL")
    print()


def test_invalid_direction():
    """Test a response with invalid movement direction."""
    mock_service = MockStateService(["HAPPY", "SAD", "EXCITED", "idle", "walking"])
    validator = ResponseValidator(mock_service)

    response = "(HAPPY) 要去哪裡呢？ [MOVE:dir=diagonal;distance=50]"
    result = validator.validate(response)

    print(f"Test 4 - Invalid movement direction")
    print(f"  Input: {response}")
    print(f"  Result: valid={result.valid}, error={result.error_message}")
    print(f"  ✅ PASS" if not result.valid and "Invalid movement direction" in (result.error_message or "") else f"  ❌ FAIL")
    print()


def test_only_dialogue():
    """Test a response with only dialogue (no state or movement)."""
    mock_service = MockStateService(["HAPPY", "SAD", "EXCITED", "idle", "walking"])
    validator = ResponseValidator(mock_service)

    response = "今天天氣真好呀～"
    result = validator.validate(response)

    print(f"Test 5 - Only dialogue (no state or movement)")
    print(f"  Input: {response}")
    print(f"  Result: valid={result.valid}, has_state={result.has_state}, has_movement={result.has_movement}, has_dialogue={result.has_dialogue}")
    print(f"  ✅ PASS" if result.valid and not result.has_state and not result.has_movement and result.has_dialogue else f"  ❌ FAIL")
    print()


def test_empty_response():
    """Test an empty response."""
    mock_service = MockStateService(["HAPPY", "SAD", "EXCITED", "idle", "walking"])
    validator = ResponseValidator(mock_service)

    response = ""
    result = validator.validate(response)

    print(f"Test 6 - Empty response")
    print(f"  Input: (empty)")
    print(f"  Result: valid={result.valid}, error={result.error_message}")
    print(f"  ✅ PASS" if not result.valid and "empty" in (result.error_message or "").lower() else f"  ❌ FAIL")
    print()


def test_retry_prompt_building():
    """Test retry prompt building."""
    mock_service = MockStateService(["HAPPY", "SAD", "EXCITED", "idle", "walking"])
    validator = ResponseValidator(mock_service)

    # Invalid response
    response = "(CONFUSED) 我不知道..."
    result = validator.validate(response)

    # Should retry
    should_retry = validator.should_retry(result)

    # Build retry prompt
    retry_prompt = validator.build_retry_prompt(result, "跟我打招呼")

    print(f"Test 7 - Retry prompt building")
    print(f"  Original message: 跟我打招呼")
    print(f"  Invalid response: {response}")
    print(f"  Should retry: {should_retry}")
    print(f"  Retry prompt includes error: {result.error_message in retry_prompt}")
    print(f"  Retry prompt includes original: {'跟我打招呼' in retry_prompt}")
    print(f"  ✅ PASS" if should_retry and result.error_message in retry_prompt and "跟我打招呼" in retry_prompt else f"  ❌ FAIL")
    print()


def test_chinese_directions():
    """Test Chinese direction tokens."""
    mock_service = MockStateService(["HAPPY", "SAD", "EXCITED", "idle", "walking"])
    validator = ResponseValidator(mock_service)

    response = "(HAPPY) 向左邊走走吧～ [MOVE:dir=左;distance=60]"
    result = validator.validate(response)

    print(f"Test 8 - Chinese direction (左)")
    print(f"  Input: {response}")
    print(f"  Result: valid={result.valid}, has_movement={result.has_movement}")
    print(f"  ✅ PASS" if result.valid and result.has_movement else f"  ❌ FAIL")
    print()


def main():
    print("=" * 60)
    print("Response Validator Test Suite")
    print("=" * 60)
    print()

    test_valid_response()
    test_valid_response_with_movement()
    test_invalid_state()
    test_invalid_direction()
    test_only_dialogue()
    test_empty_response()
    test_retry_prompt_building()
    test_chinese_directions()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
