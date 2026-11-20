"""Volleyball candidates vs the rally model and Superbet's price on the offered events (read-only).
230059 '1.Set/Mecz' (4-way: set-1 winner / match winner), 786 '1. set - handicap punkty', 100080/100081 team points.
Each event: last pre-start snapshot, pinned id / orientation / result from runs/sofa/shadow/volleyball/<d>/settled.json,
rally forecast as of the start (vb_point_pricer.forecast_fixtures on the indexed history), 4,000 sims seeded by id.
Writes vb_rows.jsonl (one row per selection)."""
import sys, json, glob, pickle, collections, itertools
from datetime import datetime
import numpy as np
sys.path[:0] = ["/Users/mkoziol/projects/bet/src", "/Users/mkoziol/projects/bet"]
from bet.sofa import vb_point_pricer as vpp
from bet.sofa import volleyball_point_model as vpm
ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
def utc(s): return datetime.fromisoformat(s.replace("Z", "+00:00"))
raw = pickle.load(open("vb_history.pkl", "rb"))
history = sorted((vpm.VbMatch(int(e), int(ts), int(c), int(h), int(a), bool(w), tuple(hs), tuple(as_))
                  for e, ts, c, h, a, w, hs, as_ in raw), key=lambda m: (m.ts, m.event_id))
women = vpp.women_by_team(history); by_id = {m.event_id: m for m in history}
# settled SHADOW events by superbet id
sett = {}
for f in sorted(glob.glob(f"{ROOT}/shadow/volleyball/2026-11-*/settled.json")):
    for sb, ev in (json.load(open(f)).get("events") or {}).items():
        sett[str(sb)] = ev
meta = {}
for f in glob.glob(f"{ROOT}/shadow/volleyball/2026-11-*/snapshots.jsonl"):
    for line in open(f):
        s = json.loads(line); meta[s["superbet_event_id"]] = (s["team1"], s["team2"], s["kickoff_utc"], s["tournament"])
groups = collections.defaultdict(dict)
for l in open("unmapped_candidates.jsonl"):
    r = json.loads(l)
    if r["sport"] != "volleyball" or r["mid"] not in (230059, 786, 100080, 100081): continue
    key = r["sbv"] if r["mid"] != 230059 else ""
    groups[(r["mid"], r["sb"], key, r["mname"] if r["mid"] in (100080, 100081) else "")].setdefault(r["ts"], {})[r["name"]] = r["price"]
stat = collections.Counter(); fixtures = {}; todo = []
for (mid, sb, key, mn), byts in groups.items():
    if sb not in meta: stat["no_meta"] += 1; continue
    t1, t2, ko, tour = meta[sb]
    pre = [t for t in byts if utc(t) < utc(ko)]
    if not pre: stat["no_pre"] += 1; continue
    sel = byts[max(pre)]
    ev = sett.get(sb)
    if not ev or not ev.get("pinned_id") or ev.get("orientation_unclear"): stat["not_pinned_or_unsettled"] += 1; continue
    if ev.get("state") != "SETTLED" or not ev.get("t1_periods"): stat[f"state_{ev.get('state')}"] += 1; continue
    sid = int(ev["sofascore_event_id"])
    if sid not in fixtures:
        comp = by_id[sid].competition if sid in by_id else -1
        m = vpp.fixture_match(sid, utc(ev.get("sofascore_start_utc") or ko), ev.get("sofascore_home_id"), ev.get("sofascore_away_id"), comp, women)
        if m is None: stat["no_fixture"] += 1; continue
        fixtures[sid] = m
    todo.append((mid, sb, key, mn, sel, ev, sid, t1, t2, tour, max(pre)))
print(dict(stat), "groups ok", len(todo), "fixtures", len(fixtures), flush=True)
pricer = vpp.VbPricer(vpp.forecast_fixtures(history, list(fixtures.values())))
out = open("vb_rows.jsonl", "w"); n = 0
for mid, sb, key, mn, sel, ev, sid, t1, t2, tour, ts in todo:
    s = pricer.sim(sid)
    if s is None: continue
    if not ev.get("home_is_team1", True): s = s.swapped()
    P = s.points
    s1 = P[:, 0, 0] > P[:, 0, 1]
    w1 = (P[:, :, 0] > P[:, :, 1]).sum(axis=1); w2 = (P[:, :, 1] > P[:, :, 0]).sum(axis=1)
    m1 = w1 > w2
    tp, tq = ev["t1_periods"], ev["t2_periods"]
    a_s1 = tp[0] > tq[0]; a_m1 = ev.get("winner") == "T1"
    inv = {k: 1 / v for k, v in sel.items()}; tot = sum(inv.values())
    f = pricer.forecasts[sid]
    base = dict(mid=mid, sb=sb, sid=sid, tour=tour, ts=ts, margin=round(tot - 1, 4), women=f.women, rated=list(f.rated), mu=round(f.mu, 4))
    rows = []
    if mid == 230059:
        names = {f"{a}/{b}": (a == t1, b == t1) for a, b in itertools.product((t1, t2), repeat=2)}
        if set(sel) != set(names): stat["230059_names"] += 1; continue
        for nm, (x1, y1) in names.items():
            p = float(((s1 == x1) & (m1 == y1)).mean()); y = int(a_s1 == x1 and a_m1 == y1)
            rows.append(dict(base, sel=nm, kind="same" if x1 == y1 else "split", p=p, fair=inv[nm] / tot, odds=sel[nm], y=y))
    elif mid == 786:
        if len(sel) != 2: continue
        d1 = P[:, 0, 0] - P[:, 0, 1]; ad = tp[0] - tq[0]
        for nm, price in sel.items():
            team, ln = nm.rsplit(" (", 1); ln = float(ln.rstrip(")"))
            if team not in (t1, t2): stat["786_team"] += 1; break
            sign = 1 if team == t1 else -1
            p = float(((sign * d1 + ln) > 0).mean()); y = int(sign * ad + ln > 0)
            rows.append(dict(base, sel=nm, line=ln, p=p, fair=inv[nm] / tot, odds=price, y=y))
    else:
        team = mn.rsplit(" - liczba punktów", 1)[0]
        if team not in (t1, t2) or len(sel) != 2: stat["pts_team"] += 1; continue
        col = 0 if team == t1 else 1
        pts = P[:, :, col].sum(axis=1); act = sum(tp) if col == 0 else sum(tq)
        for nm, price in sel.items():
            ln = float(nm.split()[-1]); over = nm.startswith("powy")
            p = float(((pts > ln) if over else (pts < ln)).mean()); y = int((act > ln) if over else (act < ln))
            rows.append(dict(base, sel=nm, line=ln, p=p, fair=inv[nm] / tot, odds=price, y=y))
    for r in rows: out.write(json.dumps(r) + "\n"); n += 1
print("rows", n, dict(stat))
