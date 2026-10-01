"""A match listed twice on Superbet, once at a 00:00:00Z placeholder, keeps
the real time - review 2026-10-01: three ITF matches lost 168 priced rungs
to the earlier-clock gate."""

from __future__ import annotations

from datetime import UTC, datetime

from scripts.sofa.run_resolve import merged_superbet_kickoff

MIDNIGHT = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
REAL = datetime(2026, 10, 1, 11, 8, tzinfo=UTC)
OTHER = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def test_a_placeholder_gives_way_to_a_real_time() -> None:
    assert merged_superbet_kickoff(MIDNIGHT, REAL) == REAL


def test_a_real_time_is_kept() -> None:
    assert merged_superbet_kickoff(REAL, MIDNIGHT) == REAL
    assert merged_superbet_kickoff(REAL, OTHER) == REAL


def test_a_lone_midnight_is_a_real_kickoff() -> None:
    assert merged_superbet_kickoff(MIDNIGHT, MIDNIGHT) == MIDNIGHT
    assert merged_superbet_kickoff(None, MIDNIGHT) == MIDNIGHT
    assert merged_superbet_kickoff(MIDNIGHT, None) == MIDNIGHT
