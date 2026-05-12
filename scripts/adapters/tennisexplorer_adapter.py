"""Site adapter for TennisExplorer — match schedules, results, H2H, and surface.

Extracts: match lines (player1/player2/time/tournament), surface info,
match detail URLs, scores, country flags.
TennisExplorer covers ATP, WTA, ITF, and Challenger tours.
"""
import logging
import re
from typing import Dict, List

from bs4 import BeautifulSoup

from .raw_adapter import parse as raw_parse

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
_SCORE_RE = re.compile(r"(\d+)\s*[-:]\s*(\d+)")
_SET_SCORE_RE = re.compile(r"(\d)\s*[-:]\s*(\d)")
_SURFACE_RE = re.compile(r"(hard|clay|grass|carpet|indoor|outdoor)", re.I)
_MATCH_DETAIL_RE = re.compile(r"/match-detail/\?id=(\d+)")
_PLAYER_LINK_RE = re.compile(r"/player/|/profile/")


def parse(html: str, url: str) -> List[Dict]:
    """Parse TennisExplorer HTML for match data."""
    soup = BeautifulSoup(html, "html.parser")

    # H2H pages have their own parser
    if "/head-to-head/" in url:
        results = _parse_h2h_page(soup, url)
        if results:
            logger.info("[tennisexplorer] H2H page: %d records from %s", len(results), url)
            return results

    results = _parse_match_tables(soup, url)
    if not results:
        results = _parse_match_rows(soup, url)
    if not results:
        logger.warning("[tennisexplorer] No matches found, falling back to raw_parse for %s", url)
        return raw_parse(html, url)

    logger.info("[tennisexplorer] Parsed %d matches from %s", len(results), url)
    return results


