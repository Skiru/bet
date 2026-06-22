from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from bet.enrichment.football_data_foundation.kernel.contracts import FactType, EvidenceClaim
from .conflict import FusionConflict


@dataclass(frozen=True)
class FusedFootballFact:
    fact_type: FactType
    value: dict[str, Any]
    source_keys: tuple[str, ...]
    proof_levels: tuple[str, ...]
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
                    "value": f.value,
                    "source_keys": list(f.source_keys),
                    "proof_levels": list(f.proof_levels),
                    "selectable_for_production": f.selectable_for_production,
                }
                for f in self.fused_facts
            ],
            "conflicts": [
                {
                    "fact_type": c.fact_type.value,
                    "reason": c.reason,
                    "source_keys": list(c.source_keys),
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
