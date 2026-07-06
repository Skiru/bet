import json
import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.pipeline_steps.s2_tipsters_shadow_evidence as wrapper_mod
from bet.pipeline.runtime_modes import RuntimeMode


def test_wrapper_fails_closed_without_local_review_json(tmp_path, monkeypatch):
    """Wrapper must fail closed if terms reviewed JSON is not provided or missing."""
    monkeypatch.setattr(sys, "argv", [
        "s2_tipsters_shadow_evidence.py",
        "--date", "2026-07-06",
        "--runtime-mode", "LIVE_SHADOW",
    ])
    with pytest.raises(SystemExit) as exc_info:
        wrapper_mod.main()
    assert exc_info.value.code == 10


def test_wrapper_fails_closed_with_nonexistent_local_review_json(tmp_path, monkeypatch):
    """Wrapper must fail closed if terms reviewed JSON path does not exist."""
    monkeypatch.setattr(sys, "argv", [
        "s2_tipsters_shadow_evidence.py",
        "--date", "2026-07-06",
        "--terms-reviewed-json", str(tmp_path / "nonexistent.json"),
        "--runtime-mode", "LIVE_SHADOW",
    ])
    with pytest.raises(SystemExit) as exc_info:
        wrapper_mod.main()
    assert exc_info.value.code == 11


def test_wrapper_paths_deterministic_and_respect_sandbox(tmp_path, monkeypatch):
    """Verify that default output paths respect BET_PIPELINE_ARTIFACT_DIR/BET_PIPELINE_DATA_DIR."""
    date = "2026-07-06"
    
    # Set up sandbox folders
    run_root = tmp_path / "run_root"
    artifact_dir = run_root / "artifacts"
    data_dir = run_root / "data"
    artifact_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    # Mock environment variables
    monkeypatch.setenv("BET_PIPELINE_RUN_ROOT", str(run_root))
    monkeypatch.setenv("BET_PIPELINE_ARTIFACT_DIR", str(artifact_dir))
    monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BET_PIPELINE_COUPON_DIR", str(run_root / "coupons"))
    monkeypatch.setenv("BET_PIPELINE_BETTING_DAY", date)
    monkeypatch.setenv("BET_PIPELINE_RUN_ID", "default")
    monkeypatch.setenv("BET_PIPELINE_RUNTIME_MODE", "LIVE_SHADOW")

    review_file = tmp_path / "review.json"
    review_file.write_text(json.dumps({
        "source_reviews": {
            "forebet": {
                "status": "allow_live_dry_run",
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "reviewed_by": "operator",
                "reviewed_at_utc": "2026-07-06T12:00:00Z",
            }
        }
    }), encoding="utf-8")

    # Mock the actual execution of s2_tipsters_v2_live_dry_run.py
    # Since we don't want real network/external script calls, we mock subprocess.run
    called_args = []
    class DummyCompletedProcess:
        returncode = 0
        stdout = "total_picks=1\n[live-dry-run] wrote=dummy.json"
        stderr = ""

    def mock_subprocess_run(cmd, env, **kwargs):
        called_args.append((cmd, env))
        # Create mock handoff file to simulate script success
        h_out = cmd[cmd.index("--handoff-out") + 1]
        out = cmd[cmd.index("--out") + 1]
        
        # Write dummy output files
        Path(out).write_text(json.dumps({"total_picks": 1, "consensus": []}), encoding="utf-8")
        Path(h_out).write_text(json.dumps({
            "schema_version": "tipster_evidence_handoff_v1",
            "contract": "evidence_only_not_betting_decision",
            "source_stage": "S2 tipster evidence",
            "allowed_consumers": [],
            "forbidden_actions": ["EV", "stake", "coupon", "final bet", "Superbet combined odds"],
            "sources": [],
            "events": [],
            "fail_closed": False,
        }), encoding="utf-8")
        
        return DummyCompletedProcess()

    monkeypatch.setattr(wrapper_mod.subprocess, "run", mock_subprocess_run)

    monkeypatch.setattr(sys, "argv", [
        "s2_tipsters_shadow_evidence.py",
        "--date", date,
        "--terms-reviewed-json", str(review_file),
        "--runtime-mode", "LIVE_SHADOW",
    ])

    with pytest.raises(SystemExit) as exc_info:
        wrapper_mod.main()

    assert exc_info.value.code == 0
    assert len(called_args) == 1
    
    cmd, env = called_args[0]
    
    # Assert default output paths used sandboxed directories
    out_arg = cmd[cmd.index("--out") + 1]
    handoff_arg = cmd[cmd.index("--handoff-out") + 1]
    sqlite_arg = cmd[cmd.index("--sqlite-db") + 1]

    assert Path(out_arg).parent == data_dir
    assert Path(handoff_arg).parent == artifact_dir
    assert Path(sqlite_arg).parent == data_dir

    # Check that forbidden fields are completely absent and handoff schema matches
    handoff_content = json.loads(Path(handoff_arg).read_text(encoding="utf-8"))
    assert handoff_content["schema_version"] == "tipster_evidence_handoff_v1"
    assert "EV" in handoff_content["forbidden_actions"]
    assert "stake" in handoff_content["forbidden_actions"]
