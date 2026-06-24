from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fail_closed import is_valid_pass_b_status
from .provider_corpus import ProviderCorpusRecord


@dataclass(frozen=True)
class SourceBoundShadowArtifact:
    artifact_id: str
    sport: str
    status: str
    source_keys: tuple[str, ...]
    corpus_ids: tuple[str, ...]
    minimum_fact_policy: dict[str, bool]
    unknown_fields: tuple[str, ...]
    blocked_reason: str | None
    manual_authorization_required: bool = True
    production_selectable: bool = False
    betting_decisions_enabled: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "sport": self.sport,
            "status": self.status,
            "source_keys": list(self.source_keys),
            "corpus_ids": list(self.corpus_ids),
            "minimum_fact_policy": self.minimum_fact_policy,
            "unknown_fields": list(self.unknown_fields),
            "blocked_reason": self.blocked_reason,
            "manual_authorization_required": self.manual_authorization_required,
            "production_selectable": self.production_selectable,
            "betting_decisions_enabled": self.betting_decisions_enabled,
        }


def build_source_bound_shadow(sport: str, corpus_records: list[ProviderCorpusRecord], required_facts: tuple[str, ...]) -> SourceBoundShadowArtifact:
    mapped_records = [r for r in corpus_records if r.sport == sport and r.status == "SOURCE_BOUND_SHADOW_READY" and r.participant_evidence]
    unknown_fields = tuple(fact for fact in required_facts if not mapped_records)
    if mapped_records:
        status = "SOURCE_BOUND_SHADOW_READY"
        blocked_reason = None
    elif any(r.sport == sport for r in corpus_records):
        status = "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"
        blocked_reason = "Provider corpus exists, but participant/event mapping is insufficient for source-bound shadow."
    else:
        status = "BLOCKED_PROVIDER_MAPPING_NOT_FOUND"
        blocked_reason = "No usable provider corpus record exists for this sport."
    assert is_valid_pass_b_status(status)
    return SourceBoundShadowArtifact(
        artifact_id=f"msb-shadow-{sport}",
        sport=sport,
        status=status,
        source_keys=tuple(sorted({r.source_key for r in mapped_records})),
        corpus_ids=tuple(sorted(r.corpus_id for r in mapped_records)),
        minimum_fact_policy={fact: fact not in unknown_fields for fact in required_facts},
        unknown_fields=unknown_fields,
        blocked_reason=blocked_reason,
    )
