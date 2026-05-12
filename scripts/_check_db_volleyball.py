#!/usr/bin/env python3
"""Quick DB schema check for scan_results."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from bet.db.connection import get_db

with get_db() as db:
    cur = db.cursor()
    cur.execute("PRAGMA table_info(scan_results)")
    rows = cur.fetchall()
    print("scan_results schema:")
    for r in rows:
        print(f"  {dict(r)}")
    
    print("\nSample volleyball rows:")
    cur.execute("SELECT * FROM scan_results WHERE sport='volleyball' ORDER BY scan_timestamp DESC LIMIT 2")
    for r in cur.fetchall():
        d = dict(r)
        # Truncate raw_data for readability
        if "raw_data" in d and d["raw_data"]:
            d["raw_data"] = d["raw_data"][:200] + "..."
        for k, v in d.items():
            print(f"  {k}: {v}")
        print()
