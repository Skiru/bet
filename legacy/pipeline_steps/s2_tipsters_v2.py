#!/usr/bin/env python3
"""S2 tipster scraper v2 entrypoint (safe/offline-first).

Production integration should wire real HTTP fetchers behind compliance gates.
This script intentionally supports deterministic HTML fixture runs because all
parser behavior must be validated before any live dry-run is allowed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bet.tipsters.extractors import dispatch_extract, make_raw
from bet.tipsters.storage import persist_sqlite, write_json_artifact, build_payload
from bet.tipsters.handoff import write_handoff_artifact
from bet.tipsters.source_registry import CORE_SOURCE_IDS, RESEARCH_SOURCE_IDS, SOURCES, CERTIFIED_SHADOW_SOURCE_IDS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--fixture-html-dir", type=Path, required=True, help="Directory with <source_id>.html files for deterministic parse run")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--sqlite-db", type=Path, default=None, help="Optional SQLite sink for tipster_picks_v2/tipster_consensus_v2")
    parser.add_argument("--include-research", action="store_true", help="Also parse research fixtures if present; never use for production promotion")
    parser.add_argument("--include-certified-shadow-fixtures", action="store_true", help="Include certified shadow sources (like zawodtyper) from fixtures")
    parser.add_argument("--handoff-out", type=Path, default=None, help="Optional output path for tipster evidence handoff JSON")
    args = parser.parse_args()

    results = []
    source_ids = CORE_SOURCE_IDS + (RESEARCH_SOURCE_IDS if args.include_research else ())
    if args.include_certified_shadow_fixtures:
        source_ids = source_ids + CERTIFIED_SHADOW_SOURCE_IDS
    for source_id in source_ids:
        html_path = args.fixture_html_dir / f"{source_id}.html"
        if not html_path.exists():
            continue
        policy = SOURCES[source_id]
        doc = make_raw(source_id, policy.entrypoints[0], html_path.read_text(encoding="utf-8"))
        results.append(dispatch_extract(doc, source_id))
    out = args.out or Path("betting/data") / f"{args.date}_tipster_consensus_v2.json"
    write_json_artifact(results, out)

    if args.handoff_out:
        payload = build_payload(results)
        write_handoff_artifact(payload, args.handoff_out)
        print(f"[s2-tipsters-v2] wrote handoff to={args.handoff_out}")

    sqlite_counts = None
    if args.sqlite_db:
        sqlite_counts = persist_sqlite(results, args.sqlite_db)
    print(f"[s2-tipsters-v2] wrote {out} from {len(results)} source fixtures")
    if sqlite_counts:
        print(f"[s2-tipsters-v2] sqlite persisted picks={sqlite_counts['picks']} consensus={sqlite_counts['consensus']}")
    return 0 if any(r.picks for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
