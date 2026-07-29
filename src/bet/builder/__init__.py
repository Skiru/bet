"""Same-event Bet Builder engine module."""
from __future__ import annotations

from bet.builder.models import (
    BuilderLegV1,
    BuilderCompatibilityDecisionV1,
    JointModelScopeV1,
    JointProbabilityEstimateV1,
    SameEventBuilderCandidateV1,
    S8IdeaGroupV1,
    BuilderRejectionV1,
)
from bet.builder.engine import (
    BetBuilderEngineError,
    validate_leg_compatibility,
    compute_joint_builder_pricing,
    generate_same_event_builders,
)
