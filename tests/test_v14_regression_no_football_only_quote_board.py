from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run_id = os.environ.get("SUPERBET_SESSION_RUN_ID", "FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V16")
RUN_ROOT = ROOT / "reports" / "pipeline_runs" / run_id


def test_v14_regression_no_football_only_quote_board() -> None:
    path = RUN_ROOT / "10_final_session_report.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    by_sport = data.get("quote_cards_by_sport") or data.get("QUOTE_CARDS_BY_SPORT") or {}
    
    # Assert that there are non-football quote cards in the final board
    non_football_sports = [s for s in by_sport if s != "football"]
    assert len(non_football_sports) > 0
    assert by_sport.get("tennis", 0) > 0
    assert by_sport.get("basketball", 0) > 0
