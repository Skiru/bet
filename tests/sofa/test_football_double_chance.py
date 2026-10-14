"""Audit D1, double chance only: the football "Podwójna szansa" from the pure
rating, behind epochs.FOOTBALL_RESULT_MARKETS_FROM_UTC (None). Offline and
fast. Plan: docs/sofa/evidence/football_result_phase_2026-10-13.md,
"Decyzja i plan implementacji (DC; DNB czeka)".

The Superbet shape is the real one (tests/sofa/golden/offer_mappable_items.json,
Villarreal - Napoli, fetched 2026-10-12): "Podwójna szansa" 1X 1.35 / X2 1.66
/ 12 1.26, "Mecz" 1 2.15 / X 3.60 / 2 3.05.
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
from bet.sofa.confidence import (
    OWN_CURVE_ONLY,
    Calibration,
    direction_key,
    has_cross_league_unlinked_note,
    overround,
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
from bet.sofa.engine import has_calibratable_model
from bet.sofa.football_result import (
    DOUBLE_CHANCE,
    SELECTIONS,
    ResultConfig,
    classify_result,
    count_pmf,
    load_config,
    market_probs,
    result_probs,
    score_grid,
    selection_holds,
)
from bet.sofa.line_evidence import LineEvidence
from bet.sofa.metrics import double_chance_value
from bet.sofa.offer import classify_odd
from bet.sofa.samples import metrics_from_offer
from bet.sofa.settle import settle as settle_value
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS
from scripts.sofa.run_settle import _settle_double_chance
from scripts.sofa.run_sheet import (
    double_chance_rows,
    process_fixture,
    sheet_row_json,
)
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
# before tests.sofa.test_player_markets._fixture()'s start: not in-play
PRE_KICKOFF = datetime(2026, 9, 22, tzinfo=UTC)


def _item(market: str, selection: str, price: float) -> dict[str, Any]:
    return {"marketName": market, "name": selection, "offerStateId": 1,
            "price": price, "status": "active"}


# --- the switch ------------------------------------------------------------------


def test_switch_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # operator 2026-10-14: on from 14:20Z into the built day (mixed)
    assert epochs.FOOTBALL_RESULT_MARKETS_FROM_UTC == datetime(2026, 10, 14, 14, 20, tzinfo=UTC)
    assert not epochs.football_result_markets("2026-10-13", datetime(2027, 1, 1, tzinfo=UTC))
    assert not epochs.football_result_markets("2026-10-14", datetime(2026, 10, 14, 14, 19, tzinfo=UTC))
    assert epochs.football_result_markets("2026-10-14", datetime(2026, 10, 14, 14, 20, tzinfo=UTC))
    monkeypatch.setattr(epochs, "FOOTBALL_RESULT_MARKETS_FROM_UTC", None)
    assert epochs.FOOTBALL_RESULT_MARKETS == "result_markets_v1"
    late = datetime(2027, 1, 1, tzinfo=UTC)
    assert not epochs.football_result_markets("2027-01-01", late)
    monkeypatch.setattr(epochs, "FOOTBALL_RESULT_MARKETS_FROM_UTC",
                        datetime(2026, 10, 16, tzinfo=UTC))
    assert epochs.football_result_markets(
        "2026-10-16", datetime(2026, 10, 16, 1, tzinfo=UTC))
    assert not epochs.football_result_markets("2026-10-15", late)
    assert not epochs.football_result_markets(
        "2026-10-16", datetime(2026, 10, 15, 23, tzinfo=UTC))


# --- OFFER: the names ---------------------------------------------------------------


@pytest.mark.parametrize("market,selection,expected", [
    ("Podwójna szansa", "1X", (DOUBLE_CHANCE, "1X", 0.5, "OVER")),
    ("Podwójna szansa", "X2", (DOUBLE_CHANCE, "X2", 0.5, "OVER")),
    ("Podwójna szansa", "12", (DOUBLE_CHANCE, "12", 0.5, "OVER")),
    # the 1X2 outcome a selection leaves out is its UNDER
    ("Mecz", "2", (DOUBLE_CHANCE, "1X", 0.5, "UNDER")),
    ("Mecz", "1", (DOUBLE_CHANCE, "X2", 0.5, "UNDER")),
    ("Mecz", "X", (DOUBLE_CHANCE, "12", 0.5, "UNDER")),
])
def test_classify_result_reads_the_full_match_names(
        market: str, selection: str, expected: tuple[str, str, float, str]) -> None:
    assert classify_result(market, selection) == expected


@pytest.mark.parametrize("market,selection", [
    ("1.połowa - podwójna szansa", "1X"),
    ("2.połowa - podwójna szansa", "X2"),
    ("1. połowa/mecz - podwójna szansa", "1/1 lub X/1"),
    ("Podwójna szansa & liczba goli (2.5)", "1X & powyżej 2.5"),
    ("Podwójna szansa & obie drużyny strzelą", "1X & tak"),
    ("Mecz & liczba goli (2.5)", "Villarreal & powyżej 2.5"),
    ("Podwójna szansa", "1"),
    ("Mecz", "1X"),
    ("Zakład bez remisu", "1"),
])
def test_classify_result_refuses_halves_combinations_and_other_shapes(
        market: str, selection: str) -> None:
    assert classify_result(market, selection) is None


def test_classify_odd_reads_the_double_chance_only_when_asked() -> None:
    item = _item("Podwójna szansa", "1X", 1.35)
    assert classify_odd(item) == (None, "Podwójna szansa")
    assert classify_odd(item, (), True, (), True) == (None, "Podwójna szansa")
    assert classify_odd(item, (), False, (), False, True) == (
        (DOUBLE_CHANCE, "1X", 0.5, "OVER"), None)


def _offers(football_result: bool) -> dict[int, dict[str, Any]]:
    data = payloads()
    fixtures = [fixture(sport, str(p["eventId"])) for sport, p in sorted(data.items())]
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        fetcher = offer_mod.OfferFetcher(
            _Client(data), ampersand_subjects=True, mappable_families=False,
            football_result=football_result)
        offers = fetcher.fetch_offers(fixtures)
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return {o.sofascore_event_id: o.model_dump(mode="json") for o in offers}


def test_switch_off_offer_is_byte_identical_to_the_golden() -> None:
    golden = (GOLDEN_DIR / "offer_mappable_off.json").read_text(encoding="utf-8")
    assert dumps(offer_dump(False)) + "\n" == golden
    assert dumps(list(_offers(False).values())) + "\n" == golden


def test_switch_on_offer_adds_three_two_sided_rungs_to_football_only() -> None:
    data = payloads()
    football_id = int(data["football"]["eventId"])
    tennis_id = int(data["tennis"]["eventId"])
    off, on = _offers(False), _offers(True)
    assert on[tennis_id] == off[tennis_id]
    dc = {r["subject"]: r for r in on[football_id]["rungs"]
          if r["market"] == DOUBLE_CHANCE}
    assert set(dc) == set(SELECTIONS)
    # DC price OVER, the left-out "Mecz" outcome UNDER
    assert (dc["1X"]["over_odds"], dc["1X"]["under_odds"]) == (1.35, 3.05)
    assert (dc["X2"]["over_odds"], dc["X2"]["under_odds"]) == (1.66, 2.15)
    assert (dc["12"]["over_odds"], dc["12"]["under_odds"]) == (1.26, 3.6)
    for r in dc.values():
        assert r["line"] == 0.5
        assert overround(r["over_odds"], r["under_odds"]) is not None
    assert overround(1.35, 3.05) == pytest.approx(1 / 1.35 + 1 / 3.05 - 1)
    # every other rung unchanged
    rest = [r for r in on[football_id]["rungs"] if r["market"] != DOUBLE_CHANCE]
    assert rest == off[football_id]["rungs"]
    # the two full-match names leave unmapped; halves and combinations stay
    unmapped_off = set(off[football_id]["unmapped_markets"])
    unmapped_on = set(on[football_id]["unmapped_markets"])
    assert {"Podwójna szansa", "Mecz"} <= unmapped_off
    assert unmapped_off - unmapped_on == {"Podwójna szansa", "Mecz"}
    assert "1.połowa - podwójna szansa" in unmapped_on
    assert "Podwójna szansa & liczba goli (2.5)" in unmapped_on


def _fetch_one(odds: list[dict[str, Any]], sport: str = "football") -> FixtureOffer:
    fx = fixture(sport, "1")
    payload = {"eventId": "1", "matchName": "Villarreal·Napoli", "odds": odds}

    class C:
        def event_odds(self, _eid: str) -> dict[str, Any]:
            return payload

    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        out = offer_mod.OfferFetcher(C(), football_result=True).fetch_offers([fx])
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return out[0]


def test_a_result_price_alone_is_no_double_chance_offer() -> None:
    out = _fetch_one([_item("Mecz", "1", 2.15), _item("Mecz", "X", 3.6)])
    assert out.rungs == []
    assert out.unmapped_markets == []


def test_a_double_chance_without_the_result_market_is_one_sided() -> None:
    out = _fetch_one([_item("Podwójna szansa", "1X", 1.35)])
    assert [(r.market, r.subject, r.over_odds, r.under_odds) for r in out.rungs] == [
        (DOUBLE_CHANCE, "1X", 1.35, None)]


def test_a_tennis_fixture_never_reads_the_double_chance() -> None:
    out = _fetch_one([_item("Podwójna szansa", "1X", 1.35)], sport="tennis")
    assert out.rungs == []
    assert out.unmapped_markets == ["Podwójna szansa"]


def test_samples_never_builds_a_double_chance_sample() -> None:
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market=DOUBLE_CHANCE, subject="1X", line=0.5,
                          over_odds=1.35, under_odds=3.05, fetched_at_utc=FROZEN)])
    assert metrics_from_offer(offer) == set()
    assert DOUBLE_CHANCE in RATING_ONLY_MARKETS
    assert DOUBLE_CHANCE in OWN_CURVE_ONLY


# --- the score grid -------------------------------------------------------------------


def test_ported_grid_matches_the_measurement() -> None:
    from scripts.sofa import measure_football_result_model as m

    rng = np.random.default_rng(0)
    lam_h = rng.uniform(0.3, 3.0, 50)
    lam_a = rng.uniform(0.3, 3.0, 50)
    r = np.full(50, 7.586)
    ours = market_probs(score_grid(count_pmf(lam_h, r), count_pmf(lam_a, r)))
    theirs = m.market_probs(m.score_grid(m.count_pmf(lam_h, r), m.count_pmf(lam_a, r)))
    assert np.allclose(ours, theirs.res, atol=1e-12)
    pois = market_probs(score_grid(count_pmf(lam_h, None), count_pmf(lam_a, None)))
    assert np.allclose(pois, m.market_probs(m.score_grid(
        m.count_pmf(lam_h, None), m.count_pmf(lam_a, None))).res, atol=1e-12)


@pytest.mark.parametrize("lh,la", [(1.5, 1.1), (0.4, 2.8), (2.9, 0.3), (1.0, 1.0),
                                   (0.05, 0.05), (4.5, 3.9)])
def test_result_probs_sum_and_range(lh: float, la: float) -> None:
    p = result_probs(lh, la, 7.586)
    assert p["1X"] + p["X2"] + p["12"] == pytest.approx(2.0, abs=1e-9)
    assert p["1"] + p["X"] + p["2"] == pytest.approx(1.0, abs=1e-9)
    for v in p.values():
        assert 0.0 <= v <= 1.0
    assert p["1X"] == pytest.approx(p["1"] + p["X"])


def test_result_probs_moves_with_the_centres() -> None:
    even = result_probs(1.3, 1.3, 7.586)
    assert even["1X"] == pytest.approx(even["X2"], abs=1e-12)
    strong = result_probs(2.2, 0.8, 7.586)
    assert strong["1X"] > even["1X"] and strong["X2"] < even["X2"]
    # the overdispersed grid draws less than the Poisson one at the same means
    pois_draw = float(market_probs(score_grid(
        count_pmf(np.array([1.3]), None), count_pmf(np.array([1.3]), None)))[0, 1])
    assert even["X"] < pois_draw


@pytest.mark.parametrize("lh,la,r", [(0.0, 1.0, 7.0), (1.0, -1.0, 7.0),
                                     (1.0, 1.0, 0.0), (float("nan"), 1.0, 7.0)])
def test_result_probs_refuses_a_bad_input(lh: float, la: float, r: float) -> None:
    with pytest.raises(ValueError):
        result_probs(lh, la, r)


def test_the_installed_config_is_the_measured_r(tmp_path: Path) -> None:
    cfg = load_config()
    assert cfg.nb_r == pytest.approx(7.586)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"nb_r": 0}))
    with pytest.raises(ValueError):
        load_config(bad)
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "absent.json")


# --- SHEET ----------------------------------------------------------------------------


def _book(away_league: int = 1) -> fr.RatingBook:
    """Team 1 scores 3-1 at home in league 1; team 2 draws 1-1 away in
    `away_league` (another league with no link: UNLINKED)."""
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


def _rung(selection: str = "1X", over: float = 1.35,
          under: float | None = 3.05) -> PricedRung:
    return PricedRung(market=DOUBLE_CHANCE, subject=selection, line=0.5,
                      over_odds=over, under_odds=under,
                      fetched_at_utc=PRE_KICKOFF)


def _sheet(result_config: ResultConfig | None,
           forecast: fr.FootballForecast | None) -> list[dict[str, Any]]:
    from tests.sofa.test_player_markets import _fixture

    fetched = PRE_KICKOFF
    obs = [Observation(sofascore_event_id=1000 + i,
                       match_date_utc=FROZEN - timedelta(days=i + 1),
                       value=float(v), opponent=f"O{i}", venue="home",
                       competition_id=1, season_id=1)
           for i, v in enumerate([2, 3, 1, 4, 2, 3, 2, 1, 3, 2])]
    samples = FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={"goals_total": MetricSample(
            metric="goals_total", side_a=obs, side_b=obs, h2h=[])})
    rungs = [
        PricedRung(market="goals_total", subject="", line=2.5,
                   over_odds=1.8, under_odds=1.95, fetched_at_utc=fetched),
        *(_rung(s, o, u) for s, o, u in (("1X", 1.35, 3.05), ("X2", 1.66, 2.15),
                                         ("12", 1.26, 3.6))),
    ]
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED",
                         unmapped_markets=[], rungs=rungs)
    rows, _ = process_fixture(
        _fixture(), samples, offer, baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), football=forecast,
        stats_only=True, result_config=result_config)
    return [sheet_row_json(r) for r in rows]


def test_switch_off_sheet_is_unchanged() -> None:
    off = _sheet(None, _forecast())
    assert off and all(r["market"] != DOUBLE_CHANCE for r in off)
    assert all("result_rule" not in r for r in off)
    on = _sheet(CFG, _forecast())
    assert [r for r in on if r["market"] != DOUBLE_CHANCE] == off


def test_double_chance_rows_carry_the_pure_rating_p() -> None:
    fc = _forecast()
    home = fc.centre("goals_for", "side_a")
    away = fc.centre("goals_for", "side_b")
    assert home is not None and away is not None
    want = result_probs(home[0], away[0], CFG.nb_r)
    rows = {r["subject"]: r for r in _sheet(CFG, fc) if r["market"] == DOUBLE_CHANCE}
    assert set(rows) <= set(SELECTIONS) and rows
    for sel, r in rows.items():
        assert r["direction"] == "OVER"  # the UNDER (a 1X2 outcome) is never priced
        assert r["p_central"] == round(want[sel], 4)
        assert r["forecast_p"] == r["p_central"]
        assert r["forecast_source"] == "football_rating"
        assert r["sample_size"] == 0 and r["bar_reason"] == "rating_only"
        assert r["result_rule"] == epochs.FOOTBALL_RESULT_MARKETS
        assert r["verdict"] != "VALUE"
        assert any(n.startswith("FOOTBALL_RESULT_MARKETS") for n in r["notes"])
        assert any(n.startswith("UNFITTED_CONSTANTS") and "FOOTBALL_RESULT_NB_R" in n
                   for n in r["notes"])
        assert not has_cross_league_unlinked_note(r["notes"])
    # the price is beside p, never in it
    assert rows["1X"]["offered_odds"] == 1.35
    # devigged from the two-sided rung (DC price vs the left-out 1X2 price)
    assert 0.65 < rows["1X"]["market_p"] < 0.75


def test_unlinked_fixture_is_refused_like_every_football_row() -> None:
    fc = _forecast(away_league=5)
    assert fc.fixture_link() == fr.UNLINKED
    out, skipped = double_chance_rows(_fixture_model(), _rung(), fc, CFG, {}, True)
    assert not skipped and len(out) == 1
    assert has_cross_league_unlinked_note(out[0].notes)


def _fixture_model() -> Any:
    from tests.sofa.test_player_markets import _fixture

    return _fixture()


def test_no_rating_no_row() -> None:
    out, skipped = double_chance_rows(_fixture_model(), _rung(), None, CFG, {}, True)
    assert out == [] and skipped[0][1] == GapReason.NOT_RATED
    # a team under MIN_TEAM_MATCHES: no goals centre, no row
    thin = fr.FootballForecast(_book(), 1, 1, 999)
    out, skipped = double_chance_rows(_fixture_model(), _rung(), thin, CFG, {}, True)
    assert out == [] and skipped[0][1] == GapReason.NOT_RATED
    assert all(r["market"] != DOUBLE_CHANCE for r in _sheet(CFG, None))


# --- CONFIDENCE: no curve, its own lines -> NO_LINE_EVIDENCE --------------------


def test_installed_curves_and_evidence_give_double_chance_nothing() -> None:
    assert has_calibratable_model(DOUBLE_CHANCE)
    cal = Calibration.load()
    for p in (0.72, 0.85, 0.93):
        # no own curve, and no pool stands in (OWN_CURVE_ONLY)
        assert cal.realised(DOUBLE_CHANCE, p, "football", "OVER") is None
    evidence = LineEvidence.load(v2=True, bucket_deff=True)
    key = direction_key(DOUBLE_CHANCE, "OVER")
    assert evidence.read("football", key, 0.85, None, 1.35) is None


def test_enough_settled_lines_would_give_a_confidence() -> None:
    from bet.sofa.line_evidence import bucket_label, bucket_of

    key = direction_key(DOUBLE_CHANCE, "OVER")
    doc = {"keys": {"football": {key: {"buckets": {
        bucket_label(bucket_of(0.85)): {"n": 400, "k": 352, "games": 300,
                                        "deff": 1.0}}}}}}
    read = LineEvidence(doc, v2=True, bucket_deff=True).read(
        "football", key, 0.85, None, 1.35)
    assert read is not None and read.source == f"sb:football:{key}"
    assert 0.80 < read.value < 0.88


def test_confidence_refuses_the_leg_no_line_evidence(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
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
    (run / "03_samples.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "readiness": "READY", "gaps": [],
        "players": {}, "metrics": {}}]))
    row = {
        "sofascore_event_id": 1, "sport": "football", "market": DOUBLE_CHANCE,
        "subject": "1X", "line": 0.5, "direction": "OVER", "sample_size": 0,
        "sample_mean": 0.0, "sample_sd": 0.0, "centre": 0.85, "p_central": 0.85,
        "market_p": 0.69, "ladder_centre": None, "ladder_sigma": None,
        "p_bar": 0.85, "bar_reason": "rating_only", "required_odds": 1.2,
        "offered_odds": 1.35, "edge": 0.16, "surplus": 0.1, "verdict": "LEAN",
        "notes": ["FOOTBALL_RESULT_MARKETS: test"], "epoch": "stats_only",
        "forecast_p": 0.85, "forecast_source": "football_rating",
        "result_rule": epochs.FOOTBALL_RESULT_MARKETS,
    }
    (run / "05_sheet.json").write_text(json.dumps([row]))
    (run / "vetoes.json").write_text("[]")
    (run / "04_offer.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "status": "PRICED", "unmapped_markets": [],
        "price_collisions": [],
        "rungs": [{"market": DOUBLE_CHANCE, "subject": "1X", "line": 0.5,
                   "over_odds": 1.35, "under_odds": 3.05,
                   "fetched_at_utc": z(t0 - timedelta(minutes=1))}]}]))
    monkeypatch.setenv("SOFA_NOW", z(t0))
    monkeypatch.setattr(sys, "argv", [
        "run_confidence.py", "--date", day, "--runs-dir", str(tmp_path)])
    assert run_confidence.main() == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    # the installed curves and line evidence (read-only): the leg reached the
    # line-evidence read and stopped there
    assert summary["metrics"]["refused"] == {"NO_LINE_EVIDENCE": 1}
    doc = json.loads((run / "08_confidence.json").read_text())
    assert doc["singles"] == [] and doc["legs"] == []


# --- SETTLE: the 90-minute score ---------------------------------------------------


def _event(code: int, home: dict[str, int], away: dict[str, int]) -> dict[str, Any]:
    return {"status": {"type": "finished", "description": "Ended", "code": code},
            "homeScore": home, "awayScore": away}


NORMAL_2_0 = _event(100, {"current": 2, "period1": 1, "period2": 1, "normaltime": 2},
                    {"current": 0, "period1": 0, "period2": 0, "normaltime": 0})
# 1-1 at 90 minutes, straight to penalties (home 4-3): code 120
PENS_1_1 = _event(120, {"current": 5, "period1": 1, "period2": 0, "normaltime": 1,
                        "penalties": 4},
                  {"current": 4, "period1": 0, "period2": 1, "normaltime": 1,
                   "penalties": 3})
# 1-1 at 90 minutes, home won 2-1 after extra time: code 110
AET_2_1 = _event(110, {"current": 2, "period1": 1, "period2": 0, "normaltime": 1,
                       "extra1": 1, "extra2": 0},
                 {"current": 1, "period1": 0, "period2": 1, "normaltime": 1,
                  "extra1": 0, "extra2": 0})


@pytest.mark.parametrize("event,wins", [
    (NORMAL_2_0, {"1X": 1.0, "X2": 0.0, "12": 1.0}),
    (PENS_1_1, {"1X": 1.0, "X2": 1.0, "12": 0.0}),
    (AET_2_1, {"1X": 1.0, "X2": 1.0, "12": 0.0}),
])
def test_settle_grades_on_the_90_minute_score(
        event: dict[str, Any], wins: dict[str, float]) -> None:
    for sel, value in wins.items():
        assert double_chance_value(sel, event) == value
        row = {"market": DOUBLE_CHANCE, "subject": sel, "line": 0.5,
               "direction": "OVER"}
        assert _settle_double_chance(row, event) == (
            value, "WIN" if value else "LOSS")
        assert settle_value(value, 0.5, "UNDER") == ("LOSS" if value else "WIN")


def test_settle_refuses_what_it_cannot_read() -> None:
    assert double_chance_value("1", NORMAL_2_0) == GapReason.STAT_KEY_ABSENT
    no_score = _event(100, {}, {})
    assert double_chance_value("1X", no_score) == GapReason.STAT_KEY_ABSENT
    bad = _event(100, {"current": 2, "period1": 1, "period2": 0, "normaltime": 2},
                 {"current": 0, "period1": 0, "period2": 0, "normaltime": 0})
    assert double_chance_value("1X", bad) == GapReason.INTERNAL_INCONSISTENT
    assert _settle_double_chance(
        {"market": DOUBLE_CHANCE, "subject": "1X", "line": 0.5,
         "direction": "OVER"}, no_score) == "double_chance:STAT_KEY_ABSENT"


def test_regrade_grades_like_settle() -> None:
    from scripts.sofa.regrade_settled import grade_live

    row = {"market": DOUBLE_CHANCE, "subject": "X2", "line": 0.5,
           "direction": "OVER", "sport": "football"}
    assert grade_live(row, PENS_1_1, None, None, None) == (1.0, "WIN")


def test_selection_holds() -> None:
    assert selection_holds("1X", 1, 1) and selection_holds("1X", 2, 0)
    assert not selection_holds("1X", 0, 1)
    assert selection_holds("12", 0, 1) and not selection_holds("12", 2, 2)
    with pytest.raises(ValueError):
        selection_holds("1", 1, 0)
