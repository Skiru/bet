"""Full-pipeline shadow acceptance harness for non-production safety certification."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Sequence
from unittest.mock import patch

from bet.pipeline.agent_artifact_contracts import agent_artifact_template_for_step
from bet.pipeline.artifact_gate import (
    artifact_path_for,
    expected_s8_coupon_draft_path,
    evaluate_gate_before_step,
    load_artifact,
    sha256_file,
)
from bet.pipeline.integration_artifacts import write_script_evidence
from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.run_evidence import utc_now_iso, write_json_atomic
from bet.pipeline.runtime_modes import LIVE_ACK_KEY, LIVE_ACK_VALUE, RuntimeMode, parse_runtime_mode


TASK_ID = "PIPELINE_FULL_SHADOW_ACCEPTANCE_A"
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class FullShadowAcceptanceConfig:
    base_dir: Path
    betting_day: str
    run_id: str
    runtime_mode: str
    allow_live_calls: bool = False
    allow_production_execution: bool = False
    allow_repo_protected_writes: bool = False

    def normalized(self) -> "FullShadowAcceptanceConfig":
        return FullShadowAcceptanceConfig(
            base_dir=Path(self.base_dir).resolve(strict=False),
            betting_day=self.betting_day,
            run_id=self.run_id,
            runtime_mode=parse_runtime_mode(self.runtime_mode).value,
            allow_live_calls=self.allow_live_calls,
            allow_production_execution=self.allow_production_execution,
            allow_repo_protected_writes=self.allow_repo_protected_writes,
        )


@dataclass(frozen=True)
class FullShadowAcceptanceReport:
    task_id: str
    status: str
    base_dir: Path
    betting_day: str
    run_id: str
    runtime_mode: str
    pipeline_terminal_status: str
    terminal_step: str | None
    s8_coupon_draft_path: str | None
    s8_coupon_draft_sha256: str | None
    s8_coupon_draft_count: int
    s8_requires_human_gate: bool
    s8_ready_for_human_gate: bool
    s8_ready_for_production_execution: bool
    s8_production_coupon_write: bool
    s8_executable_coupon: bool
    s8_betclic_execution_enabled: bool
    s9_missing_blocks: bool
    s9_bound_approval_unblocks_s10_gate: bool
    s9_bare_tmp_approval_blocks: bool
    s9_wrong_sha_blocks: bool
    s10_gate_without_bound_s9: bool
    protected_repo_write_verdict: str
    ready_for_paper_trading: bool
    ready_for_production_execution: bool
    blockers: list[str]

    def to_jsonable(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            payload[field.name] = str(value) if isinstance(value, Path) else value
        return payload


def protected_repo_roots(repo_root: Path = REPO_ROOT) -> tuple[Path, ...]:
    root = Path(repo_root).resolve(strict=False)
    return (
        root / "betting" / "data",
        root / "betting" / "coupons",
        root / "betting" / "journal",
        root / "reports",
    )


def acceptance_base_run_dir(config: FullShadowAcceptanceConfig) -> Path:
    return Path(config.base_dir) / "pipeline_runs"


def acceptance_run_root(config: FullShadowAcceptanceConfig) -> Path:
    return acceptance_base_run_dir(config) / config.betting_day / config.run_id


def expected_acceptance_s8_draft_path(config: FullShadowAcceptanceConfig) -> Path:
    return expected_s8_coupon_draft_path(config.base_dir, config.betting_day, config.run_id)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve(strict=False).relative_to(Path(root).resolve(strict=False))
    except ValueError:
        return False
    return True


def is_protected_repo_path(path: Path | str | None, repo_root: Path = REPO_ROOT) -> bool:
    if not path:
        return False
    candidate = Path(path).resolve(strict=False)
    return any(_path_is_within(candidate, protected_root) for protected_root in protected_repo_roots(repo_root))


def validate_full_shadow_acceptance_config(
    config: FullShadowAcceptanceConfig,
    *,
    report_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    normalized = config.normalized()
    blockers: list[str] = []
    mode = parse_runtime_mode(normalized.runtime_mode)

    if mode == RuntimeMode.PRODUCTION:
        blockers.append("PRODUCTION mode is forbidden for full shadow acceptance")
    if normalized.allow_live_calls:
        blockers.append("live provider calls are forbidden for full shadow acceptance")
    if normalized.allow_production_execution:
        blockers.append("production execution must remain disabled")
    if normalized.allow_repo_protected_writes:
        blockers.append("repo protected writes must remain disabled")
    if _path_is_within(normalized.base_dir, Path(repo_root).resolve(strict=False)):
        blockers.append(f"base_dir must be outside repo root: {normalized.base_dir}")
    if report_path is not None and is_protected_repo_path(report_path, repo_root):
        blockers.append(f"report_path cannot be under protected repo-local paths: {report_path}")

    return blockers


def snapshot_paths(roots: Sequence[Path]) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for root in roots:
        resolved_root = Path(root).resolve(strict=False)
        if not resolved_root.exists():
            continue
        for path in sorted(resolved_root.rglob("*")):
            if not path.is_file():
                continue
            stat = path.stat()
            resolved_path = path.resolve(strict=False)
            snapshot[str(resolved_path)] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": sha256_file(resolved_path),
            }
    return snapshot


def snapshot_protected_repo_paths(repo_root: Path = REPO_ROOT) -> dict[str, dict[str, Any]]:
    return snapshot_paths(protected_repo_roots(repo_root))


def compare_path_snapshots(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> list[str]:
    changes: list[str] = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            changes.append(f"CREATED:{path}")
            continue
        if path not in after:
            changes.append(f"DELETED:{path}")
            continue
        if before[path] != after[path]:
            changes.append(f"MODIFIED:{path}")
    return changes


def is_run_scoped_s8_draft_path(path: Path | str | None, config: FullShadowAcceptanceConfig) -> bool:
    if not path:
        return False
    candidate = Path(path).resolve(strict=False)
    expected = expected_acceptance_s8_draft_path(config).resolve(strict=False)
    return candidate == expected


def _canonical_artifact_path(config: FullShadowAcceptanceConfig, step_id: str) -> Path:
    return artifact_path_for(config.base_dir, config.betting_day, config.run_id, step_id)


def write_fixture_s8_coupon_draft(
    config: FullShadowAcceptanceConfig,
    *,
    coupon_draft_count: int = 1,
) -> Path:
    draft_path = expected_acceptance_s8_draft_path(config)
    payload = {
        "schema_version": 1,
        "artifact_type": "S8_COUPON_DRAFTS",
        "betting_day": config.betting_day,
        "run_id": config.run_id,
        "runtime_mode": parse_runtime_mode(config.runtime_mode).value,
        "source_input_path": str(acceptance_run_root(config) / "data" / f"{config.betting_day}_s7_gate_results.json"),
        "requires_human_gate": True,
        "ready_for_human_gate": True,
        "ready_for_production_execution": False,
        "production_selectable": False,
        "production_coupon_write": False,
        "executable_coupon": False,
        "betclic_execution_enabled": False,
        "coupon_draft_count": coupon_draft_count,
        "drafts": [
            {
                "draft_id": "shadow-acceptance-draft-1",
                "selections": [
                    {
                        "fixture": "Alpha vs Beta",
                        "market": "Goals Over 2.5",
                        "direction": "OVER",
                        "line": 2.5,
                        "odds": 1.95,
                    }
                ],
                "not_for_production_execution": True,
            }
        ],
    }
    write_json_atomic(draft_path, payload)
    return draft_path


def build_s9_human_gate_artifact(
    config: FullShadowAcceptanceConfig,
    *,
    coupon_draft_path: Path | str,
    coupon_draft_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "betting_day": config.betting_day,
        "run_id": config.run_id,
        "manual_review": {
            "reviewed_by_user": "shadow-acceptance",
            "reviewed_at_utc": utc_now_iso(),
            "betclic_manual_verification": True,
            "coupon_draft_path": str(coupon_draft_path),
            "coupon_draft_sha256": coupon_draft_sha256,
        },
    }


def write_s9_human_gate_artifact(
    config: FullShadowAcceptanceConfig,
    artifact: dict[str, Any],
) -> Path:
    path = _canonical_artifact_path(config, "S9")
    write_json_atomic(path, artifact)
    return path


def evaluate_s10_gate(config: FullShadowAcceptanceConfig):
    return evaluate_gate_before_step("S10", config.base_dir, config.betting_day, config.run_id)


def _build_agent_artifact(
    config: FullShadowAcceptanceConfig,
    step_id: str,
    *,
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    artifact = agent_artifact_template_for_step(step_id, config.betting_day, config.run_id)
    artifact.update(
        {
            "status": "PASS",
            "point_in_time_as_of": utc_now_iso(),
            "source_bound": True,
            "sources": ["shadow-acceptance-fixture"],
            "unknowns": [],
            "blocked_reasons": [],
            "evidence_refs": list(evidence_refs),
        }
    )

    if step_id == "S2.3":
        artifact["payload"] = {
            "gaps": [],
            "enrichment_gaps": [],
            "gaps_bounded": True,
            "gaps_status": "BOUNDED",
        }
    elif step_id == "S2.5":
        artifact["payload"] = {
            "provider_observations": [{"provider": "fixture", "status": "stubbed"}],
            "source_observations": [{"source": "fixture", "status": "current"}],
        }
    elif step_id == "S2.7":
        artifact["payload"] = {
            "disputed_facts": [{"field": "market", "status": "resolved"}],
            "reconciliation": {
                "unknown_facts": [],
                "decision_basis": "fixture consensus",
            },
        }
    elif step_id == "S2.9":
        artifact["payload"] = {
            "readiness": "PASS",
            "readiness_basis": "fixture data fully bounded for shadow acceptance",
            "s3_may_proceed": True,
        }
    elif step_id == "S5":
        artifact["payload"] = {
            "injuries_lineups": "fixture-reviewed",
            "motivation_tournament_context": "fixture-reviewed",
            "travel_fatigue": "fixture-reviewed",
            "morale_recent_form": "fixture-reviewed",
            "upset_volatility_risk": "fixture-reviewed",
        }
    else:
        raise ValueError(f"Unsupported agent step: {step_id}")

    return artifact


def seed_positive_agent_artifacts(config: FullShadowAcceptanceConfig) -> dict[str, Path]:
    written: dict[str, Path] = {}

    for step_id in ("S2.3", "S2.5", "S2.7", "S2.9", "S5"):
        refs: list[str] = []
        if step_id == "S2.7":
            refs = [str(written["S2.3"]), str(written["S2.5"])]
        elif step_id == "S2.9":
            refs = [str(written["S2.3"]), str(written["S2.5"]), str(written["S2.7"])]
        elif step_id == "S5":
            refs = [
                str(_canonical_artifact_path(config, "S2.9")),
                str(_canonical_artifact_path(config, "S3")),
                str(_canonical_artifact_path(config, "S4")),
            ]

        path = _canonical_artifact_path(config, step_id)
        write_json_atomic(path, _build_agent_artifact(config, step_id, evidence_refs=refs))
        written[step_id] = path

    return written


def _write_shadow_script_evidence(step_id: str, *, environ: dict[str, str], payload: dict[str, Any]) -> None:
    write_script_evidence(
        step_id,
        status="PASS",
        payload=payload,
        sources=(f"shadow-acceptance:{step_id}",),
        evidence_refs=(),
        environ=environ,
        no_pick_edge_stake_coupon_emitted=step_id not in {"S7", "S7b", "S8"},
        production_selectable=False,
        betting_decisions_enabled=False,
    )


def _positive_s7_gate_payload(config: FullShadowAcceptanceConfig) -> dict[str, Any]:
    return {
        "date": config.betting_day,
        "gate_results": {
            "approved": [
                {
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "sport": "football",
                    "odds": {"market_best": 1.95},
                    "best_market": {
                        "name": "Goals Over 2.5",
                        "direction": "OVER",
                        "line": 2.5,
                        "safety_score": 0.85,
                        "probability": 0.85,
                    },
                }
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }


def _positive_s7b_validation_payload(config: FullShadowAcceptanceConfig) -> dict[str, Any]:
    return {
        "date": config.betting_day,
        "validation_status": "PASS",
        "validation": [
            {
                "event": "Alpha vs Beta",
                "market": "Goals Over 2.5",
                "betclic_available": True,
                "home_team": "Alpha",
                "away_team": "Beta",
                "sport": "football",
                "odds": {"market_best": 1.95},
                "best_market": {
                    "name": "Goals Over 2.5",
                    "direction": "OVER",
                    "line": 2.5,
                    "safety_score": 0.85,
                    "probability": 0.85,
                },
            }
        ],
    }


def _run_positive_full_pipeline_shadow(config: FullShadowAcceptanceConfig) -> dict[str, Any]:
    normalized = config.normalized()
    acceptance_base_run_dir(normalized).mkdir(parents=True, exist_ok=True)
    seed_positive_agent_artifacts(normalized)

    original_run = subprocess.run
    mode = parse_runtime_mode(normalized.runtime_mode)
    orchestrator = Orchestrator(
        betting_day=normalized.betting_day,
        run_id=normalized.run_id,
        runtime_mode=mode.value,
        base_run_dir=acceptance_base_run_dir(normalized),
        allow_live_network=mode == RuntimeMode.LIVE_SHADOW,
        allow_write=False,
    )
    orchestrator.env["BET_PIPELINE_RUN_ROOT"] = str(normalized.base_dir)
    if mode == RuntimeMode.LIVE_SHADOW:
        orchestrator.env[LIVE_ACK_KEY] = LIVE_ACK_VALUE

    run_root = acceptance_run_root(normalized)
    data_dir = run_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    def artifact_path_override(
        _base_dir: Path,
        betting_day: str,
        run_id: str,
        step_id: str,
        fixture_key: str | None = None,
    ) -> Path:
        return artifact_path_for(normalized.base_dir, betting_day, run_id, step_id, fixture_key)

    def gate_override(step_id: str, _base_dir: Path, betting_day: str, run_id: str):
        return evaluate_gate_before_step(step_id, normalized.base_dir, betting_day, run_id)

    def subprocess_side_effect(cmd: list[str], env: dict[str, str] | None = None, **kwargs: Any):
        wrapper_name = Path(cmd[1]).name
        child_env = env or orchestrator.env
        if wrapper_name == "s8_build_coupons.py":
            return original_run(cmd, env=child_env, **kwargs)

        payload = {
            "shadow_acceptance_fixture": True,
            "runtime_mode": normalized.runtime_mode,
        }

        if wrapper_name == "s7_validate.py":
            s7_path = data_dir / f"{normalized.betting_day}_s7_gate_results.json"
            validation_path = data_dir / f"betclic_market_validation_{normalized.betting_day}.json"
            if not s7_path.exists():
                write_json_atomic(s7_path, _positive_s7_gate_payload(normalized))
            write_json_atomic(validation_path, _positive_s7b_validation_payload(normalized))
            payload = {
                "s7b_input_path": str(s7_path),
                "s7b_json_output": str(validation_path),
                "validated_market_availability_path": str(validation_path),
            }
            _write_shadow_script_evidence("S7b", environ=child_env, payload=payload)
            return subprocess.CompletedProcess(cmd, 0)

        if wrapper_name == "s5_gate.py":
            s7_path = data_dir / f"{normalized.betting_day}_s7_gate_results.json"
            write_json_atomic(s7_path, _positive_s7_gate_payload(normalized))
            payload = {
                "approved_count": 1,
                "total_candidates": 1,
                "rejected_count": 0,
                "s7_json_output": str(s7_path),
                "sandbox_certification_fixture": True,
                "not_real_betting_recommendation": True,
                "market_availability_status": "AVAILABLE",
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": False,
            }
            _write_shadow_script_evidence("S7", environ=child_env, payload=payload)
            return subprocess.CompletedProcess(cmd, 0)

        wrapper_to_step = {
            "s0_settler.py": "S0",
            "s1_discover.py": "S1",
            "s2_tipsters.py": "S2",
            "s3_stats.py": "S3",
            "s4_valuator.py": "S4",
            "s6_repeats.py": "S6",
        }
        step_id = wrapper_to_step.get(wrapper_name)
        if step_id is None:
            raise ValueError(f"Unexpected wrapper during shadow acceptance: {wrapper_name}")
        _write_shadow_script_evidence(step_id, environ=child_env, payload=payload)
        return subprocess.CompletedProcess(cmd, 0)

    with (
        patch("bet.pipeline.orchestrator.artifact_path_for", side_effect=artifact_path_override),
        patch("bet.pipeline.orchestrator.evaluate_gate_before_step", side_effect=gate_override),
        patch("bet.pipeline.orchestrator.subprocess.run", side_effect=subprocess_side_effect),
    ):
        if mode == RuntimeMode.LIVE_SHADOW:
            with patch.dict(os.environ, {LIVE_ACK_KEY: LIVE_ACK_VALUE}, clear=False):
                return orchestrator.run(start_step="S0", stop_after_step="S9")
        return orchestrator.run(start_step="S0", stop_after_step="S9")


def classify_pipeline_terminal(summary: dict[str, Any]) -> tuple[str, str | None]:
    if summary.get("valid_no_action_terminal") is True and summary.get("blocked_at_step") == "S7":
        return "S7_NO_ACTION_TERMINAL", "S7"

    for step in summary.get("steps", []):
        if step.get("step_id") == "S9" and step.get("status") == "BLOCK":
            if step.get("blocked_reason") == "BLOCKED_WAITING_FOR_HUMAN_APPROVAL":
                return "S9_BLOCK_WAITING_FOR_HUMAN_GATE", "S9"

    terminal_step = summary.get("blocked_at_step") or summary.get("last_completed_step")
    return "UNEXPECTED_PIPELINE_TERMINAL", terminal_step


def evaluate_s9_gate_matrix(
    config: FullShadowAcceptanceConfig,
    draft_path: Path,
) -> dict[str, bool]:
    s9_path = _canonical_artifact_path(config, "S9")
    if s9_path.exists():
        s9_path.unlink()

    draft_sha256 = sha256_file(draft_path)
    missing_blocks = evaluate_s10_gate(config).verdict.value == "BLOCK"

    valid_artifact = build_s9_human_gate_artifact(
        config,
        coupon_draft_path=draft_path,
        coupon_draft_sha256=draft_sha256,
    )
    write_s9_human_gate_artifact(config, valid_artifact)
    bound_unblocks = evaluate_s10_gate(config).verdict.value == "PASS"

    wrong_sha_artifact = build_s9_human_gate_artifact(
        config,
        coupon_draft_path=draft_path,
        coupon_draft_sha256="0" * 64,
    )
    write_s9_human_gate_artifact(config, wrong_sha_artifact)
    wrong_sha_blocks = evaluate_s10_gate(config).verdict.value == "BLOCK"

    bare_tmp_artifact = build_s9_human_gate_artifact(
        config,
        coupon_draft_path=Path("/tmp") / f"{config.betting_day}_s8_coupon_drafts.json",
        coupon_draft_sha256=draft_sha256,
    )
    write_s9_human_gate_artifact(config, bare_tmp_artifact)
    bare_tmp_blocks = evaluate_s10_gate(config).verdict.value == "BLOCK"

    write_s9_human_gate_artifact(config, valid_artifact)

    return {
        "s9_missing_blocks": missing_blocks,
        "s9_bound_approval_unblocks_s10_gate": bound_unblocks,
        "s9_wrong_sha_blocks": wrong_sha_blocks,
        "s9_bare_tmp_approval_blocks": bare_tmp_blocks,
        "s10_gate_without_bound_s9": missing_blocks,
    }


def run_full_shadow_acceptance(
    config: FullShadowAcceptanceConfig,
    *,
    task_id: str = TASK_ID,
    report_path: Path | None = None,
) -> FullShadowAcceptanceReport:
    normalized = config.normalized()
    blockers = validate_full_shadow_acceptance_config(normalized, report_path=report_path)
    if blockers:
        raise ValueError("; ".join(blockers))

    before_snapshot = snapshot_protected_repo_paths()
    summary: dict[str, Any] = {}
    pipeline_terminal_status = "NOT_RUN"
    terminal_step: str | None = None
    s8_draft_path = expected_acceptance_s8_draft_path(normalized)

    try:
        summary = _run_positive_full_pipeline_shadow(normalized)
        pipeline_terminal_status, terminal_step = classify_pipeline_terminal(summary)
    except Exception as exc:
        blockers.append(f"Scenario A execution failed: {exc}")
        pipeline_terminal_status = "EXECUTION_FAILED"

    if not s8_draft_path.exists():
        write_fixture_s8_coupon_draft(normalized)

    draft = load_artifact(s8_draft_path)
    gate_matrix = evaluate_s9_gate_matrix(normalized, s8_draft_path)
    for key, passed in gate_matrix.items():
        if not passed:
            blockers.append(f"Acceptance gate failed: {key}")

    after_snapshot = snapshot_protected_repo_paths()
    protected_changes = compare_path_snapshots(before_snapshot, after_snapshot)
    if protected_changes:
        blockers.extend(protected_changes)
    protected_repo_write_verdict = "PASS" if not protected_changes else "FAIL"

    run_scoped_ok = is_run_scoped_s8_draft_path(s8_draft_path, normalized)
    if not run_scoped_ok:
        blockers.append(f"S8 draft path is not run-scoped: {s8_draft_path}")

    draft_sha256 = sha256_file(s8_draft_path)
    draft_count = int(draft.get("coupon_draft_count", 0))
    s8_requires_human_gate = draft.get("requires_human_gate") is True
    s8_ready_for_human_gate = draft.get("ready_for_human_gate") is True
    s8_ready_for_production_execution = draft.get("ready_for_production_execution") is True
    s8_production_coupon_write = draft.get("production_coupon_write") is True
    s8_executable_coupon = draft.get("executable_coupon") is True
    s8_betclic_execution_enabled = draft.get("betclic_execution_enabled") is True

    if not s8_requires_human_gate:
        blockers.append("S8 draft does not require human gate")
    if not s8_ready_for_human_gate:
        blockers.append("S8 draft is not marked ready for human gate")
    if s8_ready_for_production_execution:
        blockers.append("S8 draft incorrectly marks ready_for_production_execution=true")
    if s8_production_coupon_write:
        blockers.append("S8 draft incorrectly marks production_coupon_write=true")
    if s8_executable_coupon:
        blockers.append("S8 draft incorrectly marks executable_coupon=true")
    if s8_betclic_execution_enabled:
        blockers.append("S8 draft incorrectly marks betclic_execution_enabled=true")
    if draft_count <= 0:
        blockers.append("S8 draft count must be > 0 for positive acceptance")

    ready_for_paper_trading = False
    status = "BLOCKED_UNEXPECTED_PIPELINE_TERMINAL"
    if protected_repo_write_verdict == "FAIL":
        status = "BLOCKED_PROTECTED_REPO_WRITES"
    elif pipeline_terminal_status == "S7_NO_ACTION_TERMINAL":
        status = "BLOCKED_NO_ACTION_TERMINAL"
    elif pipeline_terminal_status == "S9_BLOCK_WAITING_FOR_HUMAN_GATE" and not blockers:
        ready_for_paper_trading = True
        status = "PASS"
    elif blockers:
        status = "BLOCKED_ACCEPTANCE_CONTRACT"

    return FullShadowAcceptanceReport(
        task_id=task_id,
        status=status,
        base_dir=normalized.base_dir,
        betting_day=normalized.betting_day,
        run_id=normalized.run_id,
        runtime_mode=normalized.runtime_mode,
        pipeline_terminal_status=pipeline_terminal_status,
        terminal_step=terminal_step,
        s8_coupon_draft_path=str(s8_draft_path),
        s8_coupon_draft_sha256=draft_sha256,
        s8_coupon_draft_count=draft_count,
        s8_requires_human_gate=s8_requires_human_gate,
        s8_ready_for_human_gate=s8_ready_for_human_gate,
        s8_ready_for_production_execution=s8_ready_for_production_execution,
        s8_production_coupon_write=s8_production_coupon_write,
        s8_executable_coupon=s8_executable_coupon,
        s8_betclic_execution_enabled=s8_betclic_execution_enabled,
        s9_missing_blocks=gate_matrix["s9_missing_blocks"],
        s9_bound_approval_unblocks_s10_gate=gate_matrix["s9_bound_approval_unblocks_s10_gate"],
        s9_bare_tmp_approval_blocks=gate_matrix["s9_bare_tmp_approval_blocks"],
        s9_wrong_sha_blocks=gate_matrix["s9_wrong_sha_blocks"],
        s10_gate_without_bound_s9=gate_matrix["s10_gate_without_bound_s9"],
        protected_repo_write_verdict=protected_repo_write_verdict,
        ready_for_paper_trading=ready_for_paper_trading,
        ready_for_production_execution=False,
        blockers=blockers,
    )
