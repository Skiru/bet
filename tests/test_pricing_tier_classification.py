import json
from pathlib import Path


RUN_ROOT = Path("tests/fixtures/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def test_unpriced_and_partial_candidates_have_price_gate_blocks() -> None:
    candidates = json.loads((RUN_ROOT / "07_analytical_candidates.json").read_text(encoding="utf-8")).get("candidates") or []
    partial = next(candidate for candidate in candidates if candidate.get("pricing_tier") == "PARTIALLY_PRICED_ANALYTICAL")
    unpriced = next(candidate for candidate in candidates if candidate.get("pricing_tier") == "UNPRICED_DEEP_ANALYTICAL")

    assert partial.get("bettable") is False
    assert partial.get("bettable_status") == "NOT_BETTABLE_WAITING_FOR_OPERATOR_ODDS"

    assert unpriced.get("ev_status") == "EV_BLOCKED_UNTIL_OPERATOR_ODDS"
    assert unpriced.get("stake_status") == "STAKE_BLOCKED_UNTIL_PRICE_GATE"
    assert unpriced.get("manual_quote_required_for_bettable") is True
