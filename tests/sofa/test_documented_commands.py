"""Every command the agents, the slash commands and the runbooks tell someone to
run must exist: the script, the stage after --only / --from-stage, and every
flag. An agent definition is loaded at session start, so a wrong command in
one is only discovered by the next session that obeys it - this test is the
check that can run in the session that wrote it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.sofa import run_pipeline

REPO = Path(__file__).resolve().parents[2]
DOCS = [
    REPO / "CLAUDE.md",
    *sorted((REPO / ".claude" / "agents").glob("*.md")),
    *sorted((REPO / ".claude" / "commands").glob("*.md")),
    *sorted((REPO / ".claude" / "skills").glob("*/SKILL.md")),
    *sorted((REPO / ".claude" / "skills").glob("*/references/*.md")),
    *sorted((REPO / "docs" / "sofa").glob("*.md")),
]
_COMMAND = re.compile(r"(scripts/sofa/[a-z0-9_]+\.py)([^`\"|#)\n]*)")
_FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")


def _commands() -> list[tuple[str, str, str]]:
    found = []
    for doc in DOCS:
        if not doc.exists():
            continue
        # A command continued with a trailing backslash is one command.
        text = re.sub(r"\\\n\s*", " ", doc.read_text(encoding="utf-8"))
        for m in _COMMAND.finditer(text):
            found.append((doc.relative_to(REPO).as_posix(), m.group(1), m.group(2)))
    return found


COMMANDS = _commands()


def test_the_docs_name_commands_at_all() -> None:
    assert len(COMMANDS) > 50
    assert any("shadow_daily.py" in script for _, script, _ in COMMANDS)


@pytest.mark.parametrize(("doc", "script", "args"), COMMANDS)
def test_a_documented_command_exists_with_its_flags(
    doc: str, script: str, args: str
) -> None:
    path = REPO / script
    assert path.exists(), f"{doc}: {script} does not exist"
    source = path.read_text(encoding="utf-8")
    for flag in _FLAG.findall(args):
        assert f'"{flag}"' in source, f"{doc}: {script} declares no {flag}"
    if script.endswith("run_pipeline.py"):
        stages = set(run_pipeline.STAGE_MODULES)
        for opt in ("--only", "--from-stage"):
            m = re.search(rf"{opt}\s+([A-Z0-9_]+)", args)
            if m:
                assert m.group(1) in stages, f"{doc}: unknown stage {m.group(1)}"


AGENTS = sorted((REPO / ".claude" / "agents").glob("sofa-*.md"))


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_an_agent_definition_loads(path: Path) -> None:
    """A frontmatter that does not parse loses the agent silently next session."""
    import yaml

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    front = yaml.safe_load(text.split("---\n", 2)[1])
    assert front["name"] == path.stem
    assert isinstance(front["description"], str) and len(front["description"]) > 40
    skills_dir = REPO / ".claude" / "skills"
    for skill in front.get("skills") or []:
        assert (skills_dir / skill / "SKILL.md").exists(), f"{path.name}: {skill}"


FRONTMATTERED = [
    *sorted((REPO / ".claude" / "commands").glob("*.md")),
    *sorted((REPO / ".claude" / "skills").glob("*/SKILL.md")),
]


@pytest.mark.parametrize(
    "path", FRONTMATTERED, ids=lambda p: p.relative_to(REPO / ".claude").as_posix()
)
def test_a_command_or_skill_frontmatter_parses(path: Path) -> None:
    import yaml

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    front = yaml.safe_load(text.split("---\n", 2)[1])
    assert isinstance(front.get("description"), str) and front["description"]
