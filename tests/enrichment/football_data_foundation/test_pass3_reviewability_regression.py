from __future__ import annotations

import ast
from pathlib import Path


def test_pass3_reviewability_regression() -> None:
    files_to_check = [
        "src/bet/enrichment/football_data_foundation/transport/http_json.py",
        "src/bet/enrichment/football_data_foundation/provider_clients/current_live.py",
        "src/bet/enrichment/football_data_foundation/open_data_adapters/pass2_parsers.py",
        "src/bet/enrichment/football_data_foundation/soccerdata_replay/pass2_replay.py",
        "src/bet/enrichment/football_data_foundation/shadow_certification/summary.py",
        "src/bet/enrichment/football_data_foundation/fusion/fuser.py",
        "src/bet/enrichment/football_data_foundation/shadow_artifacts/writer.py",
        "src/bet/enrichment/football_data_foundation/certification/final_gate.py",
        "src/bet/enrichment/football_data_foundation/fixture_context/loader.py",
    ]

    collapsed_patterns = [
        "from __future__ " + "import annotations import ",
        " import hashlib " + "import ",
        " import json " + "import ",
        " import os " + "import ",
        " class ",
    ]

    for fpath in files_to_check:
        path = Path(fpath)
        assert path.exists(), f"{fpath} does not exist"

        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        line_count = len(lines)

        assert line_count > 20, f"{fpath} has too few lines: {line_count}"

        # AST parsing check
        try:
            ast.parse(text, filename=fpath)
        except SyntaxError as e:
            assert False, f"Syntax error in {fpath}: {e}"

        # check collapsed patterns
        for pattern in collapsed_patterns:
            assert pattern not in text, (
                f"Collapsed pattern '{pattern}' found in {fpath}"
            )
