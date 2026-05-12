"""ATP Tour adapter — parses atptour.com for tournament scores, player rankings, draws.

Extracts structured data from:
  /en/scores/current — today's match scores with tournament/round/surface context
  /en/rankings/singles — ATP singles rankings with points
  /en/tournaments/*/draws — tournament draw brackets

ATP Tour pages use both server-rendered tables and embedded JSON data.
"""
import json
import logging
import re
from typing import Dict, List

from bs4 import BeautifulSoup

from .raw_adapter import parse as raw_parse

logger = logging.getLogger(__name__)

_SURFACE_MAP = {
    "hard": "hard",
    "clay": "clay",
    "grass": "grass",
    "carpet": "carpet",
    "indoor hard": "hard",
    "outdoor hard": "hard",
}


def parse(html: str, url: str) -> List[Dict]:
    """Parse ATP Tour HTML for tennis data."""
    soup = BeautifulSoup(html, "html.parser")

    if "/scores" in url:
        results = _parse_scores_page(soup, url)
        if results:
            logger.info("[atptour] Parsed %d matches from scores page %s", len(results), url)
            return results

    if "/rankings" in url:
        results = _parse_rankings_page(soup, url)
        if results:
            logger.info("[atptour] Parsed %d player rankings from %s", len(results), url)
            return results

    if "/draws" in url:
        results = _parse_draws_page(soup, url)
        if results:
            logger.info("[atptour] Parsed %d draw entries from %s", len(results), url)
            return results

    logger.warning("[atptour] No structured data found, falling back to raw_parse for %s", url)
    return raw_parse(html, url)


