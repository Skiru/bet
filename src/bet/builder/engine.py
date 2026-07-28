"""Engine for Bet Builder calculations and joint pricing."""
from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence

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
    """Exception raised for errors in Bet Builder pricing or calculation."""
    pass


def validate_leg_compatibility(*legs: Any) -> BuilderCompatibilityDecisionV1:
    """Validate whether legs can form a valid Bet Builder combination."""
    if len(legs) == 1 and isinstance(legs[0], (list, tuple)):
        legs_seq = legs[0]
    else:
        legs_seq = legs

    if len(legs_seq) < 2:
        return BuilderCompatibilityDecisionV1(
            compatible=False,
            canonical_event_id=getattr(legs_seq[0], "canonical_event_id", "") if legs_seq else "",
            leg_ids=tuple(getattr(l, "leg_id", "") for l in legs_seq),
            rejection_reason="INSUFFICIENT_LEGS",
        )

    event_ids = {getattr(l, "canonical_event_id", None) for l in legs_seq}
    if len(event_ids) > 1:
        return BuilderCompatibilityDecisionV1(
            compatible=False,
            canonical_event_id=getattr(legs_seq[0], "canonical_event_id", ""),
            leg_ids=tuple(getattr(l, "leg_id", "") for l in legs_seq),
            rejection_reason="DIFFERENT_EVENTS_FORBIDDEN",
        )

    market_fams = [getattr(l, "market_family", "").lower() for l in legs_seq]
    if len(market_fams) != len(set(market_fams)):
        return BuilderCompatibilityDecisionV1(
            compatible=False,
            canonical_event_id=getattr(legs_seq[0], "canonical_event_id", ""),
            leg_ids=tuple(getattr(l, "leg_id", "") for l in legs_seq),
            rejection_reason="DUPLICATE_MARKET_FAMILY",
        )

    return BuilderCompatibilityDecisionV1(
        compatible=True,
        canonical_event_id=getattr(legs_seq[0], "canonical_event_id", ""),
        leg_ids=tuple(getattr(l, "leg_id", "") for l in legs_seq),
        rejection_reason=None,
    )


def calculate_combined_odds(
    leg_probabilities: Sequence[float],
    joint_model: Any = None,
) -> dict[str, Any]:
    """Calculate combined odds for Bet Builder legs.

    Rejects unless passed a resolved joint package that computes the conjunction.
    Does NOT calculate marginal multiplication (p_a * p_b).
    """
    if joint_model is None or getattr(joint_model, "is_eligible", False) == False or getattr(joint_model, "is_pricing_eligible", lambda: False)() == False:
        return {
            "combined_odds": None,
            "rejection_reason": "NO_VERIFIED_JOINT_MODEL_SCOPE",
        }
    if hasattr(joint_model, "compute_conjunction"):
        return joint_model.compute_conjunction(leg_probabilities)
    return {
        "combined_odds": None,
        "rejection_reason": "NO_VERIFIED_JOINT_MODEL_SCOPE",
    }


