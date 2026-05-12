#!/usr/bin/env python3
"""One-shot diagnostic: test all API clients and Playwright adapters.

Tests:
1. API clients — can they connect? Do they return data?
2. Playwright adapters — can key URLs be fetched and parsed?
"""
import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from api_clients import CLIENT_REGISTRY, get_client
from api_clients.rate_limiter import RateLimiter

TODAY = "2026-05-12"
rl = RateLimiter()

print("=" * 70)
print("SECTION 1: API CLIENT HEALTH CHECK")
print("=" * 70)

for name in sorted(CLIENT_REGISTRY.keys()):
    try:
        client = get_client(name, rl)
        available = client.is_available()
        has_key = bool(getattr(client, 'api_key', None))
        broken = getattr(client, '_HOST_BROKEN', False)
        print(f"  {name:25s} available={available}  has_key={has_key}  broken={broken}")
        if available and name not in ("serpapi", "nba-api"):
            # Try a small fixtures call
            try:
                fixtures = client.get_fixtures(TODAY)
                print(f"    → fixtures({TODAY}): {len(fixtures)} found")
            except Exception as e:
                print(f"    → fixtures({TODAY}): ERROR: {e}")
    except Exception as e:
        print(f"  {name:25s} INIT ERROR: {e}")
    time.sleep(0.3)

print()
print("=" * 70)
print("SECTION 2: KEY URL REACHABILITY (HTTP GET, no Playwright)")
print("=" * 70)

import requests

TEST_URLS = {
    # Tennis sources
    "TennisExplorer": "https://www.tennisexplorer.com/matches/",
    "TennisAbstract ATP Elo": "https://www.tennisabstract.com/reports/atp_elo_ratings.html",
    "TennisAbstract WTA Elo": "https://www.tennisabstract.com/reports/wta_elo_ratings.html",
    "UltimateTennisStats": "https://www.ultimatetennisstatistics.com/",
    "TennisPrediction": "https://tennisprediction.com/",
    "ATP Tour Scores": "https://www.atptour.com/en/scores/current",
    "WTA Tour Scores": "https://www.wtatennis.com/scores",
    # Football sources
    "Flashscore": "https://www.flashscore.com/",
    "Soccerway": "https://int.soccerway.com/",
    "SoccerStats": "https://www.soccerstats.com/latest.asp?league=england",
    "TotalCorner": "https://www.totalcorner.com/match/today",
    "Betaminic Corners": "https://www.betaminic.com/statistics/corners-team-stats-tables/",
    "WhoScored": "https://www.whoscored.com/Previews",
    "FootyStats": "https://footystats.org/",
    # Odds sources
    "BetExplorer": "https://www.betexplorer.com/football/",
    "OddsPortal": "https://www.oddsportal.com/football/",
    "Scores24 Football": "https://scores24.live/en/soccer",
    "Scores24 Tennis": "https://scores24.live/en/tennis",
    "Scores24 Basketball": "https://scores24.live/en/basketball",
    # Basketball
    "Basketball-Reference": "https://www.basketball-reference.com/",
    "DunksAndThrees": "https://www.dunksandthrees.com/",
    "Eurobasket": "https://www.eurobasket.com/",
    "RealGM Basketball": "https://basketball.realgm.com/",
    "Proballers": "https://www.proballers.com/",
    # Hockey
    "Hockey-Reference": "https://www.hockey-reference.com/",
    "NaturalStatTrick": "https://www.naturalstattrick.com/",
    "MoneyPuck": "https://moneypuck.com/",
    "DailyFaceoff": "https://www.dailyfaceoff.com/",
    "EliteProspects": "https://www.eliteprospects.com/",
    "Eurohockey": "https://www.eurohockey.com/",
    # Volleyball
    "CEV": "https://www.cev.eu/",
    "PlusLiga": "https://plusliga.pl/",
    "VolleyballWorld": "https://www.volleyballworld.com/",
    # Tipsters
    "Forebet Football": "https://www.forebet.com/en/football-tips-and-predictions-for-today",
    "Forebet Tennis": "https://www.forebet.com/en/tennis/predictions-today",
    "Bettingclosed": "https://www.bettingclosed.com/",
    "BetIdeas": "https://betideas.com/tips",
    "Feedinco": "https://feedinco.com/",
    "FootyAmigo": "https://footyamigo.com/",
    # Exotic league sources
    "AiScore": "https://www.aiscore.com/",
    "NowGoal": "https://www.nowgoal.com/",
    "Goaloo": "https://www.goaloo.com/",
    # TransferMarkt
    "TransferMarkt": "https://www.transfermarkt.com/",
    # TheSportsDB API
    "TheSportsDB API": "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=2026-05-12",
    # BallDontLie API — v1 deprecated, removed from pipeline
    # API-Tennis DNS
    "API-Tennis DNS": "https://v1.tennis.api-sports.io/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

for label, url in TEST_URLS.items():
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        size = len(r.content)
        redir = f" → {r.url}" if r.url != url else ""
        print(f"  {label:30s} HTTP {r.status_code}  {size:>8,} bytes{redir}")
    except requests.exceptions.ConnectionError as e:
        print(f"  {label:30s} CONN ERROR: {e}")
    except requests.exceptions.Timeout:
        print(f"  {label:30s} TIMEOUT (10s)")
    except Exception as e:
        print(f"  {label:30s} ERROR: {e}")
    time.sleep(0.2)

print()
print("=" * 70)
print("DONE")
print("=" * 70)
