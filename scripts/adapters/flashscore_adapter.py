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


def _detect_sport_from_url(url: str) -> str | None:
    m = re.search(r'flashscore\.com/(\w+)/', url)
    if m:
        sport_map = {"football": "football", "tennis": "tennis", "basketball": "basketball", 
                     "hockey": "hockey", "volleyball": "volleyball", "handball": "handball",
                     "baseball": "baseball", "rugby": "rugby"}
        return sport_map.get(m.group(1).lower())
    return None

def _competition_from_url(url: str) -> str:
    """Extract competition name from a Flashscore league-specific URL path.

    Examples:
        /football/brazil/serie-a/       → "Brazil - Serie A"
        /football/usa/mls/              → "Usa - Mls"
        /football/england/premier-league/ → "England - Premier League"
        /football/brazil/                → "Brazil"
        /football/                       → ""
    """
    m = re.search(r'flashscore\.com/[^/]+/([^/]+)/([^/]+)', url)
    if m:
        country = m.group(1).replace('-', ' ').title()
        league = m.group(2).replace('-', ' ').title()
        return f"{country} - {league}"
    m = re.search(r'flashscore\.com/[^/]+/([^/]+)/?$', url)
    if m:
        country = m.group(1).replace('-', ' ').title()
        return country
    return ""
# Patterns for identifying match row elements
_MATCH_CLASS_RE = re.compile(r"event__match|event__participant", re.I)
# Patterns for time elements
_TIME_CLASS_RE = re.compile(r"event__time|event__stage|event__startTime", re.I)


def _text_short(t: str) -> bool:
    return 3 < len(t) < 120


# Patterns indicating a parsed "team name" is actually page chrome / garbage
_GARBAGE_RE = re.compile(
    r"today's matches|pinned leagues|my teams|add the team|advertisement|"
    r"advancing to next round|winner:|latest scores|previous match day|"
    r"there are no .* matches|sets legs points|"
    r"overview|preview|head-to-head|line-ups|"
    r"atp\b.*\bsingles|wta\b.*\bsingles|atp\b.*\bdoubles|wta\b.*\bdoubles|"
    r"quali\w*\s*-\s*singles|quali\w*\s*-\s*doubles|"
    r"\bdraw\s+\d{1,2}:\d{2}\b|"
    r"completed|match stats|\bcourt\b.*\bcompleted\b|\bpuchar\b|\bpremiership league\b|"
    r"pregame report|postgame",
    re.I,
)


def _is_garbage_entry(home: str, away: str) -> bool:
    """Return True if the parsed home/away looks like page chrome, not a real match."""
    if not home or not away:
        return True
    # Too long — real team/player names are short
    if len(home) > 60 or len(away) > 60:
        return True
    # Home == Away
    if home.strip().lower() == away.strip().lower():
        return True
    # Contains known garbage patterns
    if _GARBAGE_RE.search(home) or _GARBAGE_RE.search(away):
        return True
    # Home/away starts with a date pattern (e.g., "CZW 30.04.2026 20:30 Northampton")
    if re.match(r"^[A-Z]{2,4}\s+\d{2}\.\d{2}\.\d{4}", home) or re.match(r"^[A-Z]{2,4}\s+\d{2}\.\d{2}\.\d{4}", away):
        return True
    # Contains path separators (league navigation like "Football / Europe / ...")
    if " / " in home or " / " in away:
        return True
    # Contains " : " followed by time — section header blob
    if re.search(r" : .+\d{1,2}:\d{2}", home) or re.search(r" : .+\d{1,2}:\d{2}", away):
        return True
    return False


def _has_class_match(el, pattern: re.Pattern) -> bool:
    """Check if any class on the element matches the given pattern."""
    classes = el.get("class")
    if not classes:
        return False
    joined = " ".join(classes) if isinstance(classes, (list, tuple)) else classes
    return bool(pattern.search(joined))


