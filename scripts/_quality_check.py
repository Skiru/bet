#!/usr/bin/env python3
"""Quick quality check on tipster consensus output."""
import json
from collections import Counter

d = json.load(open("betting/data/2026-05-10_tipster_consensus.json"))
picks = d["all_picks"]
consensus = d["consensus"]

# Garbage check
garbage = []
for p in picks:
    e = p["event"]
    parts = e.split(" vs ")
    if len(parts) != 2:
        garbage.append(f'NO-VS [{p["source_site"]}] {e[:60]}')
        continue
    h, a = parts
    for n in (h, a):
        nl = n.lower()
        if len(n) <= 2:
            garbage.append(f'[{p["source_site"]}] {e[:60]}')
            break
        if any(x in nl for x in [
            "view", "page", "predict", "betting site", "fans", "modern",
            "not found", "guide", "review", "advice", "service", "incredibly",
            "bookmaker", "telegram", "fanpage"
        ]):
            garbage.append(f'[{p["source_site"]}] {e[:60]}')
            break

print(f"Garbage: {len(garbage)}")
for g in garbage:
    print(f"  {g}")

# Stats
stat = sum(1 for p in picks if p.get("market_type") == "statistical")
print(f"\nTotal: {len(picks)} picks, {stat} statistical, {len(consensus)} events")

# By source
src = Counter(p["source_site"] for p in picks)
for s, c in src.most_common():
    print(f"  {s}: {c}")

# ZawodTyper sample
zw = [p for p in picks if p["source_site"] == "ZawodTyper"][:5]
print(f"\n=== ZawodTyper sample ===")
for p in zw:
    print(f"  {p['event'][:45]} | m={p.get('market','?')[:25]} | d={p.get('direction','?')}")

# BetIdeas sample
bi = [p for p in picks if p["source_site"] == "BetIdeas"][:5]
print(f"\n=== BetIdeas sample ===")
for p in bi:
    print(f"  {p['event'][:45]} | m={p.get('market','?')[:25]} | d={p.get('direction','?')}")

# Feedinco sample
fi = [p for p in picks if p["source_site"] == "Feedinco"][:5]
print(f"\n=== Feedinco sample ===")
for p in fi:
    print(f"  {p['event'][:45]} | m={p.get('market','?')[:25]} | d={p.get('direction','?')}")

# Multi-tipster events
multi = [c for c in consensus if c["total_tipsters"] >= 2]
print(f"\n=== Multi-tipster: {len(multi)} ===")
for m in multi[:15]:
    print(f"  {m['event'][:40]} | {m['total_tipsters']} tips | {m.get('consensus_market','?')[:20]} | {m.get('consensus_direction','?')}")

# Market breakdown
markets = Counter()
for p in picks:
    m = p.get("market", "N/A")
    if m == "N/A":
        markets["N/A"] += 1
    else:
        markets[m[:30]] += 1
print(f"\n=== Markets ===")
for m, c in markets.most_common(15):
    print(f"  {c:3}x {m}")
