# Manual Test Scripts

This directory contains manual test scripts for external integrations and exploratory testing.

## Scripts

### test_lmstudio_response.py
Tests LM Studio API response format.
```bash
python tests/manual/test_lmstudio_response.py
```

### test_lmstudio_structured_output.py
Tests LM Studio structured output capabilities.
```bash
python tests/manual/test_lmstudio_structured_output.py
```

### test_validator.py
Tests response validator without requiring PySide6.
```bash
python tests/manual/test_validator.py
```

### test_logging.py
Tests logging system functionality.
```bash
python tests/manual/test_logging.py
```

## Note

These are manual test scripts, not automated pytest tests.
They are used for:
- Testing external API integrations
- Exploratory testing
- Manual verification of functionality

For automated tests, see the parent `tests/` directory.
