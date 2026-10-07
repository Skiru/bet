#!/usr/bin/env python3
"""Fit config/sofa_superbet_line_evidence.json - every key's settled Superbet lines.

Between days only (CLAUDE.md: never mid-day). Read from
epochs.LINE_EVIDENCE_FROM_UTC by CONFIDENCE and SPORT_CONFIDENCE through
bet.sofa.line_evidence: a curve its settled lines show overstating is lowered,
a key without a curve reads its own settled lines, nothing is refused by name.

Populations, each read against the curve installed NOW (the offset is a
statement about that curve, so a refit of the curves re-runs this):

* football / tennis - the sheet rows of every stats-only day (epochs.
  STATS_ONLY_DATE ..) before --before: 07_settled.json, a priced row graded
  WIN / LOSS, its p_central (no price since 2026-10-05) read through
  confidence.Calibration as CONFIDENCE reads it (stats-only flags; a derived
  joint has no curve), keyed market|DIRECTION, a class leg under its class;
* hockey / basketball / volleyball / CS2 - the settled Superbet lines with
  their model p (no price): --sport-rows-dir/<sport>_superbet_settled.jsonl
  as fit_sport_confidence.py --rows-out writes them, read through the
  installed sport curves of any fitted key, each joined back to its graded
  side in the day's settled.json for the price band; without the directory,
  the installed calibration's own out-of-sample section (oos.superbet_settled)
  - an offset and the bucket, but NO price-band cap (it carries no price).

* hockey / basketball player lines - every graded player side in the
  shadow settled.json of a day before --before whose model_p is the pre-game
  one (`model_source` pregame: player_model's number SHADOW wrote before the
  start, no price); no history curve, so these are their only evidence.

Every row carries Superbet's price for line_evidence's price-band cap.

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_line_evidence.py \
        --before <d> [--dry-run] [--sport-rows-dir <dir>]
Exit 0 written (or --dry-run printed), 2 on a crash.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import line_evidence as le  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    Calibration,
    direction_key,
    is_derived,
    match_class,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import cs2_day_dir  # noqa: E402
from bet.sofa.epochs import STATS_ONLY_DATE  # noqa: E402
from bet.sofa.shadow import SETTLED_FILE, shadow_day_dir  # noqa: E402

SHEET_SPORTS = ("football", "tennis")


def stats_only_days(runs_dir: Path, before: str) -> list[str]:
    return sorted(
        d.name for d in runs_dir.iterdir()
        if d.is_dir() and len(d.name) == 10 and d.name[4] == "-"
        and STATS_ONLY_DATE <= d.name < before
        and (d / "07_settled.json").exists())


def _board_sides(run_dir: Path) -> dict[str, tuple[str, str]]:
    path = run_dir / "01_board.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc if isinstance(doc, list) else doc.get(
        "fixtures", doc.get("events", []))
    return {str(e["superbet_event_id"]): (str(e.get("side_a") or ""),
                                          str(e.get("side_b") or ""))
            for e in entries if isinstance(e, dict) and e.get("superbet_event_id")}


def sheet_rows(runs_dir: Path, days: list[str], cal: Calibration
               ) -> Iterator[le.Row]:
    for day in days:
        run_dir = runs_dir / day
        fixtures = {int(f["sofascore_event_id"]): f for f in json.loads(
            (run_dir / "02_fixtures.json").read_text(encoding="utf-8"))}
        sides = _board_sides(run_dir)
        for r in json.loads((run_dir / "07_settled.json").read_text(encoding="utf-8")):
            sport = r.get("sport")
            if sport not in SHEET_SPORTS or r.get("outcome") not in ("WIN", "LOSS"):
                continue
            if r.get("p_central") is None or not r.get("offered_odds") \
                    or not r.get("direction"):
                continue
            fx = fixtures.get(int(r["sofascore_event_id"])) or {}
            board = next((sides[str(i)] for i in fx.get("superbet_event_ids") or []
                          if str(i) in sides), None)
            klass = match_class(
                sport, fx.get("category_name") if sport == "tennis"
                else fx.get("competition_name"), board, fx.get("competition_id"))
            p = float(r["p_central"])
            hit = None if is_derived(r["market"]) else cal.realised(
                r["market"], p, sport, r["direction"], klass)
            yield {"sport": sport,
                   "key": le.evidence_key(direction_key(r["market"], r["direction"]),
                                          klass),
                   "p": p, "y": 1 if r["outcome"] == "WIN" else 0,
                   "game": f"{day}:{r['sofascore_event_id']}",
                   "base": None if hit is None else float(hit[0]),
                   "odds": float(r["offered_odds"])}


def graded_odds(runs_dir: str, sport: str, date: str
                ) -> dict[tuple[Any, ...], float]:
    """(superbet event, family, period, subject, line, side) -> the graded
    side's price, from the day's settled.json (SHADOW_SETTLE / CS2_SETTLE)."""
    day_dir = cs2_day_dir(runs_dir, date) if sport == "cs2" \
        else shadow_day_dir(runs_dir, sport, date)  # type: ignore[arg-type]
    path = day_dir / SETTLED_FILE
    if not path.exists():
        return {}
    period = "map_nr" if sport == "cs2" else "period"
    out: dict[tuple[Any, ...], float] = {}
    for eid, ev in (json.loads(path.read_text(encoding="utf-8"))
                    .get("events") or {}).items():
        for g in ev.get("graded") or []:
            if g.get("odds"):
                out[(str(eid), g["family"], int(g.get(period) or 0),
                     str(g.get("subject") or ""), g.get("line"), g["side"])] = \
                    float(g["odds"])
    return out


def sport_rows(rows_dir: Path, calibration: scf.SportCalibration,
               runs_dir: str) -> Iterator[le.Row]:
    for sport in scf.SPORT_KEYS:
        path = rows_dir / f"{sport}_superbet_settled.jsonl"
        if not path.exists():
            continue
        prices: dict[str, dict[tuple[Any, ...], float]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            family, side = str(r["key"]).split("|")
            conf = calibration.lookup(sport, family, side, float(r["p"]),
                                      require_admitted=False)
            _, date, eid = str(r["game"]).split(":")
            if date not in prices:
                prices[date] = graded_odds(runs_dir, sport, date)
            odds = prices[date].get((eid, r["family"], int(r.get("period") or 0),
                                     str(r.get("subject") or ""), r.get("line"),
                                     r["side"]))
            yield {"sport": sport, "key": r["key"], "p": float(r["p"]),
                   "y": int(r["y"]), "game": str(r["game"]),
                   "base": None if conf is None else conf.value, "odds": odds}


def player_rows(runs_dir: str, before: str) -> Iterator[le.Row]:
    for sport in ("hockey", "basketball"):
        root = Path(runs_dir) / "shadow" / sport
        if not root.exists():
            continue
        for day_dir in sorted(root.iterdir()):
            day = day_dir.name
            if not (len(day) == 10 and day < before):
                continue
            path = shadow_day_dir(runs_dir, sport, day) / SETTLED_FILE
            if not path.exists():
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            for eid, ev in (doc.get("events") or {}).items():
                for g in ev.get("graded") or []:
                    if not str(g.get("family", "")).startswith("player_") \
                            or g.get("model_source") != "pregame" \
                            or g.get("model_p") is None \
                            or g.get("outcome") not in ("WIN", "LOSS"):
                        continue
                    yield {"sport": sport,
                           "key": scf.curve_key(str(g["family"]), str(g["side"])),
                           "p": float(g["model_p"]),
                           "y": 1 if g["outcome"] == "WIN" else 0,
                           "game": f"s:{day}:{eid}", "base": None,
                           "odds": float(g["odds"]) if g.get("odds") else None}


def sport_section(calibration: scf.SportCalibration) -> dict[str, dict[str, Any]]:
    """The installed calibration's own oos.superbet_settled, as evidence."""
    out: dict[str, dict[str, Any]] = {}
    for sport, entry in (calibration.doc.get("sports") or {}).items():
        oos = ((entry.get("oos") or {}).get("superbet_settled")) or {}
        keys: dict[str, Any] = {}
        for key, ev in oos.items():
            buckets = {label: {"n": int(b["n"]),
                               "k": round(float(b["realised"]) * int(b["n"]))}
                       for label, b in (ev.get("buckets") or {}).items()}
            item: dict[str, Any] = {"n": int(ev.get("n") or 0),
                                    "games": int(ev.get("games") or 0),
                                    "buckets": buckets}
            if ev.get("printable"):
                item["printable"] = ev["printable"]
            keys[key] = item
        if keys:
            out[sport] = keys
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True, help="settled days strictly before")
    ap.add_argument("--sport-rows-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(le.DEFAULT_EVIDENCE))
    ap.add_argument("--sport-calibration", default=None,
                    help="the sport curves the offsets are read against "
                    "(default: the ones the --before day reads, "
                    "sport_confidence.calibration_path_for)")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir)

    cal = dataclasses.replace(Calibration.load(), gap_shrink_k=0.0,
                              cap_market_by_thin=True, cap_pool_by_neighbour=True)
    days = stats_only_days(runs_dir, args.before)
    fitted = le.fit(sheet_rows(runs_dir, days, cal))
    keys, bands = fitted["keys"], fitted["bands"]
    sport_printable = fitted["sport_printable"]
    sport_cal = scf.SportCalibration.load(
        Path(args.sport_calibration) if args.sport_calibration
        else scf.calibration_path_for(args.before))
    sport_source = "none"
    if sport_cal is not None:
        if args.sport_rows_dir:
            sport_fit = le.fit([*sport_rows(Path(args.sport_rows_dir), sport_cal,
                                            config.runs_dir),
                                *player_rows(config.runs_dir, args.before)])
            keys.update(sport_fit["keys"])
            bands.update(sport_fit["bands"])
            sport_printable.update(sport_fit["sport_printable"])
            sport_source = f"rows:{args.sport_rows_dir}"
        else:
            keys.update(sport_section(sport_cal))
            sport_source = "calibration:oos.superbet_settled (no price-band cap)"
    doc = {
        "fitted_from": {
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "before": args.before,
            "sheet_days": days,
            "sport_source": sport_source,
            "sport_calibration_fitted_from": None if sport_cal is None
            else sport_cal.fitted_from,
        },
        "min_bucket": le.MIN_EVIDENCE_BUCKET,
        "min_cap_cell": le.MIN_CAP_CELL,
        "min_offset_rows": le.MIN_OFFSET_ROWS,
        "min_offset_games": le.MIN_OFFSET_GAMES,
        "min_sport_offset_games": le.MIN_SPORT_OFFSET_GAMES,
        "printable_from": le.PRINTABLE_FROM,
        "unfitted_constants": list(le.UNFITTED_CONSTANTS),
        "price_bands": [list(b) for b in le.PRICE_BANDS],
        "keys": keys,
        "bands": bands,
        "sport_printable": sport_printable,
    }
    summary = {
        sport: {
            "keys": len(entry),
            "lines": sum(int(v.get("n") or 0) for v in entry.values()),
            "lowered": sorted(k for k in entry
                              if le.LineEvidence({"keys": {sport: entry}})
                              .offset(sport, k) < 0),
        }
        for sport, entry in sorted(keys.items())
    }
    print(json.dumps({"fitted_from": doc["fitted_from"], "summary": summary},
                     indent=1, ensure_ascii=False))
    if not args.dry_run:
        write_atomic(Path(args.out),
                     json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        print(f"written {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - exit code contract: 2 on a crash
        print(f"FIT_LINE_EVIDENCE_FAILED: {exc!r}", file=sys.stderr)
        sys.exit(2)
