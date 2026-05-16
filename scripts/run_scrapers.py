#!/usr/bin/env python3
"""CLI entry point for the modular sports scraper system.

Usage:
    python scripts/run_scrapers.py --sport football --source fbref --season 2425
    python scripts/run_scrapers.py --sport hockey --source nhl-api --season 2425 --fixtures 2025-01-15
    python scripts/run_scrapers.py --list
    python scripts/run_scrapers.py --sport all --season 2425
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Ensure src/ is on path when run as script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.scrapers import available_scrapers, get_scraper
from bet.scrapers.constants import SPORT_SOURCE_MAP
from bet.scrapers.engine import get_session_factory, init_scraper_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_scrapers")


def run_single(sport: str, source: str, season: str, competition: str,
               fixtures_date: str | None, verbose: bool, limit: int = 0,
               teams: list[str] | None = None) -> dict:
    """Run a single scraper and return results summary."""
    log.info("▶ %s/%s  competition=%s  season=%s", sport, source, competition or "(default)", season)
    start = time.time()

    scraper_cls = get_scraper(sport, source)
    sf = get_session_factory()
    scraper = scraper_cls(sf)

    results: dict = {"sport": sport, "source": source, "status": "ok", "counts": {}}
    try:
        kwargs = {}
        if limit > 0 or teams:
            import inspect
            sig = inspect.signature(scraper.scrape_team_season_stats)
            if 'max_teams' in sig.parameters and limit > 0:
                kwargs['max_teams'] = limit
            if 'team_list' in sig.parameters and teams:
                kwargs['team_list'] = teams
        team_count = scraper.scrape_team_season_stats(competition, season, **kwargs)
        results["counts"]["team_stats"] = team_count
        log.info("  team_stats: %d records", team_count)
    except NotImplementedError:
        results["counts"]["team_stats"] = "n/a"
    except Exception as e:
        log.warning("  team_stats FAILED: %s", e)
        results["counts"]["team_stats"] = f"error: {e}"
        results["status"] = "partial"

    try:
        player_count = scraper.scrape_player_season_stats(competition, season)
        results["counts"]["player_stats"] = player_count
        log.info("  player_stats: %d records", player_count)
    except NotImplementedError:
        results["counts"]["player_stats"] = "n/a"
    except Exception as e:
        log.warning("  player_stats FAILED: %s", e)
        results["counts"]["player_stats"] = f"error: {e}"
        results["status"] = "partial"

    if fixtures_date:
        try:
            fix_count = scraper.scrape_fixtures(fixtures_date)
            results["counts"]["fixtures"] = fix_count
            log.info("  fixtures (%s): %d records", fixtures_date, fix_count)
        except NotImplementedError:
            results["counts"]["fixtures"] = "n/a"
        except Exception as e:
            log.warning("  fixtures FAILED: %s", e)
            results["counts"]["fixtures"] = f"error: {e}"
            results["status"] = "partial"

    elapsed = time.time() - start
    results["elapsed_s"] = round(elapsed, 1)
    log.info("  done in %.1fs", elapsed)
    return results


def main():
    parser = argparse.ArgumentParser(description="Run sports data scrapers")
    parser.add_argument("--sport", type=str, help="Sport name or 'all'")
    parser.add_argument("--source", type=str, help="Source name (e.g. fbref, nhl-api)")
    parser.add_argument("--season", type=str, default="2425", help="Season code (default: 2425)")
    parser.add_argument("--competition", type=str, default="", help="Competition name override")
    parser.add_argument("--fixtures", type=str, help="Date for fixtures scrape (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=0, help="Max teams to fetch (Flashscore only, 0=all)")
    parser.add_argument("--teams", type=str, help="Comma-separated team names (Flashscore only)")
    parser.add_argument("--exclude", type=str, help="Comma-separated sources to skip (e.g. flashscore)")
    parser.add_argument("--list", action="store_true", help="List available scrapers and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list:
        scrapers = available_scrapers()
        print(f"\nAvailable scrapers ({len(scrapers)}):\n")
        for (sport, source), cls_name in sorted(scrapers.items()):
            print(f"  {sport:15s} {source:25s} → {cls_name}")
        print(f"\nSport groups (--sport all):")
        for sport, sources in sorted(SPORT_SOURCE_MAP.items()):
            print(f"  {sport:15s} {', '.join(sources)}")
        return

    if not args.sport:
        parser.error("--sport is required (or use --list)")

    init_scraper_db()

    all_results: list[dict] = []
    team_list = [t.strip() for t in args.teams.split(",")] if args.teams else None
    exclude_sources = {s.strip() for s in args.exclude.split(",")} if args.exclude else set()

    if args.sport == "all":
        for sport, sources in SPORT_SOURCE_MAP.items():
            for source in sources:
                if source in exclude_sources:
                    log.info("⏭ Skipping %s/%s (excluded)", sport, source)
                    continue
                res = run_single(sport, source, args.season, args.competition,
                                 args.fixtures, args.verbose, args.limit, team_list)
                all_results.append(res)
    elif args.source:
        res = run_single(args.sport, args.source, args.season, args.competition,
                         args.fixtures, args.verbose, args.limit, team_list)
        all_results.append(res)
    else:
        sources = SPORT_SOURCE_MAP.get(args.sport, [])
        if not sources:
            parser.error(f"Unknown sport '{args.sport}'. Use --list to see available.")
        for source in sources:
            if source in exclude_sources:
                log.info("⏭ Skipping %s/%s (excluded)", args.sport, source)
                continue
            res = run_single(args.sport, source, args.season, args.competition,
                             args.fixtures, args.verbose, args.limit, team_list)
            all_results.append(res)

    # Summary
    failures = [r for r in all_results if r["status"] != "ok"]
    print("\n" + "=" * 60)
    print("AGENT_SUMMARY:" + json.dumps({
        "verdict": "OK" if not failures else "PARTIAL",
        "scrapers_run": len(all_results),
        "scrapers_failed": len(failures),
        "failed_sources": [f"{r['sport']}/{r['source']}" for r in failures],
        "results": all_results,
    }))


if __name__ == "__main__":
    main()
