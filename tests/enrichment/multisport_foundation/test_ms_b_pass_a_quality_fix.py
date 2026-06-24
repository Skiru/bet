from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pathlib import Path


def test_pass_a_markdown_goal_assertion_is_not_truthy_bug() -> None:
    test_path = ROOT / "tests/enrichment/multisport_foundation/test_ms_a_foundation.py"
    if not test_path.exists():
        return
    text = test_path.read_text(encoding="utf-8")
    assert 'assert "## Goals" or "## Goal" in markdown' not in text
    assert ('assert "## Goals" in markdown or "## Goal" in markdown' in text) or ('assert any(marker in markdown for marker in ("## Goals", "## Goal"))' in text)
