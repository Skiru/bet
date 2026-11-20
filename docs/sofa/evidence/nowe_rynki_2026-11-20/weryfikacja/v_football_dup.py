"""Independent per-event same-event check: unmapped full-match / half handicaps vs that day's 04_offer read rungs."""
import gzip, json, re, sys, ast
from collections import Counter, defaultdict
from pathlib import Path
from bet.sofa.market_mapper import fold
from bet.sofa import leg_identity as li
DAYS = sys.argv[1:]
MK = {"handicap": "FT2", "handicap 1x2": "FT3", "1.polowa - handicap": "H1", "1. polowa - handicap": "H1",
      "2.polowa - handicap": "H2", "2. polowa - handicap": "H2", "remis w obu polowach": "DBH"}
SEL = re.compile(r"^(?P<t>.+) \((?P<l>[+-]?\d+(?:\.\d+)?)\)$")
E3 = re.compile(r"^(?P<t>.+) \((?P<x>\d+):(?P<y>\d+)\)$")
f_ = lambda s: " ".join(fold(s or "").split())
def held_fn(kind, sel, home, away, sbs):
    def side(t):
        t = f_(t)
        hits = {i for i, ns in enumerate((home, away)) for n in ns if n and t == f_(n)}
        return hits.pop() if len(hits) == 1 else None
    if kind == "DBH":
        if f_(sel) not in ("tak", "nie"): return None
        yes = f_(sel) == "tak"
        return lambda s: ((s[0] == s[1] and s[2] == s[3]) == yes)
    if kind == "FT3":
        m = E3.match(sel)
        if not m: return None
        x, y = int(m["x"]), int(m["y"])
        if f_(m["t"]) == "remis":
            return lambda s: (s[0] + s[2] + x) == (s[1] + s[3] + y)
        sd = side(m["t"])
        if sd is None: return None
        return lambda s: ((s[0]+s[2]+x) > (s[1]+s[3]+y)) if sd == 0 else ((s[0]+s[2]+x) < (s[1]+s[3]+y))
    m = SEL.match(sel)
    if not m: return None
    L = float(m["l"]); sd = side(m["t"])
    if sd is None or L == int(L): return None
    def g(s):
        if kind == "FT2": h, a = s[0]+s[2], s[1]+s[3]
        elif kind == "H1": h, a = s[0], s[1]
        else: h, a = s[2], s[3]
        own, oth = (h, a) if sd == 0 else (a, h)
        return own + L > oth
    return g
tot = Counter(); newex = defaultdict(list); bylab = defaultdict(Counter)
for day in DAYS:
    rd = Path("runs/sofa") / day
    fx = {int(f["sofascore_event_id"]): f for f in json.load(open(rd / "02_fixtures.json")) if f.get("sport") == "football"}
    # read vectors per event
    board = {str(e["superbet_event_id"]): (e.get("side_a") or "", e.get("side_b") or "") for e in json.load(open(rd / "01_board.json"))}
    readv = defaultdict(dict)
    for e in json.load(open(rd / "04_offer.json")):
        try: eid = int(e["sofascore_event_id"])
        except Exception: continue
        if eid not in fx: continue
        rungs = e["rungs"]
        if isinstance(rungs, str): rungs = ast.literal_eval(rungs)
        h, a = f_(fx[eid]["home_name"]), f_(fx[eid]["away_name"])
        for r in rungs:
            subj = r.get("subject") or ""; sd = None
            if r["market"] in li._SIDE_COUNT_MARKETS:
                s = f_(subj); sd = 0 if s == h else 1 if s == a else None
                if sd is None: continue
            v = li._football_vector(r["market"], subj, sd, float(r["line"] if r["line"] is not None else 0.5))
            if v is None: continue
            if r.get("over_odds"): readv[eid].setdefault(v, f"{r['market']}@{subj}@{r['line']}|OVER")
            if r.get("under_odds"): readv[eid].setdefault(tuple(None if x is None else not x for x in v), f"{r['market']}@{subj}@{r['line']}|UNDER")
    # unmapped: latest pre-kickoff record per selection, fair p within its snapshot group
    groups = defaultdict(list)
    for fp in sorted((rd / "unmapped_prices").glob("2026*.jsonl.gz")):
        for line in gzip.open(fp, "rt", encoding="utf-8"):
            d = json.loads(line)
            eid = d.get("sofascore_event_id")
            if not isinstance(eid, int) or eid not in fx: continue
            kind = MK.get(f_(d.get("marketName")))
            if kind is None or d.get("status") != "active" or not d.get("price"): continue
            if (d.get("fetched_at_utc") or "") >= fx[eid]["kickoff_utc"]: continue
            groups[(eid, kind, d.get("specialBetValue"), d["fetched_at_utc"])].append(d)
    latest = {}
    for (eid, kind, sbv, ts), rs in groups.items():
        inv = sum(1 / r["price"] for r in rs)
        n_exp = 3 if kind == "FT3" else 2
        if len(rs) != n_exp: continue
        for r in rs:
            k = (eid, kind, r["name"], sbv)
            if k not in latest or latest[k][0] <= ts:
                latest[k] = (ts, r["price"], (1 / r["price"]) / inv, str(r.get("superbet_event_id")))
    for (eid, kind, name, sbv), (ts, price, fair, sb) in latest.items():
        f = fx[eid]; b = board.get(sb, ("", ""))
        g = held_fn(kind, name, (f["home_name"], b[0]), (f["away_name"], b[1]), sbv)
        if g is None: tot[(kind, "unparsed")] += 1; continue
        zone = 1.09 <= price <= 1.43 and fair >= 0.70
        vec = tuple(g(s) for s in li._STATES)
        hit = readv.get(eid, {}).get(vec)
        lab = re.sub(r"^.*\(", "(", name)
        tot[(kind, "zone" if zone else "out", "dup" if hit else "new")] += 1
        if zone:
            bylab[(kind, "dup" if hit else "new")][lab] += 1
            if not hit and len(newex[kind]) < 6: newex[kind].append((day, eid, name, price, round(fair, 3)))
for k in sorted(tot, key=str): print(k, tot[k])
for k in sorted(bylab, key=str): print(k, bylab[k].most_common(10))
for k, v in newex.items(): print("NEW example", k, v)
