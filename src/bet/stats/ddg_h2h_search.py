"""DuckDuckGo-based H2H search for tennis players.

Uses duckduckgo_search library (free, no API key) to find head-to-head
records between two players, then parses results to extract match history.

Fallback L6 in tennis H2H chain — works when tennis-abstract is rate-limited
and SofaScore event H2H is unavailable.
"""

import json
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Delay between DDG searches to avoid rate-limiting
DDG_DELAY = 2.0


def search_tennis_h2h(
    player_a: str,
    player_b: str,
    max_results: int = 8,
) -> Optional[dict]:
    """Search DuckDuckGo for H2H data between two tennis players.

    Returns:
        dict with keys:
            - meetings: list of dicts with date, winner, score, sets, games
            - total_meetings: int
            - player_a_wins: int
            - player_b_wins: int
            - source: str (URL of best source)
        or None if no H2H data found.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.error("duckduckgo_search not installed")
        return None

    queries = [
        f'"{player_a}" vs "{player_b}" head to head tennis',
        f'"{player_a}" "{player_b}" h2h tennis results',
    ]

    all_results = []
    for query in queries:
        try:
            time.sleep(DDG_DELAY)
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                all_results.extend(results)
        except Exception as e:
            logger.debug(f"DDG search failed for '{query}': {e}")
            continue

    if not all_results:
        return None

    # Try to extract H2H data from snippets
    h2h_data = _parse_h2h_from_snippets(all_results, player_a, player_b)

    if h2h_data and h2h_data.get("total_meetings", 0) > 0:
        return h2h_data

    # If snippets didn't yield enough, try fetching top result pages
    priority_domains = ["tennisabstract.com", "sofascore.com", "flashscore.com", "atptour.com", "stevegtennis.com"]
    for result in all_results[:5]:
        url = result.get("href", "")
        if any(domain in url for domain in priority_domains):
            page_data = _fetch_and_parse_h2h_page(url, player_a, player_b)
            if page_data and page_data.get("total_meetings", 0) > 0:
                page_data["source"] = url
                return page_data

    return h2h_data


def _parse_h2h_from_snippets(
    results: list[dict],
    player_a: str,
    player_b: str,
) -> Optional[dict]:
    """Extract H2H record from search result snippets.

    Many results contain patterns like "Player A leads 3-1" or "2 wins, 1 loss".
    """
    h2h = {
        "meetings": [],
        "total_meetings": 0,
        "player_a_wins": 0,
        "player_b_wins": 0,
        "source": None,
    }

    name_a_parts = player_a.lower().split()
    name_b_parts = player_b.lower().split()
    surname_a = name_a_parts[-1] if name_a_parts else ""
    surname_b = name_b_parts[-1] if name_b_parts else ""

    for result in results:
        body = result.get("body", "") or result.get("snippet", "")
        title = result.get("title", "")
        text = f"{title} {body}".lower()

        # Pattern: "X leads Y-Z" or "X leads the h2h Y-Z"
        lead_pattern = re.compile(
            rf'({re.escape(surname_a)}|{re.escape(surname_b)})\s+leads?\s+(?:the\s+)?(?:h2h\s+)?(\d+)\s*[-–]\s*(\d+)',
            re.IGNORECASE,
        )
        match = lead_pattern.search(text)
        if match:
            leader = match.group(1).lower()
            wins = int(match.group(2))
            losses = int(match.group(3))
            if leader == surname_a.lower():
                h2h["player_a_wins"] = wins
                h2h["player_b_wins"] = losses
            else:
                h2h["player_a_wins"] = losses
                h2h["player_b_wins"] = wins
            h2h["total_meetings"] = wins + losses
            h2h["source"] = result.get("href", "")
            break

        # Pattern: "head to head: X-Y" or "h2h: X-Y" or "X - Y in ... meetings"
        h2h_pattern = re.compile(
            r'(?:head\s*to\s*head|h2h)[:\s]+(\d+)\s*[-–]\s*(\d+)',
            re.IGNORECASE,
        )
        match = h2h_pattern.search(text)
        if match:
            # Need to determine who has which score
            score_1 = int(match.group(1))
            score_2 = int(match.group(2))
            # Check if player_a is mentioned first
            a_pos = text.find(surname_a.lower())
            b_pos = text.find(surname_b.lower())
            if a_pos >= 0 and b_pos >= 0 and a_pos < b_pos:
                h2h["player_a_wins"] = score_1
                h2h["player_b_wins"] = score_2
            else:
                h2h["player_a_wins"] = score_2
                h2h["player_b_wins"] = score_1
            h2h["total_meetings"] = score_1 + score_2
            h2h["source"] = result.get("href", "")
            break

        # Pattern: "X wins, Y losses" relative to one player
        wins_pattern = re.compile(
            rf'({re.escape(surname_a)}|{re.escape(surname_b)}).*?(\d+)\s*wins?\s*.*?(\d+)\s*loss',
            re.IGNORECASE,
        )
        match = wins_pattern.search(text)
        if match:
            player = match.group(1).lower()
            wins = int(match.group(2))
            losses = int(match.group(3))
            if player == surname_a.lower():
                h2h["player_a_wins"] = wins
                h2h["player_b_wins"] = losses
            else:
                h2h["player_a_wins"] = losses
                h2h["player_b_wins"] = wins
            h2h["total_meetings"] = wins + losses
            h2h["source"] = result.get("href", "")
            break

    # Try to extract individual match scores from snippets
    score_pattern = re.compile(r'(\d)-(\d)\s*[,;]\s*(\d)-(\d)(?:\s*[,;]\s*(\d)-(\d))?')
    for result in results:
        body = result.get("body", "") or result.get("snippet", "")
        matches_found = score_pattern.findall(body)
        for m in matches_found[:10]:
            sets = []
            total_games = 0
            for i in range(0, len(m), 2):
                if m[i] and m[i + 1]:
                    g1, g2 = int(m[i]), int(m[i + 1])
                    sets.append(f"{g1}-{g2}")
                    total_games += g1 + g2
            if sets:
                h2h["meetings"].append({
                    "score": ", ".join(sets),
                    "total_sets": len(sets),
                    "total_games": total_games,
                })

    return h2h if h2h["total_meetings"] > 0 else None


def _fetch_and_parse_h2h_page(
    url: str,
    player_a: str,
    player_b: str,
) -> Optional[dict]:
    """Fetch a page and try to extract H2H match data.

    Only fetches known-safe domains. Returns parsed H2H dict or None.
    """
    import requests

    safe_domains = ["tennisabstract.com", "stevegtennis.com", "atptour.com"]
    if not any(domain in url for domain in safe_domains):
        return None

    try:
        time.sleep(1.5)
        resp = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            },
        )
        if resp.status_code != 200:
            return None

        return _parse_h2h_html(resp.text, player_a, player_b)
    except Exception as e:
        logger.debug(f"Failed to fetch H2H page {url}: {e}")
        return None


def _parse_h2h_html(html: str, player_a: str, player_b: str) -> Optional[dict]:
    """Parse H2H match data from an HTML page."""
    h2h = {
        "meetings": [],
        "total_meetings": 0,
        "player_a_wins": 0,
        "player_b_wins": 0,
        "source": "web-page",
    }

    surname_a = player_a.split()[-1].lower()
    surname_b = player_b.split()[-1].lower()

    # Extract match scores — pattern: "6-4 6-3" or "7-6(4) 3-6 6-2"
    score_pattern = re.compile(
        r'(\d-\d(?:\(\d+\))?)\s+(\d-\d(?:\(\d+\))?)'
        r'(?:\s+(\d-\d(?:\(\d+\))?))?'
        r'(?:\s+(\d-\d(?:\(\d+\))?))?'
        r'(?:\s+(\d-\d(?:\(\d+\))?))?'
    )

    matches_found = score_pattern.findall(html)
    for m in matches_found[:15]:
        sets = [s for s in m if s]
        if len(sets) >= 2:
            total_games = 0
            for s in sets:
                # Parse "6-4" or "7-6(4)"
                nums = re.findall(r'(\d+)', s)
                if len(nums) >= 2:
                    total_games += int(nums[0]) + int(nums[1])

            h2h["meetings"].append({
                "score": " ".join(sets),
                "total_sets": len(sets),
                "total_games": total_games,
            })

    h2h["total_meetings"] = len(h2h["meetings"])

    # Try to count wins per player from context around scores
    text_lower = html.lower()
    a_wins = text_lower.count(f"{surname_a}") - text_lower.count(f"def. {surname_a}")
    b_wins = text_lower.count(f"{surname_b}") - text_lower.count(f"def. {surname_b}")

    # Better: count "Player def. Opponent" patterns
    def_a = len(re.findall(rf'{re.escape(surname_a)}.*?def', text_lower))
    def_b = len(re.findall(rf'{re.escape(surname_b)}.*?def', text_lower))
    if def_a + def_b > 0:
        h2h["player_a_wins"] = def_a
        h2h["player_b_wins"] = def_b

    return h2h if h2h["total_meetings"] > 0 else None


def convert_h2h_to_stat_values(
    h2h_data: dict,
    stat_key: str = "total_games",
) -> list[float]:
    """Convert parsed H2H meetings to stat values for team_form storage.

    Args:
        h2h_data: Dict from search_tennis_h2h()
        stat_key: One of 'total_games', 'total_sets'

    Returns:
        List of float values suitable for h2h_values in team_form.
    """
    values = []
    for meeting in h2h_data.get("meetings", []):
        if stat_key == "total_games":
            val = meeting.get("total_games")
        elif stat_key == "total_sets":
            val = meeting.get("total_sets")
        else:
            val = meeting.get(stat_key)

        if val is not None:
            values.append(float(val))

    return values
