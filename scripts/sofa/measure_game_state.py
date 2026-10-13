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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import centre_replay as cr  # noqa: E402
from bet.sofa import count_dispersion  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import game_state as gs  # noqa: E402
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


def live_centre(row: cr.CentreRow) -> float:
    """SHEET's centre today: the rating blended in only where the market is
    rated (cards_points_for is UNRATED: the sample alone)."""
    if row.rating is not None and row.market not in fr.UNRATED_MARKETS:
        return fr.W_FOOTBALL_RATING * row.rating + (
            1 - fr.W_FOOTBALL_RATING) * row.sample
    return row.sample


def collect(history: list[fr.FootballResult], train_from: str, end: str,
            markets: tuple[str, ...]) -> list[tuple[cr.CentreRow, float]]:
    """(row, live centre) for every side with a supremacy."""
    out = []
    for row in cr.walk(history, _ts(train_from),
                       _ts(end) + 86400, markets, k_table(markets)):
        if row.supremacy is None:
            continue
        out.append((row, live_centre(row)))
    return out


def role(s: float) -> str:
    return "fav" if s > ROLE_CUT else "out" if s < -ROLE_CUT else "even"


def measure(rows: list[tuple[cr.CentreRow, float]], start: str, end: str,
            table: count_dispersion.DispersionTable) -> dict[str, Any]:
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
        print(market, json.dumps(out[market]), flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-08-01")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    db = SofaConfig.from_env().db_path
    history = fr.load_history(db, Path(db).parent / "cache")
    rows = collect(history, args.train_from, args.end, gs.GAME_STATE_MARKETS)
    print(f"rows {len(rows)}", flush=True)
    result = measure(rows, args.start, args.end, count_dispersion.load_table())
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
