"""Site adapter for Basketball-Reference — deep NBA/WNBA box scores and schedules.

Extracts: match lines (home/away/time/competition), scores.
Basketball-Reference uses clean HTML tables, making parsing reliable.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}\s*[ap]m?)\b", re.I)
_DATE_RE = re.compile(r"\b(\w+\s+\d{1,2},\s*\d{4})\b")
_SCORE_RE = re.compile(r"(\d{2,3})\s*[-–]\s*(\d{2,3})")


def parse(html: str, url: str) -> List[Dict]:
    """Parse Basketball-Reference HTML for match/schedule data."""
    soup = BeautifulSoup(html, "html.parser")

    if "/boxscores/" in url:
        results = _parse_box_score(soup, url)
        if results:
            return results
            
    if "/teams/" in url and re.search(r"/\d{4}\.html", url):
        results = _parse_team_stats(soup, url)
        if results:
            return results

    results = _parse_schedule_table(soup, url)
    if not results:
        results = _parse_game_rows(soup, url)
    if not results:
        return raw_parse(html, url)
    return results

def get_deep_links(html: str, url: str) -> list[str]:
    """Extract box score URLs from a schedule page for deep link discovery."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for cell in soup.find_all(["td", "th"], attrs={"data-stat": "box_score_text"}):
        a = cell.find("a")
        if a and a.get("href"):
            href = a.get("href")
            if href.startswith("/"):
                links.append("https://www.basketball-reference.com" + href)
    return links

def _get_stat(elem, stat_name: str, default=0.0):
    """Helper to extract a numeric stat from a data-stat cell."""
    cell = elem.find(["td", "th"], attrs={"data-stat": stat_name})
    if cell:
        text = cell.get_text(strip=True)
        if text:
            try:
                return float(text)
            except (ValueError, TypeError):
                pass
    return default

