#!/usr/bin/env python3
"""
Phase 3 Fixture — Success Case
Returns deterministic structured JSON output for testing.

Usage:
    python scripts/fixtures/bet-script-success.py --match-id <id>

Exit codes:
    0 — Success
    2 — Invalid arguments
"""

import argparse
import json
import sys
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description="Success fixture")
    parser.add_argument("--match-id", required=True, help="Match identifier")
    args = parser.parse_args()

    # Validate match_id format
    import re
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", args.match_id):
        print(json.dumps({"error": "Invalid match_id format"}), file=sys.stderr)
        sys.exit(2)

    # Deterministic output
    result = {
        "status": "success",
        "match_id": args.match_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "home_team": "Team Alpha",
            "away_team": "Team Beta",
            "competition": "Test League",
            "kickoff": "2026-06-15T18:00:00Z",
            "markets": [
                {"name": "Match Winner", "options": ["Home", "Draw", "Away"]},
                {"name": "Over/Under 2.5", "options": ["Over", "Under"]}
            ]
        },
        "metadata": {
            "fixture_version": "1.0.0",
            "source": "deterministic_fixture"
        }
    }

    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
