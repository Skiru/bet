#!/usr/bin/env python3
"""Fetch ESPN odds for a given date — free, no API key, no credit cost.

Uses ESPN Core API to discover events and fetch multi-provider odds
(DraftKings, FanDuel, BetMGM, Bet365, ESPN BET, Caesars).

Usage:
    python3 scripts/fetch_espn_odds.py --date 2026-05-07
    python3 scripts/fetch_espn_odds.py --date 2026-05-07 --sports football,basketball,hockey
    python3 scripts/fetch_espn_odds.py --date 2026-05-07 --event-id 401234567
    python3 scripts/fetch_espn_odds.py --list-sports

Output: betting/data/espn_odds_snapshot_{date}.json
Format compatible with odds_api_snapshot.json for generate_market_matrix.py consumption.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from bet.api_clients.espn_odds import ESPNOddsClient, ESPN_SPORT_SLUGS
from bet.api_clients.espn import ESPNClient, ESPN_LEAGUES, ESPN_SPORT_MAP
from bet.api_clients.rate_limiter import RateLimiter

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"


def list_sports():
    """Print available sports and their leagues."""
    print(f"\n{'Sport':<15} {'Leagues'}")
    print("-" * 80)
    for sport, leagues in sorted(ESPN_LEAGUES.items()):
        print(f"{sport:<15} {len(leagues)} leagues: {', '.join(leagues[:10])}")
        if len(leagues) > 10:
            print(f"{'':15} ... and {len(leagues) - 10} more")
    print(f"\nTotal: {sum(len(v) for v in ESPN_LEAGUES.values())} leagues across {len(ESPN_LEAGUES)} sports")
    print("ESPN odds are FREE — no API key, no credit cost.")


def _espn_odds_to_bookmaker_format(odds_list: list, home_team: str, away_team: str) -> list:
    """Convert ESPN odds entries to the-odds-api bookmakers format.

    ESPN format (from ESPNOddsClient._parse_odds_response):
        {"bookmaker": "DraftKings", "markets": {"moneyline": {home, away, draw}, "totals": {...}, "spread": {...}}}

    Target format (the-odds-api compatible for generate_market_matrix.py):
        {"title": "DraftKings", "markets": [{"key": "h2h", "outcomes": [{"name": "Team", "price": 1.85}]}]}
    """
    bookmakers = []

    for odds_entry in odds_list:
        bm_name = odds_entry.get("bookmaker", "ESPN")
        markets_raw = odds_entry.get("markets", {})
        markets = []

        # Moneyline → h2h
        ml = markets_raw.get("moneyline")
        if ml and ml.get("home") and ml.get("away"):
            outcomes = [
                {"name": home_team, "price": round(ml["home"], 3)},
                {"name": away_team, "price": round(ml["away"], 3)},
            ]
            if ml.get("draw"):
                outcomes.append({"name": "Draw", "price": round(ml["draw"], 3)})
            markets.append({"key": "h2h", "outcomes": outcomes})

        # Totals → totals
        totals = markets_raw.get("totals")
        if totals and totals.get("over") and totals.get("line"):
            outcomes = [
                {"name": "Over", "price": round(totals["over"], 3), "point": totals["line"]},
            ]
            if totals.get("under"):
                outcomes.append({"name": "Under", "price": round(totals["under"], 3), "point": totals["line"]})
            markets.append({"key": "totals", "outcomes": outcomes})

        # Spread → spreads
        spread = markets_raw.get("spread")
        if spread and spread.get("home") and spread.get("line") is not None:
            outcomes = [
                {"name": home_team, "price": round(spread["home"], 3), "point": spread["line"]},
            ]
            if spread.get("away"):
                outcomes.append({"name": away_team, "price": round(spread["away"], 3), "point": -spread["line"]})
            markets.append({"key": "spreads", "outcomes": outcomes})

        if markets:
            bookmakers.append({"title": bm_name, "key": bm_name.lower().replace(" ", "_"), "markets": markets})

    return bookmakers


def fetch_espn_odds_for_date(date: str, sport_filter: list[str] | None = None, event_id: str | None = None) -> dict:
    """Fetch ESPN odds for all configured sports/leagues on the given date.

    Returns snapshot dict compatible with odds_api_snapshot.json format.
    """
    client = ESPNOddsClient()
    now = datetime.now(timezone.utc)

    sports_to_scan = {}
    for sport, leagues in ESPN_LEAGUES.items():
        if sport_filter and sport not in sport_filter:
            continue
        # Only scan sports that ESPN has odds for (US-focused + soccer)
        if sport in ESPN_SPORT_SLUGS:
            sports_to_scan[sport] = leagues

    print(f"\n{'='*80}")
    print(f"ESPN ODDS — Scan @ {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Target date: {date}")
    print(f"Sports: {', '.join(sports_to_scan.keys())}")
    print(f"{'='*80}")

    all_events = []
    total_odds_found = 0

    for sport, leagues in sports_to_scan.items():
        print(f"\n--- {sport.upper()} ({len(leagues)} leagues) ---")
        sport_events_count = 0

        for league in leagues:
            # If specific event requested, skip irrelevant leagues
            if event_id:
                odds = client.get_event_odds(sport, league, event_id)
                if odds:
                    # Need to get event details from scoreboard
                    slug = ESPN_SPORT_SLUGS.get(sport, sport)
                    sb_url = f"http://site.api.espn.com/apis/site/v2/sports/{slug}/{league}/scoreboard"
                    sb_data = client._request(sb_url, params={"dates": date.replace("-", "")})
                    for ev in sb_data.get("events", []):
                        if ev.get("id") == event_id:
                            comps = ev.get("competitions", [{}])
                            comp = comps[0] if comps else {}
                            competitors = comp.get("competitors", [])
                            home_team = ""
                            away_team = ""
                            for c in competitors:
                                if c.get("homeAway") == "home":
                                    home_team = c.get("team", {}).get("displayName", "")
                                else:
                                    away_team = c.get("team", {}).get("displayName", "")

                            bookmakers = _espn_odds_to_bookmaker_format(odds, home_team, away_team)
                            if bookmakers:
                                event_out = {
                                    "id": event_id,
                                    "sport_key": f"espn_{sport}_{league}",
                                    "sport_title": f"{sport.title()} - {league}",
                                    "home_team": home_team,
                                    "away_team": away_team,
                                    "commence_time": comp.get("date", ""),
                                    "bookmakers": bookmakers,
                                    "_our_sport": sport,
                                    "_source": "espn",
                                }
                                all_events.append(event_out)
                                total_odds_found += 1
                    # Found the event, stop searching leagues
                    if all_events:
                        break
                continue

            # Normal scan: get all events for this league on this date
            try:
                events_odds = client.get_all_events_odds(sport, league, date)
            except Exception as exc:
                print(f"  {league}: ERROR {exc}")
                continue

            if not events_odds:
                continue

            # Get scoreboard for team names
            slug = ESPN_SPORT_SLUGS.get(sport, sport)
            date_compact = date.replace("-", "")
            sb_url = f"http://site.api.espn.com/apis/site/v2/sports/{slug}/{league}/scoreboard"
            sb_data = client._request(sb_url, params={"dates": date_compact})

            # Build event_id → event info lookup
            event_info = {}
            for ev in sb_data.get("events", []):
                eid = ev.get("id", "")
                comps = ev.get("competitions", [{}])
                comp = comps[0] if comps else {}
                competitors = comp.get("competitors", [])
                home_team = ""
                away_team = ""
                for c in competitors:
                    if c.get("homeAway") == "home":
                        home_team = c.get("team", {}).get("displayName", "")
                    else:
                        away_team = c.get("team", {}).get("displayName", "")
                event_info[eid] = {
                    "home_team": home_team,
                    "away_team": away_team,
                    "commence_time": comp.get("date", ""),
                    "venue": comp.get("venue", {}).get("fullName", ""),
                }

            league_count = 0
            for eid, odds_list in events_odds.items():
                info = event_info.get(eid, {})
                home_team = info.get("home_team", "")
                away_team = info.get("away_team", "")

                if not home_team or not away_team:
                    continue

                bookmakers = _espn_odds_to_bookmaker_format(odds_list, home_team, away_team)
                if bookmakers:
                    event_out = {
                        "id": eid,
                        "sport_key": f"espn_{sport}_{league}",
                        "sport_title": f"{sport.title()} - {league}",
                        "home_team": home_team,
                        "away_team": away_team,
                        "commence_time": info.get("commence_time", ""),
                        "bookmakers": bookmakers,
                        "_our_sport": sport,
                        "_source": "espn",
                    }
                    all_events.append(event_out)
                    league_count += 1

            if league_count:
                print(f"  {league}: {league_count} events with odds")
                sport_events_count += league_count

            # Brief pause to be respectful to ESPN servers
            time.sleep(0.2)

        if sport_events_count:
            total_odds_found += sport_events_count
            print(f"  → {sport.upper()} total: {sport_events_count} events")
        else:
            print(f"  → {sport.upper()}: no odds found")

    # Build snapshot
    snapshot = {
        "timestamp": now.isoformat(),
        "source": "espn-core-api",
        "date": date,
        "cost": "FREE (no API key required)",
        "total_events": len(all_events),
        "sports_scanned": list(sports_to_scan.keys()),
        "events": all_events,
    }

    print(f"\n{'='*80}")
    print(f"SUMMARY: {len(all_events)} events with odds across {len(sports_to_scan)} sports")
    print(f"Cost: FREE (ESPN Core API, no key needed)")
    print(f"{'='*80}\n")

    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Fetch ESPN odds (free, no API key)")
    parser.add_argument("--date", type=str, help="Date to fetch (YYYY-MM-DD)")
    parser.add_argument("--sports", type=str, help="Comma-separated sports filter")
    parser.add_argument("--event-id", type=str, help="Fetch specific event by ESPN ID")
    parser.add_argument("--list-sports", action="store_true", help="List available sports/leagues")
    parser.add_argument("--no-persist-db", action="store_true", help="Skip DB persistence")
    args = parser.parse_args()

    if args.list_sports:
        list_sports()
        return

    if not args.date:
        args.date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sport_filter = None
    if args.sports:
        sport_filter = [s.strip() for s in args.sports.split(",")]

    snapshot = fetch_espn_odds_for_date(args.date, sport_filter, args.event_id)

    # Save output
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / f"espn_odds_snapshot_{args.date}.json"
    output_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Data saved: {output_file}")

    # Also save as current (for pipeline compatibility)
    current_file = DATA_DIR / "espn_odds_snapshot.json"
    current_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Current link: {current_file}")

    # Persist to DB
    if not args.no_persist_db:
        _persist_to_db(snapshot)


def _persist_to_db(snapshot: dict) -> None:
    """Persist ESPN odds snapshot to SQLite database."""
    try:
        from bet.db.connection import get_db
        from bet.db.schema import init_db
        from bet.db.models import OddsRecord
        from bet.db.repositories import OddsRepo
    except ImportError:
        print("  [DB] Skipping DB persistence (imports failed)")
        return

    db_path = Path(__file__).parent.parent / "betting" / "data" / "betting.db"
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    try:
        with get_db(db_path) as conn:
            init_db(conn)
            odds_repo = OddsRepo(conn)

            for event in snapshot.get("events", []):
                home = event.get("home_team", "")
                away = event.get("away_team", "")
                # Try to find fixture by team names
                fixture_row = conn.execute(
                    "SELECT id FROM fixtures WHERE home_team = ? AND away_team = ? "
                    "ORDER BY kickoff DESC LIMIT 1",
                    (home, away),
                ).fetchone()
                if not fixture_row:
                    continue
                fixture_id = fixture_row["id"]

                for bm in event.get("bookmakers", []):
                    bookmaker = bm.get("title", "ESPN")
                    for market in bm.get("markets", []):
                        market_key = market.get("key", "")
                        for outcome in market.get("outcomes", []):
                            record = OddsRecord(
                                id=None,
                                fixture_id=fixture_id,
                                bookmaker=bookmaker,
                                market=market_key,
                                selection=outcome.get("name", ""),
                                odds=outcome.get("price", 0.0),
                                line=outcome.get("point"),
                                fetched_at=now,
                                is_closing=False,
                            )
                            odds_repo.upsert(record)
                            count += 1

            conn.commit()
        print(f"  [DB] Persisted {count} odds records to database")
    except Exception as e:
        print(f"  [DB] Error persisting to DB: {e}")


if __name__ == "__main__":
    main()
