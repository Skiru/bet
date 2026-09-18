"""F46 — three defects a tennis match brought to the surface.

The 2026-09-18 board priced Wunderlich–Corwin (UTR PTT group) at p_central
0.78 for OVER 17.5 games against a devigged market price near 0.31. Three
separate faults compounded:

1. the sample took the ten *oldest* of the thirty most recent matches;
2. a third of the tennis slots were burnt because `gamesWon` is missing from
   /statistics on 35% of matches, while the set scores sat in the listing;
3. K_CENTRE, fitted on a history that is 98% football, put two thirds of the
   centre on "the average tennis match".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import extract_metric
from scripts.sofa.run_sheet import read_constant


# --------------------------------------------------------------------------
# 1. the sample must be the most recent matches, not the first ones listed
# --------------------------------------------------------------------------


def _event(event_id: int, day: int, entity_id: int = 1) -> dict:
    return {
        "id": event_id,
        "startTimestamp": int(
            datetime(2026, 9, day, 12, 0, tzinfo=UTC).timestamp()
        ),
        "status": {"type": "finished", "code": 100},
        "homeTeam": {"id": entity_id},
        "awayTeam": {"id": 99},
        "homeScore": {"period1": 6, "period2": 6, "current": 2},
        "awayScore": {"period1": 4, "period2": 4, "current": 0},
        "groundType": "Hardcourt outdoor",
    }


def test_sofascore_pages_are_oldest_first_so_the_cut_must_come_last() -> None:
    """Measured: 296 of 296 cached page-0 listings are ascending.

    Taking the first `sample_n` of an ascending page is taking the oldest.
    """
    from bet.sofa.samples import get_historical_events

    class _Cache:
        def get_entity_events(self, *a: object) -> dict | None:
            # One page of 20, ascending, days 1..20 of September.
            return {"events": [_event(1000 + d, d) for d in range(1, 21)]}

        def save_entity_events(self, *a: object) -> None:
            return None

    class _Fixture:
        kickoff_utc = datetime(2026, 9, 25, tzinfo=UTC)
        ground_type = "Hardcourt outdoor"
        default_period_count = None

    class _Config:
        sample_n = 10

    events = get_historical_events(
        client=None,  # never reached: the cache answers
        cache=_Cache(),
        entity_id=1,
        sport="football",
        fixture=_Fixture(),
        config=_Config(),
    )
    assert len(events) == 10
    days = [
        datetime.fromtimestamp(e["startTimestamp"], UTC).day for e in events
    ]
    # The ten most recent, newest first — not days 1..10.
    assert days == [20, 19, 18, 17, 16, 15, 14, 13, 12, 11]


# --------------------------------------------------------------------------
# 2. games come from the listing when the statistic is absent
# --------------------------------------------------------------------------

LISTING = {
    "homeScore": {"period1": 4, "period2": 3},
    "awayScore": {"period1": 6, "period2": 6},
}


def test_games_fall_back_to_the_set_scores() -> None:
    """`gamesWon` is absent from /statistics on 689 of 1,992 cached tennis
    events. The number it would have carried is in the listing on all of them,
    and check_internal_consistency has always asserted the two agree."""
    no_stat = {"ALL": {"aces": (2.0, 5.0)}}
    assert extract_metric("games_total", "tennis", no_stat, None, LISTING, True) == 19.0
    assert (
        extract_metric("games_won_for", "tennis", no_stat, None, LISTING, True) == 7.0
    )
    assert (
        extract_metric("games_won_for", "tennis", no_stat, None, LISTING, False) == 12.0
    )


def test_the_statistic_still_wins_when_it_is_there() -> None:
    with_stat = {"ALL": {"gamesWon": (7.0, 12.0)}}
    assert (
        extract_metric("games_total", "tennis", with_stat, None, LISTING, True) == 19.0
    )


def test_neither_source_is_still_a_refusal() -> None:
    assert (
        extract_metric("games_total", "tennis", {"ALL": {}}, None, {}, True)
        == GapReason.STAT_KEY_ABSENT
    )


def test_a_partial_set_score_is_not_a_short_match() -> None:
    """A set present on one side only cannot be summed."""
    lopsided = {"homeScore": {"period1": 6, "period2": 6}, "awayScore": {"period1": 4}}
    value = extract_metric("games_total", "tennis", {"ALL": {}}, None, lopsided, True)
    assert value == 10.0  # only the set both sides report


# --------------------------------------------------------------------------
# 3. K_CENTRE is per sport, because the priors are not comparable
# --------------------------------------------------------------------------


def test_k_centre_is_read_per_sport() -> None:
    constants = {"K_CENTRE": {"value": 25.0, "by_sport": {"tennis": 2.0}}}
    assert read_constant(constants, "K_CENTRE", 10.0, "tennis") == (2.0, True)
    assert read_constant(constants, "K_CENTRE", 10.0, "football") == (25.0, True)
    assert read_constant(constants, "K_CENTRE", 10.0, "") == (25.0, True)


def test_a_sport_without_its_own_fit_falls_back_to_the_pooled_value() -> None:
    constants = {"K_CENTRE": {"value": 25.0, "by_sport": {"football": 25.0}}}
    assert read_constant(constants, "K_CENTRE", 10.0, "baseball") == (25.0, True)


def test_an_unfitted_constant_is_still_unfitted_per_sport() -> None:
    constants = {"K_CENTRE": {"value": None, "by_sport": {}}}
    assert read_constant(constants, "K_CENTRE", 10.0, "tennis") == (10.0, False)


def test_the_shipped_fit_separates_the_two_sports() -> None:
    """Football's prior is per competition and informative; tennis's is one
    global mean, so it must be trusted far less."""
    import json
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    entry = json.loads(
        (repo / "config/sofa_engine_constants.json").read_text(encoding="utf-8")
    )["K_CENTRE"]
    by_sport = entry.get("by_sport") or {}
    if not by_sport:
        pytest.skip("constants not fitted in this checkout")
    assert by_sport["tennis"] < by_sport["football"], by_sport
