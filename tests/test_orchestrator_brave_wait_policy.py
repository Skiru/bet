"""Focused customization checks for the orchestrator Brave async-wait policy.

This module is intentionally scoped to the touched artifacts for this feature.
Known repo-wide model-literal drift outside this slice is excluded from the
acceptance gate on purpose.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WAIT_RESOURCE = ROOT / ".github/skills/bet-orchestrating-workflows/resources/async-wait-overlap.md"
STAGE_RESOURCE = ROOT / ".github/skills/bet-orchestrating-workflows/resources/stage-context-packs.md"
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
STAGE_PROMPT_BULLET = "the pre-handoff stage context pack for this stage when required by `stage-context-packs.md`"
ELIGIBLE_PROMPTS = [
    ROOT / ".github/internal-prompts/bet-enrich.prompt.md",
    ROOT / ".github/internal-prompts/bet-deep-stats.prompt.md",
    ROOT / ".github/internal-prompts/bet-odds-ev.prompt.md",
    ROOT / ".github/internal-prompts/bet-context-upset.prompt.md",
    ROOT / ".github/internal-prompts/bet-gate.prompt.md",
    ROOT / ".github/internal-prompts/bet-time-sensitive.prompt.md",
]
EXCLUDED_PROMPTS = [
    ROOT / ".github/internal-prompts/bet-tipsters.prompt.md",
    ROOT / ".github/internal-prompts/bet-portfolio.prompt.md",
    ROOT / ".github/internal-prompts/bet-validate.prompt.md",
]
STAGE_MATRIX_ROWS = [
    "| S2 tipsters | Excluded | No mandatory stage pack. |",
    "| S2.3 / S2.5 enrichment | Required when the finished output exposes material gaps, stale coverage, or blocked bridges. | Only the surfaced gaps or blocked-source questions. |",
    "| S3 deep stats | Required when the finished output flags anomalies, thin context, or advancement candidates. | Only the flagged candidates or one surfaced topic. |",
    "| S4 odds and EV | Required when drift, stale lines, or bookmaker divergence needs explanation. | Only the surfaced pricing conflicts. |",
    "| S5 / S6 context and upset | Required by default for flagged or advancing picks. | Only the advancing or flagged frontier. |",
    "| S7 gate | Required for borderline, escalated, or evidence-thin picks. | Only the unresolved final-judgment subset. |",
    "| S3B time-sensitive recheck | Required by default. | Only the late-breaking changes tied to the affected picks. |",
    "| S8 portfolio | Excluded | No mandatory stage pack. |",
    "| Final validation | Excluded | No mandatory stage pack. |",
]
STAGE_OWNER_MARKERS = [
    "Named trigger: `Finished Output Read`.",
    "Named consequence: `Handoff Incomplete`.",
    "Max one `Stage Context Pack` per eligible handoff.",
    "One pack may cover up to two frontier targets or one stage-level topic.",
    "Each target may use up to three Brave queries (`web`, `news`, `llm-context`) plus read-only local checks.",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_canonical_resources_exist_and_are_referenced_by_skill_and_prompt():
    assert WAIT_RESOURCE.exists(), "Missing canonical async-wait overlap resource"
    assert STAGE_RESOURCE.exists(), "Missing canonical stage-context-pack resource"

    skill_text = _read(SKILL)
    prompt_text = _read(PROMPT)

    assert "[async-wait-overlap.md](resources/async-wait-overlap.md)" in skill_text
    assert "[stage-context-packs.md](resources/stage-context-packs.md)" in skill_text
    assert "bet-orchestrating-workflows/resources/async-wait-overlap.md" in prompt_text
    assert "bet-orchestrating-workflows/resources/stage-context-packs.md" in prompt_text


def test_touched_workflow_references_resolve_correctly():
    wait_resource_text = _read(WAIT_RESOURCE)
    stage_resource_text = _read(STAGE_RESOURCE)

    assert (SKILL.parent / "resources/async-wait-overlap.md").exists()
    assert (SKILL.parent / "resources/stage-context-packs.md").exists()
    assert (WAIT_RESOURCE.parent / "../../../instructions/agent-execution-protocol.instructions.md").resolve().exists()
    assert (WAIT_RESOURCE.parent / "../../bet-navigating-sources/SKILL.md").resolve().exists()
    assert (WAIT_RESOURCE.parent / "handoff-contracts.md").resolve().exists()
    assert (WAIT_RESOURCE.parent / "resume-stop-gates.md").resolve().exists()
    assert (STAGE_RESOURCE.parent / "../../bet-navigating-sources/SKILL.md").resolve().exists()
    assert (STAGE_RESOURCE.parent / "async-wait-overlap.md").resolve().exists()
    assert (STAGE_RESOURCE.parent / "handoff-contracts.md").resolve().exists()

    assert "[agent-execution-protocol.instructions.md](../../../instructions/agent-execution-protocol.instructions.md)" in wait_resource_text
    assert "[bet-navigating-sources](../../bet-navigating-sources/SKILL.md)" in wait_resource_text
    assert "[handoff-contracts.md](handoff-contracts.md)" in wait_resource_text
    assert "[resume-stop-gates.md](resume-stop-gates.md)" in wait_resource_text

    assert "[async-wait-overlap.md](async-wait-overlap.md)" in stage_resource_text
    assert "[handoff-contracts.md](handoff-contracts.md)" in stage_resource_text
    assert "[bet-navigating-sources](../../bet-navigating-sources/SKILL.md)" in stage_resource_text


def test_canonical_resource_defines_explicit_trigger_scope_and_budget():
    text = _read(WAIT_RESOURCE)

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
    text = _read(WAIT_RESOURCE)

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
    text = _read(WAIT_RESOURCE)

    assert "## Async Wait Addendum" in text
    assert "Use this optional addendum only when wait-window research produces evidence" in text
    assert "Append it by reference to the generic payload from [handoff-contracts.md](handoff-contracts.md)" in text
    assert "Specialist verdicts on finished outputs remain authoritative." in text
    assert "never replaces the finished-output-first delegation rule" in text


def test_stage_context_resource_defines_owner_trigger_matrix_and_pack_shape():
    text = _read(STAGE_RESOURCE)

    assert "This file owns mandatory post-output, pre-handoff `Stage Context Pack` policy for eligible stages." in text
    assert "This file does not own in-flight wait behavior, generic handoff payloads, or source-selection rules." in text
    assert "Mandatory after the orchestrator reads finished output for an eligible stage and before it delegates to the next specialist." in text
    assert "If the required pack is missing, the handoff is incomplete." in text
    assert "A `Stage Context Pack` is a bounded artifact, not an open-ended research activity." in text
    assert "The pack may be assembled from evidence gathered during async waits or after script completion." in text
    assert "The pack requirement is independent from the wait-window policy" in text

    for row in STAGE_MATRIX_ROWS:
        assert row in text

    for marker in STAGE_OWNER_MARKERS:
        assert marker in text

    assert "### Stage Context Pack (when required)" in text
    assert "findings for specialist verification: <supplemental evidence, not final truth>" in text
    assert "The pack never authorizes early delegation, dependent script execution, or shared-state mutation." in text


def test_eligible_and_excluded_prompts_respect_stage_context_pack_boundary():
    for path in ELIGIBLE_PROMPTS:
        assert STAGE_PROMPT_BULLET in _read(path), f"{path.relative_to(ROOT)} should require the stage context pack"

    for path in EXCLUDED_PROMPTS:
        assert STAGE_PROMPT_BULLET not in _read(path), f"{path.relative_to(ROOT)} should stay quiet for stage packs"



def test_skill_and_prompt_stay_thin_and_keep_shared_baselines_generic():
    skill_text = _read(SKILL)
    prompt_text = _read(PROMPT)

    assert "opt-in add-on" in skill_text
    assert "remain generic baselines rather than secondary policy owners" in skill_text

    for text in (skill_text, prompt_text):
        for marker in SECOND_OWNER_MARKERS:
            assert marker not in text
        for marker in STAGE_OWNER_MARKERS:
            assert marker not in text


def test_async_wait_resource_remains_the_wait_policy_owner_only():
    text = _read(WAIT_RESOURCE)

    for marker in STAGE_OWNER_MARKERS:
        assert marker not in text
    assert "### Stage Context Pack (when required)" not in text
    assert "| S2.3 / S2.5 enrichment |" not in text


def test_shared_baselines_and_agent_do_not_become_second_policy_owners():
    for path in SHARED_BASELINES + [ORCHESTRATOR_AGENT]:
        text = _read(path)
        for marker in SECOND_OWNER_MARKERS:
            assert marker not in text, f"{path.relative_to(ROOT)} should not own async-wait policy details"
        for marker in STAGE_OWNER_MARKERS:
            assert marker not in text, f"{path.relative_to(ROOT)} should not own stage-pack policy details"
        assert "### Stage Context Pack (when required)" not in text, f"{path.relative_to(ROOT)} should not own the stage pack schema"
        assert "| S2.3 / S2.5 enrichment |" not in text, f"{path.relative_to(ROOT)} should not own the stage matrix"


def test_touched_prompt_frontmatter_integrity():
    """Verify the daily orchestrator prompt preserves required frontmatter fields."""
    text = _read(PROMPT)
    assert "agent: bet-orchestrator" in text
    assert 'name: orchestrate-betting-day' in text
    assert "bet-orchestrating-workflows" in text