#!/usr/bin/env python3
"""Run a sport-specific scanner directly.

Replaces inline `python3 -c "from scripts.scanners.X_scanner import ..."` blocks
that GARBLE in fish shell due to quote nesting.

Usage:
    python3 scripts/run_scanner.py --sport football
    python3 scripts/run_scanner.py --sport hockey --timeout 60
    python3 scripts/run_scanner.py --sport tennis --max-deep-links 10

Exit codes:
    0 = Scan completed with validation PASS
    1 = Scan completed with validation issues (MARGINAL)
    2 = Scan failed critically
"""

import argparse
import importlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SCANNER_MAP = {
    "football": "scripts.scanners.football_scanner.FootballScanner",
    "basketball": "scripts.scanners.basketball_scanner.BasketballScanner",
    "hockey": "scripts.scanners.hockey_scanner.HockeyScanner",
    "tennis": "scripts.scanners.tennis_scanner.TennisScanner",
    "volleyball": "scripts.scanners.volleyball_scanner.VolleyballScanner",
}


def main():
    parser = argparse.ArgumentParser(description="Run a sport-specific scanner")
    parser.add_argument("--sport", required=True, choices=list(SCANNER_MAP.keys()), help="Sport to scan")
    parser.add_argument("--date", default=str(date.today()), help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--timeout", type=int, default=45, help="Timeout per page in seconds")
    parser.add_argument("--max-deep-links", type=int, default=None, help="Override max_deep_links")
    args = parser.parse_args()

    scanner_path = SCANNER_MAP[args.sport]
    module_path, class_name = scanner_path.rsplit(".", 1)

    try:
        module = importlib.import_module(module_path)
        scanner_cls = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        print(f"ERROR: Cannot load scanner {scanner_path}: {e}")
        sys.exit(2)

    try:
        from scripts.scanners.domain_semaphore import DomainSemaphoreMap
    except ImportError:
        print("ERROR: Cannot import DomainSemaphoreMap")
        sys.exit(2)

    scanner = scanner_cls()
    scanner.timeout_per_page = args.timeout
    if args.max_deep_links is not None:
        scanner.max_deep_links = args.max_deep_links

    print(f"Running {args.sport} scanner for {args.date} (timeout={args.timeout}s)")
    stats = scanner.scan(args.date, DomainSemaphoreMap())

    print(f"\n{args.sport.title()}: {stats.events_found} events | {stats.sources_ok} OK | {stats.sources_failed} failed")
    if hasattr(stats, "deep_links_found"):
        print(f"Deep links: {stats.deep_links_found}")
    print(f'Validation: {"PASS" if stats.validation_passed else "FAIL"}')
    if not stats.validation_passed:
        print(f"  Gaps: {stats.gaps_description}")

    # AGENT_SUMMARY
    summary = {
        "verdict": "OK" if stats.validation_passed else "FAILED",
        "sport": args.sport,
        "events_found": stats.events_found,
        "sources_ok": stats.sources_ok,
        "sources_failed": stats.sources_failed,
    }
    print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")

    sys.exit(0 if stats.validation_passed else 2)


if __name__ == "__main__":
    main()
