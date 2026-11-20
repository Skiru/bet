import gzip, json, sys
from collections import Counter, defaultdict
S = "/private/tmp/claude-501/-Users-mkoziol-projects-bet/04c6201e-4497-4273-b02c-92e4cd7d7f51/scratchpad/football"
sys.path[:0] = [S]
from stats import bucket, wilson_lo
dup = json.load(open(S + "/step1_same_event_printable.json"))
DUPLAB = set()
for cand, c in dup.items():
    for d in c["dups"]:
        gk, label = d.split(" = ")[0].split(" ", 1)
        DUPLAB.add((cand, gk, label))
print({c: (len(v["dups"]), {k: v[k] for k in v if k != "dups"}) for c, v in dup.items()})
def key(cand, label):
    tail = label.split(":")[-1]
    return f"{cand}|{tail}" if tail in ("tak", "nie") else f"{cand}|OVER"
curve = defaultdict(lambda: defaultdict(lambda: [0, 0]))
for line in gzip.open(S + "/history_rows.jsonl.gz", "rt"):
    eid, ts, women, cand, gk, label, p, y = json.loads(line)
    if not cand.startswith("half"): continue
    if cand.endswith("handicap") and "(-" in label: continue
    c = curve[key(cand, label)][bucket(p)]; c[0] += y; c[1] += 1
def cc(cand, label, p):
    c = curve.get(key(cand, label), {}).get(bucket(p))
    return None if not c or c[1] < 100 else wilson_lo(c[0], c[1])
rows = [json.loads(l) for l in gzip.open(S + "/live_eval.jsonl.gz", "rt")]
rows = [r for r in rows if r["cand"] in ("half1_handicap","half2_handicap") and r["complete"] and r["p_sim"] is not None and r["y"] in (0,1,"REFUND")]
print("example", {k: rows[0][k] for k in rows[0]})
for cand in ("half1_handicap","half2_handicap"):
    for variant in ("raw","curve"):
        for usedup in (True, False):
            legs=[]
            for r in rows:
                if r["cand"]!=cand: continue
                if usedup and (r["cand"], r["gk"], r["label"]) in DUPLAB: continue
                conf = r["p_sim"] if variant=="raw" else cc(r["cand"], r["label"], r["p_sim"])
                if conf is None or conf<0.70 or conf*r["price"]<0.90 or r["overround"]>1.15 or r["price"]<1/0.9202: continue
                legs.append(r)
            lab = Counter(l["label"][1:] for l in legs)
            sides = Counter(l["label"][1:2] for l in legs)
            ev = len({(l["eid"]) for l in legs}); evline=len({(l["eid"],abs(float(l['label'][2:-1]))) for l in legs})
            print(cand, variant, "dedup" if usedup else "nodedup", len(legs), dict(sorted(lab.items())), "sign", sides, "events", ev, "per-day", round(len(legs)/14,1))
# nesting: legs per (event) for curve+dedup, both halves together
legsall=[]
for r in rows:
    if (r["cand"], r["gk"], r["label"]) in DUPLAB: continue
    conf = cc(r["cand"], r["label"], r["p_sim"])
    if conf is None or conf<0.70 or conf*r["price"]<0.90 or r["overround"]>1.15 or r["price"]<1/0.9202: continue
    legsall.append(r)
ev=Counter(r["eid"] for r in legsall); evh=Counter((r["eid"],r["cand"]) for r in legsall)
print("B both halves legs", len(legsall), "events", len(ev), "legs/event", round(len(legsall)/len(ev),2), "event-halves with >1 leg", sum(1 for v in evh.values() if v>1), "of", len(evh))
print("distinct events/day", round(len(ev)/14,1))
