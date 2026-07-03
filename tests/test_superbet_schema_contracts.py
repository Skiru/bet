from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "docs" / "pipeline" / "superbet_full_day_v3" / "schemas"


def load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_manual_quote_card_schema_blocks_final_without_human_quote() -> None:
    schema = load("manual_superbet_quote_card.schema.json")
    props = schema["properties"]
    assert props["operator"]["const"] == "Superbet"
    assert props["manual_quote_required"]["const"] is True
    assert props["combined_bookmaker_odds_computed"]["const"] is False
    assert props["final_coupon_ready"]["const"] is False
    assert "human_entered_quote" in props


def test_analytical_candidate_schema_keeps_analysis_and_bettable_separate() -> None:
    schema = load("analytical_candidate.schema.json")
    props = schema["properties"]
    assert "READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW" in props["analysis_status"]["enum"]
    assert props["manual_superbet_quote_required"]["const"] is True
    assert props["combined_bookmaker_odds_computed"]["const"] is False
    assert props["final_coupon_ready"]["const"] is False
    assert props["automated_placement_ready"]["const"] is False
