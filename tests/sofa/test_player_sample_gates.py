"""A football player row on a lineup market reads no sample-shape gate
(epochs.PLAYER_SAMPLE_GATES_FROM_UTC, from 2026-10-17 00:00Z, operator 2026-10-16).

A footballer's sample is his starts in his team's last 10 matches, 5-10
values, so THIN_SAMPLE_FOR_BUILDER (< 10) admitted only a player who started
all ten, and LINE_BEYOND_SAMPLE refused OVER 0.5 for a player who had a shot
in every start. The lineup-market player curves are fitted on a replay with 5
starts and no shape gate; measured, the refused groups realise on the curve
(docs/sofa/evidence/player_sample_gates_2026-10-16.md,
player_line_evidence_2026-10-16.md). With the switch such a row needs only
PLAYER_MIN_SAMPLE values; a leg a gate would have refused carries that gate
as its marker and never joins a builder. A leg every gate passes, a team row
and a shot-detail row (its own estimator, unmeasured) are unchanged.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.confidence import (
    Calibration,
    player_shape_gate_scope,
    shape_gate_refusal,
)
from bet.sofa.config import SofaConfig
from bet.sofa.line_evidence import LineEvidence, evidence_key
from tests.sofa.confidence_day import DAY, NOW, _fixture, _offer, _samples, _sheet_row

PLAYER = "Doe, John"
SHOTS = "player_shots_for"
RIGHT_FOOT = "player_right_foot_shots_for"  # shot detail: outside the switch
P, ODDS = 0.88, 1.25
ON = datetime(2025, 12, 1, tzinfo=UTC)  # before DAY: the switch is on for it
TEAM = 50

ALWAYS_OVER = [1, 2, 3, 1, 2, 4]        # LINE_BEYOND_SAMPLE
MODE_ZERO = [0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 3, 2]  # mode 0 loses OVER 0.5
SIX_WITH_BLANK = [0, 2, 3, 1, 2, 4]     # THIN_SAMPLE_FOR_BUILDER (6 < 10)
TEN_WITH_BLANK = [0, 2, 3, 1, 2, 4, 1, 2, 3, 1]  # passes every gate
FIVE_WITH_BLANK = [0, 2, 3, 1, 2]       # exactly PLAYER_MIN_SAMPLE
FOUR = [1, 2, 3, 1]                      # below PLAYER_MIN_SAMPLE


def _player_obs(values: list[int]) -> list[dict[str, Any]]:
    return [{"sofascore_event_id": 9000 + i,
             "match_date_utc": (NOW - timedelta(days=4 + 4 * i))
             .isoformat().replace("+00:00", "Z"),
             "opponent": "X", "value": float(v), "minutes": 90,
             "competition_id": 9, "season_id": 9, "venue": None}
            for i, v in enumerate(values)]


def _player_row(eid: int, market: str) -> dict[str, Any]:
    row = _sheet_row(eid, P, ODDS, 0.0)
    row.update({"market": market, "subject": PLAYER, "line": 0.5,
                "sample_size": 6, "sample_mean": 2.0, "sample_sd": 1.0,
                "centre": 2.0, "market_p": None})
    return row


def _player_offer(eid: int, market: str) -> dict[str, Any]:
    offer = _offer(eid, ODDS, 0.0)
    offer["rungs"][0].update({"market": market, "subject": PLAYER, "line": 0.5,
                              "under_odds": None})
    return offer


def _day(tmp_path: Path, players: dict[int, tuple[str, list[int]]],
         team_leg_beside: int | None = None) -> Path:
    """One fixture per player row (market, sample of starts); fixture TEAM a
    goals_total 1.5 OVER row whose every sampled value is over the line
    (LINE_BEYOND_SAMPLE with or without the switch); `team_leg_beside` adds an
    ordinary goals_total leg to that player's fixture (a builder candidate)."""
    run = tmp_path / DAY
    run.mkdir()
    fixtures, samples, offers, sheet = [], [], [], []
    for eid, (market, values) in players.items():
        fixtures.append(_fixture(eid))
        s = _samples(eid)
        s["players"] = {f"{market}|{PLAYER}": {"observations": _player_obs(values)}}
        samples.append(s)
        offers.append(_player_offer(eid, market))
        sheet.append(_player_row(eid, market))
        if eid == team_leg_beside:
            offers[-1]["rungs"] += _offer(eid, 1.40, 2.75)["rungs"]
            sheet.append(_sheet_row(eid, 0.72, 1.40, 0.69))
    team = _samples(TEAM)
    for side in ("side_a", "side_b"):
        for o in team["metrics"]["goals_total"][side]:
            o["value"] = 3.0
    fixtures.append(_fixture(TEAM))
    samples.append(team)
    offers.append(_offer(TEAM, 1.40, 2.75))
    sheet.append(_sheet_row(TEAM, 0.72, 1.40, 0.69))
    (run / "02_fixtures.json").write_text(json.dumps(fixtures))
    (run / "03_samples.json").write_text(json.dumps(samples))
    (run / "04_offer.json").write_text(json.dumps(offers))
    (run / "05_sheet.json").write_text(json.dumps(sheet))
    (run / "vetoes.json").write_text("[]")
    return tmp_path


