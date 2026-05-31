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
from bs4 import BeautifulSoup
from bet.resilience import resilient_request, atomic_json_write

def tennisabstract_parse(html: str, url: str) -> list[dict]:
    """Parse TennisAbstract Elo ratings HTML table (inlined from deleted adapter)."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    tour = "atp" if "atp" in url.lower() else "wta"

    elo_table = soup.find("table", id="reportable") or soup.find("table", class_="tablesorter")
    if not elo_table:
        for t in soup.find_all("table"):
            if len(t.find_all("tr", recursive=False)) > 100:
                elo_table = t
                break
    if not elo_table:
        return results

    trs = elo_table.find_all("tr")
    header_cells = []
    data_start = 0
    for i, tr in enumerate(trs):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if any("Elo" in c for c in cells) and any("Player" in c for c in cells):
            header_cells = cells
            data_start = i + 1
            break

    col_idx = {h.strip(): i for i, h in enumerate(header_cells) if h.strip()}

    def _col(name, cells_list, cast=float):
        idx = col_idx.get(name)
        if idx is None or idx >= len(cells_list):
            return None
        val = cells_list[idx].strip()
        if not val:
            return None
        try:
            return cast(val)
        except (ValueError, TypeError):
            return None

    for tr in trs[data_start:]:
        cells = [c.get_text(strip=True).replace("\xa0", " ") for c in tr.find_all(["td", "th"])]
        if len(cells) < 10:
            continue
        try:
            rank = int(cells[0])
        except (ValueError, IndexError):
            continue
        player = cells[1] if len(cells) > 1 else ""
        if not player or len(player) < 3:
            continue
        try:
            elo = _col("Elo", cells) if col_idx else (float(cells[3]) if cells[3] else None)
        except (ValueError, IndexError):
            continue

        h_elo = _col("hElo", cells) if col_idx else None
        c_elo = _col("cElo", cells) if col_idx else None
        g_elo = _col("gElo", cells) if col_idx else None
        peak_elo = _col("Peak Elo", cells) or _col("Peak", cells) if col_idx else None

        result = {
            "home": player,
            "away": f"{tour.upper()} Elo #{rank}",
            "sport": "tennis",
            "source_type": "tennisabstract_elo",
            "elo_rank": rank,
            "official_rank": rank,
            "elo_rating": elo,
            "tour": tour,
        }
        if h_elo: result["hard_elo"] = h_elo
        if c_elo: result["clay_elo"] = c_elo
        if g_elo: result["grass_elo"] = g_elo
        if peak_elo: result["peak_elo"] = peak_elo
        results.append(result)

    return results

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

    result = resilient_request("GET", url, headers=HEADERS, timeout=30.0)
    if not result.success:
        print(f"[fetch-elo] FAILED to fetch {url}: {result.error}")
        return {"tour": tour, "players": 0, "errors": 1}
    html = result.data

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
        atomic_json_write(player_file, player)
        stored += 1

    # Store combined tour summary
    summary_file = CACHE_DIR / f"{tour}_elo.json"
    summary = {
        "tour": tour,
        "player_count": len(results),
        "players": results,
        "source_url": url,
    }
    atomic_json_write(summary_file, summary)

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
