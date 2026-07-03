import json
from pathlib import Path


RUN_ROOT = Path("reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def test_tipster_context_remains_secondary_analysis_context() -> None:
    context = json.loads((RUN_ROOT / "18E_tipster_analysis_context.json").read_text(encoding="utf-8"))
    candidates = json.loads((RUN_ROOT / "07_analytical_candidates.json").read_text(encoding="utf-8")).get("candidates") or []
    assert context.get("tipster_context_status") == "ATTEMPTED_NO_MATCHES"
    assert context.get("tipster_signal") is None
    assert all(candidate.get("tipster_context_status") == "ATTEMPTED_NO_MATCHES" for candidate in candidates)
    assert all(candidate.get("tipster_signal") is None for candidate in candidates)
