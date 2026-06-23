from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SHADOW_READY_STATUS = "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW"
ACTIVATION_CANDIDATE_STATUS = "ACTIVATION_CANDIDATE_SHADOW_ONLY"

DEFAULT_REQUIRED_PROVIDERS = (
    "api-football",
    "football-data-org",
    "espn-baseline",
    "sportdb",
    "highlightly",
)


@dataclass(frozen=True)
class ActivationArtifactPaths:
    fixture_slug: str
    fixture_dir: Path
    snapshot_path: Path
    sqlite_path: Path
    verifier_path: Path
    provider_fact_counts_path: Path
    public_artifact_proof_path: Path

    @classmethod
    def from_shadow_root(cls, shadow_root: Path, fixture_slug: str) -> "ActivationArtifactPaths":
        fixture_dir = shadow_root / fixture_slug.replace("-", "_")
        return cls(
            fixture_slug=fixture_slug,
            fixture_dir=fixture_dir,
            snapshot_path=fixture_dir / "source_bound_shadow_snapshot.json",
            sqlite_path=fixture_dir / "source_bound_shadow.sqlite",
            verifier_path=fixture_dir / "source_bound_verifier_result.json",
            provider_fact_counts_path=fixture_dir / "provider_fact_counts.json",
            public_artifact_proof_path=fixture_dir / "public_artifact_proof.json",
        )

    def to_json(self) -> dict[str, str]:
        return {
            "fixture_slug": self.fixture_slug,
            "fixture_dir": str(self.fixture_dir),
            "snapshot_path": str(self.snapshot_path),
            "sqlite_path": str(self.sqlite_path),
            "verifier_path": str(self.verifier_path),
            "provider_fact_counts_path": str(self.provider_fact_counts_path),
            "public_artifact_proof_path": str(self.public_artifact_proof_path),
        }


@dataclass(frozen=True)
class ActivationPolicy:
    required_providers: tuple[str, ...] = DEFAULT_REQUIRED_PROVIDERS
    expected_fixture_slug: str | None = None
    expected_score: dict[str, int] | None = None
    require_public_artifact_proof: bool = True
    require_sqlite_provider_rows: bool = True
    allow_live_network: bool = False
    allow_betting_decisions: bool = False
    allow_production_db_writes: bool = False
    allow_production_selectable: bool = False

    @classmethod
    def strict_worldcup_acceptance(cls) -> "ActivationPolicy":
        return cls(
            expected_fixture_slug="worldcup2026-norway-senegal",
            expected_score={"home": 3, "away": 2},
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "required_providers": list(self.required_providers),
            "expected_fixture_slug": self.expected_fixture_slug,
            "expected_score": self.expected_score,
            "require_public_artifact_proof": self.require_public_artifact_proof,
            "require_sqlite_provider_rows": self.require_sqlite_provider_rows,
            "allow_live_network": self.allow_live_network,
            "allow_betting_decisions": self.allow_betting_decisions,
            "allow_production_db_writes": self.allow_production_db_writes,
            "allow_production_selectable": self.allow_production_selectable,
        }


@dataclass(frozen=True)
class ActivationDecision:
    status: str
    selectable_for_production: bool
    manual_authorization_required: bool
    production_db_write_allowed: bool
    betting_decision_allowed: bool
    live_network_allowed: bool
    reason: str

    @classmethod
    def shadow_only(cls, reason: str) -> "ActivationDecision":
        return cls(
            status=ACTIVATION_CANDIDATE_STATUS,
            selectable_for_production=False,
            manual_authorization_required=True,
            production_db_write_allowed=False,
            betting_decision_allowed=False,
            live_network_allowed=False,
            reason=reason,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "selectable_for_production": self.selectable_for_production,
            "manual_authorization_required": self.manual_authorization_required,
            "production_db_write_allowed": self.production_db_write_allowed,
            "betting_decision_allowed": self.betting_decision_allowed,
            "live_network_allowed": self.live_network_allowed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ActivationCandidate:
    fixture_slug: str
    source_artifacts: ActivationArtifactPaths
    provider_ids: dict[str, str]
    provider_fact_counts: dict[str, int]
    score: dict[str, int]
    conflicts: list[Any]
    shadow_status: str
    source_bound_verifier_verdict: str
    sqlite_summary: dict[str, Any]
    decision: ActivationDecision
    policy: ActivationPolicy
    integration_mode: str = "shadow_only_facade"
    source_bundle_mutated: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "fixture_slug": self.fixture_slug,
            "source_artifacts": self.source_artifacts.to_json(),
            "provider_ids": dict(sorted(self.provider_ids.items())),
            "provider_fact_counts": dict(sorted(self.provider_fact_counts.items())),
            "score": dict(self.score),
            "conflicts": self.conflicts,
            "shadow_status": self.shadow_status,
            "source_bound_verifier_verdict": self.source_bound_verifier_verdict,
            "sqlite_summary": self.sqlite_summary,
            "decision": self.decision.to_json(),
            "policy": self.policy.to_json(),
            "integration_mode": self.integration_mode,
            "source_bundle_mutated": self.source_bundle_mutated,
        }


@dataclass(frozen=True)
class ActivationVerificationResult:
    verdict: str
    failed_requirements: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "failed_requirements": list(self.failed_requirements),
            "checks": dict(sorted(self.checks.items())),
        }
