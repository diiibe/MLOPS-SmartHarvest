#!/usr/bin/env python3
"""
Script to fix test file patches - remove non-existent main.py function patches.
Since main.py doesn't have wrapper functions, we don't need to patch anything.
The tests should just call main.run_pipeline() directly.
"""

import re
import sys


def fix_test_file(filepath):
    """Remove non-existent @patch decorators from test files."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove the @patch decorators that don't exist
    patterns_to_remove = [
        r'    @patch\("main\.get_st1"\)\n',
        r'    @patch\("main\.get_st2"\)\n',
        r'    @patch\("main\.get_landsat"\)\n',
        r'    @patch\("main\.get_srtm"\)\n',
        r'    @patch\("main\.get_missing_partitions"\)\n',
    ]

    for pattern in patterns_to_remove:
        content = re.sub(pattern, "", content)

    # Remove mock_missing parameter and its setup
    content = re.sub(r", mock_missing", "", content)
    content = re.sub(r"mock_missing, ", "", content)
    content = re.sub(r"        start_date = datetime\(2025, 6, 1\)\n", "", content)
    content = re.sub(r"        mock_missing\.return_value = \[start_date\]\n", "", content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Fixed: {filepath}")


if __name__ == "__main__":
    files = [
        "tests/test_gate_b.py",
        "tests/test_gate_c.py",
        "tests/test_gate_d.py",
        "tests/test_e2e_pipeline.py",
    ]

    for filepath in files:
        try:
            fix_test_file(filepath)
        except Exception as e:
            print(f"Error fixing {filepath}: {e}")
            sys.exit(1)

    print("\nAll test files fixed successfully!")
