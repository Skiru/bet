"""Fit the season-phase coefficients (audit 2026-10-13 C1) into
config/sofa_season_phase.json.

c[market][phase] per market of season_phase.SEASON_PHASE_MARKETS (or
--markets) by season_phase.fit_coefficients on every row of the cached
history from --train-from to the day before --before, the centre as SHEET
builds it (measure_season_phase.live_centre over bet.sofa.centre_replay), the
phase as of each kickoff (season_phase.phases_by_event). Dry run by default:
prints the table; --write writes the file atomically. The file is read only
while epochs.SEASON_PHASE_FROM_UTC is set (inert otherwise).

    SOFA_DB_PATH=... PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/fit_season_phase.py --before 2026-10-13 \\
        [--markets goals_for goals_total] [--write] [--out <file>]
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

from bet.sofa import season_phase as sp  # noqa: E402
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from scripts.sofa.measure_season_phase import (  # noqa: E402
    collect,
    live_centre,
    load_history,
)

EVIDENCE = "docs/sofa/evidence/season_phase_2026-10-13.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--train-from", default="2024-10-01")
    ap.add_argument("--markets", nargs="+", default=list(sp.SEASON_PHASE_MARKETS))
    ap.add_argument("--history", help="the parsed history pickle (read-only)")
    ap.add_argument("--awarded-excluded", action="store_true", help=(
        "results awarded at the table out of the history (epochs."
        "AWARDED_EXCLUDED, SHEET from 2026-10-30)"))
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", help="default config/sofa_season_phase.json")
    args = ap.parse_args()
    bad = [m for m in args.markets if m not in sp.SEASON_PHASE_MARKETS]
    if bad:
        print(f"not season-phase markets: {bad}", file=sys.stderr)
        return 2
    last_day = (date.fromisoformat(args.before) - timedelta(days=1)).isoformat()
    history = load_history(Path(args.history) if args.history else None,
                           awarded_out=args.awarded_excluded)
    phases = sp.phases_by_event(history)
    rows = collect(history, args.train_from, last_day, args.markets)
    del history
    markets = {}
    for m in args.markets:
        r = rows[m]
        labels = [phases.get(int(e)) for e in r.event]
        coefs = sp.fit_coefficients(live_centre(r, m).tolist(), r.y.tolist(), labels)
        markets[m] = {
            "coefficients": {k: round(v, 6) for k, v in coefs.items()},
            "n_rows": int(len(r.y)),
            "n_rows_by_phase": {p: sum(1 for x in labels if x == p)
                                for p in sp.PHASES},
        }
    doc = {
        "_doc": ("Season-phase coefficients (audit 2026-10-13 C1): a football "
                 "goals centre x exp(c[market][phase]), mid-season 0. INERT "
                 "while epochs.SEASON_PHASE_FROM_UTC is None. Written by "
                 "scripts/sofa/fit_season_phase.py."),
        "fitted_from": {
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_from": args.train_from, "before": args.before,
            "awarded_excluded": bool(args.awarded_excluded),
            "method": ("per phase log(sum y / sum centre) minus mid-season's; "
                       "centre = W_FOOTBALL_RATING blend (centre_replay)"),
            "evidence": EVIDENCE,
        },
        "unfitted_constants": list(sp.SEASON_PHASE_UNFITTED),
        "markets": markets,
    }
    sp.parse_table(doc)  # what is written must be readable
    text = json.dumps(doc, indent=2) + "\n"
    print(text)
    if args.write:
        target = Path(args.out) if args.out else config_path(sp.CONFIG_FILE)
        write_bytes_atomic(target, text.encode("utf-8"))
        print(f"wrote {target}")
    else:
        print("dry run: nothing written (--write to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
