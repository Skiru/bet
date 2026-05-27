#!/usr/bin/env python3
"""Inspect deep stats results for night events."""
import json

with open("betting/data/2026-05-26_s3_deep_stats.json") as f:
    data = json.load(f)

# Check structure
print(f"Top-level keys: {list(data.keys())}")
analyses = data.get("analyses", data.get("candidates", data.get("results", [])))
print(f"Analyses count: {len(analyses)}")

# Properly extract event names
if analyses:
    print(f"\nFirst entry keys: {list(analyses[0].keys())}")
    
ranked = []
for a in analyses:
    bm = a.get("best_market", {})
    if not bm:
        continue
    safety = bm.get("safety_score", 0) or 0
    # Try different event name keys
    event = a.get("event_name") or a.get("name") or a.get("fixture") or f"{a.get('home_team','?')} vs {a.get('away_team','?')}"
    ranked.append((safety, event, a))

ranked.sort(key=lambda x: -x[0])

print(f"\n{'='*120}")
print(f"{'#':<3} {'Event':<55} {'Market':<25} {'Dir':<6} {'Safety':<7} {'L10':<7} {'L5':<6} {'H2H':<6} {'Combined Avg'}")
print(f"{'='*120}")
for i, (safety, event, a) in enumerate(ranked, 1):
    bm = a.get("best_market", {})
    market = bm.get("name", "?")[:23]
    direction = bm.get("direction", "?")
    l10 = bm.get("hit_rate_l10", "N/A")
    l5 = bm.get("hit_rate_l5", "N/A")
    h2h = bm.get("hit_rate_h2h", "N/A")
    avg = bm.get("combined_avg", "?")
    line = bm.get("line", "?")
    print(f"{i:<3} {event[:53]:<55} {market} {line:<5} {direction:<6} {safety:<7.2f} {l10:<7} {l5:<6} {h2h:<6} avg={avg}")

# Show full details for top 8
print(f"\n{'='*120}")
print("TOP 8 DETAILED:")
print(f"{'='*120}")
for i, (safety, event, a) in enumerate(ranked[:8], 1):
    bm = a.get("best_market", {})
    sport = a.get("sport", "?")
    quality = a.get("data_quality", "?")
    markets_eval = a.get("markets_evaluated", 0)
    print(f"\n{i}. {event} ({sport}, quality={quality}, markets_evaluated={markets_eval})")
    print(f"   Best: {bm.get('name')} {bm.get('direction')} {bm.get('line')} | safety={bm.get('safety_score')}")
    print(f"   L10={bm.get('hit_rate_l10')} L5={bm.get('hit_rate_l5')} H2H={bm.get('hit_rate_h2h')}")
    print(f"   combined_avg={bm.get('combined_avg')} | one_sided={bm.get('one_sided')} h2h_blind={bm.get('h2h_blind')}")
    print(f"   source={bm.get('source')}")
    # Check for alternate markets
    all_markets = a.get("all_markets", a.get("markets", []))
    if all_markets and len(all_markets) > 1:
        print(f"   Other markets ({len(all_markets)} total):")
        for m in all_markets[:5]:
            if isinstance(m, dict):
                print(f"     - {m.get('name','?')} {m.get('direction','?')} {m.get('line','?')} safety={m.get('safety_score','?')} L10={m.get('hit_rate_l10','?')}")
