"""Shared utilities for betting pipeline scripts."""

import re
import unicodedata
from datetime import date as _date_cls, timedelta


def normalize_team_name(name: str) -> str:
    """Normalize team/player name for fuzzy matching across sources.

    Strips diacritics, removes common club suffixes (FC, SC, United, etc.),
    parenthetical qualifiers, and extra whitespace. Returns lowercase.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    s = re.sub(
        r"\b(FC|SC|CF|CD|SK|FK|AS|AC|US|SS|SV|TSV|VfB|VfL|BSC|"
        r"IF|BK|IFK|AIK|FF|GIF|AFC|RFC|SFC|CFC|United|Utd|City|"
        r"Town|Rovers|Wanderers|Athletic|Athletico|Sporting)\b",
        "",
        s,
        flags=re.IGNORECASE,
    )
    # Normalize hyphens/dashes to spaces (e.g. "Saint-Germain" → "Saint Germain")
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


# Pre-compiled pattern: bare time like "19:00", "01:30", "23:05"
_BARE_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def normalize_kickoff(raw: str, betting_date: str) -> str:
    """Normalize a kickoff value to full ISO 8601 datetime string.

    Handles three input forms:
    1. Already ISO (contains 'T') — returned as-is.
    2. Date-only like '2026-05-08' — appended with T00:00:00+02:00.
    3. Bare time like '19:00' — combined with *betting_date* and assumed
       CEST (UTC+2).  Times 00:00–05:59 are treated as next calendar day
       (betting-day convention: 06:00 today → 05:59 tomorrow).

    All bare times are assumed CEST because Playwright scrapes European sites
    that display local (CEST) times for the user.
    """
    if not raw:
        return ""
    raw = raw.strip()

    # Already full ISO
    if "T" in raw:
        return raw

    # Date-only (e.g. "2026-05-08")
    if len(raw) == 10 and raw.count("-") == 2:
        return f"{raw}T00:00:00+02:00"

    # Bare time (e.g. "19:00", "01:30")
    m = _BARE_TIME_RE.match(raw)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        # Betting-day convention: times 00:00-05:59 belong to next calendar day
        if hour < 6:
            parts = betting_date.split("-")
            d = _date_cls(int(parts[0]), int(parts[1]), int(parts[2]))
            d += timedelta(days=1)
            use_date = d.isoformat()
        else:
            use_date = betting_date
        return f"{use_date}T{hour:02d}:{minute:02d}:00+02:00"

    return raw
