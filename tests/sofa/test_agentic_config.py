"""The `.claude` configuration must not contradict the code it drives.

Agent definitions, commands and skills are loaded at session start and are then
the only thing standing between an agent with Bash and a live day. Nothing at
runtime checks that a path they name exists, that a constant they quote is
still the constant, or that an analyst told to write no file is not also handed
a command that writes three. These tests do.

Checked here rather than by running the agents, because a rewritten definition
cannot be exercised in the session that wrote it.

Replaces tests/test_agent_definitions_are_consistent.py, which guarded the
retired `simple` pipeline's analysts and went silent when they were archived.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLAUDE = ROOT / ".claude"
AGENTS = sorted((CLAUDE / "agents").glob("*.md"))
COMMANDS = sorted((CLAUDE / "commands").glob("*.md"))
SKILLS = sorted(d for d in (CLAUDE / "skills").iterdir() if d.is_dir())
LIVE_MD = sorted(
    p
    for p in CLAUDE.rglob("*.md")
    if "legacy" not in p.parts and "worktrees" not in p.parts
)

# `simple` is retired. One exception, and it is named rather than implied:
# scripts/simple/audit_slip.py is a standalone EV calculator over a bookmaker
# consensus. It runs no stage, reads no `sofa` artifact, and the bet-slip-audit
# skill says so where it uses it.
LEGACY_SCRIPT_ALLOWLIST = {"scripts/simple/audit_slip.py"}


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    end = text.index("\n---", 3)
    head, body = text[3:end], text[end + 4 :]
    fields = dict(re.findall(r"^([a-z-]+):\s*(.*)$", head, re.M))
    fields["_raw"] = head
    return fields, body


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_agent_frontmatter_is_wired_to_things_that_exist(path: Path) -> None:
    fields, _ = _frontmatter(path)
    assert fields.get("name") == path.stem, f"{path.name}: name must equal the filename"
    assert fields.get(
        "description"
    ), f"{path.name}: no description, so it is never picked"
    assert fields.get("tools"), f"{path.name}: no tools line"
    for skill in re.findall(r"^\s+-\s+(\S+)$", fields["_raw"], re.M):
        assert (CLAUDE / "skills" / skill / "SKILL.md").exists(), (
            f"{path.name} preloads skill {skill!r}, which does not exist"
        )


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_no_sofa_agent_can_edit_code(path: Path) -> None:
    """A run that needed a file edited is a run that needs a human."""
    fields, _ = _frontmatter(path)
    tools = {t.strip() for t in fields.get("tools", "").split(",")}
    assert not tools & {"Write", "Edit", "NotebookEdit"}, (
        f"{path.name} carries a writing tool. Agents compose data through Bash; "
        f"they do not repair code."
    )


@pytest.mark.parametrize("path", COMMANDS, ids=lambda p: p.stem)
def test_command_frontmatter(path: Path) -> None:
    fields, body = _frontmatter(path)
    assert fields.get("description"), f"{path.name}: no description"
    assert fields.get("argument-hint"), f"{path.name}: no argument-hint"
    assert len(body.splitlines()) > 20, f"{path.name}: too thin to run a day from"


@pytest.mark.parametrize("path", LIVE_MD, ids=lambda p: str(p.relative_to(CLAUDE)))
def test_every_path_named_in_the_live_config_exists(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    missing = []
    pattern = (
        r"(?<![\w/`])((?:scripts|src|config|docs|tests|userscripts)"
        r"/[A-Za-z0-9_./-]+)"
    )
    for ref in re.findall(pattern, text):
        ref = ref.rstrip(".,);:*`")
        if "." not in Path(ref).name:  # a directory reference, allow with or without /
            continue
        if not (ROOT / ref).exists():
            missing.append(ref)
    assert not missing, (
        f"{path.name} names paths that do not exist: {sorted(set(missing))}"
    )


@pytest.mark.parametrize("path", LIVE_MD, ids=lambda p: str(p.relative_to(CLAUDE)))
def test_live_config_does_not_drive_the_retired_pipeline(path: Path) -> None:
    refs = {
        f"scripts/simple/{m}"
        for m in re.findall(
            r"scripts/simple/([A-Za-z0-9_]+\.py)", path.read_text("utf-8")
        )
    }
    unexpected = refs - LEGACY_SCRIPT_ALLOWLIST
    assert not unexpected, (
        f"{path.name} instructs a retired `simple` script: {sorted(unexpected)}"
    )


@pytest.mark.parametrize("path", AGENTS + COMMANDS, ids=lambda p: p.stem)
def test_named_agents_and_commands_exist(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    known = {p.stem for p in AGENTS} | {p.stem for p in COMMANDS}
    named = set(re.findall(r"[`/](sofa-[a-z-]+?)[`\s.,]", text)) - {"sofa-pipeline"}
    skill_names = {d.name for d in SKILLS}
    unknown = {n for n in named if n not in known and n not in skill_names}
    assert not unknown, (
        f"{path.name} refers to unknown agents/commands: {sorted(unknown)}"
    )


def test_the_veto_schema_in_the_config_matches_the_contract() -> None:
    """`vetoes.json` is the analyst's only channel; a wrong key voids the file."""
    from bet.sofa.contracts import Veto

    contract = CLAUDE / "skills/sofa-analysis-core/references/veto-contract.md"
    text = contract.read_text("utf-8")
    for field in Veto.model_fields:
        assert field in text, f"veto-contract.md does not document the {field!r} field"
    annotation = Veto.model_fields["reason_class"].annotation
    classes = get_args(annotation)
    assert classes, "reason_class is no longer a Literal - update this test"
    for reason_class in classes:
        assert reason_class in text, (
            f"veto-contract.md omits reason_class {reason_class!r}"
        )
    from bet.sofa.contracts import ContextSignal

    for tag in get_args(ContextSignal):
        assert tag in text, f"veto-contract.md omits context tag {tag!r}"
    sources = CLAUDE / "skills/sofa-analysis-core/references/context-sources.md"
    assert sources.exists(), "veto-contract.md points at context-sources.md"


