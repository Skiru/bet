from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bet.enrichment.football_data_foundation.kernel.contracts import (
    EvidenceClaim,
    FactType,
)

from .conflict import FusionConflict


@dataclass(frozen=True)
class FusedFootballFact:
    fact_type: FactType
    identity_key: str
    value: dict[str, Any]
    primary_source_key: str
    supporting_source_keys: tuple[str, ...]
    proof_levels: tuple[str, ...]
    confidence: float
    selected_reason: str
    selectable_for_production: bool = False


@dataclass(frozen=True)
class FusionRunSummary:
    run_id: str
    fused_facts: tuple[FusedFootballFact, ...]
    conflicts: tuple[FusionConflict, ...]
    excluded_claims: tuple[EvidenceClaim, ...]
    missing_fact_types: tuple[FactType, ...]
    source_coverage: dict[str, list[str]]
    manual_authorization_required: bool = True
    selectable_for_production: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "fused_facts": [
                {
                    "fact_type": f.fact_type.value,
                    "identity_key": f.identity_key,
                    "value": f.value,
                    "primary_source_key": f.primary_source_key,
                    "supporting_source_keys": list(f.supporting_source_keys),
                    "proof_levels": list(f.proof_levels),
                    "confidence": f.confidence,
                    "selected_reason": f.selected_reason,
                    "selectable_for_production": f.selectable_for_production,
                }
                for f in self.fused_facts
            ],
            "conflicts": [
                {
                    "fact_type": c.fact_type.value,
                    "identity_key": c.identity_key,
                    "source_keys": list(c.source_keys),
                    "values_by_source": c.values_by_source,
                    "reason": c.reason,
                    "severity": c.severity,
                }
                for c in self.conflicts
            ],
            "excluded_claims": [
                {
                    "source_key": claim.source.source_key,
                    "fact_type": claim.fact_type.value,
                    "proof_level": claim.proof_level.value,
                }
                for claim in self.excluded_claims
            ],
            "missing_fact_types": [f_t.value for f_t in self.missing_fact_types],
            "source_coverage": self.source_coverage,
            "manual_authorization_required": self.manual_authorization_required,
            "selectable_for_production": self.selectable_for_production,
        }
