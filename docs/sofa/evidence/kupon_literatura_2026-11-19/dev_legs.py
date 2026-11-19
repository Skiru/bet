"""Dev only: does the de-vigged market_p predict a leg better than 1/odds?"""
import math, random, sys
from collections import defaultdict
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from legs import load

split = sys.argv[1] if len(sys.argv) > 1 else "dev"
rows = [r for r in load(split) if 1.10 <= r["odds"] <= 2.00]
two = [r for r in rows if r["mp"] is not None]
one = [r for r in rows if r["mp"] is None]
print(split, "legs 1.10-2.00:", len(rows), "two-sided:", len(two), "one-sided:", len(one))
def ret(rs): return sum(r["won"] * r["odds"] for r in rs) / len(rs)
print("realised / price  two-sided %.4f  one-sided %.4f" % (ret(two), ret(one) if one else float("nan")))

def scores(rs, f):
    b = sum((f(r) - r["won"]) ** 2 for r in rs) / len(rs)
    ll = -sum(math.log(f(r)) if r["won"] else math.log(1 - f(r)) for r in rs) / len(rs)
    return b, ll
ests = {"1/odds": lambda r: 1 / r["odds"], "market_p": lambda r: r["mp"],
        "min(conf,1/odds)": lambda r: min(r["conf"], 1 / r["odds"]),
        "min(conf,market_p)": lambda r: min(r["conf"], r["mp"]),
        "conf": lambda r: r["conf"]}
for k, f in ests.items():
    print("%-20s Brier %.5f  logloss %.5f  mean %.4f" % ((k,) + scores(two, f) + (sum(f(r) for r in two) / len(two),)))
print("hit rate", sum(r["won"] for r in two) / len(two))
# paired bootstrap by match: Brier(min(conf,mp)) - Brier(min(conf,1/odds))
by = defaultdict(list)
for r in two: by[r["match"]].append(r)
keys = list(by); random.seed(7)
def diff(ks):
    a = b = n = 0
    for k in ks:
        for r in by[k]:
            a += (min(r["conf"], r["mp"]) - r["won"]) ** 2
            b += (min(r["conf"], 1 / r["odds"]) - r["won"]) ** 2; n += 1
    return (a - b) / n
d0 = diff(keys); bs = sorted(diff(random.choices(keys, k=len(keys))) for _ in range(500))
print("Brier min(conf,mp) - min(conf,1/odds): %.5f [%.5f, %.5f]" % (d0, bs[12], bs[487]))
# realised per unit price by margin and price band (FLB)
cell = defaultdict(list)
for r in two:
    if r["ov"] is None: continue
    pb = "1.10-1.25" if r["odds"] < 1.25 else "1.25-1.45" if r["odds"] < 1.45 else "1.45-2.00"
    mb = "<0.06" if r["ov"] < 0.06 else "0.06-0.09" if r["ov"] < 0.09 else ">=0.09"
    cell[(pb, mb)].append(r)
for k in sorted(cell):
    rs = cell[k]
    print(k, len(rs), "realised/price %.4f" % ret(rs), "pred mp*odds %.4f" % (sum(r["mp"] * r["odds"] for r in rs) / len(rs)))
