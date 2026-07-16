"""Focused tests for S3 sandbox shortlist handoff remediation."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from bet.pipeline.run_evidence import sha256_file
from bet.pipeline.runtime_paths import is_system_temp_path, paths_refer_to_same_location
from scripts.pipeline_steps import s3_stats


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s3-remediation-{tmp_path.name}-{uuid4().hex[:8]}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s3-remediation",
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


def _write_shortlist(environ: dict[str, str], payload: dict) -> Path:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    shortlist_path = data_dir / f"{environ['BET_PIPELINE_BETTING_DAY']}_s2_shortlist.json"
    candidates = payload.get("candidates", payload.get("events", []))
    artifact = {
        "artifact_type": "S2_SHORTLIST",
        "total_candidates": len(candidates) if isinstance(candidates, list) else None,
        **payload,
    }
    shortlist_path.write_text(json.dumps(artifact), encoding="utf-8")
    artifact_dir = Path(environ["BET_PIPELINE_ARTIFACT_DIR"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "S2.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S2",
                "status": "PASS",
                "betting_day": environ["BET_PIPELINE_BETTING_DAY"],
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "payload": {
                    "s2_shortlist_path": str(shortlist_path),
                    "s2_output_sha256": sha256_file(shortlist_path),
                },
            }
        ),
        encoding="utf-8",
    )
    return shortlist_path


def _write_s3_reports(environ: dict[str, str], *, with_data: int) -> None:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    betting_day = environ["BET_PIPELINE_BETTING_DAY"]
    (data_dir / f"{betting_day}_s3_deep_stats.md").write_text("# S3\n", encoding="utf-8")
    (data_dir / f"{betting_day}_s3_deep_stats.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact_type": "S3_DEEP_STATS",
                "betting_day": betting_day,
                "run_id": environ["BET_PIPELINE_RUN_ID"],
                "source_s2_path": str(data_dir / f"{betting_day}_s2_shortlist.json"),
                "source_s2_sha256": sha256_file(data_dir / f"{betting_day}_s2_shortlist.json"),
                "total_candidates": 1,
                "candidates_with_data": with_data,
                "analyses": [],
            }
        ),
        encoding="utf-8",
    )


def test_s3_wrapper_resolves_shortlist_from_data_dir_and_passes_shortlist_path(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    shortlist_path_expected = _write_shortlist(
        environ,
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
        },
    )
    data_alias = Path(environ["BET_PIPELINE_RUN_ROOT"]) / "data-alias"
    data_alias.symlink_to(shortlist_path_expected.parent, target_is_directory=True)
    aliased_shortlist_path = data_alias / shortlist_path_expected.name
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
        assert betting_day == "2026-06-25"
        assert shortlist_path.resolve() == shortlist_path_expected.resolve()
        assert child_env["BET_PIPELINE_DATA_DIR"] == environ["BET_PIPELINE_DATA_DIR"]
        _write_s3_reports(environ, with_data=1)
        report_path = (
            Path(environ["BET_PIPELINE_DATA_DIR"])
            / "2026-06-25_s3_deep_stats.json"
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["source_s2_path"] = str(aliased_shortlist_path)
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return (0, "")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch(
        "scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_invoke
    ):
        with pytest.raises(SystemExit) as exc_info:
            s3_stats.main()

    assert exc_info.value.code == 0
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert paths_refer_to_same_location(
        evidence["payload"]["shortlist_path"], shortlist_path_expected
    )
    assert evidence["payload"]["shortlist_resolved"] is True
    assert evidence["payload"]["shortlist_event_count"] == 1
    assert evidence["payload"]["s3_report_paths"]
    assert all(is_system_temp_path(path) for path in evidence["payload"]["s3_report_paths"])


def test_s3_wrapper_blocks_when_shortlist_missing(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
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

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s3_stats.main()

    assert exc_info.value.code == 2
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S3_SHORTLIST_MISSING"]
    assert evidence["payload"]["shortlist_path"] is None
    assert evidence["payload"]["shortlist_resolved"] is False
    assert evidence["payload"]["searched_paths"]


def test_s3_wrapper_blocks_when_shortlist_json_is_invalid(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    shortlist_path = _write_shortlist(environ, {"candidates": [{}]})
    shortlist_path.write_text("{not-json", encoding="utf-8")
    evidence_path = Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / "S2.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["payload"]["s2_output_sha256"] = sha256_file(shortlist_path)
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
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

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s3_stats.main()

    assert exc_info.value.code == 2
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S3_SHORTLIST_INVALID"]
    assert evidence["payload"]["shortlist_path"] is None


def test_s3_wrapper_blocks_when_shortlist_is_empty(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    _write_shortlist(environ, {"candidates": []})
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

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s3_stats.main()

    assert exc_info.value.code == 2
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S3_SHORTLIST_EMPTY"]
    assert evidence["payload"]["shortlist_event_count"] == 0
