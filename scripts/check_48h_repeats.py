#!/usr/bin/env python3
"""48-hour repeat pick detector — finds same team+market losses in recent history.

Reads picks-ledger.csv and identifies picks in the last 48 hours with the same
team+market combination that resulted in a loss. These are flagged for the S7 gate
(§7.5 point #14: "48h repeat check — same team+market lost → HARD REJECT").
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path


def normalize_team(name: str) -> str:
    """Normalize team name for fuzzy matching."""
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    # Remove common suffixes/prefixes
    for token in ["fc ", "sc ", "ac ", "ss ", "bv ", "ud ", "sv ", "tsv ", "vfb "]:
        if name.startswith(token):
            name = name[len(token):]
    for token in [" fc", " sc", " ac", " cf"]:
        if name.endswith(token):
            name = name[: -len(token)]
    return name.strip()


def normalize_market(market: str) -> str:
    """Normalize market type for matching."""
    market = market.lower().strip()
    market = re.sub(r"\s+", " ", market)
    # Normalize common variants
    market = market.replace("over ", "o").replace("under ", "u")
    market = market.replace("o/u ", "").replace("over/under ", "")
    return market


def fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
    """Check if two strings match above a similarity threshold."""
    return SequenceMatcher(None, a, b).ratio() >= threshold


def load_recent_losses(
    ledger_path: Path, hours: int = 48
) -> list[dict]:
    """Read picks-ledger.csv and filter to status=loss within last N hours."""
    if not ledger_path.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    losses = []

    with open(ledger_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status", "").strip().lower() != "loss":
                continue

            # Parse betting_day
            betting_day = row.get("betting_day", "").strip()
            if not betting_day:
                continue
            try:
                # Treat betting_day as end-of-day to ensure full 48h calendar coverage
                day_dt = datetime.strptime(betting_day, "%Y-%m-%d") + timedelta(hours=23, minutes=59)
            except ValueError:
                continue

            if day_dt < cutoff:
                continue

            # Extract team names from event field
            event = row.get("event", "").strip()
            teams = extract_teams(event)

            losses.append({
                "betting_day": betting_day,
                "pick_id": row.get("pick_id", "").strip(),
                "event": event,
                "sport": row.get("sport", "").strip(),
                "market": row.get("market", "").strip(),
                "selection": row.get("selection", "").strip(),
                "teams": teams,
                "teams_normalized": [normalize_team(t) for t in teams],
                "market_normalized": normalize_market(row.get("market", "")),
                "days_ago": (datetime.now() - day_dt).days,
            })

    return losses


def extract_teams(event: str) -> list[str]:
    """Extract team/player names from event string."""
    # Try "Team A vs Team B" pattern
    match = re.match(r"(.+?)\s+(?:vs\.?|@)\s+(.+?)(?:\s*\(|$)", event, re.IGNORECASE)
    if match:
        return [match.group(1).strip(), match.group(2).strip()]
    # Fallback: split by common separators
    for sep in [" vs ", " vs. ", " @ ", " - "]:
        if sep in event.lower():
            idx = event.lower().index(sep)
            return [event[:idx].strip(), event[idx + len(sep):].strip()]
    return [event]


def find_repeats(
    check_teams: list[str],
    recent_losses: list[dict],
    check_market: str | None = None,
) -> list[dict]:
    """Find matching team+market combinations in recent losses."""
    warnings = []
    check_teams_norm = [normalize_team(t) for t in check_teams]
    check_market_norm = normalize_market(check_market) if check_market else None

    for loss in recent_losses:
        for check_team in check_teams_norm:
            for loss_team in loss["teams_normalized"]:
                if fuzzy_match(check_team, loss_team):
                    # Team matches — check market if provided
                    if check_market_norm:
                        if not fuzzy_match(check_market_norm, loss["market_normalized"], 0.6):
                            continue

                    warnings.append({
                        "team": check_team,
                        "matched_team": loss_team,
                        "market": loss["market"],
                        "selection": loss["selection"],
                        "lost_on": loss["betting_day"],
                        "pick_id": loss["pick_id"],
                        "event": loss["event"],
                        "sport": loss["sport"],
                        "days_ago": loss["days_ago"],
                        "action": "HARD REJECT per §7.5 #14",
                    })

    return warnings


def parse_shortlist_teams(shortlist_path: Path) -> list[str]:
    """Extract team names from shortlist markdown file."""
    if not shortlist_path.exists():
        return []

    text = shortlist_path.read_text(encoding="utf-8")
    teams = set()

    # Look for "X vs Y" patterns
    for match in re.finditer(
        r"([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)\s+vs\.?\s+([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)(?:\s*[\|(]|$)",
        text,
        re.MULTILINE,
    ):
        teams.add(match.group(1).strip())
        teams.add(match.group(2).strip())

    return list(teams)


def main():
    parser = argparse.ArgumentParser(
        description="Detect 48-hour repeat team+market losses in picks-ledger."
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("betting/journal/picks-ledger.csv"),
        help="Path to picks-ledger.csv",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=48,
        help="Lookback window in hours (default: 48)",
    )
    parser.add_argument(
        "--teams",
        type=str,
        default=None,
        help="Comma-separated team names to check (e.g., 'Liverpool,Arsenal')",
    )
    parser.add_argument(
        "--shortlist",
        type=Path,
        default=None,
        help="Path to shortlist markdown file to extract team names",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )
    args = parser.parse_args()

    # Load recent losses
    recent_losses = load_recent_losses(args.ledger, args.hours)

    result = {
        "window_hours": args.hours,
        "recent_losses_count": len(recent_losses),
        "repeats_found": 0,
        "warnings": [],
    }

    if not recent_losses:
        if args.format == "text":
            print(f"No losses found in last {args.hours}h. Clear to proceed.")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    # If no specific teams provided, show all recent losses
    if not args.teams and not args.shortlist:
        if args.format == "text":
            print(f"═══ Recent Losses (last {args.hours}h) ═══")
            for loss in recent_losses:
                print(
                    f"  {loss['betting_day']} | {loss['pick_id']} | "
                    f"{loss['event']} | {loss['market']} | {loss['selection']}"
                )
            print(f"\nTotal: {len(recent_losses)} losses")
            print("Use --teams or --shortlist to check for repeats.")
        else:
            result["recent_losses"] = recent_losses
            print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    # Get teams to check
    check_teams = []
    if args.teams:
        check_teams = [t.strip() for t in args.teams.split(",")]
    elif args.shortlist:
        check_teams = parse_shortlist_teams(args.shortlist)

    if not check_teams:
        if args.format == "text":
            print("No teams to check.")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    # Find repeats
    warnings = find_repeats(check_teams, recent_losses)

    # Deduplicate warnings (same team+market+pick_id)
    seen = set()
    unique_warnings = []
    for w in warnings:
        key = (w["team"], w["market"], w["pick_id"])
        if key not in seen:
            seen.add(key)
            unique_warnings.append(w)

    result["repeats_found"] = len(unique_warnings)
    result["warnings"] = unique_warnings

    if args.format == "text":
        print(f"═══ 48h Repeat Check ═══")
        print(f"Teams checked: {len(check_teams)} | Recent losses: {len(recent_losses)}")
        if unique_warnings:
            print(f"\n⚠️  REPEATS FOUND: {len(unique_warnings)}")
            for w in unique_warnings:
                print(
                    f"  ✗ {w['team']} × {w['market']} — lost {w['lost_on']} "
                    f"({w['pick_id']}) → {w['action']}"
                )
        else:
            print("\n✓ No repeats found. Clear to proceed.")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    sys.exit(1 if unique_warnings else 0)


if __name__ == "__main__":
    main()
