#!/usr/bin/env python3
"""CLI for validating live session candidate universe quality."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bet.pipeline.live_session_universe import (
    LiveSessionUniverseConfig,
    build_pre_s7_universe,
    write_universe_report,
)

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate live session universe quality before S7.")
    p.add_argument("--input", required=True, type=Path, help="Path to input candidates list (S4 valuation candidates json)")
    p.add_argument("--output", required=True, type=Path, help="Path to save output universe report json")
    p.add_argument("--min-candidates", type=int, default=8, help="Minimum valid pre-S7 candidates required")
    p.add_argument("--provider-universe-exhausted", action="store_true", default=False, help="Flag if upstream provider universe was exhausted")
    return p.parse_args()

def main() -> int:
    args = parse_args()
    
    if not args.input.exists():
        print(f"ERROR: input file {args.input} does not exist", file=sys.stderr)
        return 1
        
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"ERROR: failed to parse input JSON {args.input}: {e}", file=sys.stderr)
        return 2

    # Extract raw candidates list
    # S4 structure usually has key "candidates"
    raw_candidates = []
    if isinstance(payload, list):
        raw_candidates = payload
    elif isinstance(payload, dict):
        if "candidates" in payload:
            raw_candidates = payload["candidates"]
        elif "payload" in payload and isinstance(payload["payload"], dict) and "candidates" in payload["payload"]:
            raw_candidates = payload["payload"]["candidates"]
        elif "payload" in payload and isinstance(payload["payload"], list):
            raw_candidates = payload["payload"]
        else:
            raw_candidates = [payload]

    config = LiveSessionUniverseConfig(
        min_candidates=args.min_candidates,
        provider_universe_exhausted=args.provider_universe_exhausted,
    )

    report = build_pre_s7_universe(raw_candidates, config)
    write_universe_report(report, args.output)

    print(f"LIVE_SESSION_UNIVERSE_STATUS={report.status}")
    print(f"VALID_PRE_S7_COUNT={report.valid_count}")
    print(f"REJECTED_COUNT={report.rejected_count}")
    print(f"SOURCE_GAP_COUNT={report.source_gap_count}")

    if report.status == "READY_FOR_S7":
        return 0
    elif report.status == "BLOCKED_PROVIDER_UNIVERSE_EXHAUSTED":
        print(f"BLOCKED: {report.status}")
        return 3
    else:
        print(f"BLOCKED: {report.status}")
        return 4

if __name__ == "__main__":
    sys.exit(main())
