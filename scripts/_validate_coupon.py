#!/usr/bin/env python3
"""Validate coupon for 2026-05-18: identify past events, check arithmetic, deep describe."""
import json
import sys
from datetime import datetime, timezone
from dateutil.parser import parse as dtparse

DATE = "2026-05-18"
NOW_UTC = datetime.now(timezone.utc)

with open(f"betting/coupons/{DATE}.json", "r") as f:
    data = json.load(f)

print(f"Current UTC: {NOW_UTC.strftime('%Y-%m-%d %H:%M')}")
print(f"Current CEST: {NOW_UTC.hour + 2}:{NOW_UTC.minute:02d}")
print()

# === 1. Identify all unique events ===
all_events = {}
for section in ["singles", "core_coupons", "combos", "discovery_singles"]:
    items = data.get(section, [])
    for item in items:
        for leg in item.get("legs", []):
            ko_str = leg.get("kickoff", "")
            home = leg.get("home_team", "?")
            away = leg.get("away_team", "?")
            key = f"{home} vs {away}"
            all_events[key] = ko_str

# Banker
if data.get("banker"):
    for leg in data["banker"].get("legs", []):
        ko_str = leg.get("kickoff", "")
        home = leg.get("home_team", "?")
        away = leg.get("away_team", "?")
        key = f"{home} vs {away}"
        all_events[key] = ko_str

# === 2. Classify started vs upcoming ===
started = []
upcoming = []
for event, ko_str in sorted(all_events.items(), key=lambda x: x[1]):
    try:
        ko = dtparse(ko_str)
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        if ko <= NOW_UTC:
            started.append((event, ko_str, ko))
        else:
            upcoming.append((event, ko_str, ko))
    except Exception as e:
        upcoming.append((event, ko_str, None))

print(f"=== ALREADY STARTED / PAST ({len(started)}) ===")
for e, k, ko in started:
    cest = f"{ko.hour + 2}:{ko.minute:02d}" if ko else "?"
    print(f"  ❌ {cest} CEST | {e}")

print(f"\n=== STILL UPCOMING ({len(upcoming)}) ===")
for e, k, ko in upcoming:
    cest = f"{ko.hour + 2}:{ko.minute:02d}" if ko else "?"
    print(f"  ✅ {cest} CEST | {e}")

# === 3. Validate arithmetic of core coupons ===
def get_odds(leg):
    """Extract odds from leg, handling dict format."""
    o = leg.get("odds", {})
    if isinstance(o, dict):
        return o.get("market_best", o.get("implied", 1.0))
    if isinstance(o, (int, float)):
        return o
    return leg.get("implied_odds", 1.0)

print(f"\n=== ARITHMETIC VALIDATION (core_coupons) ===")
for i, c in enumerate(data["core_coupons"]):
    legs = c["legs"]
    calculated = 1.0
    leg_odds_list = []
    for leg in legs:
        odds = get_odds(leg)
        calculated *= odds
        leg_odds_list.append(odds)
    listed = c["combined_odds"]
    diff = abs(calculated - listed)
    status = "✅" if diff <= 0.02 else "⚠️"
    print(f"  {status} {c['id']}: listed={listed:.2f}, calculated={calculated:.2f} (legs: {leg_odds_list}), diff={diff:.3f}")

# === 4. Validate singles ===
print(f"\n=== SINGLES VALIDATION ===")
mismatches = 0
for i, s in enumerate(data["singles"]):
    legs = s["legs"]
    odds = get_odds(legs[0])
    listed = s["combined_odds"]
    if abs(odds - listed) > 0.02:
        mismatches += 1
        print(f"  ⚠️ {s['id']}: listed={listed:.2f}, leg_odds={odds:.2f}")
if mismatches == 0:
    print("  ✅ All singles odds match")

# === 5. Check duplicates ===
print(f"\n=== DUPLICATE EVENT CHECK ===")
core_events = {}
for c in data["core_coupons"]:
    for leg in c["legs"]:
        key = f"{leg.get('home_team')} vs {leg.get('away_team')}"
        if key not in core_events:
            core_events[key] = []
        core_events[key].append(c["id"])

dupes = {k: v for k, v in core_events.items() if len(v) > 1}
if dupes:
    for event, coupons in dupes.items():
        print(f"  ⚠️ {event} appears in: {', '.join(coupons)}")
else:
    print("  ✅ No duplicate events across core coupons")

# === 6. Bankroll check ===
print(f"\n=== BANKROLL CHECK ===")
bankroll = data["bankroll"]
summary = data["summary"]
total_spend = summary["total_spend"]
max_allowed = bankroll * 0.25
print(f"  Bankroll: {bankroll:.2f} PLN")
print(f"  Total spend: {total_spend:.2f} PLN")
print(f"  Max allowed (25%): {max_allowed:.2f} PLN")
status = "✅" if total_spend <= max_allowed else "⚠️ OVER BUDGET"
print(f"  Status: {status}")

# === 7. Concentration warnings ===
print(f"\n=== CONCENTRATION WARNINGS ===")
for w in data.get("concentration_warnings", []):
    if w.get("flagged"):
        print(f"  ⚠️ {w['event']} in {w['appearances']} coupons, exposure {w['exposure_pct_of_daily']:.0f}%")

# === 8. Summary of affected coupons ===
print(f"\n=== COUPONS AFFECTED BY STARTED EVENTS ===")
started_events = set(e for e, _, _ in started)
for section_name in ["singles", "core_coupons", "combos"]:
    items = data.get(section_name, [])
    for item in items:
        affected_legs = []
        for leg in item.get("legs", []):
            key = f"{leg.get('home_team')} vs {leg.get('away_team')}"
            if key in started_events:
                affected_legs.append(key)
        if affected_legs:
            print(f"  ❌ {item['id']} ({section_name}): {', '.join(affected_legs)}")

# Banker check
if data.get("banker"):
    for leg in data["banker"].get("legs", []):
        key = f"{leg.get('home_team')} vs {leg.get('away_team')}"
        if key in started_events:
            print(f"  ❌ {data['banker']['id']} (banker): {key}")
