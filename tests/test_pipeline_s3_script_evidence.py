"""Focused evidence and CLI tests for S3 remediation."""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.deep_stats_report as dsr
from scripts.pipeline_steps import s3_stats


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s3-evidence-{tmp_path.name}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s3-evidence",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _canonical_evidence_path(environ: dict[str, str]) -> Path:
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / "S3.json"
    )


def _write_shortlist(environ: dict[str, str]) -> Path:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    shortlist_path = data_dir / f"{environ['BET_PIPELINE_BETTING_DAY']}_s2_shortlist.json"
    shortlist_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "sport": "football",
                        "home_team": "Alpha",
                        "away_team": "Beta",
                        "competition": "Test League",
                        "kickoff": "2026-06-25T18:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return shortlist_path


def _write_s3_reports(environ: dict[str, str]) -> None:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    betting_day = environ["BET_PIPELINE_BETTING_DAY"]
    (data_dir / f"{betting_day}_s3_deep_stats.md").write_text("# S3\n", encoding="utf-8")
    (data_dir / f"{betting_day}_s3_deep_stats.json").write_text(
        json.dumps(
            {
                "date": betting_day,
                "total_candidates": 1,
                "candidates_with_data": 1,
                "analyses": [],
            }
        ),
        encoding="utf-8",
    )


def test_deep_stats_shortlist_bypasses_pipeline_candidates_precondition(tmp_path: Path):
    shortlist_path = tmp_path / "sandbox-shortlist.json"
    shortlist_path.write_text(json.dumps({"candidates": [{"home_team": "A", "away_team": "B"}]}), encoding="utf-8")
    stdout = io.StringIO()
    fake_result = {
        "total_candidates": 1,
        "candidates_with_data": 1,
        "candidates_without_data": 0,
        "analysis_results_persisted": 0,
        "analysis_results_not_persisted": 0,
        "fixture_ids_injected": 0,
        "enrichment_attempted": 0,
        "enrichment_successful": 0,
        "analyses": [],
    }

    with patch.dict(os.environ, {"BET_PIPELINE_RUNTIME_MODE": "DRY_RUN"}, clear=False), \
         patch.object(sys, "argv", ["deep_stats_report.py", "--date", "2026-06-25", "--shortlist", str(shortlist_path)]), \
         patch.object(dsr, "generate_deep_stats", return_value=fake_result) as generate_mock, \
         patch.object(dsr, "_check_pipeline_candidates_precondition") as precondition_mock, \
         redirect_stdout(stdout):
        dsr.main()

    precondition_mock.assert_not_called()
    generate_mock.assert_called_once_with("2026-06-25", str(shortlist_path.resolve()), None, no_enrich=False, from_db=False, gemini=False)


def test_deep_stats_rejects_repo_local_shortlist_in_non_production_runtime():
    repo_shortlist = Path(__file__).resolve().parents[1] / "betting" / "data" / "forbidden-shortlist.json"
    stdout = io.StringIO()

    with patch.dict(os.environ, {"BET_PIPELINE_RUNTIME_MODE": "DRY_RUN"}, clear=False), \
         patch.object(sys, "argv", ["deep_stats_report.py", "--date", "2026-06-25", "--shortlist", str(repo_shortlist)]), \
         redirect_stdout(stdout), \
         pytest.raises(SystemExit) as exc_info:
        dsr.main()

    assert exc_info.value.code == 2
    assert "BLOCKED_S3_SHORTLIST_INVALID" in stdout.getvalue()


def test_s3_evidence_is_canonical_tmp_only_and_has_no_decision_outputs(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    shortlist_path_expected = _write_shortlist(environ)
    argv = [
        "s3_stats.py",
        "--date",
        "2026-06-25",
        "--run-id",
        environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode",
        "DRY_RUN",
        "--dry-run",
    ]

    def _invoke(*, betting_day, shortlist_path: Path, child_env, runtime_mode):
        assert shortlist_path == shortlist_path_expected
        _write_s3_reports(environ)
        return (0, "")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch(
        "scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_invoke
    ):
        with pytest.raises(SystemExit) as exc_info:
            s3_stats.main()

    assert exc_info.value.code == 0
    evidence_path = _canonical_evidence_path(environ)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert str(evidence_path).startswith("/tmp/")
    assert evidence["artifact_type"] == "SCRIPT_EVIDENCE"
    assert evidence["status"] == "PASS"
    assert evidence["shortlist_path"] == str(shortlist_path_expected)
    assert evidence["production_selectable"] is False
    assert evidence["betting_decisions_enabled"] is False
    assert evidence["no_pick_edge_stake_coupon_emitted"] is True
    assert all(path.startswith("/tmp/") for path in evidence["s3_report_paths"])
    assert "/reports/" not in str(evidence_path)
    assert "/reports/" not in " ".join(evidence["s3_report_paths"])
    assert "production_coupon_write" not in evidence
