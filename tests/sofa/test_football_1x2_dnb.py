"""Football 1X2 (home / away win) and draw no bet from the pure rating with a
season-phase curve class, behind epochs.FOOTBALL_RESULT_1X2_DNB_FROM_UTC.
Offline and fast. Evidence:
docs/sofa/evidence/football_1x2_dnb_phase_2026-10-15.md.

The Superbet shape is the real one (tests/sofa/golden/offer_mappable_items.json,
Villarreal - Napoli, fetched 2026-10-12): "Mecz" 1 2.15 / X 3.60 / 2 3.05,
"Podwójna szansa" 1X 1.35 / X2 1.66 / 12 1.26, "Zakład bez remisu"
Villarreal 1.59 / Napoli 2.25.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import football_1x2_dnb as r12
from bet.sofa import football_rating as fr
from bet.sofa import offer as offer_mod
from bet.sofa.confidence import (
    OWN_CURVE_ONLY,
    Calibration,
    has_cross_league_unlinked_note,
)
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    GapReason,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.football_result import DOUBLE_CHANCE, ResultConfig, result_probs
from bet.sofa.metrics import result_1x2_dnb_value
from bet.sofa.samples import metrics_from_offer
from bet.sofa.season_phase import PHASE_EARLY, PHASE_MID
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS
from scripts.sofa.run_settle import _settle_result_1x2_dnb
from scripts.sofa.run_sheet import process_fixture, result_1x2_dnb_rows, sheet_row_json
from tests.sofa.offer_mappable_scenarios import (
    FROZEN,
    GOLDEN_DIR,
    _Client,
    dumps,
    fixture,
    payloads,
)

DAY_S = 86400
CFG = ResultConfig(nb_r=7.586, source="test")
PRE_KICKOFF = datetime(2026, 9, 22, tzinfo=UTC)


def _item(market: str, selection: str, price: float) -> dict[str, Any]:
    return {"marketName": market, "name": selection, "offerStateId": 1,
            "price": price, "status": "active"}


# --- the switch ---------------------------------------------------------------


def test_switch_reads_the_day_and_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    at = datetime(2026, 10, 15, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_RESULT_1X2_DNB_FROM_UTC", at)
    assert epochs.football_result_1x2_dnb("2026-10-15", at)
    assert not epochs.football_result_1x2_dnb("2026-10-14", at + timedelta(hours=1))
    assert not epochs.football_result_1x2_dnb("2026-10-15", at - timedelta(seconds=1))
    monkeypatch.setattr(epochs, "FOOTBALL_RESULT_1X2_DNB_FROM_UTC", None)
    assert not epochs.football_result_1x2_dnb("2027-01-01", at + timedelta(days=99))


def test_switch_value_is_the_next_day() -> None:
    assert epochs.FOOTBALL_RESULT_1X2_DNB_FROM_UTC == datetime(
        2026, 10, 15, 0, 0, tzinfo=UTC)


# --- OFFER ----------------------------------------------------------------------


@pytest.mark.parametrize("market,sel,want", [
    ("Mecz", "1", [("result_1x2", "1", 0.5, "OVER")]),
    ("Mecz", "2", [("result_1x2", "2", 0.5, "OVER")]),
    ("Mecz", "X", []),
    ("Podwójna szansa", "X2", [("result_1x2", "1", 0.5, "UNDER")]),
    ("Podwójna szansa", "1X", [("result_1x2", "2", 0.5, "UNDER")]),
    ("Podwójna szansa", "12", []),
    ("Zakład bez remisu", "Villarreal", [("draw_no_bet", "1", 0.5, "OVER")]),
    ("Zakład bez remisu", "Napoli", [("draw_no_bet", "1", 0.5, "UNDER")]),
    ("Zakład bez remisu", "Roma", []),
    ("1.połowa - zakład bez remisu", "Villarreal", []),
    ("Mecz & liczba goli (2.5)", "1 i powyżej 2.5", []),
])
def test_classify_reads_the_full_match_names(
        market: str, sel: str, want: list[tuple[str, str, float, str]]) -> None:
    assert r12.classify(market, sel, "Villarreal", "Napoli") == want


def test_dnb_side_is_never_guessed() -> None:
    assert r12.dnb_side("Villarreal", "Villarreal", "Napoli") == "1"
    assert r12.dnb_side("Napoli", "Villarreal", "Napoli") == "2"
    # a name in both (or neither) side: no side
    assert r12.dnb_side("FC", "FC Porto", "FC Arouca") is None
    assert r12.dnb_side("Roma", "Villarreal", "Napoli") is None
    assert r12.dnb_side("Villarreal", None, None) is None


def _offers(on: bool, dc: bool = False) -> dict[int, dict[str, Any]]:
    data = payloads()
    fixtures = [fixture(sport, str(p["eventId"])) for sport, p in sorted(data.items())]
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        fetcher = offer_mod.OfferFetcher(
            _Client(data), ampersand_subjects=True, mappable_families=False,
            football_result=dc, football_1x2_dnb=on)
        offers = fetcher.fetch_offers(fixtures)
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return {o.sofascore_event_id: o.model_dump(mode="json") for o in offers}


def test_switch_off_offer_is_byte_identical_to_the_golden() -> None:
    golden = (GOLDEN_DIR / "offer_mappable_off.json").read_text(encoding="utf-8")
    assert dumps(list(_offers(False).values())) + "\n" == golden


@pytest.mark.parametrize("dc", [False, True])
def test_switch_on_offer_adds_the_result_and_dnb_rungs(dc: bool) -> None:
    data = payloads()
    football_id = int(data["football"]["eventId"])
    tennis_id = int(data["tennis"]["eventId"])
    off, on = _offers(False, dc), _offers(True, dc)
    assert on[tennis_id] == off[tennis_id]
    new = {(r["market"], r["subject"]): r for r in on[football_id]["rungs"]
           if r["market"] in r12.MARKETS}
    assert set(new) == {("result_1x2", "1"), ("result_1x2", "2"),
                        ("draw_no_bet", "1")}
    # 1X2 price OVER, the double chance leaving it out UNDER
    one, two = new[("result_1x2", "1")], new[("result_1x2", "2")]
    assert (one["over_odds"], one["under_odds"]) == (2.15, 1.66)
    assert (two["over_odds"], two["under_odds"]) == (3.05, 1.35)
    dnb = new[("draw_no_bet", "1")]
    assert (dnb["over_odds"], dnb["under_odds"]) == (1.59, 2.25)
    assert all(r["line"] == 0.5 for r in new.values())
    # every other rung unchanged (the double chance included, when on)
    rest = [r for r in on[football_id]["rungs"] if r["market"] not in r12.MARKETS]
    assert rest == off[football_id]["rungs"]
    if dc:
        dcs = {r["subject"]: r for r in rest if r["market"] == DOUBLE_CHANCE}
        assert (dcs["X2"]["over_odds"], dcs["X2"]["under_odds"]) == (1.66, 2.15)
    unmapped_off = set(off[football_id]["unmapped_markets"])
    unmapped_on = set(on[football_id]["unmapped_markets"])
    # "Mecz" X and "Podwójna szansa" 12 are no 1X2 / DNB side: they stay
    assert unmapped_off - unmapped_on == {"Zakład bez remisu"}
    assert "1.połowa - zakład bez remisu" in unmapped_on


def _fetch_one(odds: list[dict[str, Any]], sport: str = "football") -> FixtureOffer:
    fx = fixture(sport, "1")
    payload = {"eventId": "1", "matchName": "Villarreal·Napoli", "odds": odds}

    class C:
        def event_odds(self, _eid: str) -> dict[str, Any]:
            return payload

    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        out = offer_mod.OfferFetcher(C(), football_1x2_dnb=True).fetch_offers([fx])
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return out[0]


def test_a_double_chance_price_alone_is_no_1x2_offer() -> None:
    out = _fetch_one([_item("Podwójna szansa", "X2", 1.66)])
    assert out.rungs == []


def test_a_tennis_fixture_never_reads_them() -> None:
    out = _fetch_one([_item("Zakład bez remisu", "Villarreal", 1.59)], sport="tennis")
    assert out.rungs == [] and out.unmapped_markets == ["Zakład bez remisu"]


def test_samples_never_builds_a_sample_for_them() -> None:
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market=m, subject="1", line=0.5, over_odds=1.6,
                          under_odds=2.2, fetched_at_utc=FROZEN)
               for m in sorted(r12.MARKETS)])
    assert metrics_from_offer(offer) == set()
    assert r12.MARKETS <= RATING_ONLY_MARKETS
    assert r12.MARKETS <= OWN_CURVE_ONLY


# --- the price ------------------------------------------------------------------


@pytest.mark.parametrize("lh,la", [(1.4, 1.1), (0.6, 2.2), (2.5, 0.4)])
def test_probabilities_follow_the_grid(lh: float, la: float) -> None:
    pr = result_probs(lh, la, CFG.nb_r)
    got = r12.probabilities(lh, la, CFG.nb_r)
    assert got["1x2:1"] == pytest.approx(pr["1"])
    assert got["1x2:2"] == pytest.approx(pr["2"])
    assert got["dnb:1"] == pytest.approx(pr["1"] / (pr["1"] + pr["2"]))
    assert got["dnb:1"] + got["dnb:2"] == pytest.approx(1.0)
    assert got["dnb:1"] > got["1x2:1"]  # the draw is refunded, not lost
    assert r12.row_p("result_1x2", "1", "OVER", got) == got["1x2:1"]
    assert r12.row_p("result_1x2", "1", "UNDER", got) is None
    assert r12.row_p("draw_no_bet", "1", "UNDER", got) == got["dnb:2"]


# --- SHEET ----------------------------------------------------------------------


def _book(away_league: int = 1) -> fr.RatingBook:
    history = []
    t = 0
    for i in range(fr.MIN_LEAGUE_MATCHES + 10):
        history.append(fr.FootballResult(
            i * 2, t, 1, 1, 100 + i, {"goals_for": (3.0, 1.0)}))
        history.append(fr.FootballResult(
            i * 2 + 1, t + 1, away_league, 200 + i, 2, {"goals_for": (1.0, 1.0)}))
        t += DAY_S
    return fr.replay(history, cut_ts=10**9)


def _forecast(away_league: int = 1) -> fr.FootballForecast:
    return fr.FootballForecast(_book(away_league), 1, 1, 2)


def _fixture_model() -> Any:
    from tests.sofa.test_player_markets import _fixture

    return _fixture()


def _rungs() -> list[PricedRung]:
    return [
        PricedRung(market="result_1x2", subject="1", line=0.5, over_odds=2.15,
                   under_odds=1.66, fetched_at_utc=PRE_KICKOFF),
        PricedRung(market="result_1x2", subject="2", line=0.5, over_odds=3.05,
                   under_odds=1.35, fetched_at_utc=PRE_KICKOFF),
        PricedRung(market="draw_no_bet", subject="1", line=0.5, over_odds=1.59,
                   under_odds=2.25, fetched_at_utc=PRE_KICKOFF),
    ]


def _sheet(cfg: ResultConfig | None, forecast: fr.FootballForecast | None,
           phase: str | None = PHASE_EARLY) -> list[dict[str, Any]]:
    obs = [Observation(sofascore_event_id=1000 + i,
                       match_date_utc=FROZEN - timedelta(days=i + 1),
                       value=float(v), opponent=f"O{i}", venue="home",
                       competition_id=1, season_id=1)
           for i, v in enumerate([2, 3, 1, 4, 2, 3, 2, 1, 3, 2])]
    samples = FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={"goals_total": MetricSample(
            metric="goals_total", side_a=obs, side_b=obs, h2h=[])})
    rungs = [PricedRung(market="goals_total", subject="", line=2.5,
                        over_odds=1.8, under_odds=1.95, fetched_at_utc=PRE_KICKOFF),
             *_rungs()]
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED",
                         unmapped_markets=[], rungs=rungs)
    rows, _ = process_fixture(
        _fixture_model(), samples, offer, baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), football=forecast,
        stats_only=True, result_1x2_dnb=cfg, result_phase=phase)
    return [sheet_row_json(r) for r in rows]


def test_switch_off_sheet_is_unchanged() -> None:
    off = _sheet(None, _forecast())
    assert off and all(r["market"] not in r12.MARKETS for r in off)
    assert all("result_1x2_dnb_rule" not in r and "result_phase" not in r
               for r in off)
    on = _sheet(CFG, _forecast())
    assert [r for r in on if r["market"] not in r12.MARKETS] == off


def test_rows_carry_the_pure_rating_p_and_the_phase() -> None:
    fc = _forecast()
    home = fc.centre("goals_for", "side_a")
    away = fc.centre("goals_for", "side_b")
    assert home is not None and away is not None
    want = r12.probabilities(home[0], away[0], CFG.nb_r)
    rows = {(r["market"], r["subject"], r["direction"]): r
            for r in _sheet(CFG, fc) if r["market"] in r12.MARKETS}
    assert set(rows) == {("result_1x2", "1", "OVER"), ("result_1x2", "2", "OVER"),
                         ("draw_no_bet", "1", "OVER"), ("draw_no_bet", "1", "UNDER")}
    assert rows[("result_1x2", "1", "OVER")]["p_central"] == round(want["1x2:1"], 4)
    assert rows[("draw_no_bet", "1", "UNDER")]["p_central"] == round(want["dnb:2"], 4)
    for r in rows.values():
        assert r["result_1x2_dnb_rule"] == epochs.FOOTBALL_RESULT_1X2_DNB
        assert r["result_phase"] == PHASE_EARLY
        assert r["sample_size"] == 0 and r["bar_reason"] == "rating_only"
        assert r["forecast_source"] == "football_rating"
        assert r["verdict"] != "VALUE"
        assert any(n.startswith(r12.NOTE) for n in r["notes"])
        assert any(n.startswith("UNFITTED_CONSTANTS") and "FOOTBALL_RESULT_NB_R" in n
                   for n in r["notes"])
    assert rows[("draw_no_bet", "1", "UNDER")]["offered_odds"] == 2.25
    no_phase = _sheet(CFG, fc, phase=None)
    assert all("result_phase" not in r for r in no_phase)


def test_unlinked_and_unrated() -> None:
    fc = _forecast(away_league=5)
    assert fc.fixture_link() == fr.UNLINKED
    out, _ = result_1x2_dnb_rows(_fixture_model(), _rungs()[2], fc, CFG, None, {},
                                 True)
    assert len(out) == 2 and all(has_cross_league_unlinked_note(r.notes) for r in out)
    out, skipped = result_1x2_dnb_rows(_fixture_model(), _rungs()[0], None, CFG,
                                       None, {}, True)
    assert out == [] and skipped[0][1] == GapReason.NOT_RATED


# --- CONFIDENCE: the phase class --------------------------------------------------


def test_leg_class_reads_season_early_only_for_marked_men_rows() -> None:
    row = {"market": "draw_no_bet", "result_1x2_dnb_rule": "r",
           "result_phase": PHASE_EARLY}
    assert r12.leg_class(row, None) == r12.CLASS_SEASON_EARLY
    assert r12.leg_class(row, "women") == "women"
    assert r12.leg_class({**row, "result_phase": PHASE_MID}, None) is None
    assert r12.leg_class({**row, "result_1x2_dnb_rule": None}, None) is None
    assert r12.leg_class({**row, "market": "goals_total"}, None) is None
    assert r12.curve_class(False, PHASE_EARLY) == r12.CLASS_SEASON_EARLY
    assert r12.curve_class(True, PHASE_EARLY) == r12.CLASS_WOMEN
    assert r12.curve_class(False, None) is None


def test_a_class_curve_is_read_and_never_the_unclassed_one() -> None:
    curve = {"0.800-0.825": {"n": 900, "realised": 0.80, "realised_lo95": 0.78}}
    early = {"0.800-0.825": {"n": 900, "realised": 0.75, "realised_lo95": 0.73}}
    cal = Calibration(
        pooled={}, by_market={},
        by_market_direction={"draw_no_bet|OVER": curve},
        by_class={"season_early": {"by_market_direction": {
            "draw_no_bet|OVER": early}}})
    assert cal.realised("draw_no_bet", 0.81, "football", "OVER") == (
        0.78, "market:draw_no_bet|OVER", 900)
    assert cal.realised("draw_no_bet", 0.81, "football", "OVER",
                        r12.CLASS_SEASON_EARLY) == (
        0.73, "season_early:market:draw_no_bet|OVER", 900)
    # the class has no UNDER curve: refused, never the unclassed curve
    assert cal.realised("draw_no_bet", 0.81, "football", "UNDER",
                        r12.CLASS_SEASON_EARLY) is None
    # a rating-only market: no pool stands in
    assert cal.realised("result_1x2", 0.81, "football", "OVER") is None


# --- SETTLE: the 90-minute score, a DNB draw a refund -------------------------------


def _event(code: int, home: dict[str, int], away: dict[str, int]) -> dict[str, Any]:
    return {"status": {"type": "finished", "description": "Ended", "code": code},
            "homeScore": home, "awayScore": away}


NORMAL_2_0 = _event(100, {"current": 2, "period1": 1, "period2": 1, "normaltime": 2},
                    {"current": 0, "period1": 0, "period2": 0, "normaltime": 0})
NORMAL_0_1 = _event(100, {"current": 0, "period1": 0, "period2": 0, "normaltime": 0},
                    {"current": 1, "period1": 1, "period2": 0, "normaltime": 1})
AET_2_1 = _event(110, {"current": 2, "period1": 1, "period2": 0, "normaltime": 1,
                       "extra1": 1, "extra2": 0},
                 {"current": 1, "period1": 0, "period2": 1, "normaltime": 1,
                  "extra1": 0, "extra2": 0})


def _row(market: str, subject: str, direction: str) -> dict[str, Any]:
    return {"market": market, "subject": subject, "line": 0.5,
            "direction": direction, "sport": "football"}


def test_settle_result_1x2() -> None:
    assert _settle_result_1x2_dnb(_row("result_1x2", "1", "OVER"), NORMAL_2_0) == (
        1.0, "WIN")
    assert _settle_result_1x2_dnb(_row("result_1x2", "2", "OVER"), NORMAL_2_0) == (
        0.0, "LOSS")
    assert _settle_result_1x2_dnb(_row("result_1x2", "2", "OVER"), NORMAL_0_1) == (
        1.0, "WIN")
    # 1-1 after 90 minutes: neither side won the 1X2, extra time is not counted
    assert _settle_result_1x2_dnb(_row("result_1x2", "1", "OVER"), AET_2_1) == (
        0.0, "LOSS")


def test_settle_dnb_and_its_draw_refund() -> None:
    assert _settle_result_1x2_dnb(_row("draw_no_bet", "1", "OVER"), NORMAL_2_0) == (
        1.0, "WIN")
    assert _settle_result_1x2_dnb(_row("draw_no_bet", "1", "UNDER"), NORMAL_2_0) == (
        1.0, "LOSS")
    assert _settle_result_1x2_dnb(_row("draw_no_bet", "1", "UNDER"), NORMAL_0_1) == (
        0.0, "WIN")
    for d in ("OVER", "UNDER"):
        assert _settle_result_1x2_dnb(
            _row("draw_no_bet", "1", d), AET_2_1) == r12.DNB_DRAW_REFUND
    assert result_1x2_dnb_value("draw_no_bet", "1", AET_2_1) is None
    assert r12.outcome("draw_no_bet", "1", "OVER", 1, 1) is None


def test_settle_refuses_what_it_cannot_read() -> None:
    assert result_1x2_dnb_value("result_1x2", "X", NORMAL_2_0) == \
        GapReason.STAT_KEY_ABSENT
    assert _settle_result_1x2_dnb(_row("result_1x2", "1", "OVER"),
                                  _event(100, {}, {})) == "result_1x2:STAT_KEY_ABSENT"


def test_regrade_grades_like_settle() -> None:
    from scripts.sofa.regrade_settled import grade_live

    assert grade_live(_row("draw_no_bet", "1", "UNDER"), NORMAL_0_1,
                      None, None, None) == (0.0, "WIN")
    assert grade_live(_row("draw_no_bet", "1", "OVER"), AET_2_1,
                      None, None, None) == r12.DNB_DRAW_REFUND
