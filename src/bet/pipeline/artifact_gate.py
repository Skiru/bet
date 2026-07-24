"""Pipeline artifact gate - validates and checks upstream artifact readiness."""
from __future__ import annotations

import os
import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.pipeline.readiness_contracts import (
    CentralSafetyClassification,
    PipelineArtifact,
    PipelineArtifactType,
    PipelineReadinessStatus,
    GateDecision,
    ReadinessIssue,
    ForbiddenDecisionSignal,
    AllowedNegativeAssertionKeys,
    normalize_status,
    required_statuses_for_artifact,
    status_blocks,
    status_satisfies_required_gate,
    get_central_safety_classification,
)


FORBIDDEN_DECISION_KEYS = {
    ForbiddenDecisionSignal.PICK.value,
    ForbiddenDecisionSignal.PICKS.value,
    ForbiddenDecisionSignal.SELECTION.value,
    ForbiddenDecisionSignal.SELECTIONS.value,
    ForbiddenDecisionSignal.BET.value,
    ForbiddenDecisionSignal.BETTING_DECISION.value,
    ForbiddenDecisionSignal.EDGE.value,
    ForbiddenDecisionSignal.EXPECTED_VALUE.value,
    ForbiddenDecisionSignal.STAKE.value,
    ForbiddenDecisionSignal.COUPON.value,
    ForbiddenDecisionSignal.ACCUMULATOR.value,
    ForbiddenDecisionSignal.PARLAY.value,
}

ALLOWED_NEGATIVE_ASSERTION_KEYS = {item.value for item in AllowedNegativeAssertionKeys}

FORBIDDEN_DECISION_PHRASES = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\brecommended\s+pick\b",
        r"\bpick\s*:",
        r"\bstake\s*:",
        r"\bedge\s*:",
        r"\bexpected\s+value\s*:",
        r"\bcoupon\s*:",
        r"\bparlay\b",
        r"\baccumulator\b",
    )
)

ALLOWED_SECRET_METADATA_KEYS = {
    "provider_authorization",
    "provider_authorization_status",
    "authorization_status",
    "authorized_for_sanitized_live_probe",
}

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTECTED_REPO_DRAFT_DIRS = (
    REPO_ROOT / "betting" / "data",
    REPO_ROOT / "betting" / "coupons",
    REPO_ROOT / "betting" / "journal",
    REPO_ROOT / "reports",
)

FORBIDDEN_SECRET_KEYS = {
    "api_key",
    "apikey",
    "secret",
    "password",
    "access_token",
    "refresh_token",
    "bearer_token",
    "authorization_header",
    "auth_header",
    "http_authorization",
}


def _has_placeholder(node: Any, is_pass_status: bool = False) -> str | None:
    if isinstance(node, str):
        s = node.strip()
        if s.startswith("TODO_") or s in (
            "TODO_FILL_BY_AGENT",
            "NOT_FINAL_TEMPLATE",
            "TEMPLATE_NOT_FILLED",
        ):
            return f"placeholder value found: '{node}'"
    elif isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str):
                ks = k.strip()
                if ks.startswith("TODO_") or ks in (
                    "TODO_FILL_BY_AGENT",
                    "NOT_FINAL_TEMPLATE",
                    "TEMPLATE_NOT_FILLED",
                ):
                    return f"placeholder key found: '{k}'"
                if is_pass_status and ks in ("template_status", "approval_state"):
                    return f"template-only key '{k}' forbidden in PASS artifacts"
            res = _has_placeholder(v, is_pass_status)
            if res:
                return res
    elif isinstance(node, (list, tuple, set)):
        for item in node:
            res = _has_placeholder(item, is_pass_status)
            if res:
                return res
    return None


def _normalize_key(key: str) -> str:
    return str(key).strip().lower().replace("-", "_").replace(".", "_")


def _is_forbidden_decision_key(key: str) -> bool:
    normalized = _normalize_key(key)
    if normalized in ALLOWED_NEGATIVE_ASSERTION_KEYS:
        return False
    return normalized in FORBIDDEN_DECISION_KEYS


def _string_has_forbidden_decision_phrase(value: str) -> bool:
    return any(pattern.search(value) for pattern in FORBIDDEN_DECISION_PHRASES)


def _is_secret_key(key: str) -> bool:
    normalized = _normalize_key(key)
    if normalized in ALLOWED_SECRET_METADATA_KEYS:
        return False
    return normalized in FORBIDDEN_SECRET_KEYS


