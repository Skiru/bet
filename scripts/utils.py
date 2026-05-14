"""Shared utilities for betting pipeline scripts."""

import re
from datetime import date as _date_cls, timedelta

# Single source of truth — see src/bet/utils.py
from bet.utils import normalize_team_name  # noqa: F401


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
