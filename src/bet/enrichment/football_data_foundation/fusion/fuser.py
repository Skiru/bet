from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from bet.enrichment.football_data_foundation.kernel.contracts import (
    EvidenceClaim,
    FactType,
    ProofLevel,
    SourceRole,
)

from .conflict import FusionConflict
from .output import FusedFootballFact, FusionRunSummary
from .policy import FusionPolicy


def identity_key_for_claim(claim: EvidenceClaim) -> str:
    """
    Computes a stable identity key for a claim.
    Uses provider_fixture_id when present, otherwise normalized_home_name + normalized_away_name,
    otherwise source-specific fallback.
    """
    identity = claim.identity
    if identity and identity.provider_fixture_id:
        return str(identity.provider_fixture_id).strip()

    if identity and identity.normalized_home_name and identity.normalized_away_name:
        home = str(identity.normalized_home_name).strip().lower()
        away = str(identity.normalized_away_name).strip().lower()
        home = re.sub(r"\s+", "-", home)
        away = re.sub(r"\s+", "-", away)
        return f"{home}_{away}"

    return f"{claim.source.source_key}_fallback_fixture"


class ShadowFactFuser:
    def __init__(self, policy: FusionPolicy | None = None):
        self.policy = policy or FusionPolicy()

    def fuse(self, claims: Iterable[EvidenceClaim]) -> FusionRunSummary:
        # 1. Materialize input immediately
        claims_tuple = tuple(claims)

        eligible: list[EvidenceClaim] = []
        excluded: list[EvidenceClaim] = []

        # 4. Exclude by policy
        for claim in claims_tuple:
            # Check excluded proof levels
            if claim.proof_level in self.policy.excluded_proof_levels:
                excluded.append(claim)
                continue

            # Check excluded source roles
            if claim.source.role in self.policy.excluded_source_roles:
                excluded.append(claim)
                continue

            # Check special criteria for current fact types (MATCH_STATUS, SCORE, STANDINGS)
            if claim.fact_type in self.policy.current_fact_types:
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

        # 3. Group eligible claims by (identity_key, fact_type)
        by_group: dict[tuple[str, FactType], list[EvidenceClaim]] = {}
        for claim in eligible:
            ikey = identity_key_for_claim(claim)
            by_group.setdefault((ikey, claim.fact_type), []).append(claim)

        fused: list[FusedFootballFact] = []
        conflicts: list[FusionConflict] = []
        source_coverage: dict[str, list[str]] = {}

        # 7. Priority scoring function
        def get_main_rank(claim: EvidenceClaim) -> int:
            role = claim.source.role
            proof = claim.proof_level
            # highest: REAL_ACCEPTED_ARTIFACT_PROOF + CURRENT_LIVE_BENCHMARK
            if (
                proof == ProofLevel.REAL_ACCEPTED_ARTIFACT_PROOF
                and role == SourceRole.CURRENT_LIVE_BENCHMARK
            ):
                return 10
            # then REAL_LIVE_API_PROOF + CURRENT_LIVE
            if (
                proof == ProofLevel.REAL_LIVE_API_PROOF
                and role == SourceRole.CURRENT_LIVE
            ):
                return 9
            # then CURRENT_REFERENCE
            if role == SourceRole.CURRENT_REFERENCE:
                return 8
            # then detailed shadow
            if role in {
                SourceRole.CURRENT_LIVE_OR_RECENT_DETAILED_SHADOW,
                SourceRole.REFERENCE_METADATA_SHADOW,
            }:
                return 7
            # then local open data / dependency replay for context only
            if (
                proof
                in {
                    ProofLevel.REAL_LOCAL_OPEN_DATA_PROOF,
                    ProofLevel.REAL_DEPENDENCY_REPLAY_PROOF,
                }
                or role == SourceRole.DEPENDENCY_REPLAY
            ):
                return 6

            # General fallback using policy indexes
            role_idx = 0
            if role in self.policy.source_role_priority:
                role_idx = len(
                    self.policy.source_role_priority
                ) - self.policy.source_role_priority.index(role)
            proof_idx = 0
            if proof in self.policy.proof_level_priority:
                proof_idx = len(
                    self.policy.proof_level_priority
                ) - self.policy.proof_level_priority.index(proof)
            return role_idx + proof_idx

        def claim_sort_key(claim: EvidenceClaim) -> tuple[int, float, str]:
            return (-get_main_rank(claim), -claim.confidence, claim.source.source_key)

        for (identity_key, fact_type), fact_claims in by_group.items():
            # Populate source coverage
            for claim in fact_claims:
                skey = claim.source.source_key
                source_coverage.setdefault(skey, []).append(fact_type.value)

            is_current = fact_type in self.policy.current_fact_types

            # 5. Handle current facts disagreement
            if is_current:
                unique_vals: dict[str, list[EvidenceClaim]] = {}
                for claim in fact_claims:
                    serialized = json.dumps(claim.claim_value, sort_keys=True)
                    unique_vals.setdefault(serialized, []).append(claim)

                if len(unique_vals) > 1:
                    v_by_source = {
                        c.source.source_key: c.claim_value for c in fact_claims
                    }
                    conflicts.append(
                        FusionConflict(
                            fact_type=fact_type,
                            identity_key=identity_key,
                            source_keys=tuple(
                                sorted({c.source.source_key for c in fact_claims})
                            ),
                            values_by_source=v_by_source,
                            reason="current_fact_value_disagreement",
                            severity="BLOCKING",
                        )
                    )
                    continue

            # 6. For context facts, select primary deterministically and do not block
            sorted_claims = sorted(fact_claims, key=claim_sort_key)
            primary_claim = sorted_claims[0]
            primary_rank = get_main_rank(primary_claim)

            supporting_sources = tuple(
                sorted(
                    {
                        c.source.source_key
                        for c in sorted_claims
                        if c.source.source_key != primary_claim.source.source_key
                    }
                )
            )

            fused_proofs = tuple(sorted({c.proof_level.value for c in sorted_claims}))

            fused.append(
                FusedFootballFact(
                    fact_type=fact_type,
                    identity_key=identity_key,
                    value=dict(primary_claim.claim_value),
                    primary_source_key=primary_claim.source.source_key,
                    supporting_source_keys=supporting_sources,
                    proof_levels=fused_proofs,
                    confidence=primary_claim.confidence,
                    selected_reason=f"deterministic priority (rank={primary_rank})",
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

        # 8. Deterministic run_id generation
        hasher = hashlib.sha256()
        sorted_claims_for_hash = sorted(
            list(claims_tuple),
            key=lambda c: (
                identity_key_for_claim(c),
                c.fact_type.value,
                c.source.source_key,
                c.proof_level.value,
                json.dumps(c.claim_value, sort_keys=True),
            ),
        )
        for c in sorted_claims_for_hash:
            hasher.update(identity_key_for_claim(c).encode("utf-8"))
            hasher.update(c.fact_type.value.encode("utf-8"))
            hasher.update(c.source.source_key.encode("utf-8"))
            hasher.update(c.proof_level.value.encode("utf-8"))
            hasher.update(json.dumps(c.claim_value, sort_keys=True).encode("utf-8"))
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
        )  # guardrail
