"""DailyFaceoff adapter — NHL starting goalie confirmations.

Critical for hockey totals betting: knowing the confirmed starter vs.
expected/backup goalie fundamentally changes game totals analysis.

DailyFaceoff is a Next.js app that embeds game data as JSON in a
<script id="__NEXT_DATA__"> tag. This is far more reliable than scraping
the Tailwind/styled-components DOM. The adapter extracts:
  - Teams and game time
  - Goalie names, W-L-OTL record, SV%, GAA, shutouts
  - Goalie confirmation status (from rendered HTML text near each game)
  - Point spread and moneyline odds

Page types:
  Starting goalies: /starting-goalies/ — daily goalie confirmations
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import json
import re
from .raw_adapter import parse as raw_parse


# Normalize confirmation status to one of: confirmed, expected, unconfirmed
_STATUS_MAP = {
    "confirmed": "confirmed",
    "expected": "expected",
    "likely": "expected",
    "probable": "expected",
    "unconfirmed": "unconfirmed",
    "tbd": "unconfirmed",
    "not yet confirmed": "unconfirmed",
}


def parse(html: str, url: str) -> List[Dict]:
    """Parse DailyFaceoff HTML for goalie confirmations."""
    soup = BeautifulSoup(html, "html.parser")

    if "/starting-goalies" in url:
        # Strategy 1: Parse embedded Next.js JSON data (most reliable)
        results = _parse_next_data(soup, url)
        if results:
            # Enrich with confirmation status from rendered HTML
            _enrich_confirmation_status(soup, results)
            return results

        # Strategy 2: Fallback to HTML card parsing
        results = _parse_html_cards(soup, url)
        if results:
            return results

    return raw_parse(html, url)


def _normalize_status(raw_status: str) -> str:
    """Normalize goalie confirmation status."""
    clean = raw_status.strip().lower()
    return _STATUS_MAP.get(clean, "unconfirmed")


def _parse_next_data(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse DailyFaceoff's __NEXT_DATA__ JSON for structured game data.

    DailyFaceoff embeds all game data in a <script> tag with JSON containing
    props.pageProps.data — an array of game objects with fields like:
    homeTeamName, awayTeamName, homeGoalieName, awayGoalieName, etc.
    """
    results = []

    for script in soup.find_all("script"):
        text = script.get_text()
        if "pageProps" not in text or "homeTeam" not in text:
            continue

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue

        games = data.get("props", {}).get("pageProps", {}).get("data", [])
        if not games:
            continue

        for game in games:
            home_team = game.get("homeTeamName", "")
            away_team = game.get("awayTeamName", "")
            if not home_team or not away_team:
                continue

            home_goalie = game.get("homeGoalieName", "")
            away_goalie = game.get("awayGoalieName", "")

            # Build goalie stats dicts
            goalie_home = {
                "name": home_goalie,
                "status": "unconfirmed",  # enriched later from HTML
                "wins": game.get("homeGoalieWins"),
                "losses": game.get("homeGoalieLosses"),
                "otl": game.get("homeGoalieOvertimeLosses"),
                "sv_pct": _safe_float(game.get("homeGoalieSavePercentage")),
                "gaa": _safe_float(game.get("homeGoalieGoalsAgainstAvg")),
                "shutouts": game.get("homeGoalieShutouts"),
                "rating": _safe_float(game.get("homeGoalieOverallScore")),
            }
            goalie_away = {
                "name": away_goalie,
                "status": "unconfirmed",
                "wins": game.get("awayGoalieWins"),
                "losses": game.get("awayGoalieLosses"),
                "otl": game.get("awayGoalieOvertimeLosses"),
                "sv_pct": _safe_float(game.get("awayGoalieSavePercentage")),
                "gaa": _safe_float(game.get("awayGoalieGoalsAgainstAvg")),
                "shutouts": game.get("awayGoalieShutouts"),
                "rating": _safe_float(game.get("awayGoalieOverallScore")),
            }

            # Build odds from embedded data
            odds = {}
            spread = game.get("pointSpread")
            if spread is not None:
                odds["spread"] = _safe_float(spread)
            ml_home = game.get("homeTeamMoneylinePointSpread")
            ml_away = game.get("awayTeamMoneylinePointSpread")
            if ml_home is not None:
                odds["ml_home"] = _safe_float(ml_home)
            if ml_away is not None:
                odds["ml_away"] = _safe_float(ml_away)

            entry = {
                "home": home_team,
                "away": away_team,
                "time": game.get("time", ""),
                "date": game.get("date", ""),
                "league": "NHL",
                "sport": "hockey",
                "source_url": url,
                "source_type": "dailyfaceoff",
                "goalie_home": goalie_home,
                "goalie_away": goalie_away,
                "raw": f"{away_team} @ {home_team}",
            }
            if odds:
                entry["odds"] = odds

            results.append(entry)

        break  # Only need the first matching script

    return results


