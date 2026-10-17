"""Football "or" result markets, the underdog's European handicap and the DC
& goals pairs (bet.sofa.football_score_markets), behind
epochs.FOOTBALL_SCORE_MARKETS_FROM_UTC. Offline and fast. Evidence:
docs/sofa/evidence/football_score_markets_2026-10-16.md.

The Superbet names and prices are the real ones (unmapped_prices of
2026-10-15, TSG Hoffenheim - Beşiktaş JK; Superbet writes the short club
names "Hoffenheim" / "Besiktas" in the selections).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any

import numpy as np
import pytest

from bet.sofa import epochs
from bet.sofa import football_score_markets as fsm
from bet.sofa import offer as offer_mod
from bet.sofa.confidence import (
    OWN_CURVE_ONLY,
    Calibration,
    has_cross_league_unlinked_note,
    is_derived,
    quantity_family,
)
from bet.sofa.contracts import FixtureOffer, GapReason, PricedRung
from bet.sofa.football_result import ResultConfig, result_probs
from bet.sofa.metrics import score_market_value
from bet.sofa.samples import metrics_from_offer
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS
from scripts.sofa.run_settle import _settle_score_market
from scripts.sofa.run_sheet import score_market_rows, sheet_row_json
from tests.sofa.offer_mappable_scenarios import FROZEN, fixture
from tests.sofa.test_football_1x2_dnb import (
    AET_2_1,
    NORMAL_0_1,
    NORMAL_2_0,
    _event,
    _fixture_model,
    _forecast,
)

CFG = ResultConfig(nb_r=7.586, source="test")
PRE_KICKOFF = datetime(2026, 9, 22, tzinfo=UTC)
H, A = "TSG Hoffenheim", "Beşiktaş JK"


def _item(market: str, selection: str, price: float) -> dict[str, Any]:
    return {"marketName": market, "name": selection, "offerStateId": 1,
            "price": price, "status": "active"}


# --- the switch ---------------------------------------------------------------


def test_switch_reads_the_day_and_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    # moved by the operator into the built day 10-16 (07:46Z): 10-16 mixed
    at = datetime(2026, 10, 16, 7, 46, tzinfo=UTC)
    assert epochs.FOOTBALL_SCORE_MARKETS_FROM_UTC == at
    assert epochs.football_score_markets("2026-10-16", at)
    assert epochs.football_score_markets("2026-10-17", at + timedelta(hours=1))
    assert not epochs.football_score_markets("2026-10-15", at + timedelta(hours=1))
    assert not epochs.football_score_markets("2026-10-16", at - timedelta(seconds=1))
    monkeypatch.setattr(epochs, "FOOTBALL_SCORE_MARKETS_FROM_UTC", None)
    assert not epochs.football_score_markets("2027-01-01", at + timedelta(days=99))


# --- OFFER: the names -------------------------------------------------------------


@pytest.mark.parametrize("market,sel,want", [
    ("Mecz lub liczba goli (2.5)", "Hoffenheim lub poniżej 2.5",
     [("result_or_under", "1", 2.5, "OVER")]),
    ("Mecz lub liczba goli (2.5)", "remis lub powyżej 2.5",
     [("result_or_over", "X", 2.5, "OVER")]),
    ("Mecz lub liczba goli (0.5)", "Besiktas lub powyżej 0.5",
     [("result_or_over", "2", 0.5, "OVER")]),
    # the line in the name and in the selection must agree
    ("Mecz lub liczba goli (2.5)", "Hoffenheim lub poniżej 3.5", []),
    ("Mecz lub liczba goli (6.5)", "remis lub powyżej 6.5", []),
    ("Hoffenheim wygra lub poniżej X goli w meczu", "2.5 - Tak",
     [("result_or_under", "1", 2.5, "OVER")]),
    ("Hoffenheim wygra lub poniżej X goli w meczu", "2.5 - Nie",
     [("result_or_under", "1", 2.5, "UNDER")]),
    ("Remis lub powyżej X goli w meczu", "3.5 - Tak",
     [("result_or_over", "X", 3.5, "OVER")]),
    ("Besiktas wygra lub powyżej X goli w meczu", "1.5 - Nie",
     [("result_or_over", "2", 1.5, "UNDER")]),
    ("Obie drużyny strzelą gola lub powyżej 2.5 gola", "tak",
     [("btts_or_over", "", 2.5, "OVER")]),
    ("Obie drużyny strzelą gola lub powyżej 3.5 gola", "nie",
     [("btts_or_over", "", 3.5, "UNDER")]),
    ("Hoffenheim wygra lub obie drużyny strzelą gola", "Tak",
     [("result_or_btts", "1", 0.5, "OVER")]),
    ("Remis lub obie drużyny strzelą gola", "Nie",
     [("result_or_btts", "X", 0.5, "UNDER")]),
    ("Besiktas wygra lub którakolwiek drużyna zachowa czyste konto", "Tak",
     [("result_or_clean_sheet", "2", 0.5, "OVER")]),
    ("Remis lub którakolwiek drużyna zachowa czyste konto", "Tak",
     [("result_or_clean_sheet", "X", 0.5, "OVER")]),
    # Handicap: +L is the side's OVER, -L the other side's UNDER; +0.5 is the
    # double chance (read elsewhere) and is left out
    ("Handicap", "Besiktas (1.5)", [("result_handicap", "2", 1.5, "OVER")]),
    ("Handicap", "Hoffenheim (-1.5)", [("result_handicap", "2", 1.5, "UNDER")]),
    ("Handicap", "Hoffenheim (2.5)", [("result_handicap", "1", 2.5, "OVER")]),
    ("Handicap", "Besiktas (-2.5)", [("result_handicap", "1", 2.5, "UNDER")]),
    ("Handicap", "Besiktas (0.5)", []),
    ("Handicap", "Hoffenheim (-0.5)", []),
    ("Handicap 1X2", "Remis (0:1)", []),
    ("Strzały - Handicap", "Besiktas (3.5)", []),
    ("Podwójna szansa & liczba goli (2.5)", "12 & powyżej 2.5",
     [("dc_and_over", "12", 2.5, "OVER")]),
    ("Podwójna szansa & liczba goli (4.5)", "1X & poniżej 4.5",
     [("dc_and_under", "1X", 4.5, "OVER")]),
    # measured failing / never reaching 0.70: not read
    ("Podwójna szansa & liczba goli (2.5)", "1X & powyżej 2.5", []),
    ("Podwójna szansa & liczba goli (2.5)", "X2 & poniżej 2.5", []),
    ("Podwójna szansa & liczba goli (2.5)", "12 & poniżej 2.5", []),
    # halves and other questions are not these markets
    ("Mecz lub 1.połowa liczba goli (1.5)", "Hoffenheim lub poniżej 1.5", []),
    ("1. połowa lub mecz", "1 lub 1", []),
    ("Mecz & liczba goli (2.5)", "1 & powyżej 2.5", []),
    ("Zawodnik - strzeli gola lub zaliczy asystę", "Kramaric, Andrej", []),
    ("Przedział goli", "1-3", []),
    # a team that is neither side: never guessed
    ("Roma wygra lub obie drużyny strzelą gola", "Tak", []),
])
def test_classify_reads_the_superbet_names(
        market: str, sel: str, want: list[tuple[str, str, float, str]]) -> None:
    assert fsm.classify(market, sel, H, A) == want


def test_classify_needs_both_sides() -> None:
    assert fsm.classify("Remis lub obie drużyny strzelą gola", "Tak", None, None) == [
        ("result_or_btts", "X", 0.5, "OVER")]
    assert fsm.classify("Handicap", "Besiktas (1.5)", None, None) == []


def _fetch(odds: list[dict[str, Any]], on: bool, sport: str = "football",
           ) -> FixtureOffer:
    fx = fixture(sport, "1")
    payload = {"eventId": "1", "matchName": f"{H}·{A}", "odds": odds}

    class C:
        def event_odds(self, _eid: str) -> dict[str, Any]:
            return payload

    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        out = offer_mod.OfferFetcher(
            C(), football_score_markets=on, football_1x2_dnb=True,
            football_result=True).fetch_offers([fx])
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return out[0]


ODDS = [
    _item("Mecz lub liczba goli (2.5)", "Hoffenheim lub poniżej 2.5", 1.32),
    _item("Hoffenheim wygra lub poniżej X goli w meczu", "2.5 - Tak", 1.33),
    _item("Hoffenheim wygra lub poniżej X goli w meczu", "2.5 - Nie", 3.05),
    _item("Remis lub powyżej X goli w meczu", "2.5 - Tak", 1.2),
    _item("Mecz lub liczba goli (2.5)", "remis lub powyżej 2.5", 1.21),
    _item("Remis lub powyżej X goli w meczu", "2.5 - Nie", 3.9),
    _item("Handicap", "Besiktas (1.5)", 1.32),
    _item("Handicap", "Hoffenheim (-1.5)", 3.25),
    _item("Handicap", "Besiktas (0.5)", 1.85),
    _item("Podwójna szansa & liczba goli (2.5)", "12 & powyżej 2.5", 1.66),
    _item("Podwójna szansa & liczba goli (2.5)", "X2 & powyżej 2.5", 2.92),
    _item("Obie drużyny strzelą gola lub powyżej 2.5 gola", "nie", 3.55),
    _item("Mecz", "1", 1.9),
]


def test_switch_off_offer_reads_none_of_them() -> None:
    off = _fetch(ODDS, on=False)
    assert all(r.market not in fsm.MARKETS for r in off.rungs)
    assert "Mecz lub liczba goli (2.5)" in off.unmapped_markets
    assert "Handicap" in off.unmapped_markets


def test_switch_on_offer_builds_two_sided_rungs_without_collisions() -> None:
    off, on = _fetch(ODDS, on=False), _fetch(ODDS, on=True)
    new = {(r.market, r.subject, r.line): r for r in on.rungs if r.market in fsm.MARKETS}
    assert set(new) == {("result_or_under", "1", 2.5), ("result_or_over", "X", 2.5),
                        ("result_handicap", "2", 1.5), ("dc_and_over", "12", 2.5)}
    # the same bet in two Superbet markets: the lower price, no collision
    assert (new[("result_or_under", "1", 2.5)].over_odds,
            new[("result_or_under", "1", 2.5)].under_odds) == (1.32, 3.05)
    assert (new[("result_or_over", "X", 2.5)].over_odds,
            new[("result_or_over", "X", 2.5)].under_odds) == (1.2, 3.9)
    assert (new[("result_handicap", "2", 1.5)].over_odds,
            new[("result_handicap", "2", 1.5)].under_odds) == (1.32, 3.25)
    assert new[("dc_and_over", "12", 2.5)].under_odds is None
    assert on.price_collisions == off.price_collisions == []
    # an UNDER alone (BTTS-or-over "nie" with no "tak") is no offer
    assert ("btts_or_over", "", 2.5) not in new
    # every other rung unchanged
    assert [r for r in on.rungs if r.market not in fsm.MARKETS] == off.rungs
    assert set(off.unmapped_markets) - set(on.unmapped_markets) == {
        "Mecz lub liczba goli (2.5)", "Hoffenheim wygra lub poniżej X goli w meczu",
        "Remis lub powyżej X goli w meczu",
        "Obie drużyny strzelą gola lub powyżej 2.5 gola"}
    # a market with a selection not read (+0.5, X2 & over) stays listed
    assert {"Handicap", "Podwójna szansa & liczba goli (2.5)"} <= set(
        on.unmapped_markets)


def test_a_tennis_fixture_never_reads_them() -> None:
    out = _fetch([_item("Handicap", "Besiktas (1.5)", 1.3)], on=True, sport="tennis")
    assert all(r.market not in fsm.MARKETS for r in out.rungs)


def test_rating_only_and_never_derived() -> None:
    assert fsm.MARKETS <= RATING_ONLY_MARKETS
    assert fsm.MARKETS <= OWN_CURVE_ONLY
    for m in fsm.MARKETS:
        # a "handicap_" / "most_" / "both_over_" prefix would make it a derived
        # joint, whose curves are not read (DERIVED_CURVES off)
        assert not is_derived(m)
        assert quantity_family(m) == "goals"
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market="result_or_over", subject="X", line=2.5,
                          over_odds=1.2, under_odds=3.9, fetched_at_utc=FROZEN)])
    assert metrics_from_offer(offer) == set()


# --- the price ------------------------------------------------------------------


def _brute(market: str, subject: str, line: float, lh: float, la: float) -> float:
    grid = fsm.score_grid(lh, la, CFG.nb_r)
    total = 0.0
    for i, j in product(range(grid.shape[0]), repeat=2):
        res = "1" if i > j else ("X" if i == j else "2")
        btts = i > 0 and j > 0
        hit = {
            "result_or_over": res == subject or i + j > line,
            "result_or_under": res == subject or i + j < line,
            "btts_or_over": btts or i + j > line,
            "result_or_btts": res == subject or btts,
            "result_or_clean_sheet": res == subject or not btts,
            "result_handicap": (i + line > j) if subject == "1" else (j + line > i),
            "dc_and_over": i != j and i + j > line,
            "dc_and_under": i >= j and i + j < line,
        }[market]
        total += grid[i, j] if hit else 0.0
    return total


RUNGS = [("result_or_over", "1", 2.5), ("result_or_over", "X", 3.5),
         ("result_or_under", "2", 1.5), ("btts_or_over", "", 2.5),
         ("result_or_btts", "X", 0.5), ("result_or_clean_sheet", "1", 0.5),
         ("result_handicap", "2", 1.5), ("result_handicap", "1", 3.5),
         ("dc_and_over", "12", 2.5), ("dc_and_under", "1X", 3.5)]


@pytest.mark.parametrize("lh,la", [(1.4, 1.1), (0.6, 2.2), (2.5, 0.4)])
@pytest.mark.parametrize("rung", RUNGS)
def test_row_p_is_the_events_mass_on_the_grid(
        rung: tuple[str, str, float], lh: float, la: float) -> None:
    grid = fsm.score_grid(lh, la, CFG.nb_r)
    assert fsm.row_p(*rung, grid) == pytest.approx(_brute(*rung, lh, la))


def test_identities_with_the_double_chance_grid() -> None:
    lh, la = 1.6, 0.9
    grid = fsm.score_grid(lh, la, CFG.nb_r)
    pr = result_probs(lh, la, CFG.nb_r)
    assert grid.sum() == pytest.approx(1.0)
    # "1 or over -1" is the home win alone at line < 0 - check the parts
    i = np.arange(grid.shape[0])[:, None]
    j = np.arange(grid.shape[0])[None, :]
    assert float(grid[i > j].sum()) == pytest.approx(pr["1"], abs=1e-9)
    # the +1.5 handicap of the away side = not (home wins by 2 or more)
    p_away_plus = fsm.row_p("result_handicap", "2", 1.5, grid)
    assert p_away_plus == pytest.approx(1 - float(grid[(i - j) >= 2].sum()))
    # "X or over 0.5" misses only 0:0's complement... it misses nothing but
    # a non-draw with 0 goals, which cannot exist: p = 1
    assert fsm.row_p("result_or_over", "X", 0.5, grid) == pytest.approx(1.0)


def test_unknown_rungs_are_refused() -> None:
    for bad in [("result_or_over", "12", 2.5), ("result_handicap", "X", 1.5),
                ("result_handicap", "1", 0.5), ("dc_and_over", "1X", 2.5),
                ("btts_or_over", "1", 2.5), ("result_or_btts", "1", 2.5)]:
        assert not fsm.valid_rung(*bad)
        with pytest.raises(ValueError):
            fsm.event_mask(*bad)


# --- SHEET ----------------------------------------------------------------------


def _rung(market: str, subject: str, line: float, over: float = 1.3,
          under: float | None = 3.2) -> PricedRung:
    return PricedRung(market=market, subject=subject, line=line, over_odds=over,
                      under_odds=under, fetched_at_utc=PRE_KICKOFF)


def test_sheet_prices_the_over_from_the_pure_rating() -> None:
    fc = _forecast()
    home, away = fc.centre("goals_for", "side_a"), fc.centre("goals_for", "side_b")
    assert home is not None and away is not None
    grid = fsm.score_grid(home[0], away[0], CFG.nb_r)
    for market, subject, line in RUNGS:
        rows, skipped = score_market_rows(
            _fixture_model(), _rung(market, subject, line), fc, CFG, {}, True)
        want = fsm.row_p(market, subject, line, grid)
        if not 0.05 <= want <= 0.95:
            assert rows == [] and skipped[0][1] == GapReason.OUTSIDE_MODEL_RESOLUTION
            continue
        assert len(rows) == 1 and skipped == []
        r = sheet_row_json(rows[0])
        assert r["direction"] == "OVER"
        assert r["p_central"] == round(want, 4)
        assert r["score_market_rule"] == epochs.FOOTBALL_SCORE_MARKETS
        assert r["sample_size"] == 0 and r["bar_reason"] == "rating_only"
        assert r["forecast_source"] == "football_rating"
        assert any(n.startswith(fsm.NOTE) for n in r["notes"])
        assert any(n.startswith("UNFITTED_CONSTANTS") and "FOOTBALL_RESULT_NB_R" in n
                   for n in r["notes"])


def test_sheet_unlinked_unrated_and_unknown() -> None:
    fc = _forecast(away_league=5)
    out, _ = score_market_rows(_fixture_model(), _rung("result_or_over", "1", 2.5),
                               fc, CFG, {}, True)
    assert len(out) == 1 and has_cross_league_unlinked_note(out[0].notes)
    out, skipped = score_market_rows(_fixture_model(),
                                     _rung("result_or_over", "1", 2.5), None, CFG,
                                     {}, True)
    assert out == [] and skipped[0][1] == GapReason.NOT_RATED
    out, skipped = score_market_rows(_fixture_model(),
                                     _rung("result_or_over", "12", 2.5), _forecast(),
                                     CFG, {}, True)
    assert out == [] and skipped[0][1] == GapReason.NO_MATCHING_EVENT


def test_switch_off_sheet_has_no_such_row() -> None:
    from tests.sofa.test_football_1x2_dnb import _sheet

    off = _sheet(None, _forecast())
    assert all(r["market"] not in fsm.MARKETS for r in off)
    assert all("score_market_rule" not in r for r in off)


# --- CONFIDENCE -------------------------------------------------------------------


def test_own_curve_or_nothing() -> None:
    curve = {"0.800-0.825": {"n": 900, "realised": 0.80, "realised_lo95": 0.78}}
    cal = Calibration(pooled={"0.800-0.825": {"n": 9000, "realised": 0.81,
                                              "realised_lo95": 0.80}},
                      by_market={},
                      by_market_direction={"result_or_over|OVER": curve})
    assert cal.realised("result_or_over", 0.81, "football", "OVER") == (
        0.78, "market:result_or_over|OVER", 900)
    # no curve of its own: the pool never stands in
    assert cal.realised("result_or_under", 0.81, "football", "OVER") is None
    assert cal.realised("result_or_over", 0.81, "football", "UNDER") is None


# --- SETTLE: the 90-minute score, the indicator graded at 0.5 ----------------------


def _row(market: str, subject: str, line: float, direction: str = "OVER",
         ) -> dict[str, Any]:
    return {"market": market, "subject": subject, "line": line,
            "direction": direction, "sport": "football"}


NORMAL_1_1 = _event(100, {"current": 1, "period1": 1, "period2": 0, "normaltime": 1},
                    {"current": 1, "period1": 0, "period2": 1, "normaltime": 1})


def test_settle_grades_the_event_never_the_goals_line() -> None:
    # X or over 2.5 on 1-1: the draw - a WIN although 1 < 2.5
    assert _settle_score_market(_row("result_or_over", "X", 2.5), NORMAL_1_1) == (
        1.0, "WIN")
    # 1 or under 1.5 on 2-0: the home win - a WIN although 1.0 < 1.5 would read
    # it as "under"
    assert _settle_score_market(_row("result_or_under", "1", 1.5), NORMAL_2_0) == (
        1.0, "WIN")
    # 2 or over 2.5 on 2-0: neither
    assert _settle_score_market(_row("result_or_over", "2", 2.5), NORMAL_2_0) == (
        0.0, "LOSS")
    # the UNDER of a rung (never priced, graded consistently)
    assert _settle_score_market(_row("result_or_over", "2", 2.5, "UNDER"),
                                NORMAL_2_0) == (0.0, "WIN")
    assert _settle_score_market(_row("btts_or_over", "", 2.5), NORMAL_1_1) == (
        1.0, "WIN")
    assert _settle_score_market(_row("result_or_btts", "2", 0.5), NORMAL_2_0) == (
        0.0, "LOSS")
    assert _settle_score_market(_row("result_or_clean_sheet", "2", 0.5),
                                NORMAL_2_0) == (1.0, "WIN")
    # +1.5 of the away side on 2-0: lost by exactly two
    assert _settle_score_market(_row("result_handicap", "2", 1.5), NORMAL_2_0) == (
        0.0, "LOSS")
    assert _settle_score_market(_row("result_handicap", "2", 2.5), NORMAL_2_0) == (
        1.0, "WIN")
    assert _settle_score_market(_row("result_handicap", "1", 1.5), NORMAL_0_1) == (
        1.0, "WIN")
    assert _settle_score_market(_row("dc_and_over", "12", 1.5), NORMAL_2_0) == (
        1.0, "WIN")
    assert _settle_score_market(_row("dc_and_under", "1X", 2.5), NORMAL_0_1) == (
        0.0, "LOSS")


def test_settle_reads_regular_time_and_refuses_the_unreadable() -> None:
    # 2-1 after extra time, 1-1 at 90 minutes: the draw
    assert _settle_score_market(_row("result_or_under", "X", 1.5), AET_2_1) == (
        1.0, "WIN")
    assert _settle_score_market(_row("result_or_under", "1", 1.5), AET_2_1) == (
        0.0, "LOSS")
    assert score_market_value("result_or_over", "12", 2.5, NORMAL_2_0) == \
        GapReason.STAT_KEY_ABSENT
    assert _settle_score_market(_row("result_or_over", "1", 2.5),
                                _event(100, {}, {})) == \
        "result_or_over:STAT_KEY_ABSENT"


def test_outcome_agrees_with_the_mask() -> None:
    for market, subject, line in RUNGS:
        mask = fsm.event_mask(market, subject, line)
        for i, j in product(range(6), repeat=2):
            assert fsm.outcome(market, subject, line, i, j) == int(mask[i, j])
    # a score past the grid
    assert fsm.outcome("result_or_under", "1", 2.5, 14, 0) == 1


def test_regrade_grades_like_settle() -> None:
    from scripts.sofa.regrade_settled import grade_live

    assert grade_live(_row("result_or_over", "X", 2.5), NORMAL_1_1,
                      None, None, None) == (1.0, "WIN")
    assert grade_live(_row("result_handicap", "2", 1.5), NORMAL_2_0,
                      None, None, None) == (0.0, "LOSS")


# --- the curve is per slice; the early phase its own class ---------------------------


def test_curve_market_is_the_slice() -> None:
    from bet.sofa.confidence import curve_market

    row = {"market": "result_or_over", "subject": "X", "line": 2.5}
    assert curve_market(row) == "result_or_over@X@2.5"
    assert curve_market({"market": "btts_or_over", "subject": "", "line": 3.5}) == \
        "btts_or_over@-@3.5"
    assert curve_market({"market": "goals_total", "subject": "", "line": 2.5}) == \
        "goals_total"
    assert fsm.is_curve_slice("result_or_over@X@2.5")
    assert not fsm.is_curve_slice("goals_total")


def test_a_slice_without_its_curve_never_reads_a_pool_or_another_slice() -> None:
    curve = {"0.800-0.825": {"n": 900, "realised": 0.80, "realised_lo95": 0.78}}
    pool = {"0.800-0.825": {"n": 9000, "realised": 0.81, "realised_lo95": 0.80}}
    cal = Calibration(pooled=pool, by_market={"result_or_over": pool},
                      by_market_direction={"result_or_over@X@2.5|OVER": curve,
                                           "result_or_over|OVER": pool},
                      pooled_by_sport={"football": pool})
    assert cal.realised("result_or_over@X@2.5", 0.81, "football", "OVER") == (
        0.78, "market:result_or_over@X@2.5|OVER", 900)
    assert cal.realised("result_or_over@X@4.5", 0.81, "football", "OVER") is None
    assert cal.realised("result_or_over@X@2.5", 0.81, "football", "UNDER") is None


def test_leg_class_reads_season_early_only_for_marked_men_rows() -> None:
    from bet.sofa.season_phase import PHASE_EARLY, PHASE_MID

    row = {"market": "result_or_over", "score_market_rule": "r",
           "result_phase": PHASE_EARLY}
    assert fsm.leg_class(row, None) == fsm.CLASS_SEASON_EARLY
    assert fsm.leg_class(row, "women") == "women"
    assert fsm.leg_class({**row, "result_phase": PHASE_MID}, None) is None
    assert fsm.leg_class({**row, "score_market_rule": None}, None) is None
    assert fsm.leg_class({**row, "market": "goals_total"}, None) is None


def test_sheet_row_carries_the_phase() -> None:
    from bet.sofa.season_phase import PHASE_EARLY

    rows, _ = score_market_rows(_fixture_model(), _rung("result_or_over", "1", 2.5),
                                _forecast(), CFG, {}, True, PHASE_EARLY)
    assert sheet_row_json(rows[0])["result_phase"] == PHASE_EARLY
    rows, _ = score_market_rows(_fixture_model(), _rung("result_or_over", "1", 2.5),
                                _forecast(), CFG, {}, True)
    assert "result_phase" not in sheet_row_json(rows[0])


# --- every OFFER reader builds its fetcher from one list of the day's switches ----


def test_day_flags_cover_every_offerfetcher_switch(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import inspect
    from pathlib import Path

    params = {n for n, p in inspect.signature(offer_mod.OfferFetcher).parameters.items()
              if p.annotation in (bool, "bool")}
    monkeypatch.setenv("SOFA_NOW", "2026-10-17T06:00:00Z")  # the build clock
    flags = offer_mod.day_flags("2026-10-17")
    assert set(flags) == params - {"record_unmapped"}
    assert flags["football_score_markets"] and flags["tennis_set_complements"]
    assert not offer_mod.day_flags("2026-10-15")["football_score_markets"]
    repo = Path(__file__).resolve().parents[2]
    for reader in ("scripts/sofa/run_offer.py", "scripts/sofa/capture_closing.py",
                   ".claude/agents/sofa-verifier.md",
                   ".claude/agents/sofa-market-scout.md"):
        assert "**day_flags(" in (repo / reader).read_text(), reader


def test_the_closing_capture_finds_a_score_market_leg() -> None:
    from scripts.sofa.capture_closing import close_record

    leg = {"market": "result_or_over", "subject": "X", "line": 2.5,
           "direction": "OVER", "offered_odds": 1.21, "sofascore_event_id": 1,
           "kickoff_utc": "2026-10-17T18:00:00Z"}
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED", unmapped_markets=[],
                         rungs=[_rung("result_or_over", "X", 2.5, 1.19, 3.9)])
    rec = close_record("official", leg, offer, datetime(2026, 10, 17, 17, 0, tzinfo=UTC))
    assert rec is not None and rec["odds_close"] == 1.19 and rec["partner_close"] == 3.9


def test_line_evidence_reads_the_slice_curve_and_keys_the_market(
        tmp_path: Any) -> None:
    """fit_line_evidence measures a settled score-market line against the
    curve CONFIDENCE read (the slice's), under the row's market key."""
    import json as _json

    from scripts.sofa.fit_line_evidence import sheet_rows

    day = tmp_path / "2026-10-17"
    day.mkdir()
    (day / "02_fixtures.json").write_text(_json.dumps([
        {"sofascore_event_id": 1, "superbet_event_ids": ["9"],
         "competition_name": "Liga", "competition_id": 3}]))
    (day / "07_settled.json").write_text(_json.dumps([
        {"sofascore_event_id": 1, "sport": "football", "market": "result_or_over",
         "subject": "X", "line": 2.5, "direction": "OVER", "p_central": 0.81,
         "offered_odds": 1.2, "outcome": "WIN"}]))
    curve = {"0.800-0.825": {"n": 900, "realised": 0.80, "realised_lo95": 0.78}}
    cal = Calibration(pooled={}, by_market={},
                      by_market_direction={"result_or_over@X@2.5|OVER": curve})
    rows = list(sheet_rows(tmp_path, ["2026-10-17"], cal))
    assert len(rows) == 1
    assert rows[0]["key"] == "result_or_over|OVER"
    assert rows[0]["base"] == 0.78


def test_confidence_reads_the_installed_slice_curves(
        tmp_path: Any, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """The whole CONFIDENCE stage on one fixture, with the installed curves:
    a slice with a curve prints from it (one-sided rungs included), a
    refused slice (result_or_over 1 @ 5.5 overstated on the holdout) reads
    no pool - NO_LINE_EVIDENCE - and an early-phase row reads season_early."""
    import json as _json
    import sys as _sys

    from scripts.sofa import run_confidence
    from tests.sofa.test_locked_print import _fixture as base_fixture

    day = "2026-10-17"
    t0 = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
    ko = "2026-10-17T18:00:00Z"
    run = tmp_path / day
    run.mkdir()

    def z(t: datetime) -> str:
        return t.isoformat().replace("+00:00", "Z")

    fx = {**base_fixture(1), "kickoff_utc": ko, "superbet_kickoff_utc": ko}
    (run / "02_fixtures.json").write_text(_json.dumps([fx]))
    (run / "03_samples.json").write_text(_json.dumps([{
        "sofascore_event_id": 1, "readiness": "READY", "gaps": [],
        "players": {}, "metrics": {}}]))

    def row(market: str, subject: str, line: float, p: float, odds: float,
            phase: str | None = None) -> dict[str, Any]:
        return {
            "sofascore_event_id": 1, "sport": "football", "market": market,
            "subject": subject, "line": line, "direction": "OVER",
            "sample_size": 0, "sample_mean": 0.0, "sample_sd": 0.0,
            "centre": p, "p_central": p, "market_p": None, "ladder_centre": None,
            "ladder_sigma": None, "p_bar": p, "bar_reason": "rating_only",
            "required_odds": 1.1, "offered_odds": odds, "edge": 0.0,
            "surplus": 0.0, "verdict": "LEAN", "notes": [f"{fsm.NOTE}: test"],
            "epoch": "stats_only", "forecast_p": p,
            "forecast_source": "football_rating",
            "score_market_rule": epochs.FOOTBALL_SCORE_MARKETS,
            **({"result_phase": phase} if phase else {})}

    rows = [row("result_or_over", "X", 2.5, 0.86, 1.25),
            row("result_or_over", "1", 5.5, 0.86, 1.25),
            row("result_or_under", "1", 3.5, 0.84, 1.2, phase="early"),
            # the same slice at 1.30-1.60: football's pooled price-band cap
            # (no own lines yet) reads 0.69 there - below the floor
            row("result_or_under", "1", 2.5, 0.84, 1.35, phase="early")]
    (run / "05_sheet.json").write_text(_json.dumps(rows))
    (run / "vetoes.json").write_text("[]")
    fetched = z(t0 - timedelta(minutes=1))
    (run / "04_offer.json").write_text(_json.dumps([{
        "sofascore_event_id": 1, "status": "PRICED", "unmapped_markets": [],
        "price_collisions": [],
        "rungs": [
            {"market": "result_or_over", "subject": "X", "line": 2.5,
             "over_odds": 1.25, "under_odds": None, "fetched_at_utc": fetched},
            {"market": "result_or_over", "subject": "1", "line": 5.5,
             "over_odds": 1.25, "under_odds": 4.0, "fetched_at_utc": fetched},
            {"market": "result_or_under", "subject": "1", "line": 3.5,
             "over_odds": 1.2, "under_odds": 4.5, "fetched_at_utc": fetched},
            {"market": "result_or_under", "subject": "1", "line": 2.5,
             "over_odds": 1.35, "under_odds": 3.0, "fetched_at_utc": fetched}]}]))
    monkeypatch.setenv("SOFA_NOW", z(t0))
    monkeypatch.setattr(_sys, "argv", [
        "run_confidence.py", "--date", day, "--runs-dir", str(tmp_path)])
    # The live evidence file is refitted every morning: once the score
    # markets' own lines settle (from 10-17) their keys exist and the refused
    # slice reads them. This test pins the state it describes - no own lines
    # yet - by dropping the score markets' keys from the loaded evidence.
    real_load = run_confidence.LineEvidence.load

    def load_without_score_keys(*a: Any, **k: Any) -> Any:
        ev = real_load(*a, **k)
        for sport_keys in (ev.doc.get("keys") or {}).values():
            for key in [x for x in sport_keys
                        if x.split(":")[-1].split("|")[0] in fsm.MARKETS]:
                del sport_keys[key]
        return ev

    monkeypatch.setattr(run_confidence.LineEvidence, "load",
                        staticmethod(load_without_score_keys))
    assert run_confidence.main() == 0
    summary = _json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    doc = _json.loads((run / "08_confidence.json").read_text())
    assert summary["metrics"]["refused"] == {"NO_LINE_EVIDENCE": 1,
                                             "BELOW_CONFIDENCE_FLOOR": 1}
    legs = {(leg["market"], leg["subject"], leg["line"]): leg for leg in doc["singles"]}
    assert set(legs) == {("result_or_over", "X", 2.5), ("result_or_under", "1", 3.5)}
    x = legs[("result_or_over", "X", 2.5)]
    assert x["calibrated_on"].startswith("market:result_or_over@X@2.5|OVER")
    assert x["one_sided_market"] is True and x["overround"] is None
    early = legs[("result_or_under", "1", 3.5)]
    assert early["calibrated_on"].startswith(
        "season_early:market:result_or_under@1@3.5|OVER")
    assert early["overround"] is not None


@pytest.mark.parametrize("market,subject,line,want", [
    ("result_or_over", "X", 2.5, "Mecz lub liczba goli: remis lub powyżej 2.5 (Tak)"),
    ("result_or_under", "1", 3.5,
     "Mecz lub liczba goli: Hoffenheim lub poniżej 3.5 (Tak)"),
    ("btts_or_over", "", 2.5, "Obie drużyny strzelą gola lub powyżej 2.5 gola (Tak)"),
    ("result_or_btts", "2", 0.5, "Besiktas wygra lub obie drużyny strzelą gola (Tak)"),
    ("result_or_btts", "X", 0.5, "remis lub obie drużyny strzelą gola (Tak)"),
    ("result_or_clean_sheet", "1", 0.5,
     "Hoffenheim wygra lub którakolwiek drużyna zachowa czyste konto (Tak)"),
    ("result_handicap", "2", 1.5, "Handicap: Besiktas (+1.5)"),
    ("dc_and_over", "12", 2.5, "Podwójna szansa & liczba goli: 12 & powyżej 2.5"),
    ("dc_and_under", "1X", 4.5, "Podwójna szansa & liczba goli: 1X & poniżej 4.5"),
    ("set_score_not", "Daniil Medvedev 0:2", 0.5, "Daniil Medvedev wygra seta (Tak)"),
    ("goals_total", "", 2.5, None),
])
def test_the_coupon_names_the_leg_in_superbets_words(
        market: str, subject: str, line: float, want: str | None) -> None:
    leg = {"market": market, "subject": subject, "line": line,
           "match": "Hoffenheim - Besiktas"}
    assert fsm.display_market(leg) == want


# --- the rebuild of the mixed day 10-16 ------------------------------------------


def _rebuild_state(**kw: Any) -> Any:
    from bet.sofa import rebuild_plan as rp

    now = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    base: dict[str, Any] = dict(
        offer_fixtures=2, open_fixtures=2,
        oldest_open_rung=now - timedelta(minutes=5),
        newest_rung=now - timedelta(minutes=5),
        offer_has_football=True, offer_has_tennis=True,
        offer_has_score=False, sheet_has_score=False,
        offer_has_set_not=False, sheet_has_set_not=False)
    base.update(kw)
    return rp.DayState("2026-10-16", now, timedelta(minutes=45), **base)


def test_rebuild_of_the_built_day_rereads_offer_and_sheet_once_on(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The switch moved into 10-16 (07:46Z) after OFFER / SHEET read the day:
    the plain rebuild re-reads OFFER (a fresh price would not trigger it) and
    re-runs SHEET, before CONFIDENCE - no step by hand."""
    from bet.sofa import rebuild_plan as rp

    on = rp.build_plan(_rebuild_state()).names()
    assert "OFFER" in on and "SHEET" in on
    assert on.index("OFFER") < on.index("SHEET") < on.index("CONFIDENCE")
    # a tennis-only gap alone re-reads too
    tennis = rp.build_plan(_rebuild_state(
        offer_has_score=True, sheet_has_score=True)).names()
    assert "OFFER" in tennis and "SHEET" in tennis
    # the offer already carries the rungs, the sheet not: SHEET only
    sheet_only = rp.build_plan(_rebuild_state(
        offer_has_score=True, offer_has_set_not=True)).names()
    assert "OFFER" not in sheet_only and "SHEET" in sheet_only
    # both carry them: nothing re-runs
    done = rp.build_plan(_rebuild_state(
        offer_has_score=True, sheet_has_score=True,
        offer_has_set_not=True, sheet_has_set_not=True)).names()
    assert not {"OFFER", "SHEET"} & set(done)
    # switches off: nothing re-runs either
    monkeypatch.setattr(epochs, "FOOTBALL_SCORE_MARKETS_FROM_UTC", None)
    monkeypatch.setattr(epochs, "TENNIS_SET_COMPLEMENTS_FROM_UTC", None)
    off = rp.build_plan(_rebuild_state()).names()
    assert not {"OFFER", "SHEET"} & set(off)


def test_rebuild_before_the_switch_clock_reads_nothing_new() -> None:
    from bet.sofa import rebuild_plan as rp

    early = _rebuild_state()
    seven = datetime(2026, 10, 16, 7, 0, tzinfo=UTC)
    early = rp.DayState(**{**early.__dict__, "now": seven,
                           "oldest_open_rung": seven - timedelta(minutes=5)})
    assert not {"OFFER", "SHEET"} & set(rp.build_plan(early).names())


def test_rebuild_observes_the_rungs_and_rows_on_disk(tmp_path: Any) -> None:
    import json

    from bet.sofa import rebuild_plan as rp

    day = tmp_path / "2026-10-16"
    day.mkdir()
    fx = [{"sofascore_event_id": 1, "sport": "football",
           "kickoff_utc": "2026-10-16T18:00:00Z"},
          {"sofascore_event_id": 2, "sport": "tennis",
           "kickoff_utc": "2026-10-16T18:00:00Z"}]
    rung = {"fetched_at_utc": "2026-10-16T08:55:00Z", "market": "goals_total"}
    offers = [{"sofascore_event_id": 1, "rungs": [rung]},
              {"sofascore_event_id": 2, "rungs": [{**rung, "market": "games_total"}]}]
    (day / "02_fixtures.json").write_text(json.dumps(fx))
    (day / "04_offer.json").write_text(json.dumps(offers))
    (day / "05_sheet.json").write_text(json.dumps([{"market": "goals_total"}]))
    now = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    st = rp.observe(str(tmp_path), "2026-10-16", now, timedelta(minutes=45))
    assert st.offer_has_football and st.offer_has_tennis
    assert not (st.offer_has_score or st.sheet_has_score
                or st.offer_has_set_not or st.sheet_has_set_not)
    offers[0]["rungs"].append({**rung, "market": "result_or_over"})
    offers[1]["rungs"].append({**rung, "market": "set_score_not"})
    (day / "04_offer.json").write_text(json.dumps(offers))
    (day / "05_sheet.json").write_text(json.dumps(
        [{"market": "result_handicap"}, {"market": "set_score_not"}]))
    st = rp.observe(str(tmp_path), "2026-10-16", now, timedelta(minutes=45))
    assert st.offer_has_score and st.sheet_has_score
    assert st.offer_has_set_not and st.sheet_has_set_not
