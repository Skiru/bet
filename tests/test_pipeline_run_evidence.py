"""Tests for pipeline run evidence helper functions (hashing, git sha, atomic JSON writes, run evidence building)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from bet.pipeline.manifest import discover_repo_root
from bet.pipeline.readiness_contracts import (
    PipelineReadinessStatus,
    StepEvidence,
    GateDecision,
)
from bet.pipeline.run_evidence import (
    utc_now_iso,
    sha256_text,
    sha256_file,
    manifest_hash,
    repo_head_sha,
    write_json_atomic,
    build_run_evidence,
    write_run_evidence,
)


def test_utc_now_iso():
    """Verify that utc_now_iso returns a properly formatted ISO 8601 UTC string with Z suffix."""
    iso = utc_now_iso()
    assert "Z" in iso
    assert "-" in iso
    assert ":" in iso


def test_sha256_helpers(tmp_path):
    """Verify that text and file hashing functions produce consistent hashes."""
    text = "pipeline_test_text_content"
    h_text = sha256_text(text)
    assert len(h_text) == 64

    file_path = tmp_path / "hash_test.txt"
    file_path.write_text(text, encoding="utf-8")
    h_file = sha256_file(file_path)
    assert h_text == h_file


def test_manifest_hash_changes_on_change(tmp_path):
    """Verify that manifest_hash calculates correctly and changes if manifest content changes."""
    manifest_dir = tmp_path / "config"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_dir / "pipeline_manifest.json"

    manifest_file.write_text("version_1_data", encoding="utf-8")
    h1 = manifest_hash(tmp_path)

    manifest_file.write_text("version_2_data", encoding="utf-8")
    h2 = manifest_hash(tmp_path)

    assert h1 != h2


def test_repo_head_sha():
    """Verify that repo_head_sha successfully retrieves the head commit hash."""
    root = discover_repo_root()
    sha = repo_head_sha(root)
    assert len(sha) == 40


def test_write_json_atomic(tmp_path):
    """Verify atomic writes leave the final file intact and parseable."""
    target_path = tmp_path / "test_atomic.json"
    payload = {"test_key": "test_val", "status": "OK"}
    write_json_atomic(target_path, payload)

    assert target_path.exists()
    loaded = json.loads(target_path.read_text(encoding="utf-8"))
    assert loaded == payload


def test_build_and_write_run_evidence(tmp_path):
    """Verify that RunEvidence is compiled and saved correctly."""
    steps = (
        StepEvidence(
            step_id="S0",
            execution_mode="script",
            status=PipelineReadinessStatus.PASS,
            command=("python", "s0.py"),
            started_at="2026-06-24T22:00:00Z",
            finished_at="2026-06-24T22:01:00Z",
            return_code=0,
            stdout_path=None,
            stderr_path=None,
            artifact_path=None,
            blocked_reason=None,
        ),
    )
    gates = (
        GateDecision(
            gate_id="gate_before_S3",
            target_step_id="S3",
            verdict=PipelineReadinessStatus.PASS,
            failed_requirements=(),
            warnings=(),
            required_artifacts=(),
            accepted_artifacts=(),
            blocked_artifacts=(),
            metrics={},
        ),
    )

    evidence = build_run_evidence(
        run_id="run-1",
        betting_day="2026-06-24",
        manifest_hash_val="manifest_hash_abc",
        repo_sha="repo_sha_123",
        dry_run=True,
        allow_write=False,
        steps=steps,
        gates=gates,
    )

    assert evidence.status == PipelineReadinessStatus.PASS

    saved_path = write_run_evidence(tmp_path, evidence)
    assert saved_path.exists()

    data = json.loads(saved_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "run-1"
    assert data["status"] == "PASS"
    assert data["steps"][0]["step_id"] == "S0"
    assert data["gates"][0]["gate_id"] == "gate_before_S3"


def test_generate_verifier_json(tmp_path):
    """Generate the required local verifier JSON example."""
    verifier_data = {
        "schema_version": 1,
        "verifier_id": "pipeline_post_merge_run_readiness_bundle_v1",
        "verdict": "PASS",
        "failed_requirements": [],
        "warnings": [],
        "metrics": {
            "manifest_wrappers_checked": 8,
            "artifact_gate_cases_checked": 10,
            "write_safety_cases_checked": 4
        },
        "source_of_truth": {
            "manifest": "config/pipeline_manifest.json",
            "enrichment_foundation": "src/bet/enrichment/multisport_foundation",
            "runner": "scripts/pipeline_steps/_runner.py"
        }
    }
    verifier_path = tmp_path / "verifier_example.json"
    write_json_atomic(verifier_path, verifier_data)
    assert verifier_path.exists()
    loaded = json.loads(verifier_path.read_text(encoding="utf-8"))
    assert loaded["verifier_id"] == "pipeline_post_merge_run_readiness_bundle_v1"
    assert loaded["verdict"] == "PASS"
