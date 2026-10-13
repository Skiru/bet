"""Measure the game-state term (audit 2026-10-13 B1, epochs.GAME_STATE).

Pre-registered in docs/sofa/evidence/game_state_2026-10-13.md. One step ahead
on the cached football history (bet.sofa.centre_replay): a side's centre as
SHEET builds it (0.5 rating + 0.5 shrunk sample where the market is rated,
the sample alone for cards_points_for) against the same centre times
exp(beta_m x s), s the side's expected goal difference from the rating's
goals book. beta_m is fitted walk-forward: for every month of the window, on
the sides of matches strictly before that month's first day.

Primary metric: NB log-loss of the observed count (alpha from the installed
config/sofa_count_dispersion.json, market x competition), new minus old per
side, 95% from resampling matches (2000, seed 0). Secondary: squared error,
bias by role (favourite s > +0.5, even, outsider s < -0.5).

Read-only: writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_game_state.py \\
        [--from 2025-08-01] [--to 2026-10-12] [--train-from 2024-10-01] \\
        [--json-out <file>]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import centre_replay as cr  # noqa: E402
from bet.sofa import count_dispersion, epochs  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import game_state as gs  # noqa: E402
from bet.sofa import rating_weight as rw  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.per_market_k import k_for_market  # noqa: E402

ROLE_CUT = 0.5


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def _months(start: str, end: str) -> list[tuple[str, int, int]]:
    """(label, first ts, next month's first ts) covering [start, end]."""
    d = date.fromisoformat(start).replace(day=1)
    stop = date.fromisoformat(end) + timedelta(days=1)
    out = []
    while d < stop:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        lo = max(d, date.fromisoformat(start))
        out.append((d.strftime("%Y-%m"), _ts(lo.isoformat()),
                    _ts(min(nxt, stop).isoformat())))
        d = nxt
    return out


def k_table(markets: tuple[str, ...]) -> dict[str, float]:
    constants = json.loads(config_path("sofa_engine_constants.json").read_text())
    sport_k = float(constants["K_CENTRE"]["by_sport"]["football"])
    return {m: k_for_market(constants, "football", m, sport_k) for m in markets}


def _repo_relative(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(_REPO))
    except ValueError:
        return path


@dataclass(frozen=True)
class CentreRules:
    """Which SHEET rules the replayed centre follows. The default is the
    centre the installed betas were fitted on (2026-10-13 11:39Z): the 0.5
    blend outside UNRATED_MARKETS, the sample alone inside them."""

    # epochs.FOOTBALL_RATED_SCOPE (B2): markets of UNRATED_MARKETS rated anyway
    rated_scope: frozenset[str] = frozenset()
    # epochs.FOOTBALL_RATING_WEIGHT (B14): the per-market W (None = 0.5)
    rating_weights: rw.RatingWeightTable | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "rated_scope": sorted(self.rated_scope),
            "rating_weight": _repo_relative(self.rating_weights.path or "table")
            if self.rating_weights is not None else None,
        }


DEFAULT_RULES = CentreRules()


def rules_as_of(day: str, build_at: datetime | None = None,
                weight_path: Path | None = None) -> CentreRules:
    """The rules SHEET builds `day` with (as of `build_at`), from epochs:
    RATED_SCOPE_MARKETS rated while FOOTBALL_RATED_SCOPE is on, the fitted
    W table while FOOTBALL_RATING_WEIGHT is on."""
    scope = (fr.RATED_SCOPE_MARKETS
             if epochs.football_rated_scope(day, build_at) else frozenset())
    table = (rw.load_table(weight_path)
             if epochs.football_rating_weight(day, build_at) else None)
    return CentreRules(scope, table)


def live_centre(row: cr.CentreRow, rules: CentreRules = DEFAULT_RULES) -> float:
    """SHEET's centre: the rating blended in only where the market is rated
    (UNRATED_MARKETS outside ``rules.rated_scope`` keep the sample alone), at
    the market's W under ``rules.rating_weights`` (rating_weight.blend, the
    function SHEET calls), else W_FOOTBALL_RATING."""
    if row.rating is not None and (row.market not in fr.UNRATED_MARKETS
                                   or row.market in rules.rated_scope):
        return rw.blend(row.rating, row.sample, row.market, rules.rating_weights)
    return row.sample


def collect(history: list[fr.FootballResult], train_from: str, end: str,
            markets: tuple[str, ...], rules: CentreRules = DEFAULT_RULES,
            ) -> list[tuple[cr.CentreRow, float]]:
    """(row, live centre under `rules`) for every side with a supremacy."""
    out = []
    for row in cr.walk(history, _ts(train_from),
                       _ts(end) + 86400, markets, k_table(markets)):
        if row.supremacy is None:
            continue
        out.append((row, live_centre(row, rules)))
    return out


def role(s: float) -> str:
    return "fav" if s > ROLE_CUT else "out" if s < -ROLE_CUT else "even"


