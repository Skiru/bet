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
goals_for home row, as the 2026-10-17 measurement read it). With
--season-phase the offset also carries the installed season-phase term
(epochs.SEASON_PHASE is on live; the measurement ran without it). Dry run by
default: prints the table; --write writes the file atomically. The file is
read only while epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC is set (inert
otherwise). Run it on a COPY of the DB (CLAUDE.md, Changing the pipeline 4):
the parsed history pickle is kept in a cache/ directory next to --db-path.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_goals_stretch.py \\
        --before 2026-10-17 --db-path data/refit_<d>/sofa_replay.db \\
        [--live-rules] [--season-phase] [--markets goals_for ...] \\
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
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
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


def collect(
    history: list[fr.FootballResult], train_from: str, last_day: str,
    markets: tuple[str, ...], rules: CentreRules,
    phases: dict[int, str | None] | None = None,
    phase_table: sp.SeasonPhaseTable | None = None,
) -> dict[str, tuple[list[float], list[float], list[float], set[int]]]:
    """market -> (centres, supremacy, y, event ids) for every row with a
    supremacy. A total's s is the home side's from the same match's
    goals_for row (no such row: the total is left out)."""
    walk_markets = tuple(sorted(set(markets) | {HOME_SUPREMACY_MARKET}))
    out: dict[str, tuple[list[float], list[float], list[float], set[int]]] = (
        defaultdict(lambda: ([], [], [], set())))
    home_sup: dict[int, float] = {}
    totals: list[tuple[str, int, float, float]] = []
    for row in cr.walk(history, _ts(train_from), _ts(last_day) + 86400,
                       walk_markets, k_table(walk_markets)):
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
    for market, event_id, c, y in totals:
        s = home_sup.get(event_id)
        if s is None:
            continue
        cell = out[market]
        cell[0].append(c)
        cell[1].append(s)
        cell[2].append(y)
        cell[3].add(event_id)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--markets", nargs="+", default=list(gst.GOALS_STRETCH_MARKETS))
    ap.add_argument("--db-path", help="the DB (a copy) whose cached football "
                    "history is read; default SOFA_DB_PATH / data/sofa.db")
    ap.add_argument("--season-phase", nargs="?", const="installed",
                    help="the offset also carries the season-phase term from "
                    "this file (default config/sofa_season_phase.json)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", help="default config/sofa_goals_stretch.json")
    add_rule_args(ap)
    args = ap.parse_args()
    bad = [m for m in args.markets if m not in gst.GOALS_STRETCH_MARKETS]
    if bad:
        print(f"not goals-stretch markets: {bad}", file=sys.stderr)
        return 2
    last_day = (date.fromisoformat(args.before) - timedelta(days=1)).isoformat()
    rules = rules_from_args(args, last_day)
    db = Path(args.db_path) if args.db_path else Path(SofaConfig.from_env().db_path)
    history = fr.load_history(db, db.parent / "cache")
    phase_table = (
        sp.load_table(None if args.season_phase == "installed"
                      else Path(args.season_phase))
        if args.season_phase else None)
    phases = sp.phases_by_event(history) if phase_table is not None else None
    rows = collect(history, args.train_from, last_day, tuple(args.markets),
                   rules, phases, phase_table)
    del history
    markets: dict[str, dict[str, object]] = {}
    for m in args.markets:
        centres, sup, y, events = rows[m]
        coefs = gst.fit_terms(m, centres, sup, y)
        names = ("g1", "g2") if gst.is_total(m) else ("beta",)
        cell: dict[str, object] = {
            n: round(v, 6) for n, v in zip(names, coefs, strict=True)}
        cell.update({"n_rows": len(y), "n_matches": len(events)})
        markets[m] = cell
    doc = {
        "_doc": ("Goals stretch (epochs.FOOTBALL_GOALS_STRETCH): a football "
                 "goals centre x exp(beta x s) (goals_for / goals_1h_for / "
                 "goals_2h_for, s the side's expected goal difference) or "
                 "exp(g1 |s| + g2 s^2) (the totals, s the home side's). INERT "
                 "while epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC is None. "
                 "Written by scripts/sofa/fit_goals_stretch.py."),
        "fitted_from": {
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_from": args.train_from, "before": args.before,
            "db_path": str(db),
            "method": "Poisson pseudo-likelihood, log link, offset log centre",
            "centre_rules": rules.describe(),
            "season_phase": (None if phase_table is None
                             else phase_table.path or "in-memory"),
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
