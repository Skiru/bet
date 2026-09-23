"""Fit the tennis rating's calibration layer into config/tennis_rating.json.

Outside the pipeline sequence on purpose, like fit_constants.py: re-fitting
mid-day would change how every tennis row of the day is priced between two
runs of SHEET. Run it deliberately, with a cut that is strictly before any day
the result will be used on, and say so in the commit.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_tennis_rating.py --cut 2026-09-17
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from bet.sofa.config import SofaConfig
from bet.sofa.tennis_rating import (
    DEFAULT_CONFIG,
    FEATURES,
    MIN_RATED,
    NEIGHBOURS,
    fit_coefficients,
    load_history,
    replay,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cut", required=True, help="YYYY-MM-DD, exclusive")
    parser.add_argument("--out", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    cut = datetime.strptime(args.cut, "%Y-%m-%d").replace(tzinfo=UTC)
    config = SofaConfig.from_env()
    history = load_history(config.db_path)
    _, rated = replay(history, int(cut.timestamp()))
    tiers = fit_coefficients(rated)
    out = {
        "fitted_from": {
            "source": "sofa_entity_events (kind=last), completed singles",
            "cut_utc": cut.isoformat(),
            "history_matches": sum(1 for r in history if r.ts < cut.timestamp()),
            "rated_matches": len(rated),
            "fitted_at_utc": datetime.now(UTC).isoformat(),
        },
        "features": list(FEATURES),
        "min_rated": MIN_RATED,
        "neighbours": NEIGHBOURS,
        "tiers": tiers,
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    for tier, entry in tiers.items():
        coefficients = ", ".join(f"{c:+.3f}" for c in entry["coefficients"])
        print(f"{tier:5s} n={entry['n']:6d} [{coefficients}]")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
