"""Risk policy contract for tipster evidence.

Defines compliance tiers, evidence use tiers, and the RiskPolicy model to ensure
strict separation between certified shadow and operator-risk sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ComplianceTier(str, Enum):
    CERTIFIED_SHADOW = "certified_shadow"
    CANDIDATE_COMPLIANT = "candidate_compliant"
    OPERATOR_RISK_PUBLIC_READ = "operator_risk_public_read"
    FIXTURE_ONLY = "fixture_only"
    MANUAL_REVIEW_ONLY = "manual_review_only"
    HARD_BLOCKED = "hard_blocked"


class EvidenceUse(str, Enum):
    CERTIFIED_CONTEXT = "certified_context"
    LOW_TRUST_CONTEXT = "low_trust_context"
    MANUAL_REVIEW_ONLY = "manual_review_only"
    REJECTED = "rejected"


@dataclass
class RiskPolicy:
    source_id: str
    compliance_tier: ComplianceTier
    robots_policy: str
    operator_ack_required: bool
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    promotion_allowed: bool = False
    risk_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "compliance_tier": self.compliance_tier.value,
            "robots_policy": self.robots_policy,
            "operator_ack_required": self.operator_ack_required,
            "allowed_actions": self.allowed_actions,
            "forbidden_actions": self.forbidden_actions,
            "promotion_allowed": self.promotion_allowed,
            "risk_warnings": self.risk_warnings,
        }


def get_risk_policy(source_id: str, is_certified: bool = False) -> RiskPolicy:
    """Factory to build RiskPolicy for a source."""
    forbidden = ["EV", "stake", "coupon", "final bet", "Superbet combined odds"]

    if is_certified:
        return RiskPolicy(
            source_id=source_id,
            compliance_tier=ComplianceTier.CERTIFIED_SHADOW,
            robots_policy="allowed_or_reviewed",
            operator_ack_required=False,
            allowed_actions=["USE_AS_CONTEXT", "USE_AS_MARKET_SANITY_CHECK"],
            forbidden_actions=forbidden,
            promotion_allowed=True,
            risk_warnings=[],
        )
    else:
        # Default operator-risk public read discovery
        return RiskPolicy(
            source_id=source_id,
            compliance_tier=ComplianceTier.OPERATOR_RISK_PUBLIC_READ,
            robots_policy="may_ignore_or_bypass_for_discovery",
            operator_ack_required=True,
            allowed_actions=["MANUAL_REVIEW_ONLY"],
            forbidden_actions=forbidden,
            promotion_allowed=False,
            risk_warnings=[
                "not_certified_shadow",
                "operator_risk_public_read",
                "manual_review_required_before_use",
            ],
        )
