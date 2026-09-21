"""The league-baseline prior: how much evidence it needs, and what it must admit.

Written 2026-09-21 after the coupon carried a `corners_2h_for OVER 2.5` at a
claimed 62.3% for a team whose own eight matches produced one. The arithmetic
was perfect the whole way down; the prior it started from was not.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts.sofa.fit_constants import (
    MIN_BASELINE_OBSERVATIONS,
    SECOND_HALF_SHARE_BAND,
    check_half_match_coherence,
    fit_baselines,
)
from scripts.sofa.run_sheet import get_prior


def _db(rows: list[tuple]) -> sqlite3.Connection:
    """A settled table holding exactly the rows a test cares about."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE sofa_settled_row (
               competition_id INTEGER, market TEXT, subject TEXT,
               sofascore_event_id INTEGER, actual_value REAL)"""
    )
    conn.executemany(
        "INSERT INTO sofa_settled_row VALUES (?,?,?,?,?)", rows
    )
    return conn


def test_a_pool_thinner_than_a_league_entry_is_not_written():
    """The pool is held to the same bar as a league entry.

    Before this, `MIN_BASELINE_OBSERVATIONS` filtered per-league entries and
    then the pooled mean of those same too-thin values was written anyway, so
    the rule it enforced was decorative: whatever was rejected as a league
    prior came back as a global one.
    """
    rows = [
        (1, "corners_2h_for", "a", i, 1.0)
        for i in range(MIN_BASELINE_OBSERVATIONS - 1)
    ]
    out = fit_baselines(_db(rows))
    assert "corners_2h_for" not in out


def test_a_pool_at_the_bar_is_written_and_carries_its_own_n():
    rows = [
        (1, "corners_2h_for", "a", i, 2.0)
        for i in range(MIN_BASELINE_OBSERVATIONS)
    ]
    out = fit_baselines(_db(rows))
    glob = out["corners_2h_for"]["global"]
    assert glob == {"mean": 2.0, "n": MIN_BASELINE_OBSERVATIONS}


def test_a_refused_pool_means_no_prior_not_a_silent_zero():
    """`get_prior` returning None makes run_sheet use the sample's own mean.

    That is the whole reason refusing the pool is safe rather than reckless.
    """
    assert get_prior({}, "corners_2h_for", 17) is None


def test_get_prior_reads_both_the_new_pool_shape_and_the_old_one():
    """Every baselines file written before 2026-09-21 holds a bare float."""
    assert get_prior({"m": {"global": {"mean": 2.65, "n": 110}}}, "m", 17) == 2.65
    assert get_prior({"m": {"global": 3.4286}}, "m", 17) == 3.4286


def test_a_league_entry_still_beats_the_pool():
    baselines = {"m": {"17": {"mean": 1.0, "n": 50}, "global": {"mean": 9.0, "n": 900}}}
    assert get_prior(baselines, "m", 17) == 1.0
    assert get_prior(baselines, "m", 99) == 9.0


def test_the_split_that_shipped_on_2026_09_21_is_reported():
    """61.5% of a match's corners in the second half is not a fact about football.

    The sum test alone would have passed this: 4.077 + 6.500 = 10.577 against
    a full-match 9.904 is only 6.8% adrift. The share is what was wrong.
    """
    shipped = {
        "corners_total": {"global": 9.904},
        "corners_1h_total": {"global": 4.0769},
        "corners_2h_total": {"global": 6.5},
    }
    findings = check_half_match_coherence(shipped)
    assert any("second half is 61.5%" in f for f in findings)


def test_the_measured_split_passes():
    """Fitted from this repo's own settled rows: 4.4485 / 5.1587 = 53.7%."""
    measured = {
        "corners_total": {"global": {"mean": 9.904, "n": 900}},
        "corners_1h_total": {"global": {"mean": 4.4485, "n": 359}},
        "corners_2h_total": {"global": {"mean": 5.1587, "n": 63}},
    }
    assert check_half_match_coherence(measured) == []


@pytest.mark.parametrize("share", [0.30, 0.70])
def test_an_implausible_share_is_caught_in_both_directions(share: float):
    whole = 10.0
    second = whole * share
    first = whole - second
    out = check_half_match_coherence(
        {
            "goals_total": {"global": whole},
            "goals_1h_total": {"global": first},
            "goals_2h_total": {"global": second},
        }
    )
    low, high = SECOND_HALF_SHARE_BAND
    assert not low <= share <= high
    assert any("second half is" in f for f in out)


def test_a_family_with_no_half_markets_is_not_invented():
    assert check_half_match_coherence({"aces_total": {"global": 5.5}}) == []
