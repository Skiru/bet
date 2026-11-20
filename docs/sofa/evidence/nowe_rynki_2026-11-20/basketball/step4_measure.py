"""Step 4: model vs Superbet on graded offered selections 11-06..11-19.

Milestones (one-sided): the book's number is 1/price (raw, margin inside)
and, second, the book after a same-sample Platt (logistic on logit 1/price):
the best any de-vig of the one-sided price could do on these rows. The
model: raw installed p, and same-sample Platt (upper bound of any curve).
Double-double (two-sided Tak / Nie): fair p proportional de-vig of the pair;
model = independence of the three marginals P(>=10) (steals / blocks left
out - shown separately). Match bootstrap (2,000) 95% CI on differences.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

S = os.path.join(os.path.dirname(__file__), "out")
B = 2000
TAX = 0.88


def lg(t):
    return "NBA" if t == "USA - NBA" else ("EL" if t == "Euroliga" else "inne")


def clip(p):
    return min(max(p, 1e-4), 1 - 1e-4)


def ll(p, y):
    p = clip(p)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def platt(ps, ys, iters=200):
    """Logistic a + b logit p by Newton; returns the fitted function."""
    xs = [math.log(clip(p) / (1 - clip(p))) for p in ps]
    a, b = 0.0, 1.0
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys):
            q = 1 / (1 + math.exp(-(a + b * x)))
            r = q - y
            w = q * (1 - q)
            ga += r; gb += r * x
            haa += w; hab += w * x; hbb += w * x * x
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a -= da; b -= db
        if abs(da) + abs(db) < 1e-9:
            break
    return lambda p: 1 / (1 + math.exp(-(a + b * math.log(clip(p) / (1 - clip(p)))))), (a, b)


def boot(rows, stat, key="superbet_event_id"):
    """Match bootstrap of a per-row mean: `stat(rows)` must be a mean of a
    per-row value; it is evaluated per row via stat([r]) and aggregated per
    event, so a replicate costs O(events)."""
    by = defaultdict(lambda: [0.0, 0])
    for r in rows:
        v = stat([r])
        by[r[key]][0] += v
        by[r[key]][1] += 1
    sums = list(by.values())
    rng = random.Random(7)
    k = len(sums)
    vals = []
    for _ in range(B):
        s = n = 0.0
        for _ in range(k):
            a, b = sums[rng.randrange(k)]
            s += a
            n += b
        vals.append(s / n)
    vals.sort()
    return stat(rows), vals[int(0.025 * B)], vals[int(0.975 * B)]


def fmt(t, k=1000):
    return "%+.2f [%+.2f; %+.2f]" % (t[0] * k, t[1] * k, t[2] * k)


rows = [json.loads(x) for x in open(f"{S}/scored.jsonl")]
print("rows", len(rows), Counter((r["kind"], r.get("outcome")) for r in rows))

# ---------------------------------------------------------------- milestones
ms = [r for r in rows if r["kind"] == "milestone"]
print("\n== milestones: model reasons", Counter(r["model_reason"] if r["model_p"] is None else "P" for r in ms))
g = [r for r in ms if r.get("outcome") in ("WIN", "LOSS") and r["model_p"] is not None]
for r in g:
    r["y"] = 1 if r["outcome"] == "WIN" else 0
    r["q"] = 1 / r["price"]
print("graded with p:", len(g), "events", len({r["superbet_event_id"] for r in g}),
      "by league", Counter(lg(r["tournament"]) for r in g))
print("outcomes all milestones:", Counter(r.get("outcome") for r in ms))


def brier_diff(rs):
    return sum((r["model_p"] - r["y"]) ** 2 - (r["q"] - r["y"]) ** 2 for r in rs) / len(rs)


def ll_diff(rs):
    return sum(ll(r["model_p"], r["y"]) - ll(r["q"], r["y"]) for r in rs) / len(rs)


def summary(rs, label):
    if len(rs) < 30:
        print(label, "n", len(rs), "too few")
        return
    n = len(rs)
    bm = sum((r["model_p"] - r["y"]) ** 2 for r in rs) / n
    bq = sum((r["q"] - r["y"]) ** 2 for r in rs) / n
    print(f"{label}: n {n} ev {len({r['superbet_event_id'] for r in rs})} hit {sum(r['y'] for r in rs)/n:.3f} "
          f"mean model {sum(r['model_p'] for r in rs)/n:.3f} mean 1/price {sum(r['q'] for r in rs)/n:.3f} "
          f"Brier model {bm:.4f} price(raw) {bq:.4f}; diff x1e3 {fmt(boot(rs, brier_diff))}; "
          f"logloss diff x1e3 {fmt(boot(rs, ll_diff))}")


summary(g, "ALL")
for L in ("NBA", "EL", "inne"):
    summary([r for r in g if lg(r["tournament"]) == L], L)
for f in sorted({r["family"] for r in g}):
    summary([r for r in g if r["family"] == f], f)

# Platt (same sample) on both
fm, cm = platt([r["model_p"] for r in g], [r["y"] for r in g])
fq, cq = platt([r["q"] for r in g], [r["y"] for r in g])
for r in g:
    r["mp"] = fm(r["model_p"]); r["qp"] = fq(r["q"])
print("Platt model a,b", cm, "Platt price a,b", cq)
d = boot(g, lambda rs: sum((r["mp"] - r["y"]) ** 2 - (r["qp"] - r["y"]) ** 2 for r in rs) / len(rs))
print("after same-sample Platt on both: Brier diff x1e3", fmt(d))

# calibration bands (model raw)
print("\n== calibration bands (model raw p), hit vs claimed vs 1/price")
for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.92), (0.92, 1.0)):
    rs = [r for r in g if lo <= r["model_p"] < hi]
    if not rs:
        continue
    t = boot(rs, lambda x: sum(r["y"] - r["model_p"] for r in x) / len(x))
    print(f"{lo:.2f}-{hi:.2f}: n {len(rs)} claimed {sum(r['model_p'] for r in rs)/len(rs):.3f} "
          f"hit {sum(r['y'] for r in rs)/len(rs):.3f} 1/price {sum(r['q'] for r in rs)/len(rs):.3f} "
          f"hit-claimed pp {t[0]*100:+.1f} [{t[1]*100:+.1f}; {t[2]*100:+.1f}]")
print("== calibration bands of 1/price")
for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.92), (0.92, 1.0)):
    rs = [r for r in g if lo <= r["q"] < hi]
    if rs:
        print(f"{lo:.2f}-{hi:.2f}: n {len(rs)} 1/price {sum(r['q'] for r in rs)/len(rs):.3f} hit {sum(r['y'] for r in rs)/len(rs):.3f}")

# gates
print("\n== would-print: model p >= 0.70 and p*odds >= 0.90 (no curve, no line evidence, raw p)")
gate = [r for r in g if r["model_p"] >= 0.70 and r["model_p"] * r["price"] >= 0.90]
days = len({r["shadow_day"] for r in g})


def roi(rs, tax=1.0):
    return sum((r["price"] * tax if r["y"] else 0) - 1 for r in rs) / len(rs)


if gate:
    print(f"n {len(gate)} over {days} days = {len(gate)/days:.1f}/day; hit {sum(r['y'] for r in gate)/len(gate):.3f} "
          f"mean p {sum(r['model_p'] for r in gate)/len(gate):.3f} mean 1/odds {sum(r['q'] for r in gate)/len(gate):.3f}")
    print("ROI flat", fmt(boot(gate, roi), 100), "% ; after 12% tax", fmt(boot(gate, lambda x: roi(x, TAX)), 100), "%")
    for L in ("NBA", "EL", "inne"):
        rs = [r for r in gate if lg(r["tournament"]) == L]
        if rs:
            print(" ", L, len(rs), "hit %.3f p %.3f 1/odds %.3f ROI %+.1f%%" % (
                sum(r['y'] for r in rs)/len(rs), sum(r['model_p'] for r in rs)/len(rs),
                sum(r['q'] for r in rs)/len(rs), 100*roi(rs)))
# with Platt-on-model (same-sample curve, optimistic)
gate2 = [r for r in g if r["mp"] >= 0.70 and r["mp"] * r["price"] >= 0.90]
if gate2:
    print(f"with same-sample Platt as confidence: n {len(gate2)} ({len(gate2)/days:.1f}/day) hit "
          f"{sum(r['y'] for r in gate2)/len(gate2):.3f} conf {sum(r['mp'] for r in gate2)/len(gate2):.3f} "
          f"1/odds {sum(r['q'] for r in gate2)/len(gate2):.3f} ROI {fmt(boot(gate2, roi), 100)}%")
# zone selections overall: hit vs 1/price
zone = [r for r in g if 1.09 <= r["price"] <= 1.43]
print(f"\nzone 1.09-1.43: n {len(zone)} hit {sum(r['y'] for r in zone)/len(zone):.3f} "
      f"1/price {sum(r['q'] for r in zone)/len(zone):.3f} ROI {fmt(boot(zone, roi), 100)}% "
      f"(tax {fmt(boot(zone, lambda x: roi(x, TAX)), 100)}%)")
print("all graded milestones ROI", fmt(boot(g, roi), 100), "%")
json.dump(g, open(f"{S}/milestones_graded.json", "w"))

# ---------------------------------------------------------------- double double
print("\n== double-double")
dd = [r for r in rows if r["kind"] == "double_double"]
print("outcomes", Counter(r.get("outcome") for r in dd))
pairs = defaultdict(dict)
for r in dd:
    pairs[(r["superbet_event_id"], r["subject"])][r["side"]] = r
gr = []
for (eid, subj), sides in pairs.items():
    any_ = next(iter(sides.values()))
    if any_.get("outcome") not in ("WIN", "LOSS"):
        continue
    pp = [any_.get(f"p10_{f}") for f in ("player_points", "player_rebounds", "player_assists")]
    p_ind = None
    if all(p is not None for p in pp):
        a, b, c = pp
        p_ind = a * b + a * c + b * c - 2 * a * b * c
    fair = None
    if "Tak" in sides and "Nie" in sides:
        it, inn = 1 / sides["Tak"]["price"], 1 / sides["Nie"]["price"]
        fair = it / (it + inn)
    gr.append({"superbet_event_id": eid, "subject": subj, "y": 1 if any_["dd"] else 0,
               "dd_pra_only": any_["dd_pra_only"], "p_ind": p_ind, "fair": fair,
               "tak": sides.get("Tak", {}).get("price"), "nie": sides.get("Nie", {}).get("price"),
               "tournament": any_["tournament"], "shadow_day": any_["shadow_day"],
               "box_vals": any_.get("box_vals")})
print("graded players", len(gr), "two-sided", sum(1 for x in gr if x["fair"] is not None),
      "with model", sum(1 for x in gr if x["p_ind"] is not None),
      "both", sum(1 for x in gr if x["fair"] is not None and x["p_ind"] is not None))
print("DD via steals/blocks (not pts/reb/ast pair):", sum(1 for x in gr if x["y"] and not x["dd_pra_only"]))
both = [x for x in gr if x["fair"] is not None and x["p_ind"] is not None]
if both:
    for x in both:
        x["model_p"], x["q"] = x["p_ind"], x["fair"]
    n = len(both)
    print(f"Tak side: n {n} ev {len({x['superbet_event_id'] for x in both})} DD rate {sum(x['y'] for x in both)/n:.3f} "
          f"model {sum(x['p_ind'] for x in both)/n:.3f} fair {sum(x['fair'] for x in both)/n:.3f}")
    print("Brier diff (model - fair) x1e3", fmt(boot(both, brier_diff)), "logloss x1e3", fmt(boot(both, ll_diff)))
    print("by league", Counter(lg(x["tournament"]) for x in both))
    for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.0)):
        rs = [x for x in both if lo <= x["p_ind"] < hi]
        if rs:
            print(f" model {lo}-{hi}: n {len(rs)} model {sum(x['p_ind'] for x in rs)/len(rs):.3f} "
                  f"fair {sum(x['fair'] for x in rs)/len(rs):.3f} DD {sum(x['y'] for x in rs)/len(rs):.3f}")
    # Nie side gates: confidence = 1 - p_ind
    nie = [{"superbet_event_id": x["superbet_event_id"], "y": 1 - x["y"], "model_p": 1 - x["p_ind"],
            "q": 1 / x["nie"], "price": x["nie"], "fair": 1 - x["fair"], "shadow_day": x["shadow_day"],
            "ovr": 1 / x["tak"] + 1 / x["nie"] - 1} for x in both]
    tak = [{"superbet_event_id": x["superbet_event_id"], "y": x["y"], "model_p": x["p_ind"],
            "q": 1 / x["tak"], "price": x["tak"], "fair": x["fair"], "shadow_day": x["shadow_day"],
            "ovr": 1 / x["tak"] + 1 / x["nie"] - 1} for x in both]
    days = len({x["shadow_day"] for x in both})
    for name, side in (("Nie", nie), ("Tak", tak)):
        gt = [r for r in side if r["model_p"] >= 0.70 and r["model_p"] * r["price"] >= 0.90 and r["ovr"] <= 0.15]
        if gt:
            print(f"gate {name}: n {len(gt)} ({len(gt)/days:.1f}/day) hit {sum(r['y'] for r in gt)/len(gt):.3f} "
                  f"conf {sum(r['model_p'] for r in gt)/len(gt):.3f} fair {sum(r['fair'] for r in gt)/len(gt):.3f} "
                  f"1/odds {sum(r['q'] for r in gt)/len(gt):.3f} ROI {fmt(boot(gt, roi), 100)}% "
                  f"tax {fmt(boot(gt, lambda x: roi(x, TAX)), 100)}%")
        else:
            print("gate", name, "none")
    # fair p calibration of the book on Nie >= 0.70
    for lo, hi in ((0.6, 0.7), (0.7, 0.8), (0.8, 0.92), (0.92, 1.0)):
        rs = [r for r in nie if lo <= r["model_p"] < hi]
        if rs:
            print(f" Nie model band {lo}-{hi}: n {len(rs)} claimed {sum(r['model_p'] for r in rs)/len(rs):.3f} "
                  f"hit {sum(r['y'] for r in rs)/len(rs):.3f} fair {sum(r['fair'] for r in rs)/len(rs):.3f}")
json.dump(gr, open(f"{S}/dd_graded.json", "w"))

# ---------------------------------------------------------------- extras
print("\n== milestones: same-sample Platt per league (both model and price)")
for L in ("NBA", "EL", "inne"):
    rs = [r for r in g if lg(r["tournament"]) == L]
    fm_, _ = platt([r["model_p"] for r in rs], [r["y"] for r in rs])
    fq_, _ = platt([r["q"] for r in rs], [r["y"] for r in rs])
    for r in rs:
        r["mpl"], r["qpl"] = fm_(r["model_p"]), fq_(r["q"])
    t = boot(rs, lambda x: sum((r["mpl"] - r["y"]) ** 2 - (r["qpl"] - r["y"]) ** 2 for r in x) / len(x))
    print(L, "n", len(rs), "Brier diff after Platt x1e3", fmt(t))
print("\n== milestones: calibration of model per league, 0.70-0.92")
for L in ("NBA", "EL", "inne"):
    rs = [r for r in g if lg(r["tournament"]) == L and 0.70 <= r["model_p"] < 0.92]
    t = boot(rs, lambda x: sum(r["y"] - r["model_p"] for r in x) / len(x))
    print(L, "n", len(rs), "claimed %.3f hit %.3f 1/price %.3f gap pp %+.1f [%+.1f; %+.1f]" % (
        sum(r["model_p"] for r in rs) / len(rs), sum(r["y"] for r in rs) / len(rs),
        sum(r["q"] for r in rs) / len(rs), t[0] * 100, t[1] * 100, t[2] * 100))
print("\n== milestones: by model_n (own sample size), 0.70-0.92")
for lo, hi in ((5, 10), (10, 20), (20, 61)):
    rs = [r for r in g if lo <= (r["model_n"] or 0) < hi and 0.70 <= r["model_p"] < 0.92]
    if rs:
        print(f"n {lo}-{hi}: rows {len(rs)} claimed {sum(r['model_p'] for r in rs)/len(rs):.3f} hit {sum(r['y'] for r in rs)/len(rs):.3f}")
print("\n== milestones in-zone: hit vs 1/price per family / N")
zz = defaultdict(list)
for r in g:
    if 1.09 <= r["price"] <= 1.43:
        zz[(r["family"], r["N"])].append(r)
for k in sorted(zz):
    rs = zz[k]
    if len(rs) >= 100:
        print(k, "n", len(rs), "hit %.3f 1/price %.3f model %.3f ROI %+.1f%%" % (
            sum(r["y"] for r in rs) / len(rs), sum(r["q"] for r in rs) / len(rs),
            sum(r["model_p"] for r in rs) / len(rs), 100 * roi(rs)))

if both:
    print("\n== double-double: power de-vig (margin on the long shot) as the book")
    for x in both:
        a, b = 1 / x["tak"], 1 / x["nie"]
        lo_, hi_ = 1.0, 3.0
        for _ in range(60):
            k = (lo_ + hi_) / 2
            if a ** k + b ** k > 1:
                lo_ = k
            else:
                hi_ = k
        x["q_pow"] = a ** k
    t = boot(both, lambda x: sum((r["p_ind"] - r["y"]) ** 2 - (r["q_pow"] - r["y"]) ** 2 for r in x) / len(x))
    print("Brier model - power fair x1e3", fmt(t), "mean power fair %.3f" % (sum(x["q_pow"] for x in both) / len(both)))
    fm_, _ = platt([x["p_ind"] for x in both], [x["y"] for x in both])
    fq_, _ = platt([x["fair"] for x in both], [x["y"] for x in both])
    t = boot(both, lambda x: sum((fm_(r["p_ind"]) - r["y"]) ** 2 - (fq_(r["fair"]) - r["y"]) ** 2 for r in x) / len(x))
    print("after same-sample Platt on both x1e3", fmt(t))
    for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 1.0)):
        rs = [x for x in both if lo <= x["q_pow"] < hi]
        if rs:
            print(f" power fair {lo}-{hi}: n {len(rs)} fair_pow {sum(x['q_pow'] for x in rs)/len(rs):.3f} "
                  f"fair_prop {sum(x['fair'] for x in rs)/len(rs):.3f} DD {sum(x['y'] for x in rs)/len(rs):.3f} model {sum(x['p_ind'] for x in rs)/len(rs):.3f}")
    # Nie in the zone, hit vs 1/odds
    zn = [r for r in nie if 1.09 <= r["price"] <= 1.43]
    print("Nie zone 1.09-1.43: n", len(zn), "hit %.3f 1/odds %.3f model %.3f ROI %s%%" % (
        sum(r["y"] for r in zn) / len(zn), sum(r["q"] for r in zn) / len(zn),
        sum(r["model_p"] for r in zn) / len(zn), fmt(boot(zn, roi), 100)))
    alln = nie
    print("Nie all: n", len(alln), "hit %.3f 1/odds %.3f ROI %s%%" % (
        sum(r["y"] for r in alln) / len(alln), sum(r["q"] for r in alln) / len(alln), fmt(boot(alln, roi), 100)))
    print("Tak all: n", len(tak), "hit %.3f 1/odds %.3f ROI %s%%" % (
        sum(r["y"] for r in tak) / len(tak), sum(r["q"] for r in tak) / len(tak), fmt(boot(tak, roi), 100)))
    # model independence error on the offered set: model vs realised DD by band (Tak)
