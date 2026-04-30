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
    "/tennis/", "/basketball/", "/volleyball/", "/handball/",
    "/baseball/", "/table-tennis/", "/esports/", "/mma/",
    "/snooker/", "/darts/", "/padel/", "/speedway/",
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

    # Try to find rows with odds
    for tr in soup.find_all("tr"):
        text = tr.get_text(" ", strip=True)
        if not text:
            continue
        # match patterns like "Team A - Team B" inside the row (require spaces)
        odds = ODDS_RE.findall(text)
        if odds:
            # Split on " - " or " vs " with spaces required
            parts = re.split(r"\s+vs\.?\s+|\s+-\s+|\s+–\s+|\s+—\s+", text, flags=re.I)
            if len(parts) >= 2:
                home = parts[0].strip()
                away = parts[1].strip()
                if len(home) >= 2 and len(away) >= 2:
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

    if results:
        from adapters import dedup_results
        return dedup_results(
            results,
            key_fn=lambda r: (r.get("home"), r.get("away"), tuple(r.get("odds", []))),
        )

    return raw_parse(html, url)
