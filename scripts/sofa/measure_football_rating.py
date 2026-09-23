"""Reprint the evidence behind bet.sofa.football_rating.ALPHA_BY_METRIC.

One-step-ahead squared error per side, on cached history strictly before
``--cut``, for three forecasts of what a side produces in its next match:

  * last-10 - the mean of the side's own last ten values (what a raw sample is);
  * league  - the league's running per-side rate, home and away separately;
  * rating  - league rate x attack x opponent defence, at each ALPHA tried.

An analysis tool: it writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_rating.py \\
        --from 2026-06-01 --cut 2026-09-17
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import UTC, datetime

from bet.sofa import football_rating as fr
from bet.sofa.config import SofaConfig

ALPHAS = (0.01, 0.02, 0.03, 0.04, 0.05, 0.08)


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def evaluate(
    history: list[fr.FootballResult], alpha: float, start: int, cut: int
) -> dict[str, list[float]]:
    """metric -> [rating SSE, last-10 SSE, league SSE, n]."""
    saved = dict(fr.ALPHA_BY_METRIC)
    fr.ALPHA_BY_METRIC.update({m: alpha for m in fr.BASE_METRICS})
    try:
        book = fr.RatingBook()
        last: dict[tuple[int, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=10)
        )
        err: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        for r in history:
            if r.ts >= cut:
                break
            if r.ts >= start:
                for m, (vh, va) in r.values.items():
                    exp = book.expected(r.competition_id, r.home_id, r.away_id, m)
                    rates = book.league_rates(r.competition_id, m)
                    lh, la = last[(r.home_id, m)], last[(r.away_id, m)]
                    if (
                        exp is None or rates is None
                        or book.team_matches(r.home_id, m) < fr.MIN_TEAM_MATCHES
                        or book.team_matches(r.away_id, m) < fr.MIN_TEAM_MATCHES
                        or len(lh) < 5 or len(la) < 5
                    ):
                        continue
                    bh, ba = sum(lh) / len(lh), sum(la) / len(la)
                    e = err[m]
                    e[0] += (exp[0] - vh) ** 2 + (exp[1] - va) ** 2
                    e[1] += (bh - vh) ** 2 + (ba - va) ** 2
                    e[2] += (rates[0] - vh) ** 2 + (rates[1] - va) ** 2
                    e[3] += 2
            for m, (vh, va) in r.values.items():
                last[(r.home_id, m)].append(vh)
                last[(r.away_id, m)].append(va)
            book.update(r)
        return err
    finally:
        fr.ALPHA_BY_METRIC.clear()
        fr.ALPHA_BY_METRIC.update(saved)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", default="2026-06-01")
    parser.add_argument("--cut", default="2026-09-17")
    args = parser.parse_args()
    history = fr.load_history(SofaConfig.from_env().db_path)
    start, cut = _ts(args.start), _ts(args.cut)
    results = {a: evaluate(history, a, start, cut) for a in ALPHAS}
    first = results[ALPHAS[0]]
    print(f"{'metric':24s} {'n':>7s} {'last10':>8s} {'league':>8s} "
          + " ".join(f"a={a:<6g}" for a in ALPHAS) + "  shipped")
    for m in sorted(first):
        n = first[m][3]
        cells = " ".join(f"{results[a][m][0] / n:8.3f}" for a in ALPHAS)
        print(f"{m:24s} {int(n):7d} {first[m][1] / n:8.3f} {first[m][2] / n:8.3f} "
              f"{cells}  {fr.ALPHA_BY_METRIC.get(m)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
