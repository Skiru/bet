from pathlib import Path

from scripts.audit_orchestrated_session_continuation import REQUIRED_SNIPPETS, validate_resume_prompt


WORKSPACE_ROOT = Path("/Users/mkoziol/projects/bet")


def test_contract_doc_exists_and_mentions_inheritance_policy():
    path = WORKSPACE_ROOT / "docs/pipeline/Unified Orchestrated Analyst Session Contract.md"
    content = path.read_text(encoding="utf-8")
    assert "The active Kilo UI runtime model is the source of truth" in content
    assert "must inherit the active parent/orchestrator model" in content


def test_continuation_doc_exists_and_mentions_j2_only_resume():
    path = WORKSPACE_ROOT / "docs/pipeline/Orchestrated Session Continuation Protocol.md"
    content = path.read_text(encoding="utf-8")
    assert "do not repeat model repair" in content
    assert "run J2 only" in content


def test_resume_prompt_validator_accepts_required_snippets(tmp_path):
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("\n".join(REQUIRED_SNIPPETS), encoding="utf-8")
    assert validate_resume_prompt(resume_path) == []
