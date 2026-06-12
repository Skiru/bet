#!/usr/bin/env python3
"""
Phase 3 Fixture — Slow Case
Sleeps beyond the configured timeout for testing timeout handling.

Usage:
    python scripts/fixtures/bet-script-slow.py [--sleep-seconds N]

Exit codes:
    0 — Completed (should not happen if timeout works)
    2 — Invalid arguments
"""

import argparse
import json
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="Slow fixture")
    parser.add_argument("--sleep-seconds", type=int, default=10,
                        help="Seconds to sleep (default: 10)")
    args = parser.parse_args()

    # Validate sleep seconds
    if not 1 <= args.sleep_seconds <= 60:
        print(json.dumps({"error": "sleep_seconds must be 1-60"}), file=sys.stderr)
        sys.exit(2)

    # Print a start message
    start_msg = {
        "status": "started",
        "sleep_seconds": args.sleep_seconds,
        "message": f"Sleeping for {args.sleep_seconds} seconds..."
    }
    print(json.dumps(start_msg), flush=True)

    # Sleep
    time.sleep(args.sleep_seconds)

    # This should not be reached if timeout works
    end_msg = {
        "status": "completed",
        "message": "Sleep completed (timeout did not fire)"
    }
    print(json.dumps(end_msg))
    sys.exit(0)


if __name__ == "__main__":
    main()
