#!/usr/bin/env python3
"""Re-measure CONFIDENCE's disagreement gate on settled, priced rows.

`MAX_DISAGREEMENT = 0.10` (src/bet/sofa/confidence.py) refuses a leg whose
claim sits more than 0.10 above the devigged market price. It was measured
on 2026-09-21, before the estimator changed (football rating centre, NB
counts, 09-23/24), so this script asks again whether the rows it refuses do
worse than the rows it admits.

What is reproduced, per settled row (sofa_settled_row, run_date in range):

  * the quantity the gate compares - `disagrees_with_price(p_central,
    market_p, confidence, odds, sample_frequency)`, the very function
    run_confidence.py calls. `sample_frequency` is not stored in the DB; it
    is read (read-only) from the day's 05_sheet.json for tennis rows, the
    only rows that ever carry it. Football rows never do, so football reads
    p_central exactly as CONFIDENCE does;
  * confidence = Calibration.realised(market, p_central, sport, direction,
    klass) on the calibration file given, with the match class derived from
    02_fixtures.json / 01_board.json the way run_confidence.py derives it
    (competition id alone where the artifacts are absent or --no-artifacts);
    a row the lookup refuses (NOT_CALIBRATED / NO_CLASS_CURVE) is skipped;
  * each profile's floor and price rule (confidence.PROFILES), MIN_ODDS
    (MIN_ODDS_FOR_CEILING), and the exclusions CONFIDENCE makes from the
    market alone: no model, derived markets, player props, friendlies.

What is NOT reproduced - settled rows do not carry it - and is named in the
output: the ladder margin (max_overround applies to singles), vetoes,
kickoff and price-age gates, UNREACHABLE_BAR / CROSS_LEAGUE_UNLINKED notes,
and the sample-shape gates (LINE_BEYOND_SAMPLE, MODE_LOSES, thin / stale
samples). The confidence of a leg also depends on the curves at build time;
this script reads ONE calibration file for every day, so a row may be
admitted here that the coupon of its day refused, and the reverse. A refit
changes the result.

Per cell: rows, matches, mean confidence, mean claim, mean market_p,
realised hit rate, realised - market_p, ROI per bet at offered_odds, a 95%
interval from resampling whole matches (bet.sofa.clv.cluster_ratio_interval,
"-" below --min-clusters), and the two event-id halves (even / odd) apart.

This is a measurement only. The decision to change MAX_DISAGREEMENT is the
operator's, taken between days, with a coupon replay before it is installed
- the same rule as a refit. The script writes nothing the pipeline reads and
opens the DB read-only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_disagreement.py \\
        --from 2026-09-24 --to 2026-10-01 [--sport football] [--profile both]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.clv import MIN_CLUSTERS, cluster_ratio_interval  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    DEFAULT_CALIBRATION,
    MAX_DISAGREEMENT,
    MIN_ODDS_FOR_CEILING,
    PLAYER_PROP_MARKETS,
    PROFILES,
    Calibration,
    ConfidenceProfile,
    disagrees_with_price,
    match_class,
    reads_catch_all_bucket,
)
from bet.sofa.engine import has_calibratable_model  # noqa: E402
from bet.sofa.fit_meta import friendly_exclusion_sql  # noqa: E402
from bet.sofa.market_mapper import is_derived  # noqa: E402

# run_confidence.py: MIN_ODDS = MIN_ODDS_FOR_CEILING.
MIN_ODDS = MIN_ODDS_FOR_CEILING

BANDS = ("<0", "0-0.05", "0.05-0.10", "0.10-0.15", ">=0.15")
GATE_CELLS = ("refused", "admitted")

NOT_REPRODUCED = (
    "ladder margin (max_overround)", "vetoes", "kickoff / price age",
    "UNREACHABLE_BAR / CROSS_LEAGUE_UNLINKED notes",
    "sample-shape gates (beyond sample, mode, thin, stale)",
)

# Never written to: the pipeline's inputs and outputs.
_PROTECTED_DIRS = ("data", "runs", "config")

RowKey = tuple[int, str, str, float, str]


@dataclass(frozen=True)
class SettledRow:
    run_date: str
    sofascore_event_id: int
    sport: str
    competition_id: int | None
    market: str
    subject: str
    line: float
    direction: str
    p_central: float
    market_p: float
    offered_odds: float
    won: bool

    @property
    def key(self) -> RowKey:
        return (self.sofascore_event_id, self.market, self.subject,
                float(self.line), self.direction)

    @property
    def profit(self) -> float:
        return self.offered_odds - 1.0 if self.won else -1.0


@dataclass(frozen=True)
class GatedRow:
    row: SettledRow
    confidence: float
    claim: float  # sample_frequency where the row has one, else p_central
    gap: float  # claim - market_p
    refused: bool  # disagrees_with_price


@dataclass
class DayArtifacts:
    """What the day's artifacts add to a settled row (read-only)."""

    classes: dict[int, str | None] = field(default_factory=dict)
    sample_frequency: dict[RowKey, float] = field(default_factory=dict)
    fixtures_found: bool = False
    sheet_found: bool = False