def _safe_float(val) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _enrich_confirmation_status(soup: BeautifulSoup, results: List[Dict]) -> None:
    """Enrich game results with goalie confirmation status from rendered HTML.

    DailyFaceoff renders confirmation status as text in the DOM
    (e.g., "Confirmed", "Unconfirmed", "Expected"). We scan the full page
    text to find these near team/goalie names.
    """
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for result in results:
        home_goalie = result["goalie_home"]["name"]
        away_goalie = result["goalie_away"]["name"]

        # Search for confirmation status near goalie names
        for i, line in enumerate(lines):
            if home_goalie and home_goalie in line:
                # Look at nearby lines for status
                nearby = " ".join(lines[max(0, i - 3):i + 4]).lower()
                for status_text, norm in _STATUS_MAP.items():
                    if status_text in nearby:
                        result["goalie_home"]["status"] = norm
                        break
            if away_goalie and away_goalie in line:
                nearby = " ".join(lines[max(0, i - 3):i + 4]).lower()
                for status_text, norm in _STATUS_MAP.items():
                    if status_text in nearby:
                        result["goalie_away"]["status"] = norm
                        break


def _parse_html_cards(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Fallback: parse goalie data from HTML card elements.

    Used when __NEXT_DATA__ JSON is not available.
    """
    results = []

    # Look for card-based layout
    cards = soup.find_all(True, class_=re.compile(
        r"starting-goalies|goalie-card|matchup-card|game-card|goalies-card", re.I
    ))

    for card in cards:
        team_els = card.find_all(True, class_=re.compile(r"team-name|teamName", re.I))
        goalie_els = card.find_all(True, class_=re.compile(
            r"goalie-name|goalieName|player-name", re.I
        ))
        status_els = card.find_all(True, class_=re.compile(r"status|confirm|badge", re.I))
        time_el = card.find(True, class_=re.compile(r"time|game-time|start-time|gameTime", re.I))

        if len(team_els) < 2:
            team_links = card.find_all("a", href=re.compile(r"/teams/", re.I))
            if len(team_links) >= 2:
                team_els = team_links

        if len(team_els) < 2:
            continue

        away_team = team_els[0].get_text(strip=True)
        home_team = team_els[1].get_text(strip=True)
        if not away_team or not home_team or len(away_team) > 60 or len(home_team) > 60:
            continue

        goalie_away_name = goalie_els[0].get_text(strip=True) if len(goalie_els) >= 1 else ""
        goalie_home_name = goalie_els[1].get_text(strip=True) if len(goalie_els) >= 2 else ""

        status_away = "unconfirmed"
        status_home = "unconfirmed"
        if len(status_els) >= 2:
            status_away = _normalize_status(status_els[0].get_text(strip=True))
            status_home = _normalize_status(status_els[1].get_text(strip=True))

        results.append({
            "home": home_team,
            "away": away_team,
            "time": time_el.get_text(strip=True) if time_el else "",
            "league": "NHL",
            "sport": "hockey",
            "source_url": url,
            "source_type": "dailyfaceoff",
            "goalie_home": {"name": goalie_home_name, "status": status_home},
            "goalie_away": {"name": goalie_away_name, "status": status_away},
            "raw": f"{away_team} @ {home_team}",
        })

    return results
