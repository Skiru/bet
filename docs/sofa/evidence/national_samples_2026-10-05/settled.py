import sys, sqlite3, numpy as np, collections, json, glob, os
sys.path.insert(0, '/private/tmp/claude-501/-Users-mkoziol-projects-bet/326c21e7-29e6-43a0-88f5-09a4e6cdf26e/scratchpad/nations')
import measure_nations as M
from scripts.sofa.measure_sample_composition import before, split_metric, paired_interval
from bet.sofa.comparability import MatchKind
h, targets, meta = M.load()
tg = {t.event_id: t for t in targets}
nat_ids = set(tg)
con = sqlite3.connect("file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro", uri=True)
DAY = 86400
# base stat for a market (for the history lookup)
BASE = {"goals": "goals", "corners": "corners", "yellow_cards": "yellow_cards", "shots": "shots", "shots_on_target": "shots_on_target", "fouls": "fouls", "offsides": "offsides"}
def oldest_age(t, market):
    stat, _, scope = market.rpartition("_")
    if stat in ("goals_1h", "goals_2h"): stat = "goals"
    if stat not in BASE: stat = "goals"  # fall back to the match list itself
    metric = stat + "_" + ("for" if scope == "for" else "total")
    try: split_metric(metric)
    except ValueError: metric = "goals_total"
    out = []
    for side in (t.home, t.away):
        b = [p for p in before(h.get(side, []), t.ts, metric) if p.kind is not MatchKind.FRIENDLY][:10]
        if b: out.append((t.ts - b[-1].ts) / DAY)
    return max(out) if out else None
rng = np.random.default_rng(3)
def table(rows, label):
    print(f"\n### {label}: {len(rows)} rows, {len({r[0] for r in rows})} matches")
    print("| oldest-age bucket | rows | matches | mean p_central | realised | gap (real - p) [95% by match] |")
    for lo, hi in ((0, 180), (180, 400), (400, 730), (730, 1e9), (None, None)):
        sel = [r for r in rows if (r[3] is None if lo is None else (r[3] is not None and lo < r[3] <= hi))]
        if len(sel) < 20: print(f"| {lo}-{hi} | {len(sel)} | too few |"); continue
        ids = np.array([r[0] for r in sel]); p = np.array([r[1] for r in sel]); y = np.array([r[2] for r in sel])
        a, b = paired_interval(y - p, ids, rng, 500)
        print(f"| {lo}-{hi} | {len(sel)} | {len(set(ids.tolist()))} | {p.mean():.3f} | {y.mean():.3f} | {(y-p).mean():+.3f} [{a:+.3f}; {b:+.3f}] |")
for live in (False, True):
    q = ("SELECT sofascore_event_id, market, p_central, outcome, offered_odds FROM sofa_settled_row WHERE sport='football' AND p_central >= 0.70 AND run_date " + ("!=" if live else "=") + " 'cache-calibration'")
    rows = []; allrows = []
    for eid, market, p, out, odds in con.execute(q):
        if eid not in nat_ids: continue
        if market.startswith(("most_", "handicap_", "both_")) or "player" in market: continue
        t = tg[eid]
        age = oldest_age(t, market)
        rows.append((eid, p, 1.0 if out == "WIN" else 0.0, age, market, meta[eid]['senior_men'], odds))
    lab = "LIVE" if live else "cache-calibration"
    table(rows, f"{lab} national competitive, p_central>=0.70, all markets")
    table([r for r in rows if r[5]], f"{lab} senior men")
    table([r for r in rows if r[4].startswith("goals")], f"{lab} goals markets")
    table([r for r in rows if r[4].startswith("corners")], f"{lab} corners markets")
    if live:
        pr = [r for r in rows if r[6]]
        print("live priced rows", len(pr))
        if pr:
            ids=np.array([r[0] for r in pr]); y=np.array([r[2] for r in pr]); o=np.array([r[6] for r in pr]); p=np.array([r[1] for r in pr])
            print("implied", (1/o).mean(), "realised", y.mean(), "p", p.mean())
            for lo,hi in ((0,180),(180,400),(400,730),(730,1e9)):
                s=np.array([r[3] is not None and lo<r[3]<=hi for r in pr])
                if s.sum()>=20:
                    roi=(y[s]*o[s]-1); a,b=paired_interval(roi,ids[s],rng,500)
                    print(f" age {lo}-{hi}: n={s.sum()} matches={len(set(ids[s].tolist()))} p={p[s].mean():.3f} implied={(1/o[s]).mean():.3f} realised={y[s].mean():.3f} flat ROI={roi.mean():+.3f} [{a:+.3f};{b:+.3f}]")
# reference: all football cache rows at p>=0.70 (non-national), realised - p
q = "SELECT p_central, outcome FROM sofa_settled_row WHERE sport='football' AND p_central>=0.70 AND run_date='cache-calibration' AND market NOT LIKE 'most_%' AND market NOT LIKE 'handicap_%' AND market NOT LIKE 'both_%' AND (sofascore_event_id % 50)=0"
arr = np.array([(p, 1.0 if o == 'WIN' else 0.0) for p, o in con.execute(q)])
print("\nreference all-football cache rows (1/50 subsample by event id):", len(arr), "p", arr[:,0].mean().round(3), "realised", arr[:,1].mean().round(3), "gap", (arr[:,1]-arr[:,0]).mean().round(3))
