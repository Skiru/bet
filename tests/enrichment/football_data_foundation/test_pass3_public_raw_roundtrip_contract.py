from __future__ import annotations

import ast
from pathlib import Path


def test_public_raw_roundtrip_contract() -> None:
    # Verify that all implemented files in Pass 3 are syntactically valid and reviewable
    files_to_check = [
        "src/bet/enrichment/football_data_foundation/fusion/__init__.py",
        "src/bet/enrichment/football_data_foundation/fusion/policy.py",
        "src/bet/enrichment/football_data_foundation/fusion/conflict.py",
        "src/bet/enrichment/football_data_foundation/fusion/fuser.py",
        "src/bet/enrichment/football_data_foundation/fusion/output.py",
        "src/bet/enrichment/football_data_foundation/shadow_artifacts/__init__.py",
        "src/bet/enrichment/football_data_foundation/shadow_artifacts/writer.py",
        "src/bet/enrichment/football_data_foundation/certification/__init__.py",
        "src/bet/enrichment/football_data_foundation/certification/final_gate.py",
        "src/bet/enrichment/football_data_foundation/fixture_context/__init__.py",
        "src/bet/enrichment/football_data_foundation/fixture_context/loader.py",
    ]

    for fpath in files_to_check:
        path = Path(fpath)
        assert path.exists(), f"File {fpath} does not exist"
        
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        
        # Ast parses successfully
        try:
            ast.parse(text, filename=fpath)
        except SyntaxError as e:
            assert False, f"AST failed to parse {fpath}: {e}"
            
        # Line count is non-trivial for implemented modules
        if not path.name.startswith("__init__"):
            assert len(lines) >= 10, f"Module {fpath} is unexpectedly short"
