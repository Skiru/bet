from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run_id = os.environ.get("SUPERBET_SESSION_RUN_ID", "FULL_DAY_SESSION_20260703_SUPERBET_PRODUCTION_V16")
RUN_ROOT = ROOT / "reports" / "pipeline_runs" / run_id


def test_no_quote_card_inflation() -> None:
    path = RUN_ROOT / "09_manual_superbet_quote_cards.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    cards = data.get("quote_cards") or []

    sigs = []
    for card in cards:
        sig = (
            card.get("event_id"),
            card.get("market_family"),
            card.get("selection"),
            card.get("line"),
        )
        sigs.append(sig)

    assert len(sigs) == len(set(sigs))
