#!/usr/bin/env python3
"""Temporary script to analyze S3 deep stats output."""
import json
import sys
from pathlib import Path

path = sys.argv[1] if len(sys.argv) > 1 else "betting/data/2026-05-11_s3_deep_stats.json"
if not Path(path).exists():
    print(f"ERROR: File not found: {path}")
    sys.exit(1)
with open(path) as f:
    data = json.load(f)

total = data["total_candidates"]
with_data = data["candidates_with_data"]
print(f"Total candidates: {total}")
print(f"With data: {with_data}")

safety_scores = []
dq_labels = {}
sports = {}
markets_per = []
h2h_blind = 0
no_market = 0
top_picks = []

for a in data["analyses"]:
    bm = a.get("best_market")
    sport = a["sport"]
    sports[sport] = sports.get(sport, 0) + 1
    dq = a.get("data_quality", {})
    label = dq.get("label", "?")
    dq_labels[label] = dq_labels.get(label, 0) + 1
    me = a.get("markets_evaluated", 0)
    markets_per.append(me)
    if bm:
        safety_scores.append(bm["safety_score"])
        if bm.get("h2h_blind"):
            h2h_blind += 1
        if bm["safety_score"] >= 0.45:
            top_picks.append({
                "match": f"{a['home_team']} vs {a['away_team']}",
                "sport": sport,
                "market": bm["name"],
                "direction": bm["direction"],
                "line": bm["line"],
                "safety": bm["safety_score"],
                "l10_avg": bm["combined_avg"],
                "h2h_avg": bm.get("h2h_avg"),
                "h2h_blind": bm.get("h2h_blind"),
                "hit_l10": bm.get("hit_rate_l10"),
                "hit_h2h": bm.get("hit_rate_h2h"),
                "dq": label,
                "comp": a.get("competition", ""),
            })
    else:
        no_market += 1

avg_s = sum(safety_scores) / len(safety_scores) if safety_scores else 0
max_s = max(safety_scores) if safety_scores else 0
min_s = min(safety_scores) if safety_scores else 0
avg_m = sum(markets_per) / len(markets_per) if markets_per else 0

print(f"\n=== Safety Score Stats ===")
print(f"  avg: {avg_s:.3f}, max: {max_s:.3f}, min: {min_s:.3f}")
print(f"  H2H-blind: {h2h_blind}/{len(safety_scores)}")
print(f"  No market: {no_market}")

print(f"\n=== Data Quality ===")
for k, v in sorted(dq_labels.items()):
    print(f"  {k}: {v}")

print(f"\n=== Sports ===")
for k, v in sorted(sports.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

print(f"\n=== Avg markets/candidate: {avg_m:.1f} ===")

buckets = {"0.00-0.19": 0, "0.20-0.39": 0, "0.40-0.59": 0, "0.60-0.79": 0, "0.80-1.00": 0}
for s in safety_scores:
    if s < 0.20: buckets["0.00-0.19"] += 1
    elif s < 0.40: buckets["0.20-0.39"] += 1
    elif s < 0.60: buckets["0.40-0.59"] += 1
    elif s < 0.80: buckets["0.60-0.79"] += 1
    else: buckets["0.80-1.00"] += 1
print(f"\n=== Safety Distribution ===")
for k, v in buckets.items():
    pct = v / len(safety_scores) * 100 if safety_scores else 0
    print(f"  {k}: {v} ({pct:.0f}%)")

# Top picks sorted by safety
top_picks.sort(key=lambda x: x["safety"], reverse=True)
print(f"\n=== TOP {min(30, len(top_picks))} CANDIDATES (safety >= 0.45) ===")
for i, p in enumerate(top_picks[:30], 1):
    h2h_str = f"H2H:{p['h2h_avg']}" if p['h2h_avg'] is not None else "H2H-BLIND"
    print(f"  {i}. [{p['sport'][:4].upper()}] {p['match']}")
    print(f"     {p['market']} {p['direction']} {p['line']} | Safety={p['safety']:.2f} | L10={p['l10_avg']} | {h2h_str} | Hit={p['hit_l10']}/{p['hit_h2h']} | DQ={p['dq']} | {p['comp']}")
