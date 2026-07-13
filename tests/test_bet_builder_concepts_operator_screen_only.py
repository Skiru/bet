import json
from pathlib import Path


RUN_ROOT = Path("tests/fixtures/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def test_bet_builder_concepts_remain_operator_screen_only() -> None:
    concepts = json.loads((RUN_ROOT / "18C_superbet_bet_builder_concepts.json").read_text(encoding="utf-8")).get("concepts") or []
    assert concepts
    for concept in concepts:
        assert concept.get("combined_odds_status") == "OPERATOR_SCREEN_ONLY"
        assert concept.get("combined_bookmaker_odds_computed") is False
        assert concept.get("bettable") is False
