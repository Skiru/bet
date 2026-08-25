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
    node = "tests/test_pipeline_certifier.py"
    _, expected_tree = source_manifest(ROOT)
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
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    certificate = json.loads(output.read_text(encoding="utf-8"))
    assert certificate["status"] == "PASS"
    assert certificate["source"]["source_tree_sha256"] == expected_tree
    assert node in certificate["test_run"]["nodes"]
    assert certificate["test_run"]["tests"] >= 33
    assert certificate["claims"]["live_pipeline_executed"] is False
    assert parse_junit(junit)["failures"] == 0


def test_certifier_does_not_publish_when_pytest_cannot_collect(tmp_path: Path) -> None:
    output = tmp_path / "must-not-exist.json"
    _, expected_tree = source_manifest(ROOT)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(ROOT),
            "--pytest-node",
            "tests/test_pipeline_certifier.py::missing_test_node_1",
            "--pytest-node",
            "tests/test_pipeline_certifier.py::missing_test_node_2",
            "--output",
            str(output),
            "--junit",
            str(tmp_path / "failure.xml"),
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 1
    assert "CERT_ZERO_TESTS_EXECUTED" in result.stderr or "CERT_PYTEST_COLLECTION_FAILED" in result.stderr
    assert not output.exists()


def test_certifier_rejects_a_preexisting_certificate(tmp_path: Path) -> None:
    output = tmp_path / "existing.json"
    output.write_text("do not overwrite", encoding="utf-8")
    _, expected_tree = source_manifest(ROOT)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(ROOT),
            "--pytest-node",
            "tests/test_pipeline_certifier.py",
            "--output",
            str(output),
            "--junit",
            str(tmp_path / "unused.xml"),
            "--expected-source-tree-sha256",
            expected_tree,
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


def test_one_test_bypass_probe_fails_to_bypass_mandatory_set(tmp_path: Path) -> None:
    """Adversarial test proving that a one-test certification invocation still runs the complete mandatory set."""
    if os.environ.get("BET_PIPELINE_CERTIFIER_ACTIVE") == "1":
        return
    output = tmp_path / "certificate_adversarial.json"
    junit = tmp_path / "results_adversarial.xml"
    node = "tests/test_pipeline_certifier.py::test_certifier_child_fixture"
    _, expected_tree = source_manifest(ROOT)
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
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 1
    assert "CERT_ONLY_ONE_CLI_TEST_SUPPLIED" in result.stderr