def compute_joint_builder_pricing(
    *args: Any,
    joint_model: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compute joint builder pricing for candidates or legs.

    Rejects with NO_VERIFIED_JOINT_MODEL_SCOPE when joint model is missing or ineligible.
    """
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        candidates = args[0]
    elif len(args) >= 2:
        if joint_model is None and (hasattr(args[-1], "joint_model_id") or hasattr(args[-1], "promotion_status")):
            joint_model = args[-1]
            candidates = args[:-1]
        else:
            candidates = args
    else:
        candidates = args

    is_eligible = False
    if joint_model is not None:
        if hasattr(joint_model, "is_pricing_eligible"):
            is_eligible = bool(joint_model.is_pricing_eligible())
        else:
            is_eligible = getattr(joint_model, "is_eligible", False) is True

    if not is_eligible and joint_model is not None:
        raise BetBuilderEngineError("Joint model scope is not PRICING_ELIGIBLE: NO_VERIFIED_JOINT_MODEL_SCOPE")

    if is_eligible and hasattr(joint_model, "compute_pricing"):
        return joint_model.compute_pricing(candidates)

    return {
        "combined_odds": None,
        "combined_probability": None,
        "rejection_reason": "NO_VERIFIED_JOINT_MODEL_SCOPE",
        "candidates": list(candidates) if isinstance(candidates, (list, tuple)) else [candidates],
    }


def generate_same_event_builders(
    legs: Sequence[BuilderLegV1],
    joint_models: Sequence[JointModelScopeV1] = (),
    event_metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[list[S8IdeaGroupV1], list[BuilderRejectionV1]]:
    """Generate same-event Bet Builder idea groups and rejection records."""
    if not legs:
        return [], []

    by_event: dict[str, list[BuilderLegV1]] = {}
    for leg in legs:
        by_event.setdefault(leg.canonical_event_id, []).append(leg)

    idea_groups: list[S8IdeaGroupV1] = []
    rejections: list[BuilderRejectionV1] = []

    for eid, event_legs in by_event.items():
        if len(event_legs) < 2:
            continue

        for i in range(len(event_legs)):
            for j in range(i + 1, len(event_legs)):
                leg_a = event_legs[i]
                leg_b = event_legs[j]

                compat = validate_leg_compatibility(leg_a, leg_b)
                if not compat.compatible:
                    rejections.append(
                        BuilderRejectionV1(
                            rejection_id=f"REJ-{leg_a.leg_id}-{leg_b.leg_id}",
                            canonical_event_id=eid,
                            leg_ids=(leg_a.leg_id, leg_b.leg_id),
                            reason_code=compat.rejection_reason or "INCOMPATIBLE_LEGS",
                        )
                    )
                    continue

                pair_a_b = (leg_a.market_family.lower(), leg_b.market_family.lower())
                pair_b_a = (leg_b.market_family.lower(), leg_a.market_family.lower())

                matching_model = None
                for jm in joint_models:
                    if getattr(jm, "is_pricing_eligible", lambda: False)():
                        supported = getattr(jm, "supported_market_family_pairs", ())
                        norm_pairs = [
                            (p[0].lower(), p[1].lower()) for p in supported
                        ]
                        if pair_a_b in norm_pairs or pair_b_a in norm_pairs:
                            matching_model = jm
                            break

                if matching_model is None or not hasattr(matching_model, "compute_conjunction"):
                    rejections.append(
                        BuilderRejectionV1(
                            rejection_id=f"REJ-{leg_a.leg_id}-{leg_b.leg_id}",
                            canonical_event_id=eid,
                            leg_ids=(leg_a.leg_id, leg_b.leg_id),
                            reason_code="NO_JOINT_MODEL_SCOPE",
                        )
                    )
                    continue

                prob_a = leg_a.calibrated_probability
                prob_b = leg_b.calibrated_probability
                conjunction_res = matching_model.compute_conjunction([prob_a, prob_b])
                joint_prob = conjunction_res.get("joint_probability")
                if joint_prob is None or joint_prob <= 0 or joint_prob >= 1:
                    rejections.append(
                        BuilderRejectionV1(
                            rejection_id=f"REJ-{leg_a.leg_id}-{leg_b.leg_id}",
                            canonical_event_id=eid,
                            leg_ids=(leg_a.leg_id, leg_b.leg_id),
                            reason_code="NO_JOINT_MODEL_SCOPE",
                        )
                    )
                    continue

                fair_odds_dec = (Decimal("1.0") / Decimal(str(joint_prob))).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                min_odds_dec = (fair_odds_dec * Decimal("1.08")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )

                prob_estimate = JointProbabilityEstimateV1(
                    joint_model_id=matching_model.joint_model_id,
                    calibrated_joint_probability=round(joint_prob, 4),
                    conservative_joint_probability=round(joint_prob, 4),
                    independence_assumed=matching_model.assumes_independence,
                    fair_combined_odds=fair_odds_dec,
                    minimum_acceptable_combined_odds=min_odds_dec,
                )

                candidate = SameEventBuilderCandidateV1(
                    builder_id=f"BUILDER-{eid}-{leg_a.leg_id}-{leg_b.leg_id}",
                    canonical_event_id=eid,
                    sport=leg_a.sport,
                    competition=leg_a.competition,
                    home_team=leg_a.home_team,
                    away_team=leg_a.away_team,
                    legs=(leg_a, leg_b),
                    joint_model_id=matching_model.joint_model_id,
                    joint_probability=prob_estimate,
                    correlation_risk="NEUTRAL",
                    visible_superbet_combined_odds=None,
                )

                event_name = f"{leg_a.home_team} vs {leg_a.away_team}"
                existing_group = next((g for g in idea_groups if g.canonical_event_id == eid), None)
                if existing_group:
                    existing_group.builder_candidates.append(candidate)
                else:
                    group = S8IdeaGroupV1(
                        idea_group_id=f"IG-{eid}",
                        canonical_event_id=eid,
                        sport=leg_a.sport,
                        competition=leg_a.competition,
                        event_name=event_name,
                        builder_candidates=[candidate],
                    )
                    idea_groups.append(group)

    return idea_groups, rejections
