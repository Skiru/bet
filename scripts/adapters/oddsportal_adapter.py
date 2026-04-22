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
        # match patterns like "Team A - Team B" inside the row
        if "-" in text or "vs" in text.lower():
            odds = ODDS_RE.findall(text)
            if odds:
                # very small normalization: split on -/vs to get teams
                parts = re.split(r"\s+vs\s+|\s+-\s+|\s+–\s+", text, flags=re.I)
                if len(parts) >= 2:
                    home = parts[0].strip()
                    away = parts[1].strip()
                    results.append({
                        "home": home,
                        "away": away,
                        "odds": odds,
                        "source_url": url,
                        "raw": text,
                    })

    if results:
        # dedupe
        seen = set()
        dedup = []
        for r in results:
            key = (r.get("home"), r.get("away"), tuple(r.get("odds", [])))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(r)
        return dedup

    return raw_parse(html, url)
