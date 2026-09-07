import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "betting-pipeline-contract",
    "betting-evidence-contract",
    "betting-pipeline-runtime",
    "context-safe-agentics",
)
LEGACY = re.compile(
    r"bet-(?:orchestrator|engineer|scanner|scout|enricher|statistician|valuator|"
    r"challenger|test-engineer|db-analyst|reconciler|settler(?!-postevent))"
)


def load_skill(name: str) -> tuple[dict, str]:
    raw = (ROOT / ".kilo/skills" / name / "SKILL.md").read_bytes()
    assert raw.startswith(b"---\n")
    assert b"\n---\n" in raw
    header, body = raw[4:].split(b"\n---\n", 1)
    return yaml.safe_load(header), body.decode("utf-8")


def test_all_four_skills_have_standard_frontmatter():
    for name in SKILLS:
        frontmatter, _ = load_skill(name)
        assert frontmatter["name"] == name
        assert frontmatter["description"]
        assert "model" not in frontmatter
        assert "permission" not in frontmatter


def test_skills_use_only_current_power_agent_contracts():
    for name in SKILLS:
        _, body = load_skill(name)
        assert LEGACY.search(body) is None, f"{name} contains a deleted agent"


def test_runtime_skills_define_safe_continuation():
    for name in ("betting-pipeline-runtime", "context-safe-agentics"):
        _, body = load_skill(name)
        lowered = body.lower()
        assert "safe checkpoint" in lowered
        assert "safe_continuation_required" in lowered
        assert "never claims pass" in lowered
        assert "exact continuation prompt" in lowered


def test_pipeline_and_evidence_semantics():
    _, pipeline = load_skill("betting-pipeline-contract")
    _, evidence = load_skill("betting-evidence-contract")
    assert "S9 requires a real human-entered Superbet quote" in pipeline
    assert "Every discovered event must receive an explicit terminal status or reason" in pipeline
    assert "Tipster absence" in pipeline
    assert "EV, bettable status, Kelly sizing, and stake recommendations require real human-entered operator odds" in evidence
