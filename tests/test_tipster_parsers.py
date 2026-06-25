from __future__ import annotations

import json
from pathlib import Path

from bet.pipeline.tipster_parsers import extract_zawodtyper_bets_payload, parse_zawodtyper_xhr_bets


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tipsters" / "zawodtyper_np_ajax_success.json"


def _classify_market(market: str, _context: str) -> str:
    lower = market.lower()
    return "statistical" if "over" in lower or "under" in lower else "outcome"


def _extract_direction(market: str, _context: str) -> str:
    lower = market.lower()
    if "over" in lower:
        return "OVER"
    if "under" in lower:
        return "UNDER"
    return "OTHER"


def _extract_stats_cited(text: str) -> list[str]:
    stats: list[str] = []
    if "corners" in text.lower():
        stats.append("corners")
    if "games" in text.lower():
        stats.append("games")
    return stats


def test_extract_zawodtyper_bets_payload_from_fixture():
    body = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = extract_zawodtyper_bets_payload(body)
    assert len(payload) == 4
    assert payload[0]["match_name"] == "Liverpool - Arsenal"


def test_parse_zawodtyper_xhr_bets_deduplicates_and_normalizes():
    body = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    picks = parse_zawodtyper_xhr_bets(
        extract_zawodtyper_bets_payload(body),
        now_iso="2026-06-25T08:00:00Z",
        classify_market=_classify_market,
        extract_direction=_extract_direction,
        extract_stats_cited=_extract_stats_cited,
    )

    assert len(picks) == 2
    football_pick = next(pick for pick in picks if pick["sport"] == "football")
    assert football_pick["tipster_name"] == "AnalystA"
    assert football_pick["accuracy_pct"] == 67
    assert football_pick["market"] == "Over 9.5 corners"
    assert football_pick["direction"] == "OVER"
    assert football_pick["stats_cited"] == ["corners"]
    assert "statistical support" in football_pick["reasoning"]


def test_extract_zawodtyper_payload_rejects_non_success():
    assert extract_zawodtyper_bets_payload({"success": False, "data": []}) == []
