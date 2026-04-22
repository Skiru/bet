"""Site adapter for Flashscore (best-effort).

This adapter attempts to find match lines and odds inside HTML produced by
Flashscore. Flashscore heavily relies on JS; this adapter falls back to the
generic raw adapter when it cannot find structured data.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse


def _text_short(t: str) -> bool:
    return 3 < len(t) < 120


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Require spaces around separators to avoid splitting on "v" in team names
    vs_re = re.compile(r"(.+?)\s+(?:vs\.?|v\.)\s+(.+)", re.I)
    dash_re = re.compile(r"(.{3,}?)\s+[-–—]\s+(.{3,})")

    # Heuristic 1: find elements that look like match rows (classes containing
    # 'event', 'match', 'fixture', 'row') and extract short text with vs/dash
    for div in soup.find_all(True, class_=lambda c: c and re.search(r"event|match|fixture|row", " ".join(c) if isinstance(c, (list, tuple)) else c, re.I)):
        text = (div.get_text(separator=" ") or "").strip()
        if not text or len(text) > 300:
            continue
        m = vs_re.search(text) or dash_re.search(text)
        if m and _text_short(m.group(1)) and _text_short(m.group(2)):
            home = m.group(1).strip()
            away = m.group(2).strip()
            if len(home) < 2 or len(away) < 2:
                continue
            # try find time in the row
            time_m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
            time = time_m.group(1) if time_m else None
            results.append({"home": home, "away": away, "time": time, "source_url": url, "raw": text})

    # Heuristic 2: look for participant spans (common in Flashscore markup)
    if not results:
        participants = []
        for span in soup.find_all(True, class_=lambda c: c and re.search(r"participant|team|name", " ".join(c) if isinstance(c, (list, tuple)) else c, re.I)):
            t = (span.get_text() or "").strip()
            if _text_short(t):
                participants.append((span, t))
        # pair adjacent participants
        for i in range(0, len(participants) - 1, 2):
            home = participants[i][1]
            away = participants[i + 1][1]
            if home and away and home != away:
                results.append({"home": home, "away": away, "time": None, "source_url": url, "raw": f"{home} - {away}"})

    if results:
        # dedupe
        seen = set()
        dedup = []
        for r in results:
            key = (r.get("home"), r.get("away"), r.get("time"))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(r)
        return dedup

    # final fallback
    return raw_parse(html, url)
