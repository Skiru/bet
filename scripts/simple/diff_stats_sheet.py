#!/usr/bin/env python3
"""Replay ANALYZE on a frozen EVENT_DOSSIER_V1 fixture and diff against a baseline.

Every phase of docs/PLAN_BOGATE_STATYSTYKI.md changes how many rows the stats
sheet produces. Without a fixed input and a fixed expected output there is no
way to tell a phase's intended change apart from an accidental regression in
code the phase was not supposed to touch.

Usage:
    # Check the current code against the recorded baseline (exit 1 on any diff):
    python3 scripts/simple/diff_stats_sheet.py

    # After a phase intentionally changes the sheet, look at what changed:
    python3 scripts/simple/diff_stats_sheet.py --dossier PATH --baseline PATH

    # Record a new baseline once a change has been reviewed and accepted:
    python3 scripts/simple/diff_stats_sheet.py --write-baseline

    # Prove the BET_MARKETS_PROFILE=legacy rollback switch still reproduces
    # exactly the pre-plan market/line grid (docs/PLAN_BOGATE_STATYSTYKI.md
    # 3bis.1). Defaults --baseline to the dedicated legacy fixture when
    # --profile legacy is passed without an explicit --baseline:
    python3 scripts/simple/diff_stats_sheet.py --profile legacy

Rows are matched by (event_id, market, line, direction, team_name,
player_name) -- the same tuple that makes a stats-sheet row unique. A key
present on only one side is ADDED or REMOVED; a key present on both sides
with a different p_low is CHANGED. Nothing else is compared: hit_rate, mean,
median and sample_size all move whenever p_low does, and listing them too
would just repeat the same finding four times.

Exit codes: 0 = no diff (or baseline written), 1 = diff found, 2 = error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.simple_stats.analyze import analyze_dossiers  # noqa: E402
from bet.simple_stats.contracts import EventDossierListV1, StatsSheetV1  # noqa: E402

DEFAULT_DOSSIER = ROOT / "tests" / "fixtures" / "simple_stats" / "dossiers_2026-08-31.json"
DEFAULT_BASELINE = ROOT / "tests" / "fixtures" / "simple_stats" / "stats_sheet_baseline_2026-08-31.json"
DEFAULT_LEGACY_BASELINE = (
    ROOT / "tests" / "fixtures" / "simple_stats" / "stats_sheet_baseline_legacy_2026-08-31.json"
)

RowKey = tuple[str, str, float, str, str | None, str | None]


def _row_key(row) -> RowKey:
    return (row.event_id, row.market, row.line, row.direction, row.team_name, row.player_name)


def _index(sheet: StatsSheetV1) -> dict[RowKey, float]:
    """Key -> p_low. A duplicate key would mean two rows describe the same
    bet, which analyze_dossiers must never produce; fail loudly rather than
    silently keeping one and hiding the other from the diff."""
    index: dict[RowKey, float] = {}
    for row in sheet.rows:
        key = _row_key(row)
        if key in index:
            raise ValueError(f"duplicate stats-sheet row for key {key}")
        index[key] = row.p_low
    return index


def diff_sheets(baseline: StatsSheetV1, current: StatsSheetV1) -> dict[str, list]:
    base_index = _index(baseline)
    curr_index = _index(current)
    added = sorted(curr_index.keys() - base_index.keys())
    removed = sorted(base_index.keys() - curr_index.keys())
    changed = sorted(
        key for key in (base_index.keys() & curr_index.keys())
        if base_index[key] != curr_index[key]
    )
    return {"added": added, "removed": removed, "changed": changed}


def _format_key(key: RowKey) -> str:
    event_id, market, line, direction, team_name, player_name = key
    subject = player_name or team_name or "match"
    return f"{event_id[:12]} {market} {line} {direction} [{subject}]"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dossier", default=str(DEFAULT_DOSSIER), help="Frozen EVENT_DOSSIER_V1[] fixture")
    parser.add_argument("--baseline", default=None, help="Recorded STATS_SHEET_V1 to diff against")
    parser.add_argument(
        "--write-baseline", action="store_true",
        help="Overwrite --baseline with the sheet computed from --dossier by today's code, instead of diffing",
    )
    parser.add_argument(
        "--profile", choices=("v2", "legacy"), default="v2",
        help="BET_MARKETS_PROFILE to analyze under (docs/PLAN_BOGATE_STATYSTYKI.md 3bis.1). "
             "'legacy' also switches the default --baseline to the dedicated legacy fixture.",
    )
    args = parser.parse_args()

    dossier_path = Path(args.dossier)
    if args.baseline is not None:
        baseline_path = Path(args.baseline)
    else:
        baseline_path = DEFAULT_LEGACY_BASELINE if args.profile == "legacy" else DEFAULT_BASELINE

    os.environ["BET_MARKETS_PROFILE"] = args.profile
    dossier_list = EventDossierListV1.model_validate_json(dossier_path.read_text(encoding="utf-8"))
    current = analyze_dossiers(dossier_list)

    if args.write_baseline:
        baseline_path.write_text(json.dumps(current.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {len(current.rows)} rows to {baseline_path}")
        return 0

    if not baseline_path.exists():
        print(f"no baseline at {baseline_path} -- run with --write-baseline first", file=sys.stderr)
        return 2

    baseline = StatsSheetV1.model_validate_json(baseline_path.read_text(encoding="utf-8"))
    diff = diff_sheets(baseline, current)

    if not diff["added"] and not diff["removed"] and not diff["changed"]:
        print(f"no diff: {len(current.rows)} rows match {baseline_path.name}")
        return 0

    if diff["added"]:
        print(f"ADDED ({len(diff['added'])}):")
        for key in diff["added"]:
            print(f"  + {_format_key(key)}")
    if diff["removed"]:
        print(f"REMOVED ({len(diff['removed'])}):")
        for key in diff["removed"]:
            print(f"  - {_format_key(key)}")
    if diff["changed"]:
        base_index = _index(baseline)
        curr_index = _index(current)
        print(f"CHANGED p_low ({len(diff['changed'])}):")
        for key in diff["changed"]:
            print(f"  ~ {_format_key(key)}: {base_index[key]:.4f} -> {curr_index[key]:.4f}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
