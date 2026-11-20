"""Calibration on history (vb_joint_hist.jsonl): the 4-way joint's selections, the favourite 'same' selection, 1st-set handicap."""
import json, math, random, collections
R = [json.loads(l) for l in open("vb_joint_hist.jsonl")]
def boot(v, reps=3000):
    rng = random.Random(4); n = len(v); s = sorted(sum(v[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return sum(v) / n, s[int(.025 * reps)], s[int(.975 * reps) - 1]
print("matches", len(R))
pairs = [(p, int(r["y"] == k)) for r in R for k, p in r["joint"].items()]
print("all 4-way selections: Brier %.4f; bands:" % (sum((p - y) ** 2 for p, y in pairs) / len(pairs)))
b = collections.defaultdict(list)
for p, y in pairs: b[min(math.floor(p * 10) / 10, 0.9)].append((p, y))
for k in sorted(b):
    v = b[k]; g = boot([y - p for p, y in v]); print(f"  [{k:.1f},{k+.1:.1f}) n {len(v):5d} claimed {sum(p for p,_ in v)/len(v):.3f} realised {sum(y for _,y in v)/len(v):.3f} gap %+.3f [%+.3f, %+.3f]" % g)
# p >= 0.70 selections (all are 'same' favourite)
hi = [(p, y) for p, y in pairs if p >= 0.70]
print("p>=0.70: n %d claimed %.3f realised %.3f gap %+.3f [%+.3f, %+.3f]" % ((len(hi), sum(p for p,_ in hi)/len(hi), sum(y for _,y in hi)/len(hi)) + boot([y - p for p, y in hi])))
# P(set-1 winner = match winner)
same = [(r["joint"]["11"] + r["joint"]["00"], int(r["y"] in ("11", "00"))) for r in R]
print("P(set1 winner = match winner): claimed %.3f realised %.3f" % (sum(p for p,_ in same)/len(same), sum(y for _,y in same)/len(same)))
# set-1 handicap at p>=0.70 (lines -7.5..+7.5 both teams); which lines reach it
hc = collections.defaultdict(list)
for r in R:
    for L, p in r["hcp"].items():
        L = float(L); y = int(r["d1"] + L > 0)
        for side, pp, yy in (("home", p, y), ("away", 1 - p, 1 - y)):
            if pp >= 0.70: hc[L if side == "home" else -L].append((pp, yy))
tot = [x for v in hc.values() for x in v]
print("1st-set handicap sides with p>=0.70: n %d claimed %.3f realised %.3f gap %+.3f [%+.3f, %+.3f]" % ((len(tot), sum(p for p,_ in tot)/len(tot), sum(y for _,y in tot)/len(tot)) + boot([y - p for p, y in tot])))
for L in sorted(hc):
    v = hc[L]
    if len(v) >= 30: print(f"   own line {L:+.1f}: n {len(v)} claimed {sum(p for p,_ in v)/len(v):.3f} realised {sum(y for _,y in v)/len(v):.3f}")
