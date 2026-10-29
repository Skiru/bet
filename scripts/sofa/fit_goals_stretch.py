"""Fit the goals-stretch coefficients (epochs.FOOTBALL_GOALS_STRETCH) into
config/sofa_goals_stretch.json.

beta_m per side market (goals_for, goals_1h_for, goals_2h_for) and (g1_m,
g2_m) per total (goals_total, goals_1h_total, goals_2h_total) of
goals_stretch.GOALS_STRETCH_MARKETS (or --markets), by Poisson
pseudo-likelihood (goals_stretch.fit_terms) on every row of the cached
history from --train-from to the day before --before, the centre as SHEET
builds it (measure_game_state.live_centre over bet.sofa.centre_replay - the
blend GAME_STATE multiplies), s the side's expected goal difference from the
rating's goals book (a total: the home side's, read off the match's
goals_for home row, as the 2026-10-17 measurement read it). By default the
offset carries the installed season-phase term (epochs.SEASON_PHASE is on
live, and the v2 per-phase measurement fitted on top of it; --season-phase
FILE reads another table, --no-season-phase leaves it out), and the rating
book learns the league strength in international club cups
(epochs.FOOTBALL_CUP_STRENGTH, on live since 2026-10-16;
config/sofa_cup_strength.json of the config dir, --cup-strength FILE another,
--no-cup-strength the plain book).

--per-phase MARKET[:PHASE,PHASE...] (rule goals_stretch_v2) also fits the
market once per season phase (season_phase.phases_by_event, a match with no
phase ``none``; every phase of supremacy_stretch.STRETCH_PHASES unless
listed) into its ``by_phase``; a phase with fewer than --min-phase-rows rows
gets no set (it reads the market's single one, which is always fitted too).
The 2026-10-17 measurement (fit before 2026): goals_for per phase in early /
mid / late / final - a match with no phase reads the single set (its own set
was worse, raw NB per-phase minus single +0.00018 [+0.00011, +0.00025]) -
goals_1h_for / goals_2h_for early only:
``--per-phase goals_for:early,mid,late,final goals_1h_for:early
goals_2h_for:early``. Dry run by default: prints the table; --write writes
the file atomically. The file is read only while
epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC is set (inert otherwise). Run it on
a COPY of the DB (CLAUDE.md, Changing the pipeline 4): the parsed history
pickle is kept in a cache/ directory next to --db-path.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_goals_stretch.py \\
        --before 2026-10-17 --db-path data/refit_<d>/sofa_replay.db \\
        --live-rules [--no-season-phase] [--no-cup-strength] \\
        [--markets goals_for ...] \\
        [--per-phase goals_for:early,mid,late,final goals_1h_for:early \\
         goals_2h_for:early] \\
        [--write [--out <file>]]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import centre_replay as cr  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import goals_stretch as gst  # noqa: E402
from bet.sofa import season_phase as sp  # noqa: E402
from bet.sofa import supremacy_stretch as ss  # noqa: E402
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.cup_strength import CupStrength  # noqa: E402
from bet.sofa.cup_strength import load as load_cup_strength  # noqa: E402
from scripts.sofa.measure_game_state import (  # noqa: E402
    CentreRules,
    _ts,
    add_rule_args,
    k_table,
    live_centre,
    rules_from_args,
)

# the side market whose home row carries a total's supremacy
HOME_SUPREMACY_MARKET = "goals_for"
# a phase cell is fitted only from this many rows (as season_phase's)
MIN_PHASE_ROWS = sp.MIN_FIT_ROWS


def parse_per_phase(specs: list[str], markets: list[str]) -> dict[str, tuple[str, ...]]:
    """--per-phase MARKET[:PHASE,...] -> market -> the phases to fit."""
    out: dict[str, tuple[str, ...]] = {}
    for spec in specs:
        market, _, raw = spec.partition(":")
        if market not in markets:
            raise ValueError(f"--per-phase {market}: not among --markets")
        phases = tuple(p for p in raw.split(",") if p) if raw else ss.STRETCH_PHASES
        bad = [p for p in phases if p not in ss.STRETCH_PHASES]
        if bad:
            raise ValueError(f"--per-phase {spec}: {bad} not in "
                             f"{list(ss.STRETCH_PHASES)}")
        out[market] = phases
    return out


def fit_by_phase(
    market: str, centres: list[float], sup: list[float], y: list[float],
    row_phases: list[str | None], phases: tuple[str, ...],
    min_rows: int = MIN_PHASE_ROWS,
) -> dict[str, dict[str, object]]:
    """phase -> its coefficient cell (with n_rows), fitted on the rows of
    that phase; a phase under ``min_rows`` rows is left out."""
    out: dict[str, dict[str, object]] = {}
    total = gst.is_total(market)
    for phase in phases:
        idx = [i for i, p in enumerate(row_phases) if ss.phase_key(p) == phase]
        if len(idx) < min_rows:
            continue
        coefs = gst.fit_terms(market, [centres[i] for i in idx],
                              [sup[i] for i in idx], [y[i] for i in idx])
        cell: dict[str, object] = dict(ss.cell_json(total, coefs))
        cell["n_rows"] = len(idx)
        out[phase] = cell
    return out


def collect(
    history: list[fr.FootballResult], train_from: str, last_day: str,
    markets: tuple[str, ...], rules: CentreRules,
    phases: dict[int, str | None] | None = None,
    phase_table: sp.SeasonPhaseTable | None = None,
    row_events: dict[str, list[int]] | None = None,
    cup_strength: CupStrength | None = None,
) -> dict[str, tuple[list[float], list[float], list[float], set[int]]]:
    """market -> (centres, supremacy, y, event ids) for every row with a
    supremacy. A total's s is the home side's from the same match's
    goals_for row (no such row: the total is left out). ``row_events``,
    when given, receives each market's per-row event ids (row order)."""
    walk_markets = tuple(sorted(set(markets) | {HOME_SUPREMACY_MARKET}))
    out: dict[str, tuple[list[float], list[float], list[float], set[int]]] = (
        defaultdict(lambda: ([], [], [], set())))
    home_sup: dict[int, float] = {}
    totals: list[tuple[str, int, float, float]] = []
    for row in cr.walk(history, _ts(train_from), _ts(last_day) + 86400,
                       walk_markets, k_table(walk_markets),
                       cup_strength=cup_strength):
        if (row.market == HOME_SUPREMACY_MARKET and row.side == "side_a"
                and row.supremacy is not None):
            home_sup[row.event_id] = row.supremacy
        if row.market not in markets:
            continue
        c = live_centre(row, rules)
        if phase_table is not None and phases is not None:
            c, _ = sp.apply(c, row.market, phases.get(row.event_id), phase_table)
        if gst.is_total(row.market):
            totals.append((row.market, row.event_id, c, row.y))
            continue
        if row.supremacy is None:
            continue
        cell = out[row.market]
        cell[0].append(c)
        cell[1].append(row.supremacy)
        cell[2].append(row.y)
        cell[3].add(row.event_id)
        if row_events is not None:
            row_events.setdefault(row.market, []).append(row.event_id)
    for market, event_id, c, y in totals:
        s = home_sup.get(event_id)
        if s is None:
            continue
        cell = out[market]
        cell[0].append(c)
        cell[1].append(s)
        cell[2].append(y)
        cell[3].add(event_id)
        if row_events is not None:
            row_events.setdefault(market, []).append(event_id)
    return out


