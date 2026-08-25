#!/usr/bin/env python3
"""CLI script for controlled promotion of validated results from shadow DB to canonical DB."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
src_path = str(ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from bet.pipeline.launch_bridge import promote_shadow_results, resolve_canonical_db_path


def main() -> None:
    p = argparse.ArgumentParser(description="Promote shadow DB results into canonical DB.")
    p.add_argument("--run-id", required=True, help="Run ID")
    p.add_argument("--shadow-db-path", required=True, type=Path, help="Path to runtime_analysis_shadow.db")
    p.add_argument("--canonical-db-path", type=Path, help="Optional canonical DB path override")
    p.add_argument("--expected-canonical-sha256", help="Expected SHA256 of canonical DB before promotion")
    args = p.parse_args()

    c_path = args.canonical_db_path or resolve_canonical_db_path()

    print(f"Starting promotion for run_id={args.run_id}...")
    res = promote_shadow_results(
        canonical_db_path=c_path,
        shadow_db_path=args.shadow_db_path,
        run_id=args.run_id,
        expected_canonical_sha=args.expected_canonical_sha256,
    )

    print(f"Promotion finished with status={res['status']}")
    print(f"Promotion ID: {res['promotion_id']}")
    print(f"Canonical SHA before: {res['canonical_db_sha256_before']}")
    print(f"Canonical SHA after:  {res['canonical_db_sha256_after']}")


if __name__ == "__main__":
    main()
