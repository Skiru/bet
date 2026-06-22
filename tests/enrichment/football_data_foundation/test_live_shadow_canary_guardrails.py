import re
from pathlib import Path


def test_guardrails_no_forbidden_imports_in_source() -> None:
    source_dir = Path("src/bet/enrichment/football_data_foundation/live_shadow_canary")
    python_files = list(source_dir.glob("**/*.py"))
    assert len(python_files) > 0

    forbidden_imports = {
        "betting",
        "db",
        "pipeline",
        "api_clients",
        "scrapers",
    }

    import_re = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)")

    for py_file in python_files:
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            m = import_re.match(line)
            if m:
                first_part = m.group(1).split(".")[0]
                # Allow standard bet imports except forbidden ones
                if first_part == "bet":
                    # Check next sub-module
                    parts = m.group(1).split(".")
                    if len(parts) > 1:
                        sub_part = parts[1]
                        assert sub_part not in forbidden_imports, (
                            f"Forbidden import '{m.group(1)}' found in {py_file.name}"
                        )


def test_guardrails_no_writing_to_betting_data() -> None:
    source_dir = Path("src/bet/enrichment/football_data_foundation/live_shadow_canary")
    python_files = list(source_dir.glob("**/*.py"))
    
    for py_file in python_files:
        content = py_file.read_text(encoding="utf-8")
        # Ensure no betting/data string exists
        assert "betting/data" not in content, (
            f"Reference to betting/data found in {py_file.name}"
        )


def test_guardrails_no_secrets_or_forbidden_markers_in_reports() -> None:
    reports_dir = Path("reports/football_data_foundation/live_shadow_canary")
    if not reports_dir.exists():
        # Reports might not be generated yet, which is fine
        return

    # Check all files in reports
    for report_file in reports_dir.glob("**/*"):
        if report_file.is_file():
            text = report_file.read_text(encoding="utf-8")
            
            # 1. No raw payload/response body keywords
            forbidden_raw = {"raw_payload", "response_body", "json_raw", "raw_json", "raw_html"}
            for keyword in forbidden_raw:
                assert keyword not in text.lower(), (
                    f"Forbidden raw payload keyword '{keyword}' found in report {report_file.name}"
                )
                
            # 2. No PRODUCTION_READY or production_ready
            assert "production_ready" not in text.lower(), (
                f"Forbidden 'production_ready' marker found in report {report_file.name}"
            )
            
            # 3. No secrets or tokens
            assert "api_key" not in text.lower(), (
                f"Secret-like key 'api_key' found in report {report_file.name}"
            )
            assert "auth_token" not in text.lower(), (
                f"Secret-like key 'auth_token' found in report {report_file.name}"
            )