def parse_day(text: str) -> str:
    """A real calendar date only - 'cache-calibration' is not a day."""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a date: {text!r}") from exc


def day_range(first: str, last: str) -> list[str]:
    d0, d1 = date.fromisoformat(first), date.fromisoformat(last)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def connect_ro(db_path: str | Path) -> sqlite3.Connection:
    uri = f"file:{Path(db_path).resolve()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def load_rows(
    conn: sqlite3.Connection, first: str, last: str, sports: Sequence[str]
) -> tuple[list[SettledRow], Counter[str]]:
    """Priced WIN/LOSS rows of real days in [first, last], minus the rows
    CONFIDENCE refuses on the market alone. Returns the rows and why the
    others were dropped."""
    marks = ",".join("?" for _ in sports)
    sql = (
        "SELECT run_date, sofascore_event_id, sport, competition_id, market, "
        "subject, line, direction, p_central, market_p, offered_odds, outcome, "
        f"NOT ({friendly_exclusion_sql()}) AS friendly "
        "FROM sofa_settled_row "
        "WHERE run_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
        "AND run_date BETWEEN ? AND ? "
        f"AND sport IN ({marks}) "
        "AND offered_odds IS NOT NULL AND market_p IS NOT NULL "
        "AND outcome IN ('WIN', 'LOSS')"
    )
    all_rows = conn.execute(sql, (first, last, *sports)).fetchall()
    dropped: Counter[str] = Counter()
    out: list[SettledRow] = []
    for r in all_rows:
        market = str(r[4])
        if r[12]:
            dropped["FRIENDLY_FIXTURE"] += 1
            continue
        if not has_calibratable_model(market):
            dropped["NOT_IN_CALIBRATION_FIT"] += 1
            continue
        if is_derived(market):
            dropped["DERIVED_NOT_CALIBRATABLE"] += 1
            continue
        if market in PLAYER_PROP_MARKETS:
            dropped["PLAYER_PROP"] += 1
            continue
        odds = float(r[10])
        if odds < MIN_ODDS:
            dropped["ODDS_TOO_LOW"] += 1
            continue
        out.append(SettledRow(
            run_date=str(r[0]), sofascore_event_id=int(r[1]), sport=str(r[2]),
            competition_id=None if r[3] is None else int(r[3]), market=market,
            subject=str(r[5] or ""), line=float(r[6]), direction=str(r[7]),
            p_central=float(r[8]), market_p=float(r[9]), offered_odds=odds,
            won=r[11] == "WIN",
        ))
    return out, dropped