def _confidence(runs: Path, monkeypatch: pytest.MonkeyPatch,
                switch: datetime | None) -> dict[str, Any]:
    import scripts.sofa.run_confidence as rc

    monkeypatch.setattr(epochs, "PLAYER_SAMPLE_GATES_FROM_UTC", switch)
    # the test day is older than these: a player leg prints only by
    # ONE_SIDED_SINGLES, and reads the line evidence the precondition reads
    for switch_name in ("ONE_SIDED_SINGLES_FROM_UTC", "LINE_EVIDENCE_FROM_UTC",
                        "LINE_EVIDENCE_V2_FROM_UTC", "BUCKET_DESIGN_EFFECT_FROM_UTC"):
        monkeypatch.setattr(epochs, switch_name, ON)
    for date_name in ("LINE_EVIDENCE_DATE", "LINE_EVIDENCE_V2_DATE"):
        monkeypatch.setattr(epochs, date_name, ON.strftime("%Y-%m-%d"))
    monkeypatch.setattr(sys, "argv", ["run_confidence.py", "--date", DAY,
                                      "--runs-dir", str(runs)])
    assert rc.main() == 0
    return dict(json.loads((runs / DAY / "08_confidence.json").read_text()))


@pytest.fixture
def player_legs_would_print() -> None:
    """The installed curves and line evidence print both player markets at
    (P, ODDS) at all - else every assertion below would be vacuous."""
    cal = dataclasses.replace(Calibration.load(), gap_shrink_k=0.0,
                              cap_market_by_thin=True, cap_pool_by_neighbour=True)
    evidence = LineEvidence.load(v2=True, bucket_deff=True)
    for market in (SHOTS, RIGHT_FOOT):
        hit = cal.realised(market, P, "football", "OVER", None)
        got = evidence.read("football", evidence_key(f"{market}|OVER"), P, hit, ODDS)
        assert got is not None and got.value >= 0.70 and got.value * ODDS >= 0.90, (
            f"precondition: {market} OVER at p {P} / {ODDS} no longer prints ({got})")


def _by_id(legs: list[dict[str, Any]], market: str) -> dict[int, dict[str, Any]]:
    return {int(x["sofascore_event_id"]): x for x in legs if x["market"] == market}


def _in_builders(doc: dict[str, Any], market: str) -> set[int]:
    return {int(b["sofascore_event_id"]) for b in doc["builders"]
            for leg in b["legs"] if leg["market"] == market}


# --- the rule ----------------------------------------------------------------


def test_the_switch_starts_the_next_day_and_never_mid_day() -> None:
    start = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
    assert epochs.PLAYER_SAMPLE_GATES_FROM_UTC == start
    assert epochs.player_sample_gates_off("2026-10-17", start)
    # a day built before it stays off on a later clock (a rebuild of 10-16)
    assert not epochs.player_sample_gates_off(
        "2026-10-16", datetime(2026, 10, 17, 9, 0, tzinfo=UTC))
    assert not epochs.player_sample_gates_off(
        "2026-10-17", datetime(2026, 10, 16, 23, 59, tzinfo=UTC))


