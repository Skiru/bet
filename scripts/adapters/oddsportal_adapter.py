"""Site adapter for OddsPortal (heuristic odds extraction).

This adapter looks for table rows that often contain odds in OddsPortal pages.
It extracts simple markets when possible and otherwise falls back to `raw_adapter`.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse

ODDS_RE = re.compile(r"\b\d+\.\d{2}\b")

# Sports where OddsPortal shows 2-way odds (no draw)
_TWO_WAY_URL_PATTERNS = (
    "/tennis/", "/basketball/", "/volleyball/",
)


def _is_two_way(url: str) -> bool:
    """Detect if URL is for a 2-way sport (no draw)."""
    url_lower = url.lower()
    return any(pat in url_lower for pat in _TWO_WAY_URL_PATTERNS)


def _build_odds_structured(odds: List[str], two_way: bool) -> Dict:
    """Build named odds dict based on sport type."""
    try:
        vals = [float(o) for o in odds]
    except (ValueError, TypeError):
        return {}

    if two_way and len(vals) >= 2:
        return {"home_win": vals[0], "away_win": vals[1]}
    elif not two_way and len(vals) >= 3:
        return {"home_win": vals[0], "draw": vals[1], "away_win": vals[2]}
    return {}


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    two_way = _is_two_way(url)

    # OddsPortal renders match data via React/JS — HTML contains league
    # navigation links with "X - Y" patterns that are NOT matches.
    # Filter out league/navigation links that look like "3. CFL - Group A (6)".
    _LEAGUE_NAV_RE = re.compile(
        r"group\s+[a-z]|\bliga\b|\bleague\b|\bdivision\b|\bcup\b|\bplay\s*off|"
        r"\(\d+\)$|\d+\.\s+\w+\s+-\s+",
        re.I,
    )

    # --- Strategy 1: React SPA DOM with participant-name elements ---
    participants = soup.find_all(class_="participant-name")
    if len(participants) >= 2:
        for i in range(0, len(participants) - 1, 2):
            home = participants[i].get_text(strip=True)
            away = participants[i + 1].get_text(strip=True)
            if len(home) < 2 or len(away) < 2:
                continue
            # Walk up to find container with odds
            odds_texts = []
            match_url = ""
            container = participants[i].parent
            for _ in range(8):
                if not container:
                    break
                odds_els = container.find_all(
                    class_=lambda c: c and "default-odds-bg-bgcolor" in c if c else False
                )
                if odds_els:
                    odds_texts = [
                        o.get_text(strip=True) for o in odds_els
                        if o.get_text(strip=True) and o.get_text(strip=True) != "-"
                    ]
                    break
                container = container.parent
            # Try to find match URL from nearby <a> with h2h path
            link_parent = participants[i].parent
            for _ in range(4):
                if not link_parent:
                    break
                link = link_parent.find("a", href=re.compile(r"/h2h/"))
                if link:
                    match_url = link.get("href", "")
                    if match_url and not match_url.startswith("http"):
                        match_url = f"https://www.oddsportal.com{match_url}"
                    break
                link_parent = link_parent.parent
            odds_valid = [o for o in odds_texts if ODDS_RE.match(o)]
            entry = {
                "home": home,
                "away": away,
                "odds": odds_valid,
                "market_type": "h2h",
                "source_url": url,
                "raw": f"{home} - {away}",
            }
            if match_url:
                entry["match_url"] = match_url
            structured = _build_odds_structured(odds_valid, two_way)
            if structured:
                entry["odds_structured"] = structured
            results.append(entry)

    # --- Strategy 2: Traditional table rows (pre-SPA pages) ---
    if not results:
        for tr in soup.find_all("tr"):
            text = tr.get_text(" ", strip=True)
            if not text:
                continue
            odds = ODDS_RE.findall(text)
            if odds:
                parts = re.split(r"\s+vs\.?\s+|\s+-\s+|\s+–\s+|\s+—\s+", text, flags=re.I)
                if len(parts) >= 2:
                    home = parts[0].strip()
                    away = parts[1].strip()
                    if len(home) >= 2 and len(away) >= 2:
                        full_text = f"{home} - {away}"
                        if _LEAGUE_NAV_RE.search(full_text):
                            continue
                        entry = {
                            "home": home,
                            "away": away,
                            "odds": odds,
                            "market_type": "h2h",
                            "source_url": url,
                            "raw": text,
                        }
                        structured = _build_odds_structured(odds, two_way)
                        if structured:
                            entry["odds_structured"] = structured
                        results.append(entry)

    # --- Strategy 3: Link-based extraction ---
    if not results:
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if not text or len(text) > 120 or len(text) < 8:
                continue
            parts = re.split(r"\s+-\s+", text)
            if len(parts) == 2:
                home = parts[0].strip()
                away = parts[1].strip()
                if (len(home) >= 2 and len(away) >= 2
                        and not _LEAGUE_NAV_RE.search(text)
                        and not home[0].isdigit()):
                    parent = link.parent
                    odds = []
                    if parent:
                        parent_text = parent.get_text(" ", strip=True)
                        odds = ODDS_RE.findall(parent_text)
                    entry = {
                        "home": home,
                        "away": away,
                        "odds": odds,
                        "market_type": "h2h",
                        "source_url": url,
                        "raw": text,
                    }
                    if odds:
                        structured = _build_odds_structured(odds, two_way)
                        if structured:
                            entry["odds_structured"] = structured
                    results.append(entry)

    if results:
        from adapters import dedup_results
        return dedup_results(
            results,
            key_fn=lambda r: (r.get("home"), r.get("away"), tuple(r.get("odds", []))),
        )

    return []
