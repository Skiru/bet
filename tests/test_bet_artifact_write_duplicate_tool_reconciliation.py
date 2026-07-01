from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL_PATH = PROJECT_ROOT / ".kilo" / "tool" / "bet_artifact_write.ts"
PLUGIN_PATH = PROJECT_ROOT / ".kilo" / "plugin" / "bet_artifact_write.ts"


def _content(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_exactly_one_project_source_registers_bet_artifact_write() -> None:
    sources = {
        str(TOOL_PATH.relative_to(PROJECT_ROOT)): "export default tool(" in _content(TOOL_PATH),
        str(PLUGIN_PATH.relative_to(PROJECT_ROOT)): "export default tool(" in _content(PLUGIN_PATH),
    }

    active = [path for path, registers in sources.items() if registers]
    assert active == [".kilo/tool/bet_artifact_write.ts"]


def test_no_legacy_report_roots_only_source_remains() -> None:
    tool_content = _content(TOOL_PATH)
    plugin_content = _content(PLUGIN_PATH)

    legacy_roots = 'const REPORT_ROOTS = ["reports/betting-demo", "reports/betting"]'
    assert legacy_roots not in tool_content
    assert legacy_roots not in plugin_content
    assert '"reports/pipeline_runs"' in tool_content
    assert 'const SCHEMA_VERSION = 2' in tool_content
    assert 'const TOOL_VERSION = "standalone-pipeline-runs-v2"' in tool_content


def test_plugin_and_tool_do_not_both_register_same_name() -> None:
    tool_content = _content(TOOL_PATH)
    plugin_content = _content(PLUGIN_PATH)

    assert 'const TOOL_NAME = "bet_artifact_write"' in tool_content
    assert "export default tool(" in tool_content
    assert "export default tool(" not in plugin_content
    assert 'registers_tool_name: false' in plugin_content
