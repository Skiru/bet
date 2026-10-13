#!/usr/bin/env python3
"""One step ahead: a regional unit's league strength from 0 (old) or from
its competition's (new; audit 2026-10-13 A1, epochs.UNIT_STRENGTH_FROM_PARENT).
Pre-registered in docs/sofa/evidence/unit_strength_2026-10-13.md. Read-only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_unit_strength.py \\
        [--from 2026-06-01] [--to 2026-10-12] [--json-out f]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402

METRIC = "goals_for"


def pois_ll(lam: float, k: float) -> float:
    lam = max(lam, 1e-6)
    kk = int(round(k))
    return -(kk * math.log(lam) - lam - math.lgamma(kk + 1))


def boot(groups: dict[str, float], seed: int = 0, reps: int = 2000) -> list[float]:
    keys = sorted(groups)
    if not keys:
        return [float("nan")] * 4
    vals = [groups[k] for k in keys]
    rng = random.Random(seed)
    stats = sorted(sum(vals[rng.randrange(len(vals))] for _ in vals) / len(vals)
                   for _ in range(reps))
    return [sum(vals) / len(vals), stats[int(0.025 * reps)],
            stats[int(0.975 * reps) - 1], float(len(vals))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2026-06-01")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    db = SofaConfig.from_env().db_path
    history = fr.load_history(db, Path(db).parent / "cache")
    t0 = int(datetime.fromisoformat(args.start).replace(tzinfo=UTC).timestamp())
    t1 = int((datetime.fromisoformat(args.end) + timedelta(days=1)).replace(
        tzinfo=UTC).timestamp())
    old = fr.RatingBook()
    new = fr.RatingBook(unit_strength_from_parent=True)
    scopes: dict[str, dict[str, float]] = defaultdict(dict)
    mse: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in history:
        if r.ts >= t1:
            break
        if METRIC not in r.values:
            continue
        r = dataclasses.replace(r, values={METRIC: r.values[METRIC]})
        if r.ts >= t0 and all(
                b.team_matches(t, METRIC) >= fr.MIN_TEAM_MATCHES
                for b in (old, new) for t in (r.home_id, r.away_id)):
            preds = []
            linked = False
            for b in (old, new):
                status, lf = b.link(r.home_id, r.away_id, METRIC)
                linked = linked or status == fr.LINKED
                preds.append(b.expected(r.competition_id, r.home_id, r.away_id,
                                        METRIC, lf, cross=status != fr.LINKED))
            if preds[0] is not None and preds[1] is not None:
                vh, va = r.values[METRIC]
                (oh, oa), (nh, na) = preds[0], preds[1]
                d = (pois_ll(nh, vh) - pois_ll(oh, vh)
                     + pois_ll(na, va) - pois_ll(oa, va))
                dm = [(oh - vh) ** 2 + (oa - va) ** 2, (nh - vh) ** 2 + (na - va) ** 2]
                mid = str(r.event_id)
                unit_side = any(
                    (dom := new.domain(t)) is not None
                    and new.unit_competition(dom) != dom
                    for t in (r.home_id, r.away_id))
                tags = ["all"]
                if not linked:
                    tags.append("cross")
                    if unit_side:
                        tags.append("cross_unit")
                for tag in tags:
                    scopes[tag][mid] = d
                    m = mse[tag]
                    m[0] += dm[0]
                    m[1] += dm[1]
                    m[2] += 2
        old.update(r)
        new.update(r)
    out: dict[str, Any] = {}
    for tag, groups in sorted(scopes.items()):
        m = mse[tag]
        out[tag] = {"logloss_new_minus_old_per_match": boot(groups),
                    "mse_old": m[0] / m[2], "mse_new": m[1] / m[2]}
    text = json.dumps(out, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
