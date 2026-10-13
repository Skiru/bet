"""Fit the game-state betas (audit 2026-10-13 B1) into config/sofa_game_state.json.

beta_m per market of game_state.GAME_STATE_MARKETS (or --markets), by Poisson
pseudo-likelihood on every side of the cached history from --train-from to
the day before --before, centre as SHEET builds it
(measure_game_state.live_centre over bet.sofa.centre_replay). Dry run by
default: prints the table; --write writes the file atomically. The file is
read only while epochs.GAME_STATE_FROM_UTC is set (inert otherwise).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_game_state.py \\
        --before 2026-10-13 [--markets corners_for ...] [--write]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import game_state as gs  # noqa: E402
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from scripts.sofa.measure_game_state import collect  # noqa: E402

EVIDENCE = "docs/sofa/evidence/game_state_2026-10-13.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--markets", nargs="+", default=list(gs.GAME_STATE_MARKETS))
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", help="default config/sofa_game_state.json")
    args = ap.parse_args()
    bad = [m for m in args.markets if m not in gs.GAME_STATE_MARKETS]
    if bad:
        print(f"not game-state markets: {bad}", file=sys.stderr)
        return 2
    last_day = (date.fromisoformat(args.before) - timedelta(days=1)).isoformat()
    db = SofaConfig.from_env().db_path
    history = fr.load_history(db, Path(db).parent / "cache")
    rows = collect(history, args.train_from, last_day, tuple(args.markets))
    markets = {}
    for m in args.markets:
        mrows = [(r, c) for r, c in rows if r.market == m]
        beta = gs.fit_beta([c for _, c in mrows],
                           [r.supremacy or 0.0 for r, _ in mrows],
                           [r.y for r, _ in mrows])
        markets[m] = {"beta": round(beta, 6), "n_sides": len(mrows),
                      "n_matches": len({r.event_id for r, _ in mrows})}
    doc = {
        "_doc": ("Game-state betas (audit 2026-10-13 B1): a football side's centre "
                 "x exp(beta x its expected goal difference). INERT while "
                 "epochs.GAME_STATE_FROM_UTC is None. Written by "
                 "scripts/sofa/fit_game_state.py."),
        "fitted_from": {
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_from": args.train_from, "before": args.before,
            "method": "Poisson pseudo-likelihood, log link, offset log centre",
            "evidence": EVIDENCE,
        },
        "unfitted_constants": list(gs.GAME_STATE_UNFITTED),
        "markets": markets,
    }
    gs.parse_table(doc)  # what is written must be readable
    text = json.dumps(doc, indent=2) + "\n"
    print(text)
    if args.write:
        target = Path(args.out) if args.out else config_path(gs.CONFIG_FILE)
        write_bytes_atomic(target, text.encode("utf-8"))
        print(f"wrote {target}")
    else:
        print("dry run: nothing written (--write to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
