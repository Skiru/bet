"""Tests for evidence-derived pipeline certification."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.certify_pipeline_final_closure import (
    CertificationError,
    parse_junit,
    source_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "certify_pipeline_final_closure.py"


def test_certifier_child_fixture() -> None:
    """A bounded real pytest node used by the outer certifier test."""
    assert True


def test_certifier_runs_real_pytest_and_binds_current_source(tmp_path: Path) -> None:
    if os.environ.get("BET_PIPELINE_CERTIFIER_ACTIVE") == "1":
        return
    output = tmp_path / "certificate.json"
    junit = tmp_path / "results.xml"
    node = "tests/test_pipeline_certifier.py::test_certifier_child_fixture"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(ROOT),
            "--pytest-node",
            node,
            "--output",
            str(output),
            "--junit",
            str(junit),
            "--timeout-seconds",
            "60",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    certificate = json.loads(output.read_text(encoding="utf-8"))
    _, expected_tree = source_manifest(ROOT)
    assert certificate["status"] == "PASS"
    assert certificate["source"]["source_tree_sha256"] == expected_tree
    assert certificate["test_run"]["nodes"] == [node]
    assert certificate["test_run"]["tests"] == 1
    assert certificate["claims"]["live_pipeline_executed"] is False
    assert parse_junit(junit)["failures"] == 0


def test_certifier_does_not_publish_when_pytest_cannot_collect(tmp_path: Path) -> None:
    output = tmp_path / "must-not-exist.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(ROOT),
            "--pytest-node",
            "tests/test_pipeline_certifier.py::missing_test_node",
            "--output",
            str(output),
            "--junit",
            str(tmp_path / "failure.xml"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 1
    assert "CERT_ZERO_TESTS_EXECUTED" in result.stderr
    assert not output.exists()


def test_certifier_rejects_a_preexisting_certificate(tmp_path: Path) -> None:
    output = tmp_path / "existing.json"
    output.write_text("do not overwrite", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(ROOT),
            "--pytest-node",
            "tests/test_pipeline_certifier.py::test_certifier_child_fixture",
            "--output",
            str(output),
            "--junit",
            str(tmp_path / "unused.xml"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 1
    assert "CERT_OUTPUT_ALREADY_EXISTS" in result.stderr
    assert output.read_text(encoding="utf-8") == "do not overwrite"


def test_junit_parser_rejects_zero_tests(tmp_path: Path) -> None:
    junit = tmp_path / "empty.xml"
    junit.write_text('<testsuite tests="0" failures="0" errors="0"/>', encoding="utf-8")
    with pytest.raises(CertificationError, match="CERT_ZERO_TESTS_EXECUTED"):
        parse_junit(junit)


def test_certifier_contains_no_snapshot_specific_branch_or_sha() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "fix/s5-s6-s7-canonical-continuity-final-v1" not in source
    assert "f925aef8" not in source
    assert "28422d9c" not in source
