from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fail_closed import assert_no_forbidden_success_text

@dataclass(frozen=True)
class LiveObservationArtifact:
    artifact_id: str
    sport: str
    status: str
    observation_mode: str
    source_pass_b_status: str
    source_keys: tuple[str, ...]
    corpus_ids: tuple[str, ...]
    blocked_reason: str | None = None
    unknown_fields: tuple[str, ...] = ()
    provider_access_attempted: bool = False
    live_call_made: bool = False
    manual_authorization_required: bool = True
    production_selectable: bool = False
    betting_decisions_enabled: bool = False
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.manual_authorization_required:
            raise ValueError("manual_authorization_required must always be true.")
        if self.production_selectable:
            raise ValueError("production_selectable must always be false.")
        if self.betting_decisions_enabled:
            raise ValueError("betting_decisions_enabled must always be false.")
        if self.live_call_made:
            raise ValueError("live_call_made must be false in this pass.")
        if self.provider_access_attempted:
            raise ValueError("provider_access_attempted must be false in this pass.")
        if self.observation_mode != "fail_closed_no_live_call":
            raise ValueError("observation_mode must be fail_closed_no_live_call.")

        # Let's verify no forbidden success terms are present in the JSON representation
        assert_no_forbidden_success_text(self.to_json())

    def to_json(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "sport": self.sport,
            "status": self.status,
            "observation_mode": self.observation_mode,
            "provider_access_attempted": self.provider_access_attempted,
            "live_call_made": self.live_call_made,
            "source_pass_b_status": self.source_pass_b_status,
            "source_keys": list(self.source_keys),
            "corpus_ids": list(self.corpus_ids),
            "blocked_reason": self.blocked_reason,
            "unknown_fields": list(self.unknown_fields),
            "manual_authorization_required": self.manual_authorization_required,
            "production_selectable": self.production_selectable,
            "betting_decisions_enabled": self.betting_decisions_enabled,
            "evidence_refs": list(self.evidence_refs),
        }


def build_live_observation(
    sport: str,
    pass_b_status: str,
    source_keys: tuple[str, ...],
    corpus_ids: tuple[str, ...],
    unknown_fields: tuple[str, ...] = (),
    source_shadow_report_path: str = "reports/multisport_foundation/pass_b/source_bound_shadow_status_by_sport.json",
    blocked_reason: str | None = None,
) -> LiveObservationArtifact:
    """Build a LiveObservationArtifact from Pass B status and inputs."""

    if pass_b_status == "SOURCE_BOUND_SHADOW_READY" and source_keys and corpus_ids:
        status = "ACTIVATION_CANDIDATE_SHADOW_ONLY"
        derived_blocked_reason = None
    elif pass_b_status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT":
        status = "REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING"
        derived_blocked_reason = blocked_reason or "Real provider access observed, but mapping is insufficient."
    elif pass_b_status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE":
        status = "BLOCKED_PROVIDER_TERMS_OR_SCOPE"
        derived_blocked_reason = blocked_reason or "Access blocked due to provider terms or scope."
    else:
        status = "BLOCKED_NO_REAL_PROVIDER_ACCESS"
        derived_blocked_reason = blocked_reason or f"Access blocked because Pass B status is {pass_b_status}."

    evidence_refs = (source_shadow_report_path,)

    return LiveObservationArtifact(
        artifact_id=f"msc-observation-{sport}",
        sport=sport,
        status=status,
        observation_mode="fail_closed_no_live_call",
        provider_access_attempted=False,
        live_call_made=False,
        source_pass_b_status=pass_b_status,
        source_keys=source_keys,
        corpus_ids=corpus_ids,
        blocked_reason=derived_blocked_reason,
        unknown_fields=unknown_fields,
        manual_authorization_required=True,
        production_selectable=False,
        betting_decisions_enabled=False,
        evidence_refs=evidence_refs,
    )


def write_pass_c_reports(
    pass_b_path: str = "reports/multisport_foundation/pass_b/source_bound_shadow_status_by_sport.json",
    out_dir: str = "reports/multisport_foundation/pass_c",
) -> dict[str, str]:
    """Generate Pass C JSON reports for all target sports."""
    import os
    import json
    from .activation_candidate import build_activation_candidate

    with open(pass_b_path, "r", encoding="utf-8") as fh:
        pass_b_data = json.load(fh)

    sports = ["basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"]

    activation_reports = {}
    observation_reports = {}

    metrics = {
        "total_target_sports": len(sports),
        "activation_candidate_shadow_only_count": 0,
        "blocked_no_real_provider_access_count": 0,
        "blocked_provider_terms_or_scope_count": 0,
        "real_provider_access_observed_but_live_shadow_blocked_insufficient_mapping_count": 0,
        "live_calls_made": False,
        "provider_access_attempted": False,
        "production_activation": False,
        "betting_decisions": False,
    }

    activation_statuses = {}
    observation_statuses = {}

    for sport in sports:
        sport_b = pass_b_data[sport]
        pass_b_status = sport_b["status"]
        source_keys = tuple(sport_b.get("source_keys", []))
        corpus_ids = tuple(sport_b.get("corpus_ids", []))
        unknown_fields = tuple(sport_b.get("unknown_fields", []))
        blocked_reason = sport_b.get("blocked_reason")

        act_art = build_activation_candidate(
            sport=sport,
            pass_b_status=pass_b_status,
            source_keys=source_keys,
            corpus_ids=corpus_ids,
            source_shadow_report_path=pass_b_path,
            blocked_reason=blocked_reason,
        )

        obs_art = build_live_observation(
            sport=sport,
            pass_b_status=pass_b_status,
            source_keys=source_keys,
            corpus_ids=corpus_ids,
            unknown_fields=unknown_fields,
            source_shadow_report_path=pass_b_path,
            blocked_reason=blocked_reason,
        )

        activation_reports[sport] = act_art.to_json()
        observation_reports[sport] = obs_art.to_json()

        activation_statuses[sport] = act_art.status
        observation_statuses[sport] = obs_art.status

        # Count metrics
        if act_art.status == "ACTIVATION_CANDIDATE_SHADOW_ONLY":
            metrics["activation_candidate_shadow_only_count"] += 1
        elif act_art.status == "BLOCKED_NO_REAL_PROVIDER_ACCESS":
            metrics["blocked_no_real_provider_access_count"] += 1
        elif act_art.status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE":
            metrics["blocked_provider_terms_or_scope_count"] += 1
        elif act_art.status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING":
            metrics["real_provider_access_observed_but_live_shadow_blocked_insufficient_mapping_count"] += 1

    summary_report = {
        "summary_version": "ms-c-summary-v1",
        "target_sports": sports,
        "activation_candidate_statuses": activation_statuses,
        "live_observation_statuses": observation_statuses,
        "metrics": metrics,
    }

    os.makedirs(out_dir, exist_ok=True)

    paths = {
        "activation": os.path.join(out_dir, "activation_candidate_by_sport.json"),
        "observation": os.path.join(out_dir, "live_fail_closed_observation_by_sport.json"),
        "summary": os.path.join(out_dir, "pass_c_summary.json"),
    }

    for key, path in paths.items():
        data = (
            activation_reports if key == "activation"
            else (observation_reports if key == "observation" else summary_report)
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, sort_keys=True) + "\n")

    return paths
