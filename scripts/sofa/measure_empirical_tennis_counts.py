# ruff: noqa: E501, UP031  - a one-off measurement harness; its report lines are tables.
"""Normal CDF vs NB vs empirical frequency for few-valued tennis MATCH totals.

Replayed from cache, the way run_sheet prices a `_total` rung: the sample is
both players' own histories pooled and de-duplicated by event (L13), each side
= its last 10 observations strictly before kickoff, scoped by surface
(surfaces_comparable on groundType) and best-of (infer_best_of); n >= 8 per
side, all-zero samples refused. Centre = raw sample mean (no ladder, no prior,
no price) - the same bare comparison F49 used to put games_won_for on
EMPIRICAL_FREQUENCY_METRICS.

Metrics:
  tiebreaks_total   0..3 on BO3; today priced from a normal CDF with no
                    Poisson floor, and refused by CONFIDENCE as
                    NOT_IN_CALIBRATION_FIT.
  games_set1_total  one set's games, both players: 6,7,8,9,10,12,13 - there is
  games_set2_total  no 11. Superbet's "1. set - liczba gemow" ladder.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_empirical_tennis_counts.py
"""

from __future__ import annotations

import collections
import json
import sqlite3
import statistics
import sys
from typing import Any

from bet.sofa.engine import (
    calc_p_central_nb_raw,
    calc_p_central_raw,
    outside_model_resolution,
    predictive_sd,
    support_floor_for,
    uses_poisson_floor,
    winning_boundary,
)
from bet.sofa.metrics import extract_flat_statistics, extract_metric, infer_best_of
from bet.sofa.settle import is_completed_event, settle, surfaces_comparable

METRICS = {
    "tiebreaks_total": [0.5, 1.5, 2.5],
    "games_set1_total": [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5],
    "games_set2_total": [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5],
}
SAMPLE_N, MIN_N = 10, 8

conn = sqlite3.connect("file:data/sofa.db?mode=ro", uri=True, timeout=120)
events: dict[int, dict[str, Any]] = {}
for (ej,) in conn.execute("SELECT events_json FROM sofa_entity_events"):
    try:
        evs = json.loads(ej)
    except ValueError:
        continue
    if isinstance(evs, dict):
        evs = evs.get("events", [])
    for e in evs if isinstance(evs, list) else []:
        if not isinstance(e, dict) or not isinstance(e.get("id"), int):
            continue
        sport = (
            ((e.get("tournament") or {}).get("category") or {}).get("sport") or {}
        ).get("slug")
        if sport == "tennis" and e["id"] not in events and is_completed_event(e):
            events[e["id"]] = e
print("tennis completed listing events", len(events), file=sys.stderr)

flat_by_event: dict[int, dict[str, dict[str, tuple[float, float]]]] = {}
ids = list(events)
for i in range(0, len(ids), 500):
    chunk = ids[i : i + 500]
    q = (
        "SELECT sofascore_event_id, statistics_json FROM sofa_event_stats WHERE status_type='finished' AND sofascore_event_id IN (%s)"
        % ",".join("?" * len(chunk))
    )
    for eid, sj in conn.execute(q, chunk):
        if sj:
            try:
                flat_by_event[eid] = extract_flat_statistics(json.loads(sj))
            except ValueError:
                pass
print("with statistics", len(flat_by_event), file=sys.stderr)

# The set-games metrics read the listing, not /statistics, so an event with no
# statistics still carries them; tiebreaks needs the statistics.
played = sorted(
    (e for e in events.values() if e.get("startTimestamp")),
    key=lambda e: e["startTimestamp"],
)

