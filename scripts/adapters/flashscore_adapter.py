"""Site adapter for Flashscore (best-effort).

This adapter attempts to find match lines and odds inside HTML produced by
Flashscore. Flashscore heavily relies on JS; this adapter falls back to the
generic raw adapter when it cannot find structured data.
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse

# Patterns for identifying Flashscore section/league headers
_HEADER_CLASS_RE = re.compile(
    r"event__header|event__title|league-header|tournament-header|"
    r"event__round|event__series",
    re.I,
)
# Patterns for identifying match row elements
_MATCH_CLASS_RE = re.compile(r"event__match|event__participant", re.I)
# Patterns for time elements
_TIME_CLASS_RE = re.compile(r"event__time|event__stage|event__startTime", re.I)


def _text_short(t: str) -> bool:
    return 3 < len(t) < 120


def _has_class_match(el, pattern: re.Pattern) -> bool:
    """Check if any class on the element matches the given pattern."""
    classes = el.get("class")
    if not classes:
        return False
    joined = " ".join(classes) if isinstance(classes, (list, tuple)) else classes
    return bool(pattern.search(joined))


def _heuristic0_event_classes(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Heuristic 0: Flashscore event__ class structure.

    Targets Flashscore's actual DOM pattern where match rows use ``event__match``
    classes and participants use ``event__participant``. League/section headers
    use ``event__header`` or ``event__title`` and are tracked separately so
    their text does not leak into team names.

    Works for volleyball and improves all other sports too.
    """
    results = []
    current_league = ""

    # Collect header elements to know which text to skip
    header_texts = set()
    for el in soup.find_all(True, class_=lambda c: c and _HEADER_CLASS_RE.search(
            " ".join(c) if isinstance(c, (list, tuple)) else c)):
        t = (el.get_text(separator=" ") or "").strip()
        if t:
            header_texts.add(t)

    # Walk all elements with event__match or event__participant classes
    match_rows = soup.find_all(
        True,
        class_=lambda c: c and _MATCH_CLASS_RE.search(
            " ".join(c) if isinstance(c, (list, tuple)) else c,
        ),
    )

    if not match_rows:
        return []

    # Also find all header elements in document order so we can track
    # the current league context.
    all_elements = soup.find_all(
        True,
        class_=lambda c: c and re.search(
            r"event__header|event__title|event__match|event__participant|"
            r"league-header|tournament-header",
            " ".join(c) if isinstance(c, (list, tuple)) else c,
            re.I,
        ),
    )

    participants_buf: List[str] = []
    row_time = None
    row_league = current_league

    for el in all_elements:
        # Detect header — update league context and skip
        if _has_class_match(el, _HEADER_CLASS_RE):
            current_league = (el.get_text(separator=" ") or "").strip()
            # flush any incomplete participant buffer
            participants_buf = []
            row_time = None
            row_league = current_league
            continue

        # Participant element
        if _has_class_match(el, _MATCH_CLASS_RE):
            # Try to extract time from siblings/children with time class
            time_el = el.find(True, class_=lambda c: c and _TIME_CLASS_RE.search(
                " ".join(c) if isinstance(c, (list, tuple)) else c))
            if time_el:
                tm = re.search(r"\b(\d{1,2}:\d{2})\b", time_el.get_text(strip=True))
                if tm:
                    row_time = tm.group(1)

            # Collect participant names from child participant elements
            child_parts = el.find_all(
                True,
                class_=lambda c: c and re.search(
                    r"participant|team|name",
                    " ".join(c) if isinstance(c, (list, tuple)) else c,
                    re.I,
                ),
            )
            if child_parts:
                for cp in child_parts:
                    t = (cp.get_text(strip=True) or "").strip()
                    if t and _text_short(t) and t not in header_texts:
                        participants_buf.append(t)
            else:
                # The element itself contains the text
                t = (el.get_text(separator=" ") or "").strip()
                # Strip any leading header text that may have been merged
                for ht in header_texts:
                    if t.startswith(ht):
                        t = t[len(ht):].strip(" -–—:")
                if t and _text_short(t):
                    participants_buf.append(t)

            # Also check for time in the broader row context
            if row_time is None:
                row_text = (el.get_text(separator=" ") or "")
                tm = re.search(r"\b(\d{1,2}:\d{2})\b", row_text)
                if tm:
                    row_time = tm.group(1)

            # When we have a pair, emit a result
            if len(participants_buf) >= 2:
                home = participants_buf[0]
                away = participants_buf[1]
                if home and away and home != away and len(home) >= 2 and len(away) >= 2:
                    entry = {
                        "home": home,
                        "away": away,
                        "time": row_time,
                        "source_url": url,
                        "raw": f"{home} - {away}",
                    }
                    if row_league:
                        entry["league"] = row_league
                    results.append(entry)
                participants_buf = []
                row_time = None
                row_league = current_league

    return results


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Heuristic 0: Flashscore event__ class structure (works best for
    # volleyball and improves other sports too).
    results = _heuristic0_event_classes(soup, url)
    if results:
        from adapters import dedup_results
        return dedup_results(results)

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
        from adapters import dedup_results
        return dedup_results(results)

    # final fallback
    return raw_parse(html, url)
