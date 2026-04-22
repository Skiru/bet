"""Adapter for Betclic (minimal extractor).

Betclic's front page and event pages often include team names and decimal odds
within elements that include numeric patterns. This adapter tries to find short
team pairs and nearby decimal odds (patterns like 1.23).
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse

ODDS_RE = re.compile(r"\b\d+\.\d{2}\b")


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Look for clickable event blocks
    for el in soup.find_all(["a", "div", "section"], class_=lambda c: c and re.search(r"event|match|market|coupon|fixture|odds", " ".join(c) if isinstance(c, (list, tuple)) else c, re.I)):
        text = (el.get_text(" ") or "").strip()
        if not text or len(text) > 500:
            continue
        m = re.search(r"(.+?)\s*(?:vs|v|–|-|—|:)\s*(.+)", text, re.I)
        if m:
            home = m.group(1).strip()
            away = m.group(2).strip()
            odds = ODDS_RE.findall(text)
            results.append({"home": home, "away": away, "odds": odds, "source_url": url, "raw": text})

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
