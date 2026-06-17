# ruff: noqa: E501
import pytest
from datetime import datetime, timezone, timedelta
from bet.enrichment.football.time import (
    require_aware_datetime,
    to_utc,
    format_utc,
    parse_canonical_or_offset_datetime,
)

def test_require_aware_datetime():
    with pytest.raises(ValueError):
        require_aware_datetime(datetime(2023, 1, 1))
    
    # Aware datetime should not raise
    require_aware_datetime(datetime(2023, 1, 1, tzinfo=timezone.utc))

def test_to_utc():
    # Offset +02:00 should be converted to UTC
    tz = timezone(timedelta(hours=2))
    dt = datetime(2023, 1, 1, 12, tzinfo=tz)
    dt_utc = to_utc(dt)
    assert dt_utc.tzinfo == timezone.utc
    assert dt_utc.hour == 10

def test_format_utc():
    tz = timezone(timedelta(hours=2))
    dt = datetime(2023, 1, 1, 12, 30, 45, 123456, tzinfo=tz)
    fmt = format_utc(dt)
    assert fmt == "2023-01-01T10:30:45.123456Z"

def test_parse_canonical_or_offset_datetime():
    # String with offset
    dt = parse_canonical_or_offset_datetime("2023-01-01T12:00:00+02:00")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 10
    
    # String with Zulu suffix
    dt_z = parse_canonical_or_offset_datetime("2023-01-01T12:00:00Z")
    assert dt_z.tzinfo == timezone.utc
    assert dt_z.hour == 12

    # Datetime object input
    dt_obj = datetime(2023, 1, 1, 12, tzinfo=timezone.utc)
    assert parse_canonical_or_offset_datetime(dt_obj) == dt_obj