def load_artifact(path: Path) -> dict[str, Any]:
    """Load and parse artifact JSON from path. Fails closed on any error."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Artifact file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in artifact {path}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to read artifact {path}: {e}")

    if not isinstance(data, dict):
        raise ValueError(f"Artifact JSON top-level must be an object at {path}")

    return data


def expected_s8_coupon_draft_path(base_dir: Path, betting_day: str, run_id: str) -> Path:
    return (
        Path(base_dir)
        / "pipeline_runs"
        / betting_day
        / run_id
        / "data"
        / f"{betting_day}_s8_coupon_drafts.json"
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_path_for(
    base_dir: Path,
    betting_day: str,
    run_id: str,
    step_id: str,
    fixture_key: str | None = None,
) -> Path:
    """Get the canonical artifact path on disk."""
    base_dir = Path(base_dir)
    if fixture_key:
        return (
            base_dir
            / "pipeline_runs"
            / betting_day
            / run_id
            / "artifacts"
            / "fixtures"
            / fixture_key
            / f"{step_id}.json"
        )
    return (
        base_dir
        / "pipeline_runs"
        / betting_day
        / run_id
        / "artifacts"
        / f"{step_id}.json"
    )


def _path_is_within(path: Path, candidate_root: Path) -> bool:
    try:
        path.relative_to(candidate_root)
    except ValueError:
        return False
    return True


def _block_issue(code: str, message: str) -> ReadinessIssue:
    return ReadinessIssue(
        code=code,
        severity=PipelineReadinessStatus.BLOCK,
        message=message,
    )


def is_mock_value_injected(obj: Any) -> bool:
    """Run the opt-in diagnostic scan for historically injected numeric values."""
    if os.environ.get("BET_FORCE_MAGIC_VALUE_SCAN") != "True":
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("probability", "safety_score") and (v == 0.85 or str(v) == "0.85"):
                return True
            if k in ("odds_decimal", "best_odds") and (v == 2.10 or str(v) == "2.10" or v == 2.1 or str(v) == "2.1"):
                return True
            if k == "ev" and (v == 0.15 or str(v) == "0.15"):
                return True
            if is_mock_value_injected(v):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if is_mock_value_injected(item):
                return True
    return False


def _has_synthetic_provenance(obj: Any) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized = _normalize_key(str(key))
            if normalized in {"mock", "synthetic", "test_only", "agent_generated", "generated"} and value is True:
                return True
            if normalized in {"provenance", "origin", "source_type"} and any(
                marker in str(value).strip().lower()
                for marker in ("mock", "test", "synthetic", "generated", "replay", "shadow")
            ):
                return True
            if _has_synthetic_provenance(value):
                return True
    elif isinstance(obj, list):
        return any(_has_synthetic_provenance(item) for item in obj)
    return False


def _has_legacy_operator_evidence(obj: Any) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized = _normalize_key(str(key))
            if normalized.startswith("legacy_operator"):
                return True
            if normalized == "operator_workflow" and value not in {None, "", "SUPERBET_MANUAL_BET_BUILDER"}:
                return True
            if _has_legacy_operator_evidence(value):
                return True
    elif isinstance(obj, list):
        return any(_has_legacy_operator_evidence(item) for item in obj)
    return False


def _is_valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_production_s9_schema(raw: dict[str, Any]) -> list[ReadinessIssue]:
    """Validate the canonical production Superbet S9 structure."""
    issues: list[ReadinessIssue] = []
    manual_review = raw.get("manual_review")
    if not isinstance(manual_review, dict):
        return [_block_issue("MISSING_MANUAL_REVIEW", "manual_review object is required for approved S9 gate")]

    workflow = manual_review.get("operator_workflow")
    if _has_legacy_operator_evidence(raw):
        issues.append(_block_issue("LEGACY_OPERATOR_S9_FORBIDDEN", "Legacy operator fields and workflows are forbidden in production S9"))
    reviewed_by = str(manual_review.get("reviewed_by_user") or "").strip().lower()
    if (
        _has_synthetic_provenance(raw)
        or reviewed_by in {"shadow-acceptance", "mock", "test", "generated", "synthetic"}
        or normalize_status(raw.get("status")) == PipelineReadinessStatus.TEST_ONLY_GENERATED_HUMAN_GATE
    ):
        issues.append(_block_issue("TEST_ONLY_GENERATED_HUMAN_GATE", "Generated/test S9 cannot satisfy a production gate"))
    if not workflow:
        issues.append(_block_issue("MISSING_S9_OPERATOR_WORKFLOW", "S9 operator_workflow is required"))
    elif workflow != "SUPERBET_MANUAL_BET_BUILDER":
        issues.append(_block_issue("INVALID_S9_WORKFLOW", "S9 operator_workflow must be SUPERBET_MANUAL_BET_BUILDER"))
    if manual_review.get("approval_origin") != "HUMAN_OPERATOR":
        issues.append(_block_issue("INVALID_S9_ORIGIN", "S9 approval_origin must be HUMAN_OPERATOR"))
    if not str(manual_review.get("visible_operator_market_name") or "").strip():
        issues.append(_block_issue("MISSING_VISIBLE_MARKET", "S9 manual_review.visible_operator_market_name is required"))
    if manual_review.get("visible_operator_line") is None:
        issues.append(_block_issue("MISSING_VISIBLE_LINE", "S9 manual_review.visible_operator_line is required"))

    quote = manual_review.get("human_entered_decimal_quote")
    if quote is None:
        issues.append(_block_issue("MISSING_HUMAN_QUOTE", "S9 manual_review.human_entered_decimal_quote is required"))
    else:
        try:
            numeric_quote = float(quote)
            if numeric_quote <= 1.0:
                raise ValueError
        except (TypeError, ValueError):
            issues.append(_block_issue("INVALID_HUMAN_QUOTE", "S9 human_entered_decimal_quote must be numeric and greater than 1.0"))

    if not _is_valid_timestamp(manual_review.get("quote_as_of")):
        issues.append(_block_issue("MISSING_QUOTE_AS_OF", "S9 manual_review.quote_as_of must be a valid timestamp"))
    if not (manual_review.get("source_candidate_id") or manual_review.get("source_quote_card_id")):
        issues.append(_block_issue("MISSING_SOURCE_ID", "S9 manual_review.source_candidate_id or source_quote_card_id is required"))
    if not manual_review.get("explicit_operator_decision"):
        issues.append(_block_issue("MISSING_DECISION", "S9 manual_review.explicit_operator_decision is required"))

    checksum = raw.get("checksum") or manual_review.get("checksum")
    if not isinstance(checksum, str) or re.fullmatch(r"[0-9a-fA-F]{64}", checksum) is None:
        issues.append(_block_issue("MISSING_CHECKSUM", "S9 checksum must be a 64-character SHA256 value"))
    for field, code in (
        ("reviewed_by_user", "INVALID_REVIEWED_BY_USER"),
        ("reviewed_at_utc", "INVALID_REVIEWED_AT_UTC"),
        ("coupon_draft_path", "INVALID_COUPON_DRAFT_PATH"),
        ("coupon_draft_sha256", "INVALID_COUPON_DRAFT_SHA256"),
    ):
        if not isinstance(manual_review.get(field), str) or not manual_review[field].strip():
            issues.append(_block_issue(code, f"manual_review.{field} must be non-empty"))
    return issues


def validate_s9_human_gate_artifact_for_run(
    raw: dict[str, Any],
    *,
    base_dir: Path,
    betting_day: str,
    run_id: str,
) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []

    # Detect if S9 is generated or mock odds are active
    is_mock_env = os.environ.get("BET_MOCK_ODDS") or os.environ.get("BET_PIPELINE_SKIP_FETCH")
    manual_review = raw.get("manual_review") or {}
    reviewed_by = str(manual_review.get("reviewed_by_user") or "").strip().lower()

    # Pre-read referenced S8 coupon draft (if path is provided) to check for mock injection
    has_mock_draft = False
    coupon_draft_path_value = manual_review.get("coupon_draft_path")
    if coupon_draft_path_value:
        try:
            supplied_path = Path(coupon_draft_path_value)
            # Find the expected S8 path and resolve it
            expected_path = expected_s8_coupon_draft_path(base_dir, betting_day, run_id)
            if expected_path.exists():
                draft_content = json.loads(expected_path.read_text(encoding="utf-8"))
                if is_mock_value_injected(draft_content):
                    has_mock_draft = True
        except Exception:
            pass

    is_generated = (
        is_mock_env
        or has_mock_draft
        or reviewed_by in ("shadow-acceptance", "mock", "test", "generated", "synthetic")
        or raw.get("status") == "TEST_ONLY_GENERATED_HUMAN_GATE"
        or _has_synthetic_provenance(raw)
        or is_mock_value_injected(raw)
    )

    if is_generated:
        raw["status"] = "TEST_ONLY_GENERATED_HUMAN_GATE"
        raw["can_place_bet_now"] = False
        raw["safe_user_action"] = "DO_NOT_PLACE_BET"
        issues.append(
            _block_issue(
                "TEST_ONLY_GENERATED_HUMAN_GATE",
                "S9 is a generated/test-only human gate and is not valid for live betting",
            )
        )

    if raw.get("artifact_type") != PipelineArtifactType.HUMAN_GATE.value:
        issues.append(_block_issue("INVALID_S9_ARTIFACT_TYPE", "S9 artifact_type must be HUMAN_GATE"))
    if raw.get("step_id") != "S9":
        issues.append(_block_issue("INVALID_S9_STEP_ID", "S9 step_id must be S9"))

    expected_status = PipelineReadinessStatus.HUMAN_APPROVED
    if is_generated:
        expected_status = PipelineReadinessStatus.TEST_ONLY_GENERATED_HUMAN_GATE

    if normalize_status(raw.get("status")) not in (PipelineReadinessStatus.HUMAN_APPROVED, PipelineReadinessStatus.TEST_ONLY_GENERATED_HUMAN_GATE):
        issues.append(_block_issue("INVALID_S9_STATUS", "S9 status must be HUMAN_APPROVED or TEST_ONLY_GENERATED_HUMAN_GATE"))

    manual_review = raw.get("manual_review")
    if not isinstance(manual_review, dict):
        issues.append(_block_issue("MISSING_MANUAL_REVIEW", "manual_review object is required for approved S9 gate"))
        return issues

    issues.extend(validate_production_s9_schema(raw))
    coupon_draft_path_value = manual_review.get("coupon_draft_path")
    coupon_draft_sha256 = manual_review.get("coupon_draft_sha256")

    # Generated gates remain eligible for paper-only binding checks, never production progression.
    if any(issue.code != "TEST_ONLY_GENERATED_HUMAN_GATE" for issue in issues):
        return issues

    expected_path = expected_s8_coupon_draft_path(base_dir, betting_day, run_id)
    expected_resolved = expected_path.resolve(strict=False)
    supplied_path = Path(coupon_draft_path_value)
    supplied_resolved = supplied_path.resolve(strict=False)

    for protected_dir in PROTECTED_REPO_DRAFT_DIRS:
        if _path_is_within(supplied_resolved, protected_dir.resolve(strict=False)):
            issues.append(
                _block_issue(
                    "PROTECTED_COUPON_DRAFT_PATH",
                    f"manual_review.coupon_draft_path cannot be under protected repo path: {supplied_resolved}",
                )
            )
            break

    if supplied_resolved != expected_resolved:
        issues.append(
            _block_issue(
                "MISMATCH_COUPON_DRAFT_PATH",
                (
                    "manual_review.coupon_draft_path must resolve exactly to "
                    f"{expected_resolved}, got {supplied_resolved}"
                ),
            )
        )

    if not expected_path.exists():
        issues.append(_block_issue("MISSING_S8_COUPON_DRAFT", f"S8 coupon draft file not found: {expected_path}"))
        return issues

    try:
        draft = load_artifact(expected_path)
    except ValueError as exc:
        issues.append(_block_issue("INVALID_S8_COUPON_DRAFT_JSON", f"S8 coupon draft JSON is invalid: {exc}"))
        return issues

    actual_sha256 = sha256_file(expected_path)
    if actual_sha256 != coupon_draft_sha256:
        issues.append(
            _block_issue(
                "MISMATCH_COUPON_DRAFT_SHA256",
                (
                    "manual_review.coupon_draft_sha256 must match the canonical S8 draft file "
                    f"SHA256: expected {actual_sha256}, got {coupon_draft_sha256}"
                ),
            )
        )

    checksum = raw.get("checksum") or manual_review.get("checksum")
    if checksum != actual_sha256:
        issues.append(_block_issue("INVALID_S9_CHECKSUM", "S9 checksum must match the canonical S8 coupon draft SHA256"))

    required_draft_fields: tuple[tuple[str, Any], ...] = (
        ("betting_day", betting_day),
        ("run_id", run_id),
        ("requires_human_gate", True),
        ("ready_for_human_gate", True),
        ("ready_for_production_execution", False),
        ("production_selectable", False),
        ("production_coupon_write", False),
        ("executable_coupon", False),
    )
    if draft.get("artifact_type") not in {"S8_COUPON_DRAFTS", "S8_SUPERBET_MANUAL_QUOTE_PACK"}:
        issues.append(_block_issue("INVALID_S8_DRAFT_ARTIFACT_TYPE", "S9 must bind to a canonical S8 quote artifact"))
    for field_name, expected_value in required_draft_fields:
        if draft.get(field_name) != expected_value:
            issues.append(
                _block_issue(
                    f"INVALID_S8_DRAFT_{field_name.upper()}",
                    f"S8 coupon draft field {field_name} must equal {expected_value!r}",
                )
            )

    if draft.get("artifact_type") == "S8_SUPERBET_MANUAL_QUOTE_PACK":
        if draft.get("operator_workflow") != "SUPERBET_MANUAL_BET_BUILDER":
            issues.append(_block_issue("INVALID_S8_OPERATOR_WORKFLOW", "S8 quote pack must use manual Superbet Bet Builder"))
        if draft.get("operator_automation_enabled") is not False:
            issues.append(_block_issue("INVALID_S8_OPERATOR_AUTOMATION", "S8 quote pack must disable operator automation"))

    count_field = "quote_card_count" if draft.get("artifact_type") == "S8_SUPERBET_MANUAL_QUOTE_PACK" else "coupon_draft_count"
    coupon_draft_count = draft.get(count_field)
    if isinstance(coupon_draft_count, bool) or not isinstance(coupon_draft_count, int) or coupon_draft_count < 0:
        issues.append(
            _block_issue(
                "INVALID_S8_DRAFT_COUPON_DRAFT_COUNT",
                f"S8 quote artifact field {count_field} must be an integer >= 0",
            )
        )

    source_id = manual_review.get("source_candidate_id") or manual_review.get("source_quote_card_id")
    if source_id and str(source_id) not in _collect_binding_ids(draft):
        issues.append(_block_issue("INVALID_S9_SOURCE_BINDING", "S9 source candidate/card ID is not present in the canonical S8 draft"))

    return issues


def _collect_binding_ids(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            normalized = _normalize_key(str(key))
            if normalized == "id" or normalized.endswith("_id"):
                if value is not None:
                    found.add(str(value))
            found.update(_collect_binding_ids(value))
    elif isinstance(node, list):
        for value in node:
            found.update(_collect_binding_ids(value))
    return found


def get_final_betting_readiness(
    *,
    base_dir: Path,
    betting_day: str,
    run_id: str,
) -> CentralSafetyClassification:
    """Return placement readiness only after every production gate is verified."""
    loaded: dict[str, dict[str, Any]] = {}
    for step_id in ("S7", "S7b", "S9"):
        path = artifact_path_for(base_dir, betting_day, run_id, step_id)
        if not path.exists():
            return get_central_safety_classification()
        try:
            loaded[step_id] = load_artifact(path)
        except ValueError:
            return get_central_safety_classification()

    draft_path = expected_s8_coupon_draft_path(base_dir, betting_day, run_id)
    if not draft_path.exists():
        return get_central_safety_classification()
    try:
        draft = load_artifact(draft_path)
    except ValueError:
        return get_central_safety_classification()

    safety = get_central_safety_classification({"artifacts": loaded, "s8_draft": draft})
    if not safety.production_eligibility:
        return safety

    for step_id in ("S7", "S7b"):
        artifact, issues = validate_pipeline_artifact(loaded[step_id], step_id)
        if artifact is None or any(issue.severity == PipelineReadinessStatus.BLOCK for issue in issues):
            return safety

    s9_artifact, generic_issues = validate_pipeline_artifact(loaded["S9"], "S9")
    detailed_issues = validate_s9_human_gate_artifact_for_run(
        loaded["S9"], base_dir=base_dir, betting_day=betting_day, run_id=run_id
    )
    if (
        s9_artifact is None
        or generic_issues
        or detailed_issues
        or draft.get("coupon_draft_count", 0) <= 0
    ):
        return safety

    return CentralSafetyClassification(
        production_eligibility=True,
        runtime_classification="PRODUCTION_STABLE",
        contamination_reasons=[],
        betting_valid=True,
        can_place_bet_now=True,
        safe_user_action="MANUAL_PLACEMENT_ALLOWED",
    )


def find_forbidden_decision_signals(payload: Any, path: str = "$") -> list[str]:
    """Recursively search payload for forbidden betting decision keys and phrases."""
    found: list[str] = []

    def recurse(node: Any, current_path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{current_path}.{key}"
                if _is_forbidden_decision_key(str(key)):
                    found.append(f"{child_path}: forbidden decision key '{key}'")
                recurse(value, child_path)
            return

        if isinstance(node, list):
            for idx, item in enumerate(node):
                recurse(item, f"{current_path}[{idx}]")
            return

        if isinstance(node, str) and _string_has_forbidden_decision_phrase(node):
            found.append(f"{current_path}: forbidden decision phrase")

    recurse(payload, path)
    return found


def find_s5_forbidden_execution_signals(raw: dict[str, Any]) -> list[str]:
    """Allow analytical selection/EV facts while blocking execution advice."""
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return find_forbidden_decision_signals(raw)
    candidate_keys = {"candidates", "rejected_candidates"}
    scan_raw = dict(raw)
    scan_raw["payload"] = {
        key: value for key, value in payload.items() if key not in candidate_keys
    }
    found = find_forbidden_decision_signals(scan_raw)
    execution_keys = {
        "internal_pick",
        "recommended_pick",
        "stake",
        "staking",
        "stake_decimal",
        "coupon",
        "parlay",
        "accumulator",
        "betting_decision",
        "executable_coupon",
        "can_place_bet_now",
    }
    for category in candidate_keys:
        records = payload.get(category, [])
        if not isinstance(records, list):
            continue
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            for key in record:
                if _normalize_key(str(key)) in execution_keys:
                    found.append(
                        f"$.payload.{category}[{index}].{key}: forbidden execution key '{key}'"
                    )
    return found


def detect_secrets(node: Any, path: str = "$") -> list[str]:
    """Recursively check for forbidden secret/header keys without substring false positives."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            if _is_secret_key(str(key)) and value not in (None, "", False):
                found.append(child_path)
            found.extend(detect_secrets(value, child_path))
        return found

    if isinstance(node, list):
        for idx, item in enumerate(node):
            found.extend(detect_secrets(item, f"{path}[{idx}]"))
    return found


