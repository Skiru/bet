"""Focused sweep tests for script-wrapper evidence contracts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from bet.pipeline.integration_artifacts import write_script_evidence
from bet.pipeline.orchestrator import Orchestrator
from scripts.pipeline_steps import s2_tipsters
from scripts.pipeline_steps import s3_stats
from scripts.pipeline_steps import s4_valuator
from scripts.pipeline_steps import s5_gate
from scripts.pipeline_steps import s6_repeats
from scripts.pipeline_steps import s7_validate
from scripts.pipeline_steps import s8_build_coupons


WRAPPER_CASES = (
    {
        "step_id": "S2",
        "module": s2_tipsters,
        "argv0": "s2_tipsters.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["tipster_aggregator.py", "tipster_xref.py"],
        "block_token": "BLOCKED_NO_VALID_TIPS",
        "no_pick": True,
    },
    {
        "step_id": "S3",
        "module": s3_stats,
        "argv0": "s3_stats.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["deep_stats_report.py"],
        "block_token": "BLOCKED_STATS_INPUT_MISSING",
        "no_pick": True,
    },
    {
        "step_id": "S6",
        "module": s6_repeats,
        "argv0": "s6_repeats.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["check_48h_repeats.py"],
        "block_token": "BLOCKED_REPEAT_SIGNAL_CONFLICT",
        "no_pick": True,
    },
    {
        "step_id": "S7",
        "module": s5_gate,
        "argv0": "s5_gate.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["gate_checker.py"],
        "block_token": "BLOCKED_HARD_APPROVAL_GATE",
        "no_pick": True,
    },
    {
        "step_id": "S7b",
        "module": s7_validate,
        "argv0": "s7_validate.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["validate_betclic_markets.py"],
        "block_token": "BLOCKED_MARKET_AVAILABILITY_MISSING",
        "no_pick": True,
    },
    {
        "step_id": "S8",
        "module": s8_build_coupons,
        "argv0": "s8_build_coupons.py",
        "run_patch": "scripts.pipeline_steps._script_evidence.run_scripts",
        "expected_scripts": ["coupon_builder.py"],
        "block_token": "BLOCKED_COUPON_INPUT_MISSING",
        "no_pick": False,
    },
)


def _runtime_environ(step_id: str) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-wrapper-sweep-{step_id.lower()}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": f"run-{step_id.lower()}",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _canonical_evidence_path(environ: dict[str, str], step_id: str) -> Path:
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / f"{step_id}.json"
    )


def _mirrored_evidence_path(environ: dict[str, str], step_id: str) -> Path:
    return Path(environ["BET_PIPELINE_ARTIFACT_DIR"]) / f"{step_id}.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_s3_shortlist(environ: dict[str, str]) -> Path:
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


def _write_s3_reports(environ: dict[str, str], *, with_data: int = 1) -> None:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    betting_day = environ["BET_PIPELINE_BETTING_DAY"]
    (data_dir / f"{betting_day}_s3_deep_stats.md").write_text("# S3\n", encoding="utf-8")
    (data_dir / f"{betting_day}_s3_deep_stats.json").write_text(
        json.dumps(
            {
                "date": betting_day,
                "total_candidates": 1,
                "candidates_with_data": with_data,
                "analyses": [],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("case", WRAPPER_CASES, ids=lambda case: case["step_id"])
def test_target_wrappers_write_pass_script_evidence_in_tmp_sandbox(case):
    environ = _runtime_environ(case["step_id"])
    argv = [
        case["argv0"],
        "--date", "2026-06-25",
        "--run-id", environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode", "DRY_RUN",
        "--dry-run",
    ]

    s3_shortlist_path = None
    if case["step_id"] == "S3":
        s3_shortlist_path = _seed_s3_shortlist(environ)

    def _s3_pass(*, betting_day, shortlist_path, child_env, runtime_mode):
        assert shortlist_path == s3_shortlist_path
        _write_s3_reports(environ, with_data=1)
        return (0, "")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if case["step_id"] == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_s3_pass)
        else:
            patch_target = patch(case["run_patch"], return_value=0)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                case["module"].main()

    assert exc_info.value.code == 0
    canonical_path = _canonical_evidence_path(environ, case["step_id"])
    mirrored_path = _mirrored_evidence_path(environ, case["step_id"])
    assert canonical_path.exists()
    assert mirrored_path.exists()
    assert str(canonical_path).startswith("/tmp/")
    assert str(mirrored_path).startswith("/tmp/")
    assert "/reports/" not in str(canonical_path)
    assert "/reports/" not in str(mirrored_path)

    evidence = _load(canonical_path)
    assert evidence == _load(mirrored_path)
    assert evidence["artifact_type"] == "SCRIPT_EVIDENCE"
    assert evidence["step_id"] == case["step_id"]
    assert evidence["status"] == "PASS"
    assert evidence["production_selectable"] is False
    assert evidence["betting_decisions_enabled"] is False
    expected_payload = {
        "step_id": case["step_id"],
        "wrapper_scripts": case["expected_scripts"],
        "runtime_mode": "DRY_RUN",
        "dry_run": True,
        "allow_write": False,
        "allow_live_network": False,
        "production_write": False,
        "runtime_path_source": "orchestrator_inherited_sandbox",
        "child_run_root": environ["BET_PIPELINE_RUN_ROOT"],
        "child_artifact_dir": environ["BET_PIPELINE_ARTIFACT_DIR"],
    }
    if case["step_id"] == "S3":
        payload = evidence["payload"]
        for key, value in expected_payload.items():
            assert payload[key] == value
        assert payload["wrapper_rc"] == 0
        assert payload["shortlist_resolved"] is True
        assert payload["shortlist_event_count"] == 1
        assert payload["shortlist_path"] == str(s3_shortlist_path)
        assert all(path.startswith("/tmp/") for path in payload["s3_report_paths"])
    else:
        expected_payload["wrapper_rc"] = 0
        assert evidence["payload"] == expected_payload
    if case["no_pick"]:
        assert evidence["no_pick_edge_stake_coupon_emitted"] is True
        assert "production_coupon_write" not in evidence
    else:
        assert evidence["no_pick_edge_stake_coupon_emitted"] is False
        assert evidence["production_coupon_write"] is False


@pytest.mark.parametrize("case", WRAPPER_CASES, ids=lambda case: case["step_id"])
def test_target_wrappers_write_block_evidence_for_controlled_output(case, capsys: pytest.CaptureFixture[str]):
    environ = _runtime_environ(case["step_id"])
    argv = [
        case["argv0"],
        "--date", "2026-06-25",
        "--run-id", environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode", "DRY_RUN",
        "--dry-run",
    ]

    if case["step_id"] == "S3":
        _seed_s3_shortlist(environ)

    def _controlled(*args, **kwargs):
        print(case["block_token"])
        return 9

    def _s3_controlled(*args, **kwargs):
        return (9, f"{case['block_token']}\n")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if case["step_id"] == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_s3_controlled)
        else:
            patch_target = patch(case["run_patch"], side_effect=_controlled)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                case["module"].main()

    assert exc_info.value.code == 9
    captured = capsys.readouterr()
    if case["step_id"] != "S3":
        assert case["block_token"] in captured.out
    evidence = _load(_canonical_evidence_path(environ, case["step_id"]))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == [case["block_token"]]


@pytest.mark.parametrize("case", WRAPPER_CASES, ids=lambda case: case["step_id"])
def test_target_wrappers_write_failed_evidence_for_unexpected_non_zero(case):
    environ = _runtime_environ(case["step_id"])
    argv = [
        case["argv0"],
        "--date", "2026-06-25",
        "--run-id", environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode", "DRY_RUN",
        "--dry-run",
    ]

    if case["step_id"] == "S3":
        _seed_s3_shortlist(environ)

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if case["step_id"] == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", return_value=(42, "unexpected crash"))
        else:
            patch_target = patch(case["run_patch"], return_value=42)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                case["module"].main()

    assert exc_info.value.code == 42
    evidence = _load(_canonical_evidence_path(environ, case["step_id"]))
    assert evidence["status"] == "FAILED"
    assert evidence["blocked_reasons"] == ["FAILED_UNEXPECTED_SUBPROCESS_ERROR"]


def test_s4_wrapper_contract_pass_block_failed_and_tmp_paths():
    environ = _runtime_environ("S4")
    argv = [
        "s4_valuator.py",
        "--date", "2026-06-25",
        "--run-id", environ["BET_PIPELINE_RUN_ID"],
        "--runtime-mode", "DRY_RUN",
        "--dry-run",
    ]
    canonical_path = _canonical_evidence_path(environ, "S4")
    mirrored_path = _mirrored_evidence_path(environ, "S4")

    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = data_dir / "odds_api_snapshot.json"
    snapshot_path.write_text("{}", encoding="utf-8")

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s4_valuator.run_scripts", side_effect=[0, 0]):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 0
    evidence = _load(canonical_path)
    assert evidence == _load(mirrored_path)
    assert evidence["status"] == "PASS"
    assert evidence["no_pick_edge_stake_coupon_emitted"] is True
    assert evidence["production_selectable"] is False
    assert evidence["betting_decisions_enabled"] is False
    assert evidence["payload"]["runtime_path_source"] == "orchestrator_inherited_sandbox"
    assert evidence["payload"]["child_artifact_dir"] == environ["BET_PIPELINE_ARTIFACT_DIR"]
    assert str(canonical_path).startswith("/tmp/")
    assert "/reports/" not in str(canonical_path)

    snapshot_path.unlink()
    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s4_valuator.run_scripts", side_effect=[0, 0]):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 1
    evidence = _load(canonical_path)
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_LIVE_SOURCE_MISSING"]

    with patch.dict(os.environ, environ, clear=False), \
         patch.object(sys, "argv", argv), \
         patch("scripts.pipeline_steps.s4_valuator.run_scripts", return_value=77):
        with pytest.raises(SystemExit) as exc_info:
            s4_valuator.main()

    assert exc_info.value.code == 77
    evidence = _load(canonical_path)
    assert evidence["status"] == "FAILED"
    assert evidence["blocked_reasons"] == ["FAILED_UNEXPECTED_SUBPROCESS_ERROR"]


def test_orchestrator_links_wrapper_block_evidence_without_missing_marker(tmp_path):
    reports_root = tmp_path / "sandbox"
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-s4-block-link",
        runtime_mode="DRY_RUN",
        base_run_dir=reports_root,
    )

    write_script_evidence(
        "S2.9",
        status="PASS",
        payload={"test": True},
        sources=(),
        evidence_refs=(),
        environ=orch.env,
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
    )
    write_script_evidence(
        "S3",
        status="PASS",
        payload={"test": True},
        sources=(),
        evidence_refs=(),
        environ=orch.env,
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
    )

    with patch("bet.pipeline.orchestrator.subprocess.run") as mock_run:
        def side_effect(*args, **kwargs):
            write_script_evidence(
                "S4",
                status="BLOCK",
                payload={"test": True},
                sources=(),
                evidence_refs=(),
                environ=orch.env,
                no_pick_edge_stake_coupon_emitted=True,
                production_selectable=False,
                betting_decisions_enabled=False,
                blocked_reasons=("BLOCKED_UPSTREAM_DATA_MISSING",),
            )
            result = MagicMock()
            result.returncode = 1
            return result

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S4", stop_after_step="S4")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S4"
    step = next(item for item in summary["steps"] if item["step_id"] == "S4")
    assert step["evidence_path"]
    assert not any("BLOCKED_SCRIPT_EVIDENCE_MISSING" in str(blocker) for blocker in summary["blockers"])
    summary_path = orch.run_root / "run_summary.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    s4_step = next(item for item in summary_data["steps"] if item["step_id"] == "S4")
    assert s4_step["evidence_path"] == step["evidence_path"]