def _board_sides(run_dir: Path) -> dict[str, tuple[str, str]]:
    """Superbet's side names by event id - as run_confidence.py reads them."""
    path = run_dir / "01_board.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc if isinstance(doc, list) else doc.get(
        "fixtures", doc.get("events", []))
    sides: dict[str, tuple[str, str]] = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("superbet_event_id"):
            sides[str(entry["superbet_event_id"])] = (
                str(entry.get("side_a") or ""), str(entry.get("side_b") or ""))
    return sides


def load_day_artifacts(run_dir: Path, need_sheet: bool) -> DayArtifacts:
    """Match class per fixture and tennis sample_frequency per row key."""
    art = DayArtifacts()
    fx_path = run_dir / "02_fixtures.json"
    if fx_path.exists():
        art.fixtures_found = True
        board = _board_sides(run_dir)
        for fx in json.loads(fx_path.read_text(encoding="utf-8")):
            sport = fx.get("sport")
            sides = next(
                (board[str(i)] for i in fx.get("superbet_event_ids") or []
                 if str(i) in board), None)
            art.classes[int(fx["sofascore_event_id"])] = match_class(
                sport,
                fx.get("category_name") if sport == "tennis"
                else fx.get("competition_name"),
                sides,
                fx.get("competition_id"),
            )
    sheet_path = run_dir / "05_sheet.json"
    if need_sheet and sheet_path.exists():
        art.sheet_found = True
        for r in json.loads(sheet_path.read_text(encoding="utf-8")):
            freq = r.get("sample_frequency")
            if freq is None:
                continue
            key = (int(r["sofascore_event_id"]), str(r["market"]),
                   str(r.get("subject") or ""), float(r["line"]),
                   str(r["direction"]))
            art.sample_frequency[key] = float(freq)
    return art


def row_class(row: SettledRow, art: DayArtifacts | None) -> str | None:
    if art is not None and row.sofascore_event_id in art.classes:
        return art.classes[row.sofascore_event_id]
    # Without the fixture only the competition id can say "women".
    return match_class(row.sport, None, None, row.competition_id)


def gate_rows(
    rows: Iterable[SettledRow],
    cal: Calibration,
    artifacts: dict[str, DayArtifacts] | None,
) -> tuple[list[GatedRow], Counter[str]]:
    """Confidence and the gate's verdict for every row the curve serves."""
    out: list[GatedRow] = []
    skipped: Counter[str] = Counter()
    for row in rows:
        art = artifacts.get(row.run_date) if artifacts is not None else None
        klass = row_class(row, art)
        hit = cal.realised(row.market, row.p_central, row.sport, row.direction,
                           klass)
        if hit is None:
            unclassed = klass is not None and cal.realised(
                row.market, row.p_central, row.sport, row.direction) is not None
            skipped["NO_CLASS_CURVE" if unclassed else "NOT_CALIBRATED"] += 1
            continue
        # As run_confidence: the gap shrink (off unless the calibration file
        # sets gap_shrink_k) comes before every gate.
        confidence = cal.shrink_for_gap(float(hit[0]), row.p_central, row.market_p)
        freq = art.sample_frequency.get(row.key) if art is not None else None
        claim = freq if freq is not None else row.p_central
        refused = disagrees_with_price(
            row.p_central, row.market_p, confidence, row.offered_odds, freq)
        out.append(GatedRow(row, confidence, claim, claim - row.market_p, refused))
    return out, skipped


def passes_profile(g: GatedRow, profile: ConfidenceProfile) -> bool:
    """Floor and price rule of the profile - the gates around the split.

    With run_confidence's CATCH_ALL_BUCKET refusal, which sits right after
    the floor there."""
    return (
        g.confidence >= profile.floor
        and not reads_catch_all_bucket(g.row.p_central)
        and profile.clears_price(g.confidence, g.row.offered_odds)
    )


def band(g: GatedRow) -> str:
    """Gap band; the 0.10 edge follows the gate itself, never a re-derivation."""
    if g.gap < 0.0:
        return "<0"
    if g.gap < 0.05:
        return "0-0.05"
    if not g.refused:
        return "0.05-0.10"
    return "0.10-0.15" if g.gap < 0.15 else ">=0.15"


