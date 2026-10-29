"""Fit the closeness-stretch coefficients (epochs.FOOTBALL_CLOSENESS_STRETCH)
into config/sofa_closeness_stretch.json.

For every market of closeness_stretch.CLOSENESS_MARKETS (or --markets) the
coefficients of exp(g1 |s| [+ g2 s^2]) - as many terms as
closeness_stretch.CLOSENESS_TERMS says - by Poisson pseudo-likelihood, log
link, offset log of the LIVE centre (supremacy_stretch.fit_terms, total
form), on every row of the replayed history from --train-from (default
2026-01-01: the mature rating book) to the day before --before.

The centre is fit_count_stretch.walk's one-step-ahead count centre (SHEET's:
last 10 values, B15 opponent correction, market K shrink to the league rate,
rating blend where rated, the cup-strength book by default), times the
terms SHEET applies before this one: GAME_STATE's exp(beta s) of
config/sofa_game_state.json (cards_points_for) and the count stretch of
config/sofa_count_stretch.json where the market has one - g is fitted ON
TOP of them, never in their place. s is the home side's expected goal
difference (|s| and s^2 are even), clamped at game_state.MAX_SUPREMACY.

Dry run by default: prints the table; --write writes the file atomically.
The file is read only while epochs.FOOTBALL_CLOSENESS_STRETCH_FROM_UTC is
set (inert otherwise). Read-only on the DB; the parsed history pickle is
kept in --cache-dir (default cache/ next to --db-path) - point it at a
scratch directory when --db-path is the live DB.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_closeness_stretch.py \\
        --before 2026-10-21 --db-path data/refit_<d>/sofa_replay.db \\
        --live-rules [--cache-dir <scratch>] [--train-from 2026-01-01] \\
        [--write [--out <file>]]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import closeness_stretch as cls  # noqa: E402
from bet.sofa import count_stretch as cst  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import supremacy_stretch as ss  # noqa: E402
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.cup_strength import load as load_cup_strength  # noqa: E402
from bet.sofa.game_state import GameStateTable  # noqa: E402
from bet.sofa.game_state import load_table as load_game_state  # noqa: E402
from scripts.sofa.fit_count_stretch import StretchRow, walk  # noqa: E402
from scripts.sofa.measure_game_state import (  # noqa: E402
    _ts,
    add_rule_args,
    k_table,
    rules_from_args,
)

DEFAULT_TRAIN_FROM = "2026-01-01"


def _repo_relative(path: str | None) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(_REPO))
    except ValueError:
        return path


def live_offset(row: StretchRow, game_state: GameStateTable,
                count_stretch: cst.CountStretchTable | None) -> float:
    """The walk's centre x the terms SHEET applies before the closeness
    term: GAME_STATE (a side) and the count stretch (where the market has
    coefficients). The walk's ``supremacy`` is the side's (a total: the
    home side's), as both terms read it."""
    centre = row.centre
    if row.side:
        g = game_state.multiplier(row.market, row.supremacy)
        if g is not None:
            centre *= g
    if count_stretch is not None:
        c = count_stretch.multiplier(row.market, row.supremacy)
        if c is not None:
            centre *= c
    return centre


def fit_rows(rows: Iterable[StretchRow], markets: Sequence[str],
             game_state: GameStateTable,
             count_stretch: cst.CountStretchTable | None,
             terms: Mapping[str, int] | None = None,
             ) -> dict[str, dict[str, object]]:
    """market -> its file cell (g1, g2, n_rows, n_matches)."""
    terms = terms if terms is not None else cls.CLOSENESS_TERMS
    cols: dict[str, tuple[list[float], list[float], list[float], set[int]]] = {
        m: ([], [], [], set()) for m in markets}
    for row in rows:
        cell = cols.get(row.market)
        if cell is None:
            continue
        cell[0].append(live_offset(row, game_state, count_stretch))
        cell[1].append(row.supremacy)  # |s| and s^2: the side's = the home's
        cell[2].append(row.y)
        cell[3].add(row.event_id)
    out: dict[str, dict[str, object]] = {}
    for m in markets:
        centres, sup, y, events = cols[m]
        coefs = ss.fit_terms(True, centres, sup, y, terms[m])
        cell_out: dict[str, object] = dict(ss.cell_json(True, coefs))
        cell_out.update({"n_rows": len(y), "n_matches": len(events)})
        out[m] = cell_out
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--train-from", default=DEFAULT_TRAIN_FROM)
    ap.add_argument("--markets", nargs="+", default=list(cls.CLOSENESS_MARKETS))
    ap.add_argument("--db-path", help="the DB whose cached football history "
                    "is read (read-only); default SOFA_DB_PATH / data/sofa.db")
    ap.add_argument("--cache-dir", help="where the parsed history pickle is "
                    "kept (default cache/ next to --db-path)")
    ap.add_argument("--cup-strength", default=None, metavar="FILE")
    ap.add_argument("--no-cup-strength", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", help="default config/sofa_closeness_stretch.json")
    add_rule_args(ap)
    ap.add_argument("--awarded-excluded", action="store_true",
                    help="football results awarded at the table (isAwarded) out of the "
                    "history, as SHEET from epochs.AWARDED_EXCLUDED_FROM_UTC")
    args = ap.parse_args()
    bad = [m for m in args.markets if m not in cls.CLOSENESS_MARKETS]
    if bad:
        print(f"not closeness-stretch markets: {bad}", file=sys.stderr)
        return 2
    if args.no_cup_strength and args.cup_strength:
        print("--cup-strength and --no-cup-strength", file=sys.stderr)
        return 2
    cup = (None if args.no_cup_strength else load_cup_strength(
        Path(args.cup_strength) if args.cup_strength else None))
    markets = tuple(args.markets)
    last_day = (date.fromisoformat(args.before) - timedelta(days=1)).isoformat()
    rules = rules_from_args(args, last_day)
    db = Path(args.db_path) if args.db_path else Path(SofaConfig.from_env().db_path)
    cache = Path(args.cache_dir) if args.cache_dir else db.parent / "cache"
    history = fr.load_history(db, cache)
    if args.awarded_excluded:
        history = fr.without_awarded(history)
    game_state = load_game_state()
    count_stretch = cst.load_table()
    table = fit_rows(walk(history, _ts(args.train_from), _ts(last_day) + 86400,
                          markets, k_table(markets), rules, cup_strength=cup),
                     markets, game_state, count_stretch)
    del history
    doc = {
        "_doc": ("Closeness stretch (epochs.FOOTBALL_CLOSENESS_STRETCH): a "
                 "football count centre x exp(g1 |s| + g2 s^2), s the home "
                 "side's expected goal difference, after GAME_STATE / the "
                 "count stretch. INERT while "
                 "epochs.FOOTBALL_CLOSENESS_STRETCH_FROM_UTC is None. Written "
                 "by scripts/sofa/fit_closeness_stretch.py."),
        "fitted_from": {
            "awarded_excluded": bool(args.awarded_excluded),
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_from": args.train_from, "before": args.before,
            "db_path": str(db),
            "method": ("Poisson pseudo-likelihood, log link, offset log of the "
                       "live centre (walk centre x GAME_STATE x count stretch)"),
            "centre": ("one-step-ahead count centre: last 10 values, B15 "
                       "opponent correction, market K shrink to the league "
                       "rate, rating blend where rated"),
            "centre_rules": rules.describe(),
            "offset_terms": {
                "game_state": _repo_relative(game_state.path),
                "count_stretch": _repo_relative(count_stretch.path)},
            "cup_strength": (None if cup is None else
                             args.cup_strength or "config/sofa_cup_strength.json"),
            "terms": {m: cls.CLOSENESS_TERMS[m] for m in markets},
            "evidence": cls.EVIDENCE,
        },
        "unfitted_constants": list(cls.CLOSENESS_UNFITTED),
        "markets": table,
    }
    cls.parse_table(doc)  # what is written must be readable
    text = json.dumps(doc, indent=2) + "\n"
    print(text)
    if args.write:
        target = Path(args.out) if args.out else config_path(cls.CONFIG_FILE)
        write_bytes_atomic(target, text.encode("utf-8"))
        print(f"wrote {target}")
    else:
        print("dry run: nothing written (--write to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
