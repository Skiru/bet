#!/usr/bin/env python3
"""Fetch odds from Odds-API.io — 265 bookmakers, 34 sports, value bets.

Usage:
    python3 scripts/fetch_odds_api_io.py                      # fetch all sports
    python3 scripts/fetch_odds_api_io.py --sports football,basketball
    python3 scripts/fetch_odds_api_io.py --value-bets         # fetch value bets only
    python3 scripts/fetch_odds_api_io.py --list-sports        # list available sports (free)

Requires odds-api-io key in config/api_keys.json.
Free tier: 5,000 requests/hour.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from api_clients.odds_api_io import OddsAPIioClient, SPORT_SLUG_MAP, fetch_odds_snapshot
from api_clients.rate_limiter import RateLimiter

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"


def main():
    parser = argparse.ArgumentParser(description="Fetch odds from Odds-API.io")
    parser.add_argument("--date", help="Date to fetch (YYYY-MM-DD, default: today)")
    parser.add_argument("--sports", help="Comma-separated sports to scan")
    parser.add_argument("--value-bets", action="store_true", help="Fetch value bets only")
    parser.add_argument("--list-sports", action="store_true", help="List available sports")
    parser.add_argument("--bookmakers", default="Betclic PL,Bet365",
                        help="Comma-separated bookmakers (free plan: max 2)")
    args = parser.parse_args()

    rl = RateLimiter()
    client = OddsAPIioClient(rate_limiter=rl)

    if not client.is_available():
        print("ERROR: No odds-api-io key in config/api_keys.json")
        sys.exit(1)

    if args.list_sports:
        sports = client.list_sports()
        print(f"\n{'Name':<30} {'Slug':<25}")
        print("-" * 60)
        for s in sports:
            print(f"{s.get('name', ''):<30} {s.get('slug', ''):<25}")
        print(f"\nTotal: {len(sports)} sports")
        return

    if args.value_bets:
        print("\n=== VALUE BETS (pre-calculated EV) ===\n")
        for bookie in ["Bet365", "Unibet", "Pinnacle"]:
            vb = client.get_value_bets(bookmaker=bookie)
            if not vb:
                print(f"  {bookie}: no value bets")
                continue
            print(f"  {bookie}: {len(vb)} value bets")
            # Sort by EV descending
            vb.sort(key=lambda x: x.get("expectedValue", 0), reverse=True)
            for bet in vb[:10]:
                ev = bet.get("expectedValue", 0) * 100
                event = bet.get("event", {})
                home = event.get("home", "?")
                away = event.get("away", "?")
                market = bet.get("market", {}).get("name", "?")
                side = bet.get("betSide", "?")
                print(f"    {home} vs {away} | {market} → {side} | EV: {ev:.1f}%")

        # Save
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        all_vb = []
        for bookie in ["Bet365", "Unibet", "Pinnacle"]:
            vb = client.get_value_bets(bookmaker=bookie)
            if vb:
                for b in vb:
                    b["_bookmaker_source"] = bookie
                all_vb.extend(vb)

        output = DATA_DIR / "odds_api_io_value_bets.json"
        output.write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(all_vb),
            "value_bets": all_vb,
        }, indent=2, ensure_ascii=False))
        print(f"\nSaved {len(all_vb)} value bets → {output}")
        return

    # Full odds scan
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sports = args.sports.split(",") if args.sports else None

    print(f"\n{'='*80}")
    print(f"ODDS-API.IO — Odds Scan for {date}")
    print(f"{'='*80}")

    snapshot = fetch_odds_snapshot(date, sports=sports, bookmakers=args.bookmakers)

    # Persist odds to DB (dual-write alongside JSON)
    _persist_io_odds_to_db(snapshot, date)

    print(f"\n{'='*80}")
    print(f"DONE: {snapshot.get('total_events_with_odds', 0)} events with odds")
    print(f"      {snapshot.get('total_value_bets', 0)} value bets found")
    print(f"{'='*80}\n")


def _persist_io_odds_to_db(snapshot: dict, date: str):
    """Persist odds-api.io odds to the DB odds_history table."""
    try:
        ROOT_DIR = Path(__file__).parent.parent
        sys.path.insert(0, str(ROOT_DIR / "src"))
        from bet.db.connection import get_db
        from bet.db.models import OddsRecord
        from bet.db.repositories import FixtureRepo, OddsRepo, SportRepo, TeamRepo

        events = snapshot.get("events", [])
        if not events:
            return

        with get_db() as conn:
            odds_repo = OddsRepo(conn)
            fixture_repo = FixtureRepo(conn)
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            persisted = 0

            for event in events:
                home = (event.get("home") or "").strip()
                away = (event.get("away") or "").strip()
                sport_name = (event.get("sport") or "").lower()
                if not home or not away:
                    continue

                # Resolve sport and fixture
                sport = sport_repo.get_by_name(sport_name)
                if not sport:
                    continue

                fixture = fixture_repo.get_by_teams_and_date(
                    home, away, date, sport.id
                )
                if not fixture:
                    # Try to create teams + fixture
                    try:
                        home_team = team_repo.find_or_create(home, sport.id)
                        away_team = team_repo.find_or_create(away, sport.id)
                        from bet.db.models import Fixture
                        kickoff = event.get("kickoff", f"{date}T00:00:00")
                        f = Fixture(
                            id=None,
                            sport_id=sport.id,
                            competition_id=None,
                            home_team_id=home_team.id,
                            away_team_id=away_team.id,
                            kickoff=kickoff,
                            status="scheduled",
                            source="odds-api-io",
                            fetched_at=datetime.now(timezone.utc).isoformat(),
                        )
                        fixture_id = fixture_repo.upsert(f)
                    except Exception:
                        continue
                else:
                    fixture_id = fixture.id

                # Persist odds per bookmaker
                for bookie_name, markets in (event.get("bookmakers") or {}).items():
                    if not isinstance(markets, list):
                        continue
                    for market_data in markets:
                        market_name = market_data.get("name", "")
                        for odds_entry in market_data.get("odds", []):
                            for side in ("home", "away", "draw"):
                                val = odds_entry.get(side)
                                if val is not None:
                                    try:
                                        record = OddsRecord(
                                            id=None,
                                            fixture_id=fixture_id,
                                            bookmaker=bookie_name,
                                            market=market_name.lower().replace("match winner", "h2h").replace("ml", "h2h"),
                                            selection=side,
                                            odds=float(val),
                                            fetched_at=datetime.now(timezone.utc).isoformat(),
                                        )
                                        odds_repo.upsert(record)
                                        persisted += 1
                                    except Exception:
                                        pass

            conn.commit()
            if persisted:
                print(f"[odds-api-io] DB: persisted {persisted} odds records to betting.db")
    except Exception as e:
        print(f"[odds-api-io] DB persistence failed (non-critical): {e}")


if __name__ == "__main__":
    main()
