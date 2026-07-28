"""Pipeline run readiness contracts - dataclasses and enums representing pipeline states."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


class PipelineReadinessStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"
    SKIPPED = "SKIPPED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"
    COMMAND_REQUEST = "COMMAND_REQUEST"
    TEST_ONLY_GENERATED_HUMAN_GATE = "TEST_ONLY_GENERATED_HUMAN_GATE"


class PipelineArtifactType(str, Enum):
    AGENT_ARTIFACT = "AGENT_ARTIFACT"
    HUMAN_GATE = "HUMAN_GATE"
    STATE_MARKER = "STATE_MARKER"
    SCRIPT_EVIDENCE = "SCRIPT_EVIDENCE"
    RUN_SUMMARY = "RUN_SUMMARY"


class ForbiddenDecisionSignal(str, Enum):
    PICK = "pick"
    PICKS = "picks"
    SELECTION = "selection"
    SELECTIONS = "selections"
    BET = "bet"
    BETTING_DECISION = "betting_decision"
    EDGE = "edge"
    EV = "ev"
    EXPECTED_VALUE = "expected_value"
    STAKE = "stake"
    STAKING = "staking"
    COUPON = "coupon"
    ACCUMULATOR = "accumulator"
    PARLAY = "parlay"


class AllowedNegativeAssertionKeys(str, Enum):
    NO_PICK = "no_pick"
    NO_EDGE = "no_edge"
    NO_STAKE = "no_stake"
    NO_COUPON = "no_coupon"
    SELECTION = "selection"
    SELECTION_ID = "selection_id"
    SELECTION_NAME = "selection_name"
    REQUESTED_SELECTION = "requested_selection"
    NO_PICK_EDGE_STAKE_COUPON_EMITTED = "no_pick_edge_stake_coupon_emitted"
    FORBIDDEN_FIELDS_ABSENT = "forbidden_fields_absent"
    BETTING_DECISIONS_ENABLED = "betting_decisions_enabled"
    PRODUCTION_SELECTABLE = "production_selectable"
    ALLOW_REAL_NETWORK = "allow_real_network"
    PROVIDER_AUTHORIZATION = "provider_authorization"
    PROVIDER_AUTHORIZATION_STATUS = "provider_authorization_status"
    AUTHORIZATION_STATUS = "authorization_status"
    AUTHORIZED_FOR_SANITIZED_LIVE_PROBE = "authorized_for_sanitized_live_probe"
    BLOCKED_NO_CREDENTIALS = "blocked_no_credentials"
    SINGLE_FLIGHT_PROBE = "single_flight_probe"


def status_is_pass(status: PipelineReadinessStatus) -> bool:
    """Check if the readiness status represents a non-blocking/passing state."""
    return status in (PipelineReadinessStatus.PASS, PipelineReadinessStatus.HUMAN_APPROVED)


def status_blocks(status: PipelineReadinessStatus) -> bool:
    """Check if the readiness status blocks execution."""
    return status in (
        PipelineReadinessStatus.BLOCK,
        PipelineReadinessStatus.UNKNOWN,
        PipelineReadinessStatus.HUMAN_REJECTED,
        PipelineReadinessStatus.COMMAND_REQUEST,
        PipelineReadinessStatus.TEST_ONLY_GENERATED_HUMAN_GATE,
    )


def normalize_status(value: str) -> PipelineReadinessStatus:
    """Normalize a string status into a PipelineReadinessStatus enum, default to UNKNOWN if invalid."""
    try:
        return PipelineReadinessStatus(value.upper())
    except (ValueError, AttributeError):
        return PipelineReadinessStatus.UNKNOWN


def required_statuses_for_artifact(
    expected_step_id: str,
    artifact_type: PipelineArtifactType,
) -> tuple[PipelineReadinessStatus, ...]:
    """Return statuses that satisfy a required gate for a step/type pair."""
    step_id = expected_step_id.strip()

    if step_id == "S9":
        if artifact_type == PipelineArtifactType.HUMAN_GATE:
            return (PipelineReadinessStatus.HUMAN_APPROVED,)
        return ()

    if step_id == "S10":
        if artifact_type == PipelineArtifactType.STATE_MARKER:
            return (PipelineReadinessStatus.PASS,)
        return ()

    if step_id in {"S2.3", "S2.5", "S2.7", "S2.9", "S5"}:
        if artifact_type == PipelineArtifactType.AGENT_ARTIFACT:
            return (PipelineReadinessStatus.PASS,)
        return ()

    if step_id in {"S0", "S1", "S1e", "S2", "S3", "S4", "S6", "S7", "S7b", "S8"}:
        if artifact_type == PipelineArtifactType.SCRIPT_EVIDENCE:
            return (PipelineReadinessStatus.PASS,)
        return ()

    return ()


def status_satisfies_required_gate(
    status: PipelineReadinessStatus,
    expected_step_id: str,
    artifact_type: PipelineArtifactType,
) -> bool:
    """Return True when the artifact status is valid for the required gate."""
    return status in required_statuses_for_artifact(expected_step_id, artifact_type)


def _to_jsonable_value(value: Any) -> Any:
    """Recursively convert a value to a JSON-compatible type."""
    if hasattr(value, "to_jsonable"):
        return value.to_jsonable()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _to_jsonable_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass
class ReadinessIssue:
    code: str
    severity: PipelineReadinessStatus
    message: str
    path: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "path": self.path,
        }


@dataclass
class PipelineArtifact:
    schema_version: int
    artifact_type: PipelineArtifactType
    step_id: str
    status: PipelineReadinessStatus
    betting_day: str
    run_id: str
    sport: str | None
    fixture_id: str | None
    fixture_key: str | None
    point_in_time_as_of: str | None
    source_bound: bool
    no_pick_edge_stake_coupon_emitted: bool
    production_selectable: bool
    betting_decisions_enabled: bool
    sources: tuple[str, ...]
    unknowns: tuple[str, ...]
    blocked_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    payload: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_type": self.artifact_type.value,
            "step_id": self.step_id,
            "status": self.status.value,
            "betting_day": self.betting_day,
            "run_id": self.run_id,
            "sport": self.sport,
            "fixture_id": self.fixture_id,
            "fixture_key": self.fixture_key,
            "point_in_time_as_of": self.point_in_time_as_of,
            "source_bound": self.source_bound,
            "no_pick_edge_stake_coupon_emitted": self.no_pick_edge_stake_coupon_emitted,
            "production_selectable": self.production_selectable,
            "betting_decisions_enabled": self.betting_decisions_enabled,
            "sources": list(self.sources),
            "unknowns": list(self.unknowns),
            "blocked_reasons": list(self.blocked_reasons),
            "evidence_refs": list(self.evidence_refs),
            "payload": _to_jsonable_value(self.payload),
        }


@dataclass
class GateDecision:
    gate_id: str
    target_step_id: str
    verdict: PipelineReadinessStatus
    failed_requirements: tuple[str, ...]
    warnings: tuple[str, ...]
    required_artifacts: tuple[str, ...]
    accepted_artifacts: tuple[str, ...]
    blocked_artifacts: tuple[str, ...]
    metrics: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "target_step_id": self.target_step_id,
            "verdict": self.verdict.value,
            "failed_requirements": list(self.failed_requirements),
            "warnings": list(self.warnings),
            "required_artifacts": list(self.required_artifacts),
            "accepted_artifacts": list(self.accepted_artifacts),
            "blocked_artifacts": list(self.blocked_artifacts),
            "metrics": _to_jsonable_value(self.metrics),
        }


@dataclass
class StepEvidence:
    step_id: str
    execution_mode: str
    status: PipelineReadinessStatus
    command: tuple[str, ...]
    started_at: str | None
    finished_at: str | None
    return_code: int | None
    stdout_path: str | None
    stderr_path: str | None
    artifact_path: str | None
    blocked_reason: str | None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "execution_mode": self.execution_mode,
            "status": self.status.value,
            "command": list(self.command),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "artifact_path": self.artifact_path,
            "blocked_reason": self.blocked_reason,
        }


@dataclass
class RunEvidence:
    schema_version: int
    run_id: str
    betting_day: str
    manifest_hash: str
    repo_head_sha: str
    dry_run: bool
    allow_write: bool
    status: PipelineReadinessStatus
    steps: tuple[StepEvidence, ...]
    gates: tuple[GateDecision, ...]
    failed_requirements: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "betting_day": self.betting_day,
            "manifest_hash": self.manifest_hash,
            "repo_head_sha": self.repo_head_sha,
            "dry_run": self.dry_run,
            "allow_write": self.allow_write,
            "status": self.status.value,
            "steps": [_to_jsonable_value(s) for s in self.steps],
            "gates": [_to_jsonable_value(g) for g in self.gates],
            "failed_requirements": list(self.failed_requirements),
            "warnings": list(self.warnings),
        }


@dataclass
class CentralSafetyClassification:
    production_eligibility: bool
    runtime_classification: str
    contamination_reasons: list[str]
    betting_valid: bool
    can_place_bet_now: bool
    safe_user_action: str

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "production_eligibility": self.production_eligibility,
            "runtime_classification": self.runtime_classification,
            "contamination_reasons": self.contamination_reasons,
            "betting_valid": self.betting_valid,
            "can_place_bet_now": self.can_place_bet_now,
            "safe_user_action": self.safe_user_action,
        }


from bet.pipeline.contracts.base import StrictBaseModel


class ModelPackageV1(StrictBaseModel):
    package_id: str
    sport: str
    competition: str
    market: str
    model_package_path: str
    model_package_sha256: str
    dataset_receipt_sha256: str
    feature_schema_sha256: str
    fitted_model_sha256: str
    code_receipt_sha256: str
    temporal_split_sha256: str
    backtest_report_sha256: str
    calibration_report_sha256: str
    uncertainty_method_sha256: str
    promotion_decision_sha256: str
    model_card_sha256: str
    is_eligible: bool = True


class ModelPackageResolver:
    """Semantic model package resolver for single-market pricing models."""

    REQUIRED_FILES = (
        "model-package.json",
        "dataset-receipt.json",
        "feature-schema.json",
        "code-receipt.json",
        "temporal-split.json",
        "backtest.json",
        "calibration.json",
        "uncertainty-method.json",
        "promotion-decision.json",
        "model-card.json",
    )

    APPROVED_MODEL_STORES = (
        "models",
        ".kilo/artifacts/models",
        "data/models",
    )

    @classmethod
    def resolve_package(cls, package_dir: str | Path) -> ModelPackageV1 | None:
        p = Path(package_dir).resolve(strict=False)
        if not p.is_dir():
            return None

        # Verify package root is inside an approved model store directory
        repo_root = Path(__file__).resolve().parents[3]
        approved_paths = [repo_root / rel for rel in cls.APPROVED_MODEL_STORES]
        is_approved = any(p == store or p.is_relative_to(store) for store in approved_paths if store.exists())
        if not is_approved:
            return None

        for fname in cls.REQUIRED_FILES:
            file_path = p / fname
            if not file_path.is_file() or file_path.is_symlink():
                return None

        try:
            meta = json.loads((p / "model-package.json").read_text(encoding="utf-8"))
            prom = json.loads((p / "promotion-decision.json").read_text(encoding="utf-8"))
            if prom.get("status") != "PROMOTED":
                return None

            pkg_sha = meta.get("model_package_sha256") or meta.get("sha256")
            dataset_sha = meta.get("dataset_receipt_sha256")
            schema_sha = meta.get("feature_schema_sha256")
            fitted_sha = meta.get("fitted_model_sha256")
            code_sha = meta.get("code_receipt_sha256")
            split_sha = meta.get("temporal_split_sha256")
            backtest_sha = meta.get("backtest_report_sha256")
            calib_sha = meta.get("calibration_report_sha256")
            unc_sha = meta.get("uncertainty_method_sha256")
            prom_sha = meta.get("promotion_decision_sha256")
            card_sha = meta.get("model_card_sha256")

            all_shas = [pkg_sha, dataset_sha, schema_sha, fitted_sha, code_sha, split_sha, backtest_sha, calib_sha, unc_sha, prom_sha, card_sha]
            if not all(isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s) for s in all_shas):
                return None

            def check_file_sha(fname: str, expected_sha: str) -> bool:
                f_path = p / fname
                if not f_path.is_file():
                    return False
                h = hashlib.sha256()
                with f_path.open("rb") as handle:
                    while chunk := handle.read(65536):
                        h.update(chunk)
                return h.hexdigest().lower() == expected_sha.lower()

            if not check_file_sha("dataset-receipt.json", dataset_sha):
                return None
            if not check_file_sha("feature-schema.json", schema_sha):
                return None
            if not check_file_sha("code-receipt.json", code_sha):
                return None
            if not check_file_sha("temporal-split.json", split_sha):
                return None
            if not check_file_sha("backtest.json", backtest_sha):
                return None
            if not check_file_sha("calibration.json", calib_sha):
                return None
            if not check_file_sha("uncertainty-method.json", unc_sha):
                return None
            if not check_file_sha("promotion-decision.json", prom_sha):
                return None
            if not check_file_sha("model-card.json", card_sha):
                return None

            bound_hashes = prom.get("bound_artifact_hashes", {})
            if isinstance(bound_hashes, dict) and bound_hashes:
                if bound_hashes.get("dataset_receipt_sha256") != dataset_sha or bound_hashes.get("calibration_report_sha256") != calib_sha:
                    return None

            return ModelPackageV1(
                package_id=meta["package_id"],
                sport=meta["sport"],
                competition=meta["competition"],
                market=meta["market"],
                model_package_path=str(p),
                model_package_sha256=pkg_sha,
                dataset_receipt_sha256=dataset_sha,
                feature_schema_sha256=schema_sha,
                fitted_model_sha256=fitted_sha,
                code_receipt_sha256=code_sha,
                temporal_split_sha256=split_sha,
                backtest_report_sha256=backtest_sha,
                calibration_report_sha256=calib_sha,
                uncertainty_method_sha256=unc_sha,
                promotion_decision_sha256=prom_sha,
                model_card_sha256=card_sha,
                is_eligible=True,
            )
        except Exception:
            return None


class ModelCardV1(StrictBaseModel):
    package_path: str = ""
    model_package: ModelPackageV1 | None = None

    def is_pricing_eligible(self) -> bool:
        if self.model_package is not None:
            return getattr(self.model_package, "is_eligible", False) is True
        if self.package_path:
            pkg = ModelPackageResolver.resolve_package(self.package_path)
            return pkg is not None and getattr(pkg, "is_eligible", False) is True
        return False


class JointModelPackageV1(StrictBaseModel):
    package_id: str
    sport: str
    competition: str
    market_pair: tuple[str, ...]
    model_package_path: str
    calibration_report_sha256: str = ""
    is_eligible: bool = True


class JointModelPackageResolver:
    """Semantic model package resolver for joint/dependence models."""

    REQUIRED_FILES = (
        "joint-model-package.json",
        "joint-dataset-receipt.json",
        "dependence-method.json",
        "joint-backtest.json",
        "joint-calibration.json",
        "conservative-bound-method.json",
        "joint-promotion-decision.json",
    )

    APPROVED_MODEL_STORES = (
        "models",
        ".kilo/artifacts/models",
        "data/models",
    )

    @classmethod
    def resolve_package(cls, package_dir: str | Path) -> JointModelPackageV1 | None:
        p = Path(package_dir).resolve(strict=False)
        if not p.is_dir():
            return None

        repo_root = Path(__file__).resolve().parents[3]
        approved_paths = [repo_root / rel for rel in cls.APPROVED_MODEL_STORES]
        is_approved = any(p == store or p.is_relative_to(store) for store in approved_paths if store.exists())
        if not is_approved:
            return None

        for fname in cls.REQUIRED_FILES:
            file_path = p / fname
            if not file_path.is_file() or file_path.is_symlink():
                return None

        try:
            meta = json.loads((p / "joint-model-package.json").read_text(encoding="utf-8"))
            prom = json.loads((p / "joint-promotion-decision.json").read_text(encoding="utf-8"))
            if prom.get("status") != "PROMOTED":
                return None

            calib_sha = meta.get("calibration_report_sha256") or meta.get("joint_calibration_sha256")
            if not calib_sha or len(calib_sha) != 64 or not all(c in "0123456789abcdefABCDEF" for c in calib_sha):
                return None

            f_path = p / "joint-calibration.json"
            h = hashlib.sha256()
            with f_path.open("rb") as handle:
                while chunk := handle.read(65536):
                    h.update(chunk)
            if h.hexdigest().lower() != calib_sha.lower():
                return None

            return JointModelPackageV1(
                package_id=meta["package_id"],
                sport=meta["sport"],
                competition=meta["competition"],
                market_pair=tuple(meta["market_pair"]),
                model_package_path=str(p),
                calibration_report_sha256=calib_sha,
                is_eligible=True,
            )
        except Exception:
            return None


class JointModelScopeV1(StrictBaseModel):
    package_path: str = ""
    joint_package: JointModelPackageV1 | None = None
    calibration_file_path: str = ""

    def is_pricing_eligible(self) -> bool:
        if self.joint_package is not None:
            return getattr(self.joint_package, "is_eligible", False) is True
        if self.package_path:
            pkg = JointModelPackageResolver.resolve_package(self.package_path)
            return pkg is not None and getattr(pkg, "is_eligible", False) is True
        return False


class ProbabilityEstimateV2(StrictBaseModel):
    candidate_id: str
    derived_probability: float
    uncertainty_margin: float
    model_package_id: str
    model_package_sha256: str

    @classmethod
    def create(
        cls,
        *,
        candidate_id: str,
        model_package: ModelPackageV1,
        prediction_result: dict[str, Any],
        **kwargs: Any,
    ) -> ProbabilityEstimateV2:
        if "calibrated_probability" in kwargs or "uncertainty_margin" in kwargs or "caller_provided_probability" in kwargs:
            raise ValueError("CALLER_PROBABILITY_FORBIDDEN: probability and uncertainty margin must be derived by model package")
        if not model_package or getattr(model_package, "is_eligible", False) is False:
            raise ValueError("MODEL_NOT_ELIGIBLE: cannot create probability estimate without an eligible model package")
        prob = float(prediction_result["derived_probability"])
        margin = float(prediction_result["uncertainty_margin"])
        return cls(
            candidate_id=candidate_id,
            derived_probability=prob,
            uncertainty_margin=margin,
            model_package_id=model_package.package_id,
            model_package_sha256=model_package.model_package_sha256,
        )


def get_central_safety_classification(
    state_or_payload: Any = None,
    extra_reasons: list[str] | None = None
) -> CentralSafetyClassification:
    import os
    reasons = []
    classification = "PRODUCTION_STABLE"

    # 1. Environment & CLI flags
    if os.environ.get("BET_MOCK_ODDS"):
        reasons.append("BET_MOCK_ODDS is active in environment")
    if os.environ.get("BET_PIPELINE_SKIP_FETCH"):
        reasons.append("BET_PIPELINE_SKIP_FETCH is active in environment")
    if os.environ.get("BET_MOCK_DATA_QUALITY"):
        reasons.append("BET_MOCK_DATA_QUALITY is active in environment")
    if os.environ.get("BET_MOCK_NOW") or os.environ.get("BET_PIPELINE_NOW"):
        reasons.append("BET_MOCK_NOW or BET_PIPELINE_NOW time override is active")
    if os.environ.get("BET_PIPELINE_PLAYBACK") or os.environ.get("BET_PLAYBACK_MODE"):
        reasons.append("Playback/replay mode is active")
    if os.environ.get("BET_NO_DB"):
        reasons.append("BET_NO_DB is active (synthetic --no-db run)")

    # 2. Check extra reasons passed down
    if extra_reasons:
        for r in extra_reasons:
            reasons.append(r)

    # 3. Recursively scan state_or_payload for mock labels, synthetic S9, and legacy shortcuts
    def scan(node: Any):
        if isinstance(node, dict):
            # Check for mock/synthetic labels
            if node.get("mock") is True or node.get("synthetic") is True or node.get("test_only") is True or node.get("agent_generated") is True:
                reasons.append(f"Synthetic/mock metadata/label detected")
            
            # Check for generated S9
            reviewed_by = str(node.get("reviewed_by_user") or "").strip().lower()
            if reviewed_by in ("shadow-acceptance", "mock", "test", "generated", "synthetic"):
                reasons.append(f"Generated S9 evidence reviewed by user: {reviewed_by}")
            
            # Check for generated S9 status
            status_val = str(node.get("status") or "").strip().upper()
            if status_val in ("TEST_ONLY_GENERATED_S9", "TEST_ONLY_GENERATED_HUMAN_GATE"):
                reasons.append(f"S9 status is generated/mock: {status_val}")

            # Legacy operator evidence is contamination regardless of runtime.
            force_scan = os.environ.get("BET_FORCE_MAGIC_VALUE_SCAN") == "True"

            if (
                "legacy_operator_manual_verification" in node
                or str(node.get("operator_workflow") or "") not in {"", "SUPERBET_MANUAL_BET_BUILDER"}
            ):
                reasons.append("Legacy operator validation or shortcut detected")

            # Magic values are diagnostic-only unless explicitly enabled.
            for k, v in node.items():
                if force_scan:
                    if k in ("probability", "safety_score") and (v == 0.85 or str(v) == "0.85"):
                        reasons.append("Magic mock value 0.85 detected in probability or safety_score")
                    if k in ("odds_decimal", "best_odds") and (v == 2.10 or str(v) == "2.10" or v == 2.1 or str(v) == "2.1"):
                        reasons.append("Magic mock value 2.10 detected in odds_decimal or best_odds")
                    if k == "ev" and (v == 0.15 or str(v) == "0.15"):
                        reasons.append("Magic mock value 0.15 detected in ev")
                
                scan(v)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    if state_or_payload is not None:
        scan(state_or_payload)

    # Clean up reasons to be unique
    unique_reasons = []
    for r in reasons:
        if r not in unique_reasons:
            unique_reasons.append(r)

    is_contaminated = len(unique_reasons) > 0

    if is_contaminated:
        # Determine specific classification
        has_mock_odds = any("MOCK_ODDS" in r or "2.10" in r for r in unique_reasons)
        has_time_override = any("time override" in r or "Playback" in r for r in unique_reasons)
        has_generated_s9 = any("Generated S9" in r or "S9 status" in r for r in unique_reasons)
        has_legacy_operator = any("Legacy" in r for r in unique_reasons)

        if has_mock_odds:
            classification = "TEST_ONLY_MOCK_ODDS"
        elif has_time_override:
            classification = "TEST_ONLY_TIME_OVERRIDE"
        elif has_generated_s9:
            classification = "TEST_ONLY_GENERATED_S9"
        elif has_legacy_operator:
            classification = "TEST_ONLY_LEGACY_OPERATOR_VALIDATION"
        else:
            classification = "TEST_ONLY_SYNTHETIC_INPUT"

        return CentralSafetyClassification(
            production_eligibility=False,
            runtime_classification=classification,
            contamination_reasons=unique_reasons,
            betting_valid=False,
            can_place_bet_now=False,
            safe_user_action="DO_NOT_PLACE_BET"
        )
    else:
        return CentralSafetyClassification(
            production_eligibility=True,
            runtime_classification="PRODUCTION_STABLE",
            contamination_reasons=[],
            betting_valid=False,
            can_place_bet_now=False,
            safe_user_action="CONTINUE_ANALYSIS_OR_REQUEST_MANUAL_QUOTE"
        )
