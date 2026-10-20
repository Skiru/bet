# ruff: noqa: E501  - Superbet names quoted whole read better unwrapped.
"""Football statistic variants behind epochs.FOOTBALL_STAT_VARIANTS_FROM_UTC
(night 2026-10-20/21; market_mapper.classify_stat_variant).

Names, selections and specialBetValues are Superbet's own, as recorded in
runs/sofa/2026-10-14..10-20/unmapped_prices (LASK Linz - Liverpool,
Feyenoord - Como, ...):

    "Każda drużyna powyżej X rzutów z autu"    "Powyżej 13.5 - Tak"  "13.5"  (63 events)
    "Każda drużyna powyżej X wybić od bramki"  "Powyżej 4.5 - Tak"   "4.5"   (63)
    "Każda z drużyn powyżej X odbiorów"        "Powyżej 12.5 - tak"  "12.5"  (45)
    "Strzały - Handicap"                       "LASK Linz (8.5)"     "8.5"   (61)
    "1. połowa - liczba strzałów - handicap"   "Liverpool (-3.5)"    "3.5"   (61)
    "2. połowa - liczba strzałów - handicap"   "LASK Linz (3.5)"     "3.5"   (61)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import offer as offer_mod
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.derived import price_derived_rungs
from bet.sofa.market_mapper import (
    STAT_VARIANT_MARKETS,
    classify_stat_variant,
    derived_base,
    derived_side_metric,
)
from bet.sofa.metrics import FOOTBALL_METRICS
from bet.sofa.offer import OfferFetcher, classify_odd
from bet.sofa.samples import metrics_from_offer
from bet.sofa.superbet_names import names
from scripts.sofa.run_settle import _settle_derived

SIDES = ("LASK Linz", "Liverpool")
FROZEN = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)


def _odd(market: str, name: str, sbv: str | None, price: float) -> dict[str, Any]:
    out: dict[str, Any] = {"marketName": market, "name": name, "price": price}
    if sbv is not None:
        out["specialBetValue"] = sbv
    return out


# The new odds of one listing, as Superbet sent them.
_NEW = [
    _odd("Każda drużyna powyżej X rzutów z autu", "Powyżej 13.5 - Tak", "13.5", 1.62),
    _odd("Każda drużyna powyżej X rzutów z autu", "Powyżej 15.5 - Tak", "15.5", 2.35),
    _odd("Każda drużyna powyżej X wybić od bramki", "Powyżej 4.5 - Tak", "4.5", 1.75),
    _odd("Każda z drużyn powyżej X odbiorów", "Powyżej 12.5 - tak", "12.5", 2.1),
    _odd("Strzały - Handicap", "LASK Linz (8.5)", "8.5", 1.85),
    _odd("Strzały - Handicap", "Liverpool (-8.5)", "8.5", 1.9),
    _odd("1. połowa - liczba strzałów - handicap", "LASK Linz (3.5)", "3.5", 1.88),
    _odd("1. połowa - liczba strzałów - handicap", "Liverpool (-3.5)", "3.5", 1.87),
    _odd("2. połowa - liczba strzałów - handicap", "LASK Linz (3.5)", "3.5", 1.9),
    _odd("2. połowa - liczba strzałów - handicap", "Liverpool (-3.5)", "3.5", 1.85),
]
# What the listing quotes besides (read before the switch already).
_OLD = [
    _odd("Liczba rzutów rożnych", "powyżej 9.5", "9.5", 1.8),
    _odd("Liczba rzutów rożnych", "poniżej 9.5", "9.5", 1.95),
    _odd("Każda z drużyn powyżej X strzałów", "Powyżej 8.5 - tak", "8.5", 1.7),
    _odd("Liczba rzutów z autu - Liverpool", "powyżej 20.5", "20.5", 1.85),
    _odd("Liczba rzutów z autu - Liverpool", "poniżej 20.5", "20.5", 1.9),
]


# --- the switch ------------------------------------------------------------


def test_the_switch_is_on_from_2026_10_21(monkeypatch: pytest.MonkeyPatch) -> None:
    # switched on 2026-10-21 00:00Z (night 2026-10-20/21)
    assert epochs.FOOTBALL_STAT_VARIANTS_FROM_UTC == datetime(2026, 10, 21, tzinfo=UTC)
    assert not epochs.football_stat_variants("2026-10-20", FROZEN)
    monkeypatch.setattr(epochs, "FOOTBALL_STAT_VARIANTS_FROM_UTC", None)
    assert not epochs.football_stat_variants("2026-10-21", FROZEN)


def test_the_switch_is_judged_on_the_day_built_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_STAT_VARIANTS_FROM_UTC",
                        datetime(2026, 10, 21, tzinfo=UTC))
    at = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)
    assert not epochs.football_stat_variants("2026-10-20", at)
    assert not epochs.football_stat_variants("2026-10-21", at - timedelta(seconds=1))
    assert epochs.football_stat_variants("2026-10-21", at)


def test_day_flags_carry_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOFA_NOW", "2026-10-21T06:00:00Z")
    monkeypatch.setattr(epochs, "FOOTBALL_STAT_VARIANTS_FROM_UTC", None)
    assert offer_mod.day_flags("2026-10-21")["football_stat_variants"] is False
    monkeypatch.setattr(epochs, "FOOTBALL_STAT_VARIANTS_FROM_UTC",
                        datetime(2026, 10, 21, tzinfo=UTC))
    assert offer_mod.day_flags("2026-10-21")["football_stat_variants"] is True


# --- the mapper: every Polish name ----------------------------------------


@pytest.mark.parametrize(
    ("market", "selection", "sbv", "expected"),
    [
        ("Każda drużyna powyżej X rzutów z autu", "Powyżej 13.5 - Tak", "13.5",
         ("both_over_throw_ins", "", 13.5, "OVER")),
        ("Każda drużyna powyżej X rzutów z autu", "Powyżej 13.5 - Nie", "13.5",
         ("both_over_throw_ins", "", 13.5, "UNDER")),
        ("Każda drużyna powyżej X wybić od bramki", "Powyżej 4.5 - Tak", "4.5",
         ("both_over_goal_kicks", "", 4.5, "OVER")),
        ("Każda z drużyn powyżej X odbiorów", "Powyżej 12.5 - tak", "12.5",
         ("both_over_tackles", "", 12.5, "OVER")),
        # the other spelling of "each team" is the same question
        ("Każda z drużyn powyżej X rzutów z autu", "Powyżej 11.5 - tak", "11.5",
         ("both_over_throw_ins", "", 11.5, "OVER")),
        ("Każda drużyna powyżej X odbiorów", "Powyżej 9.5 - Tak", "9.5",
         ("both_over_tackles", "", 9.5, "OVER")),
        ("Strzały - Handicap", "LASK Linz (8.5)", "8.5",
         ("handicap_shots", "lask linz", 8.5, "OVER")),
        ("Strzały - Handicap", "Liverpool (-8.5)", "8.5",
         ("handicap_shots", "liverpool", -8.5, "OVER")),
        ("1. połowa - liczba strzałów - handicap", "Liverpool (-3.5)", "3.5",
         ("handicap_shots_1h", "liverpool", -3.5, "OVER")),
        ("2. połowa - liczba strzałów - handicap", "LASK Linz (3.5)", "3.5",
         ("handicap_shots_2h", "lask linz", 3.5, "OVER")),
        ("2.połowa - liczba strzałów - handicap", "LASK Linz (0.5)", "0.5",
         ("handicap_shots_2h", "lask linz", 0.5, "OVER")),
    ],
)
def test_each_superbet_name_maps_to_its_market(
    market: str, selection: str, sbv: str, expected: tuple[str, str, float, str],
) -> None:
    assert classify_stat_variant(market, selection, sbv, SIDES) == expected
    assert expected[0] in STAT_VARIANT_MARKETS


@pytest.mark.parametrize(
    ("market", "selection", "sbv"),
    [
        # the selection names another rung than the specialBetValue
        ("Każda drużyna powyżej X rzutów z autu", "Powyżej 13.5 - Tak", "14.5"),
        # no line at all
        ("Każda drużyna powyżej X wybić od bramki", "Powyżej 4.5 - Tak", None),
        # neither yes nor no
        ("Każda z drużyn powyżej X odbiorów", "Powyżej 12.5", "12.5"),
        # a club that is not a side of the listing
        ("Strzały - Handicap", "Arsenal (1.5)", "1.5"),
        # a selection without its own bracketed line
        ("Strzały - Handicap", "LASK Linz", "1.5"),
        # a SuperBets combination
        ("Strzały - Handicap; Liczba goli", "LASK Linz (8.5)", "8.5"),
        # every name another classifier owns stays theirs
        ("Każda z drużyn powyżej X rzutów rożnych", "Powyżej 3.5 - tak", "3.5"),
        ("Liczba strzałów - handicap", "LASK Linz (8.5)", "8.5"),
        ("1. połowa - rzuty rożne - handicap", "LASK Linz (1.5)", "1.5"),
        # a timed throw-in market (no Sofascore timeline) is not the total
        ("Liczba rzutów z autu od 0:00 do 9:59 minuty", "Powyżej 3.5", "3.5"),
    ],
)
def test_what_it_refuses(market: str, selection: str, sbv: str | None) -> None:
    assert classify_stat_variant(market, selection, sbv, SIDES) is None


def test_every_market_it_writes_is_a_derived_market_on_a_declared_side_metric() -> None:
    for market in STAT_VARIANT_MARKETS:
        base = derived_base(market)
        assert base is not None
        assert derived_side_metric(base) in FOOTBALL_METRICS, market


def test_off_classify_odd_leaves_every_new_name_unmapped() -> None:
    for item in _NEW:
        assert classify_odd(item) == (None, item["marketName"])
        # every other switch on, this one off: still unmapped
        assert classify_odd(item, SIDES, True, SIDES, False, True, True, True,
                            False) == (None, item["marketName"])


def test_on_classify_odd_reads_them() -> None:
    for item in _NEW:
        got, label = classify_odd(item, (), True, SIDES, stat_variants=True)
        assert label is None and got is not None and got[0] in STAT_VARIANT_MARKETS


# --- OFFER end to end -------------------------------------------------------


class _Listing:
    def __init__(self, odds: list[dict[str, Any]]) -> None:
        self.odds = odds

    def event_odds(self, event_id: str) -> dict[str, Any]:
        return {"matchName": "LASK Linz·Liverpool", "utcDate": "2026-10-22T19:00:00Z",
                "odds": self.odds}


def _fixture(sport: str = "football") -> Fixture:
    return Fixture(
        sofascore_event_id=7, superbet_event_ids=["15000001"], sport=sport,
        kickoff_utc=FROZEN + timedelta(hours=10), home_name="LASK Linz",
        away_name="Liverpool", home_entity_id=1, away_entity_id=2,
        competition_name="UEFA Europa League", competition_id=679, season_id=1,
        category_name="Europe", identity="CONFIRMED", round_number=None,
        round_name=None, cup_round_type=None, previous_leg_event_id=None,
        venue_name=None, referee=None, ground_type=None, default_period_count=2)


def _fetch(on: bool | None, sport: str = "football") -> dict[str, Any]:
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        kwargs: dict[str, Any] = {"mappable_families": True,
                                  "football_score_markets": True}
        if on is not None:
            kwargs["football_stat_variants"] = on
        [entry] = OfferFetcher(_Listing(_OLD + _NEW), **kwargs).fetch_offers(
            [_fixture(sport)])
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    out: dict[str, Any] = entry.model_dump(mode="json")
    return out


def test_off_offer_is_identical_to_the_fetcher_without_the_switch() -> None:
    assert _fetch(False) == _fetch(None)
    off = _fetch(False)
    assert not any(r["market"] in STAT_VARIANT_MARKETS for r in off["rungs"])
    assert "Strzały - Handicap" in off["unmapped_markets"]


def test_on_offer_adds_exactly_the_new_rungs_and_changes_no_other() -> None:
    off, on = _fetch(False), _fetch(True)
    old = [r for r in on["rungs"] if r["market"] not in STAT_VARIANT_MARKETS]
    assert old == off["rungs"]
    new = {(r["market"], r["subject"], r["line"]): (r["over_odds"], r["under_odds"])
           for r in on["rungs"] if r["market"] in STAT_VARIANT_MARKETS}
    assert new == {
        ("both_over_throw_ins", "", 13.5): (1.62, None),
        ("both_over_throw_ins", "", 15.5): (2.35, None),
        ("both_over_goal_kicks", "", 4.5): (1.75, None),
        ("both_over_tackles", "", 12.5): (2.1, None),
        ("handicap_shots", "lask linz", 8.5): (1.85, None),
        ("handicap_shots", "liverpool", -8.5): (1.9, None),
        ("handicap_shots_1h", "lask linz", 3.5): (1.88, None),
        ("handicap_shots_1h", "liverpool", -3.5): (1.87, None),
        ("handicap_shots_2h", "lask linz", 3.5): (1.9, None),
        ("handicap_shots_2h", "liverpool", -3.5): (1.85, None),
    }
    for name in {o["marketName"] for o in _NEW}:
        assert name not in on["unmapped_markets"]
    assert set(off["unmapped_markets"]) - set(on["unmapped_markets"]) == {
        o["marketName"] for o in _NEW}


def test_on_a_tennis_listing_reads_none_of_them() -> None:
    on = _fetch(True, sport="tennis")
    assert not any(r["market"] in STAT_VARIANT_MARKETS for r in on["rungs"])


def test_on_samples_ask_for_the_side_metrics() -> None:
    offer = FixtureOffer.model_validate_json(json.dumps(_fetch(True)))
    assert {"throw_ins_for", "goal_kicks_for", "tackles_for", "shots_for",
            "shots_1h_for", "shots_2h_for"} <= metrics_from_offer(offer)


# --- SHEET prices them with the existing joint ------------------------------


def _obs(values: list[float]) -> list[Observation]:
    return [Observation(sofascore_event_id=1000 + i,
                        match_date_utc=FROZEN - timedelta(days=i + 1),
                        opponent=f"Opp{i}", value=v, competition_id=679,
                        season_id=1, venue=None)
            for i, v in enumerate(values)]


_SAMPLE_VALUES = {
    "throw_ins_for": ([18, 22, 19, 25, 17, 21, 20, 23, 16, 24],
                      [20, 18, 24, 19, 22, 17, 21, 25, 18, 20]),
    "goal_kicks_for": ([6, 8, 5, 7, 9, 6, 4, 7, 8, 6], [5, 7, 6, 4, 8, 6, 7, 5, 6, 9]),
    "tackles_for": ([15, 18, 14, 17, 16, 19, 13, 15, 17, 16],
                    [14, 16, 18, 13, 15, 17, 16, 14, 19, 15]),
    "shots_for": ([8, 11, 9, 7, 12, 10, 6, 9, 8, 10],
                  [18, 15, 20, 17, 16, 19, 14, 21, 17, 18]),
    "shots_1h_for": ([4, 5, 3, 6, 4, 5, 3, 4, 5, 4], [8, 7, 9, 6, 8, 10, 7, 8, 9, 7]),
    "shots_2h_for": ([4, 6, 6, 1, 8, 5, 3, 5, 3, 6], [10, 8, 11, 11, 8, 9, 7, 13, 8, 11]),
}


def _samples() -> FixtureSamples:
    return FixtureSamples(
        sofascore_event_id=7, readiness="READY", gaps=[],
        metrics={m: MetricSample(metric=m, side_a=_obs([float(v) for v in a]),
                                 side_b=_obs([float(v) for v in b]), h2h=[])
                 for m, (a, b) in _SAMPLE_VALUES.items()})


def _price(rungs: list[dict[str, Any]]) -> list[Any]:
    offer = FixtureOffer(
        sofascore_event_id=7, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(**{**r, "fetched_at_utc": FROZEN}) for r in rungs])
    rows, _ = price_derived_rungs(
        fixture=_fixture(), samples=_samples(), offer=offer,
        correlations={"shots": -0.0928}, vetoes=[], min_sample=5,
        max_ladder_sigma=1.5, k_price=10.0, unfitted=[], stats_only=True)
    return rows


def test_sheet_prices_every_new_market() -> None:
    on = _fetch(True)
    rows = _price([r for r in on["rungs"] if r["market"] in STAT_VARIANT_MARKETS])
    assert {r.market for r in rows} == STAT_VARIANT_MARKETS
    p = {(r.market, r.subject, r.line, r.direction): r.p_central for r in rows}
    # both teams over a higher line is never more likely
    assert p[("both_over_throw_ins", "", 13.5, "OVER")] > p[
        ("both_over_throw_ins", "", 15.5, "OVER")]
    # the two sides of one handicap are complements; the samples' gap (17.6
    # against 9.0 shots) sits on the 8.5 line, so neither side is far off 0.5
    a = p[("handicap_shots", "lask linz", 8.5, "OVER")]
    b = p[("handicap_shots", "liverpool", -8.5, "OVER")]
    assert a + b == pytest.approx(1.0, abs=1e-3)
    assert 0.4 < b < 0.6
    for half in ("handicap_shots_1h", "handicap_shots_2h"):
        assert p[(half, "lask linz", 3.5, "OVER")] + p[
            (half, "liverpool", -3.5, "OVER")] == pytest.approx(1.0, abs=1e-3)
    # the second half's gap (5.7 shots) is wider than the first's (3.0)
    assert p[("handicap_shots_2h", "liverpool", -3.5, "OVER")] > p[
        ("handicap_shots_1h", "liverpool", -3.5, "OVER")]


def test_sheet_rows_of_the_old_markets_do_not_move_when_the_new_rungs_join() -> None:
    off, on = _fetch(False), _fetch(True)
    shared = [r for r in off["rungs"] if r["market"].startswith(("both_over_", "handicap_"))]
    assert shared  # both_over_shots 8.5
    before = [r.model_dump(mode="json") for r in _price(shared)]
    after = [r.model_dump(mode="json") for r in _price(
        [r for r in on["rungs"] if r["market"].startswith(("both_over_", "handicap_"))])
        if r.market not in STAT_VARIANT_MARKETS]
    assert before == after


# --- SETTLE grades them with the derived path -------------------------------


def _row(market: str, line: float, subject: str = "", direction: str = "OVER"
         ) -> dict[str, Any]:
    return {"market": market, "line": line, "direction": direction,
            "subject": subject, "sport": "football"}


def _event() -> dict[str, Any]:
    return {"id": 7, "homeTeam": {"name": "LASK Linz"}, "awayTeam": {"name": "Liverpool"},
            "status": {"code": 100, "type": "finished"},
            "homeScore": {"current": 0, "period1": 0, "period2": 0},
            "awayScore": {"current": 2, "period1": 1, "period2": 1}}


_FLAT = {
    "ALL": {"throwIns": (14.0, 19.0), "goalKicks": (9.0, 4.0), "totalTackle": (13.0, 16.0),
            "totalShotsOnGoal": (7.0, 18.0), "passes": (300.0, 600.0)},
    "1ST": {"totalShotsOnGoal": (3.0, 10.0), "passes": (150.0, 300.0)},
    "2ND": {"totalShotsOnGoal": (4.0, 8.0), "passes": (150.0, 300.0)},
}


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (_row("both_over_throw_ins", 13.5), (14.0, "WIN")),
        (_row("both_over_throw_ins", 14.5), (14.0, "LOSS")),
        (_row("both_over_throw_ins", 14.5, direction="UNDER"), (14.0, "WIN")),
        (_row("both_over_goal_kicks", 3.5), (4.0, "WIN")),
        (_row("both_over_goal_kicks", 4.5), (4.0, "LOSS")),
        (_row("both_over_tackles", 12.5), (13.0, "WIN")),
        (_row("both_over_tackles", 13.5), (13.0, "LOSS")),
        # 7 - 18: Liverpool -8.5 wins by 11, LASK +8.5 loses
        (_row("handicap_shots", -8.5, "liverpool"), (11.0, "WIN")),
        (_row("handicap_shots", 8.5, "lask linz"), (-11.0, "LOSS")),
        (_row("handicap_shots", 11.5, "lask linz"), (-11.0, "WIN")),
        # first half 3 - 10, second half 4 - 8: each half read on its own
        (_row("handicap_shots_1h", -6.5, "liverpool"), (7.0, "WIN")),
        (_row("handicap_shots_1h", 6.5, "lask linz"), (-7.0, "LOSS")),
        (_row("handicap_shots_2h", -4.5, "liverpool"), (4.0, "LOSS")),
        (_row("handicap_shots_2h", 4.5, "lask linz"), (-4.0, "WIN")),
    ],
)
def test_settle_grades_each_new_market(row: dict[str, Any], expected: tuple[float, str]
                                       ) -> None:
    assert _settle_derived(row, "football", _FLAT, None, _event()) == expected


def test_settle_a_whole_number_landing_is_a_push_not_a_row() -> None:
    assert _settle_derived(_row("handicap_shots", -11.0, "liverpool"), "football",
                           _FLAT, None, _event()) == "PUSH"


def test_settle_a_missing_statistic_is_no_grade() -> None:
    flat = {"ALL": {"passes": (300.0, 600.0)}}
    graded = _settle_derived(_row("both_over_throw_ins", 13.5), "football", flat,
                             None, _event())
    assert isinstance(graded, str) and graded.startswith("throw_ins_for:")


# --- Superbet's words on the leg ---------------------------------------------


@pytest.mark.parametrize(
    ("leg", "expected"),
    [
        ({"market": "both_over_throw_ins", "line": 13.5, "direction": "OVER"},
         ("Każda drużyna powyżej X rzutów z autu", "Powyżej 13.5 - Tak")),
        ({"market": "both_over_goal_kicks", "line": 4.5, "direction": "OVER"},
         ("Każda drużyna powyżej X wybić od bramki", "Powyżej 4.5 - Tak")),
        ({"market": "both_over_tackles", "line": 12.5, "direction": "OVER"},
         ("Każda z drużyn powyżej X odbiorów", "Powyżej 12.5 - tak")),
        ({"market": "handicap_shots", "subject": "liverpool", "line": -8.5,
          "direction": "OVER"},
         ("Strzały - Handicap", "Liverpool (-8.5)")),
        ({"market": "handicap_shots_1h", "subject": "lask linz", "line": 3.5,
          "direction": "OVER"},
         ("1. połowa - liczba strzałów - handicap", "LASK Linz (3.5)")),
        ({"market": "handicap_shots_2h", "subject": "liverpool", "line": -3.5,
          "direction": "OVER"},
         ("2. połowa - liczba strzałów - handicap", "Liverpool (-3.5)")),
    ],
)
def test_superbet_names_of_the_new_legs(leg: dict[str, Any],
                                        expected: tuple[str, str]) -> None:
    got = names({"sport": "football", "subject": "", **leg}, SIDES)
    assert got == expected
    # and read back by the mapper as the same rung
    market, selection = expected
    sbv = selection.split()[1] if selection.startswith("Powyżej") else "0"
    mapped = classify_stat_variant(market, selection, sbv, SIDES)
    assert mapped is not None and mapped[0] == leg["market"]
    assert mapped[2] == leg["line"]
