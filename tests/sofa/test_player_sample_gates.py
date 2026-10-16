"""A football player row reads no sample-shape gate
(epochs.PLAYER_SAMPLE_GATES_FROM_UTC, from 2026-10-17 00:00Z, operator 2026-10-16).

A footballer's sample is his starts in his team's last 10 matches, 5-10
values, so THIN_SAMPLE_FOR_BUILDER (< 10) admitted only a player who started
all ten, and LINE_BEYOND_SAMPLE refused OVER 0.5 for a player who had a shot
in every start. The player curves are fitted on a replay with 5 starts and no
shape gate; measured, the refused groups realise on the curve
(docs/sofa/evidence/player_sample_gates_2026-10-16.md,
player_line_evidence_2026-10-16.md). With the switch a player row needs only
PLAYER_MIN_SAMPLE values and carries the marker; a team row is unchanged.
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
from bet.sofa.confidence import Calibration
from bet.sofa.line_evidence import LineEvidence, evidence_key
from tests.sofa.confidence_day import DAY, NOW, _fixture, _offer, _samples, _sheet_row

PLAYER = "Doe, John"
MARKET = "player_shots_for"
P, ODDS = 0.88, 1.25
ON = datetime(2025, 12, 1, tzinfo=UTC)  # before DAY: the switch is on for it


def _player_obs(values: list[float]) -> list[dict[str, Any]]:
    return [{"sofascore_event_id": 9000 + i,
             "match_date_utc": (NOW - timedelta(days=4 + 4 * i))
             .isoformat().replace("+00:00", "Z"),
             "opponent": "X", "value": float(v), "minutes": 90,
             "competition_id": 9, "season_id": 9, "venue": None}
            for i, v in enumerate(values)]


def _player_row(eid: int) -> dict[str, Any]:
    row = _sheet_row(eid, P, ODDS, None)  # type: ignore[arg-type]
    row.update({"market": MARKET, "subject": PLAYER, "line": 0.5,
                "sample_size": 6, "sample_mean": 2.0, "sample_sd": 1.0,
                "centre": 2.0, "market_p": None})
    return row


def _player_offer(eid: int) -> dict[str, Any]:
    offer = _offer(eid, ODDS, 0.0)
    offer["rungs"][0].update({"market": MARKET, "subject": PLAYER, "line": 0.5,
                              "under_odds": None})
    return offer


def _day(tmp_path: Path, starts: dict[int, list[float]]) -> Path:
    """Fixtures 1..: a player row whose sample is `starts[eid]`; fixture 50 a
    team row (goals_total 1.5 OVER) whose every sampled value is over the
    line - LINE_BEYOND_SAMPLE with or without the switch."""
    run = tmp_path / DAY
    run.mkdir()
    fixtures, samples, offers, sheet = [], [], [], []
    for eid, values in starts.items():
        fixtures.append(_fixture(eid))
        s = _samples(eid)
        s["players"] = {f"{MARKET}|{PLAYER}": {"observations": _player_obs(values)}}
        samples.append(s)
        offers.append(_player_offer(eid))
        sheet.append(_player_row(eid))
        if eid == 3:  # a team leg beside the player's: a builder candidate
            s["metrics"] = _samples(eid)["metrics"]
            offers[-1]["rungs"] += _offer(eid, 1.40, 2.75)["rungs"]
            sheet.append(_sheet_row(eid, 0.72, 1.40, 0.69))
    team = _samples(50)
    for side in ("side_a", "side_b"):
        for o in team["metrics"]["goals_total"][side]:
            o["value"] = 3.0
    fixtures.append(_fixture(50))
    samples.append(team)
    offers.append(_offer(50, 1.40, 2.75))
    sheet.append(_sheet_row(50, 0.72, 1.40, 0.69))
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
    # the test day is older than ONE_SIDED_SINGLES: a player leg prints only by it
    monkeypatch.setattr(epochs, "ONE_SIDED_SINGLES_FROM_UTC", ON)
    monkeypatch.setattr(sys, "argv", ["run_confidence.py", "--date", DAY,
                                      "--runs-dir", str(runs)])
    assert rc.main() == 0
    return dict(json.loads((runs / DAY / "08_confidence.json").read_text()))


@pytest.fixture(autouse=True)
def _player_leg_would_print() -> None:
    """The installed curve and line evidence print the player row at all."""
    cal = dataclasses.replace(Calibration.load(), gap_shrink_k=0.0,
                              cap_market_by_thin=True, cap_pool_by_neighbour=True)
    hit = cal.realised(MARKET, P, "football", "OVER", None)
    got = LineEvidence.load(v2=True, bucket_deff=True).read(
        "football", evidence_key(f"{MARKET}|OVER"), P, hit, ODDS)
    assert got is not None and got.value >= 0.70 and got.value * ODDS >= 0.90, (
        f"precondition: {MARKET} OVER at p {P} / {ODDS} no longer prints ({got})")


def _ids(legs: list[dict[str, Any]]) -> set[int]:
    return {int(leg["sofascore_event_id"]) for leg in legs}


def test_the_switch_starts_the_next_day_and_never_mid_day() -> None:
    start = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
    assert epochs.PLAYER_SAMPLE_GATES_FROM_UTC == start
    assert epochs.player_sample_gates_off("2026-10-17", start)
    assert not epochs.player_sample_gates_off("2026-10-16", start)
    assert not epochs.player_sample_gates_off(
        "2026-10-17", datetime(2026, 10, 16, 23, 59, tzinfo=UTC))
    assert epochs.PLAYER_MIN_SAMPLE == 5


def test_off_a_short_or_always_over_sample_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1: six starts, a shot in each (LINE_BEYOND_SAMPLE); 2: six starts with
    # a blank (THIN_SAMPLE_FOR_BUILDER); 3: ten starts with a blank - passes.
    runs = _day(tmp_path, {1: [1, 2, 3, 1, 2, 4], 2: [0, 2, 3, 1, 2, 4],
                           3: [0, 2, 3, 1, 2, 4, 1, 2, 3, 1]})
    doc = _confidence(runs, monkeypatch, None)
    player = [x for x in doc["legs"] if x["market"] == MARKET]
    assert _ids(player) == {3}
    assert epochs.PLAYER_SAMPLE_MARKER not in player[0]
    # ten starts pass the gates as before, and the leg may join a builder
    assert any(leg["market"] == MARKET for b in doc["builders"] for leg in b["legs"])


def test_on_the_player_legs_print_and_say_why_the_team_gate_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = _day(tmp_path, {1: [1, 2, 3, 1, 2, 4], 2: [0, 2, 3, 1, 2, 4],
                           3: [0, 2, 3, 1, 2, 4, 1, 2, 3, 1], 4: [1, 2, 3, 1]})
    doc = _confidence(runs, monkeypatch, ON)
    # 4 has four starts, below PLAYER_MIN_SAMPLE; 50 is a team row.
    player = [x for x in doc["legs"] if x["market"] == MARKET]
    assert _ids(player) == {1, 2, 3}
    assert {1, 2, 3} <= _ids(doc["singles"])  # one-sided singles, own curve
    for leg in player:
        assert leg[epochs.PLAYER_SAMPLE_MARKER] == "NO_SHAPE_GATES"
        assert leg["one_sided_market"] is True
    # admitted as a single only: no builder holds a leg the gates would refuse
    assert not any(leg["market"] == MARKET
                   for b in doc["builders"] for leg in b["legs"])
