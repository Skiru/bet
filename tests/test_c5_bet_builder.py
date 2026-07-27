"""C5 acceptance tests for same-event Bet Builder, minimum odds, and human quote flow."""
from __future__ import annotations

import pytest
from decimal import Decimal
from bet.builder.models import (
    BuilderLegV1,
    JointModelScopeV1,
    SameEventBuilderCandidateV1,
)
from bet.builder.engine import (
    BetBuilderEngineError,
    validate_leg_compatibility,
    compute_joint_builder_pricing,
    generate_same_event_builders,
)


def test_corners_and_shots_same_event_builder():
    """Verify valid corners + shots pair produces an S8 idea group with non-null fair and minimum odds."""
    leg_corners = BuilderLegV1(
        leg_id="LEG_001",
        canonical_event_id="EVT_FB_ARS_CHE",
        sport="football",
        market_family="corners",
        selection="over",
        line=7.5,
        calibrated_probability=0.60,
        fair_odds=Decimal("1.6667"),
        minimum_acceptable_odds=Decimal("1.8103"),
    )
    leg_shots = BuilderLegV1(
        leg_id="LEG_002",
        canonical_event_id="EVT_FB_ARS_CHE",
        sport="football",
        market_family="shots",
        selection="over",
        line=5.5,
        calibrated_probability=0.55,
        fair_odds=Decimal("1.8182"),
        minimum_acceptable_odds=Decimal("1.9811"),
    )

    joint_model = JointModelScopeV1(
        joint_model_id="JOINT_FOOTBALL_CORNERS_SHOTS_V1",
        model_version="1.0.0",
        sport="football",
        supported_market_family_pairs=(("corners", "shots"),),
        calibration_report_sha256="calib_corners_shots_sha256",
        promotion_status="PRICING_ELIGIBLE",
    )

    idea_groups, rejections = generate_same_event_builders(
        legs=[leg_corners, leg_shots],
        joint_models=[joint_model],
    )

    assert len(idea_groups) == 1
    assert len(rejections) == 0

    group = idea_groups[0]
    assert group.canonical_event_id == "EVT_FB_ARS_CHE"
    assert len(group.builder_candidates) == 1

    candidate = group.builder_candidates[0]
    assert candidate.visible_superbet_combined_odds is None  # MUST be None before S9
    assert candidate.joint_probability.fair_combined_odds > Decimal("1.0")
    assert candidate.joint_probability.minimum_acceptable_combined_odds > candidate.joint_probability.fair_combined_odds


def test_unsupported_pair_records_rejection():
    """Verify pair without joint model scope is rejected with NO_JOINT_MODEL_SCOPE."""
    leg_1 = BuilderLegV1(
        leg_id="LEG_001",
        canonical_event_id="EVT_FB_001",
        sport="football",
        market_family="corners",
        selection="over",
        calibrated_probability=0.60,
        fair_odds=Decimal("1.6667"),
        minimum_acceptable_odds=Decimal("1.8103"),
    )
    leg_2 = BuilderLegV1(
        leg_id="LEG_002",
        canonical_event_id="EVT_FB_001",
        sport="football",
        market_family="unsupported_custom_family",
        selection="over",
        calibrated_probability=0.50,
        fair_odds=Decimal("2.0000"),
        minimum_acceptable_odds=Decimal("2.1875"),
    )

    joint_model = JointModelScopeV1(
        joint_model_id="JOINT_FOOTBALL_CORNERS_SHOTS_V1",
        model_version="1.0.0",
        sport="football",
        supported_market_family_pairs=(("corners", "shots"),),
        calibration_report_sha256="calib_corners_shots_sha256",
    )

    idea_groups, rejections = generate_same_event_builders(
        legs=[leg_1, leg_2],
        joint_models=[joint_model],
    )

    assert len(idea_groups) == 0
    assert len(rejections) == 1
    assert rejections[0].reason_code == "NO_JOINT_MODEL_SCOPE"


def test_duplicate_market_family_rejected():
    """Verify two legs with the same market family on the same event are rejected."""
    leg_1 = BuilderLegV1(
        leg_id="LEG_001",
        canonical_event_id="EVT_001",
        sport="football",
        market_family="corners",
        selection="over_7.5",
        calibrated_probability=0.60,
        fair_odds=Decimal("1.6667"),
        minimum_acceptable_odds=Decimal("1.8103"),
    )
    leg_2 = BuilderLegV1(
        leg_id="LEG_002",
        canonical_event_id="EVT_001",
        sport="football",
        market_family="corners",
        selection="over_9.5",
        calibrated_probability=0.40,
        fair_odds=Decimal("2.5000"),
        minimum_acceptable_odds=Decimal("2.7500"),
    )

    compat = validate_leg_compatibility(leg_1, leg_2)
    assert not compat.compatible
    assert compat.rejection_reason == "DUPLICATE_MARKET_FAMILY"
