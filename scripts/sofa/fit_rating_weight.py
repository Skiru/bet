"""Fit the football rating's weight per market (audit 2026-10-13 B14) into
config/sofa_rating_weight.json.

W per market of --markets (no default: the markets whose walk-forward
measurement met the registered threshold) by rating_weight.fit_weight's rule
(the W_GRID point of the lowest mean NB log-loss; vectorised as in
measure_rating_weight, checked against fit_weight on a sample) on every rated
row of the cached history from --train-from to the day before --before. Dry
run by default; --write writes the file atomically. The file is read only
while epochs.FOOTBALL_RATING_WEIGHT_FROM_UTC is set (inert otherwise).

    SOFA_DB_PATH=... PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/fit_rating_weight.py --before 2026-10-13 \\
        --markets goals_for ... [--write] [--out <file>]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import rating_weight as rw  # noqa: E402
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from scripts.sofa.measure_rating_weight import (  # noqa: E402
    check_fit_rule,
    loss_grid,
    rated_markets,
)
from scripts.sofa.measure_season_phase import collect, load_history  # noqa: E402

EVIDENCE = "docs/sofa/evidence/rating_weight_2026-10-13.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--markets", nargs="+", required=True)
    ap.add_argument("--history", help="the parsed history pickle (read-only)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", help="default config/sofa_rating_weight.json")
    args = ap.parse_args()
    allowed = set(rated_markets(fr.RATED_SCOPE_MARKETS))
    bad = [m for m in args.markets if m not in allowed]
    if bad:
        print(f"not rated football markets: {bad}", file=sys.stderr)
        return 2
    last_day = (date.fromisoformat(args.before) - timedelta(days=1)).isoformat()
    history = load_history(Path(args.history) if args.history else None)
    rows = collect(history, args.train_from, last_day, args.markets)
    del history
    tie = np.array([abs(w - fr.W_FOOTBALL_RATING) for w in rw.W_GRID])
    markets = {}
    for m in args.markets:
        check_fit_rule(rows[m])
        r = rows[m].subset(np.isfinite(rows[m].rating))
        mean = loss_grid(r).mean(axis=1)
        w = rw.W_GRID[int(np.lexsort((tie, mean))[0])]
        markets[m] = {"w": w, "n_rows": int(len(r.y)),
                      "n_matches": int(len(np.unique(r.event))),
                      "logloss_at_w": float(mean.min()),
                      "logloss_at_0.5": float(mean[rw.W_GRID.index(0.5)])}
    doc = {
        "_doc": ("Football rating weight per market (audit 2026-10-13 B14): "
                 "centre = w x rating + (1 - w) x shrunk sample. INERT while "
                 "epochs.FOOTBALL_RATING_WEIGHT_FROM_UTC is None; a market "
                 "absent here keeps W_FOOTBALL_RATING. Written by "
                 "scripts/sofa/fit_rating_weight.py."),
        "fitted_from": {
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_from": args.train_from, "before": args.before,
            "method": "grid 0..1 step 0.05, lowest mean NB log-loss of the centre",
            "evidence": EVIDENCE,
        },
        "markets": markets,
    }
    rw.parse_table(doc)
    text = json.dumps(doc, indent=2) + "\n"
    print(text)
    if args.write:
        target = Path(args.out) if args.out else config_path(rw.CONFIG_FILE)
        write_bytes_atomic(target, text.encode("utf-8"))
        print(f"wrote {target}")
    else:
        print("dry run: nothing written (--write to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