def offset_tables(
    season_phase: str | None, no_season_phase: bool,
    cup_strength: str | None, no_cup_strength: bool,
) -> tuple[sp.SeasonPhaseTable | None, CupStrength | None]:
    """(the season-phase table the offset carries, the cup list the book
    learns from): the installed files by default, another file when named,
    None when opted out."""
    if no_season_phase and season_phase:
        raise ValueError("--season-phase and --no-season-phase")
    if no_cup_strength and cup_strength:
        raise ValueError("--cup-strength and --no-cup-strength")
    phase_table = (None if no_season_phase else sp.load_table(
        Path(season_phase) if season_phase else None))
    cup = (None if no_cup_strength else load_cup_strength(
        Path(cup_strength) if cup_strength else None))
    return phase_table, cup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--markets", nargs="+", default=list(gst.GOALS_STRETCH_MARKETS))
    ap.add_argument("--db-path", help="the DB (a copy) whose cached football "
                    "history is read; default SOFA_DB_PATH / data/sofa.db")
    ap.add_argument("--season-phase", default=None, metavar="FILE",
                    help="the season-phase table the offset carries (default "
                    "the installed config/sofa_season_phase.json)")
    ap.add_argument("--no-season-phase", action="store_true",
                    help="the offset without the season-phase term")
    ap.add_argument("--cup-strength", default=None, metavar="FILE",
                    help="the cup list the rating book learns from (default "
                    "the installed config/sofa_cup_strength.json)")
    ap.add_argument("--no-cup-strength", action="store_true",
                    help="the plain rating book, no cup league strength")
    ap.add_argument("--per-phase", nargs="+", default=[],
                    metavar="MARKET[:PHASE,...]",
                    help="also fit these markets per season phase (all "
                    "phases, or the listed ones) into by_phase")
    ap.add_argument("--min-phase-rows", type=int, default=MIN_PHASE_ROWS)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", help="default config/sofa_goals_stretch.json")
    add_rule_args(ap)
    ap.add_argument("--awarded-excluded", action="store_true",
                    help="football results awarded at the table (isAwarded) out of the "
                    "history, as SHEET from epochs.AWARDED_EXCLUDED_FROM_UTC")
    args = ap.parse_args()
    bad = [m for m in args.markets if m not in gst.GOALS_STRETCH_MARKETS]
    if bad:
        print(f"not goals-stretch markets: {bad}", file=sys.stderr)
        return 2
    try:
        per_phase = parse_per_phase(args.per_phase, args.markets)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    last_day = (date.fromisoformat(args.before) - timedelta(days=1)).isoformat()
    rules = rules_from_args(args, last_day)
    db = Path(args.db_path) if args.db_path else Path(SofaConfig.from_env().db_path)
    history = fr.load_history(db, db.parent / "cache")
    if args.awarded_excluded:
        history = fr.without_awarded(history)
    try:
        phase_table, cup = offset_tables(
            args.season_phase, args.no_season_phase, args.cup_strength,
            args.no_cup_strength)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    phases = (sp.phases_by_event(history)
              if phase_table is not None or per_phase else None)
    row_events: dict[str, list[int]] = {}
    rows = collect(history, args.train_from, last_day, tuple(args.markets),
                   rules, phases, phase_table, row_events, cup)
    del history
    markets: dict[str, dict[str, object]] = {}
    for m in args.markets:
        centres, sup, y, events = rows[m]
        coefs = gst.fit_terms(m, centres, sup, y)
        names = ("g1", "g2") if gst.is_total(m) else ("beta",)
        cell: dict[str, object] = {
            n: round(v, 6) for n, v in zip(names, coefs, strict=True)}
        cell.update({"n_rows": len(y), "n_matches": len(events)})
        if m in per_phase and phases is not None:
            by_phase = fit_by_phase(
                m, centres, sup, y,
                [phases.get(e) for e in row_events.get(m, [])],
                per_phase[m], args.min_phase_rows)
            if by_phase:
                cell["by_phase"] = by_phase
        markets[m] = cell
    doc = {
        "_doc": ("Goals stretch (epochs.FOOTBALL_GOALS_STRETCH): a football "
                 "goals centre x exp(beta x s) (goals_for / goals_1h_for / "
                 "goals_2h_for, s the side's expected goal difference) or "
                 "exp(g1 |s| + g2 s^2) (the totals, s the home side's); "
                 "by_phase: the set of a season phase (a phase absent reads "
                 "the market's single set). INERT "
                 "while epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC is None. "
                 "Written by scripts/sofa/fit_goals_stretch.py."),
        "fitted_from": {
            "awarded_excluded": bool(args.awarded_excluded),
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_from": args.train_from, "before": args.before,
            "db_path": str(db),
            "method": "Poisson pseudo-likelihood, log link, offset log centre",
            "centre_rules": rules.describe(),
            "season_phase": (None if phase_table is None
                             else phase_table.path or "in-memory"),
            "cup_strength": (None if cup is None else
                             args.cup_strength or "config/sofa_cup_strength.json"),
            "per_phase": {m: list(p) for m, p in per_phase.items()},
            "min_phase_rows": args.min_phase_rows,
            "evidence": gst.EVIDENCE,
        },
        "unfitted_constants": list(gst.GOALS_STRETCH_UNFITTED),
        "markets": markets,
    }
    gst.parse_table(doc)  # what is written must be readable
    text = json.dumps(doc, indent=2) + "\n"
    print(text)
    if args.write:
        target = Path(args.out) if args.out else config_path(gst.CONFIG_FILE)
        write_bytes_atomic(target, text.encode("utf-8"))
        print(f"wrote {target}")
    else:
        print("dry run: nothing written (--write to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
