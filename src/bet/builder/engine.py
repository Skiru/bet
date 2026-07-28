"""Engine for Bet Builder calculations and joint pricing."""
from __future__ import annotations

from typing import Any, Sequence


def calculate_combined_odds(
    leg_probabilities: Sequence[float],
    joint_model: Any = None,
) -> dict[str, Any]:
    """Calculate combined odds for Bet Builder legs.

    Rejects unless passed a resolved joint package that computes the conjunction.
    Does NOT calculate marginal multiplication (p_a * p_b).
    """
    if joint_model is None or getattr(joint_model, "is_eligible", False) == False:
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
    candidates: Sequence[dict[str, Any]],
    joint_model: Any = None,
) -> dict[str, Any]:
    """Compute joint builder pricing for candidates.

    Rejects with NO_VERIFIED_JOINT_MODEL_SCOPE when joint model is missing or ineligible.
    """
    if joint_model is None or getattr(joint_model, "is_eligible", False) == False:
        return {
            "combined_odds": None,
            "combined_probability": None,
            "rejection_reason": "NO_VERIFIED_JOINT_MODEL_SCOPE",
            "candidates": list(candidates),
        }
    if hasattr(joint_model, "compute_pricing"):
        return joint_model.compute_pricing(candidates)
    return {
        "combined_odds": None,
        "combined_probability": None,
        "rejection_reason": "NO_VERIFIED_JOINT_MODEL_SCOPE",
        "candidates": list(candidates),
    }


def generate_same_event_builders(
    candidates: Sequence[dict[str, Any]],
    joint_model: Any = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Generate same-event Bet Builder idea groups (unpriced analysis candidates)."""
    return []
