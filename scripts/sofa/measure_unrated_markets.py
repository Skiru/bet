"""Measure the rating and the venue multiplier on football_rating.UNRATED_MARKETS
(audit 2026-10-13 B2, epochs.FOOTBALL_RATED_SCOPE / FOOTBALL_VENUE_PRIOR).

Pre-registered in docs/sofa/evidence/unrated_markets_2026-10-13.md. One step
ahead on the cached football history (bet.sofa.centre_replay), per row (a
side for ``_for``, the match for ``_total``):

  * A - the centre SHEET prints today: the shrunk sample alone;
  * R - 0.5 x the rating (attack x defence x league strength, as
    FootballForecast.centre) + 0.5 x A, where both teams are rated;
  * V - A x the league's home / away multiplier (``_for`` only).

Metric: NB log-loss of the observed count (alpha from the installed
config/sofa_count_dispersion.json), variant minus A per row, 95% from
resampling matches (2000, seed 0); squared error and the rating alone (W = 1)
as secondary numbers. Reported over the whole window and the sub-windows
outside the one ALPHA_BY_METRIC was chosen on (2026-06-01..09-16).

Read-only: writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_unrated_markets.py \\
        [--from 2025-08-01] [--to 2026-10-12] [--json-out <file>]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import centre_replay as cr  # noqa: E402
from bet.sofa import count_dispersion  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.measure_game_state import k_table  # noqa: E402

MARKETS: tuple[str, ...] = tuple(sorted(fr.UNRATED_MARKETS))
# (label, from, to inclusive): the whole window and its parts; "choice" is
# where ALPHA_BY_METRIC was picked, the two others lie outside it.
WINDOWS = (
    ("pre", "2025-08-01", "2026-05-31"),
    ("choice", "2026-06-01", "2026-09-16"),
    ("post", "2026-09-17", "2026-10-12"),
)


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def _window(ts: int, start: str, end: str) -> list[str]:
    labels = ["all"] if _ts(start) <= ts < _ts(end) + 86400 else []
    labels += [lab for lab, lo, hi in WINDOWS
               if _ts(lo) <= ts < _ts(hi) + 86400]
    return labels


def measure(history: list[fr.FootballResult], start: str, end: str,
            table: count_dispersion.DispersionTable) -> dict[str, Any]:
    # market -> variant -> window -> event -> diffs
    diff: dict[str, dict[str, dict[str, dict[int, list[float]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    se: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in cr.walk(history, _ts(start), _ts(end) + 86400, MARKETS,
                       k_table(MARKETS)):
        disp = table.read("football", row.market, row.competition_id)
        alpha = disp.alpha if disp is not None else 0.0
        base = cr.nb_logloss(row.y, row.sample, alpha)
        variants: dict[str, float] = {}
        if row.rating is not None:
            variants["R"] = fr.W_FOOTBALL_RATING * row.rating + (
                1 - fr.W_FOOTBALL_RATING) * row.sample
            variants["R1"] = row.rating
        if row.venue_mult is not None:
            variants["V"] = row.sample * row.venue_mult
        windows = _window(row.ts, start, end)
        for name, centre in variants.items():
            d = cr.nb_logloss(row.y, centre, alpha) - base
            for w in windows:
                diff[row.market][name][w][row.event_id].append(d)
            if "all" in windows:
                s = se[(row.market, name)]
                s[0] += (row.sample - row.y) ** 2 - (centre - row.y) ** 2
                s[1] += 1
                se[(row.market, "A_" + name)][0] += (row.sample - row.y) ** 2
                se[(row.market, "A_" + name)][1] += 1
    out: dict[str, Any] = {}
    for market in MARKETS:
        out[market] = {}
        for name, by_w in sorted(diff[market].items()):
            cell: dict[str, Any] = {}
            for w, groups in sorted(by_w.items()):
                m, lo, hi, n, g = cr.boot_by_group(groups)
                cell[w] = {"d_logloss": [m, lo, hi], "rows": n, "matches": g}
            s, a = se[(market, name)], se[(market, "A_" + name)]
            if s[1]:
                cell["mse_A"] = a[0] / a[1]
                cell["mse_variant"] = (a[0] - s[0]) / s[1]
            out[market][name] = cell
        print(market, json.dumps(out[market]), flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-08-01")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    db = SofaConfig.from_env().db_path
    history = fr.load_history(db, Path(db).parent / "cache")
    result = measure(history, args.start, args.end, count_dispersion.load_table())
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
