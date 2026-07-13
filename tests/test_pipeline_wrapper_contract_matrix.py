"""Contract matrix for normalized wrapper block classification."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pipeline_steps import s2_tipsters
from scripts.pipeline_steps import s3_stats
from scripts.pipeline_steps import s5_gate
from scripts.pipeline_steps import s6_repeats
from scripts.pipeline_steps import s7_validate
from scripts.pipeline_steps import s8_build_coupons


NORMALIZATION_CASES = (
    ("S2", s2_tipsters, "s2_tipsters.py", ["tipster_aggregator.py", "tipster_xref.py"], "no valid tips after dedupe", "BLOCKED_NO_VALID_TIPS"),
    ("S3", s3_stats, "s3_stats.py", ["deep_stats_report.py"], "insufficient data for stats generation", "BLOCKED_STATS_GENERATION_INSUFFICIENT_DATA"),
    ("S6", s6_repeats, "s6_repeats.py", ["check_48h_repeats.py"], "repeat signal conflict detected", "BLOCKED_REPEAT_SIGNAL_CONFLICT"),
    ("S7", s5_gate, "s5_gate.py", ["gate_checker.py"], "gate failed after hard approval review", "BLOCKED_HARD_APPROVAL_GATE"),
    ("S7b", s7_validate, "s7_validate.py", ["validate_betclic_markets.py"], "manual verification required before Betclic validation", "BLOCKED_BETCLIC_MARKET_BOUNDARY"),
    ("S8", s8_build_coupons, "s8_build_coupons.py", ["coupon_builder.py"], "coupon blocked by construction guard", "BLOCKED_COUPON_CONSTRUCTION_GUARD"),
)


def _runtime_environ(step_id: str) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-wrapper-matrix-{step_id.lower()}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": f"run-{step_id.lower()}-matrix",
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


def _seed_s3_shortlist(environ: dict[str, str]) -> None:
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / f"{environ['BET_PIPELINE_BETTING_DAY']}_s2_shortlist.json").write_text(
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


@pytest.mark.parametrize("step_id,module,argv0,expected_scripts,message,expected_reason", NORMALIZATION_CASES)
def test_wrapper_contract_matrix_normalizes_controlled_block_outputs(
    step_id: str,
    module,
    argv0: str,
    expected_scripts: list[str],
    message: str,
    expected_reason: str,
):
    environ = _runtime_environ(step_id)
    argv = [argv0, "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    if step_id == "S3":
        _seed_s3_shortlist(environ)

    def _controlled(*args, **kwargs):
        print(message)
        return 5

    def _s3_controlled(*args, **kwargs):
        return (5, f"{message}\n")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if step_id in {"S7b", "S8"}:
            patch_target = patch("builtins.print")
        elif step_id == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_s3_controlled)
        else:
            patch_target = patch("scripts.pipeline_steps._script_evidence.run_scripts", side_effect=_controlled)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                module.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ, step_id).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    if step_id == "S7b":
        assert evidence["blocked_reasons"] == ["BLOCKED_S7B_CANONICAL_S7_MISSING"]
    elif step_id == "S8":
        assert evidence["blocked_reasons"] == ["BLOCKED_S8_CANONICAL_S7B_INVALID"]
    else:
        assert evidence["blocked_reasons"] == [expected_reason]
        assert evidence["payload"]["wrapper_scripts"] == expected_scripts


@pytest.mark.parametrize(
    "step_id,module,argv0,message,expected_reason",
    (
        ("S2", s2_tipsters, "s2_tipsters.py", "missing upstream shortlist input", "BLOCKED_TIPSTER_DATA_MISSING"),
        ("S3", s3_stats, "s3_stats.py", "snapshot missing for stats stage", "BLOCKED_STATS_INPUT_MISSING"),
        ("S6", s6_repeats, "s6_repeats.py", "repeat guard input missing", "BLOCKED_REPEAT_GUARD_INPUT_MISSING"),
        ("S7", s5_gate, "s5_gate.py", "approved picks missing before gate", "BLOCKED_APPROVED_PICKS_MISSING"),
        ("S7b", s7_validate, "s7_validate.py", "market unavailable for validation snapshot", "BLOCKED_MARKET_AVAILABILITY_MISSING"),
        ("S8", s8_build_coupons, "s8_build_coupons.py", "missing approved picks for coupon build", "BLOCKED_COUPON_INPUT_MISSING"),
    ),
)
def test_wrapper_contract_matrix_generic_controlled_phrases_map_to_expected_reason(
    step_id: str,
    module,
    argv0: str,
    message: str,
    expected_reason: str,
):
    environ = _runtime_environ(step_id)
    argv = [argv0, "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    if step_id == "S3":
        _seed_s3_shortlist(environ)

    def _controlled(*args, **kwargs):
        print(message)
        return 6

    def _s3_controlled(*args, **kwargs):
        return (6, f"{message}\n")

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        if step_id in {"S7b", "S8"}:
            patch_target = patch("builtins.print")
        elif step_id == "S3":
            patch_target = patch("scripts.pipeline_steps.s3_stats._invoke_deep_stats_report", side_effect=_s3_controlled)
        else:
            patch_target = patch("scripts.pipeline_steps._script_evidence.run_scripts", side_effect=_controlled)
        with patch_target:
            with pytest.raises(SystemExit) as exc_info:
                module.main()

    assert exc_info.value.code == (5 if step_id in {"S7b", "S8"} else 6)
    evidence = json.loads(_canonical_evidence_path(environ, step_id).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    if step_id == "S7b":
        assert evidence["blocked_reasons"] == ["BLOCKED_S7B_CANONICAL_S7_MISSING"]
    elif step_id == "S8":
        assert evidence["blocked_reasons"] == ["BLOCKED_S8_CANONICAL_S7B_INVALID"]
    else:
        assert evidence["blocked_reasons"] == [expected_reason]
