"""Forebet adapter — parses match predictions from forebet.com pages.

Handles both football (3-way probabilities) and tennis/other sports (2-way).
Extracts: teams, datetime, probabilities, predicted winner, avg games/goals,
predicted score, and match detail URL.

Forebet HTML structure:
  Row container (varies: div with rcnt, tr, or parent of div.tnms)
    div.tnms > div > a.tnmscn
        span.homeTeam > span (team name)
        span.awayTeam > span (team name)
        span.date_bah (date/time string: "DD/MM/YYYY HH:MM")
    div.fprc (probabilities)
        span (home win %)
        span.fpr (away win %) — for 2-way sports
        OR span/span/span (1X2 for football)
    div.predict > span.forepr (predicted winner: 1, X, or 2)
    div.ex_sc (predicted score)
    div.avg_sc (avg goals/games per set/match)
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re

# Date pattern in Forebet: DD/MM/YYYY HH:MM
_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}:\d{2})")


def _detect_sport(url: str) -> str:
    """Detect sport from Forebet URL path."""
    url_lower = url.lower()
    if "/tennis/" in url_lower:
        return "tennis"
    if "/basketball/" in url_lower:
        return "basketball"
    if "/hockey/" in url_lower:
        return "hockey"
    if "/volleyball/" in url_lower:
        return "volleyball"
    return "football"


def _parse_match_row(link_el, sport: str, source_url: str) -> Dict | None:
    """Parse a single match row from a Forebet tnmscn link element."""
    home_el = link_el.find("span", class_="homeTeam")
    away_el = link_el.find("span", class_="awayTeam")
    date_el = link_el.find("span", class_="date_bah")

    if not home_el or not away_el:
        return None

    home = home_el.get_text(strip=True)
    away = away_el.get_text(strip=True)

    if not home or not away:
        return None

    # Parse time
    time_str = None
    date_str = None
    if date_el:
        raw_date = date_el.get_text(strip=True)
        m = _DATE_RE.match(raw_date)
        if m:
            day, month, year, time_part = m.groups()
            time_str = time_part
            date_str = f"{year}-{month}-{day}"

    # Get match detail URL
    href = link_el.get("href", "")
    detail_url = f"https://www.forebet.com{href}" if href and href.startswith("/") else href

    # Walk up to find the row container that has probability data
    # Structure: a.tnmscn -> div -> div.tnms -> ROW_CONTAINER
    row = link_el.parent  # div wrapper
    if row:
        row = row.parent  # div.tnms
    if row:
        row = row.parent  # row container

    probs = {}
    prediction = None
    predicted_score = None
    avg_stat = None

    if row:
        # Extract probabilities
        fprc = row.find("div", class_=lambda c: c and "fprc" in c)
        if fprc:
            spans = fprc.find_all("span", recursive=True)
            prob_vals = []
            for s in spans:
                txt = s.get_text(strip=True)
                if txt.isdigit() and 0 < int(txt) <= 100:
                    prob_vals.append(int(txt))
            if len(prob_vals) == 3:
                probs = {"home": prob_vals[0], "draw": prob_vals[1], "away": prob_vals[2]}
            elif len(prob_vals) == 2:
                probs = {"home": prob_vals[0], "away": prob_vals[1]}

        # Extract prediction
        pred_el = row.find("span", class_="forepr")
        if pred_el:
            prediction = pred_el.get_text(strip=True)

        # Extract predicted score
        score_el = row.find("div", class_="ex_sc")
        if score_el:
            score_text = score_el.get_text(strip=True)
            if re.match(r"\d+\s*[-–]\s*\d+", score_text):
                predicted_score = score_text

        # Extract average stat (goals for football, games per set for tennis)
        avg_el = row.find("div", class_="avg_sc")
        if avg_el:
            avg_text = avg_el.get_text(strip=True)
            try:
                avg_stat = float(avg_text)
            except (ValueError, TypeError):
                pass

    result = {
        "home": home,
        "away": away,
        "time": time_str,
        "source_url": source_url,
        "raw": f"{home} vs {away}",
        "sport": sport,
        "source_type": "forebet",
    }

    if date_str:
        result["date"] = date_str
    if detail_url:
        result["detail_url"] = detail_url
    if probs:
        result["forebet_probs"] = probs
    if prediction:
        result["forebet_prediction"] = prediction
    if predicted_score:
        result["forebet_score"] = predicted_score
    if avg_stat is not None:
        result["forebet_avg"] = avg_stat

    return result


def parse(html: str, url: str) -> List[Dict]:
    """Parse a Forebet predictions page and extract match predictions."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    sport = _detect_sport(url)

    links = soup.find_all("a", class_="tnmscn")

    for link in links:
        match = _parse_match_row(link, sport, url)
        if match:
            results.append(match)

    # Deduplicate
    from adapters import dedup_results
    return dedup_results(results)
