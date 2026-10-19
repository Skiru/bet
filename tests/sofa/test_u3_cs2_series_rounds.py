"""U3 reads a snapshot line with the switches SPORT_CONFIDENCE used. Without
CS2's `series_rounds` a printed series team_rounds leg (map 0, priced from
2026-10-15) was 'not in the snapshot' (2026-10-19, Iberian Soul -
HyperSpirit team_rounds 12.5 OVER @1.28, the line on file at that price)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from scripts.sofa.audit_variants import snapshot_family


def line(family: str, map_nr: int = 0) -> SimpleNamespace:
    return SimpleNamespace(family=family, map_nr=map_nr, market_id=None)


def test_series_team_rounds_reads_as_printed_after_the_switch() -> None:
    at = datetime(2026, 10, 19, 6, 55, tzinfo=UTC)
    assert snapshot_family("cs2", line("team_rounds"), "2026-10-19", at,
                           True) == "team_rounds"


def test_series_team_rounds_not_read_before_the_switch() -> None:
    at = datetime(2026, 10, 14, 6, 55, tzinfo=UTC)
    assert snapshot_family("cs2", line("team_rounds"), "2026-10-14", at,
                           True) is None
