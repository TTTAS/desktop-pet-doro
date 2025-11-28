#!/usr/bin/env python3
"""Find Chinese characters in Python files (excluding decorative lines)."""
import re
import sys
from pathlib import Path

def find_chinese(file_path):
    """Find lines with Chinese characters."""
    results = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                # Skip decorative lines
                if '═' in line or '─' in line:
                    continue
                # Find Chinese characters
                if re.search(r'[\u4e00-\u9fff]', line):
                    results.append((i, line.rstrip()))
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
    return results

def main():
    files = [
        "doro_app/core/state/service.py",
        "doro_app/core/state/repository.py",
        "doro_app/core/movement/manager.py",
        "doro_app/core/movement/parser.py",
        "doro_app/utils/actions.py",
        "doro_app/core/chat/validator.py",
        "doro_app/core/chat/controller.py",
    ]

    for file in files:
        path = Path(file)
        if not path.exists():
            continue
        results = find_chinese(path)
        if results:
            print(f"\n{'='*60}")
            print(f"{file}")
            print('='*60)
            for line_num, line in results[:15]:  # Limit to 15 lines per file
                print(f"{line_num:4d}: {line}")

if __name__ == "__main__":
    main()
