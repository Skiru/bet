# ruff: noqa: E501
import datetime
from datetime import datetime as dt_class


def require_aware_datetime(dt: dt_class) -> None:
    if not isinstance(dt, dt_class):
        raise TypeError("Expected datetime object")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("Naive datetime is not allowed. Timezone awareness is required.")

def to_utc(dt: dt_class) -> dt_class:
    require_aware_datetime(dt)
    return dt.astimezone(datetime.UTC)

def format_utc(dt: dt_class) -> str:
    dt_utc = to_utc(dt)
    # Serialize exactly YYYY-MM-DDTHH:MM:SS.ffffffZ
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

def parse_canonical_or_offset_datetime(s: str | dt_class) -> dt_class:
    if s is None:
        raise ValueError("Datetime value is None")
    if isinstance(s, dt_class):
        require_aware_datetime(s)
        return to_utc(s)
    if not isinstance(s, str):
        raise TypeError("Expected string or datetime object")
    s_clean = s.strip()
    if not s_clean:
        raise ValueError("Empty datetime string")
    if len(s_clean) == 10 and s_clean[4] == "-" and s_clean[7] == "-":
        s_clean += "T00:00:00Z"
    if s_clean.endswith("Z"):
        s_clean = s_clean[:-1] + "+00:00"
    try:
        parsed = dt_class.fromisoformat(s_clean)
    except Exception as e:
        raise ValueError(f"Invalid datetime format: {s}") from e
    require_aware_datetime(parsed)
    return to_utc(parsed)
