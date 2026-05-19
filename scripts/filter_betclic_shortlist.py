#!/usr/bin/env python3
"""Filter S2 shortlist to only events confirmed on Betclic.

Reads:
  - betting/data/{date}_s2_shortlist.json (full shortlist)
  - betting/data/betclic_market_validation_{date}.json (Betclic validation)

Writes:
  - betting/data/{date}_s2_shortlist_betclic.json (filtered shortlist)

Usage:
  PYTHONPATH=src python3 scripts/filter_betclic_shortlist.py --date 2026-05-19 --verbose
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "betting" / "data"


def normalize(name: str) -> str:
    """Normalize event name for fuzzy matching."""
    return name.lower().replace(" - ", " v ").replace("  ", " ").strip()


def main():
    parser = argparse.ArgumentParser(description="Filter shortlist to Betclic-available events")
    parser.add_argument("--date", default=str(date.today()), help="Date YYYY-MM-DD")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    shortlist_path = DATA / f"{args.date}_s2_shortlist.json"
    validation_path = DATA / f"betclic_market_validation_{args.date}.json"
    output_path = DATA / f"{args.date}_s2_shortlist_betclic.json"

    if not shortlist_path.exists():
        print(f"ERROR: Shortlist not found: {shortlist_path}", file=sys.stderr)
        sys.exit(2)
    if not validation_path.exists():
        print(f"ERROR: Betclic validation not found: {validation_path}", file=sys.stderr)
        sys.exit(2)

    with open(shortlist_path) as f:
        shortlist_data = json.load(f)
    with open(validation_path) as f:
        validation = json.load(f)

    # Handle shortlist format: can be list or dict with "candidates" key
    if isinstance(shortlist_data, dict):
        shortlist = shortlist_data.get("candidates", [])
    else:
        shortlist = shortlist_data

    # Build set of Betclic event names (normalized) and their confirmed market types
    betclic_events = {}
    events_list = validation.get("events", validation) if isinstance(validation, dict) else validation
    for ev in events_list:
        name = ev.get("event_name", "")
        # Clean up "Obstawianie X | Bukmacher Y | Betclic Polska Bonus" format
        if "Obstawianie " in name and " | " in name:
            name = name.replace("Obstawianie ", "").split(" | ")[0]
        norm = normalize(name)
        confirmed = ev.get("confirmed_market_types", [])
        if confirmed:  # Only include events where we found confirmed markets
            betclic_events[norm] = {
                "confirmed_market_types": confirmed,
                "event_name": ev.get("event_name", ""),
                "sport": ev.get("sport", ""),
                "open_market_count": ev.get("open_market_count", 0),
            }

    if args.verbose:
        print(f"Betclic events with confirmed markets: {len(betclic_events)}")
        for name, info in betclic_events.items():
            print(f"  {name}: {info['confirmed_market_types']}")
        print()

    # Filter shortlist candidates
    filtered = []
    rejected = []
    for candidate in shortlist:
        # Build event name from home_team + away_team or event field
        home = candidate.get("home_team", "")
        away = candidate.get("away_team", "")
        if home and away:
            event_name = f"{home} v {away}"
        else:
            event_name = candidate.get("event", candidate.get("event_name", ""))
        norm = normalize(event_name)

        # Try exact match
        match = betclic_events.get(norm)

        # Try partial match (team names substring)
        if not match:
            for bname, binfo in betclic_events.items():
                # Check if both team names (or significant parts) appear
                parts = norm.replace(" v ", " - ").split(" - ")
                bparts = bname.replace(" v ", " - ").split(" - ")
                if len(parts) == 2 and len(bparts) == 2:
                    t1, t2 = parts[0].strip(), parts[1].strip()
                    bt1, bt2 = bparts[0].strip(), bparts[1].strip()
                    # Match if first significant word of each team matches
                    t1_key = t1.split()[0] if t1 else ""
                    t2_key = t2.split()[0] if t2 else ""
                    bt1_key = bt1.split()[0] if bt1 else ""
                    bt2_key = bt2.split()[0] if bt2 else ""
                    # Home vs Home and Away vs Away (same order)
                    if t1_key and t2_key and bt1_key and bt2_key:
                        if (t1_key == bt1_key or t1 in bt1 or bt1 in t1) and \
                           (t2_key == bt2_key or t2 in bt2 or bt2 in t2):
                            match = binfo
                            break
                        # Reversed order
                        if (t1_key == bt2_key or t1 in bt2 or bt2 in t1) and \
                           (t2_key == bt1_key or t2 in bt1 or bt1 in t2):
                            match = binfo
                            break

        if match:
            candidate["betclic_confirmed"] = True
            candidate["betclic_market_types"] = match["confirmed_market_types"]
            candidate["betclic_market_count"] = match["open_market_count"]
            filtered.append(candidate)
        else:
            rejected.append(candidate)

    # Write filtered shortlist (preserve original format)
    output_data = {
        "date": args.date,
        "total_candidates": len(filtered),
        "sports": sorted(set(c.get("sport", "unknown") for c in filtered)),
        "candidates": filtered,
        "filter": "betclic_available_only",
    }
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'='*60}")
    print(f"  BETCLIC FILTER — {args.date}")
    print(f"{'='*60}")
    print(f"  Input shortlist: {len(shortlist)} candidates")
    print(f"  Betclic events (with markets): {len(betclic_events)}")
    print(f"  MATCHED: {len(filtered)} candidates")
    print(f"  REJECTED: {len(rejected)} candidates (not on Betclic)")
    print()

    # Sport breakdown
    sports = {}
    for c in filtered:
        s = c.get("sport", "unknown")
        sports[s] = sports.get(s, 0) + 1
    print("  By sport (filtered):")
    for s, count in sorted(sports.items(), key=lambda x: -x[1]):
        print(f"    {s}: {count}")
    print()
    print(f"  Output: {output_path}")
    print(f"\nAGENT_SUMMARY:{{\"verdict\":\"OK\",\"input\":{len(shortlist)},\"matched\":{len(filtered)},\"rejected\":{len(rejected)},\"output\":\"{output_path}\"}}")


if __name__ == "__main__":
    main()
