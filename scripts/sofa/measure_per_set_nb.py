# ruff: noqa: E501, E731, UP031  - a one-off measurement harness; its report lines are tables.
"""NB vs normal(floor -0.5) for tennis per-set serve metrics, replayed from cache.

Centre = raw sample mean (no ladder, no prior). pred_sd = predictive_sd with
the Poisson floor as run_sheet applies it. Sample = the player's last 10
observations strictly before kickoff, scoped by surface (surfaces_comparable
on groundType) and best-of (infer_best_of), n>=8, all-zero samples refused.
"""

from __future__ import annotations

import collections
import json
import sqlite3
import statistics
import sys

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

METRICS = [
    "aces_set1_for",
    "aces_set2_for",
    "double_faults_set1_for",
    "double_faults_set2_for",
    "serve_points_set1_for",
    "serve_points_set2_for",
    # controls: already on the NB list, should reproduce the shipped sign
    "aces_for",
    "double_faults_for",
]
LINES = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5]
SAMPLE_N, MIN_N = 10, 8

conn = sqlite3.connect("file:data/sofa.db?mode=ro", uri=True, timeout=120)
events: dict[int, dict] = {}
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

flat_by_event: dict[int, dict] = {}
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

played = sorted(
    (
        e
        for e in events.values()
        if e["id"] in flat_by_event and e.get("startTimestamp")
    ),
    key=lambda e: e["startTimestamp"],
)

# player -> list of (ts, surface, best_of, {metric: value})
hist: dict[int, list] = collections.defaultdict(list)
rows = collections.defaultdict(
    list
)  # metric -> (event_id, dir, line, p_norm, p_nb, won, mean)
for e in played:
    flat = flat_by_event[e["id"]]
    surface = e.get("groundType")
    bo = infer_best_of(e)
    ts = e["startTimestamp"]
    for is_home, side in ((True, "homeTeam"), (False, "awayTeam")):
        pid = (e.get(side) or {}).get("id")
        if not pid:
            continue
        vals = {}
        for m in METRICS:
            v = extract_metric(m, "tennis", flat, None, e, is_home)
            if isinstance(v, float):
                vals[m] = v
        past = hist[pid]
        if surface is not None and bo is not None and vals:
            scoped = [
                p
                for p in past
                if p[0] < ts and p[2] == bo and surfaces_comparable(p[1], surface)
            ]
            for m, actual in vals.items():
                sample = [p[3][m] for p in scoped if m in p[3]][-SAMPLE_N:]
                n = len(sample)
                if n < MIN_N or all(v == 0.0 for v in sample):
                    continue
                mean = statistics.mean(sample)
                var = statistics.variance(sample)
                sd = predictive_sd(
                    var, mean, n, apply_poisson_floor=uses_poisson_floor(m)
                )
                for line in LINES:
                    for d in ("OVER", "UNDER"):
                        b = winning_boundary(line, d)
                        pn = calc_p_central_raw(mean, sd, b, d, support_floor_for(m))
                        pb = calc_p_central_nb_raw(mean, sd, b, d)
                        if outside_model_resolution(pn) or outside_model_resolution(pb):
                            continue
                        oc = settle(actual, line, d)
                        if oc == "PUSH":
                            continue
                        rows[m].append(
                            (
                                e["id"],
                                d,
                                line,
                                pn,
                                pb,
                                1.0 if oc == "WIN" else 0.0,
                                mean,
                            )
                        )
        past.append((ts, surface, bo, vals))


def brier(rs, i):
    return sum((r[i] - r[5]) ** 2 for r in rs) / len(rs) if rs else float("nan")


print(
    f"{'metric':24s} {'n':>6s} {'Bnorm':>8s} {'Bnb':>8s} {'dB':>9s} {'dB_even':>9s} {'dB_odd':>9s} | OVER n  p_norm  p_nb  real | tail>=.70 norm n claim real | nb n claim real | verdict"
)
for m in METRICS:
    rs = rows[m]
    if not rs:
        print(m, "no rows")
        continue
    d = brier(rs, 4) - brier(rs, 3)
    ev = [r for r in rs if r[0] % 2 == 0]
    od = [r for r in rs if r[0] % 2 == 1]
    de = brier(ev, 4) - brier(ev, 3)
    do = brier(od, 4) - brier(od, 3)
    ov = [r for r in rs if r[1] == "OVER"]
    mo = lambda i: sum(r[i] for r in ov) / len(ov)
    tn = [r for r in rs if r[3] >= 0.70]
    tb = [r for r in rs if r[4] >= 0.70]
    avg = lambda xs, i: sum(x[i] for x in xs) / len(xs) if xs else float("nan")
    if len(rs) < 2000:
        verdict = "INSUFFICIENT_DATA"
    elif d < 0 and de < 0 and do < 0:
        verdict = "ADD_TO_NB"
    else:
        verdict = "KEEP_NORMAL"
    print(
        f"{m:24s} {len(rs):6d} {brier(rs, 3):8.5f} {brier(rs, 4):8.5f} {d:+9.5f} {de:+9.5f} {do:+9.5f} | {len(ov):6d} {mo(3):.4f} {mo(4):.4f} {mo(5):.4f} | {len(tn):6d} {avg(tn, 3):.4f} {avg(tn, 5):.4f} | {len(tb):6d} {avg(tb, 4):.4f} {avg(tb, 5):.4f} | {verdict}"
    )

print("\naces_set1_for OVER 0.5, sample mean in [1.0,1.4]:")
sel = [
    r
    for r in rows["aces_set1_for"]
    if r[1] == "OVER" and r[2] == 0.5 and 1.0 <= r[6] <= 1.4
]
if sel:
    print(
        f"  n={len(sel)} mean_sample={avg(sel, 6):.3f} p_norm={avg(sel, 3):.4f} p_nb={avg(sel, 4):.4f} realised={avg(sel, 5):.4f} Bnorm={brier(sel, 3):.5f} Bnb={brier(sel, 4):.5f}"
    )
print("\naces_set1_for OVER 0.5 by sample-mean band:")
for lo, hi in (
    (0.5, 0.8),
    (0.8, 1.0),
    (1.0, 1.2),
    (1.2, 1.4),
    (1.4, 1.8),
    (1.8, 2.5),
    (2.5, 9),
):
    s = [
        r
        for r in rows["aces_set1_for"]
        if r[1] == "OVER" and r[2] == 0.5 and lo <= r[6] < hi
    ]
    if s:
        print(
            f"  [{lo},{hi}) n={len(s):5d} p_norm={avg(s, 3):.4f} p_nb={avg(s, 4):.4f} realised={avg(s, 5):.4f}"
        )
