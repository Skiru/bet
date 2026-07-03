import json
from pathlib import Path


RUN_ROOT = Path("reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def test_analysis_first_board_has_required_sections() -> None:
    rows = json.loads((RUN_ROOT / "18B_analysis_first_candidate_board.json").read_text(encoding="utf-8")).get("rows") or []
    sections = {str(row.get("section")) for row in rows}
    assert "TOP_PARTIALLY_PRICED_ANALYTICAL_CANDIDATES" in sections
    assert "TOP_UNPRICED_DEEP_ANALYTICAL_CANDIDATES" in sections
    assert "TOP_BET_BUILDER_CONCEPT_INPUTS" in sections


def test_unpriced_candidate_can_appear_in_board() -> None:
    rows = json.loads((RUN_ROOT / "18B_analysis_first_candidate_board.json").read_text(encoding="utf-8")).get("rows") or []
    assert any(row.get("section") == "TOP_UNPRICED_DEEP_ANALYTICAL_CANDIDATES" for row in rows)
