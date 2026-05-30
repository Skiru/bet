"""Validates Roo Code customization files are structurally sound."""

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestRoomodes:
    """Validate .roomodes JSON schema."""

    @pytest.fixture
    def roomodes(self):
        path = ROOT / ".roomodes"
        assert path.exists(), ".roomodes file missing"
        return json.loads(path.read_text())

    def test_has_custom_modes_key(self, roomodes):
        assert "customModes" in roomodes

    def test_minimum_mode_count(self, roomodes):
        assert len(roomodes["customModes"]) >= 10

    def test_mode_required_fields(self, roomodes):
        required = {"slug", "name", "roleDefinition", "whenToUse", "customInstructions", "groups"}
        for mode in roomodes["customModes"]:
            missing = required - set(mode.keys())
            assert not missing, f"Mode '{mode.get('slug', '?')}' missing: {missing}"

    def test_mode_slugs_unique(self, roomodes):
        slugs = [m["slug"] for m in roomodes["customModes"]]
        assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {slugs}"

    def test_all_expected_modes_present(self, roomodes):
        expected = {
            "bet-orchestrator",
            "bet-statistician",
            "bet-challenger",
            "bet-builder",
            "bet-scanner",
            "bet-settler",
            "bet-scout",
            "bet-enricher",
            "bet-valuator",
            "bet-db-analyst",
        }
        actual = {m["slug"] for m in roomodes["customModes"]}
        missing = expected - actual
        assert not missing, f"Missing modes: {missing}"

    def test_groups_valid(self, roomodes):
        valid_groups = {"read", "edit", "browser", "command", "mcp"}
        for mode in roomodes["customModes"]:
            invalid = set(mode["groups"]) - valid_groups
            assert not invalid, f"Mode '{mode['slug']}' has invalid groups: {invalid}"

    def test_orchestrator_has_all_groups(self, roomodes):
        orch = next(m for m in roomodes["customModes"] if m["slug"] == "bet-orchestrator")
        assert set(orch["groups"]) == {"read", "edit", "browser", "command", "mcp"}


class TestClinerules:
    """Validate .clinerules exists and has content."""

    def test_exists(self):
        path = ROOT / ".clinerules"
        assert path.exists(), ".clinerules file missing"

    def test_not_empty(self):
        path = ROOT / ".clinerules"
        content = path.read_text()
        assert len(content) > 100, ".clinerules too short"

    def test_contains_key_rules(self):
        content = (ROOT / ".clinerules").read_text()
        assert "fish" in content.lower() or "terminal" in content.lower()
        assert "betting.db" in content or "SQLite" in content


class TestRooMcpJson:
    """Validate .roo/mcp.json structure."""

    @pytest.fixture
    def mcp_config(self):
        path = ROOT / ".roo" / "mcp.json"
        assert path.exists(), ".roo/mcp.json missing"
        return json.loads(path.read_text())

    def test_has_mcp_servers_key(self, mcp_config):
        assert "mcpServers" in mcp_config

    def test_has_sequential_thinking(self, mcp_config):
        assert "sequentialthinking" in mcp_config["mcpServers"]

    def test_has_sqlite(self, mcp_config):
        assert "sqlite" in mcp_config["mcpServers"]

    def test_has_brave_search(self, mcp_config):
        assert "brave-search" in mcp_config["mcpServers"]

    def test_sqlite_points_to_betting_db(self, mcp_config):
        sqlite_cfg = mcp_config["mcpServers"]["sqlite"]
        args = sqlite_cfg.get("args", [])
        assert any("betting.db" in str(a) for a in args), "SQLite not pointing to betting.db"


class TestMemoryBank:
    """Validate .roo/memory-bank/ seed files."""

    EXPECTED_FILES = [
        "project-structure.md",
        "pipeline-knowledge.md",
        "workflow.md",
        "coupon-risk-lessons.md",
        "betting-preferences.md",
    ]

    def test_memory_bank_dir_exists(self):
        path = ROOT / ".roo" / "memory-bank"
        assert path.is_dir(), ".roo/memory-bank/ directory missing"

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_seed_file_exists(self, filename):
        path = ROOT / ".roo" / "memory-bank" / filename
        assert path.exists(), f"Memory bank file missing: {filename}"

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_seed_file_not_empty(self, filename):
        path = ROOT / ".roo" / "memory-bank" / filename
        assert len(path.read_text()) > 50, f"Memory bank file too short: {filename}"


class TestContinueConfig:
    """Validate .continuerc.json for Continue.dev."""

    def test_exists(self):
        path = ROOT / ".continuerc.json"
        assert path.exists(), ".continuerc.json missing"

    def test_valid_json(self):
        path = ROOT / ".continuerc.json"
        config = json.loads(path.read_text())
        assert "tabAutocompleteModel" in config

    def test_points_to_lmstudio(self):
        config = json.loads((ROOT / ".continuerc.json").read_text())
        model_cfg = config["tabAutocompleteModel"]
        assert "localhost" in model_cfg.get("apiBase", "")


class TestSecurityAndRuleDirs:
    """Validate no secrets in tracked files and rule directories exist."""

    def test_api_keys_example_has_no_real_keys(self):
        path = ROOT / "config" / "api_keys.example.json"
        content = path.read_text()
        data = json.loads(content)
        placeholder_markers = ("YOUR_", "SAME_", "register", "http")
        for key, value in data.items():
            if key == "_comment":
                continue
            val_str = str(value).lower()
            is_placeholder = value is None or any(m.lower() in val_str for m in placeholder_markers)
            assert is_placeholder, (
                f"api_keys.example.json key '{key}' may contain a real secret: {value!r}"
            )

    def test_clinerules_bans_pipeline_orchestrator(self):
        content = (ROOT / ".clinerules").read_text()
        assert "pipeline_orchestrator" in content.lower() or "BANNED" in content

    @pytest.mark.parametrize(
        "mode_slug",
        ["bet-orchestrator", "bet-statistician", "bet-challenger", "bet-builder", "bet-scanner", "bet-enricher"],
    )
    def test_per_mode_rule_dir_exists(self, mode_slug):
        path = ROOT / ".roo" / f"rules-{mode_slug}"
        assert path.is_dir(), f"Per-mode rule directory missing: .roo/rules-{mode_slug}/"

    def test_per_mode_rule_dirs_have_content(self):
        for d in (ROOT / ".roo").iterdir():
            if d.is_dir() and d.name.startswith("rules-bet-"):
                files = list(d.glob("*.md"))
                assert len(files) >= 1, f"{d.name} has no .md rule files"
