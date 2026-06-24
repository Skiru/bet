from __future__ import annotations

import re
from pathlib import Path


def test_master_final_no_worldcup_hardcoding() -> None:
    # Check that no production code under our allowed/modified directories has hardcoded tokens
    search_dirs = [
        "src/bet/enrichment/football_data_foundation/fusion",
        "src/bet/enrichment/football_data_foundation/shadow_artifacts",
        "src/bet/enrichment/football_data_foundation/certification",
        "src/bet/enrichment/football_data_foundation/fixture_context",
    ]

    forbidden_tokens = ["World Cup", "Mistrzostwa", "2026", "argentina", "austria"]

    for sdir in search_dirs:
        dir_path = Path(sdir)
        if not dir_path.exists():
            continue

        for path in dir_path.glob("**/*.py"):
            text = path.read_text(encoding="utf-8")
            # Case insensitive search for forbidden tokens
            for tok in forbidden_tokens:
                if "__pycache__" in str(path):
                    continue
                match = re.search(re.escape(tok), text, re.IGNORECASE)
                assert match is None, (
                    f"Forbidden hardcoded token '{tok}' found in production file: {path}"
                )
