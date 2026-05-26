"""Focused customization checks for the orchestrator Brave async-wait policy.

This module is intentionally scoped to the touched artifacts for this feature.
Known repo-wide model-literal drift outside this slice is excluded from the
acceptance gate on purpose.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RESOURCE = ROOT / ".github/skills/bet-orchestrating-workflows/resources/async-wait-overlap.md"
SKILL = ROOT / ".github/skills/bet-orchestrating-workflows/SKILL.md"
PROMPT = ROOT / ".github/prompts/orchestrate-betting-day.prompt.md"
ORCHESTRATOR_AGENT = ROOT / ".github/agents/bet-orchestrator.agent.md"
SHARED_BASELINES = [
    ROOT / ".github/skills/bet-orchestrating-workflows/resources/execution-spine.md",
    ROOT / ".github/skills/bet-orchestrating-workflows/resources/resume-stop-gates.md",
    ROOT / ".github/skills/bet-orchestrating-workflows/resources/handoff-contracts.md",
]
SECOND_OWNER_MARKERS = [
    "max two Brave research packs per async wait window",
    "top three unresolved candidates",
    "One pack = up to three Brave queries (`web`, `news`, `llm-context`)",
    "## Allowed Overlap Work",
    "## Prohibited Overlap Work",
    "## Async Wait Addendum",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_canonical_resource_exists_and_is_referenced_by_skill_and_prompt():
    assert RESOURCE.exists(), "Missing canonical async-wait overlap resource"

    skill_text = _read(SKILL)
    prompt_text = _read(PROMPT)

    assert "[async-wait-overlap.md](resources/async-wait-overlap.md)" in skill_text
    assert "bet-orchestrating-workflows/resources/async-wait-overlap.md" in prompt_text


def test_touched_workflow_references_resolve_correctly():
    resource_text = _read(RESOURCE)

    assert (SKILL.parent / "resources/async-wait-overlap.md").exists()
    assert (RESOURCE.parent / "../../../instructions/agent-execution-protocol.instructions.md").resolve().exists()
    assert (RESOURCE.parent / "../../bet-navigating-sources/SKILL.md").resolve().exists()
    assert (RESOURCE.parent / "handoff-contracts.md").resolve().exists()
    assert (RESOURCE.parent / "resume-stop-gates.md").resolve().exists()

    assert "[agent-execution-protocol.instructions.md](../../../instructions/agent-execution-protocol.instructions.md)" in resource_text
    assert "[bet-navigating-sources](../../bet-navigating-sources/SKILL.md)" in resource_text
    assert "[handoff-contracts.md](handoff-contracts.md)" in resource_text
    assert "[resume-stop-gates.md](resume-stop-gates.md)" in resource_text


def test_canonical_resource_defines_explicit_trigger_scope_and_budget():
    text = _read(RESOURCE)

    assert "`>120s`" in text
    assert "Mandatory whenever the orchestrator launches a step in async mode" in text
    assert "Optional for shorter manually async waits" in text
    # Full guardrail for the optional short-async path
    assert "known context gap already exists" in text
    assert "single-pass overlap can shorten the downstream specialist path" in text
    assert "active-stage frontier" in text
    assert "explicit-gap-first ordering" in text
    assert "top three unresolved candidates or one stage-level topic" in text
    assert "Never widen to the full scan universe" in text
    assert "Max two Brave research packs per async wait window" in text
    assert "One pack = up to three Brave queries (`web`, `news`, `llm-context`)" in text
    assert "If the budget is exhausted" in text


def test_canonical_resource_lists_allowed_and_prohibited_overlap_cases():
    text = _read(RESOURCE)

    assert "## Allowed Overlap Work" in text
    assert "Brave web/news/llm-context research packs on the active-stage frontier." in text
    assert "Read-only DB inspection, artifact reads, and source-policy loads needed to sharpen the same frontier." in text
    assert "Drafting a checkpoint note or optional Async Wait Addendum for the next specialist handoff." in text

    assert "## Prohibited Overlap Work" in text
    assert "Launching the next pipeline step or any dependent script before the current async step finishes." in text
    assert "Delegating specialist analysis before finished output exists." in text
    assert "Starting concurrent DB-writing pipeline work or other shared-state mutation." in text
    assert "Parallel Playwright-heavy browsing, tipster scraping, or other browser-led work in the same wait window." in text


def test_async_wait_addendum_stays_supplemental_to_finished_output_analysis():
    text = _read(RESOURCE)

    assert "## Async Wait Addendum" in text
    assert "Use this optional addendum only when wait-window research produces evidence" in text
    assert "Append it by reference to the generic payload from [handoff-contracts.md](handoff-contracts.md)" in text
    assert "Specialist verdicts on finished outputs remain authoritative." in text
    assert "never replaces the finished-output-first delegation rule" in text


def test_skill_and_prompt_stay_thin_and_keep_shared_baselines_generic():
    skill_text = _read(SKILL)
    prompt_text = _read(PROMPT)

    assert "opt-in add-on" in skill_text
    assert "remain generic baselines rather than secondary policy owners" in skill_text

    for text in (skill_text, prompt_text):
        for marker in SECOND_OWNER_MARKERS:
            assert marker not in text


def test_shared_baselines_and_agent_do_not_become_second_policy_owners():
    for path in SHARED_BASELINES + [ORCHESTRATOR_AGENT]:
        text = _read(path)
        for marker in SECOND_OWNER_MARKERS:
            assert marker not in text, f"{path.relative_to(ROOT)} should not own async-wait policy details"


def test_touched_prompt_frontmatter_integrity():
    """Verify the daily orchestrator prompt preserves required frontmatter fields."""
    text = _read(PROMPT)
    assert "agent: bet-orchestrator" in text
    assert 'name: orchestrate-betting-day' in text
    assert "bet-orchestrating-workflows" in text