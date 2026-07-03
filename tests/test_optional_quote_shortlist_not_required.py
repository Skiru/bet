import json
from pathlib import Path


RUN_ROOT = Path("reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def test_optional_quote_shortlist_is_scoped_and_not_required_for_analysis() -> None:
    report = json.loads((RUN_ROOT / "10_final_session_report.json").read_text(encoding="utf-8"))
    shortlist = json.loads((RUN_ROOT / "18D_optional_superbet_quote_check_shortlist.json").read_text(encoding="utf-8")).get("rows") or []
    assert report.get("MANUAL_QUOTE_ENTRY_REQUIRED_FOR_ANALYSIS") is False
    assert 10 <= len(shortlist) <= 30
    assert all(row.get("manual_quote_entry_required_for_analysis") is False for row in shortlist)
