"""Checkpoint T5 tests: non-fabricated same-event Bet Builder and verified joint model scope."""
from __future__ import annotations

import pytest
from decimal import Decimal
from bet.builder.models import BuilderLegV1, JointModelScopeV1
from bet.builder.engine import generate_same_event_builders, compute_joint_builder_pricing, BetBuilderEngineError


def test_t5_unpromoted_joint_model_rejected():
    """Verify ANALYSIS_ONLY joint model rejects joint pricing computation."""
    unpromoted_jm = JointModelScopeV1(
        joint_model_id="UNPROMOTED_JM",
        model_version="1.0.0",
        sport="football",
        supported_market_family_pairs=(("corners", "shots"),),
        calibration_report_sha256="0" * 64,
        promotion_status="ANALYSIS_ONLY",
    )
    l1 = BuilderLegV1(
        leg_id="L1", canonical_event_id="E1", sport="football",
        competition="EPL", home_team="A", away_team="B",
        market_family="corners", selection="over", calibrated_probability=0.5,
        fair_odds=Decimal("2.0"), minimum_acceptable_odds=Decimal("2.1")
    )
    l2 = BuilderLegV1(
        leg_id="L2", canonical_event_id="E1", sport="football",
        competition="EPL", home_team="A", away_team="B",
        market_family="shots", selection="over", calibrated_probability=0.5,
        fair_odds=Decimal("2.0"), minimum_acceptable_odds=Decimal("2.1")
    )

    with pytest.raises(BetBuilderEngineError, match="is not PRICING_ELIGIBLE"):
        compute_joint_builder_pricing(l1, l2, unpromoted_jm)


def test_t5_unsupported_scope_yields_rejection_preserving_singles():
    """Verify absence of promoted joint model records NO_JOINT_MODEL_SCOPE rejection."""
    l1 = BuilderLegV1(
        leg_id="L1", canonical_event_id="E1", sport="football",
        competition="EPL", home_team="A", away_team="B",
        market_family="corners", selection="over", calibrated_probability=0.5,
        fair_odds=Decimal("2.0"), minimum_acceptable_odds=Decimal("2.1")
    )
    l2 = BuilderLegV1(
        leg_id="L2", canonical_event_id="E1", sport="football",
        competition="EPL", home_team="A", away_team="B",
        market_family="shots", selection="over", calibrated_probability=0.5,
        fair_odds=Decimal("2.0"), minimum_acceptable_odds=Decimal("2.1")
    )

    idea_groups, rejections = generate_same_event_builders([l1, l2], [])
    assert len(idea_groups) == 0
    assert len(rejections) == 1
    assert rejections[0].reason_code == "NO_JOINT_MODEL_SCOPE"
