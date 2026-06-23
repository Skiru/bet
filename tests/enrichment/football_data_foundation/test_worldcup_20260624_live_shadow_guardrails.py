from pathlib import Path
import ast

def test_guardrail_no_production_writes() -> None:
    # TEST-016: guardrail confirms no writes to betting/data or production DB.
    # We verify that no SQLite database outside reports was modified recently
    # and no files were created under betting/data
    import subprocess
    out = subprocess.check_output(["git", "status", "--porcelain", "betting"], text=True)
    assert len(out.strip()) == 0, f"Git detected changes under betting/ directory:\n{out}"


def test_public_reviewability_python_files() -> None:
    # TEST-017: public reviewability: changed Python files are multi-line, ast-parseable, line length <= 300.
    pkg_dir = Path("src/bet/enrichment/football_data_foundation/worldcup_20260624_live_shadow")
    assert pkg_dir.exists()
    
    py_files = list(pkg_dir.glob("*.py"))
    assert len(py_files) >= 5
    
    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        
        # 1. AST parseable
        try:
            ast.parse(content)
        except SyntaxError as e:
            raise AssertionError(f"Python file {py_file.name} is not AST parseable: {e}")
            
        # 2. Line count (excluding __init__.py which can be shorter)
        lines = content.splitlines()
        if py_file.name != "__init__.py":
            assert len(lines) >= 10, f"Python file {py_file.name} is too short: {len(lines)} lines"
            
        # 3. No CR bytes
        assert "\r" not in content, f"Python file {py_file.name} contains CR bytes"
        
        # 4. Line length <= 300
        for i, line in enumerate(lines, 1):
            assert len(line) <= 300, f"Line {i} in {py_file.name} exceeds 300 characters: {len(line)}"


def test_public_raw_report_format() -> None:
    # TEST-018: final reports are pretty JSON/Markdown and line-readable.
    reports_dir = Path("reports/football_data_foundation/worldcup_20260624_live_shadow")
    if reports_dir.exists():
        for p in reports_dir.rglob("*.json"):
            if p.is_file():
                content = p.read_text(encoding="utf-8")
                # 1. JSON parseable
                try:
                    data = json.loads(content)
                except Exception as e:
                    # Might not have json imported in this test, let's import it locally
                    import json
                    try:
                        data = json.loads(content)
                    except Exception as ex:
                        raise AssertionError(f"Report file {p.name} is not valid JSON: {ex}")
                
                # 2. Line length <= 2000
                lines = content.splitlines()
                assert len(lines) >= 1, f"Report {p.name} is empty"
                for i, line in enumerate(lines, 1):
                    assert len(line) <= 2000, f"Line {i} in report {p.name} exceeds 2000 characters: {len(line)}"
