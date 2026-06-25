"""Tests for pipeline wrapper compilation and validation contracts."""
from __future__ import annotations

from pathlib import Path
import pytest

from bet.pipeline.manifest import discover_repo_root
from bet.pipeline.wrapper_contracts import (
    validate_wrapper_contracts,
    manifest_script_wrappers,
    assert_manifest_wrappers_exist,
    compile_python_file,
)
from bet.pipeline.wrapper_runtime_certification import certify_manifest_wrappers
from bet.pipeline.readiness_contracts import PipelineReadinessStatus


def test_manifest_wrappers_exist_and_compile():
    """Verify that all wrappers mentioned in the manifest exist and compile."""
    root = discover_repo_root()
    errors = assert_manifest_wrappers_exist(root)
    assert not errors, f"Missing wrappers: {errors}"

    wrappers = manifest_script_wrappers(root)
    for step_id, path in wrappers.items():
        success, msg = compile_python_file(path)
        assert success, f"Wrapper for {step_id} failed to compile: {msg}"


def test_validate_wrapper_contracts_passes_on_repo_root():
    """Verify validate_wrapper_contracts returns PASS for current repo root."""
    root = discover_repo_root()
    decision = validate_wrapper_contracts(root)
    assert decision.verdict == PipelineReadinessStatus.PASS
    assert not decision.failed_requirements
    assert decision.metrics["manifest_wrappers_checked"] > 0
    assert decision.metrics["compilation_success"] is True


def test_wrapper_compilation_catches_syntax_error(tmp_path):
    """Verify compile_python_file correctly reports syntax errors."""
    bad_file = tmp_path / "bad_syntax.py"
    bad_file.write_text("class Unclosed:\n    def missing_body(self):", encoding="utf-8")
    success, msg = compile_python_file(bad_file)
    assert success is False
    assert "syntax" in msg.lower() or "unexpected EOF" in msg.lower() or "indentation" in msg.lower() or "token" in msg.lower() or "py_compile" in msg.lower()


def test_certification_targets_compile_even_if_runtime_verdict_blocks():
    """Verify runtime certification still proves wrapper/target compilation deterministically."""
    root = discover_repo_root()
    report = certify_manifest_wrappers(root)
    for step_id, wrapper_result in report["wrappers"].items():
        assert wrapper_result["wrapper_compiles"] is True, step_id
        assert wrapper_result["targets_exist"] is True, step_id
        assert wrapper_result["targets_compile"] is True, step_id
