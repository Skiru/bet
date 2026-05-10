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

    # Try to find rows with odds in actual table elements
    for tr in soup.find_all("tr"):
        text = tr.get_text(" ", strip=True)
        if not text:
            continue
        odds = ODDS_RE.findall(text)
        if odds:
            # Split on " - " or " vs " with spaces required
            parts = re.split(r"\s+vs\.?\s+|\s+-\s+|\s+–\s+|\s+—\s+", text, flags=re.I)
            if len(parts) >= 2:
                home = parts[0].strip()
                away = parts[1].strip()
                if len(home) >= 2 and len(away) >= 2:
                    # Skip league navigation entries
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

    # Also try div-based extraction for React-rendered content
    if not results:
        # Look for links that contain "Team - Team" patterns (not league navs)
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if not text or len(text) > 120 or len(text) < 8:
                continue
            # Match "Home - Away" but NOT league navigation
            parts = re.split(r"\s+-\s+", text)
            if len(parts) == 2:
                home = parts[0].strip()
                away = parts[1].strip()
                if (len(home) >= 2 and len(away) >= 2
                        and not _LEAGUE_NAV_RE.search(text)
                        and not home[0].isdigit()):
                    # Try to find odds near this element
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

    # OddsPortal is a React SPA — match data loads via JS after page render.
    # Don't fall back to raw_parse as it captures league navigation links as
    # fake matches (e.g., "3. CFL - Group A"). Return empty instead.
    return []
