"""2026-09-23 — two tennis markets the pipeline quoted and could not use.

* "1. set - liczba gemow" / "2. set - liczba gemow": both players' games in one
  set. Superbet quoted it on 246 fixtures that day; every one went to
  unmapped_markets because no metric or mapping existed. It is priced from its
  own frequency: a set has 6, 7, 8, 9, 10, 12 or 13 games (rarely 14+) and
  never 11, and a
  normal CDF put 0.365 on OVER 10.5 where 0.220 happened (265,466 replayed
  rows, scripts/sofa/measure_empirical_tennis_counts.py).
* `tiebreaks_total`: mapped, priced and sampled, then refused by CONFIDENCE as
  NOT_IN_CALIBRATION_FIT on every row (59 that day) and skipped by the
  calibration fit, because "not a count and not empirical" was read as "no
  model". It has one — a floorless normal — and its top bucket is calibrated.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.contracts import Fixture, GapReason
from bet.sofa.engine import (
    has_calibratable_model,
    uses_empirical_frequency,
    uses_negative_binomial,
)
from bet.sofa.market_mapper import classify_market, get_mechanism_family
from bet.sofa.metrics import TENNIS_METRICS, extract_metric
from bet.sofa.offer import OfferFetcher, parse_line
from bet.sofa.timeutil import now


def _tennis_event(home: list[int], away: list[int]) -> dict[str, Any]:
    return {
        "homeScore": {f"period{i}": v for i, v in enumerate(home, start=1)},
        "awayScore": {f"period{i}": v for i, v in enumerate(away, start=1)},
        "status": {"code": 100},
    }


# ---------------------------------------------------------------------------
# set totals: mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("1. set - liczba gemów", "games_set1_total"),
        ("1.set - liczba gemów", "games_set1_total"),
        ("2. set - liczba gemów", "games_set2_total"),
        ("2.set - liczba gemów", "games_set2_total"),
    ],
)
def test_the_set_total_names_superbet_sends_are_mapped(
    name: str, expected: str
) -> None:
    assert classify_market(name) == (expected, "")


def test_the_per_player_set_market_is_unchanged() -> None:
    """The new keys must not swallow "1. set - <player> liczba gemow"."""
    assert classify_market("1. set - Kenta Kawada liczba gemów") == (
        "games_won_set1_for",
        "kenta kawada",
    )


def test_the_set_prefix_on_the_line_is_checked() -> None:
    """Superbet sends "1-9.5"; a set-2 quote must not land on the set-1 ladder."""
    assert parse_line("1-9.5", "games_set1_total") == 9.5
    assert parse_line("2-10.5", "games_set2_total") == 10.5
    with pytest.raises(ValueError, match="disagrees"):
        parse_line("2-9.5", "games_set1_total")


# ---------------------------------------------------------------------------
# set totals: the quantity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metric", "home", "away", "expected"),
    [
        ("games_set1_total", [6, 3], [4, 6], 10.0),
        ("games_set2_total", [6, 3], [4, 6], 9.0),
        ("games_set1_total", [7, 6], [6, 3], 13.0),  # the tiebreak game counts
        ("games_set1_total", [6], [0], 6.0),
    ],
)
def test_the_set_total_is_both_players_games_in_that_set(
    metric: str, home: list[int], away: list[int], expected: float
) -> None:
    event = _tennis_event(home, away)
    for is_home in (True, False):  # a total has no side
        assert extract_metric(metric, "tennis", {}, None, event, is_home) == expected


def test_an_unplayed_set_is_missing_data_not_zero() -> None:
    event = _tennis_event([6], [2])
    assert (
        extract_metric("games_set2_total", "tennis", {}, None, event, True)
        == GapReason.STAT_KEY_ABSENT
    )


def test_set_totals_are_priced_from_their_own_frequency() -> None:
    for metric in ("games_set1_total", "games_set2_total"):
        assert metric in TENNIS_METRICS
        assert uses_empirical_frequency(metric)
        assert not uses_negative_binomial(metric)
        assert has_calibratable_model(metric)


def test_a_set_total_shares_a_family_with_the_match_total() -> None:
    """One fixture must not spend two coupon slots on the same fact."""
    assert get_mechanism_family("games_set1_total") == get_mechanism_family(
        "games_total"
    )
    assert get_mechanism_family("games_set2_total") == get_mechanism_family(
        "games_total"
    )


class _Client:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items

    def event_odds(self, event_id: str | int) -> dict[str, Any]:
        return {"odds": self.items}


def _fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["101"],
        sport="tennis",
        kickoff_utc=now(),
        home_name="Daniil Glinka",
        away_name="Ugo Blanchet",
        home_entity_id=1,
        away_entity_id=2,
        competition_name="Saint Tropez, France",
        competition_id=3,
        season_id=4,
        category_name="Challenger",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type="Hardcourt outdoor",
        default_period_count=3,
    )


def test_offer_builds_a_set_total_rung_from_the_real_payload_shape() -> None:
    """Items copied from Superbet event 15109078 at 09:22Z on 2026-09-23."""
    items = [
        {"marketName": "1. set - liczba gemów", "specialBetValue": "1-9.5",
         "name": "Poniżej 9.5", "price": 2.2},
        {"marketName": "1. set - liczba gemów", "specialBetValue": "1-9.5",
         "name": "Powyżej 9.5", "price": 1.58},
        {"marketName": "2. set - liczba gemów", "specialBetValue": "2-10.5",
         "name": "Poniżej 10.5", "price": 1.38},
        {"marketName": "2. set - liczba gemów", "specialBetValue": "2-10.5",
         "name": "Powyżej 10.5", "price": 2.75},
    ]
    [offer] = OfferFetcher(_Client(items)).fetch_offers([_fixture()])
    rungs = {(r.market, r.line): r for r in offer.rungs}
    assert rungs[("games_set1_total", 9.5)].over_odds == 1.58
    assert rungs[("games_set1_total", 9.5)].under_odds == 2.2
    assert rungs[("games_set2_total", 10.5)].over_odds == 2.75
    assert rungs[("games_set2_total", 10.5)].under_odds == 1.38
    assert not any("liczba gem" in u for u in offer.unmapped_markets)


# ---------------------------------------------------------------------------
# tiebreaks: a model the confidence path did not recognise
# ---------------------------------------------------------------------------


def test_tiebreaks_have_a_model_and_xg_does_not() -> None:
    assert has_calibratable_model("tiebreaks_total")
    # Unchanged: counts, empirical metrics, and the model-less xG pair.
    assert has_calibratable_model("goals_total")
    assert has_calibratable_model("sets_total")
    assert not has_calibratable_model("xg_total")
    assert not has_calibratable_model("xg_for")


def test_tiebreaks_keep_the_normal_estimator() -> None:
    """The replay gave no evidence to switch (n=688, sign flips on a split)."""
    assert not uses_empirical_frequency("tiebreaks_total")
    assert not uses_negative_binomial("tiebreaks_total")


def test_the_calibration_fit_scores_tiebreak_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Until 2026-09-23 the fit skipped them, so no curve could ever form."""
    from scripts.sofa import fit_confidence

    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute(
        "create table sofa_settled_row (market text, line real, direction text,"
        " sample_size int, sample_mean real, sample_sd real, actual_value real,"
        " p_central real, sport text)"
    )
    # 0.3 tiebreaks a match on average: UNDER 0.5 is the likely side.
    con.executemany(
        "insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?)",
        [("tiebreaks_total", 0.5, "UNDER", 20, 0.3, 0.47, 0.0, 0.7, "tennis")] * 5
        + [("xg_total", 2.5, "OVER", 20, 2.6, 1.0, 3.1, 0.5, "football")] * 5,
    )
    con.commit()
    con.close()

    out = tmp_path / "cal.json"
    monkeypatch.setattr(
        sys, "argv", ["fit", "--db-path", str(db), "--out", str(out)]
    )
    assert fit_confidence.main() == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["fitted_from"]["scored_rows"] == 5  # tiebreaks in, xG still out


