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
print(f"schema_version={payload.get('"'"'schema_version'"'"', '')}")
print(f"total_picks={payload.get('"'"'total_picks'"'"', 0)}")
print(f"sources_with_picks={payload.get('"'"'sources_with_picks'"'"', 0)}")
print(f"blocked_sources={len(payload.get('"'"'blocked_sources'"'"', []))}")
print(f"skipped_sources={len(payload.get('"'"'skipped_sources'"'"', []))}")
for entry in payload.get('"'"'blocked_sources'"'"', []):
    print(f"blocked::{entry.get('"'"'source_id'"'"', '"'"'unknown'"'"')}::{entry.get('"'"'reason'"'"', '')}")
for entry in payload.get('"'"'skipped_sources'"'"', []):
    reason = entry.get('"'"'reason'"'"', '')
    print(f"skipped::{entry.get('"'"'source_id'"'"', '"'"'unknown'"'"')}::{reason}")
' "$json_path"

if test -n "$sqlite_db"
    if not test -f "$sqlite_db"
        echo "sqlite artifact not found: $sqlite_db" 1>&2
        exit 2
    end
    sqlite3 "$sqlite_db" 'select "tipster_picks_v2", count(*) from tipster_picks_v2 union all select "tipster_consensus_v2", count(*) from tipster_consensus_v2;'
end
