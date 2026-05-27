#!/usr/bin/env python3
"""Build night shortlist from evening events."""
import json
from collections import Counter

with open("betting/data/2026-05-26_evening_events.json") as f:
    data = json.load(f)

events = data if isinstance(data, list) else data.get("events", data.get("fixtures", []))
night = [e for e in events if (e.get("kickoff") or e.get("start_time", ""))[:16] >= "2026-05-26T22:00"]

filtered = []
for e in night:
    comp = str(e.get("competition", e.get("league", ""))).lower()
    home = str(e.get("home_team", e.get("home", ""))).lower()
    away = str(e.get("away_team", e.get("away", ""))).lower()
    sport = e.get("sport", "")

    # Skip UTR tennis, ITF low tier
    if sport == "tennis" and any(x in comp for x in ["utr", "itf"]):
        continue
    # Skip U17/U20
    if "u17" in comp or "u20" in comp or "u17" in home or "u17" in away:
        continue
    # Skip US amateur leagues
    if any(x in comp for x in ["usl league two", "uslw", "mls next"]):
        continue
    # Skip obvious amateur/academy
    if sport == "football" and any(x in home for x in ["academy", "reckoning", "storm", "kalamazoo", "marin fc"]):
        continue
    # Skip challenger doubles tennis
    if sport == "tennis" and "doubles" in comp:
        continue
    filtered.append(e)

print(f"Filtered night events: {len(filtered)}")
with open("betting/data/2026-05-26_night_events.json", "w") as f:
    json.dump(filtered, f, indent=2, ensure_ascii=False)
print("Saved to betting/data/2026-05-26_night_events.json")

print(f"By sport: {dict(Counter(e.get('sport', '?') for e in filtered).most_common())}")
for e in filtered:
    ko = (e.get("kickoff") or e.get("start_time", ""))[:16]
    home = e.get("home_team", e.get("home", "?"))
    away = e.get("away_team", e.get("away", "?"))
    comp = e.get("competition", e.get("league", "?"))
    sp = e.get("sport", "?")
    print(f"  {ko} | {sp:12} | {home} vs {away} | {comp}")