def validate_pipeline_artifact(
    raw: dict[str, Any],
    expected_step_id: str,
    *,
    enforce_required_gate: bool = True,
    allow_block_status: bool = False,
) -> tuple[PipelineArtifact | None, list[ReadinessIssue]]:
    """Validate a loaded raw artifact dict against schemas and safety constraints."""
    issues: list[ReadinessIssue] = []
    is_current_step_block = False

    # 1. schema_version check
    if "schema_version" not in raw:
        issues.append(
            ReadinessIssue(
                code="MISSING_SCHEMA_VERSION",
                severity=PipelineReadinessStatus.BLOCK,
                message="schema_version is required",
            )
        )
    else:
        try:
            sv = int(raw["schema_version"])
            if sv < 1:
                issues.append(
                    ReadinessIssue(
                        code="INVALID_SCHEMA_VERSION",
                        severity=PipelineReadinessStatus.BLOCK,
                        message="schema_version must be >= 1",
                    )
                )
        except (ValueError, TypeError):
            issues.append(
                ReadinessIssue(
                    code="INVALID_SCHEMA_VERSION_TYPE",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="schema_version must be an integer",
                )
            )

    # 2. artifact_type check
    art_type = None
    if "artifact_type" not in raw:
        issues.append(
            ReadinessIssue(
                code="MISSING_ARTIFACT_TYPE",
                severity=PipelineReadinessStatus.BLOCK,
                message="artifact_type is required",
            )
        )
    else:
        try:
            art_type = PipelineArtifactType(raw["artifact_type"])
        except ValueError:
            issues.append(
                ReadinessIssue(
                    code="INVALID_ARTIFACT_TYPE",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"Invalid artifact_type: {raw['artifact_type']}",
                )
            )

    # 3. step_id check
    if "step_id" not in raw:
        issues.append(
            ReadinessIssue(
                code="MISSING_STEP_ID",
                severity=PipelineReadinessStatus.BLOCK,
                message="step_id is required",
            )
        )
    elif raw["step_id"] != expected_step_id:
        issues.append(
            ReadinessIssue(
                code="MISMATCH_STEP_ID",
                severity=PipelineReadinessStatus.BLOCK,
                message=f"Expected step_id {expected_step_id}, got {raw['step_id']}",
            )
        )

    # 4. status check
    status_val = PipelineReadinessStatus.UNKNOWN
    if "status" not in raw:
        issues.append(
            ReadinessIssue(
                code="MISSING_STATUS",
                severity=PipelineReadinessStatus.BLOCK,
                message="status is required",
            )
        )
    else:
        status_val = normalize_status(raw["status"])
        is_current_step_block = allow_block_status and status_val in (PipelineReadinessStatus.BLOCK, PipelineReadinessStatus.COMMAND_REQUEST)
        if status_blocks(status_val) and not (allow_block_status and status_val in (PipelineReadinessStatus.BLOCK, PipelineReadinessStatus.COMMAND_REQUEST)):
            issues.append(
                ReadinessIssue(
                    code="BLOCKING_STATUS",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"Artifact status is blocking: {status_val.value}",
                )
            )
    if enforce_required_gate and art_type is not None and not status_satisfies_required_gate(status_val, expected_step_id, art_type):
        allowed_statuses = [status.value for status in required_statuses_for_artifact(expected_step_id, art_type)]
        issues.append(
            ReadinessIssue(
                code="INVALID_REQUIRED_ARTIFACT_STATUS",
                severity=PipelineReadinessStatus.BLOCK,
                message=(
                    f"Artifact {expected_step_id}/{art_type.value} requires one of {allowed_statuses}, "
                    f"got {status_val.value}"
                ),
            )
        )

    # 5. point_in_time_as_of check
    if art_type == PipelineArtifactType.AGENT_ARTIFACT and not is_current_step_block:
        if not raw.get("point_in_time_as_of"):
            issues.append(
                ReadinessIssue(
                    code="MISSING_POINT_IN_TIME",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="point_in_time_as_of is required for agent artifacts",
                )
            )

    # S9 uses the same canonical structural validator as run-bound validation.
    if expected_step_id == "S9" and status_val == PipelineReadinessStatus.HUMAN_APPROVED:
        issues.extend(validate_production_s9_schema(raw))

    # 6. enrichment specific checks (S2.3, S2.5, S2.7, S2.9)
    is_enrichment = expected_step_id in ("S2.3", "S2.5", "S2.7", "S2.9")
    if is_enrichment and not is_current_step_block:
        if raw.get("source_bound") is not True:
            issues.append(
                ReadinessIssue(
                    code="SOURCE_BOUND_REQUIRED",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="source_bound must be true for enrichment artifacts",
                )
            )
        if raw.get("no_pick_edge_stake_coupon_emitted") is not True:
            issues.append(
                ReadinessIssue(
                    code="NO_PICK_EDGE_STAKE_COUPON_EMITTED_REQUIRED",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="no_pick_edge_stake_coupon_emitted must be true for enrichment artifacts",
                )
            )
        if raw.get("production_selectable") is not False:
            issues.append(
                ReadinessIssue(
                    code="PRODUCTION_SELECTABLE_FORBIDDEN",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="production_selectable must be false for enrichment artifacts",
                )
            )
        if raw.get("betting_decisions_enabled") is not False:
            issues.append(
                ReadinessIssue(
                    code="BETTING_DECISIONS_ENABLED_FORBIDDEN",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="betting_decisions_enabled must be false for enrichment artifacts",
                )
            )

    # 7. Recursive forbidden signals & raw secrets
    payload = raw.get("payload", {})
    signals = (
        find_s5_forbidden_execution_signals(raw)
        if expected_step_id == "S5"
        else find_forbidden_decision_signals(raw)
    )
    if signals:
        issues.append(
            ReadinessIssue(
                code="FORBIDDEN_DECISION_SIGNALS",
                severity=PipelineReadinessStatus.BLOCK,
                message=f"Forbidden decision signals found: {', '.join(signals)}",
            )
        )

    secrets = detect_secrets(raw)
    if secrets:
        issues.append(
            ReadinessIssue(
                code="RAW_SECRETS_FOUND",
                severity=PipelineReadinessStatus.BLOCK,
                message=f"Obvious secret fields detected: {', '.join(secrets)}",
            )
        )

    if status_val in (PipelineReadinessStatus.PASS, PipelineReadinessStatus.HUMAN_APPROVED):
        ph_err = _has_placeholder(raw, is_pass_status=True)
        if ph_err:
            issues.append(
                ReadinessIssue(
                    code="PLACEHOLDER_DATA_FOUND",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"Placeholder data found in PASS artifact: {ph_err}",
                )
            )

    # 8. List/tuple verification
    if art_type == PipelineArtifactType.AGENT_ARTIFACT:
        if "sources" not in raw:
            issues.append(
                ReadinessIssue(
                    code="MISSING_SOURCES",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="sources is required for agent artifacts",
                )
            )
        elif not isinstance(raw["sources"], (list, tuple)):
            issues.append(
                ReadinessIssue(
                    code="INVALID_SOURCES_FORMAT",
                    severity=PipelineReadinessStatus.BLOCK,
                    message="sources must be a list or tuple",
                )
            )

    for field_name in ("unknowns", "blocked_reasons", "evidence_refs"):
        if field_name in raw and not isinstance(raw[field_name], (list, tuple)):
            issues.append(
                ReadinessIssue(
                    code=f"INVALID_{field_name.upper()}_FORMAT",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"{field_name} must be a list or tuple",
                )
            )

    # Try building PipelineArtifact
    artifact = None
    if not any(i.severity == PipelineReadinessStatus.BLOCK for i in issues):
        try:
            artifact = PipelineArtifact(
                schema_version=int(raw.get("schema_version", 1)),
                artifact_type=PipelineArtifactType(raw.get("artifact_type", "AGENT_ARTIFACT")),
                step_id=str(raw.get("step_id", expected_step_id)),
                status=status_val,
                betting_day=str(raw.get("betting_day", "")),
                run_id=str(raw.get("run_id", "")),
                sport=raw.get("sport"),
                fixture_id=raw.get("fixture_id"),
                fixture_key=raw.get("fixture_key"),
                point_in_time_as_of=raw.get("point_in_time_as_of"),
                source_bound=bool(raw.get("source_bound", False)),
                no_pick_edge_stake_coupon_emitted=bool(raw.get("no_pick_edge_stake_coupon_emitted", False)),
                production_selectable=bool(raw.get("production_selectable", False)),
                betting_decisions_enabled=bool(raw.get("betting_decisions_enabled", False)),
                sources=tuple(raw.get("sources", ())),
                unknowns=tuple(raw.get("unknowns", ())),
                blocked_reasons=tuple(raw.get("blocked_reasons", ())),
                evidence_refs=tuple(raw.get("evidence_refs", ())),
                payload=payload,
            )
        except Exception as e:
            issues.append(
                ReadinessIssue(
                    code="CONSTRUCTION_FAILED",
                    severity=PipelineReadinessStatus.BLOCK,
                    message=f"Failed to instantiate PipelineArtifact: {e}",
                )
            )

    return artifact, issues


