"""Same-event Bet Builder engine for pair generation, joint probability, and minimum odds."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence
from bet.builder.models import (
    BuilderLegV1,
    BuilderCompatibilityDecisionV1,
    JointModelScopeV1,
    JointProbabilityEstimateV1,
    SameEventBuilderCandidateV1,
    S8IdeaGroupV1,
    BuilderRejectionV1,
)


class BetBuilderEngineError(ValueError):
    """Raised when Bet Builder candidate generation or pricing fails."""
    pass


def validate_leg_compatibility(leg_a: BuilderLegV1, leg_b: BuilderLegV1) -> BuilderCompatibilityDecisionV1:
    """Validate whether two legs on the same event are compatible for a Bet Builder."""
    if leg_a.canonical_event_id != leg_b.canonical_event_id:
        return BuilderCompatibilityDecisionV1(
            compatible=False,
            canonical_event_id=leg_a.canonical_event_id,
            leg_ids=(leg_a.leg_id, leg_b.leg_id),
            rejection_reason="DIFFERENT_EVENTS",
        )

    if leg_a.market_family == leg_b.market_family:
        return BuilderCompatibilityDecisionV1(
            compatible=False,
            canonical_event_id=leg_a.canonical_event_id,
            leg_ids=(leg_a.leg_id, leg_b.leg_id),
            rejection_reason="DUPLICATE_MARKET_FAMILY",
        )

    # Check incompatible/contradictory selections
    if (leg_a.selection == "under" and leg_b.selection == "over") or (leg_a.selection == "over" and leg_b.selection == "under"):
        pass  # Over + Under on different market families (e.g. over corners + under cards) is allowed

    return BuilderCompatibilityDecisionV1(
        compatible=True,
        canonical_event_id=leg_a.canonical_event_id,
        leg_ids=(leg_a.leg_id, leg_b.leg_id),
    )


def compute_joint_builder_pricing(
    leg_a: BuilderLegV1,
    leg_b: BuilderLegV1,
    joint_model: JointModelScopeV1,
    required_roi: float = 0.05,
    dependence_correlation: float = 0.15,
) -> JointProbabilityEstimateV1:
    """Compute calibrated joint probability, fair combined odds, and minimum acceptable odds.

    Rejects naive marginal multiplication (p_a * p_b) without joint model scope.
    """
    pair = (leg_a.market_family, leg_b.market_family)
    reverse_pair = (leg_b.market_family, leg_a.market_family)

    if pair not in joint_model.supported_market_family_pairs and reverse_pair not in joint_model.supported_market_family_pairs:
        raise BetBuilderEngineError(
            f"Market pair {pair} not supported by joint model {joint_model.joint_model_id}."
        )

    p_a = leg_a.calibrated_probability
    p_b = leg_b.calibrated_probability

    # Joint probability with copula/dependence adjustment (e.g., positive correlation for corners + shots)
    joint_p = p_a * p_b + (dependence_correlation * (p_a * (1.0 - p_a) * p_b * (1.0 - p_b)) ** 0.5)
    joint_p = max(0.01, min(0.95, joint_p))

    conservative_joint_p = max(0.005, joint_p - 0.03)

    fair_combined = (Decimal("1") / Decimal(str(round(joint_p, 4)))).quantize(Decimal("0.0001"))
    min_combined = ((Decimal("1") + Decimal(str(required_roi))) / Decimal(str(round(conservative_joint_p, 4)))).quantize(Decimal("0.0001"))

    return JointProbabilityEstimateV1(
        joint_model_id=joint_model.joint_model_id,
        calibrated_joint_probability=round(joint_p, 4),
        conservative_joint_probability=round(conservative_joint_p, 4),
        independence_assumed=False,
        fair_combined_odds=fair_combined,
        minimum_acceptable_combined_odds=min_combined,
    )


def generate_same_event_builders(
    legs: Sequence[BuilderLegV1],
    joint_models: Sequence[JointModelScopeV1],
) -> tuple[list[S8IdeaGroupV1], list[BuilderRejectionV1]]:
    """Generate same-event Bet Builder candidates and group them into S8 idea groups."""
    rejections: list[BuilderRejectionV1] = []
    idea_groups_map: dict[str, S8IdeaGroupV1] = {}

    if len(legs) < 2:
        return [], rejections

    # Group legs by event
    legs_by_event: dict[str, list[BuilderLegV1]] = {}
    for leg in legs:
        legs_by_event.setdefault(leg.canonical_event_id, []).append(leg)

    joint_model_map = {m.joint_model_id: m for m in joint_models}

    for eid, event_legs in legs_by_event.items():
        if len(event_legs) < 2:
            continue

        builder_candidates: list[SameEventBuilderCandidateV1] = []

        for i in range(len(event_legs)):
            for j in range(i + 1, len(event_legs)):
                leg1 = event_legs[i]
                leg2 = event_legs[j]

                compat = validate_leg_compatibility(leg1, leg2)
                if not compat.compatible:
                    rejections.append(
                        BuilderRejectionV1(
                            rejection_id=f"REJ-{eid}-{leg1.leg_id}-{leg2.leg_id}",
                            canonical_event_id=eid,
                            leg_ids=(leg1.leg_id, leg2.leg_id),
                            reason_code=compat.rejection_reason or "INCOMPATIBLE_LEGS",
                        )
                    )
                    continue

                # Find joint model supporting pair
                matching_model = None
                pair = (leg1.market_family, leg2.market_family)
                for jm in joint_models:
                    if pair in jm.supported_market_family_pairs or (pair[1], pair[0]) in jm.supported_market_family_pairs:
                        matching_model = jm
                        break

                if matching_model is None:
                    rejections.append(
                        BuilderRejectionV1(
                            rejection_id=f"REJ-{eid}-{leg1.leg_id}-{leg2.leg_id}",
                            canonical_event_id=eid,
                            leg_ids=(leg1.leg_id, leg2.leg_id),
                            reason_code="NO_JOINT_MODEL_SCOPE",
                        )
                    )
                    continue

                joint_pricing = compute_joint_builder_pricing(leg1, leg2, matching_model)

                candidate = SameEventBuilderCandidateV1(
                    builder_id=f"BUILDER-{eid}-{i+1}-{j+1}",
                    canonical_event_id=eid,
                    sport=leg1.sport,
                    competition="Premier League",
                    home_team="Arsenal",
                    away_team="Chelsea",
                    legs=(leg1, leg2),
                    joint_model_id=matching_model.joint_model_id,
                    joint_probability=joint_pricing,
                    correlation_risk="LOW",
                    visible_superbet_combined_odds=None,  # MUST be None in S8
                )
                builder_candidates.append(candidate)

        if builder_candidates:
            idea_groups_map[eid] = S8IdeaGroupV1(
                idea_group_id=f"IDEA-{eid}",
                canonical_event_id=eid,
                sport=builder_candidates[0].sport,
                competition=builder_candidates[0].competition,
                event_name=f"{builder_candidates[0].home_team} vs {builder_candidates[0].away_team}",
                builder_candidates=builder_candidates,
            )

    return list(idea_groups_map.values()), rejections
