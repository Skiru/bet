from bet.tipsters.legacy_bridge import convert_legacy_pick_to_v2
from bet.tipsters.pipeline_adapter import to_legacy_pick


def _base_pick(**overrides):
    pick = {
        "source_site": "ZawodTyper",
        "source_id": "zawodtyper",
        "tipster_name": "Łukasz",
        "sport": "football",
        "event": "Śląsk Wrocław vs ŁKS Łódź",
        "home_team": "Śląsk Wrocław",
        "away_team": "ŁKS Łódź",
        "competition": "Ekstraklasa",
        "market": "Powyżej 2.5 bramki",
        "market_type": "statistical",
        "direction": "OVER",
        "odds": 1.87,
        "reasoning": "Śląsk w ostatnich 5 meczach regularnie tworzy sytuacje, a ŁKS traci dużo bramek.",
        "accuracy_pct": 67,
        "stats_cited": ["średnio 3.1 goals", "last 5 matches"],
        "fetch_time": "2026-07-04T13:30:00Z",
    }
    pick.update(overrides)
    return pick


def test_zawodtyper_legacy_pick_converts_to_v2():
    converted = convert_legacy_pick_to_v2(_base_pick())
    assert converted.source_id == "zawodtyper"
    assert converted.source_name == "ZawodTyper"
    assert converted.tipster_name == "Łukasz"
    assert converted.market_family == "goals"
    assert converted.direction == "OVER"


def test_accuracy_pct_is_preserved_as_source_metadata_not_confidence():
    converted = convert_legacy_pick_to_v2(_base_pick())
    assert converted.confidence_label == "source_claim"
    assert converted.valuable_signals["source_quality"] == ["accuracy_pct=67"]
    assert "accuracy_pct_reference_only" in converted.warnings


def test_odds_are_reference_only():
    converted = convert_legacy_pick_to_v2(_base_pick())
    assert converted.odds_decimal == 1.87
    assert "odds_reference_only" in converted.warnings


def test_forbidden_fields_are_dropped_with_warning():
    converted = convert_legacy_pick_to_v2(_base_pick(stake="2u", coupon={"legs": 2}, ev=0.12, final_bet=True))
    joined = " ".join(converted.warnings)
    assert "forbidden_fields_dropped:" in joined
    assert "stake" in joined
    assert "coupon" in joined
    assert "ev" in joined
    assert "final_bet" in joined


def test_polish_characters_are_preserved_in_event_and_teams():
    converted = convert_legacy_pick_to_v2(_base_pick())
    assert converted.event == "Śląsk Wrocław vs ŁKS Łódź"
    assert converted.home_team == "Śląsk Wrocław"
    assert converted.away_team == "ŁKS Łódź"


def test_missing_reasoning_yields_partial_quality():
    converted = convert_legacy_pick_to_v2(_base_pick(reasoning="", stats_cited=[]))
    assert converted.extraction_quality < 0.55
    assert "weak_or_empty_reasoning" in converted.warnings


def test_bridge_output_keeps_evidence_only_boundary():
    converted = convert_legacy_pick_to_v2(_base_pick())
    legacy = to_legacy_pick(converted)
    assert converted.valuable_signals["decision_boundary"] == ["evidence_only_not_a_bet"]
    assert legacy["decision_boundary"] == "evidence_only_not_a_bet"
