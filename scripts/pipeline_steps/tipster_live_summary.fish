#!/usr/bin/env fish

set -l json_path ""
set -l sqlite_db ""

for arg in $argv
    switch $arg
        case '--json=*'
            set json_path (string replace -- '--json=' '' $arg)
        case '--sqlite-db=*'
            set sqlite_db (string replace -- '--sqlite-db=' '' $arg)
        case '--json'
            continue
        case '--sqlite-db'
            continue
    end
end

for i in (seq (count $argv))
    switch $argv[$i]
        case '--json'
            if test (math $i + 1) -le (count $argv)
                set json_path $argv[(math $i + 1)]
            end
        case '--sqlite-db'
            if test (math $i + 1) -le (count $argv)
                set sqlite_db $argv[(math $i + 1)]
            end
    end
end

if test -z "$json_path"
    echo "usage: tipster_live_summary.fish --json <artifact.json> [--sqlite-db <artifact.sqlite>]" 1>&2
    exit 2
end

if not test -f "$json_path"
    echo "json artifact not found: $json_path" 1>&2
    exit 2
end

python3 -c '
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(f"json={sys.argv[1]}")
print(f"schema_version={payload.get("schema_version", "")}")
print(f"total_picks={payload.get("total_picks", 0)}")
print(f"sources_with_picks={payload.get("sources_with_picks", 0)}")
print(f"blocked_sources={len(payload.get("blocked_sources", []))}")
print(f"skipped_sources={len(payload.get("skipped_sources", []))}")

for entry in payload.get("blocked_sources", []):
    print(f"blocked::{entry.get("source_id", "unknown")}::{entry.get("reason", "")}")

for entry in payload.get("skipped_sources", []):
    reason = entry.get("reason", "")
    print(f"skipped::{entry.get("source_id", "unknown")}::{reason}")

print("\n--- Sources Coverage ---")
for src in payload.get("sources", []):
    src_id = src.get("source_id", "unknown")
    expected = src.get("expected_visible_count")
    extracted = src.get("extracted_count")
    ratio = src.get("coverage_ratio")
    status = src.get("coverage_status", "N/A")
    print(f"source::{src_id}::expected={expected} extracted={extracted} ratio={ratio} status={status}")
    for w in src.get("warnings", []):
        print(f"source::{src_id}::warning::{w}")

picks = payload.get("all_picks", [])
print("\n--- Top Picks (up to 10) ---")
sorted_picks = sorted(picks, key=lambda x: x.get("extraction_quality", 0.0) or 0.0, reverse=True)
for i, p in enumerate(sorted_picks[:10], start=1):
    sport = p.get("sport", "unknown")
    event = p.get("event", "unknown")
    market = p.get("market", "N/A")
    odds = p.get("odds", p.get("odds_decimal", "N/A"))
    quality = p.get("extraction_quality", 0.0)
    
    # Handle list or dict for pipeline_use safely
    p_use = p.get("pipeline_use", [])
    if isinstance(p_use, dict):
        p_use_str = ",".join(p_use.keys())
    elif isinstance(p_use, list):
        p_use_str = ",".join(str(x) for x in p_use)
    else:
        p_use_str = str(p_use)
        
    print(f"{i}. [{sport}] {event} | Market: {market} | Odds: {odds} | Quality: {quality} | Uses: {p_use_str}")
' "$json_path"

if test -n "$sqlite_db"
    if not test -f "$sqlite_db"
        echo "sqlite artifact not found: $sqlite_db" 1>&2
        exit 2
    end
    sqlite3 "$sqlite_db" 'select "tipster_picks_v2", count(*) from tipster_picks_v2 union all select "tipster_consensus_v2", count(*) from tipster_consensus_v2;'
end
