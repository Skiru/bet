"""Audit 2026-10-13 D2: the tennis match winner from the as-of rating, behind
epochs.TENNIS_MATCH_WINNER_FROM_UTC. Offline and fast. Evidence:
docs/sofa/evidence/tennis_match_winner_2026-10-13.md.

The Superbet shape is the real one (tests/sofa/golden/offer_mappable_items.json,
Alexander Zverev - Alexander Bublik, fetched 2026-10-12): market "Zwycięzca",
selections "1" @ 1.34 and "2" @ 3.05.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import offer as offer_mod
from bet.sofa import rebuild_plan as rp
from bet.sofa.confidence import (
    CLASS_TENNIS_WOMEN,
    Calibration,
    overround,
)
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.metrics import extract_metric
from bet.sofa.offer import classify_odd
from bet.sofa.samples import metrics_from_offer
from bet.sofa.settle import REFUND_REASONS
from bet.sofa.settle import settle as settle_value
from bet.sofa.tennis_rating import MatchForecast
from bet.sofa.tennis_winner import (
    MATCH_WON_FOR,
    RATING_ONLY_MARKETS,
    classify_winner,
    winner_p,
)
from scripts.sofa.fit_tennis_winner_curve import (
    fit_curve,
    holdout_calibration,
    merge,
)
from scripts.sofa.run_settle import unfinished_reason
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.offer_mappable_scenarios import (
    FROZEN,
    GOLDEN_DIR,
    _Client,
    dumps,
    fixture,
    offer_dump,
    payloads,
)

ZVEREV, BUBLIK = "Alexander Zverev", "Alexander Bublik"
NAMES = (ZVEREV, BUBLIK)


def _winner_item(selection: str, price: float) -> dict[str, Any]:
    return {"marketName": "Zwycięzca", "name": selection, "offerStateId": 1,
            "price": price, "status": "active"}


# --- the switch ---------------------------------------------------------------


def test_switch_is_off_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assert epochs.TENNIS_MATCH_WINNER_FROM_UTC is None
    late = datetime(2027, 1, 1, tzinfo=UTC)
    assert not epochs.tennis_match_winner("2027-01-01", late)
    monkeypatch.setattr(epochs, "TENNIS_MATCH_WINNER_FROM_UTC",
                        datetime(2026, 10, 14, tzinfo=UTC))
    assert epochs.tennis_match_winner(
        "2026-10-14", datetime(2026, 10, 14, 1, tzinfo=UTC))
    assert not epochs.tennis_match_winner("2026-10-13", late)
    assert not epochs.tennis_match_winner(
        "2026-10-14", datetime(2026, 10, 13, 23, tzinfo=UTC))


# --- mapping ------------------------------------------------------------------


def test_classify_winner_reads_the_two_selections_as_one_rung() -> None:
    one = classify_winner("Zwycięzca", "1", NAMES)
    two = classify_winner("Zwycięzca", "2", NAMES)
    assert one == (MATCH_WON_FOR, ZVEREV, 0.5, "OVER")
    assert two == (MATCH_WON_FOR, ZVEREV, 0.5, "UNDER")


@pytest.mark.parametrize("market,selection,names", [
    ("Zwycięzca & każdy z graczy wygra seta", "1", NAMES),
    ("Zwycięzcy setów", "1", NAMES),
    ("X. set - zwycięzca", "1. set - Alexander Zverev", NAMES),
    ("Zwycięzca", "X", NAMES),
    ("Zwycięzca", "1", (ZVEREV,)),  # no second name: the subject is unknown
    ("Zwycięzca", "1", ()),
])
def test_classify_winner_refuses_every_other_shape(
        market: str, selection: str, names: tuple[str, ...]) -> None:
    assert classify_winner(market, selection, names) is None


def test_classify_odd_off_keeps_the_winner_unmapped() -> None:
    item = _winner_item("1", 1.34)
    assert classify_odd(item, (), False, NAMES) == (None, "Zwycięzca")
    assert classify_odd(item, (), True, NAMES) == (None, "Zwycięzca")
    assert classify_odd(item, (), False, NAMES, True) == (
        (MATCH_WON_FOR, ZVEREV, 0.5, "OVER"), None)


def _offers(tennis_winner: bool) -> dict[int, dict[str, Any]]:
    data = payloads()
    fixtures = [fixture(sport, str(p["eventId"])) for sport, p in sorted(data.items())]
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        fetcher = offer_mod.OfferFetcher(
            _Client(data), ampersand_subjects=True, mappable_families=False,
            tennis_winner=tennis_winner)
        offers = fetcher.fetch_offers(fixtures)
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return {o.sofascore_event_id: o.model_dump(mode="json") for o in offers}


def test_switch_off_offer_is_byte_identical_to_the_golden() -> None:
    golden = (GOLDEN_DIR / "offer_mappable_off.json").read_text(encoding="utf-8")
    assert dumps(offer_dump(False)) + "\n" == golden
    off = _offers(False)
    assert dumps(list(off.values())) + "\n" == golden


def test_switch_on_offer_adds_one_two_sided_winner_rung_to_tennis_only() -> None:
    data = payloads()
    tennis_id = int(data["tennis"]["eventId"])
    football_id = int(data["football"]["eventId"])
    off, on = _offers(False), _offers(True)
    # football: nothing moves (its own "Zwycięzca"-free board, and the rule
    # is tennis-only anyway)
    assert on[football_id] == off[football_id]
    winner = [r for r in on[tennis_id]["rungs"] if r["market"] == MATCH_WON_FOR]
    assert len(winner) == 1
    rung = winner[0]
    assert (rung["subject"], rung["line"]) == (ZVEREV, 0.5)
    assert (rung["over_odds"], rung["under_odds"]) == (1.34, 3.05)
    # the ladder margin judges it like any two-sided rung
    margin = overround(rung["over_odds"], rung["under_odds"])
    assert margin == pytest.approx(1 / 1.34 + 1 / 3.05 - 1)
    # every other rung unchanged; "Zwycięzca" leaves unmapped_markets
    rest_on = [r for r in on[tennis_id]["rungs"] if r["market"] != MATCH_WON_FOR]
    assert rest_on == off[tennis_id]["rungs"]
    assert "Zwycięzca" in off[tennis_id]["unmapped_markets"]
    assert "Zwycięzca" not in on[tennis_id]["unmapped_markets"]


def test_football_fixture_never_reads_the_winner() -> None:
    fx = fixture("football", "1")
    payload = {"eventId": "1", "matchName": "Villarreal·Napoli",
               "odds": [_winner_item("1", 1.5), _winner_item("2", 2.5)]}

    class C:
        def event_odds(self, _eid: str) -> dict[str, Any]:
            return payload

    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        out = offer_mod.OfferFetcher(C(), tennis_winner=True).fetch_offers([fx])
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    assert out[0].rungs == []
    assert out[0].unmapped_markets == ["Zwycięzca"]


def test_samples_never_builds_a_winner_sample() -> None:
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market=MATCH_WON_FOR, subject=ZVEREV, line=0.5,
                          over_odds=1.34, under_odds=3.05,
                          fetched_at_utc=FROZEN)])
    assert metrics_from_offer(offer) == set()
    assert MATCH_WON_FOR in RATING_ONLY_MARKETS


# --- SHEET: p from the rating -------------------------------------------------


def _tennis_fixture() -> Fixture:
    return fixture("tennis", "77")


def _sheet(tennis_winner_on: bool, stats_only: bool = True,
           rating: MatchForecast | None = None,
           extra: list[PricedRung] | None = None,
           odds: tuple[float, float] = (1.34, 3.05)) -> list[dict[str, Any]]:
    fetched = FROZEN - timedelta(hours=1)  # before the start: not in-play
    obs = [Observation(sofascore_event_id=1000 + i,
                       match_date_utc=FROZEN - timedelta(days=i + 1),
                       value=float(v), opponent=f"O{i}", venue="home",
                       competition_id=3, season_id=1)
           for i, v in enumerate([20, 22, 18, 24, 21, 19, 23, 20, 22, 21])]
    samples = FixtureSamples(
        sofascore_event_id=77, readiness="READY", gaps=[],
        metrics={"games_total": MetricSample(
            metric="games_total", side_a=obs, side_b=obs, h2h=[])})
    rungs = [
        PricedRung(market="games_total", subject="", line=21.5,
                   over_odds=1.8, under_odds=1.95, fetched_at_utc=fetched),
        PricedRung(market=MATCH_WON_FOR, subject=ZVEREV, line=0.5,
                   over_odds=odds[0], under_odds=odds[1], fetched_at_utc=fetched),
        *(extra or []),
    ]
    offer = FixtureOffer(sofascore_event_id=77, status="PRICED",
                         unmapped_markets=[], rungs=rungs)
    rows, _ = process_fixture(
        _tennis_fixture(), samples, offer, baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), rating=rating,
        stats_only=stats_only, tennis_winner_on=tennis_winner_on)
    return [sheet_row_json(r) for r in rows]


def _forecast(p_home: float) -> MatchForecast:
    return MatchForecast(p_home=p_home, neighbours_home=(), neighbours_away=(),
                         rated_home=40, rated_away=25, table_scope="tier_gender")


def test_switch_off_sheet_drops_the_rung_and_keeps_every_other_row() -> None:
    off = _sheet(False, rating=_forecast(0.8))
    assert all(r["market"] != MATCH_WON_FOR for r in off)
    # the rest of the sheet is what it would be without the winner rung at all
    on = _sheet(True, rating=_forecast(0.8))
    assert [r for r in on if r["market"] != MATCH_WON_FOR] == off


def test_winner_rows_carry_the_rating_p_and_no_price() -> None:
    rows = {r["direction"]: r for r in _sheet(True, rating=_forecast(0.8))
            if r["market"] == MATCH_WON_FOR}
    assert set(rows) == {"OVER", "UNDER"}
    assert rows["OVER"]["p_central"] == 0.8
    assert rows["UNDER"]["p_central"] == 0.2
    for r in rows.values():
        assert r["subject"] == ZVEREV and r["line"] == 0.5
        assert r["sample_size"] == 0 and r["sample_frequency"] is None
        assert r["p_bar"] == r["p_central"] and r["bar_reason"] == "rating_only"
        assert r["forecast_source"] == "tennis_rating"
        assert r["verdict"] != "VALUE"
        assert any(n.startswith("TENNIS_MATCH_WINNER") for n in r["notes"])
    assert rows["OVER"]["offered_odds"] == 1.34
    assert rows["UNDER"]["offered_odds"] == 3.05
    # the price is beside p, never in it: another price, the same p
    other = _sheet(True, rating=_forecast(0.8), odds=(2.6, 1.5))
    assert [r["p_central"] for r in other if r["market"] == MATCH_WON_FOR] == [0.8, 0.2]
    assert rows["OVER"]["market_p"] is not None  # devigged, shown beside


def test_winner_subject_on_the_away_side_reads_the_away_probability() -> None:
    fx = _tennis_fixture()
    # Superbet lists Bublik first: the OVER is Bublik winning = 1 - p_home
    from scripts.sofa.run_sheet import winner_rows
    rung = PricedRung(market=MATCH_WON_FOR, subject=BUBLIK, line=0.5,
                      over_odds=3.05, under_odds=1.34, fetched_at_utc=FROZEN)
    out, skipped = winner_rows(fx, rung, _forecast(0.8), {}, True)
    assert not skipped
    assert {r.direction: r.p_central for r in out} == {"OVER": 0.2, "UNDER": 0.8}


def test_no_rating_no_row() -> None:
    from bet.sofa.contracts import GapReason
    from scripts.sofa.run_sheet import winner_rows
    rung = PricedRung(market=MATCH_WON_FOR, subject=ZVEREV, line=0.5,
                      over_odds=1.34, under_odds=3.05, fetched_at_utc=FROZEN)
    out, skipped = winner_rows(_tennis_fixture(), rung, None, {}, True)
    assert out == [] and skipped[0][1] == GapReason.NOT_RATED
    assert all(r["market"] != MATCH_WON_FOR for r in _sheet(True, rating=None))


def test_p_outside_the_model_resolution_is_refused() -> None:
    rows = [r for r in _sheet(True, rating=_forecast(0.97))
            if r["market"] == MATCH_WON_FOR]
    assert rows == []  # 0.97 above P_CEILING, 0.03 below P_FLOOR


def test_winner_p() -> None:
    assert winner_p(0.7, "OVER") == 0.7
    assert winner_p(0.7, "UNDER") == pytest.approx(0.3)


# --- CONFIDENCE: its own curve or nothing --------------------------------------


def _cal() -> Calibration:
    curve = {"0.700-0.750": {"n": 900, "realised": 0.73, "realised_lo95": 0.70},
             "0.800-0.825": {"n": 500, "realised": 0.82, "realised_lo95": 0.785}}
    pool = {f"{lo:.3f}-{hi:.3f}": {"n": 9999, "realised": 0.95, "realised_lo95": 0.94}
            for lo, hi in ((0.6, 0.7), (0.7, 0.75), (0.75, 0.8), (0.8, 0.825),
                           (0.825, 0.85), (0.85, 0.875), (0.875, 0.9))}
    return Calibration(
        pooled=pool, by_market={MATCH_WON_FOR: curve},
        pooled_by_sport={"tennis": pool},
        by_class={CLASS_TENNIS_WOMEN: {"by_market": {MATCH_WON_FOR: curve},
                                       "pooled_by_sport": {"tennis": pool}}},
        cap_market_by_thin=True, cap_pool_by_neighbour=True)


def test_curve_reads_its_own_buckets_only() -> None:
    cal = _cal()
    assert cal.realised(MATCH_WON_FOR, 0.72, "tennis", "OVER") == (
        0.70, f"market:{MATCH_WON_FOR}", 900)
    # a hole inside the range and the range above: no pool stands in
    assert cal.realised(MATCH_WON_FOR, 0.77, "tennis", "OVER") is None
    assert cal.realised(MATCH_WON_FOR, 0.86, "tennis", "UNDER") is None
    # the women's class reads its own section, never the pool
    assert cal.realised(MATCH_WON_FOR, 0.81, "tennis", "OVER",
                        CLASS_TENNIS_WOMEN)[0] == 0.785  # type: ignore[index]
    assert cal.realised(MATCH_WON_FOR, 0.77, "tennis", "OVER",
                        CLASS_TENNIS_WOMEN) is None
    # no curve at all: refused (NOT_CALIBRATED), never the pool
    empty = Calibration(pooled=_cal().pooled, by_market={},
                        pooled_by_sport=_cal().pooled_by_sport)
    assert empty.realised(MATCH_WON_FOR, 0.72, "tennis", "OVER") is None
    # an ordinary count market still reads the pool (nothing else moved)
    assert empty.realised("games_total", 0.72, "tennis", "OVER") is not None


# --- SETTLE ----------------------------------------------------------------------


def _event(winner: int | None, description: str = "Ended") -> dict[str, Any]:
    event: dict[str, Any] = {
        "status": {"type": "finished", "description": description, "code": 100},
        "homeScore": {"current": 2, "period1": 6, "period2": 6},
        "awayScore": {"current": 0, "period1": 3, "period2": 4},
    }
    if winner is not None:
        event["winnerCode"] = winner
    return event


@pytest.mark.parametrize("winner,is_home,value", [
    (1, True, 1.0), (1, False, 0.0), (2, True, 0.0), (2, False, 1.0)])
def test_settle_grades_the_winner_from_the_listing(
        winner: int, is_home: bool, value: float) -> None:
    got = extract_metric(MATCH_WON_FOR, "tennis", {}, None, _event(winner),
                         is_home, settling=True)
    assert got == value
    assert settle_value(value, 0.5, "OVER") == ("WIN" if value else "LOSS")
    assert settle_value(value, 0.5, "UNDER") == ("LOSS" if value else "WIN")


def test_settle_without_a_winner_code_is_no_grade() -> None:
    from bet.sofa.contracts import GapReason
    got = extract_metric(MATCH_WON_FOR, "tennis", {}, None, _event(None), True,
                         settling=True)
    assert got == GapReason.STAT_KEY_ABSENT
    got3 = extract_metric(MATCH_WON_FOR, "tennis", {}, None, _event(3), True,
                          settling=True)
    assert got3 == GapReason.STAT_KEY_ABSENT


@pytest.mark.parametrize("description", ["Retired", "Walkover"])
def test_retirement_and_walkover_are_refunds_before_any_grade(description: str) -> None:
    reason = unfinished_reason(_event(1, description))
    assert reason in REFUND_REASONS


# --- the rebuild -----------------------------------------------------------------


def test_rebuild_rereads_offer_and_sheet_once_the_switch_is_on(
        monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 10, 14, 12, tzinfo=UTC)
    state = rp.DayState(
        "2026-10-14", now, timedelta(minutes=45), offer_fixtures=1,
        open_fixtures=1, oldest_open_rung=now - timedelta(minutes=5),
        newest_rung=now - timedelta(minutes=5), offer_has_tennis=True,
        offer_has_winner=False, sheet_has_winner=False)
    off = rp.build_plan(state)
    assert "OFFER" not in off.names() and "SHEET" not in off.names()
    monkeypatch.setattr(epochs, "TENNIS_MATCH_WINNER_FROM_UTC",
                        datetime(2026, 10, 14, tzinfo=UTC))
    on = rp.build_plan(state).names()
    assert "OFFER" in on and "SHEET" in on
    assert on.index("OFFER") < on.index("SHEET") < on.index("CONFIDENCE")
    # a day whose sheet already carries the rows re-runs nothing
    done = rp.DayState(
        "2026-10-14", now, timedelta(minutes=45), offer_fixtures=1,
        open_fixtures=1, oldest_open_rung=now - timedelta(minutes=5),
        newest_rung=now - timedelta(minutes=5), offer_has_tennis=True,
        offer_has_winner=True, sheet_has_winner=True)
    assert not {"OFFER", "SHEET"} & set(rp.build_plan(done).names())


# --- the curve fit ------------------------------------------------------------


def _rows(n: int, p: float, wins: int, ts: int = 0) -> list[dict[str, Any]]:
    return [{"event_id": i, "ts": ts, "cls": "ITF-M", "klass": "", "scope": "tier",
             "p": p, "y": 1 if i < wins else 0, "b": 0.5} for i in range(n)]


def test_fit_curve_is_symmetric_over_the_two_selections() -> None:
    rows = _rows(500, 0.72, 360)
    curve = fit_curve(rows)
    assert curve["0.700-0.750"]["n"] == 500
    assert curve["0.700-0.750"]["realised"] == 0.72
    assert curve["0.000-0.600"]["n"] == 500  # the underdog's side
    assert curve["0.000-0.600"]["realised"] == 0.28
    # the same match listed the other way round is the same curve
    flipped = [{**r, "p": 1 - r["p"], "y": 1 - r["y"]} for r in rows]
    assert fit_curve(flipped) == curve


def test_holdout_calibration_verdicts() -> None:
    curve = fit_curve(_rows(2000, 0.72, 1440))
    good = holdout_calibration(curve, _rows(400, 0.72, 286), boot=50)
    cell = good["buckets"]["0.700-0.750"]
    assert cell["n"] == 400 and cell["verdict"] == "PASS" and good["pass"]
    bad = holdout_calibration(curve, _rows(400, 0.72, 250), boot=50)
    assert bad["buckets"]["0.700-0.750"]["verdict"] == "FAIL" and not bad["pass"]
    thin = holdout_calibration(curve, _rows(100, 0.72, 72), boot=50)
    assert thin["buckets"]["0.700-0.750"]["verdict"] == "INSUFFICIENT"
    assert not thin["pass"]  # nothing decisive is not a pass


def test_merge_puts_the_curves_where_confidence_reads_them() -> None:
    staged = {"by_market": {MATCH_WON_FOR: {"0.700-0.750": {"n": 1}}},
              "by_class": {CLASS_TENNIS_WOMEN: {"by_market": {
                  MATCH_WON_FOR: {"0.800-0.825": {"n": 2}}}}},
              "fitted_from": {"rows": 3}}
    cal = {"by_market": {"games_total": {}}, "by_class": {}}
    out = merge(cal, staged)
    assert set(out["by_market"]) == {"games_total", MATCH_WON_FOR}
    assert out["by_class"][CLASS_TENNIS_WOMEN]["by_market"][MATCH_WON_FOR] == {
        "0.800-0.825": {"n": 2}}
    assert cal == {"by_market": {"games_total": {}}, "by_class": {}}  # not mutated
