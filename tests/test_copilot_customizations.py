"""Customization-layer integrity tests for bet/.github artifacts.

Validates structural invariants after the copilot-customization-refactor.
Filesystem and regex-based only — no DB, no live pipeline, no network.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GITHUB_DIR = ROOT / ".github"
AGENTS_DIR = GITHUB_DIR / "agents"
PROMPTS_DIR = GITHUB_DIR / "prompts"
INTERNAL_PROMPTS_DIR = GITHUB_DIR / "internal-prompts"
INSTRUCTIONS_DIR = GITHUB_DIR / "instructions"
SKILLS_DIR = GITHUB_DIR / "skills"
MEMORIES_DIR = GITHUB_DIR / "memories"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _extract_frontmatter(path: Path) -> str:
    """Return raw YAML frontmatter text (without delimiters) or empty string."""
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    return m.group(1) if m else ""


def _active_agent_files() -> list[Path]:
    return sorted(AGENTS_DIR.glob("bet-*.agent.md"))


def _active_prompt_files() -> list[Path]:
    top = sorted(PROMPTS_DIR.glob("*.prompt.md"))
    internal = sorted(INTERNAL_PROMPTS_DIR.glob("*.prompt.md"))
    return top + internal


def _frontmatter_body_split(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return "", text
    return m.group(1), text[m.end():]


# ---------------------------------------------------------------------------
# 1. No .bak files
# ---------------------------------------------------------------------------


class TestNoBakFiles:
    def test_no_bak_under_github(self):
        bak_files = list(GITHUB_DIR.rglob("*.bak"))
        assert bak_files == [], f"Found .bak files: {[str(f.relative_to(ROOT)) for f in bak_files]}"


# ---------------------------------------------------------------------------
# 2. Model literals
# ---------------------------------------------------------------------------

_MODEL_RE = re.compile(r'^model:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)


class TestModelLiterals:
    @pytest.mark.parametrize(
        "artifact_file",
        sorted(GITHUB_DIR.rglob("*.md")),
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_active_model_is_gpt54(self, artifact_file: Path):
        if ".bak" in artifact_file.name:
            pytest.skip("Backup file")
        fm = _extract_frontmatter(artifact_file)
        if "model:" not in fm:
            pytest.skip("No model field")
        m = _MODEL_RE.search(fm)
        assert m is not None, f"No model field in {artifact_file.name}"
        assert m.group(1) == "GPT-5.4", (
            f"{artifact_file.name}: model is '{m.group(1)}', expected 'GPT-5.4'"
        )


# ---------------------------------------------------------------------------
# 3. Agent references from prompts
# ---------------------------------------------------------------------------

_AGENT_REF_RE = re.compile(r'^agent:\s*["\']?(bet-[\w-]+)["\']?\s*$', re.MULTILINE)


class TestAgentReferences:
    @pytest.mark.parametrize("prompt_file", _active_prompt_files(), ids=lambda p: p.name)
    def test_prompt_agent_exists(self, prompt_file: Path):
        fm = _extract_frontmatter(prompt_file)
        m = _AGENT_REF_RE.search(fm)
        if m is None:
            pytest.skip("No agent reference in frontmatter")
        agent_name = m.group(1)
        expected_path = AGENTS_DIR / f"{agent_name}.agent.md"
        assert expected_path.exists(), (
            f"{prompt_file.name} references agent '{agent_name}' but {expected_path.name} not found"
        )


_MODE_RE = re.compile(r'^mode:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)


class TestPromptFrontmatter:
    @pytest.mark.parametrize("prompt_file", _active_prompt_files(), ids=lambda p: p.name)
    def test_prompt_frontmatter_uses_spaces_not_tabs(self, prompt_file: Path):
        fm = _extract_frontmatter(prompt_file)
        assert "\t" not in fm, f"{prompt_file.name} frontmatter contains tab indentation"

    @pytest.mark.parametrize("prompt_file", _active_prompt_files(), ids=lambda p: p.name)
    def test_mode_values_are_valid_when_present(self, prompt_file: Path):
        fm = _extract_frontmatter(prompt_file)
        m = _MODE_RE.search(fm)
        if m is None:
            pytest.skip("No mode field")
        assert m.group(1) in {"ask", "edit", "agent"}, (
            f"{prompt_file.name} has invalid mode value '{m.group(1)}'"
        )


# ---------------------------------------------------------------------------
# 4. Agents arrays (orchestrator)
# ---------------------------------------------------------------------------

_AGENTS_ARRAY_RE = re.compile(r'^agents:\s*\[([^\]]+)\]', re.MULTILINE)
_AGENTS_BLOCK_RE = re.compile(r'^agents:\s*$\n((?:\s+-\s+.+\n?)+)', re.MULTILINE)


class TestAgentsArrays:
    @pytest.mark.parametrize("agent_file", _active_agent_files(), ids=lambda p: p.name)
    def test_agents_array_entries_exist(self, agent_file: Path):
        fm = _extract_frontmatter(agent_file)
        inline = _AGENTS_ARRAY_RE.search(fm)
        block = _AGENTS_BLOCK_RE.search(fm)
        if inline is not None:
            entries = [e.strip().strip('"').strip("'") for e in inline.group(1).split(",")]
        elif block is not None:
            entries = [
                line.split("-", 1)[1].strip().strip('"').strip("'")
                for line in block.group(1).splitlines()
                if line.strip().startswith("-")
            ]
        else:
            pytest.skip("No agents array")
        for entry in entries:
            if not entry:
                continue
            expected = AGENTS_DIR / f"{entry}.agent.md"
            assert expected.exists(), (
                f"{agent_file.name} lists agent '{entry}' but file not found"
            )


# ---------------------------------------------------------------------------
# 5. Instructions references
# ---------------------------------------------------------------------------

_INSTRUCTIONS_LINE_RE = re.compile(
    r"^\s+-\s+(?:\.\./instructions/|\.\./)?([\w-]+\.instructions\.md)", re.MULTILINE
)


class TestInstructionReferences:
    @pytest.mark.parametrize("agent_file", _active_agent_files(), ids=lambda p: p.name)
    def test_instruction_files_exist(self, agent_file: Path):
        fm = _extract_frontmatter(agent_file)
        refs = _INSTRUCTIONS_LINE_RE.findall(fm)
        if not refs:
            pytest.skip("No instruction refs")
        for ref in refs:
            # Resolve relative to instructions dir
            expected = INSTRUCTIONS_DIR / ref
            assert expected.exists(), (
                f"{agent_file.name} references instruction '{ref}' but file not found"
            )


_MANDATORY_INSTRUCTION_LOADS = {
    # S3 specialist
    "bet-statistician.agent.md": {"betting-mistakes-rules.instructions.md"},
    # S5/S6/S7 specialist
    "bet-challenger.agent.md": {"betting-mistakes-rules.instructions.md"},
    # S8 specialist
    "bet-builder.agent.md": {"betting-mistakes-rules.instructions.md"},
}


class TestMandatoryInstructionLoads:
    @pytest.mark.parametrize("agent_file", _active_agent_files(), ids=lambda p: p.name)
    def test_required_instruction_loads_present(self, agent_file: Path):
        required = _MANDATORY_INSTRUCTION_LOADS.get(agent_file.name)
        if not required:
            pytest.skip("No extra mandatory loads")
        fm = _extract_frontmatter(agent_file)
        refs = set(_INSTRUCTIONS_LINE_RE.findall(fm))
        missing = sorted(required - refs)
        assert not missing, f"{agent_file.name} missing mandatory instructions: {missing}"


# ---------------------------------------------------------------------------
# 6. Skills references
# ---------------------------------------------------------------------------

_SKILLS_LINE_RE = re.compile(r"^\s+-\s+(bet-[\w-]+)\s*$", re.MULTILINE)


class TestSkillReferences:
    @pytest.mark.parametrize(
        "artifact_file",
        _active_agent_files() + _active_prompt_files(),
        ids=lambda p: p.name,
    )
    def test_skill_dirs_exist(self, artifact_file: Path):
        fm = _extract_frontmatter(artifact_file)
        # Only look for skills: section
        skills_section = re.search(r"^skills:\s*\n((?:\s+-\s+.+\n?)+)", fm, re.MULTILINE)
        if not skills_section:
            pytest.skip("No skills section")
        refs = _SKILLS_LINE_RE.findall(skills_section.group(0))
        for ref in refs:
            skill_dir = SKILLS_DIR / ref
            skill_file = skill_dir / "SKILL.md"
            assert skill_file.exists(), (
                f"{artifact_file.name} references skill '{ref}' but {skill_file.relative_to(ROOT)} not found"
            )


# ---------------------------------------------------------------------------
# 7. Handoffs references
# ---------------------------------------------------------------------------

_HANDOFF_AGENT_RE = re.compile(r"^\s+agent:\s*(bet-[\w-]+)", re.MULTILINE)
_HANDOFF_PROMPT_RE = re.compile(r"^\s+prompt:\s*(.+)$", re.MULTILINE)


class TestHandoffReferences:
    @pytest.mark.parametrize("agent_file", _active_agent_files(), ids=lambda p: p.name)
    def test_handoff_agents_exist(self, agent_file: Path):
        fm = _extract_frontmatter(agent_file)
        if "handoffs:" not in fm:
            pytest.skip("No handoffs")
        agents_in_handoffs = _HANDOFF_AGENT_RE.findall(fm)
        for agent_name in agents_in_handoffs:
            expected = AGENTS_DIR / f"{agent_name}.agent.md"
            assert expected.exists(), (
                f"{agent_file.name} handoff references '{agent_name}' but file not found"
            )

    @pytest.mark.parametrize("agent_file", _active_agent_files(), ids=lambda p: p.name)
    def test_handoff_prompts_exist(self, agent_file: Path):
        fm = _extract_frontmatter(agent_file)
        if "handoffs:" not in fm:
            pytest.skip("No handoffs")
        prompt_refs = _HANDOFF_PROMPT_RE.findall(fm)
        if not prompt_refs:
            pytest.skip("No handoff prompt references")
        for raw_ref in prompt_refs:
            ref = raw_ref.strip().split()[0]
            if not ref.startswith("/"):
                continue
            prompt_name = ref.lstrip("/")
            expected_files = [
                PROMPTS_DIR / f"{prompt_name}.prompt.md",
                INTERNAL_PROMPTS_DIR / f"{prompt_name}.prompt.md",
            ]
            assert any(path.exists() for path in expected_files), (
                f"{agent_file.name} handoff references prompt '{prompt_name}' but no prompt file exists"
            )


_WORKFLOW_RESOURCE_REF_RE = re.compile(
    r"bet-orchestrating-workflows/resources/([\w-]+\.md)"
)


class TestBodyCrossReferences:
    @pytest.mark.parametrize(
        "artifact_file",
        sorted(GITHUB_DIR.rglob("*.md")),
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_workflow_resource_body_refs_exist(self, artifact_file: Path):
        if ".bak" in artifact_file.name:
            pytest.skip("Backup file")
        _, body = _frontmatter_body_split(artifact_file)
        refs = _WORKFLOW_RESOURCE_REF_RE.findall(body)
        if not refs:
            pytest.skip("No workflow resource refs")
        for ref in refs:
            expected = SKILLS_DIR / "bet-orchestrating-workflows" / "resources" / ref
            assert expected.exists(), (
                f"{artifact_file.relative_to(ROOT)} references missing workflow resource {expected.relative_to(ROOT)}"
            )


_FORBIDDEN_AGENT_BODY_PHRASES = [
    "## ⛔ HARD MANDATE: THINK BEFORE RETURNING",
    "Agent Intelligence Protocol",
    "## ⛔ agent-execution-protocol.instructions.md applies",
    "PERMANENT RULES (from copilot-instructions.md",
]


class TestAgentBodiesStayThin:
    @pytest.mark.parametrize(
        "agent_file",
        [path for path in _active_agent_files() if path.name != "bet-orchestrator.agent.md"],
        ids=lambda p: p.name,
    )
    def test_specialist_agents_do_not_copy_execution_protocol(self, agent_file: Path):
        _, body = _frontmatter_body_split(agent_file)
        for phrase in _FORBIDDEN_AGENT_BODY_PHRASES:
            assert phrase not in body, (
                f"{agent_file.name} still copies protocol text via phrase '{phrase}'"
            )


# ---------------------------------------------------------------------------
# 8. Stale prose memory-path references
# ---------------------------------------------------------------------------

# Match repo/session memory directories and specific markdown files.
_MEMORY_PATH_RE = re.compile(
    r"(/memories/repo/(?:[\w./{}-]+\.md)?|/memories/session/(?:[\w./{}-]+\.md)?|\.github/memories/(?:[\w./-]+\.md)?)"
)

# Known valid root memory files
_VALID_ROOT_MEMORY = {p.name for p in (ROOT / "memories" / "repo").glob("*.md")} if (ROOT / "memories" / "repo").exists() else set()
_VALID_SESSION_MEMORY = {str(p.relative_to(ROOT / "memories" / "session")) for p in (ROOT / "memories" / "session").rglob("*.md")} if (ROOT / "memories" / "session").exists() else set()
_VALID_GITHUB_MEMORY = set()
if MEMORIES_DIR.exists():
    _VALID_GITHUB_MEMORY = {str(p.relative_to(MEMORIES_DIR)) for p in MEMORIES_DIR.rglob("*.md")}


class TestMemoryPathReferences:
    @pytest.mark.parametrize(
        "artifact_file",
        list(GITHUB_DIR.rglob("*.md")),
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_no_stale_memory_paths(self, artifact_file: Path):
        if ".bak" in artifact_file.name:
            pytest.skip("Backup file")
        text = artifact_file.read_text(encoding="utf-8")
        stale = []
        for m in _MEMORY_PATH_RE.finditer(text):
            ref = m.group(1)
            if "{" in ref or "}" in ref:
                continue
            if ref == "/memories/repo/":
                if not (ROOT / "memories" / "repo").exists():
                    stale.append(ref)
                continue
            if ref == "/memories/session/":
                if not (ROOT / "memories" / "session").exists():
                    stale.append(ref)
                continue
            if ref == ".github/memories/":
                if not MEMORIES_DIR.exists():
                    stale.append(ref)
                continue
            if ref.startswith("/memories/repo/"):
                rel = ref.removeprefix("/memories/repo/")
                if rel not in _VALID_ROOT_MEMORY:
                    stale.append(ref)
                continue
            if ref.startswith("/memories/session/"):
                rel = ref.removeprefix("/memories/session/")
                if rel not in _VALID_SESSION_MEMORY:
                    stale.append(ref)
                continue
            if ref.startswith(".github/memories/"):
                rel = ref.removeprefix(".github/memories/")
                if rel not in _VALID_GITHUB_MEMORY:
                    stale.append(ref)
        assert stale == [], (
            f"{artifact_file.relative_to(ROOT)} has stale memory refs: {stale}"
        )
