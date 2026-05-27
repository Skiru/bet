#!/usr/bin/env python3
"""Temporary: inspect night events."""
import json
from collections import Counter

with open("betting/data/2026-05-26_evening_events.json") as f:
    data = json.load(f)

events = data if isinstance(data, list) else data.get("events", data.get("fixtures", []))
late = [e for e in events if (e.get("kickoff") or e.get("start_time", ""))[:16] >= "2026-05-26T22:00"]
print(f"Night events (22:00+): {len(late)}")
sports = Counter(e.get("sport", "?") for e in late)
print(f"By sport: {dict(sports.most_common())}")

print("\n--- Non-football:")
for e in late:
    sp = e.get("sport", "?")
    if sp != "football":
        ko = (e.get("kickoff") or e.get("start_time", ""))[:16]
        home = e.get("home_team", e.get("home", "?"))
        away = e.get("away_team", e.get("away", "?"))
        comp = e.get("competition", e.get("league", "?"))
        print(f"  {ko} | {sp} | {home} vs {away} | {comp}")

print("\n--- Top football (Copa/MLS/Serie):")
for e in late:
    if e.get("sport") == "football":
        comp = str(e.get("competition", e.get("league", ""))).lower()
        if any(x in comp for x in ["libertadores", "sudamericana", "serie a", "mls", "primeira", "copa", "conmebol"]):
            ko = (e.get("kickoff") or e.get("start_time", ""))[:16]
            home = e.get("home_team", e.get("home", "?"))
            away = e.get("away_team", e.get("away", "?"))
            league = e.get("competition", e.get("league", "?"))
            print(f"  {ko} | {home} vs {away} | {league}")

print("\n--- Argentina/Uruguay/Brazil football:")
for e in late:
    if e.get("sport") == "football":
        comp = str(e.get("competition", e.get("league", ""))).lower()
        if any(x in comp for x in ["argentina", "uruguay", "brazil", "brasil", "primera division", "superliga"]):
            ko = (e.get("kickoff") or e.get("start_time", ""))[:16]
            home = e.get("home_team", e.get("home", "?"))
            away = e.get("away_team", e.get("away", "?"))
            league = e.get("competition", e.get("league", "?"))
            print(f"  {ko} | {home} vs {away} | {league}")
