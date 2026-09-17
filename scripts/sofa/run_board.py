#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime

from bet.sofa.board import fetch_board
from bet.sofa.config import SofaConfig

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Superbet board fixtures")
    parser.add_argument("--date", type=str, required=True, help="Date in YYYY-MM-DD")
    args = parser.parse_args()
    
    config = SofaConfig.from_env()
    
    start_time = time.monotonic()
    
    try:
        fixtures = fetch_board(args.date)
    except Exception as e:
        print(f"SOFA_SUMMARY: {json.dumps({'stage': 'BOARD', 'verdict': 'FAILED', 'error': str(e)})}", flush=True)
        sys.exit(2)
        
    os.makedirs(config.runs_dir, exist_ok=True)
    out_dir = os.path.join(config.runs_dir, args.date)
    os.makedirs(out_dir, exist_ok=True)
    
    out_path = os.path.join(out_dir, "01_board.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([fix.model_dump(mode="json") for fix in fixtures], f, indent=2, ensure_ascii=False)
        
    elapsed = time.monotonic() - start_time
    
    counts = Counter(fix.sport for fix in fixtures)
    
    summary = {
        "stage": "BOARD",
        "verdict": "OK",
        "metrics": {
            "total_fixtures": len(fixtures),
            "football_fixtures": counts.get("football", 0),
            "tennis_fixtures": counts.get("tennis", 0),
            "elapsed_s": round(elapsed, 2),
        },
        "output_path": out_path
    }
    
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")
    sys.exit(0)

if __name__ == "__main__":
    main()
