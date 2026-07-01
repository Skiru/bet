from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path("/Users/mkoziol/projects/bet")
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "audit_orchestrated_session_continuation.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_orchestrated_session_continuation", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _results():
    module = _load_audit_module()
    return module.run_audit(write_reports=False)


def test_review_only_cannot_return_final_pass():
    results = _results()
    assert results["false_pass_after_review_only_forbidden"] is True


def test_continuation_required_when_phases_pending():
    results = _results()
    assert results["resume_prompt_required_when_phases_pending"] is True


def test_final_pass_requires_all_required_subagents():
    results = _results()
    assert results["full_session_pass_requires_all_subagent_artifacts"] is True


def test_final_pass_requires_omission_ledger():
    results = _results()
    assert results["full_session_pass_requires_all_subagent_artifacts"] is True


def test_resume_prompt_required_for_continuation():
    results = _results()
    assert results["resume_prompt_required_when_phases_pending"] is True


def test_phase_budget_contract_present():
    results = _results()
    assert results["phase_budgets_documented"] is True


def test_orchestrator_prompt_mentions_max_steps_guard():
    results = _results()
    assert results["orchestrator_prompt_mentions_max_steps_guard"] is True