def _parse_match_tables(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse TennisExplorer's table-based layout.

    TennisExplorer uses TWO consecutive rows per match — one row per player.
    This parser pairs consecutive player rows to form match entries.
    """
    results = []
    current_tournament = ""
    current_surface = ""
    current_country = ""

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        pending_player = None  # Buffer for first player of a match pair

        for row in rows:
            classes = " ".join(row.get("class", []))

            # Tournament/round headers
            if re.search(r"head|round|group", classes, re.I):
                header_link = row.find("a")
                if header_link:
                    text = header_link.get_text(strip=True)
                else:
                    text = row.get_text(strip=True)
                text = re.sub(r'(?:\d+[SQ])*(?:H2H|HA|TV|\d{1,2}:\d{2})*\s*$', '', text).strip()
                if 3 < len(text) < 120:
                    current_tournament = text
                    s_match = _SURFACE_RE.search(text)
                    if s_match:
                        current_surface = s_match.group(1).lower()
                    flag = row.find("img", attrs={"title": True})
                    if flag:
                        current_country = flag["title"]
                pending_player = None
                continue

            cells = row.find_all("td")
            if len(cells) < 1:
                continue

            # Extract player name and match URL from this row
            player_name = ""
            player_country = ""
            match_url = ""
            match_time = ""
            row_scores = []

            for link in row.find_all("a"):
                href = link.get("href", "")
                name = link.get_text(strip=True)

                if _MATCH_DETAIL_RE.search(href):
                    match_url = f"https://www.tennisexplorer.com{href}" if href.startswith("/") else href
                    continue

                # Skip bookmaker/ad links
                if re.search(r"(bonus|bet365|bwin|unibet|1xbet|betclic|betfair|pinnacle|betway|888sport|stream)", href + name, re.I):
                    continue

                if _PLAYER_LINK_RE.search(href) and name and len(name) > 2:
                    clean = re.sub(r'\s*\(\d+\)\s*$', '', name).strip()
                    if clean and not player_name:
                        player_name = clean
                        flag = link.find_previous("img", attrs={"title": True})
                        if flag and flag.parent == link.parent:
                            player_country = flag["title"]

            if not player_name:
                # Try cell text fallback
                for cell in cells:
                    text = cell.get_text(strip=True)
                    clean = re.sub(r'\s*\(\d+\)\s*$', '', text).strip()
                    if _is_player_name(clean):
                        player_name = clean
                        break

            if not player_name:
                pending_player = None
                continue

            # Extract time
            text = row.get_text(separator=" ", strip=True)
            time_match = _TIME_RE.search(text)
            if time_match:
                match_time = time_match.group()

            # Extract scores from this row
            score_cells = [c.get_text(strip=True) for c in cells if c.get_text(strip=True).isdigit() and len(c.get_text(strip=True)) == 1]
            row_scores = [int(s) for s in score_cells[:5]]  # Max 5 sets

            if pending_player is None:
                # First player of a match pair
                pending_player = {
                    "name": player_name,
                    "country": player_country,
                    "match_url": match_url,
                    "time": match_time,
                    "scores": row_scores,
                }
            else:
                # Second player — form the match entry
                entry = {
                    "home": pending_player["name"],
                    "away": player_name,
                    "time": pending_player["time"] or match_time,
                    "odds": "",
                    "league": current_tournament,
                    "sport": "tennis",
                    "source": "tennisexplorer.com",
                    "source_type": "tennisexplorer",
                    "url": url,
                    "surface": current_surface,
                }

                best_match_url = pending_player["match_url"] or match_url
                if best_match_url:
                    entry["match_url"] = best_match_url

                # Build period scores from paired rows
                home_scores = pending_player["scores"]
                away_scores = row_scores
                if home_scores and away_scores:
                    period_scores = []
                    for i in range(min(len(home_scores), len(away_scores))):
                        period_scores.append({"home": home_scores[i], "away": away_scores[i]})
                    if period_scores:
                        entry["period_scores"] = period_scores
                        # Total sets won
                        sets_home = sum(1 for p in period_scores if p["home"] > p["away"])
                        sets_away = sum(1 for p in period_scores if p["away"] > p["home"])
                        entry["score_home"] = sets_home
                        entry["score_away"] = sets_away

                if pending_player["country"]:
                    entry["country_home"] = pending_player["country"]
                if player_country:
                    entry["country_away"] = player_country
                if current_country:
                    entry["country"] = current_country

                results.append(entry)
                pending_player = None

    return results


def _parse_match_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse TennisExplorer alternative layouts."""
    results = []
    current_tournament = ""
    current_surface = ""

    for el in soup.find_all(True):
        classes = " ".join(el.get("class", []))

        # Tournament headers
        if re.search(r"tournament|event-header|flags", classes, re.I):
            text = el.get_text(strip=True)
            if 3 < len(text) < 120:
                current_tournament = text
                s_match = _SURFACE_RE.search(text)
                if s_match:
                    current_surface = s_match.group(1).lower()
                continue

        # Match containers
        if not re.search(r"match|result|game", classes, re.I):
            continue

        text = el.get_text(separator=" ", strip=True)
        if len(text) < 5 or len(text) > 300:
            continue

        links = el.find_all("a")
        players = []
        match_url = ""
        for link in links:
            href = link.get("href", "")
            name = link.get_text(strip=True)
            if _MATCH_DETAIL_RE.search(href):
                match_url = f"https://www.tennisexplorer.com{href}" if href.startswith("/") else href
            elif re.search(r"(bonus|bet365|bwin|unibet|1xbet|betclic|betfair|pinnacle|betway|888sport|stream|live\s*stream)", href + name, re.I):
                continue
            elif _PLAYER_LINK_RE.search(href) and name and len(name) > 2:
                players.append(name)
            elif not href.startswith("http") and name and _is_player_name(name):
                players.append(name)

        if len(players) >= 2:
            match_time = ""
            time_match = _TIME_RE.search(text)
            if time_match:
                match_time = time_match.group()

            surface = current_surface
            surface_match = _SURFACE_RE.search(text)
            if surface_match:
                surface = surface_match.group(1).lower()

            entry = {
                "home": players[0],
                "away": players[1],
                "time": match_time,
                "odds": "",
                "league": current_tournament,
                "sport": "tennis",
                "source": "tennisexplorer.com",
                "source_type": "tennisexplorer",
                "url": url,
                "surface": surface,
            }
            if match_url:
                entry["match_url"] = match_url
            results.append(entry)

    return results


def _parse_h2h_page(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse TennisExplorer H2H page for head-to-head records."""
    results = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            links = row.find_all("a")
            players = []
            for link in links:
                name = link.get_text(strip=True)
                if name and _is_player_name(name):
                    players.append(name)

            if len(players) >= 2:
                text = row.get_text(separator=" ", strip=True)
                score_home, score_away, period_scores = _extract_scores(row)

                entry = {
                    "home": players[0],
                    "away": players[1],
                    "time": "",
                    "sport": "tennis",
                    "source": "tennisexplorer.com",
                    "source_type": "tennisexplorer_h2h",
                    "url": url,
                }
                if score_home is not None:
                    entry["score_home"] = score_home
                    entry["score_away"] = score_away
                if period_scores:
                    entry["period_scores"] = period_scores

                s_match = _SURFACE_RE.search(text)
                if s_match:
                    entry["surface"] = s_match.group(1).lower()

                results.append(entry)

    return results


def _extract_scores(row) -> tuple:
    """Extract match scores from a table row.

    Returns: (score_home, score_away, period_scores) or (None, None, [])
    """
    text = row.get_text(separator=" ", strip=True)
    set_scores = _SET_SCORE_RE.findall(text)

    if not set_scores:
        return None, None, []

    score_home = int(set_scores[0][0])
    score_away = int(set_scores[0][1])
    period_scores = []
    for s in set_scores[1:]:
        period_scores.append({"home": int(s[0]), "away": int(s[1])})

    return score_home, score_away, period_scores


def _is_player_name(text: str) -> bool:
    """Heuristic: is this text likely a player name?"""
    if not text or len(text) < 3 or len(text) > 60:
        return False
    if text.isdigit():
        return False
    if _SCORE_RE.match(text):
        return False
    if re.match(r"^\d{1,2}:\d{2}$", text):
        return False
    _skip = {"vs", "v", "-", "ft", "ret.", "w/o", "completed", "live", "q",
              "1st", "2nd", "3rd", "4th", "5th", "final", "retired", "walkover",
              "info", "h2h", "tv", "ha", "draw",
              "bet365", "unibet", "1xbet", "betclic", "pinnacle", "betfair",
              "bwin", "betway", "888sport", "pokerstars", "william hill"}
    if text.strip().lower() in _skip:
        return False
    # Skip bookmaker/streaming related text
    if re.search(r"(bet365|bwin|unibet|1xbet|betclic|betfair|pinnacle|betway|888sport|stream|bonus|odds)", text, re.I):
        return False
    # Skip date/time labels
    if re.search(r"(Yesterday|Today|Tomorrow|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\d", text, re.I):
        return False
    if re.search(r"[a-zA-Z]", text):
        return True
    return False