def test_the_floor_is_the_replays_sample_floor() -> None:
    assert epochs.PLAYER_MIN_SAMPLE == SofaConfig.from_env().min_sample == 5


def test_the_scope_is_the_lineup_markets_of_football() -> None:
    assert player_shape_gate_scope("football", SHOTS)
    assert player_shape_gate_scope("football", "player_tackles_for")
    assert not player_shape_gate_scope("football", RIGHT_FOOT)
    assert not player_shape_gate_scope("football", "player_sot_headed_for")
    assert not player_shape_gate_scope("football", "goals_total")
    assert not player_shape_gate_scope("tennis", SHOTS)
    # no curve was measured for interceptions: outside until it is
    assert not player_shape_gate_scope("football", "player_interceptions_for")


def test_the_gate_order_is_confidences() -> None:
    assert shape_gate_refusal(0.5, "OVER", [1.0, 2.0]) == "LINE_BEYOND_SAMPLE"
    assert shape_gate_refusal(0.5, "OVER", [0.0, 0.0, 1.0]) == "MODE_LOSES"
    assert shape_gate_refusal(0.5, "OVER", [0.0, 1.0, 1.0]) == "THIN_SAMPLE_FOR_BUILDER"
    assert shape_gate_refusal(0.5, "OVER", [float(v) for v in TEN_WITH_BLANK]) is None
    # MODE_LOSES reads the sample it is given (a corrected one rounded)
    assert shape_gate_refusal(0.5, "OVER", [0.4] * 10 + [2.0],
                              [0.0] * 10 + [2.0]) == "MODE_LOSES"


# --- end to end through CONFIDENCE --------------------------------------------

PLAYERS = {1: (SHOTS, ALWAYS_OVER), 2: (SHOTS, SIX_WITH_BLANK),
           3: (SHOTS, TEN_WITH_BLANK), 4: (SHOTS, FOUR), 5: (SHOTS, FIVE_WITH_BLANK),
           6: (SHOTS, MODE_ZERO),
           7: (RIGHT_FOOT, TEN_WITH_BLANK), 8: (RIGHT_FOOT, ALWAYS_OVER)}


@pytest.mark.usefixtures("player_legs_would_print")
def test_off_the_gates_refuse_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = _confidence(_day(tmp_path, PLAYERS, team_leg_beside=3), monkeypatch, None)
    assert set(_by_id(doc["legs"], SHOTS)) == {3}
    assert set(_by_id(doc["legs"], RIGHT_FOOT)) == {7}
    assert TEAM not in {int(x["sofascore_event_id"]) for x in doc["legs"]}
    assert not any(epochs.PLAYER_SAMPLE_MARKER in x for x in doc["legs"])
    assert _in_builders(doc, SHOTS) == {3}


@pytest.mark.usefixtures("player_legs_would_print")
def test_on_the_lifted_legs_print_with_their_gate_and_nothing_else_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = _confidence(_day(tmp_path, PLAYERS, team_leg_beside=3), monkeypatch, ON)
    shots = _by_id(doc["legs"], SHOTS)
    # 4 has four starts (< PLAYER_MIN_SAMPLE); 5 has exactly five
    assert set(shots) == {1, 2, 3, 5, 6}
    assert {k: v.get(epochs.PLAYER_SAMPLE_MARKER) for k, v in shots.items()} == {
        1: "LINE_BEYOND_SAMPLE", 2: "THIN_SAMPLE_FOR_BUILDER", 3: None,
        5: "THIN_SAMPLE_FOR_BUILDER", 6: "MODE_LOSES"}
    assert set(shots) <= {int(x["sofascore_event_id"]) for x in doc["singles"]}
    assert all(leg["one_sided_market"] is True for leg in shots.values())
    # the shot-detail market and the team row keep their gates
    assert set(_by_id(doc["legs"], RIGHT_FOOT)) == {7}
    assert TEAM not in {int(x["sofascore_event_id"]) for x in doc["legs"]}
    # a leg every gate passed is a builder leg as before; a lifted one never is
    assert _in_builders(doc, SHOTS) == {3}


