"""The football incident markets - first goal, red cards, penalties - behind
epochs.FOOTBALL_INCIDENT_MARKETS_FROM_UTC (None). Offline and fast.

Evidence: docs/sofa/evidence/football_incidents_tennis_sets_2026-10-14.md.
The Superbet shapes are the real ones (tests/sofa/golden/
offer_mappable_items.json, Villarreal - Napoli, fetched 2026-10-12): "1. gol"
Villarreal 1.80 / nikt 16 / Napoli 2.20; "Liczba czerwonych kartek" O/U 0.5
5.45 / 1.11; "Liczba przyznanych rzutów karnych" O/U 0.5 2.82 / 1.37.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from bet.sofa import offer as offer_mod
from bet.sofa.confidence import OWN_CURVE_ONLY, Calibration
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    GapReason,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.football_incidents import (
    FIRST_GOAL,
    FIRST_GOAL_AWAY,
    FIRST_GOAL_HOME,
    FIRST_GOAL_NONE,
    INCIDENT_MARKETS,
    PENALTIES,
    RED_CARDS,
    IncidentPricing,
    IncidentRates,
    band_index,
    classify_incident,
    first_goal_probs,
    incident_value,
    rates_from_records,
    read_incidents,
)
from bet.sofa.football_result import ResultConfig, count_pmf
from bet.sofa.offer import classify_odd
from bet.sofa.samples import metrics_from_offer
from bet.sofa.settle import settle as settle_value
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS
from scripts.sofa.run_settle import _settle_incident
from scripts.sofa.run_sheet import incident_rows, process_fixture, sheet_row_json
from tests.sofa.calibration_without import calibration_without
from tests.sofa.offer_mappable_scenarios import (
    FROZEN,
    GOLDEN_DIR,
    _Client,
    dumps,
    fixture,
    offer_dump,
    payloads,
)

DAY_S = 86400
CFG = ResultConfig(nb_r=7.586, source="test")
PRE_KICKOFF = datetime(2026, 9, 22, tzinfo=UTC)
NAMES = ("Villarreal", "Napoli")


def _item(
    market: str, selection: str, price: float, line: str | None = None
) -> dict[str, Any]:
    out = {
        "marketName": market,
        "name": selection,
        "offerStateId": 1,
        "price": price,
        "status": "active",
    }
    if line is not None:
        out["specialBetValue"] = line
    return out


# --- the switch ------------------------------------------------------------------


def test_switch_reads_the_day_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # operator 2026-10-14: on from 14:50Z into the built day (mixed)
    on = datetime(2026, 10, 14, 14, 50, 0, tzinfo=UTC)
    assert epochs.FOOTBALL_INCIDENT_MARKETS_FROM_UTC == on
    monkeypatch.setattr(epochs, "FOOTBALL_INCIDENT_MARKETS_FROM_UTC", None)
    assert epochs.FOOTBALL_INCIDENT_MARKETS == "incident_markets_v1"
    late = datetime(2027, 1, 1, tzinfo=UTC)
    assert not epochs.football_incident_markets("2027-01-01", late)
    monkeypatch.setattr(
        epochs, "FOOTBALL_INCIDENT_MARKETS_FROM_UTC", datetime(2026, 10, 16, tzinfo=UTC)
    )
    assert epochs.football_incident_markets(
        "2026-10-16", datetime(2026, 10, 16, 1, tzinfo=UTC)
    )
    assert not epochs.football_incident_markets("2026-10-15", late)
    assert not epochs.football_incident_markets(
        "2026-10-16", datetime(2026, 10, 15, 23, tzinfo=UTC)
    )


# --- OFFER -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "market,selection,line,expected",
    [
        ("1. gol", "Villarreal", "1", (FIRST_GOAL, "1", 0.5, "OVER")),
        ("1. gol", "Napoli", "1", (FIRST_GOAL, "2", 0.5, "OVER")),
        ("1. gol", "nikt", "1", (FIRST_GOAL, "nikt", 0.5, "OVER")),
        (
            "Liczba czerwonych kartek",
            "Poniżej 0.5",
            "0.5",
            (RED_CARDS, "", 0.5, "UNDER"),
        ),
        (
            "Liczba czerwonych kartek",
            "Powyżej 1.5",
            "1.5",
            (RED_CARDS, "", 1.5, "OVER"),
        ),
        (
            "Liczba przyznanych rzutów karnych",
            "poniżej 0.5",
            "0.5",
            (PENALTIES, "", 0.5, "UNDER"),
        ),
        (
            "Liczba przyznanych rzutów karnych",
            "powyżej 1.5",
            "1.5",
            (PENALTIES, "", 1.5, "OVER"),
        ),
    ],
)
def test_classify_reads_the_three_names(
    market: str, selection: str, line: str, expected: tuple[str, str, float, str]
) -> None:
    assert classify_incident(market, selection, line, NAMES) == expected


@pytest.mark.parametrize(
    "market,selection,line",
    [
        ("1.połowa - 1. gol", "Villarreal", "1"),
        ("1. gol & mecz", "1 & 1", "1"),
        ("1. gol (przedziały 15-minutowe)", "0:00 - 14:59 minuty", "1"),
        ("1. gol od 0:00 do 9:59 minuty", "Villarreal", "0-1-9"),
        ("Liczba czerwonych kartek Villarreal", "Poniżej 0.5", "0.5"),
        ("1.połowa - liczba czerwonych kartek", "Powyżej 0.5", "0.5"),
        ("Villarreal - liczba przyznanych rzutów karnych", "poniżej 0.5", "0.5"),
        ("1.połowa - liczba przyznanych rzutów karnych", "poniżej 0.5", "0.5"),
        ("Liczba czerwonych kartek", "Poniżej 1", "1"),
        ("Liczba czerwonych kartek", "Poniżej 0.5", None),
        ("1. gol", "Barcelona", "1"),
    ],
)
def test_classify_refuses_halves_teams_bands_and_unknown(
    market: str, selection: str, line: str | None
) -> None:
    assert classify_incident(market, selection, line, NAMES) is None


def test_first_goal_needs_both_listing_names() -> None:
    assert classify_incident("1. gol", "Villarreal", "1", ("Villarreal",)) is None
    assert classify_incident("1. gol", "Villarreal", "1", ()) is None
    # "nikt" needs no name
    assert classify_incident("1. gol", "nikt", "1", ()) == (
        FIRST_GOAL,
        "nikt",
        0.5,
        "OVER",
    )


def test_classify_odd_reads_them_only_when_asked() -> None:
    item = _item("Liczba czerwonych kartek", "Powyżej 0.5", 5.45, "0.5")
    assert classify_odd(item) == (None, "Liczba czerwonych kartek")
    assert classify_odd(item, (), False, NAMES, False, False, False, True) == (
        (RED_CARDS, "", 0.5, "OVER"),
        None,
    )


def _offers(on: bool) -> dict[int, dict[str, Any]]:
    data = payloads()
    fixtures = [fixture(sport, str(p["eventId"])) for sport, p in sorted(data.items())]
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        fetcher = offer_mod.OfferFetcher(
            _Client(data),
            ampersand_subjects=True,
            mappable_families=False,
            football_incidents=on,
        )
        offers = fetcher.fetch_offers(fixtures)
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return {o.sofascore_event_id: o.model_dump(mode="json") for o in offers}


def test_switch_off_offer_is_byte_identical_to_the_golden() -> None:
    golden = (GOLDEN_DIR / "offer_mappable_off.json").read_text(encoding="utf-8")
    assert dumps(offer_dump(False)) + "\n" == golden
    assert dumps(list(_offers(False).values())) + "\n" == golden


def test_switch_on_offer_adds_the_rungs_to_football_only() -> None:
    data = payloads()
    football_id = int(data["football"]["eventId"])
    tennis_id = int(data["tennis"]["eventId"])
    off, on = _offers(False), _offers(True)
    assert on[tennis_id] == off[tennis_id]
    new = {
        (r["market"], r["subject"], r["line"]): r
        for r in on[football_id]["rungs"]
        if r["market"] in INCIDENT_MARKETS
    }
    fg = {
        k[1]: (r["over_odds"], r["under_odds"])
        for k, r in new.items()
        if k[0] == FIRST_GOAL
    }
    # one-sided: no single price is the complement of a first-goal selection
    assert fg == {"1": (1.8, None), "2": (2.2, None), "nikt": (16, None)}
    reds = new[(RED_CARDS, "", 0.5)]
    assert (reds["over_odds"], reds["under_odds"]) == (5.45, 1.11)
    # the suspended UNDER 1.5 ("block") is no offer
    assert (
        new[(RED_CARDS, "", 1.5)]["over_odds"],
        new[(RED_CARDS, "", 1.5)]["under_odds"],
    ) == (12, None)
    pens = new[(PENALTIES, "", 0.5)]
    assert (pens["over_odds"], pens["under_odds"]) == (2.82, 1.37)
    assert (
        new[(PENALTIES, "", 1.5)]["over_odds"],
        new[(PENALTIES, "", 1.5)]["under_odds"],
    ) == (11, 1.02)
    rest = [r for r in on[football_id]["rungs"] if r["market"] not in INCIDENT_MARKETS]
    assert rest == off[football_id]["rungs"]
    gone = set(off[football_id]["unmapped_markets"]) - set(
        on[football_id]["unmapped_markets"]
    )
    assert gone == {
        "1. gol",
        "Liczba czerwonych kartek",
        "Liczba przyznanych rzutów karnych",
    }
    assert "1. połowa - 1. gol" in on[football_id]["unmapped_markets"]
    assert "1. gol (przedziały 15-minutowe)" in on[football_id]["unmapped_markets"]


def test_samples_never_builds_an_incident_sample() -> None:
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        unmapped_markets=[],
        rungs=[
            PricedRung(
                market=m,
                subject="",
                line=0.5,
                over_odds=3.0,
                under_odds=1.3,
                fetched_at_utc=FROZEN,
            )
            for m in (RED_CARDS, PENALTIES)
        ],
    )
    assert metrics_from_offer(offer) == set()
    assert INCIDENT_MARKETS <= RATING_ONLY_MARKETS
    assert INCIDENT_MARKETS <= OWN_CURVE_ONLY


# --- the incident reader ----------------------------------------------------------


def _goal(
    t: int,
    hs: int,
    as_: int,
    home: bool,
    cls: str = "regular",
    added: int | None = None,
    secs: int | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "incidentType": "goal",
        "incidentClass": cls,
        "time": t,
        "homeScore": hs,
        "awayScore": as_,
        "isHome": home,
    }
    if added is not None:
        out["addedTime"] = added
    if secs is not None:
        out["timeSeconds"] = secs
    return out


SUB = {
    "incidentType": "substitution",
    "incidentClass": "regular",
    "time": 60,
    "isHome": True,
}


def _card(t: int, cls: str, home: bool, **kw: Any) -> dict[str, Any]:
    return {
        "incidentType": "card",
        "incidentClass": cls,
        "time": t,
        "isHome": home,
        "player": {"id": 1},
        **kw,
    }


def test_first_goal_is_the_earliest_by_half_then_clock() -> None:
    # Sofascore lists newest first; the first-half added-time goal (45+3,
    # timeSeconds 2880) comes before the second half's 47' (2820 s)
    inc = {
        "incidents": [
            _goal(47, 1, 1, False, secs=2820),
            _goal(45, 1, 0, True, added=3, secs=2880),
        ]
    }
    rec = read_incidents(inc, (1.0, 1.0))
    assert rec is not None and rec.first_goal == FIRST_GOAL_HOME
    assert rec.first_goal_minute == pytest.approx(44.999)
    assert band_index(rec.first_goal_minute, (0, 15, 30, 45, 60, 75, 1e9)) == 2


def test_an_own_goal_counts_for_the_side_its_score_moved() -> None:
    inc = {"incidents": [_goal(22, 0, 1, False, cls="ownGoal")]}
    rec = read_incidents(inc, (0.0, 1.0))
    assert rec is not None and rec.first_goal == FIRST_GOAL_AWAY


def test_extra_time_goals_do_not_count_and_a_scoreless_90_is_none() -> None:
    inc = {"incidents": [_goal(105, 1, 0, True), SUB]}
    rec = read_incidents(inc, (0.0, 0.0))
    assert rec is not None and rec.first_goal == FIRST_GOAL_NONE
    assert rec.first_goal_minute is None


def test_a_list_that_disagrees_with_the_score_is_no_record() -> None:
    inc = {"incidents": [_goal(10, 1, 0, True)]}
    assert read_incidents(inc, (2.0, 0.0)) is None
    assert read_incidents(inc, None) is None
    assert read_incidents({}, (0.0, 0.0)) is None


def test_reds_and_penalties_only_from_a_full_feed() -> None:
    listed = [
        _goal(30, 1, 0, True, cls="penalty"),
        {
            "incidentType": "inGamePenalty",
            "incidentClass": "missed",
            "time": 50,
            "isHome": False,
        },
        _card(70, "red", True),
        _card(80, "yellowRed", False),
        _card(85, "red", False, rescinded=True),
        {
            "incidentType": "card",
            "incidentClass": "red",
            "time": 88,
            "isHome": True,
            "manager": {"id": 9},
        },  # staff: not a player
        _card(100, "red", True),  # extra time
        {"incidentType": "penaltyShootout", "incidentClass": "scored", "isHome": True},
    ]
    partial = read_incidents({"incidents": listed}, (1.0, 0.0))
    assert partial is not None and partial.red_cards is None
    assert partial.penalties is None
    full = read_incidents({"incidents": [*listed, SUB]}, (1.0, 0.0))
    assert full is not None and full.full_feed
    assert full.red_cards == (1, 1)
    assert full.penalties == (1, 1)


# --- price -------------------------------------------------------------------------


@pytest.mark.parametrize("lh,la", [(1.5, 1.1), (0.4, 2.8), (2.9, 0.3), (1.0, 1.0)])
def test_first_goal_probs_are_the_nb_grid(lh: float, la: float) -> None:
    p = first_goal_probs(lh, la, 7.586)
    assert sum(p.values()) == pytest.approx(1.0)
    p00 = float(
        count_pmf(np.array([lh]), 7.586)[0, 0] * count_pmf(np.array([la]), 7.586)[0, 0]
    )
    # count_pmf renormalises over 0..12 goals: equal to its truncation
    assert p["nikt"] == pytest.approx(p00, rel=1e-3)
    assert p["1"] / p["2"] == pytest.approx(lh / la)
    with pytest.raises(ValueError):
        first_goal_probs(0.0, 1.0, 7.0)


def _rec(reds: int | None, pens: int | None) -> Any:
    from bet.sofa.football_incidents import IncidentRecord

    return IncidentRecord(
        FIRST_GOAL_NONE,
        None,
        (0, 0),
        (),
        reds is not None,
        None if reds is None else (reds, 0),
        None if pens is None else (0, pens),
    )


def _rates() -> IncidentRates:
    recs: list[tuple[int, bool, Any]] = []
    # gender pool: 300 men's matches in competition 9, 60 with a red, 90 with
    # a penalty, 6 with two reds
    for i in range(300):
        recs.append(
            (9, False, _rec(2 if i < 6 else (1 if i < 60 else 0), 1 if i < 90 else 0))
        )
    # competition 1: 10 matches, 5 with a red
    for i in range(10):
        recs.append((1, False, _rec(1 if i < 5 else 0, 0)))
    # a partial feed counts nowhere
    recs.append((1, False, _rec(None, None)))
    return rates_from_records(recs)


def test_rates_shrink_the_competition_toward_the_gender() -> None:
    rates = _rates()
    g = (65 + 0.5) / (310 + 1.0)
    assert rates.p_over(RED_CARDS, 1, 0.5) == pytest.approx((5 + 30 * g) / (10 + 30))
    # an unknown competition reads the men's rate
    assert rates.p_over(RED_CARDS, 777, 0.5) == pytest.approx(g)
    assert rates.p_over(RED_CARDS, 9, 1.5) == pytest.approx(
        (6 + 30 * (6.5 / 311)) / (300 + 30)
    )
    # an unmeasured line, or a gender without 200 matches: nothing
    assert rates.p_over(RED_CARDS, 1, 2.5) is None
    assert rates.p_over(PENALTIES, 1, 0.5) is not None
    women = rates_from_records([(5, True, _rec(1, 1))])
    assert women.p_over(RED_CARDS, 5, 0.5) is None


# --- SHEET -------------------------------------------------------------------------


def _book(away_league: int = 1) -> fr.RatingBook:
    history = []
    t = 0
    for i in range(fr.MIN_LEAGUE_MATCHES + 10):
        history.append(
            fr.FootballResult(i * 2, t, 1, 1, 100 + i, {"goals_for": (3.0, 1.0)})
        )
        history.append(
            fr.FootballResult(
                i * 2 + 1, t + 1, away_league, 200 + i, 2, {"goals_for": (1.0, 1.0)}
            )
        )
        t += DAY_S
    return fr.replay(history, cut_ts=10**9)


def _forecast(away_league: int = 1) -> fr.FootballForecast:
    return fr.FootballForecast(_book(away_league), 1, 1, 2)


def _fixture_model() -> Any:
    from tests.sofa.test_player_markets import _fixture

    return _fixture()


def _sheet(
    pricing: IncidentPricing | None, forecast: fr.FootballForecast | None
) -> list[dict[str, Any]]:
    obs = [
        Observation(
            sofascore_event_id=1000 + i,
            match_date_utc=FROZEN - timedelta(days=i + 1),
            value=float(v),
            opponent=f"O{i}",
            venue="home",
            competition_id=1,
            season_id=1,
        )
        for i, v in enumerate([2, 3, 1, 4, 2, 3, 2, 1, 3, 2])
    ]
    samples = FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        gaps=[],
        metrics={
            "goals_total": MetricSample(
                metric="goals_total", side_a=obs, side_b=obs, h2h=[]
            )
        },
    )
    f = PRE_KICKOFF
    rungs = [
        PricedRung(
            market="goals_total",
            subject="",
            line=2.5,
            over_odds=1.8,
            under_odds=1.95,
            fetched_at_utc=f,
        ),
        PricedRung(
            market=FIRST_GOAL,
            subject="1",
            line=0.5,
            over_odds=1.8,
            under_odds=None,
            fetched_at_utc=f,
        ),
        PricedRung(
            market=FIRST_GOAL,
            subject="nikt",
            line=0.5,
            over_odds=16,
            under_odds=None,
            fetched_at_utc=f,
        ),
        PricedRung(
            market=RED_CARDS,
            subject="",
            line=0.5,
            over_odds=5.45,
            under_odds=1.11,
            fetched_at_utc=f,
        ),
        PricedRung(
            market=PENALTIES,
            subject="",
            line=0.5,
            over_odds=2.82,
            under_odds=1.37,
            fetched_at_utc=f,
        ),
        PricedRung(
            market=PENALTIES,
            subject="",
            line=2.5,
            over_odds=40,
            under_odds=1.01,
            fetched_at_utc=f,
        ),
    ]
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[], rungs=rungs
    )
    rows, _ = process_fixture(
        _fixture_model(),
        samples,
        offer,
        baselines={},
        reliability={},
        engine_constants={},
        vetoes=[],
        config=SofaConfig(),
        football=forecast,
        stats_only=True,
        incident_pricing=pricing,
    )
    return [sheet_row_json(r) for r in rows]


def test_switch_off_sheet_is_unchanged() -> None:
    off = _sheet(None, _forecast())
    assert off and all(r["market"] not in INCIDENT_MARKETS for r in off)
    assert all("incident_rule" not in r for r in off)
    on = _sheet(IncidentPricing(_rates(), CFG), _forecast())
    assert [r for r in on if r["market"] not in INCIDENT_MARKETS] == off


def test_incident_rows_carry_the_model_p_and_no_price() -> None:
    fc = _forecast()
    rates = _rates()
    rows = [
        r
        for r in _sheet(IncidentPricing(rates, CFG), fc)
        if r["market"] in INCIDENT_MARKETS
    ]
    by = {(r["market"], r["subject"], r["line"], r["direction"]): r for r in rows}
    home = fc.centre("goals_for", "side_a")
    away = fc.centre("goals_for", "side_b")
    assert home is not None and away is not None
    want = first_goal_probs(home[0], away[0], CFG.nb_r)
    fg = by[(FIRST_GOAL, "1", 0.5, "OVER")]
    assert fg["p_central"] == round(want["1"], 4)
    assert fg["forecast_source"] == "football_rating"
    # one-sided: the first goal is priced OVER only
    assert (FIRST_GOAL, "1", 0.5, "UNDER") not in by
    nikt = by.get((FIRST_GOAL, "nikt", 0.5, "OVER"))
    if 0.05 <= want["nikt"] <= 0.95:
        assert nikt is not None and nikt["p_central"] == round(want["nikt"], 4)
    else:  # outside the model's resolution: no row
        assert nikt is None
    p_red = rates.p_over(RED_CARDS, 1, 0.5)
    assert p_red is not None
    assert by[(RED_CARDS, "", 0.5, "OVER")]["p_central"] == round(p_red, 4)
    assert by[(RED_CARDS, "", 0.5, "UNDER")]["p_central"] == round(1 - p_red, 4)
    assert by[(RED_CARDS, "", 0.5, "UNDER")]["offered_odds"] == 1.11
    # line 2.5 was never measured: no row
    assert not any(k[0] == PENALTIES and k[2] == 2.5 for k in by)
    for r in rows:
        assert r["incident_rule"] == epochs.FOOTBALL_INCIDENT_MARKETS
        assert r["sample_size"] == 0 and r["bar_reason"] == "rating_only"
        assert r["verdict"] != "VALUE"
        assert any(n.startswith("FOOTBALL_INCIDENT_MARKETS") for n in r["notes"])
        assert any(n.startswith("UNFITTED_CONSTANTS") for n in r["notes"])
    # the price is beside p, never in it
    assert by[(PENALTIES, "", 0.5, "OVER")]["market_p"] is not None


def test_no_rating_no_first_goal_row_but_the_rates_still_price() -> None:
    rows = [
        r
        for r in _sheet(IncidentPricing(_rates(), CFG), None)
        if r["market"] in INCIDENT_MARKETS
    ]
    assert {r["market"] for r in rows} == {RED_CARDS, PENALTIES}
    rung = PricedRung(
        market=FIRST_GOAL,
        subject="1",
        line=0.5,
        over_odds=1.8,
        under_odds=None,
        fetched_at_utc=PRE_KICKOFF,
    )
    out, skipped = incident_rows(
        _fixture_model(), rung, None, IncidentPricing(_rates(), CFG), {}, True
    )
    assert out == [] and skipped[0][1] == GapReason.NOT_RATED


def test_unlinked_first_goal_carries_the_refusal_note() -> None:
    from bet.sofa.confidence import has_cross_league_unlinked_note

    fc = _forecast(away_league=5)
    assert fc.fixture_link() == fr.UNLINKED
    rung = PricedRung(
        market=FIRST_GOAL,
        subject="1",
        line=0.5,
        over_odds=1.8,
        under_odds=None,
        fetched_at_utc=PRE_KICKOFF,
    )
    out, _ = incident_rows(
        _fixture_model(), rung, fc, IncidentPricing(_rates(), CFG), {}, True
    )
    assert len(out) == 1 and has_cross_league_unlinked_note(out[0].notes)


# --- CONFIDENCE: no curve, its own lines -> NO_LINE_EVIDENCE --------------------


# The keys that passed the one-sided holdout gate and were installed
# 2026-10-15 00:17Z (docs/sofa/evidence/new_market_curves_2026-10-15.md);
# every other direction of these markets has no curve.
INSTALLED_INCIDENT_KEYS = {
    (FIRST_GOAL, "OVER"), (PENALTIES, "UNDER"), (RED_CARDS, "UNDER")}


def test_installed_curves_are_the_gated_keys_only() -> None:
    cal = Calibration.load()
    for market in INCIDENT_MARKETS:
        for direction in ("OVER", "UNDER"):
            # 0.76: inside every installed curve (first goal's ends at 0.825)
            hit = cal.realised(market, 0.76, "football", direction)
            if (market, direction) in INSTALLED_INCIDENT_KEYS:
                assert hit is not None and hit[1] == f"market:{market}|{direction}"
            else:
                assert hit is None, (market, direction)


def test_confidence_refuses_the_leg_no_line_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.sofa import run_confidence
    from tests.sofa.test_locked_print import _fixture as base_fixture

    day = "2026-10-15"
    t0 = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
    ko = "2026-10-15T18:00:00Z"
    run = tmp_path / day
    run.mkdir()

    def z(t: datetime) -> str:
        return t.isoformat().replace("+00:00", "Z")

    fx = {**base_fixture(1), "kickoff_utc": ko, "superbet_kickoff_utc": ko}
    (run / "02_fixtures.json").write_text(json.dumps([fx]))
    (run / "03_samples.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 1,
                    "readiness": "READY",
                    "gaps": [],
                    "players": {},
                    "metrics": {},
                }
            ]
        )
    )
    row = {
        "sofascore_event_id": 1,
        "sport": "football",
        "market": PENALTIES,
        "subject": "",
        "line": 0.5,
        "direction": "UNDER",
        "sample_size": 0,
        "sample_mean": 0.0,
        "sample_sd": 0.0,
        "centre": 0.78,
        "p_central": 0.78,
        "market_p": 0.67,
        "ladder_centre": None,
        "ladder_sigma": None,
        "p_bar": 0.78,
        "bar_reason": "rating_only",
        "required_odds": 1.3,
        "offered_odds": 1.37,
        "edge": 0.11,
        "surplus": 0.07,
        "verdict": "LEAN",
        "notes": ["FOOTBALL_INCIDENT_MARKETS: test"],
        "epoch": "stats_only",
        "forecast_p": 0.78,
        "forecast_source": "league_rate",
        "incident_rule": epochs.FOOTBALL_INCIDENT_MARKETS,
    }
    (run / "05_sheet.json").write_text(json.dumps([row]))
    (run / "vetoes.json").write_text("[]")
    (run / "04_offer.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 1,
                    "status": "PRICED",
                    "unmapped_markets": [],
                    "price_collisions": [],
                    "rungs": [
                        {
                            "market": PENALTIES,
                            "subject": "",
                            "line": 0.5,
                            "over_odds": 2.82,
                            "under_odds": 1.37,
                            "fetched_at_utc": z(t0 - timedelta(minutes=1)),
                        }
                    ],
                }
            ]
        )
    )
    monkeypatch.setenv("SOFA_NOW", z(t0))
    # without the penalties curve (installed 2026-10-15): no curve, no lines
    cal = calibration_without(tmp_path, [PENALTIES])
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_confidence.py", "--date", day, "--runs-dir", str(tmp_path),
         "--calibration", str(cal)],
    )
    assert run_confidence.main() == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["metrics"]["refused"] == {"NO_LINE_EVIDENCE": 1}
    doc = json.loads((run / "08_confidence.json").read_text())
    assert doc["singles"] == [] and doc["legs"] == []


# --- SETTLE ------------------------------------------------------------------------


def _event(
    home: dict[str, int], away: dict[str, int], code: int = 100
) -> dict[str, Any]:
    return {
        "status": {"type": "finished", "description": "Ended", "code": code},
        "homeScore": home,
        "awayScore": away,
    }


EV_1_1 = _event(
    {"current": 1, "period1": 0, "period2": 1, "normaltime": 1},
    {"current": 1, "period1": 1, "period2": 0, "normaltime": 1},
)
INC_1_1 = {
    "incidents": [
        _goal(70, 1, 1, True),
        _goal(12, 0, 1, False, cls="penalty"),
        _card(80, "red", True),
        SUB,
    ]
}


@pytest.mark.parametrize(
    "market,subject,line,direction,value,outcome",
    [
        (FIRST_GOAL, "2", 0.5, "OVER", 1.0, "WIN"),
        (FIRST_GOAL, "1", 0.5, "OVER", 0.0, "LOSS"),
        (FIRST_GOAL, "nikt", 0.5, "OVER", 0.0, "LOSS"),
        (RED_CARDS, "", 0.5, "UNDER", 1.0, "LOSS"),
        (RED_CARDS, "", 1.5, "UNDER", 1.0, "WIN"),
        (PENALTIES, "", 0.5, "OVER", 1.0, "WIN"),
    ],
)
def test_settle_reads_the_regular_time_incidents(
    market: str, subject: str, line: float, direction: str, value: float, outcome: str
) -> None:
    row = {"market": market, "subject": subject, "line": line, "direction": direction}
    assert _settle_incident(row, EV_1_1, INC_1_1) == (value, outcome)
    assert settle_value(value, line, direction) == outcome


def test_settle_refuses_a_partial_feed_and_an_unreadable_list() -> None:
    partial = {"incidents": [_goal(70, 1, 1, True), _goal(12, 0, 1, False)]}
    row = {"market": RED_CARDS, "subject": "", "line": 0.5, "direction": "UNDER"}
    assert _settle_incident(row, EV_1_1, partial) == (
        "red_cards_total:INCIDENTS_PARTIAL_FEED"
    )
    # the first goal needs no full feed
    fg = {"market": FIRST_GOAL, "subject": "2", "line": 0.5, "direction": "OVER"}
    assert _settle_incident(fg, EV_1_1, partial) == (1.0, "WIN")
    assert _settle_incident(fg, EV_1_1, None) == "first_goal:INCIDENTS_UNREADABLE"
    assert incident_value("goals_total", "", EV_1_1, INC_1_1) == (
        "NOT_AN_INCIDENT_MARKET"
    )


def test_regrade_grades_like_settle() -> None:
    from scripts.sofa.regrade_settled import grade_live

    row = {
        "market": PENALTIES,
        "subject": "",
        "line": 0.5,
        "direction": "OVER",
        "sport": "football",
    }
    assert grade_live(row, EV_1_1, None, None, json.dumps(INC_1_1)) == (1.0, "WIN")


def test_the_measurement_reads_with_the_same_reader() -> None:
    from scripts.sofa import measure_football_incidents as m

    assert m.read_incidents is read_incidents
    assert m.band_index is band_index
    assert m.wilson_lower(80, 100) == pytest.approx(0.7112, abs=1e-3)
