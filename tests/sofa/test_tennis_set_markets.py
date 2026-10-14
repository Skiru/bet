"""The tennis set winner and exact sets score from the as-of rating, behind
epochs.TENNIS_SET_MARKETS_FROM_UTC (None). Offline and fast.

Evidence: docs/sofa/evidence/football_incidents_tennis_sets_2026-10-14.md.
The Superbet shapes are the real ones (tests/sofa/golden/
offer_mappable_items.json, Zverev - Bublik, fetched 2026-10-12): "X. set -
zwycięzca" "1. set - Alexander Zverev" 1.44 / "1. set - Alexander Bublik"
2.62 (set 2 alike); "Dokładny wynik" 2:0 1.95 / 2:1 3.60 / 0:2 5.0 / 1:2 5.5.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import offer as offer_mod
from bet.sofa.confidence import OWN_CURVE_ONLY, Calibration, direction_key
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    GapReason,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.line_evidence import LineEvidence
from bet.sofa.offer import classify_odd
from bet.sofa.samples import metrics_from_offer
from bet.sofa.tennis_rating import MatchForecast, Outcome
from bet.sofa.tennis_sets import (
    SET1_WON_FOR,
    SET2_WON_FOR,
    SET_MARKETS,
    SET_SCORE,
    classify_set_market,
    flip,
    score_probs,
    set_value,
    set_win_p,
    split_score_subject,
    won_match,
)
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS
from scripts.sofa.run_settle import _settle_set_market
from scripts.sofa.run_sheet import process_fixture, set_market_rows, sheet_row_json
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


def _item(market: str, selection: str, price: float) -> dict[str, Any]:
    return {
        "marketName": market,
        "name": selection,
        "offerStateId": 1,
        "price": price,
        "status": "active",
    }


# --- the switch ------------------------------------------------------------------


def test_switch_is_off_and_reads_the_day_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert epochs.TENNIS_SET_MARKETS_FROM_UTC is None
    assert epochs.TENNIS_SET_MARKETS == "tennis_set_markets_v1"
    late = datetime(2027, 1, 1, tzinfo=UTC)
    assert not epochs.tennis_set_markets("2027-01-01", late)
    monkeypatch.setattr(
        epochs, "TENNIS_SET_MARKETS_FROM_UTC", datetime(2026, 10, 16, tzinfo=UTC)
    )
    assert epochs.tennis_set_markets(
        "2026-10-16", datetime(2026, 10, 16, 1, tzinfo=UTC)
    )
    assert not epochs.tennis_set_markets("2026-10-15", late)
    assert not epochs.tennis_set_markets(
        "2026-10-16", datetime(2026, 10, 15, 23, tzinfo=UTC)
    )


# --- OFFER -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "market,selection,expected",
    [
        (
            "X. set - zwycięzca",
            "1. set - Alexander Zverev",
            (SET1_WON_FOR, ZVEREV, 0.5, "OVER"),
        ),
        (
            "X. set - zwycięzca",
            "1. set - Alexander Bublik",
            (SET1_WON_FOR, ZVEREV, 0.5, "UNDER"),
        ),
        (
            "X. set - zwycięzca",
            "2. set - Alexander Bublik",
            (SET2_WON_FOR, ZVEREV, 0.5, "UNDER"),
        ),
        ("Dokładny wynik", "2:0", (SET_SCORE, f"{ZVEREV} 2:0", 0.5, "OVER")),
        ("Dokładny wynik", "1:2", (SET_SCORE, f"{ZVEREV} 1:2", 0.5, "OVER")),
    ],
)
def test_classify_reads_the_set_names(
    market: str, selection: str, expected: tuple[str, str, float, str]
) -> None:
    assert classify_set_market(market, selection, NAMES) == expected


@pytest.mark.parametrize(
    "market,selection",
    [
        ("X. set - zwycięzca", "3. set - Alexander Zverev"),
        ("X. set - zwycięzca", "1. set - Roger Federer"),
        ("1. set - zwycięzca & liczba gemów", "Alexander Zverev & poniżej 9.5"),
        ("Dokładny wynik", "3:0"),
        ("Dokładny wynik", "6:4"),
        ("1. set - dokładny wynik", "6:4"),
        (
            "Dokładny wynik - wynik po 3 punktach w 1. gemie serwisowym "
            "Alexander Zverev",
            "40:0",
        ),
        ("Zwycięzcy setów", "1/1"),
    ],
)
def test_classify_refuses_other_shapes(market: str, selection: str) -> None:
    assert classify_set_market(market, selection, NAMES) is None


def test_classify_needs_both_listing_names() -> None:
    assert classify_set_market("Dokładny wynik", "2:0", (ZVEREV,)) is None
    assert (
        classify_set_market("X. set - zwycięzca", "1. set - Alexander Zverev", ())
        is None
    )


def test_classify_odd_reads_them_only_when_asked() -> None:
    item = _item("Dokładny wynik", "2:0", 1.95)
    assert classify_odd(item) == (None, "Dokładny wynik")
    assert classify_odd(item, (), False, NAMES, False, False, False, False, True) == (
        (SET_SCORE, f"{ZVEREV} 2:0", 0.5, "OVER"),
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
            tennis_sets=on,
        )
        offers = fetcher.fetch_offers(fixtures)
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return {o.sofascore_event_id: o.model_dump(mode="json") for o in offers}


def test_switch_off_offer_is_byte_identical_to_the_golden() -> None:
    golden = (GOLDEN_DIR / "offer_mappable_off.json").read_text(encoding="utf-8")
    assert dumps(offer_dump(False)) + "\n" == golden
    assert dumps(list(_offers(False).values())) + "\n" == golden


def test_switch_on_offer_adds_the_rungs_to_tennis_only() -> None:
    data = payloads()
    football_id = int(data["football"]["eventId"])
    tennis_id = int(data["tennis"]["eventId"])
    off, on = _offers(False), _offers(True)
    # the football "Dokładny wynik" is another question: untouched
    assert on[football_id] == off[football_id]
    new = {
        (r["market"], r["subject"]): (r["over_odds"], r["under_odds"])
        for r in on[tennis_id]["rungs"]
        if r["market"] in SET_MARKETS
    }
    assert new == {
        (SET1_WON_FOR, ZVEREV): (1.44, 2.62),
        (SET2_WON_FOR, ZVEREV): (1.44, 2.62),
        (SET_SCORE, f"{ZVEREV} 2:0"): (1.95, None),
        (SET_SCORE, f"{ZVEREV} 2:1"): (3.6, None),
        (SET_SCORE, f"{ZVEREV} 0:2"): (5.0, None),
        (SET_SCORE, f"{ZVEREV} 1:2"): (5.5, None),
    }
    rest = [r for r in on[tennis_id]["rungs"] if r["market"] not in SET_MARKETS]
    assert rest == off[tennis_id]["rungs"]
    gone = set(off[tennis_id]["unmapped_markets"]) - set(
        on[tennis_id]["unmapped_markets"]
    )
    assert gone == {"X. set - zwycięzca", "Dokładny wynik"}


def test_samples_never_builds_a_set_sample() -> None:
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        unmapped_markets=[],
        rungs=[
            PricedRung(
                market=SET1_WON_FOR,
                subject=ZVEREV,
                line=0.5,
                over_odds=1.44,
                under_odds=2.62,
                fetched_at_utc=FROZEN,
            )
        ],
    )
    assert metrics_from_offer(offer) == set()
    assert SET_MARKETS <= RATING_ONLY_MARKETS
    assert SET_MARKETS <= OWN_CURVE_ONLY


# --- price -------------------------------------------------------------------------


def _o(
    set1: tuple[int, int], set2: tuple[int, int], set3: tuple[int, int] | None = None
) -> Outcome:
    games_for = set1[0] + set2[0] + (set3[0] if set3 else 0)
    games_against = set1[1] + set2[1] + (set3[1] if set3 else 0)
    return Outcome(
        0.5, games_for, games_against, 3 if set3 else 2, 0, set1, set2, set3=set3
    )


POOL = (
    [_o((6, 3), (6, 4))] * 5  # 2:0
    + [_o((6, 3), (3, 6), (6, 2))] * 2  # 2:1
    + [_o((3, 6), (6, 3), (2, 6))] * 2  # 1:2
    + [_o((4, 6), (3, 6))] * 1  # 0:2
)


def test_neighbour_shares_are_the_measurements() -> None:
    from scripts.sofa import measure_tennis_outcome_model as m

    assert set_win_p(POOL, 1) == pytest.approx((7 + 0.5) / 11)
    assert set_win_p(POOL, 2) == pytest.approx((7 + 0.5) / 11)
    probs = score_probs(POOL)
    assert probs is not None
    assert probs == pytest.approx(
        {"2:0": 5.5 / 12, "2:1": 2.5 / 12, "1:2": 2.5 / 12, "0:2": 1.5 / 12}
    )
    assert sum(probs.values()) == pytest.approx(1.0)
    assert m.smoothed(7, 10, 2) == set_win_p(POOL, 1)
    for o in POOL:
        assert won_match(o) == m._won_match(o)
    assert set_win_p([], 1) is None and score_probs([]) is None


def _forecast(pool: list[Outcome] = POOL) -> MatchForecast:
    return MatchForecast(0.7, tuple(pool), (), 40, 25, table_scope="tier_gender")


def _sheet(on: bool, rating: MatchForecast | None) -> list[dict[str, Any]]:
    fetched = FROZEN - timedelta(hours=1)
    obs = [
        Observation(
            sofascore_event_id=1000 + i,
            match_date_utc=FROZEN - timedelta(days=i + 1),
            value=float(v),
            opponent=f"O{i}",
            venue="home",
            competition_id=3,
            season_id=1,
        )
        for i, v in enumerate([20, 22, 18, 24, 21, 19, 23, 20, 22, 21])
    ]
    samples = FixtureSamples(
        sofascore_event_id=77,
        readiness="READY",
        gaps=[],
        metrics={
            "games_total": MetricSample(
                metric="games_total", side_a=obs, side_b=obs, h2h=[]
            )
        },
    )
    rungs = [
        PricedRung(
            market="games_total",
            subject="",
            line=21.5,
            over_odds=1.8,
            under_odds=1.95,
            fetched_at_utc=fetched,
        ),
        PricedRung(
            market=SET1_WON_FOR,
            subject=ZVEREV,
            line=0.5,
            over_odds=1.44,
            under_odds=2.62,
            fetched_at_utc=fetched,
        ),
        PricedRung(
            market=SET2_WON_FOR,
            subject=BUBLIK,
            line=0.5,
            over_odds=2.62,
            under_odds=1.44,
            fetched_at_utc=fetched,
        ),
        PricedRung(
            market=SET_SCORE,
            subject=f"{ZVEREV} 2:0",
            line=0.5,
            over_odds=1.95,
            under_odds=None,
            fetched_at_utc=fetched,
        ),
        PricedRung(
            market=SET_SCORE,
            subject=f"{BUBLIK} 1:2",
            line=0.5,
            over_odds=5.5,
            under_odds=None,
            fetched_at_utc=fetched,
        ),
    ]
    offer = FixtureOffer(
        sofascore_event_id=77, status="PRICED", unmapped_markets=[], rungs=rungs
    )
    rows, _ = process_fixture(
        fixture("tennis", "77"),
        samples,
        offer,
        baselines={},
        reliability={},
        engine_constants={},
        vetoes=[],
        config=SofaConfig(),
        rating=rating,
        stats_only=True,
        set_markets_on=on,
    )
    return [sheet_row_json(r) for r in rows]


def test_switch_off_sheet_is_unchanged() -> None:
    off = _sheet(False, _forecast())
    assert off and all(r["market"] not in SET_MARKETS for r in off)
    assert all("set_market_rule" not in r for r in off)
    on = _sheet(True, _forecast())
    assert [r for r in on if r["market"] not in SET_MARKETS] == off


def test_set_rows_carry_the_neighbour_p() -> None:
    rows = {
        (r["market"], r["subject"], r["direction"]): r
        for r in _sheet(True, _forecast())
        if r["market"] in SET_MARKETS
    }
    p1 = (7 + 0.5) / 11
    assert rows[(SET1_WON_FOR, ZVEREV, "OVER")]["p_central"] == round(p1, 4)
    assert rows[(SET1_WON_FOR, ZVEREV, "UNDER")]["p_central"] == round(1 - p1, 4)
    # Bublik (the away player) listed first: his set-2 win is 1 - p_home
    assert rows[(SET2_WON_FOR, BUBLIK, "OVER")]["p_central"] == round(1 - p1, 4)
    assert rows[(SET_SCORE, f"{ZVEREV} 2:0", "OVER")]["p_central"] == round(5.5 / 12, 4)
    # "Bublik 1:2" read from Zverev's side is 2:1
    assert rows[(SET_SCORE, f"{BUBLIK} 1:2", "OVER")]["p_central"] == round(2.5 / 12, 4)
    assert (SET_SCORE, f"{ZVEREV} 2:0", "UNDER") not in rows  # one-sided
    for r in rows.values():
        assert r["set_market_rule"] == epochs.TENNIS_SET_MARKETS
        assert r["sample_size"] == 0 and r["bar_reason"] == "rating_only"
        assert r["forecast_source"] == "tennis_rating"
        assert r["verdict"] != "VALUE"
        assert any(n.startswith("TENNIS_SET_MARKETS") for n in r["notes"])


def test_no_rating_or_no_side_no_row() -> None:
    rung = PricedRung(
        market=SET1_WON_FOR,
        subject=ZVEREV,
        line=0.5,
        over_odds=1.44,
        under_odds=2.62,
        fetched_at_utc=FROZEN,
    )
    out, skipped = set_market_rows(fixture("tennis", "77"), rung, None, {}, True)
    assert out == [] and skipped[0][1] == GapReason.NOT_RATED
    stranger = rung.model_copy(update={"subject": "Roger Federer"})
    out, skipped = set_market_rows(
        fixture("tennis", "77"), stranger, _forecast(), {}, True
    )
    assert out == [] and skipped[0][1] == GapReason.NO_MATCHING_EVENT


# --- CONFIDENCE --------------------------------------------------------------------


def test_installed_curves_and_evidence_give_the_markets_nothing() -> None:
    cal = Calibration.load()
    evidence = LineEvidence.load(v2=True, bucket_deff=True)
    for market in SET_MARKETS:
        assert cal.realised(market, 0.8, "tennis", "OVER") is None
        key = direction_key(market, "OVER")
        assert evidence.read("tennis", key, 0.8, None, 1.3) is None


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

    fx = {
        **base_fixture(1),
        "kickoff_utc": ko,
        "superbet_kickoff_utc": ko,
        "sport": "tennis",
    }
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
        "sport": "tennis",
        "market": SET1_WON_FOR,
        "subject": fx["home_name"],
        "line": 0.5,
        "direction": "OVER",
        "sample_size": 0,
        "sample_mean": 0.0,
        "sample_sd": 0.0,
        "centre": 0.8,
        "p_central": 0.8,
        "market_p": 0.66,
        "ladder_centre": None,
        "ladder_sigma": None,
        "p_bar": 0.8,
        "bar_reason": "rating_only",
        "required_odds": 1.3,
        "offered_odds": 1.44,
        "edge": 0.14,
        "surplus": 0.1,
        "verdict": "LEAN",
        "notes": ["TENNIS_SET_MARKETS: test"],
        "epoch": "stats_only",
        "forecast_p": 0.8,
        "forecast_source": "tennis_rating",
        "set_market_rule": epochs.TENNIS_SET_MARKETS,
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
                            "market": SET1_WON_FOR,
                            "subject": fx["home_name"],
                            "line": 0.5,
                            "over_odds": 1.44,
                            "under_odds": 2.62,
                            "fetched_at_utc": z(t0 - timedelta(minutes=1)),
                        }
                    ],
                }
            ]
        )
    )
    monkeypatch.setenv("SOFA_NOW", z(t0))
    monkeypatch.setattr(
        sys, "argv", ["run_confidence.py", "--date", day, "--runs-dir", str(tmp_path)]
    )
    assert run_confidence.main() == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["metrics"]["refused"] == {"NO_LINE_EVIDENCE": 1}
    doc = json.loads((run / "08_confidence.json").read_text())
    assert doc["singles"] == [] and doc["legs"] == []


# --- SETTLE ------------------------------------------------------------------------


def _event(home: list[int], away: list[int]) -> dict[str, Any]:
    hs = {f"period{i + 1}": v for i, v in enumerate(home)}
    as_ = {f"period{i + 1}": v for i, v in enumerate(away)}
    return {
        "status": {"type": "finished", "code": 100},
        "winnerCode": 1,
        "homeScore": {
            "current": sum(h > a for h, a in zip(home, away, strict=True)),
            **hs,
        },
        "awayScore": {
            "current": sum(a > h for h, a in zip(home, away, strict=True)),
            **as_,
        },
    }


FX = {"home_name": ZVEREV, "away_name": BUBLIK, "sport": "tennis"}
# Zverev (home) loses set 1, wins 2 and 3: 2:1
EV = _event([4, 6, 7], [6, 3, 5])


@pytest.mark.parametrize(
    "market,subject,direction,value,outcome",
    [
        (SET1_WON_FOR, ZVEREV, "OVER", 0.0, "LOSS"),
        (SET1_WON_FOR, ZVEREV, "UNDER", 0.0, "WIN"),
        (SET2_WON_FOR, ZVEREV, "OVER", 1.0, "WIN"),
        (SET1_WON_FOR, BUBLIK, "OVER", 1.0, "WIN"),
        (SET_SCORE, f"{ZVEREV} 2:1", "OVER", 1.0, "WIN"),
        (SET_SCORE, f"{BUBLIK} 1:2", "OVER", 1.0, "WIN"),
        (SET_SCORE, f"{ZVEREV} 2:0", "OVER", 0.0, "LOSS"),
    ],
)
def test_settle_reads_the_set_scores(
    market: str, subject: str, direction: str, value: float, outcome: str
) -> None:
    row = {"market": market, "subject": subject, "line": 0.5, "direction": direction}
    assert _settle_set_market(row, EV, FX) == (value, outcome)


def test_settle_refuses_what_it_cannot_read() -> None:
    row = {"market": SET_SCORE, "subject": "nonsense", "line": 0.5, "direction": "OVER"}
    assert _settle_set_market(row, EV, FX) == "set_score:UNKNOWN_SUBJECT"
    row = {
        "market": SET1_WON_FOR,
        "subject": "Roger Federer",
        "line": 0.5,
        "direction": "OVER",
    }
    assert _settle_set_market(row, EV, FX) == "SUBJECT_NOT_MATCHED"
    assert _settle_set_market(row, EV, None) == "NO_FIXTURE"
    assert set_value(SET1_WON_FOR, True, None, _event([6], [3])) == "SET_SCORES_ABSENT"
    bo5 = _event([6, 6, 3, 6], [3, 4, 6, 2])
    assert set_value(SET_SCORE, True, "2:0", bo5) == "NOT_BEST_OF_THREE"


def test_regrade_grades_like_settle() -> None:
    from scripts.sofa.regrade_settled import grade_live

    row = {
        "market": SET2_WON_FOR,
        "subject": ZVEREV,
        "line": 0.5,
        "direction": "OVER",
        "sport": "tennis",
    }
    assert grade_live(row, EV, FX, None, None) == (1.0, "WIN")


def test_score_subject_helpers() -> None:
    assert split_score_subject(f"{ZVEREV} 2:1") == (ZVEREV, "2:1")
    assert split_score_subject("2:1") is None
    assert flip("2:1") == "1:2"