def measure(rows: list[tuple[cr.CentreRow, float]], start: str, end: str,
            table: count_dispersion.DispersionTable,
            fixed: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Walk-forward betas vs no term; with `fixed` (market -> beta, e.g. the
    installed table) also vs those betas held constant over the window."""
    out: dict[str, Any] = {}
    months = _months(start, end)
    for market in gs.GAME_STATE_MARKETS:
        mrows = [(r, c) for r, c in rows if r.market == market]
        betas: dict[str, float] = {}
        diff: dict[int, list[float]] = defaultdict(list)
        sub: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
        se = [0.0, 0.0, 0]
        bias: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        ll = [0.0, 0.0]
        fixed_beta = (fixed or {}).get(market)
        vs_fixed: dict[int, list[float]] = defaultdict(list)
        ll_fixed = 0.0
        for label, lo, hi in months:
            train = [(r, c) for r, c in mrows if r.ts < lo]
            beta = gs.fit_beta([c for _, c in train],
                               [r.supremacy or 0.0 for r, _ in train],
                               [r.y for r, _ in train])
            betas[label] = beta
            half = "2025-08..2026-02" if label < "2026-03" else "2026-03..2026-10"
            for r, c in mrows:
                if not lo <= r.ts < hi:
                    continue
                s = r.supremacy or 0.0
                new = c * math.exp(beta * gs.clamp_supremacy(s))
                disp = table.read("football", market, r.competition_id)
                alpha = disp.alpha if disp is not None else 0.0
                l_old = cr.nb_logloss(r.y, c, alpha)
                l_new = cr.nb_logloss(r.y, new, alpha)
                diff[r.event_id].append(l_new - l_old)
                if fixed_beta is not None:
                    l_fix = cr.nb_logloss(
                        r.y, c * math.exp(fixed_beta * gs.clamp_supremacy(s)), alpha)
                    vs_fixed[r.event_id].append(l_new - l_fix)
                    ll_fixed += l_fix
                sub[half][r.event_id].append(l_new - l_old)
                ll[0] += l_old
                ll[1] += l_new
                se[0] += (c - r.y) ** 2
                se[1] += (new - r.y) ** 2
                se[2] += 1
                b = bias[role(s)]
                b[0] += c - r.y
                b[1] += new - r.y
                b[2] += 1
        n = se[2]
        mean, lo95, hi95, sides, matches = cr.boot_by_group(diff)
        out[market] = {
            "d_logloss": [mean, lo95, hi95], "sides": sides, "matches": matches,
            "logloss_old": ll[0] / n if n else None,
            "logloss_new": ll[1] / n if n else None,
            "mse_old": se[0] / n if n else None, "mse_new": se[1] / n if n else None,
            "bias_by_role": {k: {"old": v[0] / v[2], "new": v[1] / v[2], "n": int(v[2])}
                             for k, v in sorted(bias.items())},
            "beta_by_month": betas,
            "halves": {h: list(cr.boot_by_group(g)) for h, g in sorted(sub.items())},
        }
        if fixed_beta is not None:
            fm, flo, fhi, _, _ = cr.boot_by_group(vs_fixed)
            out[market]["fixed_beta"] = fixed_beta
            out[market]["logloss_fixed"] = ll_fixed / n if n else None
            out[market]["d_logloss_vs_fixed"] = [fm, flo, fhi]
        print(market, json.dumps(out[market]), flush=True)
    return out


def add_rule_args(ap: argparse.ArgumentParser) -> None:
    """The centre-rule options shared with fit_game_state.py. None given: the
    default centre (DEFAULT_RULES), unchanged."""
    ap.add_argument("--rated-scope", action="store_true",
                    help="rate football_rating.RATED_SCOPE_MARKETS (B2)")
    ap.add_argument("--rating-weight", nargs="?", const="installed",
                    help="per-market W (B14) from this file (default "
                    "config/sofa_rating_weight.json)")
    ap.add_argument("--live-rules", action="store_true",
                    help="follow epochs: the rules SHEET builds the last day "
                    "of the window with, as of the following 00:00Z")


def rules_from_args(args: argparse.Namespace, last_day: str) -> CentreRules:
    weight_path = (Path(args.rating_weight)
                   if args.rating_weight not in (None, "installed") else None)
    if args.live_rules:
        if args.rated_scope or args.rating_weight:
            raise SystemExit("--live-rules excludes --rated-scope / --rating-weight")
        at = datetime.fromisoformat(last_day).replace(tzinfo=UTC) + timedelta(days=1)
        return rules_as_of(last_day, at, weight_path)
    return CentreRules(
        fr.RATED_SCOPE_MARKETS if args.rated_scope else frozenset(),
        rw.load_table(weight_path) if args.rating_weight else None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-08-01")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--json-out")
    add_rule_args(ap)
    ap.add_argument("--compare-betas", nargs="?", const="installed",
                    help="also compare against a fixed beta table (default: the "
                    "installed config/sofa_game_state.json)")
    args = ap.parse_args()
    rules = rules_from_args(args, args.end)
    print(f"centre rules {json.dumps(rules.describe())}", flush=True)
    db = SofaConfig.from_env().db_path
    history = fr.load_history(db, Path(db).parent / "cache")
    rows = collect(history, args.train_from, args.end, gs.GAME_STATE_MARKETS, rules)
    print(f"rows {len(rows)}", flush=True)
    fixed = None
    if args.compare_betas:
        fixed = dict(gs.load_table(
            None if args.compare_betas == "installed"
            else Path(args.compare_betas)).betas)
    result = measure(rows, args.start, args.end, count_dispersion.load_table(), fixed)
    result["_centre_rules"] = rules.describe()
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
