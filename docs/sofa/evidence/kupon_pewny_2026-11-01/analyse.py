import json, math, random, sys, collections
rows = [json.loads(l) for l in open(sys.argv[1])]
slips = [r for r in rows if r["kind"] == "slip"]; reqs = [r for r in rows if r["kind"] == "request"]
def grade(s):
    st = [l["status"] for l in s["legs"]]
    if "lost" in st: return "lost", -1.0
    if "unknown" in st: return "unknown", None
    won = [l for l in s["legs"] if l["status"] == "won"]
    if not won: return "refund", 0.0
    p = math.prod(l["odds"] for l in won); return "won", 0.88 * p - 1
for s in slips: s["st"], s["ret"] = grade(s)
def boot(items, f, B=2000, seed=1):
    days = sorted({i["day"] for i in items}); by = collections.defaultdict(list)
    for i in items: by[i["day"]].append(i)
    rng = random.Random(seed); vals = []
    for _ in range(B):
        smp = [x for d in (rng.choice(days) for _ in days) for x in by[d]]
        v = f(smp)
        if v is not None: vals.append(v)
    vals.sort(); return vals[int(.025*len(vals))], vals[int(.975*len(vals))-1]
def hit(xs):
    g = [x for x in xs if x["st"] in ("won", "lost")]
    return sum(x["st"] == "won" for x in g)/len(g) if g else None
def roi(xs):
    g = [x for x in xs if x["ret"] is not None]
    return sum(x["ret"] for x in g)/len(g) if g else None
def claim(xs):
    g = [x for x in xs if x["st"] in ("won", "lost")]
    return sum(x["chance"] for x in g)/len(g) if g else None
periods = {"dev": lambda d: d <= "2026-10-24", "hold": lambda d: d >= "2026-10-25", "all": lambda d: True}
for arm in ["A_def_t2", "B_def_t125", "C_safe_114", "D_safe_t13"]:
    for pn, pf in periods.items():
        xs = [s for s in slips if s["arm"] == arm and pf(s["day"])]
        c = collections.Counter(s["st"] for s in xs)
        legs = sum(len(s["legs"]) for s in xs)
        lg = [l for s in xs for l in s["legs"] if l["status"] in ("won","lost")]
        lh = sum(l["status"]=="won" for l in lg)/len(lg); lc = sum(l["chance"] for l in lg)/len(lg); li = sum(1/l["odds"] for l in lg)/len(lg)
        h, cl, r = hit(xs), claim(xs), roi(xs)
        hci, rci = boot(xs, hit), boot(xs, roi)
        below = sum(0.88*s["prod"] < 1 for s in xs)
        wonbelow = sum(1 for s in xs if s["st"]=="won" and s["ret"] < 0)
        print(f"{arm:11s} {pn:4s} slips {len(xs):4d} legs {legs:4d} ({legs/len(xs):.2f}/slip) W{c['won']} L{c['lost']} R{c['refund']} U{c['unknown']} "
              f"claim {cl:.3f} hit {h:.3f} [{hci[0]:.3f},{hci[1]:.3f}] prod {sum(s['prod'] for s in xs)/len(xs):.3f} "
              f"ROI {100*r:+.1f}% [{100*rci[0]:+.1f},{100*rci[1]:+.1f}] prod<1.1364: {below} won-but-ret<0: {wonbelow} | legs hit {lh:.3f} chance {lc:.3f} 1/odds {li:.3f} n{len(lg)}")
print()
for arm in ["A_def_t2", "B_def_t125", "C_safe_114", "D_safe_t13"]:
    rq = [r for r in reqs if r["arm"] == arm]
    print(arm, "requests", len(rq), "empty", sum(r["found"]==0 for r in rq), "1-2 slips", sum(0<r["found"]<3 for r in rq),
          "not_reached", sum(r["not_reached"] for r in rq),
          "dup_match", sum(s["dup_match"] for s in slips if s["arm"]==arm),
          "leg<1.10", sum(l["odds"]<1.10 for s in slips if s["arm"]==arm for l in s["legs"]),
          "prod<target", sum(1 for s in slips if s["arm"]==arm and s["reached"] and s["prod"] < {"A_def_t2":2,"B_def_t125":1.25,"C_safe_114":1.14,"D_safe_t13":1.3}[arm]-1e-9),
          "nlegs", collections.Counter(len(s["legs"]) for s in slips if s["arm"]==arm),
          "src_price", sum(l["src"]!="pewność" for s in slips if s["arm"]==arm for l in s["legs"]),
          "sports", collections.Counter(l["sport"] for s in slips if s["arm"]==arm for l in s["legs"]).most_common(6))
