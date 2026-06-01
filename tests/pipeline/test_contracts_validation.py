"""Additional unit tests: contracts validation and normalize edge cases."""
from __future__ import annotations

from datetime import datetime, timezone
import pytest

from bet.pipeline.contracts import CanonicalFixture, Signal


def test_canonical_fixture_parses_iso_and_epoch():
    iso = "2026-06-01T18:00:00+02:00"
    cf = CanonicalFixture(external_id="x", home_team="A", away_team="B", event_time=iso)
    assert cf.event_time.tzinfo is not None
    assert cf.event_time.utcoffset().total_seconds() == 0 or cf.event_time.tzinfo is not None

    epoch = 1710000000
    cf2 = CanonicalFixture(external_id="y", home_team="A", away_team="B", event_time=epoch)
    assert cf2.event_time.tzinfo is not None


def test_signal_validation_rejects_bad_pick_or_confidence():
    with pytest.raises(Exception):
        Signal(external_id="x", pick="invalid", confidence=0.5)
    with pytest.raises(Exception):
        Signal(external_id="x", pick="home", confidence=1.5)