@dataclass(frozen=True)
class Cell:
    n: int
    matches: int
    confidence: float | None
    claim: float | None
    market_p: float | None
    hit: float | None
    edge: float | None  # realised - market_p
    edge_ci: tuple[float, float] | None
    roi: float | None
    roi_ci: tuple[float, float] | None
    roi_even: float | None
    roi_even_ci: tuple[float, float] | None
    n_even: int
    roi_odd: float | None
    roi_odd_ci: tuple[float, float] | None
    n_odd: int


def _roi(rows: Sequence[GatedRow]) -> float | None:
    return sum(g.row.profit for g in rows) / len(rows) if rows else None


def _interval(
    rows: Sequence[GatedRow], value: str, seed: int, boot: int, min_clusters: int
) -> tuple[float, float] | None:
    clusters: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for g in rows:
        c = clusters[str(g.row.sofascore_event_id)]
        c[0] += g.row.profit if value == "roi" else (
            (1.0 if g.row.won else 0.0) - g.row.market_p)
        c[1] += 1
    return cluster_ratio_interval(
        {k: (v[0], int(v[1])) for k, v in clusters.items()},
        seed=seed, n_boot=boot, min_clusters=min_clusters)


def summarize(
    rows: Sequence[GatedRow], seed: int, boot: int, min_clusters: int
) -> Cell:
    n = len(rows)

    def mean(xs: Iterable[float]) -> float | None:
        vals = list(xs)
        return sum(vals) / len(vals) if vals else None

    even = [g for g in rows if g.row.sofascore_event_id % 2 == 0]
    odd = [g for g in rows if g.row.sofascore_event_id % 2 == 1]
    hit = mean(1.0 if g.row.won else 0.0 for g in rows)
    mp = mean(g.row.market_p for g in rows)
    return Cell(
        n=n,
        matches=len({g.row.sofascore_event_id for g in rows}),
        confidence=mean(g.confidence for g in rows),
        claim=mean(g.claim for g in rows),
        market_p=mp,
        hit=hit,
        edge=None if hit is None or mp is None else hit - mp,
        edge_ci=_interval(rows, "edge", seed, boot, min_clusters),
        roi=_roi(rows),
        roi_ci=_interval(rows, "roi", seed, boot, min_clusters),
        roi_even=_roi(even),
        roi_even_ci=_interval(even, "roi", seed, boot, min_clusters),
        n_even=len(even),
        roi_odd=_roi(odd),
        roi_odd_ci=_interval(odd, "roi", seed, boot, min_clusters),
        n_odd=len(odd),
    )


def measure_profile(
    gated: Sequence[GatedRow], profile: ConfidenceProfile,
    seed: int, boot: int, min_clusters: int,
) -> dict[str, Cell]:
    """Gate cells and gap bands for the rows that clear the profile."""
    rows = [g for g in gated if passes_profile(g, profile)]
    cells: dict[str, list[GatedRow]] = {k: [] for k in (*GATE_CELLS, *BANDS)}
    for g in rows:
        cells["refused" if g.refused else "admitted"].append(g)
        cells[band(g)].append(g)
    return {k: summarize(v, seed, boot, min_clusters) for k, v in cells.items()}


def _pct(x: float | None, digits: int = 1) -> str:
    return "-" if x is None else f"{100 * x:+.{digits}f}%"


def _prob(x: float | None) -> str:
    return "-" if x is None else f"{x:.3f}"


def _ci(ci: tuple[float, float] | None) -> str:
    return "-" if ci is None else f"[{100 * ci[0]:+.1f},{100 * ci[1]:+.1f}]"


def overlap(
    a: tuple[float, float] | None, b: tuple[float, float] | None
) -> bool | None:
    if a is None or b is None:
        return None
    return a[0] <= b[1] and b[0] <= a[1]


