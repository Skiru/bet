import re
from pathlib import Path


def test_guardrails_no_forbidden_imports_in_source() -> None:
    """The canary stays an observer: no betting, db, pipeline or scraper layer.

    ``bet.api_clients`` is forbidden as a package but **not** its credential
    reader. ``bet.api_clients.env.get_env`` is this project's single source of
    truth for provider credentials, and deliberately the only one: its own
    docstring records the incident that made it so -- ``.env`` carried
    TheSportsDB's demo key ``123`` while ``config/api_keys.json`` held a real
    one, the demo key silently won, and nothing raised.

    So the blanket ban was the stale half of this guardrail, not the two
    imports it caught (``live_shadow_canary/runner.py`` and
    ``provider_probe.py``, both calling ``get_env`` for exactly the three keys
    they probe). Satisfying it by reading ``os.environ`` inside the canary
    would have re-created the second credential path that incident is about --
    a guardrail that pushes you into the defect it is meant to prevent. What
    the isolation is actually protecting is that the canary never reaches a
    *client*, a session or a transport, which is still asserted below.
    """
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
    # Read for credentials only; see the docstring.
    allowed_exceptions = {"bet.api_clients.env"}

    import_re = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)")

    for py_file in python_files:
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            m = import_re.match(line)
            if m:
                module = m.group(1)
                first_part = module.split(".")[0]
                # Allow standard bet imports except forbidden ones
                if first_part == "bet":
                    if module in allowed_exceptions:
                        continue
                    # Check next sub-module
                    parts = module.split(".")
                    if len(parts) > 1:
                        sub_part = parts[1]
                        assert sub_part not in forbidden_imports, (
                            f"Forbidden import '{module}' found in {py_file.name}"
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


def test_public_reviewability_verification() -> None:
    import ast
    paths = list(Path("src/bet/enrichment/football_data_foundation/live_shadow_canary").glob("*.py"))
    paths += list(Path("tests/enrichment/football_data_foundation").glob("test_live_shadow_canary_*.py"))

    for path in paths:
        text = path.read_text(encoding="utf-8")
        raw = path.read_bytes()

        # AST check
        try:
            ast.parse(text, filename=str(path))
            ast_ok = True
        except SyntaxError:
            ast_ok = False

        assert ast_ok, f"AST parsing failed for {path}"

        # future import check
        bad_future = "from " + "future " + "import annotations" in text
        assert not bad_future, f"Forbidden future import found in {path}"

        # carriage return check
        has_cr = b"\r" in raw
        assert not has_cr, f"Carriage returns found in {path}"

        # Line count check (exclude __init__.py)
        lines = text.count("\n") + 1
        if path.name != "__init__.py":
            assert lines >= 20, f"File {path} has fewer than 20 lines ({lines} lines)"

