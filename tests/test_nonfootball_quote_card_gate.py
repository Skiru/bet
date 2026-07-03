from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run_id = os.environ.get("SUPERBET_SESSION_RUN_ID", "FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V16")
RUN_ROOT = ROOT / "reports" / "pipeline_runs" / run_id


def test_quote_cards_exist_for_nonfootball_sports() -> None:
    path = RUN_ROOT / "09_manual_superbet_quote_cards.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    quote_cards = data.get("quote_cards") or []
    sports = {str(card.get("sport")).lower() for card in quote_cards}
    assert "tennis" in sports
    assert "basketball" in sports