def verdict(cells: dict[str, Cell]) -> str:
    """Facts only - never a recommendation about the constant."""
    r, a = cells["refused"], cells["admitted"]

    def gt(x: float | None, y: float | None) -> str:
        return "untested" if x is None or y is None else ("yes" if x > y else "no")

    ov = overlap(r.roi_ci, a.roi_ci)
    ov_text = "untested (interval '-')" if ov is None else ("yes" if ov else "no")
    both = (
        "yes" if gt(r.roi_even, a.roi_even) == "yes"
        and gt(r.roi_odd, a.roi_odd) == "yes" and ov is False else "no"
    )
    return (
        f"refused ROI > admitted ROI: all {gt(r.roi, a.roi)}, even "
        f"{gt(r.roi_even, a.roi_even)}, odd {gt(r.roi_odd, a.roi_odd)}; "
        f"ROI intervals overlap: {ov_text}; "
        f"refused > admitted on both halves AND intervals do not overlap: {both}"
    )


def render_profile(
    name: str, profile: ConfidenceProfile, cells: dict[str, Cell]
) -> str:
    rule = ("confidence x odds > 1" if profile.min_ev is None
            else f"confidence x odds >= {profile.min_ev:.2f}")
    head = (
        f"{'cell':<10} {'rows':>6} {'match':>6} {'conf':>6} {'claim':>6} "
        f"{'mkt_p':>6} {'hit':>6} {'hit-mkt':>8} {'95% (pp)':>15} "
        f"{'ROI':>7} {'95%':>15} {'even ROI':>9} {'odd ROI':>9} "
        f"{'95% even':>15} {'95% odd':>15}"
    )
    lines = [
        f"== profile {name}: floor {profile.floor:.2f}, {rule}, odds >= "
        f"{MIN_ODDS:.4f}; gate: claim - market_p > {MAX_DISAGREEMENT:.2f} refuses ==",
        head,
    ]
    for key in (*GATE_CELLS, *BANDS):
        if key == BANDS[0]:
            lines.append("-- by gap (claim - market_p) --")
        c = cells[key]
        lines.append(
            f"{key:<10} {c.n:>6} {c.matches:>6} {_prob(c.confidence):>6} "
            f"{_prob(c.claim):>6} {_prob(c.market_p):>6} {_prob(c.hit):>6} "
            f"{_pct(c.edge):>8} {_ci(c.edge_ci):>15} {_pct(c.roi):>7} "
            f"{_ci(c.roi_ci):>15} {_pct(c.roi_even):>9} {_pct(c.roi_odd):>9} "
            f"{_ci(c.roi_even_ci):>15} {_ci(c.roi_odd_ci):>15}"
        )
    lines.append("verdict (facts): " + verdict(cells))
    return "\n".join(lines)


