import json
import os
import re
import urllib.parse

TOOL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.kilo/tool/bet_artifact_write.ts"))
PLUGIN_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.kilo/plugin/bet_artifact_write.ts"))


def read_tool_content():
    with open(TOOL_PATH, "r", encoding="utf-8") as f:
        return f.read()


def read_plugin_content():
    with open(PLUGIN_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _report_roots(content: str) -> list[str]:
    roots_match = re.search(r"const REPORT_ROOTS\s*=\s*\[([^\]]+)\]", content)
    assert roots_match is not None, "Could not find REPORT_ROOTS in active TS tool"
    return [r.strip(" '\"") for r in roots_match.group(1).split(",")]


def test_static_analysis_on_active_tool():
    content = read_tool_content()
    roots = _report_roots(content)

    assert "reports/pipeline_runs" in roots
    assert "reports/betting" in roots
    assert "reports/betting-demo" in roots
    assert "reports/other" not in roots
    assert 'const TOOL_VERSION = "standalone-pipeline-runs-v2"' in content
    assert "const SCHEMA_VERSION = 2" in content
    assert "allowed_report_roots" in content
    assert "supports_reports_pipeline_runs" in content
    assert "PATH_NOT_ALLOWED" in content
    assert "EXTENSION_MISMATCH" in content
    assert "CONTENT_SECRET_DETECTED" in content
    assert "CONTENT_INVALID_JSON" in content
    assert "PATH_TRAVERSAL" in content


def test_plugin_file_no_longer_registers_duplicate_tool():
    plugin_content = read_plugin_content()

    assert "export default tool(" not in plugin_content
    assert 'registers_tool_name: false' in plugin_content
    assert 'active_source: ".kilo/tool/bet_artifact_write.ts"' in plugin_content


def mock_is_allowed_path(path: str, roots: list[str]) -> bool:
    phase_handoffs = {
        ".kilo/state/phase-A-handoff.md",
        ".kilo/state/phase-B-handoff.md",
        ".kilo/state/phase-C-handoff.md",
        ".kilo/state/phase-D-handoff.md",
        ".kilo/state/phase-E-handoff.md",
    }
    if path in phase_handoffs:
        return True
    return any(path.startswith(f"{root}/") for root in roots)


def mock_validate_path(path: str, content_type: str, roots: list[str]):
    if path.startswith("/"):
        return {"ok": False, "code": "PATH_ABSOLUTE"}

    decoded = urllib.parse.unquote(path)
    normalized = os.path.normpath(decoded).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]

    if ".." in decoded or "../" in normalized or normalized == "..":
        code = "PATH_ENCODED_TRAVERSAL" if decoded != path else "PATH_TRAVERSAL"
        return {"ok": False, "code": code}

    if not mock_is_allowed_path(normalized, roots):
        return {"ok": False, "code": "PATH_NOT_ALLOWED"}

    expected_ext = ".md" if content_type == "markdown" else ".json"
    _, ext = os.path.splitext(normalized)
    if ext != expected_ext:
        return {"ok": False, "code": "EXTENSION_MISMATCH"}

    return {"ok": True, "normalized": normalized}


def mock_validate_content(content: str, content_type: str):
    secret_patterns = [
        r"(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|credential|auth)[\s:=]+['\"]?[^\s'\"<>]+['\"]?",
        r"Bearer\s+[A-Za-z0-9._-]+",
        r"sk-[A-Za-z0-9]{20,}",
    ]
    for pattern in secret_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return {"ok": False, "code": "CONTENT_SECRET_DETECTED"}

    if content_type == "json":
        try:
            json.loads(content)
        except ValueError:
            return {"ok": False, "code": "CONTENT_INVALID_JSON"}

    return {"ok": True}


def test_mock_validation_rules():
    roots = _report_roots(read_tool_content())

    res = mock_validate_path("reports/pipeline_runs/run_123/enricher_context_layer_tennis_1.json", "json", roots)
    assert res["ok"] is True

    res = mock_validate_path("reports/pipeline_runs/run_123/enricher_context_layer_tennis_1.md", "markdown", roots)
    assert res["ok"] is True

    res = mock_validate_path("reports/betting/some_run/some_file.json", "json", roots)
    assert res["ok"] is True

    res = mock_validate_path("reports/betting-demo/demo_file.md", "markdown", roots)
    assert res["ok"] is True

    res = mock_validate_path("/reports/pipeline_runs/run_123/file.json", "json", roots)
    assert res == {"ok": False, "code": "PATH_ABSOLUTE"}

    res = mock_validate_path("reports/pipeline_runs/run_123/../../etc/passwd", "json", roots)
    assert res == {"ok": False, "code": "PATH_TRAVERSAL"}

    res = mock_validate_path("reports/pipeline_runs/run_123/%2e%2e/file.json", "json", roots)
    assert res == {"ok": False, "code": "PATH_ENCODED_TRAVERSAL"}

    res = mock_validate_path("reports/pipeline_runs/run_123/file.txt", "json", roots)
    assert res == {"ok": False, "code": "EXTENSION_MISMATCH"}

    res = mock_validate_path("reports/other/run_123/file.json", "json", roots)
    assert res == {"ok": False, "code": "PATH_NOT_ALLOWED"}

    res = mock_validate_content("my secret token is: secret_value", "markdown")
    assert res == {"ok": False, "code": "CONTENT_SECRET_DETECTED"}

    res = mock_validate_content("{invalid json}", "json")
    assert res == {"ok": False, "code": "CONTENT_INVALID_JSON"}
