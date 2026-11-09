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

epochs.SCHEDULE_TERM (from the --before day of the switch): the keys of
epochs.SCHEDULE_TERM_MARKETS are read at the corrected p - rows before the
switch from schedule_term_evidence.BACKFILL (backfill_schedule_term_p.py),
from it their own p_central; the simulator's in-scope keys likewise in its
own path. Only those keys' entries change; every pooled number is the fit
of the rows as stored. Before the switch's day nothing is read.

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
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import (  # noqa: E402
    epochs,
    football_sim_curves,
    live_only_curves,
    schedule_term_evidence,
    tennis_point_curves,
    vb_point_pricer,
)
from bet.sofa import line_evidence as le  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    Calibration,
    calibration_path_for,
    curve_market,
    direction_key,
    is_derived,
    match_class,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import cs2_day_dir  # noqa: E402
from bet.sofa.epochs import STATS_ONLY_DATE, derived_curves  # noqa: E402
from bet.sofa.line_curves import day_reads_per_line, leg_line  # noqa: E402
from bet.sofa.shadow import SETTLED_FILE, shadow_day_dir  # noqa: E402

SHEET_SPORTS = ("football", "tennis")

# audit 2026-11-07: from a refit for this day on, the main (pooled) fit leaves
# out the tennis lines SHEET priced with the point model (epochs.
# TENNIS_POINT_MODEL / TENNIS_HANDICAP_POINT_MODEL) - their p_central is the
# point model's, not the estimator the installed / pooled curves describe, so
# they skewed the tennis pooled offset, the price-gap shrink target and the
# price-band cells; they enter only through the point-model evidence path
# (tennis_point_curves.merge_evidence). A refit for an earlier day reproduces
# the old file.
TENNIS_POINT_POOL_SPLIT_FROM_DATE = "2026-11-08"


def tennis_point_pool_split(before: str) -> bool:
    """TENNIS_POINT_POOL_SPLIT_FROM_DATE on the day being fitted for."""
    return before >= TENNIS_POINT_POOL_SPLIT_FROM_DATE


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


def point_priced_markets(run_dir: Path, day: str) -> frozenset[str]:
    """The tennis markets whose settled p_central on `day` is the point
    model's (epochs.tennis_point_markets): by the day when the switches were
    the same all day; on a day a switch turned on mid-day, by the markers of
    the day's own 05_sheet.json (every tennis row of a sheet built under a
    switch carries its marker; SETTLE copies the sheet's p_central) - no sheet
    = only what was on from 00:00Z."""
    start = datetime.fromisoformat(day).replace(tzinfo=UTC)
    first = epochs.tennis_point_markets(day, start)
    last = epochs.tennis_point_markets(
        day, start + timedelta(days=1) - timedelta(microseconds=1))
    if first == last:
        return last
    path = run_dir / "05_sheet.json"
    if not path.exists():
        return first
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc if isinstance(doc, list) else doc.get("rows") or []
    tennis = [r for r in rows if isinstance(r, dict) and r.get("sport") == "tennis"]
    out: set[str] = set(first)
    for (field, rule, _), markets in (
            (epochs.TENNIS_POINT_MODEL_MARKER, epochs.TENNIS_POINT_MODEL_MARKETS),
            (epochs.TENNIS_HANDICAP_POINT_MODEL_MARKER,
             epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS)):
        if tennis and any(r.get(field) == rule for r in tennis):
            out |= markets & last
    return frozenset(out)


