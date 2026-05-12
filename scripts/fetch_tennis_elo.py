#!/usr/bin/env python3
"""Fetch and cache TennisAbstract Elo ratings for use in safety score calculations.

Fetches ATP + WTA Elo pages, parses with tennisabstract_adapter, and stores
results in stats_cache/tennis_elo/ as individual player JSON files + combined
tour summaries. Called during enrichment phase (S2), not scan phase (S1).

Usage:
    python3 scripts/fetch_tennis_elo.py
    python3 scripts/fetch_tennis_elo.py --verbose
    python3 scripts/fetch_tennis_elo.py --tour atp
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import requests
from adapters.tennisabstract_adapter import parse as tennisabstract_parse

ELO_URLS = {
    "atp": "https://www.tennisabstract.com/reports/atp_elo_ratings.html",
    "wta": "https://www.tennisabstract.com/reports/wta_elo_ratings.html",
}

CACHE_DIR = Path(__file__).parent.parent / "betting" / "data" / "stats_cache" / "tennis_elo"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def slugify(name: str) -> str:
    """Convert player name to filesystem-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def fetch_and_cache(tour: str, verbose: bool = False) -> dict:
    """Fetch Elo page for a tour and cache results."""
    url = ELO_URLS.get(tour)
    if not url:
        print(f"[fetch-elo] Unknown tour: {tour}")
        return {"tour": tour, "players": 0, "errors": 1}

    if verbose:
        print(f"[fetch-elo] Fetching {tour.upper()} Elo ratings from {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"[fetch-elo] FAILED to fetch {url}: {e}")
        return {"tour": tour, "players": 0, "errors": 1}

    # Parse with existing adapter
    results = tennisabstract_parse(html, url)
    if verbose:
        print(f"[fetch-elo] Parsed {len(results)} {tour.upper()} players")

    # Create cache directory
    tour_dir = CACHE_DIR / tour
    tour_dir.mkdir(parents=True, exist_ok=True)

    # Store individual player files
    stored = 0
    for player in results:
        name = player.get("home", "")
        if not name:
            continue
        slug = slugify(name)
        player_file = tour_dir / f"{slug}.json"
        player_file.write_text(
            json.dumps(player, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        stored += 1

    # Store combined tour summary
    summary_file = CACHE_DIR / f"{tour}_elo.json"
    summary = {
        "tour": tour,
        "player_count": len(results),
        "players": results,
        "source_url": url,
    }
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if verbose:
        print(f"[fetch-elo] Stored {stored} player files + {tour}_elo.json summary")

    return {"tour": tour, "players": stored, "errors": 0}


def main():
    parser = argparse.ArgumentParser(description="Fetch TennisAbstract Elo ratings")
    parser.add_argument("--tour", choices=["atp", "wta"], help="Fetch only one tour")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    tours = [args.tour] if args.tour else ["atp", "wta"]
    total_players = 0
    total_errors = 0

    for tour in tours:
        result = fetch_and_cache(tour, verbose=args.verbose)
        total_players += result["players"]
        total_errors += result["errors"]
        if len(tours) > 1:
            time.sleep(1)

    verdict = "OK" if total_errors == 0 else "PARTIAL" if total_players > 0 else "FAILED"
    summary = {
        "verdict": verdict,
        "players_cached": total_players,
        "errors": total_errors,
        "tours": tours,
        "cache_dir": str(CACHE_DIR),
    }
    print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
