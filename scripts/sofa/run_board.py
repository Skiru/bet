#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from collections import Counter

from bet.sofa.board import fetch_board
from bet.sofa.config import SofaConfig
from bet.sofa.timeutil import now


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Superbet board fixtures")
    parser.add_argument(
        "--date",
        type=str,
        default=now().strftime("%Y-%m-%d"),
        help="Date in YYYY-MM-DD (default: today, UTC)",
    )
    args = parser.parse_args()

    config = SofaConfig.from_env()

    start_time = time.monotonic()

    try:
        fixtures = fetch_board(args.date)
    except Exception as e:
        print(
            "SOFA_SUMMARY: "
            + json.dumps({"stage": "BOARD", "verdict": "FAILED", "error": str(e)}),
            flush=True,
        )
        return 2

    os.makedirs(config.runs_dir, exist_ok=True)
    out_dir = os.path.join(config.runs_dir, args.date)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, "01_board.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            [fix.model_dump(mode="json") for fix in fixtures],
            f,
            indent=2,
            ensure_ascii=False,
        )

    elapsed = time.monotonic() - start_time

    counts = Counter(fix.sport for fix in fixtures)

    # An empty board is not "a quiet day" until somebody has checked: a wrong
    # sport filter looks exactly the same, and E3 is the stage where a lost
    # fixture becomes a fixture we never price (L26).
    verdict = "PARTIAL" if not fixtures else "OK"

    summary = {
        "stage": "BOARD",
        "verdict": verdict,
        "metrics": {
            "total_fixtures": len(fixtures),
            "football_fixtures": counts.get("football", 0),
            "tennis_fixtures": counts.get("tennis", 0),
            "elapsed_s": round(elapsed, 2),
        },
        "output_path": out_path,
    }

    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