def sheet_rows(runs_dir: Path, days: list[str], cal: Calibration,
               derived_curves: bool = False,
               per_line: bool = False,
               point_p: Mapping[str, float] | None = None,
               point_before: str | None = None,
               exclude_point_priced: bool = False,
               p_for: PFor | None = None,
               only_scoped: bool = False) -> Iterator[le.Row]:
    """`per_line`: read a men's football line through its own line curve
    (epochs.LINE_CURVES), as CONFIDENCE will on the --before day - the
    offsets are applied to that day's base. `point_p` (epochs.
    TENNIS_POINT_MODEL on the --before day, else None): ONLY the tennis lines
    of the point model's keys, each at the point model's p
    (tennis_point_curves.evidence_p_for: the scope and switch days of the
    `point_before` day - TENNIS_HANDICAP_POINT_MODEL adds the per-set games
    handicap) or skipped. `exclude_point_priced`
    (TENNIS_POINT_POOL_SPLIT_FROM_DATE): leave out the tennis lines priced by
    the point model (point_priced_markets) - the pooled fit's rows.
    `p_for` (epochs.SCHEDULE_TERM on the --before day, else None): a row it
    calls in scope is read at the p it gives (None: skipped), every other
    row as stored; `only_scoped`: the in-scope rows alone."""
    for day in days:
        run_dir = runs_dir / day
        point_priced = (point_priced_markets(run_dir, day)
                        if exclude_point_priced else frozenset())
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
            if sport == "tennis" and r.get("market") in point_priced:
                continue  # the point model's p: its own evidence path only
            fx = fixtures.get(int(r["sofascore_event_id"])) or {}
            board = next((sides[str(i)] for i in fx.get("superbet_event_ids") or []
                          if str(i) in sides), None)
            klass = match_class(
                sport, fx.get("category_name") if sport == "tennis"
                else fx.get("competition_name"), board, fx.get("competition_id"))
            p = float(r["p_central"])
            if point_p is not None:
                scoped, pp = tennis_point_curves.evidence_p_for(
                    r, day, point_p, point_before or day)
                if not scoped or pp is None:
                    continue  # the point model's lines only, at its own p
                p = pp
            if p_for is not None:
                scoped_st, p_st = p_for(r, day)
                if scoped_st and p_st is None:
                    continue  # no corrected p: no evidence
                if scoped_st and p_st is not None:
                    p = p_st
                elif only_scoped:
                    continue
            hit = None if is_derived(r["market"]) and not derived_curves \
                else cal.realised(
                curve_market(r), p, sport, r["direction"], klass,
                line=leg_line(r, per_line))
            yield {"sport": sport,
                   "key": le.evidence_key(direction_key(r["market"], r["direction"]),
                                          klass),
                   "p": p, "y": 1 if r["outcome"] == "WIN" else 0,
                   "game": f"{day}:{r['sofascore_event_id']}",
                   "base": None if hit is None else float(hit[0]),
                   "odds": float(r["offered_odds"])}


PFor = Callable[[Mapping[str, Any], str], tuple[bool, float | None]]


def schedule_term_p_for(backfill: schedule_term_evidence.Backfill,
                        scope: frozenset[str]) -> PFor:
    """epochs.SCHEDULE_TERM: sheet_rows' `p_for` over `scope`
    (schedule_term_evidence.evidence_p)."""
    def p_for(row: Mapping[str, Any], day: str) -> tuple[bool, float | None]:
        return schedule_term_evidence.evidence_p(row, day, backfill, scope=scope)
    return p_for


def schedule_term_backfill(before: str, path: Path | None = None
                           ) -> schedule_term_evidence.Backfill | None:
    """The corrected-p table the --before day's fit reads: None while
    epochs.SCHEDULE_TERM is off for it (nothing changes) or when the table
    is missing (the rows as stored, a WARN on stderr)."""
    if not epochs.schedule_term(before):
        return None
    got = schedule_term_evidence.load_backfill(path)
    if got is None:
        print("WARN schedule_term: no corrected-p table "
              f"({path or schedule_term_evidence.BACKFILL}); the in-scope keys read "
              "their rows as stored - run backfill_schedule_term_p.py",
              file=sys.stderr)
    return got


