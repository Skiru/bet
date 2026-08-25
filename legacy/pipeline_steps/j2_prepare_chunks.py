#!/usr/bin/env python3
"""
J2 Prepare Chunks Script
Splits the 60-event pool into manageable chunks of max 20 events.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare J2 chunk files.")
    parser.add_argument(
        "--run-id",
        required=True,
        help="Session run ID (e.g. TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101)",
    )
    args = parser.parse_args()

    run_id = args.run_id
    run_dir = ROOT / "reports" / "pipeline_runs" / run_id
    pool_path = run_dir / "j2_candidate_pool.json"

    if not pool_path.exists():
        print(f"Error: Candidate pool not found at {pool_path}", file=sys.stderr)
        return 1

    with open(pool_path, "r", encoding="utf-8") as f:
        pool_data = json.load(f)

    events = pool_data.get("events", [])
    football_events = [e for e in events if e.get("sport") == "football"]
    tennis_events = [e for e in events if e.get("sport") == "tennis"]

    # Guarantee max 20 events per chunk
    football_chunks = [football_events[i : i + 20] for i in range(0, len(football_events), 20)]
    tennis_chunks = [tennis_events[i : i + 20] for i in range(0, len(tennis_events), 20)]

    chunk_manifest: dict[str, any] = {
        "run_id": run_id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_events": len(events),
        "chunks": {},
    }

    # Prepare football chunks (expecting exactly 1 chunk of 20 events)
    for idx, chunk in enumerate(football_chunks, 1):
        chunk_name = f"j2_chunk_football.json" if len(football_chunks) == 1 else f"j2_chunk_football_{idx}.json"
        chunk_path = run_dir / chunk_name
        chunk_data = {
            "run_id": run_id,
            "chunk_id": f"football_{idx}",
            "sport": "football",
            "event_count": len(chunk),
            "events": chunk,
        }
        with open(chunk_path, "w", encoding="utf-8") as f:
            json.dump(chunk_data, f, indent=2)
        chunk_manifest["chunks"][chunk_name] = {
            "sport": "football",
            "event_count": len(chunk),
            "event_ids": [e.get("event_id") for e in chunk],
        }

    # Prepare tennis chunks (expecting exactly 2 chunks of 20 events)
    for idx, chunk in enumerate(tennis_chunks, 1):
        chunk_name = f"j2_chunk_tennis_{idx}.json"
        chunk_path = run_dir / chunk_name
        chunk_data = {
            "run_id": run_id,
            "chunk_id": f"tennis_{idx}",
            "sport": "tennis",
            "event_count": len(chunk),
            "events": chunk,
        }
        with open(chunk_path, "w", encoding="utf-8") as f:
            json.dump(chunk_data, f, indent=2)
        chunk_manifest["chunks"][chunk_name] = {
            "sport": "tennis",
            "event_count": len(chunk),
            "event_ids": [e.get("event_id") for e in chunk],
        }

    # Write chunk manifest JSON
    manifest_path = run_dir / "j2_chunk_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(chunk_manifest, f, indent=2)

    # Write summary MD
    summary_md_path = run_dir / "j2_chunk_manifest.md"
    summary_md = f"""# J2 Chunk Manifest

This artifact summarizes the prepared chunks for Phase J2 chunked execution.

- **Run ID:** {run_id}
- **Generated At:** {chunk_manifest["generated_at"]}
- **Total Events:** {chunk_manifest["total_events"]}

## Chunk Breakdown

"""
    for chunk_name, details in chunk_manifest["chunks"].items():
        summary_md += f"### {chunk_name}\n"
        summary_md += f"- **Sport:** {details['sport']}\n"
        summary_md += f"- **Event Count:** {details['event_count']}\n"
        summary_md += f"- **Event IDs:** {', '.join(details['event_ids'])}\n\n"

    with open(summary_md_path, "w", encoding="utf-8") as f:
        f.write(summary_md)

    print(f"Successfully chunked {len(events)} events for J2 execution.")
    print(f"Manifest written to: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