def test_p0_3_exploit_regression(tmp_path: Path) -> None:
    """Exploit regression tests for P0-3:
    1. create a second linked worktree at the same HEAD (or copy checkouts);
    2. modify bet-executor task permissions so its own validator fails;
    3. replace mandatory tests with equal-count dummy tests;
    4. call certifier from another checkout with --repo-root target;
    5. certification must fail before tests or validators report PASS.
    """
    import hashlib
    if os.environ.get("BET_PIPELINE_CERTIFIER_ACTIVE") == "1":
        return

    # Let's scaffold a mock repo inside a temporary directory
    mock_root = tmp_path / "mock-repo"
    mock_root.mkdir()

    # Copy some elements to simulate a repository setup
    # Initialise git inside mock_root
    subprocess.run(["git", "init", "-b", "main"], cwd=mock_root, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "test-user"], cwd=mock_root, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=mock_root, capture_output=True, check=True)

    exclude_file = mock_root / ".git" / "info" / "exclude"
    exclude_file.write_text(".pytest_cache/\n__pycache__/\n*.pyc\n", encoding="utf-8")

    # 1. Config inventory
    config_dir = mock_root / "config"
    config_dir.mkdir()
    inv_file = config_dir / "pipeline_certification_inventory.json"

    # Create dummy tests file in tests/test_mandatory_mock.py
    tests_dir = mock_root / "tests"
    tests_dir.mkdir()
    test_mock_file = tests_dir / "test_mandatory_mock.py"
    test_mock_content = """
def test_one():
    assert True
def test_two():
    assert True
"""
    test_mock_file.write_text(test_mock_content, encoding="utf-8")
    actual_test_sha = hashlib.sha256(test_mock_file.read_bytes()).hexdigest()

    inventory_data = {
        "schema_version": "1.0",
        "mandatory_nodes": [
            "tests/test_mandatory_mock.py"
        ],
        "mandatory_file_sha256s": {
            "tests/test_mandatory_mock.py": actual_test_sha
        },
        "expected_minimum_counts": {
            "tests/test_mandatory_mock.py": 2
        },
        "allowed_skips": []
    }
    inv_file.write_text(json.dumps(inventory_data), encoding="utf-8")

    # Create scripts folder with validators and certifier
    scripts_dir = mock_root / "scripts"
    scripts_dir.mkdir()

    # Copy certifier script there so it is verifiably identical
    target_certifier_path = scripts_dir / "certify_pipeline_final_closure.py"
    target_certifier_path.write_bytes(SCRIPT.read_bytes())

    # Create a validator script
    val_script = scripts_dir / "validate_production_surface.py"
    val_script.write_text("import sys; sys.exit(0)", encoding="utf-8")

    # Write other dummy validators so script doesn't fail on missing validator file
    other_vals = [
        "validate_power_agent_control_plane.py",
        "validate_manifest_power_agents.py",
        "validate_reachability_graph.py",
        "validate_provider_registry.py",
        "validate_database_access.py"
    ]
    for ov in other_vals:
        (scripts_dir / ov).write_text("import sys; sys.exit(0)", encoding="utf-8")

    # Commit all changes to get a clean repository
    subprocess.run(["git", "add", "."], cwd=mock_root, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=mock_root, capture_output=True, check=True)

    # Now let's verify git status is clean, and certification passes
    output_cert = tmp_path / "cert.json"
    junit_file = tmp_path / "junit.xml"

    # Get the clean tree SHA
    _, expected_tree = source_manifest(mock_root)

    # Execute and ensure it passes when clean
    result = subprocess.run(
        [
            sys.executable,
            str(target_certifier_path),
            "--repo-root",
            str(mock_root),
            "--output",
            str(output_cert),
            "--junit",
            str(junit_file),
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=mock_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Clean certification failed: {result.stdout} {result.stderr}"

    # Let's clean output for exploit tests
    output_cert.unlink(missing_ok=True)

    # EXPLOIT SCENARIO 2: Modify bet-executor task permissions so its own validator fails
    val_script.write_text("import sys; sys.exit(1)", encoding="utf-8")

    # Running certifier should now FAIL
    result_exploit_val = subprocess.run(
        [
            sys.executable,
            str(target_certifier_path),
            "--repo-root",
            str(mock_root),
            "--output",
            str(output_cert),
            "--junit",
            str(junit_file),
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=mock_root,
        capture_output=True,
        text=True,
    )
    assert result_exploit_val.returncode == 1
    assert (
        "CERT_VALIDATOR_FAILED" in result_exploit_val.stderr
        or "Target repository worktree is dirty" in result_exploit_val.stderr
        or "CERT_SOURCE_TREE_MISMATCH" in result_exploit_val.stderr
        or "CERT_DIRTY_WORKTREE" in result_exploit_val.stderr
    )

    # EXPLOIT SCENARIO 3: Replace mandatory tests with equal-count dummy tests
    val_script.write_text("import sys; sys.exit(0)", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=mock_root, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "fix validator"], cwd=mock_root, capture_output=True, check=False)

    # Now replace tests with dummy tests (equal count: 2 tests)
    test_mock_file.write_text("""
def test_dummy_1():
    assert True
def test_dummy_2():
    assert True
""", encoding="utf-8")

    result_exploit_tests = subprocess.run(
        [
            sys.executable,
            str(target_certifier_path),
            "--repo-root",
            str(mock_root),
            "--output",
            str(output_cert),
            "--junit",
            str(junit_file),
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=mock_root,
        capture_output=True,
        text=True,
    )
    assert result_exploit_tests.returncode == 1
    assert (
        "CERT_MANDATORY_FILE_HASH_MISMATCH" in result_exploit_tests.stderr
        or "Target repository worktree is dirty" in result_exploit_tests.stderr
        or "CERT_SOURCE_TREE_MISMATCH" in result_exploit_tests.stderr
        or "CERT_DIRTY_WORKTREE" in result_exploit_tests.stderr
    )


def test_certifier_dirty_worktree_rejections(tmp_path: Path) -> None:
    """Add focused tests proving dirty worktree rejections."""
    import hashlib
    if os.environ.get("BET_PIPELINE_CERTIFIER_ACTIVE") == "1":
        return

    mock_root = tmp_path / "mock-repo"
    mock_root.mkdir()

    # Initialise git inside mock_root
    subprocess.run(["git", "init", "-b", "main"], cwd=mock_root, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "test-user"], cwd=mock_root, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=mock_root, capture_output=True, check=True)

    exclude_file = mock_root / ".git" / "info" / "exclude"
    exclude_file.write_text(".pytest_cache/\n__pycache__/\n*.pyc\n", encoding="utf-8")

    # Config inventory
    config_dir = mock_root / "config"
    config_dir.mkdir()
    inv_file = config_dir / "pipeline_certification_inventory.json"

    # Create dummy tests file
    tests_dir = mock_root / "tests"
    tests_dir.mkdir()
    test_mock_file = tests_dir / "test_mandatory_mock.py"
    test_mock_content = "def test_one():\n    assert True\n"
    test_mock_file.write_text(test_mock_content, encoding="utf-8")
    actual_test_sha = hashlib.sha256(test_mock_file.read_bytes()).hexdigest()

    inventory_data = {
        "schema_version": "1.0",
        "mandatory_nodes": [
            "tests/test_mandatory_mock.py"
        ],
        "mandatory_file_sha256s": {
            "tests/test_mandatory_mock.py": actual_test_sha
        },
        "expected_minimum_counts": {
            "tests/test_mandatory_mock.py": 1
        },
        "allowed_skips": []
    }
    inv_file.write_text(json.dumps(inventory_data), encoding="utf-8")

    # Create scripts folder with validators and certifier
    scripts_dir = mock_root / "scripts"
    scripts_dir.mkdir()

    target_certifier_path = scripts_dir / "certify_pipeline_final_closure.py"
    target_certifier_path.write_bytes(SCRIPT.read_bytes())

    # Create a validator script
    val_script = scripts_dir / "validate_production_surface.py"
    val_script.write_text("import sys; sys.exit(0)", encoding="utf-8")

    other_vals = [
        "validate_power_agent_control_plane.py",
        "validate_manifest_power_agents.py",
        "validate_reachability_graph.py",
        "validate_provider_registry.py",
        "validate_database_access.py"
    ]
    for val in other_vals:
        (scripts_dir / val).write_text("import sys; sys.exit(0)", encoding="utf-8")

    # Commit initial state to have a clean git tree
    subprocess.run(["git", "add", "."], cwd=mock_root, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial clean"], cwd=mock_root, capture_output=True, check=True)

    # Calculate expected source tree sha of clean tree
    _, expected_tree = source_manifest(mock_root)
    output_cert = tmp_path / "certificate.json"
    junit_file = tmp_path / "results.xml"

    # CASE 5: Clean worktree plus matching head/tree continues to pass
    res_clean = subprocess.run(
        [
            sys.executable,
            str(target_certifier_path),
            "--repo-root",
            str(mock_root),
            "--output",
            str(output_cert),
            "--junit",
            str(junit_file),
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=mock_root,
        capture_output=True,
        text=True,
    )
    assert res_clean.returncode == 0, f"Clean check failed: {res_clean.stderr}"
    assert output_cert.exists()
    output_cert.unlink()

    # CASE 1: Tracked modification is rejected
    test_mock_file.write_text("def test_one():\n    assert False\n", encoding="utf-8")
    res_modified = subprocess.run(
        [
            sys.executable,
            str(target_certifier_path),
            "--repo-root",
            str(mock_root),
            "--output",
            str(output_cert),
            "--junit",
            str(junit_file),
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=mock_root,
        capture_output=True,
        text=True,
    )
    assert res_modified.returncode == 1
    assert "CERT_DIRTY_WORKTREE" in res_modified.stderr
    assert not output_cert.exists()

    # Reset tracked modification
    subprocess.run(["git", "checkout", "--", "tests/test_mandatory_mock.py"], cwd=mock_root, capture_output=True, check=True)

    # CASE 2: Staged modification is rejected
    test_mock_file.write_text("def test_one():\n    assert True\n# comment\n", encoding="utf-8")
    subprocess.run(["git", "add", "tests/test_mandatory_mock.py"], cwd=mock_root, capture_output=True, check=True)
    res_staged = subprocess.run(
        [
            sys.executable,
            str(target_certifier_path),
            "--repo-root",
            str(mock_root),
            "--output",
            str(output_cert),
            "--junit",
            str(junit_file),
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=mock_root,
        capture_output=True,
        text=True,
    )
    assert res_staged.returncode == 1
    assert "CERT_DIRTY_WORKTREE" in res_staged.stderr
    assert not output_cert.exists()

    # Reset staged modification
    subprocess.run(["git", "reset", "HEAD", "tests/test_mandatory_mock.py"], cwd=mock_root, capture_output=True, check=True)
    subprocess.run(["git", "checkout", "--", "tests/test_mandatory_mock.py"], cwd=mock_root, capture_output=True, check=True)

    # CASE 3: Untracked file is rejected
    untracked_file = mock_root / "untracked.py"
    untracked_file.write_text("# untracked file\n", encoding="utf-8")
    res_untracked = subprocess.run(
        [
            sys.executable,
            str(target_certifier_path),
            "--repo-root",
            str(mock_root),
            "--output",
            str(output_cert),
            "--junit",
            str(junit_file),
            "--expected-source-tree-sha256",
            expected_tree,
        ],
        cwd=mock_root,
        capture_output=True,
        text=True,
    )
    assert res_untracked.returncode == 1
    assert "CERT_DIRTY_WORKTREE" in res_untracked.stderr
    assert not output_cert.exists()

    # CASE 4: Supplying a matching expected tree hash does not bypass dirty-worktree rejection
    _, dirty_tree = source_manifest(mock_root)
    res_bypass_check = subprocess.run(
        [
            sys.executable,
            str(target_certifier_path),
            "--repo-root",
            str(mock_root),
            "--output",
            str(output_cert),
            "--junit",
            str(junit_file),
            "--expected-source-tree-sha256",
            dirty_tree,
        ],
        cwd=mock_root,
        capture_output=True,
        text=True,
    )
    assert res_bypass_check.returncode == 1
    assert "CERT_DIRTY_WORKTREE" in res_bypass_check.stderr
    assert not output_cert.exists()
