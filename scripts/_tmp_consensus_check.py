#!/usr/bin/env python3
"""Check enriched shortlist and consensus overlap."""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "betting" / "data"
d = json.load(open(DATA / "2026-05-12_tipster_consensus.json"))
consensus = d.get("consensus", [])

# Top consensus events (highest tipster count + stat markets)
print("TOP CONSENSUS EVENTS (by total_tipsters):")
print("=" * 70)
top = sorted(consensus, key=lambda x: -x.get("total_tipsters", 0))
for e in top[:15]:
    print(f'  {e["event"]} [{e.get("sport","")}]')
    print(f'    Tipsters: {e["total_tipsters"]} | Agreement: {e.get("agreement_pct",0)}% | Stat picks: {e.get("statistical_picks",0)} | Outcome: {e.get("outcome_picks",0)}')
    print(f'    Consensus market: {e.get("consensus_market","?")} {e.get("consensus_direction","?")}')
    # Check has_stats_backing
    if e.get("has_stats_backing"):
        print(f'    Has stats backing: YES')
    print()

# Check enriched shortlist for tipster_support
print("\n\nENRICHED SHORTLIST — candidates with tipster_support:")
print("=" * 70)
sl = json.load(open(DATA / "2026-05-12_s2_shortlist.json"))
candidates = sl.get("candidates", [])
with_tips = [c for c in candidates if c.get("tipster_support")]
print(f"Total candidates: {len(candidates)}, with tipster support: {len(with_tips)}")
for c in with_tips[:20]:
    ts = c["tipster_support"]
    print(f'  [{c.get("sport","")}] {c["home_team"]} vs {c["away_team"]} (score={c.get("score",0)})')
    print(f'    Tipsters: {ts["count"]} from {ts["tipsters"]}')
    # Show market details from tips
    for t in ts.get("tips", [])[:3]:
        m = t.get("market", "N/A")
        d_val = t.get("direction", "?")
        print(f'      → {t.get("source_site","?")}: {m} {d_val}')
    print()
