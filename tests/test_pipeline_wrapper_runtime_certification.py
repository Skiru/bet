"""Tests for wrapper runtime certification and safe runner behavior."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bet.pipeline.manifest import discover_repo_root
from bet.pipeline.wrapper_runtime_certification import (
    certify_manifest_wrappers,
    certify_wrapper,
    classify_wrapper_runtime_status,
    discover_wrapper_targets,
)
from scripts.pipeline_steps import _runner


EXPECTED_TARGETS = {
    "S0": ["scripts/settle_on_finish.py"],
    "S1": ["scripts/discover_events.py", "scripts/build_shortlist.py"],
    "S2": ["scripts/tipster_aggregator.py", "scripts/tipster_xref.py"],
    "S3": ["scripts/deep_stats_report.py"],
    "S4": ["scripts/fetch_odds_multi.py", "scripts/odds_evaluator.py"],
    "S6": ["scripts/check_48h_repeats.py"],
    "S7": ["scripts/gate_checker.py"],
    "S7b": ["scripts/validate_betclic_markets.py"],
    "S8": ["scripts/coupon_builder.py"],
}


@pytest.fixture
def repo_root() -> Path:
    return discover_repo_root()


def test_all_manifest_script_wrappers_are_certified(repo_root: Path):
    report = certify_manifest_wrappers(repo_root)
    assert report["schema_version"] == 1
    assert report["verifier_id"] == "pipeline_wrapper_runtime_certification_a"
    assert set(report["wrappers"]) == set(EXPECTED_TARGETS)


def test_all_wrapper_target_scripts_are_discovered_from_run_scripts(repo_root: Path):
    for step_id, expected_targets in EXPECTED_TARGETS.items():
        wrapper = repo_root / {
            "S0": "scripts/pipeline_steps/s0_settler.py",
            "S1": "scripts/pipeline_steps/s1_discover.py",
            "S2": "scripts/pipeline_steps/s2_tipsters.py",
            "S3": "scripts/pipeline_steps/s3_stats.py",
            "S4": "scripts/pipeline_steps/s4_valuator.py",
            "S6": "scripts/pipeline_steps/s6_repeats.py",
            "S7": "scripts/pipeline_steps/s5_gate.py",
            "S7b": "scripts/pipeline_steps/s7_validate.py",
            "S8": "scripts/pipeline_steps/s8_build_coupons.py",
        }[step_id]
        assert discover_wrapper_targets(wrapper) == expected_targets


def test_all_wrapper_target_scripts_exist(repo_root: Path):
    report = certify_manifest_wrappers(repo_root)
    for step_id, expected_targets in EXPECTED_TARGETS.items():
        assert report["wrappers"][step_id]["targets"] == expected_targets
        assert report["wrappers"][step_id]["targets_exist"] is True


def test_all_wrapper_target_scripts_compile(repo_root: Path):
    report = certify_manifest_wrappers(repo_root)
    for step_id in EXPECTED_TARGETS:
        assert report["wrappers"][step_id]["targets_compile"] is True


def test_s4_target_order_is_fetch_before_evaluator(repo_root: Path):
    wrapper = repo_root / "scripts/pipeline_steps/s4_valuator.py"
    assert discover_wrapper_targets(wrapper) == [
        "scripts/fetch_odds_multi.py",
        "scripts/odds_evaluator.py",
    ]


def test_s1_is_only_wrapper_allowed_to_continue_on_exit_code_one(repo_root: Path):
    report = certify_manifest_wrappers(repo_root)
    partial_steps = [step_id for step_id, item in report["wrappers"].items() if item["partial_exit_allowed"]]
    assert partial_steps == ["S1"]


def test_s8_cannot_be_certified_without_declared_gate_dependencies(repo_root: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "bet.pipeline.wrapper_runtime_certification.required_artifacts_before_step",
        lambda step_id: () if step_id == "S8" else (),
    )
    result = certify_wrapper("S8", repo_root / "scripts/pipeline_steps/s8_build_coupons.py", repo_root)
    assert result["evidence_contract"] == "BLOCKED_FOR_ORCHESTRATOR"
    assert result["verdict"] == "BLOCK"


def test_dry_run_default_uses_temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture_root = Path(__file__).parent / "fixtures" / "pipeline_wrappers"
    record_path = tmp_path / "capture.json"
    monkeypatch.setattr(_runner, "ROOT", fixture_root)
    monkeypatch.setenv("FIXTURE_RECORD_PATH", str(record_path))
    monkeypatch.delenv("FIXTURE_EXIT_CODE", raising=False)

    rc = _runner.run_scripts(["capture_env.py"], date="2026-06-25", dry_run=True, allow_write=False)

    assert rc == 0
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["argv"] == ["--date", "2026-06-25"]
    assert payload["dry_run"] == "1"
    assert payload["database_url"].startswith("sqlite:///")
    assert "bet_dryrun_" in payload["database_url"]


def test_allow_write_without_ack_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture_root = Path(__file__).parent / "fixtures" / "pipeline_wrappers"
    record_path = tmp_path / "capture.json"
    monkeypatch.setattr(_runner, "ROOT", fixture_root)
    monkeypatch.setenv("FIXTURE_RECORD_PATH", str(record_path))
    monkeypatch.delenv("BET_PIPELINE_WRITE_ACK", raising=False)
    monkeypatch.delenv("FORCE_ALLOW_WRITE", raising=False)

    rc = _runner.run_scripts(["capture_env.py"], dry_run=True, allow_write=True)

    assert rc == 3
    assert not record_path.exists()


def test_force_allow_write_alone_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture_root = Path(__file__).parent / "fixtures" / "pipeline_wrappers"
    record_path = tmp_path / "capture.json"
    monkeypatch.setattr(_runner, "ROOT", fixture_root)
    monkeypatch.setenv("FIXTURE_RECORD_PATH", str(record_path))
    monkeypatch.setenv("FORCE_ALLOW_WRITE", "1")
    monkeypatch.delenv("BET_PIPELINE_WRITE_ACK", raising=False)

    rc = _runner.run_scripts(["capture_env.py"], dry_run=True, allow_write=False)

    assert rc == 4
    assert not record_path.exists()


def test_non_zero_exit_codes_propagate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture_root = Path(__file__).parent / "fixtures" / "pipeline_wrappers"
    record_path = tmp_path / "capture.json"
    monkeypatch.setattr(_runner, "ROOT", fixture_root)
    monkeypatch.setenv("FIXTURE_RECORD_PATH", str(record_path))
    monkeypatch.setenv("FIXTURE_EXIT_CODE", "5")

    rc = _runner.run_scripts(["capture_env.py"], dry_run=True, allow_write=False)

    assert rc == 5
    assert record_path.exists()


def test_no_wrapper_writes_to_betting_data_or_coupons_during_certification_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture_root = Path(__file__).parent / "fixtures" / "pipeline_wrappers"
    record_path = tmp_path / "capture.json"
    (fixture_root / "betting" / "data").mkdir(parents=True, exist_ok=True)
    (fixture_root / "betting" / "coupons").mkdir(parents=True, exist_ok=True)
    before_data = sorted((fixture_root / "betting" / "data").rglob("*"))
    before_coupons = sorted((fixture_root / "betting" / "coupons").rglob("*"))

    monkeypatch.setattr(_runner, "ROOT", fixture_root)
    monkeypatch.setenv("FIXTURE_RECORD_PATH", str(record_path))
    monkeypatch.delenv("FIXTURE_EXIT_CODE", raising=False)
    rc = _runner.run_scripts(["capture_env.py"], date="2026-06-25", dry_run=True, allow_write=False)

    after_data = sorted((fixture_root / "betting" / "data").rglob("*"))
    after_coupons = sorted((fixture_root / "betting" / "coupons").rglob("*"))
    assert rc == 0
    assert before_data == after_data
    assert before_coupons == after_coupons


def test_certification_output_is_json_serializable(repo_root: Path):
    report = certify_manifest_wrappers(repo_root)
    assert json.loads(json.dumps(report))["verdict"] in {"PASS", "BLOCK"}


def test_classify_wrapper_runtime_status_warns_on_missing_evidence():
    assert classify_wrapper_runtime_status(
        targets=["scripts/example.py"],
        wrapper_compiles=True,
        targets_exist=True,
        targets_compile=True,
        dry_run_default=True,
        write_safe=True,
        date_cli_compatible=True,
        partial_exit_allowed=False,
        evidence_contract="MISSING",
        live_only=False,
        step_id="S3",
    ) == "WARN"


def test_discovery_without_run_scripts_returns_empty_and_blocks(tmp_path: Path):
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(
        "def main():\n"
        "    return 0\n",
        encoding="utf-8",
    )
    assert discover_wrapper_targets(wrapper) == []
