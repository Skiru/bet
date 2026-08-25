"""Betting-day attribution: which picks belong to the day being run.

Every one of these sources publishes several days on one page, and each states
its dates in its own timezone. Getting this wrong is not a cosmetic problem: a
consensus number built partly from yesterday is not a consensus number, and it
fails silently, looking exactly like a correct one.
"""
from __future__ import annotations

from bet.tipsters.contracts import TipsterPick
from bet.tipsters.live import DATE_TOLERANCE_DAYS, filter_picks_for_date


def _pick(match_date: str | None = "2026-08-25", *, settled: bool = False) -> TipsterPick:
    return TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="A vs B",
        home_team="A",
        away_team="B",
        market="Poniżej 10,5 rzutów rożnych",
        market_family="corners",
        direction="UNDER",
        match_date=match_date,
        is_settled=settled,
    )


def test_the_requested_day_is_kept_and_counted_as_exact():
    kept, counts = filter_picks_for_date([_pick("2026-08-25")], "2026-08-25", drop_undated=False)
    assert len(kept) == 1
    assert counts["exact_day"] == 1
    assert counts["adjacent_day_kept"] == 0


def test_an_adjacent_day_is_kept_but_counted_separately():
    """ZawodTyper publishes in Europe/Warsaw and the betting day is UTC, so a
    00:30 local kickoff is 22:30 UTC the day before. Measured on the live
    2026-08-25 payload: 6 of 74 picks sat in that window. Exact equality both
    kept picks from the wrong day and dropped picks from the right one."""
    picks = [_pick("2026-08-24"), _pick("2026-08-26")]
    kept, counts = filter_picks_for_date(picks, "2026-08-25", drop_undated=False)
    assert len(kept) == 2
    assert counts["adjacent_day_kept"] == 2
    assert counts["exact_day"] == 0
    assert counts["wrong_date"] == 0


def test_beyond_the_tolerance_is_dropped():
    far = _pick("2026-08-20")
    kept, counts = filter_picks_for_date([far], "2026-08-25", drop_undated=False)
    assert kept == []
    assert counts["wrong_date"] == 1


def test_the_tolerance_is_exactly_one_day():
    """Pinned so widening it later is a deliberate act, not a drift. One day
    covers every real timezone offset; two would start admitting a two-legged
    tie's other leg."""
    assert DATE_TOLERANCE_DAYS == 1
    _, counts = filter_picks_for_date([_pick("2026-08-27")], "2026-08-25", drop_undated=False)
    assert counts["wrong_date"] == 1


def test_a_settled_pick_is_never_a_read_on_an_upcoming_fixture():
    kept, counts = filter_picks_for_date([_pick(settled=True)], "2026-08-25", drop_undated=False)
    assert kept == []
    assert counts["settled"] == 1


def test_undated_picks_are_kept_for_a_same_day_run():
    """Typersi's tables state no fixture date. Dropping them by default would
    discard the whole source on the day it was fetched for."""
    kept, counts = filter_picks_for_date([_pick(None)], "2026-08-25", drop_undated=False)
    assert len(kept) == 1
    assert counts["undated_kept"] == 1


def test_undated_picks_are_droppable_for_a_backfill():
    kept, counts = filter_picks_for_date([_pick(None)], "2026-08-25", drop_undated=True)
    assert kept == []
    assert counts["undated_dropped"] == 1


def test_an_unparseable_date_is_dropped_and_counted_not_guessed():
    kept, counts = filter_picks_for_date([_pick("dzisiaj")], "2026-08-25", drop_undated=False)
    assert kept == []
    assert counts["unparseable_date"] == 1
    assert counts["wrong_date"] == 0  # a distinct problem, reported distinctly


def test_counts_always_reconcile_with_the_input():
    picks = [
        _pick("2026-08-25"),
        _pick("2026-08-26"),
        _pick("2026-08-01"),
        _pick(None),
        _pick(settled=True),
        _pick("nonsense"),
    ]
    kept, counts = filter_picks_for_date(picks, "2026-08-25", drop_undated=False)
    accounted = (
        counts["exact_day"]
        + counts["adjacent_day_kept"]
        + counts["undated_kept"]
        + counts["wrong_date"]
        + counts["undated_dropped"]
        + counts["settled"]
        + counts["unparseable_date"]
    )
    assert accounted == len(picks)
    assert counts["kept"] == len(kept)
