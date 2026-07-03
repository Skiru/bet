import json
from pathlib import Path


SOURCE_ROOT = Path("reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V17_1")
RUN_ROOT = Path("reports/pipeline_runs/FULL_DAY_SESSION_20260703_SUPERBET_ANALYSIS_FIRST_V18_1")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v18_keeps_v17_lineage_and_wimbledon_counts() -> None:
    source_report = _load(SOURCE_ROOT / "10_final_session_report.json")
    report = _load(RUN_ROOT / "10_final_session_report.json")
    assert report.get("SOURCE_RUN_ID") == SOURCE_ROOT.name
    assert report.get("INPUT_RUN_ID") == SOURCE_ROOT.name
    assert report.get("WIMBLEDON_QUOTE_CARDS") == source_report.get("WIMBLEDON_QUOTE_CARDS")
    assert report.get("QUOTE_CARDS_BY_SPORT") == source_report.get("QUOTE_CARDS_BY_SPORT")


def test_v18_expands_analysis_without_creating_bettable_output() -> None:
    source_candidates = (_load(SOURCE_ROOT / "07_analytical_candidates.json").get("candidates") or [])
    report = _load(RUN_ROOT / "10_final_session_report.json")
    assert int(report.get("TOTAL_ANALYTICAL_CANDIDATES") or 0) >= len(source_candidates)
    assert report.get("BETTABLE_COUNT") == 0
    assert report.get("COMBINED_BOOKMAKER_ODDS_COMPUTED") is False
