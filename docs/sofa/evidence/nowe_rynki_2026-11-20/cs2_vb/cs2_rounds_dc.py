"""CS2 231535 'Drużyna - najwięcej wygranych rund w meczu' (1X2) and 231548 'Podwójna szansa rundy' (1X / X2):
the series rounds handicap -0.5 ("1"/"2") and +0.5 ("1X"/"X2"). Read-only.
Part A (history): walk-forward rows of cs2_ot_walkforward.py (p_map as of the start, curve-fit replay) priced
  through cs2_engine.series_rounds_side_p(p, bo, 'rounds_handicap', +-0.5, side) - the live path - graded on
  the played maps' rounds. Part B (offer): last pre-start snapshot per event, team1 orientation, de-vig,
  confidence through the 2026-11-20 curve + line evidence (run_sport_confidence.read_confidence replicated)."""
import sys, json, glob, sqlite3, math, random, statistics, collections
from datetime import datetime
sys.path[:0] = ["/Users/mkoziol/projects/bet/src", "/Users/mkoziol/projects/bet"]
from bet.sofa import cs2_engine as ce, epochs
from bet.sofa import sport_confidence as scf
from bet.sofa.line_evidence import LineEvidence, DEFAULT_EVIDENCE
ROOT = "/Users/mkoziol/projects/bet/runs/sofa"; DB = "file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro"
def utc(s): return datetime.fromisoformat(s.replace("Z", "+00:00"))
def boot(groups, reps=3000, seed=5):
    keys = list(groups); rng = random.Random(seed); flat = [v for k in keys for v in groups[k]]; st = []
    for _ in range(reps):
        t = n = 0
        for _k in keys:
            g = groups[keys[rng.randrange(len(keys))]]; t += sum(g); n += len(g)
        st.append(t / n)
    st.sort(); return sum(flat) / len(flat), st[int(.025 * reps)], st[int(.975 * reps) - 1]
F = lambda t: "%+.4f [%+.4f, %+.4f]" % t
SIDES = {"1": (-0.5, "T1"), "2": (0.5, "T2"), "1X": (0.5, "T1"), "X2": (-0.5, "T2")}  # team1's handicap, side
def won(side, diff):  # diff = team1 rounds - team2 rounds
    return {"1": diff > 0, "2": diff < 0, "1X": diff >= 0, "X2": diff <= 0}[side]
def p_side(p_t1, bo, side):
    ln, sd = SIDES[side]; return ce.series_rounds_side_p(p_t1, bo, "rounds_handicap", ln, sd, None)

# ---------------- A. history ----------------
print("== A. history walk-forward (rows of cs2_ot_walkforward.py, 2026-02-01..11-20)")
t0 = utc("2026-02-01T00:00:00Z").timestamp()
H = []
for l in open("cs2_ot_wf_rows.jsonl"):
    r = json.loads(l)
    if r["ts"] < t0: continue
    diff = sum(h - a for h, a, _ in r["maps"])
    for side in SIDES:
        p = p_side(r["p_map"], r["bo"], side)
        if p is not None: H.append(dict(eid=r["eid"], bo=r["bo"], side=side, p=p, y=int(won(side, diff)), pm=r["p_map"]))
ties = collections.Counter((r["bo"], sum(h - a for h, a, _ in r["maps"]) == 0) for r in map(json.loads, open("cs2_ot_wf_rows.jsonl")) if r["ts"] >= t0)
print("series by (bo, rounds tie):", dict(ties))
for bo in (1, 3, 5):
    S = [h for h in H if h["bo"] == bo]
    if not S: continue
    print(f" bo{bo}: rows {len(S)}")
    bands = collections.defaultdict(list)
    for h in S: bands[min(math.floor(h["p"] * 10) / 10, 0.9)].append(h)
    for b in sorted(bands):
        v = bands[b]
        if len(v) < 40: continue
        g = collections.defaultdict(list)
        for h in v: g[h["eid"]].append(h["y"] - h["p"])
        print(f"   [{b:.1f},{b+.1:.1f}) n {len(v):5d} claimed {sum(h['p'] for h in v)/len(v):.3f} realised {sum(h['y'] for h in v)/len(v):.3f} gap", F(boot(g)))
    hi = [h for h in S if h["p"] >= 0.70]
    if hi:
        g = collections.defaultdict(list)
        for h in hi: g[h["eid"]].append(h["y"] - h["p"])
        print(f"   p>=0.70: n {len(hi)} series {len(g)} claimed {sum(h['p'] for h in hi)/len(hi):.3f} realised {sum(h['y'] for h in hi)/len(hi):.3f} gap", F(boot(g)))
        for sd in ("1", "2", "1X", "X2"):
            K = [h for h in hi if h["side"] == sd]
            if K: print(f"     {sd}: n {len(K)} claimed {sum(h['p'] for h in K)/len(K):.3f} realised {sum(h['y'] for h in K)/len(K):.3f}")
