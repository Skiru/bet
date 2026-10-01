"""How current a sample is, side by side.

A row's freshness used to be the newest match in its pool. A match total pools
both histories, so a side that stopped playing months ago hid behind its
opponent's last match (2026-10-01: Bublik's scoped hard-court side was 194
days old, Mensik's a day, and every total of the match read "1 day"). The
freshness that matters is the staler side's.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol


class Dated(Protocol):
    @property
    def match_date_utc(self) -> datetime | None: ...


def stalest_side_newest_days(
    sides: Sequence[Sequence[Dated]],
    now: datetime,
    fallback: Sequence[Dated] = (),
) -> int | None:
    """Days since the newest match of the stalest side that has any date.

    `fallback` is read when no side is given (a player row's appearances).
    None when nothing carries a date.
    """
    groups = [side for side in sides if side] or ([fallback] if fallback else [])
    ages = []
    for side in groups:
        dates = [o.match_date_utc for o in side if o.match_date_utc is not None]
        if dates:
            ages.append((now - max(dates)).days)
    return max(ages) if ages else None