# player -> list of (ts, surface, best_of, event_id, {metric: value})
Hist = tuple[int, str | None, int | None, int, dict[str, float]]
hist: dict[int, list[Hist]] = collections.defaultdict(list)
# metric -> (event_id, dir, line, p_norm, p_nb, p_emp, won)
Row = tuple[int, str, float, float, float, float, float]
rows: dict[str, list[Row]] = collections.defaultdict(list)
for e in played:
    flat = flat_by_event.get(e["id"], {})
    surface = e.get("groundType")
    bo = infer_best_of(e)
    ts = e["startTimestamp"]
    vals: dict[str, float] = {}
    for m in METRICS:
        v = extract_metric(m, "tennis", flat, None, e, True)
        if isinstance(v, float):
            vals[m] = v
    raw_ids = [(e.get(s) or {}).get("id") for s in ("homeTeam", "awayTeam")]
    pids = [i for i in raw_ids if isinstance(i, int)]
    if surface is not None and bo is not None and vals and len(pids) == 2:
        for m, actual in vals.items():
            pooled: dict[int, float] = {}
            ok = True
            for pid in pids:
                scoped = [
                    p
                    for p in hist[pid]
                    if p[0] < ts and p[2] == bo and surfaces_comparable(p[1], surface)
                    and m in p[4]
                ][-SAMPLE_N:]
                if len(scoped) < MIN_N:
                    ok = False
                    break
                for p in scoped:
                    pooled[p[3]] = p[4][m]
            if not ok:
                continue
            sample = list(pooled.values())
            n = len(sample)
            if all(v == 0.0 for v in sample):
                continue
            mean = statistics.mean(sample)
            var = statistics.variance(sample)
            sd = predictive_sd(var, mean, n, apply_poisson_floor=uses_poisson_floor(m))
            for line in METRICS[m]:
                for d in ("OVER", "UNDER"):
                    b = winning_boundary(line, d)
                    hits = sum(1 for v in sample if (v > b if d == "OVER" else v < b))
                    pe = hits / n
                    pn = calc_p_central_raw(mean, sd, b, d, support_floor_for(m))
                    pb = calc_p_central_nb_raw(mean, sd, b, d)
                    # The same resolution gate run_sheet applies to each path.
                    if outside_model_resolution(pe) or outside_model_resolution(pn):
                        continue
                    oc = settle(actual, line, d)
                    if oc == "PUSH":
                        continue
                    rows[m].append(
                        (e["id"], d, line, pn, pb, pe, 1.0 if oc == "WIN" else 0.0)
                    )
    for pid in pids:
        hist[pid].append((ts, surface, bo, e["id"], vals))


def brier(rs: list[Row], i: int) -> float:
    return sum((float(r[i]) - r[6]) ** 2 for r in rs) / len(rs) if rs else float("nan")


print(
    f"{'metric':18s} {'n':>6s} {'Bnorm':>8s} {'Bnb':>8s} {'Bemp':>8s} {'emp-norm':>9s} {'even':>9s} {'odd':>9s} | top(p>=.70) norm n claim real | emp n claim real"
)
def avg(xs: list[Row], i: int) -> float:
    return sum(float(x[i]) for x in xs) / len(xs) if xs else float("nan")


for m in METRICS:
    rs = rows[m]
    if not rs:
        print(m, "no rows")
        continue
    ev = [r for r in rs if r[0] % 2 == 0]
    od = [r for r in rs if r[0] % 2 == 1]
    delta = brier(rs, 5) - brier(rs, 3)
    de = brier(ev, 5) - brier(ev, 3)
    do = brier(od, 5) - brier(od, 3)
    tn = [r for r in rs if r[3] >= 0.70]
    te = [r for r in rs if r[5] >= 0.70]
    print(
        f"{m:18s} {len(rs):6d} {brier(rs, 3):8.5f} {brier(rs, 4):8.5f} {brier(rs, 5):8.5f} {delta:+9.5f} {de:+9.5f} {do:+9.5f} | {len(tn):6d} {avg(tn, 3):.4f} {avg(tn, 6):.4f} | {len(te):6d} {avg(te, 5):.4f} {avg(te, 6):.4f}"
    )
    for line in METRICS[m]:
        for dd in ("OVER", "UNDER"):
            s = [r for r in rs if r[2] == line and r[1] == dd]
            if len(s) >= 200:
                print(
                    f"    {dd:5s} {line:5.1f} n={len(s):6d} norm {avg(s, 3):.3f} nb {avg(s, 4):.3f} emp {avg(s, 5):.3f} real {avg(s, 6):.3f}"
                )
