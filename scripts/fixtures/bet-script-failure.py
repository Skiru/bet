#!/usr/bin/env python3
"""
Phase 3 Fixture — Failure Case
Returns a deterministic nonzero exit code and stderr for testing.

Usage:
    python scripts/fixtures/bet-script-failure.py [--error-code N]

Exit codes:
    1-255 — Configured error code (default: 1)
    2 — Invalid arguments
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Failure fixture")
    parser.add_argument("--error-code", type=int, default=1, 
                        help="Exit code to return (1-255)")
    args = parser.parse_args()

    # Validate error code
    if not 1 <= args.error_code <= 255:
        print(json.dumps({"error": "error_code must be 1-255"}), file=sys.stderr)
        sys.exit(2)

    # Deterministic failure output
    error_result = {
        "error": "Simulated failure",
        "error_code": args.error_code,
        "message": "This is a deterministic test failure",
        "details": {
            "reason": "fixture_failure",
            "recoverable": False
        }
    }

    print(json.dumps(error_result), file=sys.stderr)
    sys.exit(args.error_code)


if __name__ == "__main__":
    main()
