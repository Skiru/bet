#!/usr/bin/env python3
"""Validator rejecting any imports starting with src.bet or containing src.bet references."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate_no_src_bet_imports() -> list[str]:
    errors = []
    scan_dirs = [ROOT / "src", ROOT / "scripts", ROOT / "tests"]
    src_bet_token = "src" + "." + "bet"
    import_src_bet = "import " + src_bet_token
    from_src_bet = "from " + src_bet_token

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if py_file.name == "validate_no_src_bet_imports.py":
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception as e:
                errors.append(f"Failed to read {py_file}: {e}")
                continue

            for line_idx, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if import_src_bet in stripped or from_src_bet in stripped or (src_bet_token + ".") in stripped:
                    rel_path = py_file.relative_to(ROOT)
                    errors.append(f"Disallowed src.bet import found in {rel_path}:{line_idx}: {line.strip()}")

    return errors


def main() -> None:
    errors = validate_no_src_bet_imports()
    if errors:
        print("FAIL: validate_no_src_bet_imports found violations:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    print("PASS: validate_no_src_bet_imports - no src.bet imports found.")


if __name__ == "__main__":
    main()
