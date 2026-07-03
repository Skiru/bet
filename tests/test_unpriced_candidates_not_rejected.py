import json
from pathlib import Path


RUN_ROOT = Path("reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def test_unpriced_candidates_remain_analysis_visible() -> None:
    candidates = json.loads((RUN_ROOT / "07_analytical_candidates.json").read_text(encoding="utf-8")).get("candidates") or []
    unpriced = [candidate for candidate in candidates if candidate.get("pricing_tier") == "UNPRICED_DEEP_ANALYTICAL"]
    assert unpriced, "Expected at least one recovered unpriced analytical candidate"
    assert any(candidate.get("confidence") in {"HIGH", "MEDIUM"} for candidate in unpriced)
    assert all(candidate.get("analysis_status") != "REJECTED" for candidate in unpriced)
