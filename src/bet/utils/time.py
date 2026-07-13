"""Time utilities for betting-day calculations."""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Tuple, Union


WARSAW = ZoneInfo("Europe/Warsaw")


def betting_day_for(moment: datetime, tz: str = "Europe/Warsaw") -> date:
    """Return the local betting day for an aware instant using the 06:00 cutover."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("naive datetime is not allowed")
    local = moment.astimezone(ZoneInfo(tz))
    return local.date() if local.time() >= time(6, 0) else local.date() - timedelta(days=1)


def betting_day_range(date_or_dt: Union[date, datetime], tz: str = "Europe/Warsaw") -> Tuple[datetime, datetime]:
    """Return (start_utc, end_utc) for the betting day."""
    if isinstance(date_or_dt, datetime):
        local_date = betting_day_for(date_or_dt, tz)
    else:
        local_date = date_or_dt
    local_tz = ZoneInfo(tz)
    start_local = datetime.combine(local_date, time(6, 0, 0)).replace(tzinfo=local_tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc


def in_betting_day(moment: datetime, betting_day: date, tz: str = "Europe/Warsaw") -> bool:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("naive datetime is not allowed")
    start, end = betting_day_range(betting_day, tz)
    utc_moment = moment.astimezone(timezone.utc)
    return start <= utc_moment < end
