#!/usr/bin/env python3
"""
Fetch esports odds from bo3.gg and store in DB odds_history table.

Scrapes CS2 and Valorant match listing pages via Playwright to extract
moneyline odds, then matches them to existing fixtures in the database.

Usage:
    python3 scripts/fetch_esports_odds.py                    # fetch all esports
    python3 scripts/fetch_esports_odds.py --game valorant    # Valorant only
    python3 scripts/fetch_esports_odds.py --game cs2         # CS2 only
    python3 scripts/fetch_esports_odds.py --detail           # also fetch match detail pages
    python3 scripts/fetch_esports_odds.py --verbose          # verbose output
    python3 scripts/fetch_esports_odds.py --date 2026-05-24  # target date (default: today)

Source: bo3.gg (Playwright-rendered SPA)
Rate: ~3s between page loads (Playwright)
No API key required (public website).
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.db.connection import get_db
from bet.scrapers.bo3gg import Bo3GGScraper
from bet.utils import names_match, is_same_event

logger = logging.getLogger(__name__)

SPORT_IDS = {"cs2": 498, "dota2": 499, "valorant": 500}
BOOKMAKER = "bo3gg"
DATA_DIR = Path(__file__).parent.parent / "betting" / "data"


def match_fixture(home: str, away: str, fixtures: list[dict]) -> dict | None:
    """Find best matching fixture from DB by team names using smart fuzzy matching."""
    best_match = None
    best_score = 0.0
    
    for f in fixtures:
        fh = f["home_team"]
        fa = f["away_team"]
        
        # Try normal order
        score_h = names_match(home, fh, threshold=65)
        score_a = names_match(away, fa, threshold=65)
        if score_h >= 65 and score_a >= 65:
            score = score_h + score_a
            if score > best_score:
                best_score = score
                best_match = f
                continue
        
        # Try swapped order (home/away reversed)
        score_h = names_match(home, fa, threshold=65)
        score_a = names_match(away, fh, threshold=65)
        if score_h >= 65 and score_a >= 65:
            score = score_h + score_a
            if score > best_score:
                best_score = score
                best_match = f
    
    return best_match


def fetch_fixtures_for_date(date_str: str, sport_ids: list[int]) -> list[dict]:
    """Get esports fixtures from DB for the target date."""
    with get_db() as db:
        placeholders = ",".join("?" * len(sport_ids))
        cursor = db.execute(
            f"""
            SELECT f.id, t1.name as home_team, t2.name as away_team,
                   f.sport_id, f.kickoff
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.id
            JOIN teams t2 ON f.away_team_id = t2.id
            WHERE f.sport_id IN ({placeholders})
            AND f.kickoff >= ?
            AND f.kickoff < ? || 'T23:59:59'
            ORDER BY f.kickoff
            """,
            [*sport_ids, date_str, date_str],
        )
        return [
            {
                "fixture_id": row[0],
                "home_team": row[1],
                "away_team": row[2],
                "sport_id": row[3],
                "kickoff": row[4],
            }
            for row in cursor.fetchall()
        ]


def store_odds_batch(db, records: list[tuple]):
    """Store odds records in DB, skipping duplicates from the same fetch window (1 hour)."""
    stored = 0
    for fixture_id, market, selection, odds, line in records:
        # Dedup: skip if identical record exists within last hour
        existing = db.execute(
            """
            SELECT 1 FROM odds_history
            WHERE fixture_id = ? AND bookmaker = ? AND market = ? AND selection = ?
            AND fetched_at > datetime('now', '-1 hour')
            LIMIT 1
            """,
            [fixture_id, BOOKMAKER, market, selection],
        ).fetchone()
        if existing:
            continue
        db.execute(
            """
            INSERT INTO odds_history (fixture_id, bookmaker, market, selection, odds, line, fetched_at, is_closing)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            [fixture_id, BOOKMAKER, market, selection, odds, line, datetime.now(timezone.utc).isoformat()],
        )
        stored += 1
    db.commit()
    return stored


