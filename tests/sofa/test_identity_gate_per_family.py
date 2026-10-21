"""The internal identity gate per family (epochs.IDENTITY_GATE_PER_FAMILY,
2026-10-21).

Roma - Real Madrid (16938872, 2026-10-14, 3-4): Real's shots read total 16
against on 8 + off 8 + blocked 1 = 17 with no woodwork key, the goals and
every other count consistent - and the whole-match gate dropped all of Real's
metrics from the sample (INTERNAL_INCONSISTENT). On, the shot identity blocks
only the shot metrics; tennis' gamesWon identity still drops the whole match.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa.contracts import FixtureSamples, GapReason
from bet.sofa.metrics import (
    IDENTITY_GOAL_INCIDENTS,
    IDENTITY_SCORE_PERIODS,
    IDENTITY_SHOTS,
    IDENTITY_WHOLE_MATCH,
    check_identities,
    extract_flat_statistics,
    identity_failures,
    identity_gap_for_metric,
)
from bet.sofa.samples import process_historical_event
from bet.sofa.settle import historical_sample

KICKOFF = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)
ROMA, REAL = 2702, 2829

# 16938872's cached /statistics (ALL), the keys the test reads
STATS_ALL = {
    "totalShotsOnGoal": (14, 16), "shotsOnGoal": (7, 8), "shotsOffGoal": (4, 8),
    "blockedScoringAttempt": (3, 1), "cornerKicks": (5, 9),
    "yellowCards": (3, 1), "fouls": (15, 8), "passes": (546, 462),
}


def _stats(items: dict[str, tuple[int, int]]) -> dict[str, Any]:
    return {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": [
        {"key": k, "homeValue": h, "awayValue": a} for k, (h, a) in items.items()
    ]}]}]}


def _incidents() -> dict[str, Any]:
    """16938872's incidents: 7 goals (home 20', 51', 57'; away 25', 83',
    85', 90'), 4 yellows, a substitution (a full feed)."""
    goals = [(True, 20), (False, 25), (True, 51), (True, 57), (False, 83),
             (False, 85), (False, 90)]
    cards = [(True, 60, 611210), (True, 69, 1134200), (True, 89, 555540),
             (False, 90, 1085081)]
    out: list[dict[str, Any]] = [
        {"incidentType": "goal", "incidentClass": "regular", "isHome": h,
         "time": t} for h, t in goals]
    out += [{"incidentType": "card", "incidentClass": "yellow", "isHome": h,
             "time": t, "player": {"id": pid}} for h, t, pid in cards]
    out.append({"incidentType": "substitution", "isHome": True, "time": 63})
    return {"incidents": out}


def _event(eid: int = 16938872) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": int(KICKOFF.timestamp()),
        "status": {"type": "finished", "code": 100},
        "homeTeam": {"id": ROMA, "name": "Roma"},
        "awayTeam": {"id": REAL, "name": "Real Madrid"},
        "homeScore": {"current": 3, "period1": 1, "period2": 2, "normaltime": 3},
        "awayScore": {"current": 4, "period1": 1, "period2": 3, "normaltime": 4},
        "tournament": {"uniqueTournament": {"id": 7}},
        "season": {"id": 1},
    }


METRICS = {"goals_for", "goals_total", "corners_for", "cards_points_for",
           "fouls_for", "shots_for", "shots_on_target_for", "shots_1h_for"}
SHOT_METRICS = {"shots_for", "shots_on_target_for", "shots_1h_for"}


def _observe(per_family: bool) -> dict[str, Any]:
    cache = MagicMock()
    cache.get_event_stats.return_value = (
        _stats(STATS_ALL), _incidents(), "finished")
    out = process_historical_event(
        MagicMock(), cache, _event(), REAL, "football", set(METRICS),
        MagicMock(), per_family_identity=per_family)
    collected: dict[str, Any] = out["collected"]
    return collected


def test_the_shot_identity_is_the_only_one_real_madrid_fails() -> None:
    flat = extract_flat_statistics(_stats(STATS_ALL))
    failed = identity_failures(flat, _incidents(), _event(), "football")
    assert failed == {IDENTITY_SHOTS: GapReason.INTERNAL_INCONSISTENT}
    assert check_identities(flat, _incidents(), _event(), "football") is (
        GapReason.INTERNAL_INCONSISTENT)


def test_per_family_brings_back_goals_corners_cards_and_keeps_shots_out() -> None:
    got = _observe(per_family=True)
    for metric in SHOT_METRICS:
        assert got[metric] is GapReason.INTERNAL_INCONSISTENT, metric
    values = {m: got[m].value for m in METRICS - SHOT_METRICS}
    assert values == {"goals_for": 4.0, "goals_total": 7.0, "corners_for": 9.0,
                      "cards_points_for": 1.0, "fouls_for": 8.0}


def test_switch_off_drops_the_whole_match_as_before() -> None:
    got = _observe(per_family=False)
    assert all(got[m] is GapReason.INTERNAL_INCONSISTENT for m in METRICS)


def test_a_placeholder_incident_list_blocks_only_incident_metrics() -> None:
    # goal incidents != score: a list holding only the period entries
    flat = extract_flat_statistics(_stats(
        {k: v for k, v in STATS_ALL.items() if not k.startswith(("total", "shots",
                                                                  "blocked"))}))
    incidents = {"incidents": [{"incidentType": "period", "text": "HT"},
                               {"incidentType": "period", "text": "FT"}]}
    failed = identity_failures(flat, incidents, _event(), "football")
    assert set(failed) == {IDENTITY_GOAL_INCIDENTS}
    for metric in ("cards_points_for", "cards_points_1h_total", "red_cards_for",
                   "penalties_for", "both_red_cards"):
        assert identity_gap_for_metric(metric, "football", failed) is (
            GapReason.INTERNAL_INCONSISTENT), metric
    for metric in ("goals_for", "goals_1h_total", "corners_for", "shots_for"):
        assert identity_gap_for_metric(metric, "football", failed) is None, metric


def test_a_home_period_sum_blocks_the_score_reads_only() -> None:
    event = _event()
    event["homeScore"] = {"current": 3, "period1": 1, "period2": 1,
                          "normaltime": 3}
    failed = identity_failures({}, None, event, "football")
    assert set(failed) == {IDENTITY_SCORE_PERIODS}
    for metric in ("goals_for", "goals_2h_total", "red_cards_for"):
        assert identity_gap_for_metric(metric, "football", failed) is not None
    for metric in ("corners_for", "cards_points_for", "shots_for"):
        assert identity_gap_for_metric(metric, "football", failed) is None


def test_tennis_games_won_nonsense_still_drops_the_whole_match() -> None:
    event = {"homeScore": {"current": 2, "period1": 6, "period2": 6},
             "awayScore": {"current": 0, "period1": 2, "period2": 3}}
    flat = {"ALL": {"gamesWon": (22.0, 16.0)}}
    failed = identity_failures(flat, None, event, "tennis")
    assert set(failed) == {IDENTITY_WHOLE_MATCH}
    for metric in ("aces_for", "games_won_for", "sets_total", "tiebreaks_total"):
        assert identity_gap_for_metric(metric, "tennis", failed) is (
            GapReason.INTERNAL_INCONSISTENT)
    ok = {"ALL": {"gamesWon": (12.0, 5.0)}}
    assert identity_failures(ok, None, event, "tennis") == {}


def test_an_unknown_metric_is_gated_by_any_failure() -> None:
    failed = {IDENTITY_SHOTS: GapReason.INTERNAL_INCONSISTENT}
    assert identity_gap_for_metric("no_such_metric", "football", failed) is not None
    assert identity_gap_for_metric("corners_for", "football", {}) is None


def test_the_backfill_sample_reads_the_same_rule() -> None:
    later = dict(_event(), id=2, startTimestamp=int(
        (KICKOFF + timedelta(days=7)).timestamp()))
    kw: dict[str, Any] = {
        "before_utc": KICKOFF + timedelta(days=30), "entity_id": REAL,
        "sport": "football",
        "metrics_by_event": {16938872: _stats(STATS_ALL), 2: _stats(STATS_ALL)},
        "incidents_by_event": {16938872: _incidents(), 2: _incidents()},
        "sample_n": 10}
    events = [_event(), later]
    assert historical_sample(events, metric="corners_for", **kw) == []
    assert historical_sample(events, metric="corners_for",
                             per_family_identity=True, **kw) == [
        (2, 9.0), (16938872, 9.0)]
    assert historical_sample(events, metric="shots_for",
                             per_family_identity=True, **kw) == []


def test_the_switch_reads_the_build_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    on = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "IDENTITY_GATE_PER_FAMILY_FROM_UTC", on)
    assert not epochs.identity_gate_per_family("2026-10-21", on - timedelta(minutes=1))
    assert epochs.identity_gate_per_family("2026-10-21", on)
    assert not epochs.identity_gate_per_family("2026-10-20", on + timedelta(days=1))
    monkeypatch.setattr(epochs, "IDENTITY_GATE_PER_FAMILY_FROM_UTC", None)
    assert not epochs.identity_gate_per_family("2026-10-22", on + timedelta(days=1))


def test_the_marker_is_optional_on_the_samples_contract() -> None:
    old = FixtureSamples.model_validate(
        {"sofascore_event_id": 1, "readiness": "READY", "metrics": {}, "gaps": []})
    assert old.identity_gate is None
    marked = old.model_copy(update={"identity_gate": epochs.IDENTITY_GATE_MARKER})
    assert marked.model_dump(mode="json")["identity_gate"] == "per_family"


# --- the rebuild -------------------------------------------------------------

DATE = "2026-10-21"
SWITCH = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 21, 16, 0, tzinfo=UTC)


def _z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _write_day(runs: Path, samples: list[dict[str, Any]]) -> None:
    run = runs / DATE
    run.mkdir(parents=True)
    fixtures = [
        {"sofascore_event_id": 1, "sport": "football",
         "kickoff_utc": _z(NOW + timedelta(hours=3))},
        {"sofascore_event_id": 2, "sport": "football",
         "kickoff_utc": _z(NOW - timedelta(hours=1))},  # started
        {"sofascore_event_id": 3, "sport": "tennis",
         "kickoff_utc": _z(NOW + timedelta(hours=3))},
        {"sofascore_event_id": 4, "sport": "football",
         "kickoff_utc": _z(NOW + timedelta(hours=3))},
        {"sofascore_event_id": 5, "sport": "football",
         "kickoff_utc": _z(NOW + timedelta(hours=4))},
    ]
    (run / "02_fixtures.json").write_text(json.dumps(fixtures))
    (run / "03_samples.json").write_text(json.dumps(samples))


def _entry(eid: int, reason: str = "INTERNAL_INCONSISTENT",
           marker: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "sofascore_event_id": eid, "readiness": "READY", "metrics": {},
        "gaps": [{"reason": reason, "metric": "corners_for", "detail": "x"}]}
    if marker:
        out["identity_gate"] = marker
    return out


SAMPLES = [_entry(1), _entry(2), _entry(3), _entry(4, "SAMPLE_TOO_SMALL"),
           _entry(5, marker="per_family")]


def test_only_open_unmarked_football_fixtures_with_an_identity_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_day(tmp_path, SAMPLES)
    monkeypatch.setattr(epochs, "IDENTITY_GATE_PER_FAMILY_FROM_UTC", SWITCH)
    assert rp.identity_unsampled(str(tmp_path), DATE, NOW) == (1,)
    assert rp.identity_unsampled(str(tmp_path), DATE,
                                 SWITCH - timedelta(minutes=1)) == ()
    monkeypatch.setattr(epochs, "IDENTITY_GATE_PER_FAMILY_FROM_UTC", None)
    assert rp.identity_unsampled(str(tmp_path), DATE, NOW) == ()


def _plan(state_kw: dict[str, Any]) -> rp.Plan:
    state = rp.DayState(date=DATE, now=NOW, price_max_age=timedelta(minutes=45),
                        open_fixtures=0, **state_kw)
    return rp.build_plan(state, run_id="t")


def test_the_plan_samples_then_prices_the_fixtures_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "IDENTITY_GATE_PER_FAMILY_FROM_UTC", SWITCH)
    plan = _plan({"identity_unsampled": (1, 7)})
    names = plan.names()
    i_samples, i_sheet = names.index("SAMPLES"), names.index("SHEET")
    assert i_samples < i_sheet < names.index("CONFIDENCE")
    assert "BRIDGE" in names[:i_samples]
    assert plan.steps[i_samples].argv[-2:] == ("--event-ids", "1,7")
    assert plan.steps[i_sheet].argv[1] == "scripts/sofa/run_sheet.py"
    assert plan.steps[i_sheet].argv[-2:] == ("--event-ids", "1,7")
    assert plan.steps[i_samples].soft


def test_no_identity_work_no_samples_step(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "IDENTITY_GATE_PER_FAMILY_FROM_UTC", SWITCH)
    assert "SAMPLES" not in _plan({}).names()
    monkeypatch.setattr(epochs, "IDENTITY_GATE_PER_FAMILY_FROM_UTC", None)
    assert "SAMPLES" not in _plan({"identity_unsampled": (1,)}).names()


def test_a_carried_over_sample_keeps_its_old_marker_and_is_tried_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review 2026-10-21: a provider fault in step 1c carried the old,
    whole-match sample over under the fresh entry's per_family marker, so no
    later rebuild re-tried it."""
    from bet.sofa.contracts import GapEntry, GapReason
    from scripts.sofa.run_samples import carry_over_on_provider_fault

    previous = FixtureSamples.model_validate_json(json.dumps(
        {"sofascore_event_id": 4, "readiness": "READY",
         "metrics": {"corners_for": {"metric": "corners_for", "side_a": [],
                                     "side_b": [], "h2h": []}},
         "gaps": [{"reason": "INTERNAL_INCONSISTENT", "metric": "corners_for",
                   "detail": "x"}]}))
    fresh = FixtureSamples(
        sofascore_event_id=4, readiness=previous.readiness, metrics={},
        gaps=[GapEntry(reason=GapReason.CIRCUIT_OPEN, metric="all", detail="open")],
        identity_gate=epochs.IDENTITY_GATE_MARKER)
    carried, did = carry_over_on_provider_fault(fresh, previous)
    assert did and carried.identity_gate is None
    _write_day(tmp_path, [carried.model_dump(mode="json")])
    monkeypatch.setattr(epochs, "IDENTITY_GATE_PER_FAMILY_FROM_UTC", SWITCH)
    assert rp.identity_unsampled(str(tmp_path), DATE, NOW) == (4,)
