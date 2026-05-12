"""Site adapter for Covers.com — odds consensus, ATS records, matchups.

Extracts: match lines (home/away/time/competition/sport), odds consensus.
Covers.com covers NFL, NBA, MLB, NHL, NCAA, and more.

NHL-specific URL patterns:
- /nhl/matchups — matchup page with game previews
- /nhl/odds — odds comparison page
- /nhl/standings — standings context
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}\s*(?:AM|PM|ET|PT)?)\b", re.I)
_SCORE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")

# Map URL paths to sports
_SPORT_MAP = {
    "nfl": "football",
    "nba": "basketball",
    "nhl": "hockey",
    "ncaaf": "football",
    "ncaab": "basketball",
    "soccer": "football",
    "tennis": "tennis",
    "volleyball": "volleyball",
}


def _detect_sport(url: str) -> str:
    """Detect sport from URL path."""
    url_lower = url.lower()
    for key, sport in _SPORT_MAP.items():
        if f"/{key}/" in url_lower or f"/{key}-" in url_lower:
            return sport
    return "unknown"


def parse(html: str, url: str) -> List[Dict]:
    """Parse Covers.com HTML for match data."""
    soup = BeautifulSoup(html, "html.parser")
    sport = _detect_sport(url)

    results = _parse_matchup_cards(soup, url, sport)
    if not results:
        results = _parse_odds_table(soup, url, sport)
    if not results:
        return raw_parse(html, url)
    return results


def _parse_matchup_cards(soup: BeautifulSoup, url: str, sport: str) -> List[Dict]:
    """Parse Covers' matchup card layout."""
    results = []

    # Covers uses cmg_matchup_game_box or similar card elements
    for card in soup.find_all(True, class_=re.compile(r"matchup|game-box|game-card|event-card", re.I)):
        teams = card.find_all(True, class_=re.compile(r"team-name|participant|name", re.I))
        if len(teams) < 2:
            continue

        away = teams[0].get_text(strip=True)
        home = teams[1].get_text(strip=True)

        if not home or not away or len(home) > 60 or len(away) > 60:
            continue

        # Extract time
        time_el = card.find(True, class_=re.compile(r"time|date|start|status", re.I))
        kickoff = time_el.get_text(strip=True) if time_el else ""

        # Extract odds/spread if visible
        entry = {
            "home": home,
            "away": away,
            "time": kickoff,
            "league": "",
            "sport": sport,
            "source_url": url,
            "source_type": "covers",
            "raw": f"{home} vs {away}"
        }

        consensus = _extract_consensus(card)
        if consensus:
            entry["consensus"] = consensus
            odds = {}
            if "moneyline" in consensus:
                ml = consensus["moneyline"]
                if ml > 0:
                    odds["ml"] = round(1 + ml/100, 3)
                elif ml < 0:
                    odds["ml"] = round(1 + 100/abs(ml), 3)
            if "total" in consensus:
                odds["total_lines"] = consensus["total"]
            if "spread" in consensus:
                odds["handicap_lines"] = consensus["spread"]
            if odds:
                entry["odds"] = odds

        if sport == "hockey":
            hockey_extras = _extract_hockey_extras(card)
            entry.update(hockey_extras)

        results.append(entry)

    return results


def _parse_odds_table(soup: BeautifulSoup, url: str, sport: str) -> List[Dict]:
    """Fallback: parse table-based odds layouts."""
    results = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            texts = [c.get_text(strip=True) for c in cells]
            # Look for team names (non-numeric, reasonable length)
            teams = [t for t in texts if 3 < len(t) < 60 and not re.match(r"^[\d.+\-]+$", t)]
            if len(teams) >= 2:
                home = teams[1] if len(teams) > 1 else teams[0]
                away = teams[0]
                results.append({
                    "home": home,
                    "away": away,
                    "time": "",
                    "league": "",
                    "sport": sport,
                    "source_url": url,
                    "source_type": "covers",
                    "raw": f"{home} vs {away}"
                })

    return results


def _extract_consensus(el) -> dict:
    """Extract odds consensus data from a matchup element."""
    consensus = {}
    text = el.get_text(separator=" ", strip=True)

    spread_m = re.search(r"spread.*?([+-]?\d+\.?\d*)", text, re.I)
    if spread_m:
        consensus["spread"] = float(spread_m.group(1))

    total_m = re.search(r"(?:o/u|total).*?(\d+\.?\d*)", text, re.I)
    if total_m:
        consensus["total"] = float(total_m.group(1))

    ml_m = re.search(r"(?:moneyline|ml).*?([+-]\d+)", text, re.I)
    if ml_m:
        consensus["moneyline"] = int(ml_m.group(1))
    
    return consensus


def _extract_hockey_extras(card) -> dict:
    """Extract NHL-specific data from a Covers matchup card."""
    extras = {}
    text = card.get_text(separator=" ", strip=True).lower()
    
    # Goalie names — look for "goalie" label near player names
    goalie_els = card.find_all(True, class_=re.compile(r"goalie|starter|netminder", re.I))
    if len(goalie_els) >= 2:
        extras["goalie_away"] = {"name": goalie_els[0].get_text(strip=True)}
        extras["goalie_home"] = {"name": goalie_els[1].get_text(strip=True)}
    
    # PP/PK percentages — look for "PP" and "PK" labels
    pp_matches = re.findall(r"pp[:\s]*(\d+\.?\d*)%", text)
    pk_matches = re.findall(r"pk[:\s]*(\d+\.?\d*)%", text)
    if len(pp_matches) >= 2:
        extras["pp_pct_away"] = float(pp_matches[0])
        extras["pp_pct_home"] = float(pp_matches[1])
    if len(pk_matches) >= 2:
        extras["pk_pct_away"] = float(pk_matches[0])
        extras["pk_pct_home"] = float(pk_matches[1])
    
    # Record — look for W-L-OTL pattern
    record_matches = re.findall(r"(\d{1,2}-\d{1,2}-\d{1,2})", text)
    if len(record_matches) >= 2:
        extras["record_away"] = record_matches[0]
        extras["record_home"] = record_matches[1]
    
    return extras
