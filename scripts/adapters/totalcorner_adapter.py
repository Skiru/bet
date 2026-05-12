"""TotalCorner adapter — parses football match corner/goal data from totalcorner.com.

Extracts: teams, league, time, corner counts, goal handicaps, total goals lines,
and dangerous attack stats. This is a key source for football corner markets.

TotalCorner table structure:
  tr > td.td_league (league name)
       td (time)
       td.match_status (match minute or status)
       td.match_home (home team)
       td.match_goal (score)
       td.match_away (away team)
       td.match_handicap (corner handicap line)
       td with corner data (corner counts)
       td with total goals (goal total line)
       td with dangerous attacks
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)


def parse(html: str, url: str) -> List[Dict]:
    """Parse TotalCorner match listing page."""
    logger.info(f"TotalCorner parse start: {url} ({len(html)} bytes)")
    soup = BeautifulSoup(html, "html.parser")
    results = []

    trs = soup.find_all("tr")
    for tr in trs:
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue

        # Find cells by class
        league_td = tr.find("td", class_="td_league")
        home_td = tr.find("td", class_="match_home")
        away_td = tr.find("td", class_="match_away")
        goal_td = tr.find("td", class_="match_goal")
        handicap_td = tr.find("td", class_="match_handicap")

        if not home_td or not away_td:
            continue

        # Extract team name from the <a> link inside the cell, not the full cell
        # (cell contains yellow/red card counts and league position spans)
        home_link = home_td.find("a")
        away_link = away_td.find("a")
        home = home_link.get_text(strip=True) if home_link else home_td.get_text(strip=True)
        away = away_link.get_text(strip=True) if away_link else away_td.get_text(strip=True)

        if not home or not away:
            continue

        yellow_home = None
        yellow_away = None
        red_home = None
        red_away = None
        if home_td:
            yc = home_td.find("span", class_=re.compile(r"yellow|card_y", re.I))
            if yc:
                try: yellow_home = float(yc.get_text(strip=True))
                except (ValueError, TypeError, AttributeError): pass
            rc = home_td.find("span", class_=re.compile(r"red|card_r", re.I))
            if rc:
                try: red_home = float(rc.get_text(strip=True))
                except (ValueError, TypeError, AttributeError): pass
        if away_td:
            yc = away_td.find("span", class_=re.compile(r"yellow|card_y", re.I))
            if yc:
                try: yellow_away = float(yc.get_text(strip=True))
                except (ValueError, TypeError, AttributeError): pass
            rc = away_td.find("span", class_=re.compile(r"red|card_r", re.I))
            if rc:
                try: red_away = float(rc.get_text(strip=True))
                except (ValueError, TypeError, AttributeError): pass
        
        cards = {"yellow_home": yellow_home, "yellow_away": yellow_away, "red_home": red_home, "red_away": red_away}

        pos_match_home = re.search(r"\[(\d+)\]", home)
        pos_match_away = re.search(r"\[(\d+)\]", away)
        standings = {
            "home_pos": int(pos_match_home.group(1)) if pos_match_home else None,
            "away_pos": int(pos_match_away.group(1)) if pos_match_away else None
        }

        # Clean team names: remove ranking brackets like [3] or [12]
        # Only strip when square brackets are present to avoid removing
        # legitimate trailing digits (e.g., "Dynamo2", "1860 Munich")
        home = re.sub(r"\[\d+\]$", "", home).strip()
        home = re.sub(r"^\[\d+\]", "", home).strip()
        away = re.sub(r"^\[\d+\]", "", away).strip()
        away = re.sub(r"\[\d+\]$", "", away).strip()

        if not home or not away or len(home) < 2 or len(away) < 2:
            continue

        league = league_td.get_text(strip=True) if league_td else ""
        score = goal_td.get_text(strip=True) if goal_td else ""

        # Get time from the cell after league
        time_str = None
        time_td = tds[2] if len(tds) > 2 else None
        if time_td:
            txt = time_td.get_text(strip=True)
            if re.match(r"\d{1,2}:\d{2}", txt):
                time_str = txt

        # Corner handicap
        corner_handicap = None
        if handicap_td:
            hc_text = handicap_td.get_text(strip=True)
            if hc_text:
                corner_handicap = hc_text

        # Find corner counts (in the td after handicap)
        corner_count = None
        corners_ht_home = None
        corners_ht_away = None
        if handicap_td:
            next_td = handicap_td.find_next_sibling("td")
            if next_td:
                cc = next_td.get_text(strip=True)
                # Pattern: "5 - 3(4-2)" or "1 - 4(0-2)"
                m = re.match(r"(\d+)\s*-\s*(\d+)", cc)
                if m:
                    corner_count = f"{m.group(1)}-{m.group(2)}"
                ht_match = re.search(r"\((\d+)\s*-\s*(\d+)\)", cc) if cc else None
                if ht_match:
                    corners_ht_home = int(ht_match.group(1))
                    corners_ht_away = int(ht_match.group(2))

        # Find total goals line
        total_goals = None
        for td in tds:
            txt = td.get_text(strip=True)
            # Pattern: "2.25 ( 0.5)" or "3.25 (3.75)"
            m = re.match(r"(\d+\.?\d*)\s*\(", txt)
            classes = td.get("class", [])
            if m and "match_handicap" not in classes and "match_status" not in classes:
                total_goals = txt
                break
                
        attack_home = None
        attack_away = None
        for td in tds:
            cls = " ".join(td.get("class", []))
            if "attack" in cls.lower() or "danger" in cls.lower():
                txt = td.get_text(strip=True)
                m = re.match(r"(\d+)\s*[-–]\s*(\d+)", txt)
                if m:
                    attack_home = int(m.group(1))
                    attack_away = int(m.group(2))
                    break

        result = {
            "home": home,
            "away": away,
            "time": time_str,
            "source_url": url,
            "raw": f"{home} vs {away}",
            "sport": "football",
            "source_type": "totalcorner",
            "cards": cards,
            "standings": standings,
            "dangerous_attacks": {"home": attack_home, "away": attack_away},
        }

        if corners_ht_home is not None:
            result["corners_ht_home"] = corners_ht_home
        if corners_ht_away is not None:
            result["corners_ht_away"] = corners_ht_away

        if league:
            result["league"] = league
        if score and re.match(r"\d+\s*-\s*\d+", score):
            result["score"] = score
        if corner_handicap:
            result["corner_handicap"] = corner_handicap
        if corner_count:
            result["corner_count"] = corner_count
        if total_goals:
            result["total_goals_line"] = total_goals

        # Extract match detail URL from row links
        match_link = tr.find("a", href=True)
        if match_link:
            href = match_link["href"]
            if href and not href.startswith("javascript"):
                match_url = href if href.startswith("http") else f"https://www.totalcorner.com{href}"
                result["match_url"] = match_url

        results.append(result)

    logger.info(f"TotalCorner parse complete: {len(results)} matches")
    # Deduplicate
    from adapters import dedup_results
    return dedup_results(results)


def get_deep_links(html: str, url: str) -> list[str]:
    """Extract match detail URLs from TotalCorner listing page."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r'/match/\d+|/corner/', href, re.I):
            full_url = href
            if full_url.startswith("/"):
                full_url = "https://www.totalcorner.com" + full_url
            if full_url not in links:
                links.append(full_url)
    logger.info(f"TotalCorner: found {len(links)} deep links")
    return links
