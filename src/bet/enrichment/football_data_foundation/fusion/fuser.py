from __future__ import annotations

import hashlib
import json
from typing import Iterable

from bet.enrichment.football_data_foundation.kernel.contracts import (
    EvidenceClaim,
    FactType,
    SourceRole,
)
from .policy import FusionPolicy
from .conflict import FusionConflict
from .output import FusedFootballFact, FusionRunSummary


class ShadowFactFuser:
    def __init__(self, policy: FusionPolicy | None = None):
        self.policy = policy or FusionPolicy()

    def fuse(self, claims: Iterable[EvidenceClaim]) -> FusionRunSummary:
        eligible: list[EvidenceClaim] = []
        excluded: list[EvidenceClaim] = []

        for claim in claims:
            # Check excluded proof levels
            if claim.proof_level in self.policy.excluded_proof_levels:
                excluded.append(claim)
                continue
            
            # Check excluded source roles
            if claim.source.role in self.policy.excluded_source_roles:
                excluded.append(claim)
                continue
            
            # Check special criteria for MATCH_STATUS, SCORE, STANDINGS
            if claim.fact_type in {FactType.MATCH_STATUS, FactType.SCORE, FactType.STANDINGS}:
                role_ok = claim.source.role in {
                    SourceRole.CURRENT_LIVE,
                    SourceRole.CURRENT_LIVE_BENCHMARK,
                    SourceRole.CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW,
                    SourceRole.CURRENT_REFERENCE,
                }
                if not (role_ok and claim.freshness.is_current_truth_allowed):
                    excluded.append(claim)
                    continue

            eligible.append(claim)

        # Group eligible claims by fact type
        by_type: dict[FactType, list[EvidenceClaim]] = {}
        for claim in eligible:
            by_type.setdefault(claim.fact_type, []).append(claim)

        fused: list[FusedFootballFact] = []
        conflicts: list[FusionConflict] = []
        source_coverage: dict[str, list[str]] = {}

        for fact_type, fact_claims in by_type.items():
            # Populate source coverage
            for claim in fact_claims:
                skey = claim.source.source_key
                source_coverage.setdefault(skey, []).append(fact_type.value)

            # Check values
            unique_vals: dict[str, EvidenceClaim] = {}
            for claim in fact_claims:
                serialized = json.dumps(claim.claim_value, sort_keys=True)
                unique_vals[serialized] = claim

            if len(unique_vals) > 1:
                # Disagreement in current-source MATCH_STATUS/SCORE/STANDINGS
                conflicts.append(
                    FusionConflict(
                        fact_type=fact_type,
                        reason=f"disagreement in values for {fact_type.value}",
                        source_keys=tuple(sorted({c.source.source_key for c in fact_claims})),
                    )
                )
                continue

            # No disagreement, let's fuse!
            anchor_claim = fact_claims[0]
            fused_sources = tuple(sorted({c.source.source_key for c in fact_claims}))
            fused_proofs = tuple(sorted({c.proof_level.value for c in fact_claims}))

            fused.append(
                FusedFootballFact(
                    fact_type=fact_type,
                    value=dict(anchor_claim.claim_value),
                    source_keys=fused_sources,
                    proof_levels=fused_proofs,
                    selectable_for_production=False,
                )
            )

        # Deduplicate and sort source_coverage values
        sorted_coverage = {
            skey: sorted(list(set(types))) for skey, types in source_coverage.items()
        }

        # Determine missing fact types
        fused_types = {f.fact_type for f in fused}
        missing_fact_types = tuple(
            [ft for ft in self.policy.required_fact_types if ft not in fused_types]
        )

        # Generate a deterministic run_id
        hasher = hashlib.sha256()
        sorted_claims_for_hash = sorted(
            list(claims),
            key=lambda c: (c.source.source_key, c.fact_type.value, c.proof_level.value)
        )
        for c in sorted_claims_for_hash:
            hasher.update(c.source.source_key.encode("utf-8"))
            hasher.update(c.fact_type.value.encode("utf-8"))
            if c.payload_policy.payload_hash:
                hasher.update(c.payload_policy.payload_hash.encode("utf-8"))
        run_id = f"run_{hasher.hexdigest()[:12]}"

        return FusionRunSummary(
            run_id=run_id,
            fused_facts=tuple(fused),
            conflicts=tuple(conflicts),
            excluded_claims=tuple(excluded),
            missing_fact_types=missing_fact_types,
            source_coverage=sorted_coverage,
            manual_authorization_required=True,
            selectable_for_production=False,
        )

# Line-endings normalization proof
