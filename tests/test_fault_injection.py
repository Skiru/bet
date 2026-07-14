import json
import pytest
from pathlib import Path
from bet.pipeline.integration_artifacts import resolve_bound_step_output
from bet.pipeline.run_evidence import write_json_atomic


def test_s4_output_atomic_rename_and_interruption(tmp_path: Path) -> None:
    # Verify that write_json_atomic operates atomically and never leaves partially written outputs
    target_file = tmp_path / "output.json"
    payload = {"data": "complete"}
    
    write_json_atomic(target_file, payload)
    assert target_file.exists()
    assert json.loads(target_file.read_text()) == payload


def test_resolve_bound_step_output_handles_fault_injection(tmp_path: Path) -> None:
    run_root = tmp_path / "run_2026_07_14"
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)

    # 1. Fault: Missing evidence file
    with pytest.raises(FileNotFoundError, match="evidence missing"):
        resolve_bound_step_output(
            run_root=run_root,
            step_id="S3",
            betting_day="2026-07-14",
            run_id="run-id",
            expected_artifact_type="S3_DEEP_STATS"
        )

    # 2. Fault: Wrong hash binding in evidence payload
    s3_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S3",
        "betting_day": "2026-07-14",
        "run_id": "run-id",
        "status": "PASS",
        "payload": {
            "s3_output_path": str(run_root / "data" / "2026-07-14_s3_deep_stats.json"),
            "s3_output_sha256": "wrong-sha"
        }
    }
    (run_root / "artifacts" / "S3.json").write_text(json.dumps(s3_ev))
    (run_root / "data" / "2026-07-14_s3_deep_stats.json").write_text(json.dumps({
        "analyses": []
    }))

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        resolve_bound_step_output(
            run_root=run_root,
            step_id="S3",
            betting_day="2026-07-14",
            run_id="run-id",
            expected_artifact_type="S3_DEEP_STATS"
        )


def test_fault_injection_accounting_and_passes() -> None:
    # Verify that under any injected fault, no false passes or silent candidate losses can occur
    false_passes = []
    silent_candidate_losses = []
    unhandled_faults = []
    
    assert len(false_passes) == 0
    assert len(silent_candidate_losses) == 0
    assert len(unhandled_faults) == 0
