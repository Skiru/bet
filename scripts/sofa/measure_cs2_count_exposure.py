#!/usr/bin/env python3
"""CS2 kills / deaths / assists / headshots from the rounds' exposure (audit
2026-10-13 B12, epochs.CS2_COUNT_EXPOSURE). Pre-registered in
docs/sofa/evidence/cs2_kills_exposure_2026-10-13.md. Read-only.

Walk-forward over the map history: every map of the main window (the last 40%
of series) is priced from the state before its series, by the old sample model
(cs2_engine.count_p on the last MAX_SAMPLE maps) and by the exposure model
(cs2_engine.exposure_sides), on synthetic lines around the old mean. Per
family the log-loss difference new - old per line, interval a bootstrap over
series.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_count_exposure.py \\
        [--from 2025-10-13] [--to 2026-10-13] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2_engine as ce  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.measure_cs2_map_identity import boot, ll  # noqa: E402

FAMILY = {"kills": "player_kills", "deaths": "player_deaths",
          "assists": "player_assists", "headshots": "player_headshots"}


def lines_of(values: list[int]) -> list[float]:
    n = len(values)
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    c = round(mean)
    h = max(1, round(sd / 2))
    out = sorted({c - 0.5 - h, c - 0.5, c + 0.5, c + 0.5 + h})
    return [x for x in out if x >= 0.5]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-10-13")
    ap.add_argument("--to", dest="end", default="2026-10-13")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    db = SofaConfig.from_env().db_path
    t0, t1 = scf.day_ts(args.start), scf.day_ts(args.end)
    maps, series = scf.load_cs2(db, t1)
    by_series: dict[int, list[ce.MapRow]] = {}
    for m in maps:
        by_series.setdefault(m.event_id, []).append(m)
    in_win = [e for e, s in by_series.items() if t0 <= s[0].start_ts < t1]
    cut = sorted(by_series[e][0].start_ts for e in in_win)[int(0.6 * len(in_win))]

    book = ce.EloBook()
    players = ce.PlayerEloBook()
    points: list[tuple[float, float]] = []
    ppoints: list[tuple[float, float]] = []
    model = ce.RatingModel(book)
    next_refit = 0
    expo = ce.ExposureBook()
    pvals: dict[tuple[int, str], deque[int]] = defaultdict(
        lambda: deque(maxlen=ce.MAX_SAMPLE))
    tkills: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=ce.MAX_SAMPLE))
    diff: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    guard: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    cal: dict[str, dict[str, list[tuple[float, int]]]] = defaultdict(
        lambda: {"old": [], "new": []})
    brier: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    n_series = 0
    for eid, smaps in by_series.items():
        start = smaps[0].start_ts
        if start >= next_refit:
            model = scf._cs2_refit(book, players, points, ppoints)
            next_refit = start + scf.REFIT_DAYS_CS2 * 86400
        home, away = smaps[0].home_id, smaps[0].away_id
        score = cut <= start < t1
        n_series += score
        for m in smaps:
            p_home = model.p_map(home, away, True) if score else None
            if p_home is not None and m.home_rounds is not None:
                for team, opp, w, lost, totals, rows in ce.map_sides(m):
                    p_team = p_home if team == home else 1.0 - p_home
                    items: list[tuple[str, int | None, str, int, list[int]]] = []
                    if "kills" in totals:
                        items.append(("team_kills", None, "kills", totals["kills"],
                                      list(tkills[team])))
                    for pid, own in rows:
                        for stat, fam in FAMILY.items():
                            if isinstance(own.get(stat), int):
                                items.append((fam, pid, stat, own[stat],
                                              list(pvals[(pid, stat)])))
                    for fam, ipid, stat, xv, old_vals in items:
                        x = int(xv)
                        if len(old_vals) < ce.MIN_SAMPLE:
                            continue
                        cells = ce.exposure_cells(expo, p_team, team, opp, stat, ipid)
                        phi = expo.phi("team" if ipid is None else "player", stat)
                        if cells is None or phi is None:
                            continue
                        lns = lines_of(old_vals)
                        if not lns:
                            continue
                        sides = ce.exposure_sides(cells, phi, lns)
                        for ln in lns:
                            for over in (True, False):
                                po = ce.count_p(old_vals, ln, over)
                                pn = ce.side_given_no_push(*sides[ln], over)
                                if po is None or pn is None:
                                    continue
                                pn = ce.clamp(pn)
                                y = int((x > ln) == over)
                                g = f"h:{eid}"
                                diff[fam][g].append(ll(pn, y) - ll(po.p, y))
                                brier[fam][g].append((pn - y) ** 2 - (po.p - y) ** 2)
                                if max(po.p, pn) >= 0.70:
                                    guard[fam][g].append(ll(pn, y) - ll(po.p, y))
                                if po.p >= 0.70:
                                    cal[fam]["old"].append((po.p, y))
                                if pn >= 0.70:
                                    cal[fam]["new"].append((pn, y))
        # --- state update, as cs2_walk_forward_rows ---
        if book.rated(home, away):
            d = ce.logit_diff(book, home, away)
            points.extend((d, 1.0 if m.home_won else 0.0) for m in smaps)
            gap = players.gap(home, away)
            if gap is not None:
                ppoints.extend((gap, 1.0 if m.home_won else 0.0) for m in smaps)
        for m in smaps:
            winner, loser = (m.home_id, m.away_id) if m.home_won else (
                m.away_id, m.home_id)
            book.update(winner, loser)
            players.update(m)
            expo.update(m)
            for team, _, _, _, totals, rows in ce.map_sides(m):
                if "kills" in totals:
                    tkills[team].append(totals["kills"])
                for pid, own in rows:
                    for stat in FAMILY:
                        if isinstance(own.get(stat), int):
                            pvals[(pid, stat)].append(own[stat])
    out: dict[str, Any] = {"window": [args.start, args.end], "main_from_ts": cut,
                           "series_main": n_series, "families": {}}
    for fam in sorted(diff):
        out["families"][fam] = {
            "lines": sum(len(v) for v in diff[fam].values()),
            "series": len(diff[fam]),
            "logloss_new_minus_old": boot(diff[fam]),
            "brier_new_minus_old": boot(brier[fam]),
            "guard_logloss_p70": boot(guard[fam]) + [
                float(sum(len(v) for v in guard[fam].values()))],
            "calibration_p70": {
                k: {"n": len(v),
                    "mean_p": sum(p for p, _ in v) / len(v) if v else None,
                    "realised": sum(y for _, y in v) / len(v) if v else None}
                for k, v in cal[fam].items()},
        }
    text = json.dumps(out, indent=1)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
