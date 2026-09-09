"""An agent definition must not contradict itself about writing files.

Both analyst definitions carried a direct contradiction: the description said
"never writes files" and the body instructed
`python3 scripts/simple/build_forecast.py --date <date>`, which writes two.
The football one managed it in adjacent sentences -- "Never generate an
artifact." followed two lines later by "build it".

That matters more than tidiness. These agents are given Bash, so nothing but
the instruction stops them writing; when the instruction says both, the
operator cannot tell which artifacts a run may have touched. The resolution is
to name the single permitted write rather than to deny it.

Checked here rather than by running the agents, because agent definitions and
their preloaded skills load at session start: a rewritten definition cannot be
exercised in the session that wrote it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIRS = (ROOT / ".claude" / "agents", ROOT / ".kilo" / "agent")

ANALYSTS = ("bet-analyst-football.md", "bet-analyst-tennis.md")

# Commands that write into runs/ or the database. build_forecast is the one
# the analysts are allowed, and it is pure: it re-reads the sheet and dossiers
# already on disk and costs no provider calls.
_WRITING_COMMANDS = (
    "run_pipeline.py",
    "run_discover.py",
    "run_enrich.py",
    "run_analyze.py",
    "run_superbet.py",
    "run_market_context.py",
    "run_tipsters.py",
    "build_coupons.py",
)


@pytest.mark.parametrize("agent_dir", AGENT_DIRS)
@pytest.mark.parametrize("name", ANALYSTS)
def test_an_analyst_does_not_both_forbid_and_instruct_a_write(agent_dir, name) -> None:
    path = agent_dir / name
    if not path.exists():
        pytest.skip(f"{name} not present in {agent_dir}")
    text = path.read_text(encoding="utf-8")
    instructs_a_write = "build_forecast.py" in text
    for phrase in ("never writes files", "Never generate an artifact"):
        if phrase.lower() in text.lower():
            assert not instructs_a_write, (
                f"{name} in {agent_dir.name} says {phrase!r} and also instructs build_forecast.py. "
                f"Name the one permitted write instead of denying it."
            )


@pytest.mark.parametrize("agent_dir", AGENT_DIRS)
@pytest.mark.parametrize("name", ANALYSTS)
def test_an_analyst_never_instructs_a_pipeline_write(agent_dir, name) -> None:
    """The prohibition that must hold unconditionally: no pipeline, no coupon."""
    path = agent_dir / name
    if not path.exists():
        pytest.skip(f"{name} not present in {agent_dir}")
    text = path.read_text(encoding="utf-8")
    for command in _WRITING_COMMANDS:
        # A prohibition may name the command; an instruction is a command line.
        for match in re.finditer(rf"python3?\s+\S*{re.escape(command)}", text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line = text[line_start:text.find("\n", match.start())]
            prose = line.lstrip().startswith(("#", ">", "*", "-"))
            assert prose or "not" in line.lower(), (
                f"{name} in {agent_dir.name} contains a runnable {command} command: {line.strip()!r}. "
                f"Analysts read a finished day; they do not produce one."
            )
