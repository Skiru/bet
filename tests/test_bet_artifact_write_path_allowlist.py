import os
import re
import json
import urllib.parse

PLUGIN_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures/bet_artifact_write.ts"))


def read_plugin_content():
    with open(PLUGIN_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_static_analysis_on_plugin():
    content = read_plugin_content()

    # Verify REPORT_ROOTS contains reports/pipeline_runs, reports/betting, reports/betting-demo
    roots_match = re.search(r"const REPORT_ROOTS\s*=\s*\[([^\]]+)\]", content)
    assert roots_match is not None, "Could not find REPORT_ROOTS in TS plugin"

    roots_str = roots_match.group(1)
    roots = [r.strip(" '\"") for r in roots_str.split(",")]

    assert "reports/pipeline_runs" in roots, "reports/pipeline_runs must be allowed in REPORT_ROOTS"
    assert "reports/betting" in roots, "reports/betting must be allowed in REPORT_ROOTS"
    assert "reports/betting-demo" in roots, "reports/betting-demo must be allowed in REPORT_ROOTS"
    assert "reports/other" not in roots, "arbitrary reports/other/ must not be allowed"

    # Verify critical check strings still exist in the file
    assert "PATH_NOT_ALLOWED" in content, "PATH_NOT_ALLOWED must exist in TS plugin"
    assert "EXTENSION_MISMATCH" in content, "EXTENSION_MISMATCH must exist in TS plugin"
    assert "CONTENT_SECRET_DETECTED" in content, "CONTENT_SECRET_DETECTED must exist in TS plugin"
    assert "CONTENT_INVALID_JSON" in content, "CONTENT_INVALID_JSON must exist in TS plugin"
    assert "PATH_TRAVERSAL" in content, "PATH_TRAVERSAL must exist in TS plugin"


def mock_is_allowed_path(path: str, roots: list) -> bool:
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


def mock_validate_path(path: str, content_type: str, roots: list):
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
        r"sk-[A-Za-z0-9]{20,}"
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
    content = read_plugin_content()
    roots_match = re.search(r"const REPORT_ROOTS\s*=\s*\[([^\]]+)\]", content)
    roots_str = roots_match.group(1)
    roots = [r.strip(" '\"") for r in roots_str.split(",")]

    # reports/pipeline_runs/<run_id>/enricher_context_layer_tennis_1.json is allowed
    res = mock_validate_path("reports/pipeline_runs/run_123/enricher_context_layer_tennis_1.json", "json", roots)
    assert res["ok"] is True

    # reports/pipeline_runs/<run_id>/enricher_context_layer_tennis_1.md is allowed
    res = mock_validate_path("reports/pipeline_runs/run_123/enricher_context_layer_tennis_1.md", "markdown", roots)
    assert res["ok"] is True

    # reports/betting/... remains allowed
    res = mock_validate_path("reports/betting/some_run/some_file.json", "json", roots)
    assert res["ok"] is True

    # reports/betting-demo/... remains allowed
    res = mock_validate_path("reports/betting-demo/demo_file.md", "markdown", roots)
    assert res["ok"] is True

    # absolute paths are blocked
    res = mock_validate_path("/reports/pipeline_runs/run_123/file.json", "json", roots)
    assert res["ok"] is False
    assert res["code"] == "PATH_ABSOLUTE"

    # path traversal is blocked
    res = mock_validate_path("reports/pipeline_runs/run_123/../../etc/passwd", "json", roots)
    assert res["ok"] is False
    assert res["code"] == "PATH_TRAVERSAL"

    # encoded traversal is blocked
    res = mock_validate_path("reports/pipeline_runs/run_123/%2e%2e/file.json", "json", roots)
    assert res["ok"] is False
    assert res["code"] == "PATH_ENCODED_TRAVERSAL"

    # wrong extension is blocked
    res = mock_validate_path("reports/pipeline_runs/run_123/file.txt", "json", roots)
    assert res["ok"] is False
    assert res["code"] == "EXTENSION_MISMATCH"

    # arbitrary reports/other/... remains blocked
    res = mock_validate_path("reports/other/run_123/file.json", "json", roots)
    assert res["ok"] is False
    assert res["code"] == "PATH_NOT_ALLOWED"

    # secret-like content is blocked
    res = mock_validate_content("my secret token is: secret_value", "markdown")
    assert res["ok"] is False
    assert res["code"] == "CONTENT_SECRET_DETECTED"

    # invalid JSON is blocked for content_type=json
    res = mock_validate_content("{invalid json}", "json")
    assert res["ok"] is False
    assert res["code"] == "CONTENT_INVALID_JSON"
