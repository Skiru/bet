"""CS2 'no overtime in the series' walk-forward on the cached history (read-only).
p_map per series = the curve-fit replay (sport_confidence.cs2_walk_forward_rows: Elo + calibration
refitted every 7 days, as of the series start). Two models of P(no OT in series):
  race: series_distribution_mixed(p, bo) x per-map P(no OT | winner) from the round race (_race_dist at p)
  base: series_distribution_mixed(p, bo) x (1 - trailing OT share of every earlier map, LOOKBACK)
Per-map calibration of P(OT) too. Writes cs2_ot_wf_rows.jsonl."""
import sys, json, math, resource
from collections import Counter, defaultdict, deque
sys.path[:0] = ["/Users/mkoziol/projects/bet/src", "/Users/mkoziol/projects/bet"]
from bet.sofa import cs2_engine as ce
from bet.sofa import sport_confidence as scf
DB = "/Users/mkoziol/projects/bet/data/sofa.db"
START, END = sys.argv[1] if len(sys.argv) > 1 else "2026-01-01", sys.argv[2] if len(sys.argv) > 2 else "2026-11-21"

def ot(m): return m.home_rounds + m.away_rounds >= 25

def race_noot(p):
    dist = dict(ce._race_dist(round(min(max(p, 0.05), 0.95), 3)))
    w1 = sum(q for (a, b), q in dist.items() if a > b); w2 = 1 - w1
    n1 = sum(q for (a, b), q in dist.items() if a > b and a + b < 25) / w1
    n2 = sum(q for (a, b), q in dist.items() if a < b and a + b < 25) / w2
    p_ot = sum(q for (a, b), q in dist.items() if a + b >= 25)
    return n1, n2, p_ot

def series_noot(p, bo, n1, n2):
    d = ce.series_distribution_mixed(ce.clamp(p), bo)
    return sum(q * n1 ** a * n2 ** b for (a, b), q in d.items())

t0, t1 = scf.day_ts(START), scf.day_ts(END)
maps, series = scf.load_cs2(DB, t1)
print("maps loaded", len(maps), "series", len(series), "RSS MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)
rows = scf.cs2_walk_forward_rows(maps, series, t0, t1, "m", True)
p_series = {}
for r in rows:
    if r["family"] == "map_winner" and r["side"] == "T1":
        p_series.setdefault(int(r["game"][2:]), float(r["p"]))
del rows
by_series = defaultdict(list)
for m in maps: by_series[m.event_id].append(m)
window = deque(); n_ot = n_all = 0
out = open("cs2_ot_wf_rows.jsonl", "w")
stats = Counter()
for eid, smaps in by_series.items():  # oldest first (load_history order)
    st = smaps[0].start_ts
    while window and window[0][0] < st - ce.LOOKBACK_DAYS * 86400:
        _, o = window.popleft(); n_all -= 1; n_ot -= o
    if t0 <= st < t1:
        srow = series.get(eid)
        pm = p_series.get(eid)
        complete = (srow is not None and srow.best_of and srow.home_maps is not None and srow.away_maps is not None
                    and len(smaps) == srow.home_maps + srow.away_maps
                    and all(m.home_rounds is not None and m.away_rounds is not None for m in smaps))
        stats["series_in_window"] += 1
        if pm is None: stats["unrated"] += 1
        if not complete: stats["incomplete"] += 1
        if pm is not None and complete and n_all >= 200 and srow.best_of in (1, 2, 3, 5):
            n1, n2, p_ot_map = race_noot(pm)
            base = n_ot / n_all
            pr = series_noot(pm, srow.best_of, n1, n2)
            pb = series_noot(pm, srow.best_of, 1 - base, 1 - base)
            y = int(not any(ot(m) for m in smaps))
            out.write(json.dumps({"eid": eid, "ts": st, "bo": srow.best_of, "p_map": round(pm, 4),
                "p_race": round(pr, 5), "p_base": round(pb, 5), "base_map": round(base, 4), "race_map_ot": round(p_ot_map, 4),
                "n_maps": len(smaps), "ot_maps": sum(ot(m) for m in smaps), "y_noot": y,
                "maps": [[m.home_rounds, m.away_rounds, int(m.home_won)] for m in smaps]}) + "\n")
            stats["rows"] += 1
    for m in smaps:
        if m.home_rounds is not None and m.away_rounds is not None:
            o = int(ot(m)); window.append((m.start_ts, o)); n_all += 1; n_ot += o
print(dict(stats), "RSS MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)
