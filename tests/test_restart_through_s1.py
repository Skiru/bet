from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.pipeline_steps.restart_through_s1 import (
    RestartThroughS1Error,
    prepare_restart_through_s1,
)

DAY = "2026-08-24"
SOURCE_ID = "source-run"
TARGET_ID = "target-run"


def seed_source(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / SOURCE_ID
    (root / "artifacts").mkdir(parents=True)
    (root / "data").mkdir()
    matrix = root / "data" / "market_matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "sport": "football",
                        "competition": "league",
                        "home_team": "A",
                        "away_team": "B",
                        "kickoff": "2026-08-24T12:00:00Z",
                    }
                ]
            }
        )
    )
    s0 = {
        "artifact_type": "SCRIPT_EVIDENCE",
        "schema_version": 1,
        "step_id": "S0",
        "status": "PASS",
        "betting_day": DAY,
        "run_id": SOURCE_ID,
        "payload": {},
    }
    s1 = {
        "artifact_type": "SCRIPT_EVIDENCE",
        "schema_version": 1,
        "step_id": "S1",
        "status": "PASS",
        "betting_day": DAY,
        "run_id": SOURCE_ID,
        "payload": {"market_matrix_path": str(matrix)},
    }
    (root / "artifacts" / "S0.json").write_text(json.dumps(s0))
    (root / "artifacts" / "S1.json").write_text(json.dumps(s1))
    (root / "resume_ledger.json").write_text(json.dumps({"entries": []}))
    return (
        root,
        str(
            __import__("hashlib")
            .sha256((root / "artifacts" / "S0.json").read_bytes())
            .hexdigest()
        ),
        str(
            __import__("hashlib")
            .sha256((root / "artifacts" / "S1.json").read_bytes())
            .hexdigest()
        ),
    )


def test_valid_restart_creates_fresh_target_without_s1e_or_accounting(tmp_path: Path):
    source, s0_sha, s1_sha = seed_source(tmp_path)
    target = tmp_path / TARGET_ID
    result = prepare_restart_through_s1(
        source, target, SOURCE_ID, TARGET_ID, DAY, s0_sha, s1_sha
    )
    assert result["source_s0_sha256"] == s0_sha
    assert result["source_s1_sha256"] == s1_sha
    assert (target / "artifacts" / "S0.json").is_file()
    assert (target / "artifacts" / "S1.json").is_file()
    assert not (target / "artifacts" / "S1e.json").exists()
    assert not (target / "event_accounting_ledger.json").exists()
    assert not (target / "resume_ledger.json").exists()
    assert (
        json.loads((target / "artifacts" / "S1.json").read_text())["run_id"]
        == TARGET_ID
    )


def test_source_hash_mismatch_blocks_before_target_creation(tmp_path: Path):
    source, _, s1_sha = seed_source(tmp_path)
    with pytest.raises(RestartThroughS1Error, match="SOURCE_S0_SHA256_MISMATCH"):
        prepare_restart_through_s1(
            source, tmp_path / TARGET_ID, SOURCE_ID, TARGET_ID, DAY, "0" * 64, s1_sha
        )
    assert not (tmp_path / TARGET_ID).exists()


def test_existing_nonempty_target_blocks(tmp_path: Path):
    source, s0_sha, s1_sha = seed_source(tmp_path)
    target = tmp_path / TARGET_ID
    target.mkdir()
    (target / "keep").write_text("x")
    with pytest.raises(RestartThroughS1Error, match="TARGET_RUN_ROOT_EXISTS_NON_EMPTY"):
        prepare_restart_through_s1(
            source, target, SOURCE_ID, TARGET_ID, DAY, s0_sha, s1_sha
        )


def test_same_run_id_blocks(tmp_path: Path):
    source, s0_sha, s1_sha = seed_source(tmp_path)
    with pytest.raises(RestartThroughS1Error, match="SOURCE_TARGET_RUN_ID_MUST_DIFFER"):
        prepare_restart_through_s1(
            source, tmp_path / TARGET_ID, SOURCE_ID, SOURCE_ID, DAY, s0_sha, s1_sha
        )
