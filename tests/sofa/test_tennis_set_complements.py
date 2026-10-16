"""The complement of a tennis exact sets score (tennis_sets.SET_SCORE_NOT),
behind epochs.TENNIS_SET_COMPLEMENTS_FROM_UTC (riding on TENNIS_SET_MARKETS).
Offline and fast. Evidence: docs/sofa/evidence/football_score_markets_2026-10-16.md.

Names and prices are the real ones (unmapped_prices of 2026-10-16, Daniil
Medvedev - Tommy Paul): "Daniil Medvedev wygra seta" Tak 1.17 / Nie 4.5 and
"Dokładny wynik" "Daniil Medvedev 0:2" 4.4 - the same event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import offer as offer_mod
from bet.sofa.confidence import OWN_CURVE_ONLY, Calibration, curve_market
from bet.sofa.contracts import FixtureOffer, PricedRung
from bet.sofa.tennis_sets import (
    SET_MARKETS,
    SET_SCORE,
    SET_SCORE_NOT,
    classify_set_complement,
    score_probs,
    set_value,
)
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS
from scripts.sofa.run_settle import _settle_set_market
from scripts.sofa.run_sheet import set_market_rows, sheet_row_json
from tests.sofa.offer_mappable_scenarios import FROZEN, fixture
from tests.sofa.test_tennis_set_markets import BUBLIK, EV, FX, POOL, ZVEREV, _event
from tests.sofa.test_tennis_set_markets import _forecast as _rating

MED, PAUL = "Daniil Medvedev", "Tommy Paul"


def _item(market: str, selection: str, price: float) -> dict[str, Any]:
    return {"marketName": market, "name": selection, "offerStateId": 1,
            "price": price, "status": "active"}


# --- the switch ---------------------------------------------------------------


def test_switch_rides_on_the_set_markets(monkeypatch: pytest.MonkeyPatch) -> None:
    at = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
    assert epochs.TENNIS_SET_COMPLEMENTS_FROM_UTC == at
    assert epochs.tennis_set_complements("2026-10-17", at)
    assert not epochs.tennis_set_complements("2026-10-16", at + timedelta(hours=1))
    assert not epochs.tennis_set_complements("2026-10-17", at - timedelta(seconds=1))
    monkeypatch.setattr(epochs, "TENNIS_SET_MARKETS_FROM_UTC", None)
    assert not epochs.tennis_set_complements("2026-10-17", at)
    monkeypatch.undo()
    monkeypatch.setattr(epochs, "TENNIS_SET_COMPLEMENTS_FROM_UTC", None)
    assert not epochs.tennis_set_complements("2027-01-01", at + timedelta(days=99))


# --- OFFER: the names, one canonical rung per event ----------------------------


NOT_MED_02 = (SET_SCORE_NOT, f"{MED} 0:2", 0.5)
NOT_PAUL_02 = (SET_SCORE_NOT, f"{PAUL} 0:2", 0.5)


@pytest.mark.parametrize("market,sel,want", [
    ("Daniil Medvedev wygra seta", "Tak", (*NOT_MED_02, "OVER")),
    ("Daniil Medvedev wygra seta", "Nie", (*NOT_MED_02, "UNDER")),
    ("Tommy Paul wygra seta", "Tak", (*NOT_PAUL_02, "OVER")),
    # not Medvedev 2:0 is not Paul 0:2: the other player's rung
    ("Daniil Medvedev wygra bez straty seta", "Nie", (*NOT_PAUL_02, "OVER")),
    ("Daniil Medvedev wygra bez straty seta", "Tak", (*NOT_PAUL_02, "UNDER")),
    ("Daniil Medvedev liczba setów", "Powyżej 0.5", (*NOT_MED_02, "OVER")),
    ("Daniil Medvedev liczba setów", "Poniżej 0.5", (*NOT_MED_02, "UNDER")),
    ("Handicap setowy", "Daniil Medvedev (1.5)", (*NOT_MED_02, "OVER")),
    ("Handicap setowy", "Tommy Paul (-1.5)", (*NOT_MED_02, "UNDER")),
    ("Handicap setowy", "Tommy Paul (1.5)", (*NOT_PAUL_02, "OVER")),
    # other questions
    ("Daniil Medvedev liczba setów", "Powyżej 1.5", None),
    ("Każdy z zawodników wygra przynajmniej jednego seta", "tak", None),
    ("Roger Federer wygra seta", "Tak", None),
    ("Handicap setowy", "Tommy Paul (2.5)", None),
    ("Handicap", "Tommy Paul (1.5)", None),
])
def test_classify_reads_the_superbet_names(
        market: str, sel: str, want: tuple[str, str, float, str] | None) -> None:
    assert classify_set_complement(market, sel, [MED, PAUL]) == want


def test_classify_needs_both_names() -> None:
    assert classify_set_complement("Daniil Medvedev wygra seta", "Tak", [MED]) is None
    assert classify_set_complement("Daniil Medvedev wygra seta", "Tak",
                                   [MED, MED]) is None


ODDS = [
    _item("Daniil Medvedev wygra seta", "Tak", 1.17),
    _item("Daniil Medvedev wygra seta", "Nie", 4.5),
    _item("Handicap setowy", "Daniil Medvedev (1.5)", 1.18),
    _item("Handicap setowy", "Tommy Paul (-1.5)", 4.4),
    _item("Daniil Medvedev wygra bez straty seta", "Tak", 2.12),
    _item("Daniil Medvedev wygra bez straty seta", "Nie", 1.68),
    _item("Dokładny wynik", "0:2", 4.4),
]


def _fetch(on: bool, sport: str = "tennis") -> FixtureOffer:
    fx = fixture(sport, "1")
    payload = {"eventId": "1", "matchName": f"{MED}·{PAUL}", "odds": ODDS}

    class C:
        def event_odds(self, _eid: str) -> dict[str, Any]:
            return payload

    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        out = offer_mod.OfferFetcher(C(), tennis_sets=True,
                                     tennis_set_complements=on).fetch_offers([fx])
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return out[0]


def test_switch_off_reads_none_of_them() -> None:
    off = _fetch(False)
    assert all(r.market != SET_SCORE_NOT for r in off.rungs)
    assert "Daniil Medvedev wygra seta" in off.unmapped_markets


def test_switch_on_builds_one_two_sided_rung_per_event() -> None:
    off, on = _fetch(False), _fetch(True)
    new = {(r.market, r.subject): r for r in on.rungs if r.market == SET_SCORE_NOT}
    assert set(new) == {NOT_MED_02[:2], NOT_PAUL_02[:2]}
    med = new[NOT_MED_02[:2]]
    # "wygra seta" and "Handicap setowy" are one bet: the lower price
    assert (med.over_odds, med.under_odds) == (1.17, 4.4)
    paul = new[NOT_PAUL_02[:2]]
    assert (paul.over_odds, paul.under_odds) == (1.68, 2.12)
    assert on.price_collisions == []
    assert [r for r in on.rungs if r.market != SET_SCORE_NOT] == off.rungs
    # the exact score itself is still read (set_score OVER only)
    assert any(r.market == SET_SCORE and r.subject == f"{MED} 0:2" for r in on.rungs)


def test_a_football_fixture_never_reads_them() -> None:
    out = _fetch(True, sport="football")
    assert all(r.market != SET_SCORE_NOT for r in out.rungs)


def test_rating_only_own_curve() -> None:
    assert SET_SCORE_NOT in SET_MARKETS <= RATING_ONLY_MARKETS <= OWN_CURVE_ONLY \
        | RATING_ONLY_MARKETS
    assert SET_SCORE_NOT in OWN_CURVE_ONLY
    assert curve_market({"market": SET_SCORE_NOT, "subject": f"{MED} 0:2",
                         "line": 0.5}) == SET_SCORE_NOT


# --- SHEET: 1 - the score's neighbour share, OVER only ---------------------------


def _rung(subject: str) -> PricedRung:
    return PricedRung(market=SET_SCORE_NOT, subject=subject, line=0.5,
                      over_odds=1.17, under_odds=4.4,
                      fetched_at_utc=FROZEN - timedelta(hours=1))


def test_sheet_prices_one_minus_the_score() -> None:
    probs = score_probs(POOL)
    assert probs is not None
    # Zverev is the home player of the scenario's fixture
    rows, skipped = set_market_rows(fixture("tennis", "77"), _rung(f"{ZVEREV} 0:2"),
                                    _rating(), {}, True)
    assert skipped == [] and len(rows) == 1
    r = sheet_row_json(rows[0])
    assert r["direction"] == "OVER"
    assert r["p_central"] == round(1 - probs["0:2"], 4)
    assert r["set_market_rule"] == epochs.TENNIS_SET_MARKETS
    assert r["set_complement_rule"] == epochs.TENNIS_SET_COMPLEMENTS
    assert any(n.startswith("TENNIS_SET_COMPLEMENTS") for n in r["notes"])
    # the away player's 0:2 is the home player's 2:0
    rows, _ = set_market_rows(fixture("tennis", "77"), _rung(f"{BUBLIK} 0:2"),
                              _rating(), {}, True)
    assert sheet_row_json(rows[0])["p_central"] == round(1 - probs["2:0"], 4)


def test_a_set_score_row_carries_no_complement_marker() -> None:
    rung = PricedRung(market=SET_SCORE, subject=f"{ZVEREV} 2:0", line=0.5,
                      over_odds=1.95, under_odds=None,
                      fetched_at_utc=FROZEN - timedelta(hours=1))
    rows, _ = set_market_rows(fixture("tennis", "77"), rung, _rating(), {}, True)
    assert "set_complement_rule" not in sheet_row_json(rows[0])


# --- CONFIDENCE ----------------------------------------------------------------


def test_own_curve_or_nothing() -> None:
    curve = {"0.800-0.825": {"n": 900, "realised": 0.83, "realised_lo95": 0.81}}
    cal = Calibration(pooled={"0.800-0.825": {"n": 9000, "realised": 0.8,
                                              "realised_lo95": 0.79}},
                      by_market={}, by_market_direction={"set_score_not|OVER": curve})
    assert cal.realised(SET_SCORE_NOT, 0.81, "tennis", "OVER") == (
        0.81, "market:set_score_not|OVER", 900)
    assert cal.realised(SET_SCORE_NOT, 0.81, "tennis", "OVER", "tennis_women") is None


# --- SETTLE ------------------------------------------------------------------------


@pytest.mark.parametrize("subject,value,outcome", [
    # Zverev (home) won 2:1: neither player lost 0:2
    (f"{ZVEREV} 0:2", 1.0, "WIN"),
    (f"{BUBLIK} 0:2", 1.0, "WIN"),
])
def test_settle_is_the_complement_of_the_score(
        subject: str, value: float, outcome: str) -> None:
    row = {"market": SET_SCORE_NOT, "subject": subject, "line": 0.5,
           "direction": "OVER"}
    assert _settle_set_market(row, EV, FX) == (value, outcome)


def test_settle_a_straight_sets_loss() -> None:
    ev = _event([6, 6], [3, 4])  # Zverev 2:0
    row = {"market": SET_SCORE_NOT, "subject": f"{BUBLIK} 0:2", "line": 0.5,
           "direction": "OVER"}
    assert _settle_set_market(row, ev, FX) == (0.0, "LOSS")
    assert _settle_set_market({**row, "subject": f"{ZVEREV} 0:2"}, ev, FX) == (
        1.0, "WIN")
    for score in ("2:0", "2:1", "1:2", "0:2"):
        for home in (True, False):
            assert set_value(SET_SCORE_NOT, home, score, ev) == \
                1.0 - float(set_value(SET_SCORE, home, score, ev))
    bo5 = _event([6, 6, 3, 6], [3, 4, 6, 2])
    assert set_value(SET_SCORE_NOT, True, "0:2", bo5) == "NOT_BEST_OF_THREE"


def test_regrade_grades_like_settle() -> None:
    from scripts.sofa.regrade_settled import grade_live

    row = {"market": SET_SCORE_NOT, "subject": f"{BUBLIK} 0:2", "line": 0.5,
           "direction": "OVER", "sport": "tennis"}
    got = grade_live(row, _event([6, 6], [3, 4]), FX, None, None)
    assert got == (0.0, "LOSS")