def _parse_scores_page(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse today's scores page (/en/scores/current)."""
    results = []

    # Try embedded JSON data first (ATP Tour sometimes embeds match data)
    for script in soup.find_all("script"):
        text = script.string or ""
        if "matchData" in text or "scoreboard" in text:
            json_results = _parse_embedded_json(text, url)
            if json_results:
                return json_results

    # HTML parsing fallback
    current_tournament = ""
    current_surface = ""
    current_round = ""

    for el in soup.find_all(True):
        classes = " ".join(el.get("class", []))

        # Tournament headers
        if re.search(r"tournament|event-name|tourney", classes, re.I):
            text = el.get_text(strip=True)
            if 3 < len(text) < 100:
                current_tournament = text
                for raw, normalized in _SURFACE_MAP.items():
                    if raw in text.lower():
                        current_surface = normalized
                        break

        # Round headers
        if re.search(r"round|stage", classes, re.I):
            text = el.get_text(strip=True)
            if text and len(text) < 50:
                current_round = text

        # Match rows/cards
        if not re.search(r"match|score|result|day-table", classes, re.I):
            continue

        players = _extract_players(el)
        if len(players) < 2:
            continue

        # Extract time
        time_el = el.find(True, class_=re.compile(r"time|schedule|start", re.I))
        match_time = time_el.get_text(strip=True) if time_el else ""

        # Extract scores
        score_home, score_away, period_scores = _extract_atp_scores(el)

        # Extract match URL
        match_url = ""
        match_link = el.find("a", href=re.compile(r"/en/scores/"))
        if match_link:
            href = match_link.get("href", "")
            match_url = f"https://www.atptour.com{href}" if href.startswith("/") else href

        entry = {
            "home": players[0]["name"],
            "away": players[1]["name"],
            "time": match_time,
            "league": f"{current_tournament} - {current_round}" if current_round else current_tournament,
            "sport": "tennis",
            "source": "atptour.com",
            "source_type": "atptour",
            "source_url": url,
            "surface": current_surface,
        }

        if match_url:
            entry["match_url"] = match_url
        if score_home is not None:
            entry["score_home"] = score_home
            entry["score_away"] = score_away
        if period_scores:
            entry["period_scores"] = period_scores

        # Player rankings if available
        if players[0].get("rank"):
            entry["rank_home"] = players[0]["rank"]
        if players[1].get("rank"):
            entry["rank_away"] = players[1]["rank"]

        # Player countries
        if players[0].get("country"):
            entry["country_home"] = players[0]["country"]
        if players[1].get("country"):
            entry["country_away"] = players[1]["country"]

        results.append(entry)

    return results


def _parse_rankings_page(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse ATP rankings page (/en/rankings/singles)."""
    results = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            cell_texts = [c.get_text(strip=True) for c in cells]

            # Try to find rank (number) and player name
            rank = None
            player_name = ""
            points = None
            country = ""

            for i, text in enumerate(cell_texts):
                if text.isdigit() and rank is None:
                    rank = int(text)
                elif len(text) > 3 and not text.isdigit() and not player_name:
                    player_name = text
                elif text.replace(",", "").isdigit() and rank is not None and player_name:
                    points = int(text.replace(",", ""))

            # Country from flag image
            flag = row.find("img", attrs={"alt": True})
            if flag:
                country = flag.get("alt", "")

            if rank and player_name:
                results.append({
                    "home": player_name,
                    "away": f"ATP #{rank}",
                    "time": None,
                    "sport": "tennis",
                    "source": "atptour.com",
                    "source_type": "atptour_ranking",
                    "source_url": url,
                    "atp_rank": rank,
                    "atp_points": points,
                    "country": country,
                    "_ranking_only": True,
                })

    return results


def _parse_draws_page(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse tournament draw page for bracket data."""
    results = []

    for el in soup.find_all(True, class_=re.compile(r"draw|bracket|match", re.I)):
        players = _extract_players(el)
        if len(players) < 2:
            continue

        text = el.get_text(strip=True)
        round_match = re.search(r"(R\d+|QF|SF|F|Final|Semi|Quarter|Round \d+)", text, re.I)
        draw_round = round_match.group(1) if round_match else ""

        results.append({
            "home": players[0]["name"],
            "away": players[1]["name"],
            "time": "",
            "sport": "tennis",
            "source": "atptour.com",
            "source_type": "atptour_draw",
            "source_url": url,
            "league": draw_round,
        })

    return results


def _extract_players(el) -> List[Dict]:
    """Extract player info (name, rank, country) from an element."""
    players = []

    # Strategy 1: player-specific elements
    player_els = el.find_all(True, class_=re.compile(r"player|name|competitor", re.I))
    for pel in player_els:
        name = pel.get_text(strip=True)
        if not name or len(name) < 3 or len(name) > 60:
            continue
        if name.isdigit() or re.match(r"^\d{1,2}:\d{2}$", name):
            continue

        rank = None
        rank_el = pel.find(True, class_=re.compile(r"rank|seed", re.I))
        if rank_el:
            rank_text = rank_el.get_text(strip=True).strip("()")
            if rank_text.isdigit():
                rank = int(rank_text)
                # Remove rank from name
                name = name.replace(rank_el.get_text(), "").strip()

        country = ""
        flag = pel.find("img", attrs={"alt": True})
        if flag:
            country = flag.get("alt", "")

        if name and len(name) > 2:
            players.append({"name": name, "rank": rank, "country": country})

    if len(players) >= 2:
        return players

    # Strategy 2: links with player profiles
    for link in el.find_all("a", href=re.compile(r"/en/players/")):
        name = link.get_text(strip=True)
        if name and len(name) > 2 and not name.isdigit():
            country = ""
            flag = link.find("img", attrs={"alt": True})
            if flag:
                country = flag.get("alt", "")
            players.append({"name": name, "rank": None, "country": country})

    return players


def _extract_atp_scores(el) -> tuple:
    """Extract set/game scores from an ATP match element."""
    score_els = el.find_all(True, class_=re.compile(r"score|set|result", re.I))
    if not score_els:
        return None, None, []

    text = " ".join(s.get_text(strip=True) for s in score_els)
    set_scores = re.findall(r"(\d)\s*[-:]\s*(\d)", text)

    if not set_scores:
        return None, None, []

    score_home = int(set_scores[0][0])
    score_away = int(set_scores[0][1])
    period_scores = []
    for s in set_scores[1:]:
        period_scores.append({"home": int(s[0]), "away": int(s[1])})

    return score_home, score_away, period_scores


def _parse_embedded_json(script_text: str, url: str) -> List[Dict]:
    """Try to extract match data from embedded JavaScript/JSON."""
    # Look for JSON arrays/objects with match data
    json_match = re.search(r'(?:matchData|scoreboard)\s*[:=]\s*(\[[\s\S]*?\]);', script_text)
    if not json_match:
        return []

    try:
        data = json.loads(json_match.group(1))
    except (json.JSONDecodeError, ValueError):
        return []

    results = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            home = item.get("player1", {}).get("name", "") or item.get("home", "")
            away = item.get("player2", {}).get("name", "") or item.get("away", "")
            if home and away:
                results.append({
                    "home": home,
                    "away": away,
                    "time": item.get("time", ""),
                    "sport": "tennis",
                    "source": "atptour.com",
                    "source_type": "atptour",
                    "source_url": url,
                    "surface": item.get("surface", ""),
                    "league": item.get("tournament", ""),
                })

    return results