CRITICAL_CONSTANTS = {
    "MIN_ODDS_FLOOR": ("bet.sofa.coupon", 1.25),
    "MAX_SAMPLE_AGE_DAYS": ("bet.sofa.coupon", 60),
    "MAX_PER_FIXTURE": ("bet.sofa.coupon", 3),
    "MAX_PER_MECHANISM_FAMILY_PER_FIXTURE": ("bet.sofa.coupon", 1),
    "MAX_DISAGREEMENT": ("bet.sofa.confidence", 0.10),
    "BUILDER_CORRELATION_HAIRCUT": ("bet.sofa.confidence", 0.12),
    "MIN_BUILDER_SAMPLE": ("bet.sofa.confidence", 10),
    "MAX_BUILDER_LEGS": ("bet.sofa.confidence", 4),
    "MAX_BUILDER_SAMPLE_AGE_DAYS": ("bet.sofa.confidence", 180),
    "CONFIDENCE_CEILING": ("bet.sofa.confidence", 0.9202),
    "K_PRICE": ("bet.sofa.engine", 10.0),
}


@pytest.mark.parametrize("name", sorted(CRITICAL_CONSTANTS))
def test_a_quoted_constant_still_has_the_value_the_config_quotes(name: str) -> None:
    """A stale number in a contract is worse than no number: it is trusted.

    The config and the Polish documentation quote these by value, in prose an
    agent acts on. When one moves in code, both have to move with it — this is
    the test that says so out loud instead of leaving a plausible wrong number
    in a file nobody re-reads.
    """
    import importlib

    module_name, expected = CRITICAL_CONSTANTS[name]
    value = getattr(importlib.import_module(module_name), name)
    assert value == pytest.approx(expected), (
        f"{name} is {value!r} in {module_name}, but the agentic config and "
        f"docs/sofa/ describe it as {expected!r}. Update both, or neither is "
        f"trustworthy."
    )
    quoted = [p.name for p in LIVE_MD if name in p.read_text("utf-8")]
    assert quoted, f"{name} is quoted nowhere in .claude — the agents cannot know it"