# ---------------------------------------------------------------------------
# a market with no curve of its own may not claim more than measured ones
# ---------------------------------------------------------------------------


def _cal(by_market: dict[str, Any]) -> Any:
    from bet.sofa.confidence import Calibration

    pool = {
        "0.750-0.800": {"realised_lo95": 0.7515, "n": 3112},
        "0.800-0.825": {"realised_lo95": 0.7619, "n": 1672},
        "0.825-0.850": {"realised_lo95": 0.7999, "n": 1464},
        "0.900-0.925": {"realised_lo95": 0.8310, "n": 1330},
    }
    return Calibration(pooled={}, by_market=by_market, pooled_by_sport={"tennis": pool})


def test_an_unmeasured_market_is_capped() -> None:
    """The verifier's finding on the 2026-09-23 rebuild: games_set*_total and
    tiebreaks_total had no curve, so the ceiling guard (which only protects a
    market WITH a curve) never ran and they could borrow the pool to 0.83."""
    # games_won_for is the measured empirical market; its curve stops at 0.825
    cal = _cal({"games_won_for": {"0.750-0.800": {"realised_lo95": 0.70, "n": 900},
                                  "0.800-0.825": {"realised_lo95": 0.72, "n": 500}}})
    for market in ("games_set1_total", "games_set2_total", "tiebreaks_total",
                   "games_won_set1_for"):
        assert cal.realised(market, 0.78, "tennis") == (0.7515, "pooled:tennis", 3112)
        assert cal.realised(market, 0.83, "tennis") is None
        assert cal.realised(market, 0.91, "tennis") is None
    # A count market has a distribution behind it and keeps the pool.
    assert cal.realised("aces_total", 0.91, "tennis") == (0.8310, "pooled:tennis", 1330)


def test_with_no_measured_empirical_market_the_cap_is_tighter_not_absent() -> None:
    cal = _cal({})
    assert cal.realised("games_set1_total", 0.79, "tennis") is not None
    assert cal.realised("games_set1_total", 0.80, "tennis") is None


def test_tiebreaks_share_the_length_family_in_a_builder() -> None:
    """A tiebreak is a 13-game set: never an independent leg beside games."""
    from bet.sofa.confidence import quantity_family

    assert quantity_family("tiebreaks_total") == quantity_family("games_total")
    assert quantity_family("tiebreaks_total") == quantity_family("sets_total")