def main():
    parser = argparse.ArgumentParser(description="Fetch esports odds from bo3.gg")
    parser.add_argument("--game", choices=["valorant", "cs2", "all"], default="all",
                        help="Which game to fetch odds for")
    parser.add_argument("--detail", action="store_true",
                        help="Also fetch individual match detail pages (slower)")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="Target date (YYYY-MM-DD)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write to DB, just show what would be stored")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")

    # Determine which games to scrape
    games = ["valorant", "cs2"] if args.game == "all" else [args.game]
    sport_ids = [SPORT_IDS[g] for g in games if g in SPORT_IDS]

    # Load fixtures from DB
    fixtures = fetch_fixtures_for_date(args.date, sport_ids)
    print(f"Found {len(fixtures)} esports fixtures in DB for {args.date}")
    if args.verbose:
        for f in fixtures:
            logger.info("  %s vs %s (id=%d, sport=%d)", f["home_team"], f["away_team"], f["fixture_id"], f["sport_id"])

    # Scrape odds
    total_stored = 0
    total_matched = 0
    all_scraped: list[dict] = []
    pending_records: list[tuple] = []  # (fixture_id, market, selection, odds, line)

    with Bo3GGScraper() as scraper:
        for game in games:
            print(f"Scraping {game} matches from bo3.gg...")

            if game == "valorant":
                matches = scraper.get_valorant_matches_with_odds()
            else:
                matches = scraper.get_cs2_matches_with_odds()

            # Filter to target date (bo3.gg URLs use DD-MM-YYYY format)
            parts = args.date.split("-")  # 2026-05-24
            date_slug = f"{parts[2]}-{parts[1]}-{parts[0]}"  # 24-05-2026
            today_matches = [m for m in matches if date_slug in m.get("match_url", "")]
            print(f"  {game}: {len(today_matches)} matches today ({len(matches)} total on page)")

            for match in today_matches:
                home = match.get("home_team", "")
                away = match.get("away_team", "")
                odds_home = match.get("odds_home")
                odds_away = match.get("odds_away")

                if not odds_home or not odds_away:
                    if args.verbose:
                        logger.info("  SKIP (no odds): %s vs %s", home, away)
                    continue

                # Match to fixture in DB
                fixture = match_fixture(home, away, fixtures)
                if not fixture:
                    print(f"  WARNING: NO MATCH in DB: {home} vs {away}")
                    all_scraped.append({**match, "matched": False, "game": game})
                    continue

                total_matched += 1
                all_scraped.append({
                    **match, "matched": True, "fixture_id": fixture["fixture_id"], "game": game
                })

                if args.dry_run:
                    print(f"  DRY-RUN: {home} vs {away} → fixture {fixture['fixture_id']} | ML {odds_home}/{odds_away}")
                    continue

                # Queue ML odds (both selections)
                pending_records.append((fixture["fixture_id"], "h2h", "home", odds_home, None))
                pending_records.append((fixture["fixture_id"], "h2h", "away", odds_away, None))

                if args.verbose:
                    logger.info("  QUEUED: %s vs %s → %d | @%.2f/%.2f",
                                home, away, fixture["fixture_id"], odds_home, odds_away)

            # Optional: fetch detail pages for extra markets
            if args.detail:
                print(f"  Fetching detail pages for matched {game} matches...")
                for entry in all_scraped:
                    if not entry.get("matched") or entry.get("game") != game:
                        continue
                    detail = scraper.get_valorant_match_detail(entry["match_url"])
                    if detail and detail.get("ml_odds"):
                        # ML from detail (more precise)
                        ml = detail["ml_odds"]
                        if ml.get("home") and ml.get("away"):
                            if not args.dry_run:
                                pending_records.append((entry["fixture_id"], "h2h", "home", ml["home"], None))
                                pending_records.append((entry["fixture_id"], "h2h", "away", ml["away"], None))
                    if detail and detail.get("handicap"):
                        hc = detail["handicap"]
                        if hc.get("odds") and hc.get("line"):
                            if not args.dry_run:
                                pending_records.append((entry["fixture_id"], "spreads", hc.get("team", "home"),
                                                        hc["odds"], hc["line"]))

    # Batch write all odds to DB in single transaction
    if pending_records and not args.dry_run:
        with get_db() as db:
            total_stored = store_odds_batch(db, pending_records)
        print(f"  Stored {total_stored} new records ({len(pending_records) - total_stored} duplicates skipped)")

    # Save JSON snapshot
    snapshot_path = DATA_DIR / f"{args.date}_esports_odds_snapshot.json"
    with open(snapshot_path, "w") as f:
        json.dump({
            "date": args.date,
            "games": games,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "matches": all_scraped,
            "stats": {
                "total_scraped": len(all_scraped),
                "matched_to_db": total_matched,
                "odds_records_stored": total_stored,
            },
        }, f, indent=2, default=str)

    # Summary
    print(f"\nDone! Scraped {len(all_scraped)} matches, matched {total_matched} to DB, stored {total_stored} odds records.")
    print(f"Snapshot: {snapshot_path}")

    # AGENT_SUMMARY for pipeline integration
    summary = {
        "step": "esports_odds",
        "date": args.date,
        "games": games,
        "matches_scraped": len(all_scraped),
        "matches_matched": total_matched,
        "odds_stored": total_stored,
        "source": "bo3gg",
    }
    print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