def _heuristic0_event_classes(soup: BeautifulSoup, url: str) -> List[Dict]:
    """Heuristic 0: Flashscore event__ class structure.

    Targets Flashscore's actual DOM:
      div.event__match (container per match)
        div.event__time "21:00"
        div.event__homeParticipant  (home team name)
        div.event__awayParticipant  (away team name)

    League headers use event__header / event__title and are tracked for context.
    """
    results = []
    current_league = ""
    url_league = _competition_from_url(url)

    # Regex for home/away participant elements — handles two known class patterns:
    # Real Flashscore (2026): "event__homeParticipant", "event__awayParticipant"
    # Older/test format: "event__participant--home", "event__participant--away"
    _HOME_RE = re.compile(r"homeParticipant|participant--home", re.I)
    _AWAY_RE = re.compile(r"awayParticipant|participant--away", re.I)

    # Build ordered list of headers and match containers
    all_elements = soup.find_all(
        True,
        class_=lambda c: c and re.search(
            r"event__header|event__title|event__match|league-header|tournament-header",
            " ".join(c) if isinstance(c, (list, tuple)) else c,
            re.I,
        ),
    )

    if not all_elements:
        return []

    for el in all_elements:
        classes_str = " ".join(el.get("class", []))

        # Detect header — update league context
        if _HEADER_CLASS_RE.search(classes_str) and "event__match" not in classes_str:
            current_league = (el.get_text(separator=" ") or "").strip()
            continue

        # Match container
        if "event__match" not in classes_str:
            continue

        # Extract home team
        home_el = el.find(True, class_=lambda c: c and _HOME_RE.search(
            " ".join(c) if isinstance(c, (list, tuple)) else c))
        away_el = el.find(True, class_=lambda c: c and _AWAY_RE.search(
            " ".join(c) if isinstance(c, (list, tuple)) else c))

        if not home_el or not away_el:
            continue

        home = (home_el.get_text(strip=True) or "").strip()
        away = (away_el.get_text(strip=True) or "").strip()

        if not home or not away or len(home) < 2 or len(away) < 2:
            continue

        pos_match_home = re.search(r"\[(\d+)\]", home)
        pos_match_away = re.search(r"\[(\d+)\]", away)
        standings = {
            "home_pos": int(pos_match_home.group(1)) if pos_match_home else None, 
            "away_pos": int(pos_match_away.group(1)) if pos_match_away else None
        }

        # Clean suffixes and prefixes
        home = re.sub(r"\[\d+\]", "", home).strip()
        away = re.sub(r"\[\d+\]", "", away).strip()
        home = re.sub(r"Advancing to next round:?\s*.*", "", home, flags=re.I).strip()
        away = re.sub(r"Advancing to next round:?\s*.*", "", away, flags=re.I).strip()
        home = re.sub(r"Winner:?\s*.*", "", home, flags=re.I).strip()
        away = re.sub(r"Winner:?\s*.*", "", away, flags=re.I).strip()

        if _is_garbage_entry(home, away):
            continue

        # Extract time
        row_time = None
        time_el = el.find(True, class_=lambda c: c and _TIME_CLASS_RE.search(
            " ".join(c) if isinstance(c, (list, tuple)) else c))
        if time_el:
            tm = re.search(r"\b(\d{1,2}:\d{2})\b", time_el.get_text(strip=True))
            if tm:
                row_time = tm.group(1)

        league_val = current_league or url_league
        
        match_id = el.get("id")
        if match_id and match_id.startswith("g_1_"):
            match_id = match_id[4:]

        entry = {
            "home": home,
            "away": away,
            "time": row_time,
            "source_url": url,
            "raw": f"{home} - {away}",
            "standings": standings,
            "source_type": "flashscore",
            "sport": _detect_sport_from_url(url),
        }
        if match_id:
            entry["match_id"] = match_id
        if league_val:
            entry["league"] = league_val
        results.append(entry)

    return results


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    url_league = _competition_from_url(url)

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
            if _is_garbage_entry(home, away):
                continue
            # try find time in the row
            time_m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
            time = time_m.group(1) if time_m else None
            entry = {
                "home": home, 
                "away": away, 
                "time": time, 
                "source_url": url, 
                "raw": text,
                "source_type": "flashscore",
                "sport": _detect_sport_from_url(url),
            }
            if url_league:
                entry["league"] = url_league
            results.append(entry)

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
            if _is_garbage_entry(home, away):
                continue
            away = participants[i + 1][1]
            if home and away and home != away:
                entry = {
                    "home": home, 
                    "away": away, 
                    "time": None, 
                    "source_url": url, 
                    "raw": f"{home} - {away}",
                    "source_type": "flashscore",
                    "sport": _detect_sport_from_url(url),
                }
                if url_league:
                    entry["league"] = url_league
                results.append(entry)

    if results:
        from adapters import dedup_results
        return dedup_results(results)

    # final fallback
    return raw_parse(html, url)
