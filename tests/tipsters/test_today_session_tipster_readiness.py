import json
from pathlib import Path
import pytest

from bet.tipsters.contracts import TipsterPick, RawDocument
from bet.tipsters.agent_readiness import analyze_pick_readiness
from bet.tipsters.source_registry import CERTIFIED_SHADOW_SOURCE_IDS
from bet.tipsters.risk_policy import get_risk_policy, ComplianceTier
from bet.tipsters.handoff import build_tipster_evidence_handoff
from bet.tipsters.pipeline_adapter import to_legacy_pick


def test_certified_sources_set():
    # 9. source set for certified session equals zawodtyper + typersi.
    assert sorted(CERTIFIED_SHADOW_SOURCE_IDS) == ["typersi", "zawodtyper"]


def test_typersi_label_behavior():
    # 5. Typersi gets allowed label USE_AS_CONTEXT / USE_AS_MARKET_SANITY_CHECK, not USE_AS_QUALITATIVE_REASONING.
    typersi_pick = TipsterPick(
        source_id="typersi",
        source_name="Typersi",
        sport="football",
        event="Arsenal vs Chelsea",
        home_team="Arsenal",
        away_team="Chelsea",
        market="1",
        market_family="winner",
        direction="HOME",
        odds_decimal=1.9,
        reasoning="",  # Typersi has empty/static table reasoning
        tipster_name="TableTyper",
        extraction_quality=0.8
    )
    analysis = analyze_pick_readiness(typersi_pick)
    # Typersi has empty reasoning, so it is filtered to NEEDS_MANUAL_REVIEW or USE_AS_CONTEXT, NOT USE_AS_QUALITATIVE_REASONING.
    assert analysis["agent_use_decision"] != "USE_AS_QUALITATIVE_REASONING"
    assert analysis["agent_use_decision"] in {"USE_AS_CONTEXT", "USE_AS_MARKET_SANITY_CHECK", "NEEDS_MANUAL_REVIEW"}


def test_zawodtyper_qualitative_label_behavior():
    zawodtyper_pick = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="Arsenal vs Chelsea",
        home_team="Arsenal",
        away_team="Chelsea",
        market="1",
        market_family="winner",
        direction="HOME",
        odds_decimal=1.9,
        reasoning="This is some premium community analysis exceeding thirty characters.",
        tipster_name="ExpertTyper",
        extraction_quality=0.8
    )
    analysis = analyze_pick_readiness(zawodtyper_pick)
    assert analysis["agent_use_decision"] in {"USE_AS_CONTEXT", "USE_AS_QUALITATIVE_REASONING"}


def test_operator_risk_disabled_by_default():
    # 6. operator-risk is disabled by default (requires is_certified=False in get_risk_policy to flag operator risk)
    policy = get_risk_policy("protipster", is_certified=False)
    assert policy.compliance_tier == ComplianceTier.OPERATOR_RISK_PUBLIC_READ
    assert policy.operator_ack_required is True
    assert "MANUAL_REVIEW_ONLY" in policy.allowed_actions
    assert "not_certified_shadow" in policy.risk_warnings


def test_agent_readiness_in_legacy_pick():
    # 4. all picks have agent_readiness.
    pick = TipsterPick(
        source_id="typersi",
        source_name="Typersi",
        sport="football",
        event="Arsenal vs Chelsea",
        home_team="Arsenal",
        away_team="Chelsea",
        market="1",
        market_family="winner",
        direction="HOME",
        odds_decimal=1.9,
        reasoning="",
        tipster_name="TableTyper",
        extraction_quality=0.8
    )
    legacy = to_legacy_pick(pick)
    assert "agent_readiness" in legacy
    assert legacy["agent_readiness"]["source_id"] == "typersi"


def test_handoff_schema_and_happy_path():
    # 1. certified shadow run outputs handoff path.
    # 2. handoff has schema tipster_evidence_handoff_v1.
    # 3. handoff events > 0 in mocked happy path.
    mock_payload = {
        "total_picks": 2,
        "sources": [
            {"source_id": "zawodtyper", "pick_count": 1},
            {"source_id": "typersi", "pick_count": 1}
        ],
        "consensus": [
            {
                "event": "Arsenal vs Chelsea",
                "sport": "football",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "total_tipsters": 2,
                "tipster_sources": ["ZawodTyper", "Typersi"],
                "consensus_market": "1",
                "consensus_direction": "HOME",
                "agreement_pct": 100.0,
                "has_reasoning": True,
                "evidence_fields": ["winner"],
                "avg_extraction_quality": 0.8,
                "pipeline_usage": ["s3_factor_discovery"],
                "agent_readiness_summary": {
                    "all_evidence_only": True,
                    "decisions": ["USE_AS_CONTEXT", "NEEDS_MANUAL_REVIEW"],
                },
                "picks": [
                    {
                        "source_id": "zawodtyper",
                        "source_name": "ZawodTyper",
                        "market": "1",
                        "reasoning": "This is a qualitative reasoning that has more than thirty characters.",
                        "agent_readiness": {
                            "normalized_event_key": "arsenal|chelsea",
                            "agent_use_decision": "USE_AS_CONTEXT"
                        }
                    },
                    {
                        "source_id": "typersi",
                        "source_name": "Typersi",
                        "market": "1",
                        "reasoning": "",
                        "agent_readiness": {
                            "normalized_event_key": "arsenal|chelsea",
                            "agent_use_decision": "NEEDS_MANUAL_REVIEW"
                        }
                    }
                ]
            }
        ]
    }
    handoff = build_tipster_evidence_handoff(mock_payload)
    assert handoff["schema_version"] == "tipster_evidence_handoff_v1"
    assert len(handoff["events"]) > 0
    assert handoff["events"][0]["normalized_event_key"] == "arsenal|chelsea"


def test_documentation_compliance():
    # 7. daily session prompt docs mention tipsters as mandatory evidence.
    # 8. docs forbid EV/stake/coupon/final bet/Superbet combined odds.
    contract_path = Path("docs/pipeline/Today Session Tipster Evidence Contract.md")
    runbook_path = Path("docs/pipeline/Full Day Session Runbook.md")

    assert contract_path.exists()
    assert runbook_path.exists()

    contract_content = contract_path.read_text(encoding="utf-8")
    runbook_content = runbook_path.read_text(encoding="utf-8")

    # Verify mandatory evidence mentions
    assert "s2_tipsters_shadow_evidence.py" in contract_content
    assert "s2_tipsters_shadow_evidence.py" in runbook_content
    assert "mandatory" in contract_content.lower() or "must run" in contract_content.lower()
    assert "mandatory" in runbook_content.lower() or "must execute" in runbook_content.lower()

    # Verify forbidden betting fields
    for forbidden in ["EV", "stake", "coupon", "final bet", "Superbet combined odds"]:
        assert forbidden in contract_content
        assert forbidden in runbook_content