# the round tie in BO3: model vs realised
S3 = [r for r in map(json.loads, open("cs2_ot_wf_rows.jsonl")) if r["ts"] >= t0 and r["bo"] == 3]
pt = [p_side(r["p_map"], 3, "1X") + p_side(r["p_map"], 3, "X2") - 1 for r in S3]
print(" bo3 P(rounds tie): model %.4f realised %.4f (n %d)" % (statistics.mean(pt), sum(sum(h - a for h, a, _ in r["maps"]) == 0 for r in S3) / len(S3), len(S3)))

# ---------------- B. the offer ----------------
print("== B. offered events")
q = collections.defaultdict(lambda: collections.defaultdict(dict))
for l in open("unmapped_candidates.jsonl"):
    r = json.loads(l)
    if r["mid"] in (231535, 231548): q[r["sb"]][r["ts"]][(r["mid"], r["name"])] = r["price"]
meta = {}
for f in glob.glob(f"{ROOT}/cs2/2026-11-*/snapshots.jsonl"):
    for line in open(f):
        s = json.loads(line); meta[s["superbet_event_id"]] = (s["kickoff_utc"], s["tournament"])
pins = {}
for f in sorted(glob.glob(f"{ROOT}/2026-1*/sport_fixtures.json")):
    for fx in json.load(open(f)).get("fixtures", []):
        if fx.get("sport") == "cs2" and (fx.get("sofascore_event_id") or fx["superbet_event_id"] not in pins):
            pins[fx["superbet_event_id"]] = fx
wf = {r["eid"]: r for r in map(json.loads, open("cs2_ot_wf_rows.jsonl"))}
conn = sqlite3.connect(DB, uri=True)
D = "2026-11-20"; at = utc("2026-11-20T12:00:00Z")
cal = scf.SportCalibration.load(scf.calibration_path_for(D))
ev = LineEvidence.load(DEFAULT_EVIDENCE, v2=epochs.line_evidence_v2(D, at), bucket_deff=epochs.bucket_design_effect(D, at),
                       price_gap_sports=epochs.price_gap_offset_sports(D, at))
def confidence(p, side_t, odds):
    c = cal.lookup("cs2", "rounds_handicap", side_t, p, require_admitted=False)
    rd = ev.read("cs2", scf.curve_key("rounds_handicap", side_t), p, None if c is None else (c.value, c.calibrated_on, c.n), odds)
    return None if rd is None else rd.value
stat = collections.Counter(); rows = []; margins3, margins_pair, margins_dc = [], [], []
for sb, byts in q.items():
    ko, tour = meta.get(sb, (None, None))
    pre = [t for t in byts if ko and utc(t) < utc(ko) and any(k[0] == 231535 for k in byts[t])]
    if not pre: stat["no_pre"] += 1; continue
    s = byts[max(pre)]
    o = {k[1]: v for k, v in s.items() if k[0] == 231535}; dc = {k[1]: v for k, v in s.items() if k[0] == 231548}
    if set(o) != {"1", "X", "2"}: stat["1x2_incomplete"] += 1; continue
    inv3 = {k: 1 / v for k, v in o.items()}; tot3 = sum(inv3.values()); margins3.append(tot3 - 1)
    fair3 = {k: v / tot3 for k, v in inv3.items()}
    offers = {"1": (o["1"], fair3["1"], tot3 - 1), "2": (o["2"], fair3["2"], tot3 - 1)}
    if set(dc) == {"1X", "X2"}:
        margins_dc.append(1 / dc["1X"] + 1 / dc["X2"] + (1 / o["1"] + 1 / o["2"]) - 2)  # not used
        for d, comp in (("1X", "2"), ("X2", "1")):
            a, b = 1 / dc[d], 1 / o[comp]; margins_pair.append(a + b - 1)
            offers[d] = (dc[d], a / (a + b), a + b - 1)
    fx = pins.get(sb, {}); eid = fx.get("sofascore_event_id")
    if not eid: stat["not_pinned"] += 1; continue
    r = wf.get(eid)
    if r is None:
        srow = conn.execute("select status_type from cs2_series where sofascore_event_id=?", (eid,)).fetchone()
        stat["no_wf_row(" + (srow[0] if srow else "not_cached") + ")"] += 1; continue
    t1_home = bool(fx.get("home_is_team1"))
    p_t1 = r["p_map"] if t1_home else 1 - r["p_map"]
    diff = sum(h - a for h, a, _ in r["maps"]) * (1 if t1_home else -1)
    stat["graded_events"] += 1
    for side, (odds, fair, mg) in offers.items():
        p = p_side(p_t1, r["bo"], side)
        side_t = SIDES[side][1]
        conf = confidence(p, side_t, odds)
        rows.append(dict(sb=sb, eid=eid, bo=r["bo"], side=side, odds=odds, fair=fair, margin=mg, p=p, conf=conf, y=int(won(side, diff)), tour=tour))
