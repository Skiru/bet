"""The coupon must say when it priced from a fresher offer than the sheet on disk.

``--refresh-offer`` re-fetches the board and prices from it, but does not rewrite
``<date>_event_dossiers_stats_sheet.json``. On 2026-09-06 the coupon was built at
18:51Z from an 18:51Z offer while the sheet still carried 16:00Z prices, and
nothing in either file said so -- Remo-Flamengo 10.5 UNDER read 1.60 in one and
1.58 in the other.
"""
from datetime import datetime, timezone

from bet.simple_stats.coupons import _moment_utc, _stale_sheet_note


class _Stamped:
    def __init__(self, generated_at):
        self.generated_at = generated_at


def test_a_fresher_offer_than_the_sheet_is_reported_with_the_gap():
    note = _stale_sheet_note(
        _Stamped("2026-09-06T16:00:56+00:00"), _Stamped("2026-09-06T18:51:51+00:00")
    )
    assert note is not None
    assert "170 min" in note
    assert "18:51" in note and "16:00" in note


def test_a_sheet_at_least_as_fresh_as_the_offer_says_nothing():
    assert _stale_sheet_note(
        _Stamped("2026-09-06T18:51:51+00:00"), _Stamped("2026-09-06T18:51:51+00:00")
    ) is None
    assert _stale_sheet_note(
        _Stamped("2026-09-06T19:00:00+00:00"), _Stamped("2026-09-06T18:51:51+00:00")
    ) is None


def test_a_gap_under_a_minute_is_not_worth_a_note():
    # The ordinary case: ANALYZE writes the sheet, build_coupons runs seconds
    # later off the same offer. Warning there would train the reader to ignore
    # the warning that matters.
    assert _stale_sheet_note(
        _Stamped("2026-09-06T18:51:10+00:00"), _Stamped("2026-09-06T18:51:51+00:00")
    ) is None


def test_no_offer_means_no_claim():
    assert _stale_sheet_note(_Stamped("2026-09-06T16:00:00+00:00"), None) is None


def test_an_unparseable_stamp_fails_closed_rather_than_guessing():
    assert _stale_sheet_note(_Stamped("wczoraj"), _Stamped("2026-09-06T18:51:51+00:00")) is None
    assert _stale_sheet_note(_Stamped("2026-09-06T16:00:00+00:00"), _Stamped(None)) is None


def test_a_naive_stamp_is_read_as_utc_and_not_as_local():
    # Timestamps in this repo print UTC+2 unlabelled in places; a naive string
    # must not be silently shifted, or a 2h gap appears or disappears.
    got = _moment_utc("2026-09-06T18:51:51")
    assert got == datetime(2026, 9, 6, 18, 51, 51, tzinfo=timezone.utc)


def test_a_zulu_suffix_parses():
    assert _moment_utc("2026-09-06T18:51:51Z") == datetime(
        2026, 9, 6, 18, 51, 51, tzinfo=timezone.utc
    )