# --- the live path: a stats-only day on the switch's own clock ------------------

LIVE_DAY = "2026-10-17"
T0 = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
KICKOFF_LIVE = "2026-10-17T18:00:00Z"


def _z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _live_day(tmp_path: Path, players: dict[int, list[int]],
              team_leg_beside: int) -> Path:
    """A real-epoch day: stats-only sheet rows, every switch as installed."""
    run = tmp_path / LIVE_DAY
    run.mkdir()
    fixtures, samples, offers, sheet = [], [], [], []
    for eid, values in players.items():
        fx = _fixture(eid)
        fx.update({"kickoff_utc": KICKOFF_LIVE, "superbet_kickoff_utc": KICKOFF_LIVE})
        fixtures.append(fx)
        smp = _samples(eid)
        for side in ("side_a", "side_b"):
            for i, o in enumerate(smp["metrics"]["goals_total"][side]):
                o["match_date_utc"] = _z(T0 - timedelta(days=3 + i))
        obs = _player_obs(values)
        for i, o in enumerate(obs):
            o["match_date_utc"] = _z(T0 - timedelta(days=4 + 4 * i))
        smp["players"] = {f"{SHOTS}|{PLAYER}": {"observations": obs}}
        samples.append(smp)
        offer = _player_offer(eid, SHOTS)
        if eid == team_leg_beside:
            offer["rungs"] += _offer(eid, 1.40, 2.75)["rungs"]
        for rung in offer["rungs"]:
            rung["fetched_at_utc"] = _z(T0 - timedelta(minutes=1))
        offers.append(offer)
        rows = [_player_row(eid, SHOTS)]
        if eid == team_leg_beside:
            rows.append(_sheet_row(eid, 0.72, 1.40, 0.69))
        for row in rows:
            row.update({"epoch": "stats_only", "forecast_p": None,
                        "forecast_source": None})
        sheet += rows
    (run / "02_fixtures.json").write_text(json.dumps(fixtures))
    (run / "03_samples.json").write_text(json.dumps(samples))
    (run / "04_offer.json").write_text(json.dumps(offers))
    (run / "05_sheet.json").write_text(json.dumps(sheet))
    (run / "vetoes.json").write_text("[]")
    return tmp_path


@pytest.mark.usefixtures("player_legs_would_print")
def test_live_a_lifted_leg_keeps_its_marker_when_a_read_removes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.sofa.run_confidence as rc

    runs = _live_day(tmp_path, {1: ALWAYS_OVER, 2: SIX_WITH_BLANK,
                                3: TEN_WITH_BLANK}, team_leg_beside=3)
    (runs / LIVE_DAY / "reads.json").write_text(json.dumps([{
        "sofascore_event_id": 2, "market": SHOTS, "subject": PLAYER,
        "line": 0.5, "direction": "OVER", "verdict": "WATCH",
        "author": "analyst", "reason": "5 of 6 starts at 90', thin"}]))
    monkeypatch.setenv("SOFA_NOW", _z(T0))
    monkeypatch.setattr(sys, "argv", ["run_confidence.py", "--date", LIVE_DAY,
                                      "--runs-dir", str(runs)])
    assert rc.main() == 0
    doc = json.loads((runs / LIVE_DAY / "08_confidence.json").read_text())
    assert doc["epoch"] == "stats_only"
    singles = _by_id(doc["singles"], SHOTS)
    assert set(singles) == {1, 3}
    assert singles[1][epochs.PLAYER_SAMPLE_MARKER] == "LINE_BEYOND_SAMPLE"
    assert epochs.PLAYER_SAMPLE_MARKER not in singles[3]
    removed = _by_id(doc["removed_by_reads"], SHOTS)
    assert removed[2][epochs.PLAYER_SAMPLE_MARKER] == "THIN_SAMPLE_FOR_BUILDER"
    assert removed[2]["refusal"] == "WATCHED"
    # the stats-only builder pool: the passing leg joins, a lifted one never
    assert _in_builders(doc, SHOTS) <= {3}
    assert not any(leg.get(epochs.PLAYER_SAMPLE_MARKER)
                   for b in doc["builders"] for leg in b["legs"])
