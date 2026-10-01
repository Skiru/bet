"""A fresh opponent must not hide a stale side (2026-10-01, Bublik - Mensik).

Bublik's scoped hard-court side: ten matches 2025-10-03..2026-03-20, the
newest 194 days before the fixture. Mensik's: this week's. The pooled newest
read "1 day" on every total, so the 60-day STALE_SAMPLE gate never fired.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bet.sofa.coupon import MAX_SAMPLE_AGE_DAYS
from bet.sofa.sample_age import stalest_side_newest_days

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@dataclass
class Obs:
    match_date_utc: datetime | None


def side(*days_ago: int) -> list[Obs]:
    return [Obs(NOW - timedelta(days=d)) for d in days_ago]


def test_the_staler_side_sets_the_age_of_a_total() -> None:
    bublik = side(194, 200, 230, 300, 363)
    mensik = side(1, 3, 9, 20, 41)
    assert stalest_side_newest_days([bublik, mensik], NOW) == 194
    assert stalest_side_newest_days([bublik, mensik], NOW) > MAX_SAMPLE_AGE_DAYS


def test_a_one_side_row_reads_its_own_side() -> None:
    assert stalest_side_newest_days([side(5, 40)], NOW) == 5


def test_a_side_without_dates_is_ignored_and_none_means_unknown() -> None:
    assert stalest_side_newest_days([[Obs(None)], side(12)], NOW) == 12
    assert stalest_side_newest_days([[Obs(None)]], NOW) is None
    assert stalest_side_newest_days([], NOW) is None


def test_a_player_row_falls_back_to_its_appearances() -> None:
    assert stalest_side_newest_days([], NOW, side(7, 30)) == 7
