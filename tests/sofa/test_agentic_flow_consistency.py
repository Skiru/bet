"""The `/sofa-day` contracts describe the pipeline the code runs (plan
2026-10-05, part 6).

The flow lives in two places an agent obeys - the command
`.claude/commands/sofa-day.md` and the agent `.claude/agents/sofa-runner.md` -
and both load at session start, so a stage the code gained and the contracts
never mention is a stage no session runs. And since 2026-10-05 the WARIANT,
WARIANT WSZYSTKIE and the separate per-sport coupons are retired: a contract
that still describes one as current sends an agent to build a file the code
refuses (exit 2), or to report a result that no longer exists.

A paragraph may still mention a retired product, but only as history: it
names the retirement ("retired" / "historical") and a date.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.sofa import run_pipeline

ROOT = Path(__file__).resolve().parents[2]
CLAUDE = ROOT / ".claude"
SOFA_DAY = CLAUDE / "commands" / "sofa-day.md"
SOFA_RUNNER = CLAUDE / "agents" / "sofa-runner.md"

# The stages outside DEFAULT_SEQUENCE that the one coupon needs (plan K12/K14,
# F1, F7, K3).
NEW_STAGES = ("FIXTURE_CHECK", "SPORT_IDENTITY", "SPORT_CONFIDENCE", "COUPON_ASSEMBLY")

CONTRACTS = sorted(
    p
    for d in ("agents", "commands", "skills")
    for p in (CLAUDE / d).rglob("*.md")
    if "legacy" not in p.parts
)

# What a retired product is called anywhere in a contract.
RETIRED = re.compile(
    r"WARIANT|WSZYSTKIE|_wariant|--profile wariant|sport[ -]coupons?\b"
    r"|KUPON_<d(?:ate)?>_(?:CS2|HOKEJ|KOSZYKOWKA|SIATKOWKA)"
    r"|run_sport_coupon|run_multi_coupon|settle_multi_coupon|settle_sport_coupon"
    r"|multi_coupon|sofa-sport-runner",
    re.IGNORECASE,
)
HISTORY_WORD = re.compile(r"\bretired\b|\bhistorical\b|\bhistory\b", re.IGNORECASE)
DATE = re.compile(r"\b2026-\d\d-\d\d\b")


def _paragraphs(text: str) -> list[str]:
    """Blank-line separated blocks; a frontmatter is one block."""
    return [b for b in re.split(r"\n\s*\n", text) if b.strip()]


def current_mentions(text: str) -> list[str]:
    """The paragraphs that name a retired product without dating it as history."""
    return [
        b
        for b in _paragraphs(text)
        if RETIRED.search(b) and not (HISTORY_WORD.search(b) and DATE.search(b))
    ]


@pytest.mark.parametrize("path", [SOFA_DAY, SOFA_RUNNER], ids=lambda p: p.stem)
def test_every_stage_of_the_sequence_is_in_the_day_contracts(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    missing = sorted(
        {stage for stage, _ in run_pipeline.DEFAULT_SEQUENCE if stage not in text}
    )
    assert not missing, f"{path.name} never names the stages {missing}"


@pytest.mark.parametrize("stage", NEW_STAGES)
def test_a_new_stage_has_a_module_and_is_in_sofa_day(stage: str) -> None:
    assert stage in run_pipeline.STAGE_MODULES, (
        f"{stage} has no module in run_pipeline.STAGE_MODULES"
    )
    module = run_pipeline.STAGE_MODULES[stage]
    assert (ROOT / (module.replace(".", "/") + ".py")).exists(), (
        f"{stage} names {module}, which does not exist"
    )
    assert stage in SOFA_DAY.read_text(encoding="utf-8"), (
        f"sofa-day.md never names {stage}"
    )
    assert stage in SOFA_RUNNER.read_text(encoding="utf-8"), (
        f"sofa-runner.md never names {stage}"
    )


@pytest.mark.parametrize("path", CONTRACTS, ids=lambda p: str(p.relative_to(CLAUDE)))
def test_no_contract_describes_a_retired_product_as_current(path: Path) -> None:
    found = current_mentions(path.read_text(encoding="utf-8"))
    assert not found, (
        f"{path.relative_to(ROOT)} describes WARIANT / WSZYSTKIE / the per-sport "
        "coupons as current - delete the paragraph or date it as history "
        "('retired 2026-10-05 ...'):\n\n" + "\n---\n".join(b[:300] for b in found)
    )


def test_the_retired_runner_agent_is_gone() -> None:
    assert not (CLAUDE / "agents" / "sofa-sport-runner.md").exists()
    assert (CLAUDE / "agents" / "sofa-analyst-sport.md").exists()
    for path in CONTRACTS:
        assert "`sofa-sport-runner`" not in path.read_text(encoding="utf-8"), (
            f"{path.name} names the retired agent as one that exists"
        )


def test_the_history_rule_itself() -> None:
    """The checker must catch the old wording and pass a dated history line."""
    assert current_mentions("Build the WARIANT beside the coupon.")
    assert current_mentions("Launch four sofa-sport-runner agents.")
    assert current_mentions("run_multi_coupon.py assembles WSZYSTKIE (2026-09-30).")
    assert not current_mentions(
        "Retired 2026-10-05: WARIANT and WARIANT WSZYSTKIE (07:15Z)."
    )
    assert not current_mentions("The coupon prints every sport.")