def _protected(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to((_REPO / d).resolve()) for d in _PROTECTED_DIRS)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="first", required=True, type=parse_day)
    ap.add_argument("--to", dest="last", required=True, type=parse_day)
    ap.add_argument("--sport", choices=("football", "tennis", "all"),
                    default="football")
    ap.add_argument("--profile", choices=("standard", "wariant", "both"),
                    default="both")
    ap.add_argument("--db-path", default=str(_REPO / "data" / "sofa.db"))
    ap.add_argument("--calibration", default=str(DEFAULT_CALIBRATION))
    ap.add_argument("--runs-dir", default=str(_REPO / "runs" / "sofa"),
                    help="read-only: 02_fixtures/01_board (class), 05_sheet (tennis "
                         "sample_frequency)")
    ap.add_argument("--no-artifacts", action="store_true",
                    help="class from competition id only, no sample_frequency")
    ap.add_argument("--min-clusters", type=int, default=MIN_CLUSTERS)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    if args.first > args.last:
        ap.error("--from is after --to")
    if args.json_out and _protected(Path(args.json_out)):
        ap.error("--json-out may not write under data/, runs/ or config/")
    if not Path(args.db_path).exists():
        print(f"no DB at {args.db_path}", file=sys.stderr)
        return 2

    sports = ("football", "tennis") if args.sport == "all" else (args.sport,)
    profiles = ("standard", "wariant") if args.profile == "both" else (args.profile,)
    conn = connect_ro(args.db_path)
    try:
        rows, dropped = load_rows(conn, args.first, args.last, sports)
    finally:
        conn.close()
    cal = Calibration.load(args.calibration)

    artifacts: dict[str, DayArtifacts] | None = None
    if not args.no_artifacts:
        artifacts = {}
        for day in sorted({r.run_date for r in rows}):
            need_sheet = any(r.sport == "tennis" and r.run_date == day for r in rows)
            artifacts[day] = load_day_artifacts(Path(args.runs_dir) / day, need_sheet)
    gated, skipped = gate_rows(rows, cal, artifacts)

    days_with_rows = sorted({r.run_date for r in rows})
    n_class = Counter(
        row_class(r, artifacts.get(r.run_date) if artifacts else None) for r in rows)
    n_freq = sum(1 for g in gated if g.claim != g.row.p_central)
    print(
        f"measure_disagreement {args.first}..{args.last}  sport={args.sport}  "
        f"days with settled priced rows: {', '.join(days_with_rows) or 'none'}"
    )
    missing = [d for d in day_range(args.first, args.last) if d not in days_with_rows]
    if missing:
        print(f"  no settled priced rows (unsettled or absent): {', '.join(missing)}")
    print(f"  priced WIN/LOSS rows kept {len(rows)}; dropped before the curve: "
          f"{dict(sorted(dropped.items())) or 'none'}")
    refused_by_curve = {k: v for k, v in sorted(skipped.items()) if v}
    print(f"  curve refused: {refused_by_curve or 'none'}; served: {len(gated)}")
    if artifacts is None:
        print("  class: competition id only (--no-artifacts); sample_frequency: not "
              "read (football never carries it; tennis claims would be p_central)")
    else:
        no_fx = [d for d, a in artifacts.items() if not a.fixtures_found]
        print(f"  class from 02_fixtures/01_board (competition id where absent: "
              f"{', '.join(no_fx) or 'none'}): "
              f"{ {str(k): v for k, v in n_class.items()} }")
        if "tennis" in sports:
            print(f"  tennis claim = sample_frequency on {n_freq} served rows "
                  "(05_sheet.json joined on event/market/subject/line/direction)")
    print(f"  calibration: {args.calibration} (one file for every day)")
    print(f"  not reproduced from settled rows: {'; '.join(NOT_REPRODUCED)}")
    print(f"  bootstrap: {args.boot} resamples of whole matches, seed {args.seed}, "
          f"'-' below {args.min_clusters} matches; halves = event id even / odd")
    print()

    doc: dict[str, Any] = {
        "from": args.first, "to": args.last, "sport": args.sport,
        "max_disagreement": MAX_DISAGREEMENT, "calibration": args.calibration,
        "dropped": dict(dropped), "curve_refused": dict(skipped),
        "not_reproduced": list(NOT_REPRODUCED), "profiles": {},
    }
    for name in profiles:
        cells = measure_profile(gated, PROFILES[name], args.seed, args.boot,
                                args.min_clusters)
        print(render_profile(name, PROFILES[name], cells))
        print()
        doc["profiles"][name] = {
            "floor": PROFILES[name].floor, "min_ev": PROFILES[name].min_ev,
            "cells": {k: c.__dict__ for k, c in cells.items()},
            "verdict": verdict(cells),
        }
    print(
        "caveat: the coupon's legs depend on the curves at build time; this reads "
        "one calibration file for every day, and a refit changes which rows clear "
        "each profile. Measurement only - the threshold decision is the operator's, "
        "between days, with a coupon replay before install."
    )
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