print(dict(stat))
print("1X2 (231535) 3-way overround: mean %.3f min %.3f max %.3f n %d" % (statistics.mean(margins3), min(margins3), max(margins3), len(margins3)))
print("DC side + complementary 1X2 outcome, pair overround: mean %.3f min %.3f max %.3f n %d" % (statistics.mean(margins_pair), min(margins_pair), max(margins_pair), len(margins_pair)))
json.dump(rows, open("cs2_rounds_dc_rows.json", "w"))
for side in ("1", "2", "1X", "X2"):
    K = [x for x in rows if x["side"] == side]
    fq = sorted(x["fair"] for x in K)
    print(f" {side}: n {len(K)} fair q10/50/90/max {fq[int(.1*(len(fq)-1))]:.3f}/{fq[len(fq)//2]:.3f}/{fq[int(.9*(len(fq)-1))]:.3f}/{fq[-1]:.3f}  odds min {min(x['odds'] for x in K)}")
def per_event(K, f): 
    g = collections.defaultdict(list)
    for x in K: g[x["eid"]].append(f(x))
    return g
ll = lambda p, y: -math.log(min(max(p, 1e-6), 1 - 1e-6) if y else 1 - min(max(p, 1e-6), 1 - 1e-6))
for lab, K in (("1/2 (-0.5)", [x for x in rows if x["side"] in ("1", "2")]), ("1X/X2 (+0.5)", [x for x in rows if x["side"] in ("1X", "X2")])):
    print(f" {lab}: rows {len(K)} events {len({x['eid'] for x in K})} realised {statistics.mean(x['y'] for x in K):.3f}")
    print("   Brier model - fair", F(boot(per_event(K, lambda x: (x['p'] - x['y']) ** 2 - (x['fair'] - x['y']) ** 2))),
          " logloss model - fair", F(boot(per_event(K, lambda x: ll(x['p'], x['y']) - ll(x['fair'], x['y'])))))
    print("   realised - model", F(boot(per_event(K, lambda x: x['y'] - x['p']))), " realised - fair", F(boot(per_event(K, lambda x: x['y'] - x['fair']))))
    print("   corr(model p, fair) %.3f; sd model p %.3f; sd fair %.3f; sd (model - fair) %.3f" % (statistics.correlation([x['p'] for x in K], [x['fair'] for x in K]),
          statistics.pstdev([x['p'] for x in K]), statistics.pstdev([x['fair'] for x in K]), statistics.pstdev([x['p'] - x['fair'] for x in K])))
for lab, key in (("confidence (curve + line evidence)", "conf"), ("raw model p", "p")):
    P = [x for x in rows if x[key] is not None and x[key] >= 0.70 and x[key] * x["odds"] >= 0.90 and x["margin"] <= 0.15]
    print(f" gates on {lab}: {len(P)} legs / {len({x['eid'] for x in P})} events", collections.Counter(x["side"] for x in P))
    if P:
        g = per_event(P, lambda x: x["odds"] * x["y"] - 1)
        print("   hit %.3f mean 1/odds %.3f mean %s %.3f mean fair %.3f ROI %s; after 12%% tax %+.3f" % (
            statistics.mean(x['y'] for x in P), statistics.mean(1 / x['odds'] for x in P), key, statistics.mean(x[key] for x in P),
            statistics.mean(x['fair'] for x in P), F(boot(g)), statistics.mean(0.88 * x['odds'] * x['y'] for x in P) - 1))
        print("   odds of passing legs:", sorted(x["odds"] for x in P))
