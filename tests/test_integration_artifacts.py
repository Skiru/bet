from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.pipeline.integration_artifacts import (
    build_market_availability_artifact,
    require_pass_script_evidence,
    runtime_context,
    script_evidence_path,
    write_script_evidence,
)
from bet.pipeline.runtime_modes import LIVE_ACK_KEY, LIVE_ACK_VALUE, RuntimeMode
from bet.pipeline.runtime_paths import build_runtime_env


def test_runtime_context_and_evidence_path(tmp_path):
    env = build_runtime_env(RuntimeMode.LIVE_SHADOW, "2026-06-25", "run-123", base_dir=tmp_path)
    ctx = runtime_context(env)
    assert ctx["betting_day"] == "2026-06-25"
    assert ctx["run_id"] == "run-123"
    path = script_evidence_path("S7", env)
    assert path == tmp_path / "2026-06-25" / "run-123" / "pipeline_runs" / "2026-06-25" / "run-123" / "artifacts" / "S7.json"


def test_write_and_require_pass_script_evidence(tmp_path, monkeypatch: pytest.MonkeyPatch):
    env = build_runtime_env(RuntimeMode.LIVE_SHADOW, "2026-06-25", "run-123", base_dir=tmp_path)
    env[LIVE_ACK_KEY] = LIVE_ACK_VALUE
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    s7_path = write_script_evidence(
        "S7",
        status="PASS",
        payload={"approved_count": 3},
        sources=("gate_checker",),
        evidence_refs=("2026-06-25_s7_gate_results.json",),
    )
    s7b_path = write_script_evidence(
        "S7b",
        status="PASS",
        payload={"total_events": 12},
        sources=("Betclic",),
        evidence_refs=("betclic_market_validation_2026-06-25.json",),
    )

    assert s7_path and s7_path.exists()
    assert s7b_path and s7b_path.exists()
    loaded = require_pass_script_evidence(("S7", "S7b"))
    assert loaded["S7"]["status"] == "PASS"
    assert loaded["S7b"]["status"] == "PASS"


def test_require_pass_script_evidence_blocks_on_non_pass(tmp_path, monkeypatch: pytest.MonkeyPatch):
    env = build_runtime_env(RuntimeMode.LIVE_SHADOW, "2026-06-25", "run-123", base_dir=tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    write_script_evidence(
        "S7",
        status="PASS",
        payload={"approved_count": 1},
        sources=("gate_checker",),
        evidence_refs=("s7.json",),
    )
    write_script_evidence(
        "S7b",
        status="BLOCK",
        payload={"total_events": 0},
        sources=("Betclic",),
        evidence_refs=("s7b.json",),
    )

    with pytest.raises(ValueError, match="Invalid required script evidence"):
        require_pass_script_evidence(("S7", "S7b"))


def test_build_market_availability_artifact_shape():
    artifact = build_market_availability_artifact(
        date="2026-06-25",
        scanned_at="2026-06-25T08:00:00Z",
        summary={"total_events": 2},
        validation=[{"event": "Liverpool vs Arsenal", "betclic_available": True}],
        events=[{"event_name": "Liverpool - Arsenal", "confirmed_market_types": ["corners_total"]}],
        runtime_mode="LIVE_SHADOW",
        timeout_seconds=20,
    )
    assert artifact["artifact_kind"] == "market_availability"
    assert artifact["stage"] == "S7b"
    assert artifact["timeout_seconds"] == 20
    assert artifact["events"][0]["confirmed_market_types"] == ["corners_total"]
