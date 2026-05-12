#!/usr/bin/env python3
"""Temporary script to analyze tipster argument quality for S2."""
import json
import sys
from pathlib import Path
from collections import Counter

DATA = Path(__file__).parent.parent / "betting" / "data"
d = json.load(open(DATA / "2026-05-12_tipster_consensus.json"))
picks = d["all_picks"]

# === 1. Reasoning quality per source ===
print("=" * 60)
print("FEEDINCO — 24 picks")
print("=" * 60)
feed = [p for p in picks if p["source_site"] == "Feedinco"]
for p in feed[:6]:
    print(f'  {p["home_team"]} vs {p["away_team"]} | {p["market"]} {p["direction"]}')
    r = p.get("reasoning", "")
    if r:
        print(f'    Reasoning: {r[:250]}')
    print()

print("=" * 60)
print("BETTINGCLOSED — 17 picks")
print("=" * 60)
bc = [p for p in picks if p["source_site"] == "BettingClosed"]
for p in bc[:6]:
    print(f'  {p["home_team"]} vs {p["away_team"]} | {p["market"]} {p["direction"]}')
    r = p.get("reasoning", "")
    if r:
        print(f'    Reasoning: {r[:250]}')
    print()

print("=" * 60)
print("BETIDEAS — 10 picks")
print("=" * 60)
bi = [p for p in picks if p["source_site"] == "BetIdeas"]
for p in bi[:6]:
    print(f'  {p["home_team"]} vs {p["away_team"]} | {p["market"]} {p["direction"]}')
    r = p.get("reasoning", "")
    if r:
        print(f'    Reasoning: {r[:250]}')
    print()

# === 2. ZawodTyper stats_cited ===
print("=" * 60)
print("ZAWODTYPER — stats_cited content")
print("=" * 60)
zaw = [p for p in picks if p["source_site"] == "ZawodTyper"]
for p in zaw:
    sc = p.get("stats_cited", [])
    if sc:
        print(f'  {p["home_team"]} vs {p["away_team"]} | {p["market"]} {p["direction"]} odds={p.get("odds")}')
        print(f'    Stats: {sc[:5]}')
        print()

# === 3. Consensus events (multi-source agreement) ===
print("=" * 60)
print("CONSENSUS — events with picks from 2+ sources")
print("=" * 60)
event_sources = {}
for p in picks:
    key = f'{p.get("home_team","")}|{p.get("away_team","")}'
    if key not in event_sources:
        event_sources[key] = []
    event_sources[key].append(p)

multi_source = {k: v for k, v in event_sources.items() if len(set(p["source_site"] for p in v)) >= 2}
print(f"Events with 2+ sources: {len(multi_source)}")
for key, tips in sorted(multi_source.items(), key=lambda x: -len(x[1])):
    sources = list(set(t["source_site"] for t in tips))
    markets = [(t["market"], t["direction"], t["source_site"]) for t in tips]
    print(f'  {key.replace("|", " vs ")} ({len(tips)} tips from {len(sources)} sources)')
    for m, dir_, src in markets:
        print(f'    {src}: {m} {dir_}')
    print()

# === 4. Statistical market picks breakdown ===
print("=" * 60)
print("STATISTICAL MARKET PICKS (77 total)")
print("=" * 60)
stat_picks = [p for p in picks if p.get("market_type") == "statistical"]
by_sport = Counter(p.get("sport", "unknown") for p in stat_picks)
print(f"By sport: {dict(by_sport)}")
by_source = Counter(p["source_site"] for p in stat_picks)
print(f"By source: {dict(by_source)}")
print()
for p in stat_picks[:15]:
    print(f'  [{p["source_site"]}] {p["home_team"]} vs {p["away_team"]} | {p["market"]} {p["direction"]} odds={p.get("odds")}')
