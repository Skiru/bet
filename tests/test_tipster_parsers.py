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


def test_parse_zawodtyper_xhr_bets_keeps_every_tipster_on_one_match():
    """Two tipsters on Liverpool - Arsenal must stay two picks.

    Collapsing them to one (the previous behaviour, which kept whichever bet
    had the longest reasoning) makes the consensus denominator 1 for every
    fixture, so "N of M tipsters agree" can never report more than 1 of 1.
    """
    body = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    picks = parse_zawodtyper_xhr_bets(
        extract_zawodtyper_bets_payload(body),
        now_iso="2026-06-25T08:00:00Z",
        classify_market=_classify_market,
        extract_direction=_extract_direction,
        extract_stats_cited=_extract_stats_cited,
    )

    # 4 payload items, one of which is comment_type="promo" and is dropped.
    assert len(picks) == 3
    liverpool = [p for p in picks if p["home_team"] == "Liverpool"]
    assert len(liverpool) == 2
    assert {p["tipster_name"] for p in liverpool} == {"AnalystA", "AnalystB"}

    football_pick = next(pick for pick in liverpool if pick["tipster_name"] == "AnalystA")
    assert football_pick["sport"] == "football"
    assert football_pick["accuracy_pct"] == 67
    assert football_pick["market"] == "Over 9.5 corners"
    assert football_pick["direction"] == "OVER"
    assert football_pick["stats_cited"] == ["corners"]
    assert "statistical support" in football_pick["reasoning"]


def test_parse_zawodtyper_xhr_bets_deduplicates_repeated_comment_ids():
    """Offset pagination overlaps, so the same bet can arrive twice."""
    body = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    bets = extract_zawodtyper_bets_payload(body)
    picks = parse_zawodtyper_xhr_bets(
        [*bets, *bets],
        now_iso="2026-06-25T08:00:00Z",
        classify_market=_classify_market,
        extract_direction=_extract_direction,
        extract_stats_cited=_extract_stats_cited,
    )
    assert len(picks) == 3


def test_parse_zawodtyper_xhr_bets_carries_match_date_and_flags():
    picks = parse_zawodtyper_xhr_bets(
        [
            {
                "comment_id": "77",
                "comment_type": "bet",
                "match_name": "Valencia - Real Betis",
                "content": "<p>Long enough reasoning to be preserved by the parser.</p>",
                "rate": "1.60",
                "discipline": "Piłka nożna",
                "type": "Poniżej 10,5 rzutów rożnych",
                "author_name": "AnalystD",
                "author_stats": {"bet_count": 20, "ratio": 0.6},
                "match_date": "25.08.2026",
                "hour": "21:00",
                "is_betbuilder": 1,
                "settled": 0,
            }
        ],
        now_iso="2026-08-25T08:00:00Z",
        classify_market=_classify_market,
        extract_direction=_extract_direction,
        extract_stats_cited=_extract_stats_cited,
    )
    assert len(picks) == 1
    pick = picks[0]
    assert pick["match_date"] == "2026-08-25"
    assert pick["kickoff_time"] == "21:00"
    assert pick["is_combo_source_flag"] is True
    assert pick["is_settled"] is False
    assert pick["tipster_bet_count"] == 20


def test_parse_zawodtyper_xhr_bets_drops_unparseable_match_date():
    picks = parse_zawodtyper_xhr_bets(
        [
            {
                "comment_id": "78",
                "comment_type": "bet",
                "match_name": "A Team - B Team",
                "content": "",
                "rate": "2.0",
                "discipline": "Piłka nożna",
                "type": "Over 9.5 corners",
                "author_name": "X",
                "author_stats": {},
                "match_date": "dzisiaj",
            }
        ],
        now_iso="2026-08-25T08:00:00Z",
        classify_market=_classify_market,
        extract_direction=_extract_direction,
        extract_stats_cited=_extract_stats_cited,
    )
    assert picks[0]["match_date"] is None


def test_extract_zawodtyper_payload_rejects_non_success():
    assert extract_zawodtyper_bets_payload({"success": False, "data": []}) == []
