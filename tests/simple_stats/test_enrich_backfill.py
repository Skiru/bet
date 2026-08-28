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


def _dossier(event_id, readiness, observations=0):
    metrics = {}
    if observations:
        metrics["corners_total"] = MetricObservation(
            canonical_name="corners_total",
            team_a_l10=[_pv(9.0, f"m{i}") for i in range(observations)],
        )
    return EventDossierV1(
        event_id=event_id, sport="football", metrics=metrics, readiness=readiness
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
