"""Site adapter for Hockey-Reference — NHL detailed stats and schedules.

Extracts: match lines (home/away/time/competition), scores.
Hockey-Reference uses clean HTML tables similar to Basketball-Reference.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


_SCORE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")


def parse(html: str, url: str) -> List[Dict]:
    """Parse Hockey-Reference HTML for match/schedule data."""
    soup = BeautifulSoup(html, "html.parser")

    if "/boxscores/" in url or re.search(r"/boxscores/\d{9}\w+\.html", url):
        results = _parse_boxscore(soup, url)
        if results:
            return results

    results = _parse_schedule_table(soup, url)
    if not results:
        results = _parse_game_rows(soup, url)
    if not results:
        return raw_parse(html, url)
    return results


def _parse_boxscore(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse Hockey-Reference box score page."""
    scorebox = soup.find("div", class_="scorebox")
    if not scorebox:
        return []

    teams_blocks = scorebox.find_all("div", recursive=False)[:2]
    if len(teams_blocks) < 2:
        return []

    away_a = teams_blocks[0].find("a")
    home_a = teams_blocks[1].find("a")
    away_team = away_a.get_text(strip=True) if away_a else teams_blocks[0].get_text(strip=True)
    home_team = home_a.get_text(strip=True) if home_a else teams_blocks[1].get_text(strip=True)

    if not away_team or not home_team:
        return []

    away_score_div = teams_blocks[0].find("div", class_="score")
    home_score_div = teams_blocks[1].find("div", class_="score")

    try:
        away_score = int(away_score_div.get_text(strip=True)) if away_score_div else 0
        home_score = int(home_score_div.get_text(strip=True)) if home_score_div else 0
    except ValueError:
        away_score = home_score = 0

    # period scores
    period_scores = {"home": [], "away": []}
    scoring_table = soup.find("table", id="scoring")
    if scoring_table:
        tbody = scoring_table.find("tbody")
        if tbody:
            for tr in tbody.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) >= 3:
                    try:
                        period_scores["away"].append(int(cells[1].get_text(strip=True)))
                        period_scores["home"].append(int(cells[2].get_text(strip=True)))
                    except ValueError:
                        pass

    stats = {
        "goals": {"home": 0, "away": 0},
        "shots": {"home": 0, "away": 0},
        "pim": {"home": 0, "away": 0},
        "pp_goals": {"home": 0, "away": 0},
        "pp_opportunities": {"home": 0, "away": 0},
        "hits": {"home": 0, "away": 0},
        "blocks": {"home": 0, "away": 0},
        "faceoff_wins": {"home": 0, "away": 0},
        "faceoff_losses": {"home": 0, "away": 0},
    }

    # Team stats tables use data-stat attributes
    for tr in soup.find_all("tr"):
        away_td = tr.find("td", attrs={"data-stat": "visitor_team_name"})
        home_td = tr.find("td", attrs={"data-stat": "home_team_name"})
        if away_td or home_td:
            team_key = "away" if away_td else "home"

            def get_stat(td_name, default=0):
                td = tr.find("td", attrs={"data-stat": td_name})
                if td:
                    try:
                        return int(td.get_text(strip=True))
                    except ValueError:
                        return default
                return default

            stats["goals"][team_key] = get_stat("goals", stats["goals"][team_key])
            stats["shots"][team_key] = get_stat("shots", stats["shots"][team_key])
            # Handle alternative for shots
            if stats["shots"][team_key] == 0:
                stats["shots"][team_key] = get_stat("shotsOnGoal", stats["shots"][team_key])
            stats["pim"][team_key] = get_stat("pim", stats["pim"][team_key])
            stats["pp_goals"][team_key] = get_stat("pp", stats["pp_goals"][team_key])
            stats["pp_opportunities"][team_key] = get_stat("ppoa", stats["pp_opportunities"][team_key])
            stats["hits"][team_key] = get_stat("hits", stats["hits"][team_key])
            stats["blocks"][team_key] = get_stat("blocks", stats["blocks"][team_key])
            stats["faceoff_wins"][team_key] = get_stat("fow", stats["faceoff_wins"][team_key])
            stats["faceoff_losses"][team_key] = get_stat("fol", stats["faceoff_losses"][team_key])

    goalie_stats = {"home": {}, "away": {}}
    for tfoot in soup.find_all("tfoot"):
        sv = tfoot.find("td", attrs={"data-stat": "saves"})
        sv_pct = tfoot.find("td", attrs={"data-stat": "save_pct"})
        gaa = tfoot.find("td", attrs={"data-stat": "goals_against_avg"})
        if sv:
            table = tfoot.find_parent("table")
            team_key = "home" if table and "home" in table.get("id", "").lower() else "away"
            # It's an approximation, sometimes table ID doesn't have home/away cleanly, but usually standard HR boxscores do
            try:
                goalie_stats[team_key]["saves"] = int(sv.get_text(strip=True))
            except ValueError:
                pass
            if sv_pct:
                try:
                    goalie_stats[team_key]["save_pct"] = float(sv_pct.get_text(strip=True))
                except ValueError:
                    pass
            if gaa:
                try:
                    goalie_stats[team_key]["gaa"] = float(gaa.get_text(strip=True))
                except ValueError:
                    pass

    # Dynamic league detection based on URL
    league = "NHL"
    league_match = re.search(r"/(olympics|wha|nwhl|pwhl)/", url, re.I)
    if league_match:
        league = league_match.group(1).upper()

    return [{
        "home": home_team,
        "away": away_team,
        "time": "",
        "league": league,
        "sport": "hockey",
        "source_url": url,
        "source_type": "hockey_reference",
        "score_home": home_score,
        "score_away": away_score,
        "period_scores": period_scores,
        "stats": stats,
        "goalie_stats": goalie_stats,
        "raw": f"{away_team} vs {home_team}"
    }]


def _parse_schedule_table(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Parse Hockey-Reference's schedule tables."""
    results = []
    schedule = soup.find("table", id=re.compile(r"games|schedule|scores", re.I))
    if not schedule:
        return []

    rows = schedule.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        date_text = ""
        home = ""
        away = ""
        kickoff = ""

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

        if home and away:
            results.append({
                "home": home,
                "away": away,
                "time": kickoff or date_text,
                "league": "NHL",
                "sport": "hockey",
                "source_url": url,
                "source_type": "hockey_reference",
                "raw": f"{home} vs {away}"
            })

    return results


def _parse_game_rows(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Fallback: parse game summary blocks."""
    results = []

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
                    "league": "NHL",
                    "sport": "hockey",
                    "source_url": url,
                    "source_type": "hockey_reference",
                    "raw": f"{home} vs {away}"
                })

    return results
