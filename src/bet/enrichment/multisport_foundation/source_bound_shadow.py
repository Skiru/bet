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
    sport_records = [r for r in corpus_records if r.sport == sport]
    ready_records = [r for r in sport_records if r.status == "SOURCE_BOUND_SHADOW_READY" and r.participant_evidence]

    if ready_records:
        status = "SOURCE_BOUND_SHADOW_READY"
        blocked_reason = None
        active_records = ready_records
    elif any(r.status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT" for r in sport_records):
        status = "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"
        matching = [r for r in sport_records if r.status == status]
        blocked_reason = matching[0].mapping_notes or "Provider corpus exists, but participant/event mapping is insufficient for source-bound shadow."
        active_records = matching
    elif any(r.status == "BLOCKED_NO_CREDENTIALS" for r in sport_records):
        status = "BLOCKED_NO_CREDENTIALS"
        matching = [r for r in sport_records if r.status == status]
        blocked_reason = matching[0].mapping_notes or "Access blocked due to missing credentials."
        active_records = matching
    elif any(r.status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE" for r in sport_records):
        status = "BLOCKED_PROVIDER_TERMS_OR_SCOPE"
        matching = [r for r in sport_records if r.status == status]
        blocked_reason = matching[0].mapping_notes or "Access blocked due to provider terms or scope."
        active_records = matching
    elif any(r.status == "BLOCKED_PROVIDER_ACCESS" for r in sport_records):
        status = "BLOCKED_PROVIDER_ACCESS"
        matching = [r for r in sport_records if r.status == status]
        blocked_reason = matching[0].mapping_notes or "Access blocked by provider."
        active_records = matching
    else:
        status = "BLOCKED_PROVIDER_MAPPING_NOT_FOUND"
        blocked_reason = "No usable provider corpus record exists for this sport."
        active_records = []

    unknown_fields = tuple(fact for fact in required_facts if status != "SOURCE_BOUND_SHADOW_READY")

    assert is_valid_pass_b_status(status)
    return SourceBoundShadowArtifact(
        artifact_id=f"msb-shadow-{sport}",
        sport=sport,
        status=status,
        source_keys=tuple(sorted({r.source_key for r in active_records})),
        corpus_ids=tuple(sorted(r.corpus_id for r in active_records)),
        minimum_fact_policy={fact: fact not in unknown_fields for fact in required_facts},
        unknown_fields=unknown_fields,
        blocked_reason=blocked_reason,
    )


def write_source_bound_shadow_status_by_sport_report(path: str = "reports/multisport_foundation/pass_b/source_bound_shadow_status_by_sport.json") -> str:
    import os
    import json
    from .profiles import build_sport_profiles
    from .contracts import SportKey

    profiles = build_sport_profiles()
    sports = ["basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"]

    report_data = {}
    for sport in sports:
        profile = profiles[SportKey(sport)]
        required_facts = tuple(fact.name for fact in profile.required_facts)
        artifact = build_source_bound_shadow(sport, [], required_facts)
        report_data[sport] = {
            "blocked_reason": artifact.blocked_reason,
            "corpus_ids": list(artifact.corpus_ids),
            "manual_authorization_required": artifact.manual_authorization_required,
            "production_selectable": artifact.production_selectable,
            "betting_decisions_enabled": artifact.betting_decisions_enabled,
            "source_keys": list(artifact.source_keys),
            "sport": artifact.sport,
            "status": artifact.status,
            "unknown_fields": list(artifact.unknown_fields),
        }

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report_data, indent=2, sort_keys=True) + "\n")
    return path
