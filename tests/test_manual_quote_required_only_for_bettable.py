import json
from pathlib import Path


RUN_ROOT = Path("tests/fixtures/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def test_manual_quote_is_required_only_for_bettable_promotion() -> None:
    report = json.loads((RUN_ROOT / "10_final_session_report.json").read_text(encoding="utf-8"))
    candidates = json.loads((RUN_ROOT / "07_analytical_candidates.json").read_text(encoding="utf-8")).get("candidates") or []
    assert report.get("MANUAL_QUOTE_ENTRY_REQUIRED_FOR_ANALYSIS") is False
    assert report.get("MANUAL_QUOTE_ENTRY_REQUIRED_FOR_BETTABLE") is True
    assert report.get("FINAL_COUPON_ALLOWED") is False
    assert all(candidate.get("bettable") is False for candidate in candidates)
    assert all(candidate.get("operator_quote_required_for_bettable") is True for candidate in candidates)
