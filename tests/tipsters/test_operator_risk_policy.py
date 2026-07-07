import pytest
from bet.tipsters.risk_policy import get_risk_policy, ComplianceTier, EvidenceUse
from bet.tipsters.pipeline_adapter import to_legacy_pick
from bet.tipsters.contracts import TipsterPick
from bet.tipsters.handoff import build_tipster_evidence_handoff


def test_risk_policy_mapping():
    # 1. Certified shadow source
    policy_cert = get_risk_policy("zawodtyper", is_certified=True)
    assert policy_cert.compliance_tier == ComplianceTier.CERTIFIED_SHADOW
    assert policy_cert.promotion_allowed is True
    assert not policy_cert.risk_warnings

    # 2. Operator risk source
    policy_risk = get_risk_policy("protipster", is_certified=False)
    assert policy_risk.compliance_tier == ComplianceTier.OPERATOR_RISK_PUBLIC_READ
    assert policy_risk.promotion_allowed is False
    assert "not_certified_shadow" in policy_risk.risk_warnings
    assert "operator_risk_public_read" in policy_risk.risk_warnings


def test_legacy_pick_enrichment():
    pick = TipsterPick(
        source_id="protipster",
        source_name="ProTipster PL",
        sport="football",
        event="Chelsea vs Arsenal",
        home_team="Chelsea",
        away_team="Arsenal",
        market="over 2.5",
        market_family="overunder",
        direction="OVER",
        line=2.5,
        odds_decimal=1.85,
        reasoning="Good form.",
        stats_cited=True,
        source_url="https://www.protipster.pl/",
    )
    legacy = to_legacy_pick(pick)
    assert legacy["compliance_tier"] == "operator_risk_public_read"
    assert legacy["evidence_use"] == "manual_review_only_or_low_trust_context"
    assert legacy["promotion_allowed"] is False
    assert "not_certified_shadow" in legacy["warnings"]


def test_tipster_evidence_handoff_risk_mix():
    # Setup mock consensus payload
    pick_cert = {
        "source_id": "zawodtyper",
        "source_site": "ZawodTyper",
        "market": "over 2.5",
        "reasoning": "A very long detailed narrative analysis for the match context.",
        "extraction_quality": 0.85,
        "agent_readiness": {"agent_use_decision": "USE_AS_CONTEXT", "normalized_event_key": "chelsea|arsenal"},
    }
    pick_risk = {
        "source_id": "protipster",
        "source_site": "ProTipster PL",
        "market": "over 2.5",
        "reasoning": "Short prediction.",
        "extraction_quality": 0.50,
        "agent_readiness": {"agent_use_decision": "USE_AS_CONTEXT", "normalized_event_key": "chelsea|arsenal"},
    }

    # Scenario A: Certified only
    payload_cert = {
        "total_picks": 1,
        "sources": [{"source_id": "zawodtyper"}],
        "consensus": [
            {
                "event": "Chelsea vs Arsenal",
                "sport": "football",
                "consensus_direction": "OVER",
                "total_tipsters": 1,
                "avg_extraction_quality": 0.85,
                "picks": [pick_cert],
            }
        ],
    }
    handoff_cert = build_tipster_evidence_handoff(payload_cert)
    assert handoff_cert["events"][0]["source_risk_mix"] == "certified_only"
    assert handoff_cert["events"][0]["evidence_quality"] == "HIGH"

    # Scenario B: Mixed
    payload_mixed = {
        "total_picks": 2,
        "sources": [{"source_id": "zawodtyper"}, {"source_id": "protipster"}],
        "consensus": [
            {
                "event": "Chelsea vs Arsenal",
                "sport": "football",
                "consensus_direction": "OVER",
                "total_tipsters": 2,
                "avg_extraction_quality": 0.85,  # Overall average is high
                "picks": [pick_cert, pick_risk],
            }
        ],
    }
    handoff_mixed = build_tipster_evidence_handoff(payload_mixed)
    assert handoff_mixed["events"][0]["source_risk_mix"] == "mixed"
    # Even though overall average quality is 0.85, since it's mixed and certified-only is 0.85, it's HIGH.
    # What if certified is low but overall is high because of risk?
    pick_cert_low = pick_cert.copy()
    pick_cert_low["extraction_quality"] = 0.50
    pick_risk_high = pick_risk.copy()
    pick_risk_high["extraction_quality"] = 0.95
    payload_mixed_low_cert = {
        "total_picks": 2,
        "sources": [{"source_id": "zawodtyper"}, {"source_id": "protipster"}],
        "consensus": [
            {
                "event": "Chelsea vs Arsenal",
                "sport": "football",
                "consensus_direction": "OVER",
                "total_tipsters": 2,
                "avg_extraction_quality": 0.80, # high average
                "picks": [pick_cert_low, pick_risk_high],
            }
        ],
    }
    handoff_mixed_low_cert = build_tipster_evidence_handoff(payload_mixed_low_cert)
    # The average certified quality is 0.50 (< 0.75), so evidence_quality is downgraded to MEDIUM!
    assert handoff_mixed_low_cert["events"][0]["evidence_quality"] == "MEDIUM"


def test_forbidden_actions_enforcement():
    pick_with_forbidden = {
        "source_id": "zawodtyper",
        "market": "over 2.5",
        "EV": 0.12,
        "stake": 5,
        "coupon": "some_coupon",
        "final_bet": "yes",
        "superbet_combined_odds": 3.4,
        "agent_readiness": {"agent_use_decision": "USE_AS_CONTEXT"},
    }
    payload = {
        "total_picks": 1,
        "consensus": [
            {
                "event": "Chelsea vs Arsenal",
                "sport": "football",
                "consensus_direction": "OVER",
                "picks": [pick_with_forbidden],
            }
        ],
    }
    handoff = build_tipster_evidence_handoff(payload)
    for forbidden in ["EV", "stake", "coupon", "final bet", "Superbet combined odds"]:
        assert forbidden not in handoff["events"][0]
        # And ensure the pick itself had them stripped
        for p in payload["consensus"][0]["picks"]:
            assert forbidden not in p
            assert forbidden.lower().replace(" ", "_") not in p
