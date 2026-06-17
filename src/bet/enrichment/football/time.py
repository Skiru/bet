# ruff: noqa: E501
import datetime
from datetime import datetime as dt_class, timezone

def require_aware_datetime(dt: dt_class) -> None:
    if not isinstance(dt, dt_class):
        raise TypeError("Expected datetime object")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("Naive datetime is not allowed. Timezone awareness is required.")

def to_utc(dt: dt_class) -> dt_class:
    require_aware_datetime(dt)
    return dt.astimezone(timezone.utc)

def format_utc(dt: dt_class) -> str:
    dt_utc = to_utc(dt)
    return dt_utc.strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'

def parse_canonical_or_offset_datetime(s: str) -> dt_class:
    if not s:
        raise ValueError("Empty datetime string")
    # Clean string
    s_clean = s.strip()
    # Handle Zulu suffix manually or let fromisoformat do it if Python 3.11+
    if s_clean.endswith('Z'):
        s_clean = s_clean[:-1] + '+00:00'
    try:
        parsed = dt_class.fromisoformat(s_clean)
    except Exception as e:
        raise ValueError(f"Invalid datetime format: {s}") from e
    require_aware_datetime(parsed)
    return to_utc(parsed)
