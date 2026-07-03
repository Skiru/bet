from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run_id = os.environ.get("SUPERBET_SESSION_RUN_ID", "FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V16")
RUN_ROOT = ROOT / "reports" / "pipeline_runs" / run_id


def test_quote_card_distribution() -> None:
    path = RUN_ROOT / "10_final_session_report.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    distribution = data.get("quote_cards_by_sport") or data.get("QUOTE_CARDS_BY_SPORT") or {}
    assert distribution.get("tennis", 0) > 0
    assert distribution.get("basketball", 0) > 0