def required_artifacts_before_step(step_id: str) -> tuple[str, ...]:
    """Map pipeline steps to their direct prerequisite step artifacts."""
    from bet.pipeline.manifest import get_required_artifacts_before_step
    return get_required_artifacts_before_step(step_id)


def evaluate_gate_before_step(
    step_id: str, artifact_dir: Path, betting_day: str, run_id: str
) -> GateDecision:
    """Evaluate pre-requisite artifacts for a target step, returning detailed verdict."""
    req_steps = required_artifacts_before_step(step_id)
    failed_reqs = []
    warnings = []
    accepted = []
    blocked = []

    for req_step in req_steps:
        path = artifact_path_for(artifact_dir, betting_day, run_id, req_step)
        if not path.exists():
            blocked.append(req_step)
            failed_reqs.append(f"Missing required artifact for {req_step} (expected at {path})")
            continue

        try:
            raw = load_artifact(path)
            artifact, issues = validate_pipeline_artifact(raw, req_step)
            if req_step == "S2.9":
                from bet.pipeline.agent_work_orders import work_order_path_for
                from bet.pipeline.agent_artifact_contracts import validate_agent_artifact_for_work_order
                wo_path = work_order_path_for(artifact_dir, betting_day, run_id, "S2.9")
                if not wo_path.exists():
                    failed_reqs.append(f"Missing S2.9 work order at {wo_path}")
                    blocked.append(req_step)
                else:
                    try:
                        with wo_path.open("r", encoding="utf-8") as f:
                            wo_data = json.load(f)
                        wo_errors = validate_agent_artifact_for_work_order(raw, wo_data)
                        if wo_errors:
                            for err in wo_errors:
                                failed_reqs.append(f"S2.9 work order semantic validation failure: {err}")
                            blocked.append(req_step)
                    except Exception as exc:
                        failed_reqs.append(f"Failed to load or validate S2.9 work order: {exc}")
                        blocked.append(req_step)
            if req_step == "S9":
                issues.extend(
                    validate_s9_human_gate_artifact_for_run(
                        raw,
                        base_dir=artifact_dir,
                        betting_day=betting_day,
                        run_id=run_id,
                    )
                )
        except Exception as e:
            blocked.append(req_step)
            failed_reqs.append(f"Malformed or unreadable artifact for {req_step}: {e}")
            continue

        block_issues = [i for i in issues if i.severity == PipelineReadinessStatus.BLOCK]
        warn_issues = [i for i in issues if i.severity == PipelineReadinessStatus.WARN]

        if block_issues or artifact is None:
            blocked.append(req_step)
            for i in block_issues:
                failed_reqs.append(f"Artifact {req_step} has blocking issue: {i.message} [{i.code}]")
        else:
            accepted.append(req_step)
            for i in warn_issues:
                warnings.append(f"Artifact {req_step} has warning: {i.message} [{i.code}]")

    verdict = PipelineReadinessStatus.PASS
    if blocked or failed_reqs:
        verdict = PipelineReadinessStatus.BLOCK
    elif warnings:
        verdict = PipelineReadinessStatus.WARN

    metrics = {
        "required_count": len(req_steps),
        "accepted_count": len(accepted),
        "blocked_count": len(blocked),
    }

    return GateDecision(
        gate_id=f"gate_before_{step_id}",
        target_step_id=step_id,
        verdict=verdict,
        failed_requirements=tuple(failed_reqs),
        warnings=tuple(warnings),
        required_artifacts=req_steps,
        accepted_artifacts=tuple(accepted),
        blocked_artifacts=tuple(blocked),
        metrics=metrics,
    )
