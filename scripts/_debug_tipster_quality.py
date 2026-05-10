#!/usr/bin/env python3
"""Analyze tipster consensus quality after fix."""
import json
from pathlib import Path

data = json.load(open(Path(__file__).parent.parent / "betting/data/2026-05-10_tipster_consensus.json"))

picks = data.get("all_picks", [])
print(f"Total picks: {len(picks)}")

# Market types
from collections import Counter
stat = sum(1 for p in picks if p.get("market_type") == "statistical")
out = sum(1 for p in picks if p.get("market_type") == "outcome")
print(f"Statistical: {stat}, Outcome: {out}")

# Market text distribution
markets = Counter(p.get("market", "N/A") for p in picks)
print("\n=== MARKETS ===")
for m, c in markets.most_common(20):
    mt = next((p["market_type"] for p in picks if p.get("market") == m), "?")
    print(f"  [{mt[:4]}] {c:>3}x  {m}")

# Direction distribution
dirs = Counter(p.get("direction", "?") for p in picks)
print("\n=== DIRECTIONS ===")
for d, c in dirs.most_common():
    print(f"  {d}: {c}")

# Events by sport
sports = Counter(p.get("sport", "?") for p in picks)
print("\n=== SPORTS ===")
for s, c in sports.most_common():
    print(f"  {s}: {c}")

# Events by source
sources = Counter(p.get("source_site", "?") for p in picks)
print("\n=== SOURCES ===")
for s, c in sources.most_common():
    print(f"  {s}: {c}")

# Show sample picks
print("\n=== SAMPLE PICKS ===")
for p in picks[:10]:
    print(f"  [{p.get('source_site','')}] {p.get('event','?')[:45]}")
    print(f"    Market: {p.get('market','?')}")
    print(f"    Type: {p.get('market_type','?')} | Dir: {p.get('direction','?')} | Odds: {p.get('odds')}")
    reas = p.get("reasoning", "")[:120]
    if reas:
        print(f"    Reasoning: {reas}")
    print()

# Consensus quality
consensus = data.get("consensus", [])
print(f"\n=== CONSENSUS ({len(consensus)} events) ===")
for c in consensus[:10]:
    print(f"  [{c.get('sport','')}] {c.get('event','?')[:40]} | "
          f"{c.get('total_tipsters',0)} tip | {c.get('agreement_pct',0):.0f}% agree | "
          f"market: {c.get('consensus_market','?')[:30]} | dir: {c.get('consensus_direction','?')}")

# Site results
print("\n=== SITE RESULTS ===")
for r in data.get("site_results", []):
    print(f"  {r['site_name']:15s}: {r['status']:8s} {r['pick_count']:>3} picks  {r['fetch_time_ms']:>5}ms  {r.get('error','')[:80]}")
