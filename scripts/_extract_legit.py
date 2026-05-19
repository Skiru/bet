"""Extract legitimate picks from S3 deep stats for coupon rebuild."""
import json
import sys

with open("betting/data/2026-05-19_s3_deep_stats.json") as f:
    data = json.load(f)

analyses = data["analyses"]

# Get top candidates: real source, best markets with hit_rate > 5/10
top = []
for a in analyses:
    if a.get("markets_evaluated", 0) < 3:
        continue
    for m in a.get("ranking", []):
        if m.get("source") != "db":
            continue
        hr = m.get("hit_rate_l10", "0/10")
        try:
            num = int(hr.split("/")[0])
        except Exception:
            num = 0
        if num >= 6:  # > 5/10
            top.append({
                "event": f"{a['home_team']} v {a['away_team']}",
                "sport": a.get("sport"),
                "comp": a.get("competition", ""),
                "kickoff": a.get("kickoff", ""),
                "market": m["name"],
                "line": m.get("line"),
                "direction": m.get("direction"),
                "hit_rate_l10": hr,
                "hit_rate_l5": m.get("hit_rate_l5", "?"),
                "safety_score": m.get("safety_score", 0),
                "combined_avg": m.get("combined_avg"),
                "margin": m.get("margin", 0),
                "three_way": m.get("three_way_check", {}).get("alignment", "?"),
                "fixture_id": a.get("fixture_id"),
            })

# Sort by safety_score desc, then hit_rate
top.sort(key=lambda x: (-x["safety_score"], -int(x["hit_rate_l10"].split("/")[0])))
print(f"Total qualifying markets (source=db, hit_rate>=6/10): {len(top)}")
print()
print("TOP PICKS FOR COUPON:")
for i, p in enumerate(top[:40], 1):
    print(f"{i:2d}. [{p['sport'][:4]}] {p['event']}")
    print(f"    Market: {p['market']} {p['direction']} {p['line']}  |  HR={p['hit_rate_l10']} L5={p['hit_rate_l5']}  |  ss={p['safety_score']:.2f}  |  avg={p['combined_avg']}  |  {p['three_way']}")
    print(f"    Comp: {p['comp']}  |  Kickoff: {p['kickoff']}")
    print()

# Save for coupon builder
with open("betting/data/2026-05-19_legit_picks.json", "w") as f:
    json.dump(top, f, indent=2)
print(f"\nSaved {len(top)} picks to betting/data/2026-05-19_legit_picks.json")
