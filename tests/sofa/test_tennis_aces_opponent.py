# ruff: noqa: E501  - test tables and fixtures read as one line.
"""epochs.TENNIS_ACES_OPPONENT (2026-10-17): a tennis aces centre x today's
returner's factor (bet.sofa.tennis_aces_opponent), in SHEET and in the cache
replay alike, and the replay's serve markets (--tennis-serve-markets: per-set
aces / double faults and aces + double faults). Offline and fast."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa import tennis_aces_opponent as ao
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from scripts.sofa import calibrate_from_cache as cc
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_player_markets import dataclasses_replace_tennis

# tennis:M:ITF:hard in config/sofa_tennis_tier_baselines.json is read through
# this table, so the tests pin their own prior
PRIOR = 3.0
TIERS = {"aces_for": {"tennis:M:ITF:hard": {"mean": PRIOR, "n": 1000}}}
K = 8.0

# --- the arithmetic ------------------------------------------------------------


def test_an_average_returner_reads_one_and_a_weak_one_more() -> None:
    assert ao.returner_factor([PRIOR] * 10, PRIOR, K) == pytest.approx(1.0)
    weak = ao.returner_factor([6.0] * 10, PRIOR, K)
    assert weak == pytest.approx(((60 + K * PRIOR) / 18) / PRIOR)
    assert weak is not None and weak > 1.0
    strong = ao.returner_factor([1.0] * 10, PRIOR, K)
    assert strong is not None and strong < 1.0


def test_no_prior_or_a_short_returner_sample_gives_no_factor() -> None:
    assert ao.returner_factor([5.0] * 10, None, K) is None
    assert ao.returner_factor([5.0] * 10, 0.0, K) is None
    assert ao.returner_factor([5.0] * (ao.MIN_RETURNER_VALUES - 1), PRIOR, K) is None
    assert ao.returner_factor([5.0] * ao.MIN_RETURNER_VALUES, PRIOR, K) is not None


def test_the_total_moves_by_each_servers_share() -> None:
    # A serves into B's return (f 1.5), B into A's (f 1.0)
    assert ao.total_multiplier(6.0, 2.0, 1.0, 1.5) == pytest.approx(
        (6.0 * 1.5 + 2.0 * 1.0) / 8.0)
    assert ao.total_multiplier(4.0, 4.0, 1.0, 1.0) == pytest.approx(1.0)
    assert ao.total_multiplier(0.0, 0.0, 2.0, 2.0) == 1.0


def test_double_faults_are_not_corrected() -> None:
    assert not any(m.startswith("double_faults") for m in ao.ACES_MARKETS)
    assert ao.ACES_MARKETS == {"aces_for", "aces_total", "aces_set1_for",
                               "aces_set1_total", "aces_set2_for",
                               "aces_set2_total"}


# --- the switch ----------------------------------------------------------------


def test_the_switch_reads_the_day_and_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "TENNIS_ACES_OPPONENT_FROM_UTC", None)
    assert not epochs.tennis_aces_opponent("2030-01-01", datetime(2030, 1, 2, tzinfo=UTC))
    at = datetime(2026, 10, 20, tzinfo=UTC)
    monkeypatch.setattr(epochs, "TENNIS_ACES_OPPONENT_FROM_UTC", at)
    assert epochs.tennis_aces_opponent("2026-10-20", at)
    assert not epochs.tennis_aces_opponent("2026-10-20", at - timedelta(minutes=1))
    # a rebuild of an earlier day keeps the rule it printed under
    assert not epochs.tennis_aces_opponent("2026-10-19", at + timedelta(days=1))


# --- SHEET ---------------------------------------------------------------------


def _obs(own: list[float], against: list[float] | None, start: int) -> list[Observation]:
    return [
        Observation(
            sofascore_event_id=start + i,
            match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
            opponent=f"O{i}", value=v, competition_id=1, season_id=1,
            venue=None, opponent_id=9000 + i,
            against=None if against is None else against[i],
        )
        for i, v in enumerate(own)
    ]


# side A serves 4 a match and concedes 2 (a strong returner); side B serves 3
# and concedes 6 (a weak returner)
A_OWN, A_CON = [4.0] * 10, [2.0] * 10
B_OWN, B_CON = [3.0] * 10, [6.0] * 10


def _samples(with_against: bool = True) -> FixtureSamples:
    def ms(metric: str, a: list[float], b: list[float],
           a_con: list[float] | None, b_con: list[float] | None) -> MetricSample:
        return MetricSample(metric=metric, side_a=_obs(a, a_con, 100),
                            side_b=_obs(b, b_con, 200), h2h=[])
    a_con = A_CON if with_against else None
    b_con = B_CON if with_against else None
    totals = [a + b for a, b in zip(A_OWN, A_CON, strict=True)]
    totals_b = [a + b for a, b in zip(B_OWN, B_CON, strict=True)]
    return FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={
            "aces_for": ms("aces_for", A_OWN, B_OWN, a_con, b_con),
            "aces_set1_for": ms("aces_set1_for", [2.0] * 10, [1.0] * 10,
                                [1.0] * 10 if with_against else None,
                                [3.0] * 10 if with_against else None),
            "aces_total": MetricSample(
                metric="aces_total", side_a=_obs(totals, None, 100),
                side_b=_obs(totals_b, None, 200), h2h=[]),
            "double_faults_for": ms("double_faults_for", [3.0] * 10, [2.0] * 10,
                                    [2.0] * 10, [5.0] * 10),
        },
    )


def _offer() -> FixtureOffer:
    fetched = datetime(2026, 9, 22, 20, tzinfo=UTC)
    rungs = [
        PricedRung(market=m, subject=s, line=line, over_odds=1.85,
                   under_odds=1.85, fetched_at_utc=fetched)
        for m, s, line in (
            ("aces_for", "Kenta Kawada", 3.5),
            ("aces_set1_for", "Kenta Kawada", 1.5),
            ("aces_total", "", 9.5),
            ("double_faults_for", "Kenta Kawada", 2.5),
        )
    ]
    return FixtureOffer(sofascore_event_id=1, status="PRICED",
                        unmapped_markets=[], rungs=rungs)


def _sheet(on: bool | None, samples: FixtureSamples | None = None,
           tiers: dict[str, object] | None = TIERS) -> dict[tuple[str, str], dict[str, object]]:
    kwargs = {} if on is None else {"aces_opponent_on": on}
    rows, _ = process_fixture(
        dataclasses_replace_tennis(), samples or _samples(), _offer(),
        baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), tennis_tiers=tiers, stats_only=True,
        **kwargs,  # type: ignore[arg-type]
    )
    return {(r.market, r.direction): sheet_row_json(r) for r in rows}


def _centre_of(note_rows: dict[tuple[str, str], dict[str, object]], market: str) -> str:
    notes = note_rows[(market, "OVER")].get("notes") or []
    assert isinstance(notes, list)
    return next((n for n in notes if n.startswith(ao.NOTE)), "")


def test_off_the_sheet_is_byte_identical() -> None:
    def dump(rows: dict[tuple[str, str], dict[str, object]]) -> str:
        return json.dumps(sorted(rows.items()), sort_keys=True, default=str)
    assert dump(_sheet(False)) == dump(_sheet(None))


def test_on_kawada_serves_into_a_weak_returner_and_his_over_rises() -> None:
    off, on = _sheet(False), _sheet(True)
    for market in ("aces_for", "aces_set1_for"):
        assert on[(market, "OVER")]["p_central"] > off[(market, "OVER")]["p_central"]
        assert on[(market, "UNDER")]["p_central"] < off[(market, "UNDER")]["p_central"]
        f_b = ao.returner_factor(B_CON, PRIOR, 10.0)  # SofaConfig default K
        note = _centre_of(on, market)
        assert note.startswith(f"{ao.NOTE}: centre")
        assert f_b is not None and f"x {f_b:.3f}" in note
    # double faults: no correction, no note
    assert on[("double_faults_for", "OVER")] == off[("double_faults_for", "OVER")]
    assert _centre_of(on, "double_faults_for") == ""


def test_on_the_total_moves_by_the_weighted_pair() -> None:
    off, on = _sheet(False), _sheet(True)
    note = _centre_of(on, "aces_total")
    assert note.startswith(f"{ao.NOTE}: centre")
    # A (4 a match) serves into B's weak return, B (3) into A's strong one
    assert on[("aces_total", "OVER")]["p_central"] != off[("aces_total", "OVER")]["p_central"]


def test_a_sample_without_against_or_a_tier_is_left_as_it_was_and_says_so() -> None:
    off = _sheet(False, _samples(with_against=False))
    on = _sheet(True, _samples(with_against=False))
    for market in ("aces_for", "aces_total"):
        assert on[(market, "OVER")]["p_central"] == off[(market, "OVER")]["p_central"]
        assert "no correction" in _centre_of(on, market)
    no_tier_off, no_tier_on = _sheet(False, tiers={}), _sheet(True, tiers={})
    assert (no_tier_on[("aces_for", "OVER")]["p_central"]
            == no_tier_off[("aces_for", "OVER")]["p_central"])


# --- the replay ----------------------------------------------------------------


def _past(team_own: float, conceded: float, i: int, opp: int) -> cc.Past:
    return cc.Past(1_000 + i, 50_000 + i, team_own, team_own + conceded, 7,
                   True, "home", opp, 3, "Hardcourt outdoor")


def test_replay_factor_is_sheets_formula_on_total_minus_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "TENNIS_ACES_TIERS", TIERS)
    monkeypatch.setattr(cc, "TENNIS_SAMPLE_SCOPE", True)
    history = {
        (1, "aces"): [_past(4.0, 2.0, i, 100 + i) for i in range(10)],
        (2, "aces"): [_past(3.0, 6.0, i, 200 + i) for i in range(10)],
    }
    tennis = cc.TennisContext("ITF Men", "Hardcourt outdoor", False, 3)
    match = cc.Played(99, 10**9, 1, 2, "tennis", 7, {"aces": (5.0, 2.0)},
                      tennis=tennis)
    consts = {"K_CENTRE": {"by_sport": {"tennis": K}}}
    got = cc.tennis_aces_multiplier(match, "aces_for", "side_a", history, None, consts)
    assert got == pytest.approx(ao.returner_factor(B_CON, PRIOR, K))
    tot = cc.tennis_aces_multiplier(match, "aces_total", None, history, None, consts)
    want = ao.total_multiplier(
        ao.shrunk(A_OWN, PRIOR, K), ao.shrunk(B_OWN, PRIOR, K),
        ao.returner_factor(A_CON, PRIOR, K) or 0.0,
        ao.returner_factor(B_CON, PRIOR, K) or 0.0)
    assert tot == pytest.approx(want)
    # best of five: no tier prior in SHEET, none here
    bo5 = cc.Played(99, 10**9, 1, 2, "tennis", 7, {}, tennis=cc.TennisContext(
        "ITF Men", "Hardcourt outdoor", True, 5))
    assert cc.tennis_aces_multiplier(bo5, "aces_for", "side_a", history, None, consts) is None


def test_replay_reads_the_serve_bases_like_samples() -> None:
    def item(key: str, h: int, a: int) -> dict[str, object]:
        return {"key": key, "homeValue": h, "awayValue": a, "name": key,
                "home": str(h), "away": str(a)}
    stats = {"statistics": [
        {"period": "ALL", "groups": [{"groupName": "Service", "statisticsItems": [
            item("aces", 7, 3), item("doubleFaults", 2, 4)]}]},
        {"period": "1ST", "groups": [{"groupName": "Service", "statisticsItems": [
            item("aces", 4, 1), item("doubleFaults", 1, 2)]}]},
        {"period": "2ND", "groups": [{"groupName": "Service", "statisticsItems": [
            item("aces", 3, 2)]}]},
    ]}
    values = cc.serve_values({}, json.dumps(stats))
    assert values["aces_set1"] == (4.0, 1.0)
    assert values["double_faults_set1"] == (1.0, 2.0)
    assert values["serve_points"] == (9.0, 7.0)
    assert values["serve_points_set1"] == (5.0, 3.0)
    assert values["aces_set2"] == (3.0, 2.0)
    # set 2 has no double faults: no value for it, never a zero
    assert "double_faults_set2" not in values
    assert "serve_points_set2" not in values
    assert cc.serve_values({}, None) == {}
    assert cc.market_name("serve_points_set1", "for") == "serve_points_set1_for"


# --- rebuild_plan --------------------------------------------------------------


def test_a_sheet_without_the_marker_is_re_run_once_the_switch_is_on(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "TENNIS_MATCH_WINNER_FROM_UTC", None)
    at = datetime(2026, 10, 20, tzinfo=UTC)
    limit = timedelta(minutes=45)
    monkeypatch.setattr(epochs, "TENNIS_ACES_OPPONENT_FROM_UTC", at)
    stale = rp.DayState("2026-10-20", at + timedelta(hours=8), limit,
                        sheet_tennis_aces=False)
    assert "SHEET" in rp.build_plan(stale).names()
    fresh = rp.DayState("2026-10-20", at + timedelta(hours=8), limit)
    assert "SHEET" not in rp.build_plan(fresh).names()
    # the day before the switch keeps its sheet
    before = rp.DayState("2026-10-19", at + timedelta(hours=8), limit,
                         sheet_tennis_aces=False)
    assert "SHEET" not in rp.build_plan(before).names()
    field, rule, sport = epochs.TENNIS_ACES_OPPONENT_MARKER
    assert (field, sport) == ("tennis_aces_rule", "tennis")
    assert epochs.sheet_has_marker([{"sport": "football"}], epochs.TENNIS_ACES_OPPONENT_MARKER)
    assert not epochs.sheet_has_marker([{"sport": "tennis"}], epochs.TENNIS_ACES_OPPONENT_MARKER)
