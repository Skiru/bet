"""Pipeline wrapper contract verification."""
from __future__ import annotations

import py_compile
from pathlib import Path
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.readiness_contracts import GateDecision, PipelineReadinessStatus


def manifest_script_wrappers(repo_root: Path) -> dict[str, Path]:
    """Load the manifest and return only execution_mode=script wrappers."""
    repo_root = Path(repo_root)
    manifest = load_pipeline_manifest(repo_root / "config/pipeline_manifest.json")
    wrappers = {}
    for step in manifest.steps:
        if step.execution_mode == "script":
            if step.id and step.wrapper:
                wrappers[step.id] = repo_root / step.wrapper
    return wrappers


def assert_manifest_wrappers_exist(repo_root: Path) -> list[str]:
    """Check if all script wrappers in the manifest exist on disk."""
    errors = []
    wrappers = manifest_script_wrappers(repo_root)
    for step_id, path in wrappers.items():
        if not path.exists():
            errors.append(f"Wrapper for {step_id} does not exist: {path}")
    return errors


def compile_python_file(path: Path) -> tuple[bool, str]:
    """Attempt to compile a Python file. Returns (success, error_message)."""
    path = Path(path)
    try:
        py_compile.compile(str(path), doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Unexpected compilation error: {e}"


def validate_wrapper_contracts(repo_root: Path) -> GateDecision:
    """Validate all wrapper contracts (existence, compilation, paths, contents, safety)."""
    repo_root = Path(repo_root)
    failed_requirements = []
    warnings = []
    checked_count = 0

    # 1. Existence and compilation of script wrappers
    wrappers = manifest_script_wrappers(repo_root)
    for step_id, path in wrappers.items():
        checked_count += 1
        if not path.exists():
            failed_requirements.append(f"Wrapper for {step_id} does not exist: {path}")
            continue

        compiled, err_msg = compile_python_file(path)
        if not compiled:
            failed_requirements.append(f"Wrapper for {step_id} failed to compile: {err_msg}")

    # 2. Path assertions for S7b and S7
    manifest = load_pipeline_manifest(repo_root / "config/pipeline_manifest.json")
    s7b_wrapper = None
    s7_wrapper = None
    s4_wrapper = None

    for step in manifest.steps:
        if step.id == "S7b":
            s7b_wrapper = step.wrapper
        elif step.id == "S7":
            s7_wrapper = step.wrapper
        elif step.id == "S4":
            s4_wrapper = step.wrapper

    if s7b_wrapper != "scripts/pipeline_steps/s7_validate.py":
        failed_requirements.append(
            f"S7b wrapper path must be 'scripts/pipeline_steps/s7_validate.py', got '{s7b_wrapper}'"
        )
    if s7_wrapper != "scripts/pipeline_steps/s5_gate.py":
        failed_requirements.append(
            f"S7 wrapper path must be 'scripts/pipeline_steps/s5_gate.py', got '{s7_wrapper}'"
        )

    # 3. S4 content assertion: fetch_odds_multi.py before odds_evaluator.py
    if s4_wrapper:
        s4_path = repo_root / s4_wrapper
        if s4_path.exists():
            try:
                s4_text = s4_path.read_text(encoding="utf-8")
                if "fetch_odds_multi.py" not in s4_text:
                    failed_requirements.append("S4 wrapper is missing reference to 'fetch_odds_multi.py'")
                if "odds_evaluator.py" not in s4_text:
                    failed_requirements.append("S4 wrapper is missing reference to 'odds_evaluator.py'")
                if "fetch_odds_multi.py" in s4_text and "odds_evaluator.py" in s4_text:
                    idx_fetch = s4_text.index("fetch_odds_multi.py")
                    idx_eval = s4_text.index("odds_evaluator.py")
                    if idx_fetch >= idx_eval:
                        failed_requirements.append(
                            "S4 wrapper must run 'fetch_odds_multi.py' before 'odds_evaluator.py'"
                        )
            except Exception as e:
                failed_requirements.append(f"Failed to read S4 wrapper content: {e}")
        else:
            failed_requirements.append(f"S4 wrapper does not exist at '{s4_path}'")

    # 4. _runner.py safety checks
    runner_path = repo_root / "scripts/pipeline_steps/_runner.py"
    if runner_path.exists():
        checked_count += 1
        compiled, err_msg = compile_python_file(runner_path)
        if not compiled:
            failed_requirements.append(f"_runner.py failed to compile: {err_msg}")

        try:
            runner_text = runner_path.read_text(encoding="utf-8")
            # If FORCE_ALLOW_WRITE can independently set allow_write=True and dry_run=False without checking acknowledgement
            if (
                "force_allow" in runner_text
                and "allow_write = True" in runner_text
                and "dry_run = False" in runner_text
            ):
                if "BLOCKED_FORCE_ALLOW_WRITE_UNSAFE" not in runner_text:
                    failed_requirements.append(
                        "_runner.py contains unsafe, unconditional env-only FORCE_ALLOW_WRITE write enablement"
                    )
        except Exception as e:
            failed_requirements.append(f"Failed to read _runner.py content: {e}")
    else:
        failed_requirements.append(f"_runner.py does not exist at '{runner_path}'")

    verdict = PipelineReadinessStatus.PASS
    if failed_requirements:
        verdict = PipelineReadinessStatus.BLOCK

    metrics = {
        "manifest_wrappers_checked": checked_count,
        "compilation_success": len(failed_requirements) == 0,
    }

    return GateDecision(
        gate_id="gate_wrapper_contracts",
        target_step_id="ALL",
        verdict=verdict,
        failed_requirements=tuple(failed_requirements),
        warnings=tuple(warnings),
        required_artifacts=(),
        accepted_artifacts=(),
        blocked_artifacts=(),
        metrics=metrics,
    )
