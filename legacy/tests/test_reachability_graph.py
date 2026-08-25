from __future__ import annotations

from scripts.validate_reachability_graph import build


def test_every_tracked_file_has_an_explicit_classification() -> None:
    graph, classification = build()

    assert classification["unknown_files"] == []
    assert classification["tracked_file_count"] == len(classification["files"])
    assert graph["root_evidence"]["manifest_wrappers"]
    assert graph["root_evidence"]["production_agents"]
    assert graph["root_evidence"]["production_skills"]


def test_reachability_records_python_and_migration_evidence() -> None:
    graph, _classification = build()

    assert "scripts/pipeline_steps/run_daily_pipeline.py" in graph["python_edges"]
    assert graph["migration_order"] == sorted(graph["migration_order"])
