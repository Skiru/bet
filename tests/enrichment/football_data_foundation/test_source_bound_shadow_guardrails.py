import ast
import socket
import pytest
from pathlib import Path
from bet.enrichment.football_data_foundation.source_bound_shadow.runner import run_source_bound_shadow_enrichment

def test_guardrail_forbids_live_network_usage(tmp_path):
    from bet.enrichment.football_data_foundation.source_bound_shadow.runner import socket_block_context
    with socket_block_context() as attempts:
        result = run_source_bound_shadow_enrichment(
            project_root=Path("tests/fixtures"),
            output_root=tmp_path / "reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal_test",
            fixture_slug="worldcup2026-norway-senegal",
        )
        assert result["verdict"] == "PASS"
        assert result["network_probe_check"] == "PASS"
        
        # Verify no committed test reports were written to the standard workspace path
        workspace_test_report = Path("reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal_test")
        assert not workspace_test_report.exists()

def test_changed_files_ast_parseable_and_multiline():
    src_dir = Path("src/bet/enrichment/football_data_foundation/source_bound_shadow")
    files = list(src_dir.glob("*.py"))
    assert len(files) >= 5
    
    for f in files:
        content = f.read_text(encoding="utf-8")
        # Assert ast-parseable (REQ-REVIEW-003)
        tree = ast.parse(content)
        assert tree is not None
        
        # Assert no CR bytes (REQ-REVIEW-002)
        assert b"\r" not in f.read_bytes()
        
        # Assert line count >= 40 (unless __init__.py) (REQ-REVIEW-004)
        lines = content.split("\n")
        if f.name != "__init__.py":
            assert len(lines) >= 40, f"File {f.name} has only {len(lines)} lines, must be >= 40"
            
        # Assert no from __future__ import annotations (REQ-REVIEW-006)
        assert "from __future__ import annotations" not in content, f"File {f.name} contains forbidden import annotations"
        assert "from future import annotations" not in content, f"File {f.name} contains forbidden import annotations"

        # Assert no line-ending proof comments (REQ-REVIEW-007)
        for idx, line in enumerate(lines, 1):
            if "#" in line:
                comment = line.split("#", 1)[1].lower()
                assert "line ending" not in comment, f"Forbidden line-ending comment in {f.name}:{idx}"
                assert "lf only" not in comment, f"Forbidden line-ending comment in {f.name}:{idx}"
                assert "line-ending" not in comment, f"Forbidden line-ending comment in {f.name}:{idx}"
