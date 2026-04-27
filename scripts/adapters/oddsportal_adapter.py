"""Site adapter for OddsPortal (heuristic odds extraction).

This adapter looks for table rows that often contain odds in OddsPortal pages.
It extracts simple markets when possible and otherwise falls back to `raw_adapter`.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse

ODDS_RE = re.compile(r"\b\d+\.\d{2}\b")


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

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
                    results.append({
                        "home": home,
                        "away": away,
                        "odds": odds,
                        "source_url": url,
                        "raw": text,
                    })

    if results:
        from adapters import dedup_results
        return dedup_results(
            results,
            key_fn=lambda r: (r.get("home"), r.get("away"), tuple(r.get("odds", []))),
        )

    return raw_parse(html, url)