def apply_schedule_term(fitted: dict[str, Any], rows: Iterator[le.Row]) -> None:
    """epochs.SCHEDULE_TERM: the sheet-path in-scope keys' entries from
    `rows` (sheet_rows over the in-scope rows at the corrected p); every
    pooled number and every other key stays `fitted`'s (in place)."""
    schedule_term_evidence.merge_evidence(fitted, le.fit(rows))


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
               runs_dir: str,
               vb_point_p: Mapping[str, float] | None = None) -> Iterator[le.Row]:
    """`vb_point_p` (epochs.VB_POINT_MODEL on the --before day, else None):
    a volleyball line of the rally model's markets is read at the rally
    model's p (vb_point_pricer.BACKFILL) or skipped - never at the score
    model's, these keys' curves describe the rally model."""
    for sport in scf.SPORT_KEYS:
        path = rows_dir / f"{sport}_superbet_settled.jsonl"
        if not path.exists():
            continue
        prices: dict[str, dict[tuple[Any, ...], float]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            family, side = str(r["key"]).split("|")
            _, date, eid = str(r["game"]).split(":")
            if vb_point_p is not None and vb_point_pricer.in_scope(
                    sport, r.get("market_id")):
                vb_p = vb_point_p.get(vb_point_pricer.backfill_key(
                    date, eid, r["market_id"], r.get("period"), r.get("subject"),
                    r.get("line"), r["side"]))
                if vb_p is None:
                    continue
                r["p"] = vb_p
            conf = calibration.lookup(sport, family, side, float(r["p"]),
                                      require_admitted=False)
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


def reads_derived_curves(before: str, flag: bool = False) -> bool:
    """A derived joint's offsets are fitted against its history curve when the
    --before day reads it (epochs.DERIVED_CURVES), else against none - the
    morning refresh never passed the flag, so from the switch the joints got
    only the sport's pooled offset."""
    return flag or derived_curves(before)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True, help="settled days strictly before")
    ap.add_argument("--sport-rows-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(le.DEFAULT_EVIDENCE))
    ap.add_argument("--derived-curves", action="store_true",
                    help="offsets of a derived joint against its history curve even "
                    "before epochs.DERIVED_CURVES_FROM_UTC (on by itself from it)")
    ap.add_argument("--sport-calibration", default=None,
                    help="the sport curves the offsets are read against "
                    "(default: the ones the --before day reads, "
                    "sport_confidence.calibration_path_for)")
    ap.add_argument("--schedule-term-backfill", default=None,
                    help="the corrected-p table (epochs.SCHEDULE_TERM; default "
                    "schedule_term_evidence.BACKFILL)")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir)

    # The curves the --before day reads (a staged refit from its start).
    cal = dataclasses.replace(Calibration.load(calibration_path_for(args.before)),
                              gap_shrink_k=0.0,
                              cap_market_by_thin=True, cap_pool_by_neighbour=True)
    # epochs.LIVE_ONLY_CURVE_REFUSED: the base the --before day reads
    cal = live_only_curves.for_day(cal, args.before)
    days = stats_only_days(runs_dir, args.before)
    # epochs.LINE_CURVES: the base is the curve the --before day reads, at its
    # own line where that day reads per line
    per_line = day_reads_per_line(args.before)
    pool_split = tennis_point_pool_split(args.before)
    # epochs.SCHEDULE_TERM: None while off for the --before day
    schedule_bf = schedule_term_backfill(
        args.before, Path(args.schedule_term_backfill)
        if args.schedule_term_backfill else None)
    fitted = le.fit(sheet_rows(runs_dir, days, cal,
                               reads_derived_curves(args.before, args.derived_curves),
                               per_line, exclude_point_priced=pool_split))
    # epochs.TENNIS_POINT_MODEL: the point model's keys' own entries from
    # their lines at the point model's p against their own curves; every
    # pooled number (the sport's offsets, bands, design effect) and every
    # other key stays the fit above
    point_p: dict[str, float] | None = None
    if epochs.tennis_point_model(args.before):
        point_p = tennis_point_curves.load_backfill(
            handicap=epochs.tennis_handicap_point_model(args.before))
        point_fit = le.fit(sheet_rows(
            runs_dir, days, tennis_point_curves.for_day(cal, args.before),
            False, False, point_p, args.before))
        tennis_point_curves.merge_evidence(
            fitted, point_fit,
            markets=tennis_point_curves.markets_for(args.before))
    # epochs.FOOTBALL_SIM: the simulator's keys' own entries from their lines
    # at the simulator's p against their own curves - the backfilled Superbet
    # lines before the switch (football_sim_curves.BACKFILL), the days' own
    # settled rows from it; every pooled number stays the fit above
    sim_lines: list[dict[str, Any]] | None = None
    if epochs.football_sim(args.before):
        sim_cal = football_sim_curves.for_day(cal, args.before)
        sim_day = (epochs.FOOTBALL_SIM_FROM_UTC.strftime("%Y-%m-%d")
                   if epochs.FOOTBALL_SIM_FROM_UTC else None)
        sim_lines = football_sim_curves.load_backfill()
        live_days = [d for d in days if sim_day is not None and d >= sim_day]
        # epochs.SCHEDULE_TERM: the simulator's in-scope keys at the
        # corrected p (the backfilled lines and the live rows alike); the
        # four floor keys as stored
        sim_read = (sim_lines if schedule_bf is None else
                    list(schedule_term_evidence.sim_lines(sim_lines, schedule_bf)))
        sim_p_for = (None if schedule_bf is None else schedule_term_p_for(
            schedule_bf, schedule_term_evidence.sim_markets()))
        sim_fit = le.fit([
            *football_sim_curves.backfill_rows(sim_read, args.before, sim_cal,
                                               sim_day),
            *(r for r in sheet_rows(runs_dir, live_days, sim_cal, p_for=sim_p_for)
              if football_sim_curves.ours(str(r["key"])))])
        football_sim_curves.merge_evidence(fitted, sim_fit)
    # epochs.SCHEDULE_TERM: 1X2 / DNB / DC / score markets / first goal at
    # the corrected p (rows before the switch from the backfill, from it
    # their own p_central), merged over the pooled fit's entries
    if schedule_bf is not None:
        apply_schedule_term(fitted, sheet_rows(
            runs_dir, days, cal,
            reads_derived_curves(args.before, args.derived_curves), per_line,
            exclude_point_priced=pool_split,
            p_for=schedule_term_p_for(schedule_bf,
                                      schedule_term_evidence.sheet_markets()),
            only_scoped=True))
    keys, bands = fitted["keys"], fitted["bands"]
    sport_printable = fitted["sport_printable"]
    sport_by_gap = dict(fitted["sport_printable_by_gap"])
    design_effect = dict(fitted["design_effect"])
    # epochs.VB_POINT_MODEL: the rally keys' curves by the clock (a mixed day)
    sport_cal = scf.with_vb_point_curves(scf.SportCalibration.load(
        Path(args.sport_calibration) if args.sport_calibration
        else scf.calibration_path_for(args.before)), args.before, None)
    sport_source = "none"
    if sport_cal is not None:
        if args.sport_rows_dir:
            # epochs.VB_POINT_MODEL: the rally model's lines at its own p
            vb_p = (vb_point_pricer.load_backfill()
                    if epochs.vb_point_model(args.before) else None)
            sport_fit = le.fit([*sport_rows(Path(args.sport_rows_dir), sport_cal,
                                            config.runs_dir, vb_p),
                                *player_rows(config.runs_dir, args.before)])
            keys.update(sport_fit["keys"])
            bands.update(sport_fit["bands"])
            sport_printable.update(sport_fit["sport_printable"])
            sport_by_gap.update(sport_fit["sport_printable_by_gap"])
            design_effect.update(sport_fit["design_effect"])
            sport_source = f"rows:{args.sport_rows_dir}"
            if vb_p is not None:
                sport_source += (f"; volleyball rally model p "
                                 f"(epochs.VB_POINT_MODEL): {len(vb_p)} lines")
        else:
            keys.update(sport_section(sport_cal))
            sport_source = "calibration:oos.superbet_settled (no price-band cap)"
    doc: dict[str, Any] = {
        "fitted_from": {
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "before": args.before,
            "sheet_days": days,
            # epochs.LINE_CURVES: football bases read at their own line
            "per_line_base": per_line,
            # epochs.TENNIS_POINT_MODEL: backfilled point-model p of the
            # in-scope tennis lines (tennis_point_curves.BACKFILL)
            "tennis_point_model_backfill": (
                None if point_p is None else len(point_p)),
            # epochs.FOOTBALL_SIM: backfilled graded Superbet lines of the
            # path markets (football_sim_curves.BACKFILL)
            "football_sim_backfill": (
                None if sim_lines is None else len(sim_lines)),
            # epochs.SCHEDULE_TERM: corrected p of the in-scope football
            # lines before the switch (schedule_term_evidence.BACKFILL);
            # absent while off
            **({"schedule_term_backfill": {
                "sheet": len(schedule_bf.sheet),
                "sim_lines": len(schedule_bf.sim_lines),
                "built_through": schedule_bf.meta.get("built_through"),
                "config_sha256": schedule_bf.meta.get("config_sha256")}}
               if schedule_bf is not None
               else {"schedule_term_backfill": "MISSING"}
               if epochs.schedule_term(args.before) else {}),
            "sport_source": sport_source,
            "sport_calibration_fitted_from": None if sport_cal is None
            else sport_cal.fitted_from,
        },
        "min_bucket": le.MIN_EVIDENCE_BUCKET,
        "min_cap_cell": le.MIN_CAP_CELL,
        "min_offset_rows": le.MIN_OFFSET_ROWS,
        "min_offset_games": le.MIN_OFFSET_GAMES,
        "min_sport_offset_games": le.MIN_SPORT_OFFSET_GAMES,
        "min_evidence_games": le.MIN_EVIDENCE_GAMES,
        "concentration_max": le.CONCENTRATION_MAX,
        "printable_from": le.PRINTABLE_FROM,
        "unfitted_constants": list(le.UNFITTED_CONSTANTS),
        "price_bands": [list(b) for b in le.PRICE_BANDS],
        # epochs.PRICE_GAP_OFFSET: the d = curve - 1/odds buckets
        "price_gap_edges": list(le.PRICE_GAP_EDGES),
        "price_gap_shrink_k": le.PRICE_GAP_SHRINK_K,
        "keys": keys,
        "bands": bands,
        "sport_printable": sport_printable,
        "sport_printable_by_gap": sport_by_gap,
        "design_effect": design_effect,
    }
    if pool_split:
        # TENNIS_POINT_POOL_SPLIT_FROM_DATE: point-model-priced tennis lines
        # out of the pooled fit (absent before it: the old file reproduced)
        doc["fitted_from"]["tennis_point_pool_split"] = True
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
