"""Tests for agent readiness and match resolution identity."""
from __future__ import annotations

import json
from bet.tipsters.contracts import TipsterPick
from bet.tipsters.agent_readiness import (
    split_participants,
    generate_event_identity,
    analyze_pick_readiness,
)


def test_split_participants_football_vs():
    res = split_participants("Meksyk vs Anglia", "football")
    assert res == ["Meksyk", "Anglia"]


def test_split_participants_tennis_v():
    res = split_participants("Dimitrov v Fery", "tennis")
    assert res == ["Dimitrov", "Fery"]


def test_split_participants_with_dash():
    res = split_participants("Barcelona - Real Madryt", "football")
    assert res == ["Barcelona", "Real Madryt"]


def test_reserves_and_roman_numerals_not_stripped():
    res = split_participants("Austin FC II vs Colorado Rapids II", "football")
    assert res == ["Austin FC II", "Colorado Rapids II"]


def test_polish_characters_preserved_in_splitting():
    res = split_participants("Siatkówka vs Piłka Ręczna", "volleyball")
    assert "Siatkówka" in res
    assert "Piłka Ręczna" in res


def test_order_insensitive_event_key():
    id1 = generate_event_identity("Meksyk vs Anglia", "football")
    id2 = generate_event_identity("Anglia vs Meksyk", "football")
    assert id1["normalized_event_key"] == id2["normalized_event_key"]
    assert "order_reversed" in id1["ambiguity_flags"]
    assert "order_reversed" not in id2["ambiguity_flags"]


def test_tennis_double_barreled_names():
    res = split_participants("Jean-Julien Rojer vs Horia Tecau", "tennis")
    assert res == ["Jean-Julien Rojer", "Horia Tecau"]


def test_ambiguous_event_splitting():
    res = generate_event_identity("SingleTeamNoSeparator", "football")
    assert res["requires_match_resolution"] is True
    assert "ambiguous_split" in res["ambiguity_flags"]


def test_analyze_pick_readiness_fully_compliant():
    pick = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="Meksyk vs Anglia",
        home_team="Meksyk",
        away_team="Anglia",
        market="over 2.5 goals",
        market_family="goals",
        direction="OVER",
        line=2.5,
        odds_decimal=1.85,
        reasoning="This is a fully valid reasoning of more than thirty characters, making it contextually useful.",
        tipster_name="ExpertTyper",
        extraction_quality=0.85,
    )
    analysis = analyze_pick_readiness(pick)
    assert analysis["agent_use_decision"] == "USE_AS_CONTEXT"
    assert analysis["confidence_in_extraction"] == "HIGH"
    assert analysis["can_influence_pipeline"] is True
    assert "EV" in analysis["forbidden_actions"]
    assert "S3 contextual cross-check" in analysis["allowed_pipeline_stages"]


def test_analyze_pick_readiness_low_quality():
    pick = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="Meksyk vs Anglia",
        home_team="Meksyk",
        away_team="Anglia",
        market="over 2.5 goals",
        market_family="goals",
        direction="OVER",
        line=2.5,
        odds_decimal=1.85,
        reasoning="Valid reasoning, but quality is artificially set below threshold.",
        tipster_name="ExpertTyper",
        extraction_quality=0.35,  # below 0.45
    )
    analysis = analyze_pick_readiness(pick)
    assert analysis["agent_use_decision"] == "REJECT_LOW_QUALITY"
    assert analysis["confidence_in_extraction"] == "LOW"
    assert analysis["can_influence_pipeline"] is False


def test_analyze_pick_readiness_short_reasoning():
    pick = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="Meksyk vs Anglia",
        home_team="Meksyk",
        away_team="Anglia",
        market="over 2.5 goals",
        market_family="goals",
        direction="OVER",
        line=2.5,
        odds_decimal=1.85,
        reasoning="Too short.",  # < 30 chars
        tipster_name="ExpertTyper",
        extraction_quality=0.75,
    )
    analysis = analyze_pick_readiness(pick)
    assert analysis["agent_use_decision"] == "NEEDS_MANUAL_REVIEW"
    assert analysis["confidence_in_extraction"] == "MEDIUM"


def test_analyze_pick_readiness_garbage_or_promo():
    pick = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="Zawód Typer Regulamin",
        home_team="Zawód Typer",
        away_team="Regulamin",
        market="N/A",
        market_family="unknown",
        direction="OTHER",
        odds_decimal=None,
        reasoning="This is some promotional text or rules block.",
        tipster_name="Admin",
        extraction_quality=0.75,
    )
    analysis = analyze_pick_readiness(pick)
    assert analysis["agent_use_decision"] == "REJECT_GARBAGE"
    assert analysis["confidence_in_extraction"] == "LOW"
