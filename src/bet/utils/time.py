"""Time utilities for betting-day calculations."""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Tuple, Union


def betting_day_range(date_or_dt: Union[date, datetime], tz: str = "Europe/Warsaw") -> Tuple[datetime, datetime]:
    """Return (start_utc, end_utc) for the betting day."""
    if isinstance(date_or_dt, datetime):
        local_date = date_or_dt.date()
    else:
        local_date = date_or_dt
    local_tz = ZoneInfo(tz)
    start_local = datetime.combine(local_date, time(6, 0, 0)).replace(tzinfo=local_tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc
