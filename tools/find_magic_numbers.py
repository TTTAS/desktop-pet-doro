#!/usr/bin/env python3
"""Find magic numbers in Python code (excluding already defined constants)."""
import re
import sys
from pathlib import Path
from collections import defaultdict

# Known constants that should be ignored
KNOWN_CONSTANTS = {
    16, 6000, 10.0, 380, 230, 320, 240, 200, -110.0, 20.0, 360.0, 110.0, 60,
    120.0, -110.0, 1.0, 170.0, 0.55, 0.92, 0.4, 12.0, 24.0, 20.0, 48.0, 6,
    # Common innocent numbers
    0, 1, 2, 3, 4, 5, 10, 100, -1,
}

# Patterns to ignore
IGNORE_PATTERNS = [
    r'line_number.*=.*\d+',  # Line numbers
    r'range\(\d+\)',  # range() calls
    r':\d+\]',  # Array slicing
    r'\[\d+\]',  # Array indexing
    r'version.*=.*["\'][\d.]+["\']',  # Version strings
    r'py3\d+',  # Python version tags
]

def should_ignore_line(line: str) -> bool:
    """Check if line should be ignored."""
    if any(re.search(pattern, line) for pattern in IGNORE_PATTERNS):
        return True
    # Ignore lines with only common numbers
    return False

def extract_numbers(line: str) -> list[tuple[str, str]]:
    """Extract numbers from a line with context."""
    # Match integers and floats (not in strings)
    pattern = r'(?<!["\'])(?<!\w)(-?\d+\.?\d*)(?!["\'])'
    matches = []

    for match in re.finditer(pattern, line):
        num_str = match.group(1)
        try:
            num = float(num_str) if '.' in num_str else int(num_str)
            if num not in KNOWN_CONSTANTS:
                # Get context (20 chars before and after)
                start = max(0, match.start() - 20)
                end = min(len(line), match.end() + 20)
                context = line[start:end].strip()
                matches.append((num_str, context))
        except ValueError:
            pass

    return matches

def scan_file(file_path: Path) -> dict:
    """Scan a file for magic numbers."""
    results = defaultdict(list)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments, docstrings, and imports
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if 'import ' in stripped or 'from ' in stripped:
                    continue
                if should_ignore_line(line):
                    continue

                numbers = extract_numbers(line)
                for num, context in numbers:
                    results[num].append((line_num, context))

    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)

    return results

def main():
    """Scan doro_app for magic numbers."""
    files_to_scan = [
        # Core files most likely to have magic numbers
        "doro_app/core/chat/controller.py",
        "doro_app/core/chat/validator.py",
        "doro_app/core/movement/manager.py",
        "doro_app/core/movement/parser.py",
        "doro_app/ui/window.py",
        "doro_app/ui/components/bubble_controller.py",
        "doro_app/ui/rendering/rendering_engine.py",
        "doro_app/ui/layout/layout_manager.py",
    ]

    all_numbers = defaultdict(list)

    for file_str in files_to_scan:
        file_path = Path(file_str)
        if not file_path.exists():
            continue

        results = scan_file(file_path)
        if results:
            for num, occurrences in results.items():
                all_numbers[num].append((str(file_path), occurrences))

    # Sort by frequency
    sorted_numbers = sorted(
        all_numbers.items(),
        key=lambda x: sum(len(occs) for _, occs in x[1]),
        reverse=True
    )

    print("=" * 80)
    print("MAGIC NUMBERS FOUND (sorted by frequency)")
    print("=" * 80)
    print()

    for num, file_occurrences in sorted_numbers[:30]:  # Top 30
        total_count = sum(len(occs) for _, occs in file_occurrences)
        print(f"\n{num} (appears {total_count} times)")
        print("-" * 60)

        for file_path, occurrences in file_occurrences:
            print(f"  {file_path}")
            for line_num, context in occurrences[:3]:  # First 3 per file
                print(f"    L{line_num}: {context[:70]}")
            if len(occurrences) > 3:
                print(f"    ... and {len(occurrences) - 3} more")

if __name__ == "__main__":
    main()
