"""Step 3 (+4 curve): model vs price on graded live selections 11-06..11-19; calibration bands; the gates.
Needs live_eval.jsonl.gz and (for the curve variant) history_rows.jsonl.gz."""
import gzip, json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path[:0] = [str(Path(__file__).parent)]
import numpy as np
from stats import boot_ratio, wilson_lo, bucket, EDGES, fmt

S = Path(sys.argv[1])
dup = json.load(open(S / "step1_same_event_printable.json"))
DUPLAB = set()
for cand, c in dup.items():
    for d in c["dups"]:
        gk, label = d.split(" = ")[0].split(" ", 1)
        DUPLAB.add((cand, gk, label))

def key(cand, label):
    tail = label.split(":")[-1]
    return f"{cand}|{tail}" if tail in ("tak", "nie") else f"{cand}|OVER"

# history curve (Wilson lo95 per EDGES bucket, n >= 100; all classes pooled)
curve = defaultdict(lambda: defaultdict(lambda: [0, 0]))
hist_path = S / "history_rows.jsonl.gz"
if hist_path.exists():
    for line in gzip.open(hist_path, "rt"):
        eid, ts, women, cand, gk, label, p, y = json.loads(line)
        if cand.startswith("half") and cand.endswith("handicap") and "(-" in label:
            continue
        c = curve[key(cand, label)][bucket(p)]
        c[0] += y; c[1] += 1
def conf_curve(cand, label, p):
    c = curve.get(key(cand, label), {}).get(bucket(p))
    if not c or c[1] < 100:
        return None
    return wilson_lo(c[0], c[1])

rows = [json.loads(l) for l in gzip.open(S / "live_eval.jsonl.gz", "rt")]
rows = [r for r in rows if r["complete"] and r["p_sim"] is not None and r["y"] in (0, 1, "REFUND")]
out = {}
for cand in sorted({r["cand"] for r in rows}):
    rs = [r for r in rows if r["cand"] == cand]
    res = {}
    dnb = cand.endswith("_dnb")
    graded = [r for r in rs if r["y"] in (0, 1)]
    # fair p for a DNB pair is already conditional on no draw (2-way price); sim p conditional too
    # 1) one row per group: the side with the higher fair p (chosen before the result)
    by_g = defaultdict(list)
    for r in graded:
        by_g[(r["eid"], r["gk"])].append(r)
    one = [max(g, key=lambda r: (r["fair"], r["label"])) for g in by_g.values() if len(g) >= 2]
    if one:
        e = [r["eid"] for r in one]
        bs = [(r["p_sim"] - r["y"]) ** 2 for r in one]
        bf = [(r["fair"] - r["y"]) ** 2 for r in one]
        clip = lambda p: min(max(p, 1e-4), 1 - 1e-4)
        ls = [-math.log(clip(r["p_sim"]) if r["y"] else 1 - clip(r["p_sim"])) for r in one]
        lf = [-math.log(clip(r["fair"]) if r["y"] else 1 - clip(r["fair"])) for r in one]
        res["scored_rows"] = len(one); res["matches"] = len(set(e))
        res["brier_sim"] = round(float(np.mean(bs)), 5); res["brier_price"] = round(float(np.mean(bf)), 5)
        res["brier_sim_minus_price"] = fmt(boot_ratio(e, np.array(bs) - np.array(bf)), 4)
        res["logloss_sim_minus_price"] = fmt(boot_ratio(e, np.array(ls) - np.array(lf)), 4)
        res["mean_p_sim_vs_fair_vs_hit"] = [round(float(np.mean([r["p_sim"] for r in one])), 4), round(float(np.mean([r["fair"] for r in one])), 4), round(float(np.mean([r["y"] for r in one])), 4)]
    # 2) calibration bands, every selection (both sides), sim p and fair p
    bands = {}
    for who in ("p_sim", "fair"):
        for lo, hi in ((0.60, 0.70), (0.70, 0.80), (0.80, 0.92)):
            b = [r for r in graded if lo <= r[who] < hi and (r["cand"], r["gk"], r["label"]) not in DUPLAB]
            if len(b) < 10:
                bands[f"{who} {lo:.2f}-{hi:.2f}"] = {"n": len(b)}
                continue
            t = boot_ratio([r["eid"] for r in b], [r["y"] - r[who] for r in b])
            bands[f"{who} {lo:.2f}-{hi:.2f}"] = {"n": len(b), "claimed": round(float(np.mean([r[who] for r in b])), 4),
                                                 "realised": round(float(np.mean([r["y"] for r in b])), 4),
                                                 "realised_minus_claimed_pp": fmt(t, 1, pct=True)}
    res["bands"] = bands
    # 3) the gates: conf >= 0.70, conf x odds >= 0.90, overround <= 1.15, odds >= 1/0.9202, not a printable duplicate
    for variant in ("raw", "curve"):
        legs = []
        for r in rs:
            if (r["cand"], r["gk"], r["label"]) in DUPLAB:
                continue
            conf = r["p_sim"] if variant == "raw" else conf_curve(r["cand"], r["label"], r["p_sim"])
            if conf is None or conf < 0.70 or conf * r["price"] < 0.90 or r["overround"] > 1.15 or r["price"] < 1 / 0.9202:
                continue
            legs.append({**r, "conf": conf})
        g = [l for l in legs if l["y"] in (0, 1)]
        refunds = sum(1 for l in legs if l["y"] == "REFUND")
        v = {"legs": len(legs), "graded": len(g), "refunds": refunds, "days": len({l["day"] for l in legs})}
        if g:
            e = [l["eid"] for l in g]
            v["per_day"] = dict(sorted(Counter(l["day"][5:] for l in legs).items()))
            v["conf_mean"] = round(float(np.mean([l["conf"] for l in g])), 4)
            v["hit"] = round(float(np.mean([l["y"] for l in g])), 4)
            v["inv_odds_mean"] = round(float(np.mean([1 / l["price"] for l in g])), 4)
            v["fair_mean"] = round(float(np.mean([l["fair"] for l in g])), 4)
            v["hit_minus_conf_pp"] = fmt(boot_ratio(e, [l["y"] - l["conf"] for l in g]), 1, pct=True)
            v["hit_minus_fair_pp"] = fmt(boot_ratio(e, [l["y"] - l["fair"] for l in g]), 1, pct=True)
            v["roi_pct"] = fmt(boot_ratio(e, [l["y"] * l["price"] - 1 for l in g]), 1, pct=True)
            v["roi_after_tax_pct"] = fmt(boot_ratio(e, [l["y"] * 0.88 * l["price"] - 1 for l in g]), 1, pct=True)
            v["by_label"] = Counter(l["label"].split(":")[-1] if ":" in l["label"] else l["gk"] for l in legs).most_common(8)
        res[f"gates_{variant}"] = v
    out[cand] = res
json.dump(out, open(S / "step3_results.json", "w"), indent=1, ensure_ascii=False)
for c, v in out.items():
    print("=====", c)
    print(json.dumps(v, ensure_ascii=False, indent=1))
