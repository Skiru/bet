"""Variant C: history curve (Wilson lo95) lowered by today's football pooled line-evidence offset by price gap
(what a NEW key with no settled lines reads: line_evidence.gap_offset with an empty key cell = the sport pool,
config/sofa_superbet_line_evidence.json, fitted 2026-11-20); the price-band cap NOT applied (named).
Then every gate; plus a power de-vig Brier robustness for the picks."""
import gzip, json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path[:0] = ["src", ".", str(Path(__file__).parent)]
import numpy as np
from stats import boot_ratio, wilson_lo, bucket, fmt
from bet.sofa.line_evidence import price_gap_bucket
S = Path(sys.argv[1])
doc = json.load(open("config/sofa_superbet_line_evidence.json"))
pool = doc["sport_printable_by_gap"]["football"]
def key(cand, label):
    tail = label.split(":")[-1]
    return f"{cand}|{tail}" if tail in ("tak", "nie") else f"{cand}|OVER"
curve = defaultdict(lambda: defaultdict(lambda: [0, 0]))
for line in gzip.open(S / "history_rows.jsonl.gz", "rt"):
    eid, ts, women, cand, gk, label, p, y = json.loads(line)
    if cand.startswith("half") and cand.endswith("handicap") and "(-" in label:
        continue
    c = curve[key(cand, label)][bucket(p)]; c[0] += y; c[1] += 1
dup = json.load(open(S / "step1_same_event_printable.json"))
D = set()
for c, v in dup.items():
    for d in v["dups"]:
        gk, lab = d.split(" = ")[0].split(" ", 1); D.add((c, gk, lab))
rows = [json.loads(l) for l in gzip.open(S / "live_eval.jsonl.gz", "rt")]
rows = [r for r in rows if r["complete"] and r["p_sim"] is not None and r["y"] in (0, 1)]
out = {}
for cand in ("half1_handicap", "half2_handicap", "side_wins_both_halves", "draw_both_halves", "btts_and_over"):
    legs = []
    for r in rows:
        if r["cand"] != cand or (cand, r["gk"], r["label"]) in D:
            continue
        cc = curve[key(cand, r["label"])].get(bucket(r["p_sim"]))
        if not cc or cc[1] < 100:
            continue
        cv = wilson_lo(*cc)
        lab = price_gap_bucket(cv, r["price"])
        off = min(float(pool[lab]["gap"]), 0.0) if lab in pool else 0.0
        conf = cv + off
        if conf < 0.70 or conf * r["price"] < 0.90 or r["overround"] > 1.15 or r["price"] < 1 / 0.9202:
            continue
        legs.append({**r, "conf": conf})
    e = [l["eid"] for l in legs]
    v = {"legs": len(legs), "per_day_mean": round(len(legs) / 14, 1)}
    if legs:
        v |= {"conf_mean": round(float(np.mean([l["conf"] for l in legs])), 4), "hit": round(float(np.mean([l["y"] for l in legs])), 4),
              "inv_odds": round(float(np.mean([1 / l["price"] for l in legs])), 4),
              "hit_minus_conf_pp": fmt(boot_ratio(e, [l["y"] - l["conf"] for l in legs]), 1, pct=True),
              "roi_pct": fmt(boot_ratio(e, [l["y"] * l["price"] - 1 for l in legs]), 1, pct=True),
              "roi_after_tax_pct": fmt(boot_ratio(e, [l["y"] * 0.88 * l["price"] - 1 for l in legs]), 1, pct=True),
              "by_line": Counter(l["label"] for l in legs).most_common(6)}
    out[cand] = v
    print("C", cand, v)
# power de-vig robustness: p_i = (1/o_i)^k, sum = 1 (two-way groups), Brier of the higher-fair side
def power(o1, o2):
    lo, hi = 1.0, 5.0
    for _ in range(60):
        k = (lo + hi) / 2
        s = (1 / o1) ** k + (1 / o2) ** k
        lo, hi = (k, hi) if s > 1 else (lo, k)
    return (1 / o1) ** k
for cand in ("half1_handicap", "half2_handicap", "side_wins_both_halves", "draw_both_halves", "btts_and_over"):
    g = defaultdict(list)
    for r in rows:
        if r["cand"] == cand:
            g[(r["eid"], r["gk"])].append(r)
    e, d = [], []
    for rs in g.values():
        if len(rs) != 2:
            continue
        a, b = sorted(rs, key=lambda r: -r["fair"])
        pw = power(a["price"], b["price"])
        e.append(a["eid"]); d.append((a["p_sim"] - a["y"]) ** 2 - (pw - a["y"]) ** 2)
    t = boot_ratio(e, d)
    out[cand + "_brier_vs_power_devig"] = fmt(t, 4)
    print("power de-vig", cand, "Brier sim - price", fmt(t, 4), "n", len(d))
json.dump(out, open(S / "step3c_results.json", "w"), indent=1)
