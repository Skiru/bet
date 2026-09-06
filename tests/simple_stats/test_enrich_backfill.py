"""``run_enrich.py --backfill-from``: a second pass that joins the first run.

Filar F. Before bzzoiro this was pointless -- under Highlightly's 100 calls a
day a second pass had nothing left to spend -- so the merge rules that matter
here are the ones that decide what happens when the retry comes back *worse*.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from bet.simple_stats.contracts import (
    EventDossierListV1,
    EventDossierV1,
    MetricObservation,
    ProviderValue,
)

ENRICH = Path(__file__).resolve().parents[2] / "scripts/simple/run_enrich.py"


@pytest.fixture(scope="module")
def run_enrich():
    spec = importlib.util.spec_from_file_location("run_enrich_under_test", ENRICH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pv(value, match_id):
    return ProviderValue(
        provider="bzzoiro",
        match_id=match_id,
        match_date="2026-08-20",
        opponent="Opponent FC",
        value=value,
        observed_at="2026-08-26T00:00:00+00:00",
    )


def _dossier(event_id, readiness, observations=0, gaps=()):
    metrics = {}
    if observations:
        metrics["corners_total"] = MetricObservation(
            canonical_name="corners_total",
            team_a_l10=[_pv(9.0, f"m{i}") for i in range(observations)],
        )
    return EventDossierV1(
        event_id=event_id, sport="football", metrics=metrics, readiness=readiness,
        data_gaps=list(gaps),
    )


def _list(*dossiers, run_id="run-1", date="2026-08-26"):
    return EventDossierListV1(
        run_id=run_id, date=date, generated_at="2026-08-26T09:00:00+00:00",
        dossiers=list(dossiers),
    )


def test_a_better_readiness_replaces_the_earlier_dossier(run_enrich):
    prior = _list(_dossier("a", "BLOCKED"))
    fresh = _list(_dossier("a", "READY", observations=8), run_id="run-2")

    merged, improved = run_enrich._merge_dossiers(prior, fresh)
    assert improved == 1
    assert merged.dossiers[0].readiness == "READY"


def test_a_worse_retry_never_destroys_what_the_first_run_paid_for(run_enrich):
    """Quota may have run out between the two passes, or a provider gone down.
    Replacing unconditionally would let a backfill delete real data."""
    prior = _list(_dossier("a", "PARTIAL", observations=8))
    fresh = _list(_dossier("a", "BLOCKED"), run_id="run-2")

    merged, improved = run_enrich._merge_dossiers(prior, fresh)
    assert improved == 0
    assert merged.dossiers[0].readiness == "PARTIAL"
    assert len(merged.dossiers[0].metrics["corners_total"].team_a_l10) == 8


def test_same_readiness_with_more_observations_still_counts_as_better(run_enrich):
    prior = _list(_dossier("a", "PARTIAL", observations=3))
    fresh = _list(_dossier("a", "PARTIAL", observations=9), run_id="run-2")

    merged, improved = run_enrich._merge_dossiers(prior, fresh)
    assert improved == 1
    assert len(merged.dossiers[0].metrics["corners_total"].team_a_l10) == 9


def test_every_event_of_the_original_artifact_survives_in_order(run_enrich):
    """This file is the complete account of the day's slate. An event a backfill
    could not improve -- or never attempted -- must still be in it."""
    prior = _list(
        _dossier("a", "READY", observations=9),
        _dossier("b", "BLOCKED"),
        _dossier("c", "PARTIAL", observations=2),
    )
    fresh = _list(_dossier("b", "PARTIAL", observations=4), run_id="run-2")

    merged, improved = run_enrich._merge_dossiers(prior, fresh)
    assert [d.event_id for d in merged.dossiers] == ["a", "b", "c"]
    assert improved == 1


def test_the_merge_keeps_the_first_runs_run_id(run_enrich):
    """Filar F: the backfill joins the existing run rather than minting a second
    run_id for the same day, which a reader would then have to choose between."""
    prior = _list(_dossier("a", "BLOCKED"), run_id="run-1")
    fresh = _list(_dossier("a", "READY", observations=8), run_id="run-2")

    merged, _ = run_enrich._merge_dossiers(prior, fresh)
    assert merged.run_id == "run-1"
    assert merged.date == "2026-08-26"


def test_player_observations_count_towards_the_improvement_test(run_enrich):
    """A pass that adds only player props has still added something, so the
    comparison has to see them; counting team metrics alone would discard a
    props-only backfill."""
    from bet.simple_stats.contracts import PlayerMetricObservation

    prior = _list(_dossier("a", "PARTIAL", observations=4))
    with_props = _dossier("a", "PARTIAL", observations=4)
    with_props = with_props.model_copy(
        update={
            "player_metrics": [
                PlayerMetricObservation(
                    player_id="1", player_name="P", team_side="home",
                    canonical_name="player_total_shots", l10=[_pv(2.0, "p1")],
                )
            ]
        }
    )
    fresh = _list(with_props, run_id="run-2")
    merged, improved = run_enrich._merge_dossiers(prior, fresh)
    assert improved == 1
    assert merged.dossiers[0].player_metrics


def test_a_backfill_does_not_retry_what_the_slate_gate_refused(tmp_path, monkeypatch):
    """A gated fixture is excluded, not incomplete.

    Two reasons it must not be retried. It would spend the pass on events the
    gate refuses again -- and the documented backfill command carries no
    ``--superbet-offer``, so the "Superbet does not price this" rule is not in
    force on that pass and a fixture dropped for having no price would be
    enriched after all. The cap is the opposite case and stays retryable: a
    fixture the first pass could not afford is exactly what a backfill is for.
    """
    import json
    import subprocess
    import sys

    from bet.simple_stats.contracts import EventDossierV1

    prior = {
        "run_id": "RID-1",
        "date": "2026-09-03",
        "generated_at": "2026-09-03T06:00:00+00:00",
        "dossiers": [
            EventDossierV1(
                event_id="gated", sport="football", metrics={}, readiness="BLOCKED",
                data_gaps=["not enriched: bzzoiro did not discover this fixture, so ..."],
            ).model_dump(mode="json"),
            EventDossierV1(
                event_id="capped", sport="football", metrics={}, readiness="BLOCKED",
                data_gaps=["not enriched: run capped at 5 events"],
            ).model_dump(mode="json"),
            EventDossierV1(
                event_id="thin", sport="football", metrics={}, readiness="PARTIAL",
                data_gaps=["espn-football: no recent matches for 'X'"],
            ).model_dump(mode="json"),
        ],
    }
    prior_path = tmp_path / "2026-09-03_event_dossiers.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")

    events = []
    for event_id in ("gated", "capped", "thin"):
        events.append({
            "event_id": event_id, "sport": "football", "competition": "Serie A",
            "home_team": "A", "away_team": "B",
            "start_time": "2999-01-01T18:00:00+00:00",
            "identity_confidence": "CONFIRMED", "status": "ACTIVE",
        })
    list_path = tmp_path / "2026-09-03_event_list.json"
    list_path.write_text(json.dumps({
        "run_id": "RID-1", "generated_at": "x", "date": "2026-09-03",
        "sports": ["football"], "events": events,
    }), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/simple/run_enrich.py",
         "--event-list", str(list_path), "--output-dir", str(tmp_path),
         "--backfill-from", str(prior_path), "--max-events", "10",
         "--skip-preflight", "--no-slate-gate", "--db-path", str(tmp_path / "x.db")],
        capture_output=True, text=True,
    )
    scope = next(
        line for line in result.stdout.splitlines() if "backfill_scope" in line
    )
    assert "gate_refused_not_retried=1" in scope
    # "capped" and "thin" remain retryable; only the gate refusal is dropped.
    assert "incomplete_before=2" in scope


def test_a_backfill_can_repair_an_explanation_it_cannot_improve_on(run_enrich):
    """Same readiness, same observations, a better reason for having neither.

    The 2026-09-04 case. The 13:26 pass recorded Lehecka - Tsitsipas as
    ``team_a: tennis-abstract: no recent matches for 'Jiri Lehecka'`` and said
    nothing about Tsitsipas at all, whose own sample had been discarded in
    silence. A re-run under current code adds ``team_b: ... all 10 matches fall
    outside the 1000-day window (newest 2018-08-27); sample discarded as
    stale``. Zero observations either way and PARTIAL either way, so the
    two-key rule scored them equal and kept the version that hid the reason --
    which made a backfill run *after* a reporting fix unable to deliver it.
    """
    prior = _list(_dossier("a", "PARTIAL", gaps=["team_a: no recent matches"]))
    fresh = _list(
        _dossier("a", "PARTIAL", gaps=[
            "team_a: no recent matches",
            "team_b: all 10 matches fall outside the 1000-day window",
        ]),
        run_id="run-2",
    )

    merged, improved = run_enrich._merge_dossiers(prior, fresh)
    assert improved == 1
    assert len(merged.dossiers[0].data_gaps) == 2


def test_more_reasons_cannot_buy_a_pass_that_returned_less_data(run_enrich):
    """The tie-break must stay a tie-break. A retry that lost observations
    cannot win by listing more reasons for having lost them."""
    prior = _list(_dossier("a", "PARTIAL", observations=8))
    fresh = _list(_dossier("a", "PARTIAL", gaps=["x", "y", "z", "w"]), run_id="run-2")

    merged, improved = run_enrich._merge_dossiers(prior, fresh)
    assert improved == 0
    assert len(merged.dossiers[0].metrics["corners_total"].team_a_l10) == 8


def test_more_reasons_cannot_buy_a_pass_that_lost_readiness(run_enrich):
    prior = _list(_dossier("a", "READY", observations=5))
    fresh = _list(
        _dossier("a", "BLOCKED", observations=5, gaps=["x", "y"]), run_id="run-2"
    )

    merged, improved = run_enrich._merge_dossiers(prior, fresh)
    assert improved == 0
    assert merged.dossiers[0].readiness == "READY"


def test_a_backfill_retries_a_ready_dossier_that_lost_calls_upstream(
    tmp_path, monkeypatch
):
    """READY is not the same as complete.

    Measured 2026-09-05: Bucheon - Daejeon came back READY while three bzzoiro
    calls had failed with UPSTREAM_ERROR. Selecting the backfill scope on
    readiness alone skipped it, so those observations stayed lost. Re-running
    took ``corners_for`` from 8+9 to 10+10 observations and ``p_low`` to 0.6874
    on a 10/10 sweep -- top of the coupon at 1.49. A transient upstream failure
    had hidden a real bet behind a dossier that called itself ready.
    """
    import json
    import subprocess
    import sys

    from bet.simple_stats.contracts import EventDossierV1

    prior = {
        "run_id": "RID-2",
        "date": "2026-09-03",
        "generated_at": "2026-09-03T06:00:00+00:00",
        "dossiers": [
            EventDossierV1(
                event_id="ready-but-lossy", sport="football", metrics={},
                readiness="READY",
                data_gaps=["team_a: bzzoiro: UPSTREAM_ERROR for event 205103"],
            ).model_dump(mode="json"),
            EventDossierV1(
                event_id="ready-and-whole", sport="football", metrics={},
                readiness="READY", data_gaps=[],
            ).model_dump(mode="json"),
        ],
    }
    prior_path = tmp_path / "2026-09-03_event_dossiers.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")

    events = [
        {
            "event_id": event_id, "sport": "football", "competition": "Serie A",
            "home_team": "A", "away_team": "B",
            "start_time": "2999-01-01T18:00:00+00:00",
            "identity_confidence": "CONFIRMED", "status": "ACTIVE",
        }
        for event_id in ("ready-but-lossy", "ready-and-whole")
    ]
    list_path = tmp_path / "2026-09-03_event_list.json"
    list_path.write_text(json.dumps({
        "run_id": "RID-2", "generated_at": "x", "date": "2026-09-03",
        "sports": ["football"], "events": events,
    }), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/simple/run_enrich.py",
         "--event-list", str(list_path), "--output-dir", str(tmp_path),
         "--backfill-from", str(prior_path), "--max-events", "10",
         "--skip-preflight", "--db-path", str(tmp_path / "x.db")],
        capture_output=True, text=True,
    )
    scope = next(
        line for line in result.stdout.splitlines() if "backfill_scope" in line
    )
    # The lossy one is retried and counted; the whole one is left alone.
    assert "retried_for_upstream_error=1" in scope
    assert "retryable_events=1" in scope