def _parse_box_score(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse a box score page returning team totals."""
    basic_tables = soup.find_all("table", id=re.compile(r"box-[a-zA-Z0-9]+-game-basic", re.I))
    if len(basic_tables) < 2:
        return []
    
    scorebox = soup.find("div", class_=re.compile(r"scorebox", re.I))
    away_name = "Away"
    home_name = "Home"
    if scorebox:
        teams = scorebox.find_all("strong")
        team_links = [t.find("a") for t in teams if t.find("a")]
        if len(team_links) >= 2:
            away_name = team_links[0].get_text(strip=True)
            home_name = team_links[1].get_text(strip=True)

    result = {
        "home": home_name,
        "away": away_name,
        "stats": {k: {"home": 0.0, "away": 0.0} for k in [
            "points", "rebounds", "offensive_rebounds", "defensive_rebounds",
            "assists", "steals", "blocks", "turnovers", "fouls",
            "fg_pct", "three_pct", "ft_pct"
        ]},
        "sport": "basketball",
        "source_type": "basketball_reference",
        "source_url": url,
        "league": "NBA",
    }
    
    for i, table in enumerate(basic_tables[:2]):
        team_key = "away" if i == 0 else "home"
        tfoot = table.find("tfoot")
        if not tfoot:
            continue
        
        for tr in tfoot.find_all("tr"):
            pts = _get_stat(tr, "pts", None)
            if pts is None:
                continue
            result["stats"]["points"][team_key] = pts
            result["stats"]["rebounds"][team_key] = _get_stat(tr, "trb", 0.0)
            result["stats"]["offensive_rebounds"][team_key] = _get_stat(tr, "orb", 0.0)
            result["stats"]["defensive_rebounds"][team_key] = _get_stat(tr, "drb", 0.0)
            result["stats"]["assists"][team_key] = _get_stat(tr, "ast", 0.0)
            result["stats"]["steals"][team_key] = _get_stat(tr, "stl", 0.0)
            result["stats"]["blocks"][team_key] = _get_stat(tr, "blk", 0.0)
            result["stats"]["turnovers"][team_key] = _get_stat(tr, "tov", 0.0)
            result["stats"]["fouls"][team_key] = _get_stat(tr, "pf", 0.0)
            result["stats"]["fg_pct"][team_key] = _get_stat(tr, "fg_pct", 0.0)
            result["stats"]["three_pct"][team_key] = _get_stat(tr, "fg3_pct", 0.0)
            result["stats"]["ft_pct"][team_key] = _get_stat(tr, "ft_pct", 0.0)
            break  # Only process first valid totals row

    return [result]

def _parse_team_stats(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse a team season page returning per game averages."""
    table = soup.find("table", id="per_game")
    if not table:
        table = soup.find("table", id=re.compile(r"per_game", re.I))
    if not table:
        return []

    h1 = soup.find("h1")
    team_name = "Unknown"
    if h1:
        spans = h1.find_all("span")
        if len(spans) > 1:
            team_name = spans[1].get_text(strip=True)
        else:
            team_name = h1.get_text(strip=True)

    result = {
        "team": team_name,
        "season_averages": {},
        "sport": "basketball",
        "source_type": "basketball_reference",
        "source_url": url,
    }
    
    tfoot = table.find("tfoot")
    if tfoot:
        team_row = tfoot.find("tr")
        if team_row:
            def _avg(primary, fallback):
                v = _get_stat(team_row, primary, None)
                return v if v is not None else _get_stat(team_row, fallback, 0.0)
            result["season_averages"]["points"] = _avg("pts_per_g", "pts")
            result["season_averages"]["rebounds"] = _avg("trb_per_g", "trb")
            result["season_averages"]["assists"] = _avg("ast_per_g", "ast")
            result["season_averages"]["steals"] = _avg("stl_per_g", "stl")
            result["season_averages"]["blocks"] = _avg("blk_per_g", "blk")
            result["season_averages"]["turnovers"] = _avg("tov_per_g", "tov")
            result["season_averages"]["offensive_rebounds"] = _avg("orb_per_g", "orb")
            result["season_averages"]["defensive_rebounds"] = _avg("drb_per_g", "drb")
            result["season_averages"]["fg_pct"] = _get_stat(team_row, "fg_pct", 0.0)
            result["season_averages"]["three_pct"] = _get_stat(team_row, "fg3_pct", 0.0)
            result["season_averages"]["ft_pct"] = _get_stat(team_row, "ft_pct", 0.0)
            
    return [result]


def _parse_schedule_table(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse Basketball-Reference's schedule tables (id='schedule')."""
    results = []
    schedule = soup.find("table", id="schedule")
    if not schedule:
        # Also try other common table IDs
        schedule = soup.find("table", id=re.compile(r"games|schedule|scores", re.I))
    if not schedule:
        return []

    rows = schedule.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        # Try to extract date, teams, and time
        date_text = ""
        home = ""
        away = ""
        kickoff = ""
        match_url = ""

        for cell in cells:
            data_stat = cell.get("data-stat", "")
            text = cell.get_text(strip=True)

            if data_stat == "date_game":
                date_text = text
            elif data_stat == "visitor_team_name":
                a = cell.find("a")
                away = a.get_text(strip=True) if a else text
            elif data_stat == "home_team_name":
                a = cell.find("a")
                home = a.get_text(strip=True) if a else text
            elif data_stat == "game_start_time":
                kickoff = text
            elif data_stat == "box_score_text":
                a = cell.find("a")
                if a and a.get("href"):
                    href = a.get("href")
                    if href.startswith("/"):
                        match_url = "https://www.basketball-reference.com" + href

        if home and away:
            results.append({
                "home": home,
                "away": away,
                "time": kickoff or date_text,
                "league": "NBA",
                "sport": "basketball",
                "source_url": url,
                "source_type": "basketball_reference",
                "raw": f"{home} vs {away}",
                "match_url": match_url
            })

    return results


def _parse_game_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Fallback: parse any game summary blocks."""
    results = []

    # Look for game_summary divs (box score pages)
    for div in soup.find_all("div", class_=re.compile(r"game_summary|scorebox", re.I)):
        teams = div.find_all("a", href=re.compile(r"/teams/", re.I))
        if len(teams) >= 2:
            away = teams[0].get_text(strip=True)
            home = teams[1].get_text(strip=True)
            if home and away and len(home) < 60 and len(away) < 60:
                results.append({
                    "home": home,
                    "away": away,
                    "time": "",
                    "league": "NBA",
                    "sport": "basketball",
                    "source_url": url,
                    "source_type": "basketball_reference",
                    "raw": f"{home} vs {away}"
                })

    return results
