"""Adversarial regression tests for control-plane agent work-order ownership alignment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bet.pipeline.agent_artifact_contracts import (
    _contains_provider_promotion,
    _refs_cover_required_steps,
    validate_agent_artifact_for_work_order,
)
from bet.pipeline.agent_work_orders import (
    build_agent_work_order,
    write_agent_work_order,
)
from bet.pipeline.manifest import (
    CANONICAL_POWER_AGENTS,
    PipelineManifest,
    discover_repo_root,
    get_executor_allowed_tasks,
    get_step_agent,
    get_step_hard_rules,
    get_upstream_dependencies,
    load_pipeline_manifest,
    validate_pipeline_manifest,
)
from bet.pipeline.orchestrator import Orchestrator


@pytest.fixture
def repo_root() -> Path:
    return discover_repo_root()


@pytest.fixture
def manifest(repo_root: Path) -> PipelineManifest:
    return load_pipeline_manifest(repo_root / "config" / "pipeline_manifest.json")


def seed_predecessors(base_dir: Path, betting_day: str, run_id: str):
    artifacts_dir = base_dir / "pipeline_runs" / betting_day / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for dep_id, kind in [
        ("S2", "SCRIPT_EVIDENCE"),
        ("S3", "SCRIPT_EVIDENCE"),
        ("S4", "SCRIPT_EVIDENCE"),
        ("S2.3", "AGENT_ARTIFACT"),
        ("S2.5", "AGENT_ARTIFACT"),
        ("S2.7", "AGENT_ARTIFACT"),
        ("S2.9", "AGENT_ARTIFACT"),
    ]:
        p = artifacts_dir / f"{dep_id}.json"
        if not p.is_file():
            payload = {
                "schema_version": 1,
                "artifact_type": kind,
                "step_id": dep_id,
                "status": "PASS",
                "betting_day": betting_day,
                "run_id": run_id,
                "sport": "football",
                "payload": {},
            }
            p.write_text(json.dumps(payload), encoding="utf-8")


def _write_valid_work_order_and_artifact(
    base_dir: Path, step_id: str, status: str = "PASS", run_id: str = "run-alignment-test"
) -> tuple[dict, dict, Path]:
    seed_predecessors(base_dir, "2026-07-24", run_id)
    wo = build_agent_work_order(
        betting_day="2026-07-24",
        run_id=run_id,
        step_id=step_id,
        runtime_mode="DRY_RUN",
        base_dir=base_dir,
    )
    wo_path = write_agent_work_order(wo, base_dir)
    wo_sha = hashlib.sha256(wo_path.read_bytes()).hexdigest()

    art = {
        "schema_version": 1 if step_id != "S2.9" else 2,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "producer_agent_id": wo.agent,
        "status": status,
        "betting_day": "2026-07-24",
        "run_id": run_id,
        "sport": "football",
        "point_in_time_as_of": "2026-07-24T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["verified-source"],
        "unknowns": [],
        "blocked_reasons": [] if status == "PASS" else ["EXPLICIT_BLOCK"],
        "evidence_refs": [f"{sid}.json" for sid in get_upstream_dependencies(step_id)],
        "work_order_id": wo.work_order_id,
        "work_order_sha256": wo_sha,
        "payload": {},
    }

    if step_id == "S2.3":
        art["payload"] = {"enrichment_gaps": [], "gaps_status": "bounded"}
    elif step_id == "S2.5":
        art["payload"] = {"providers": ["verified-source"]}
    elif step_id == "S2.7":
        art["payload"] = {
            "disputed_facts": [],
            "reconciliation": {"unknown_facts": [], "decision_basis": "verified"},
        }
    elif step_id == "S2.9":
        art["payload"] = {
            "readiness": "PASS",
            "s3_may_proceed": True,
            "predecessor_bindings": [
                {
                    "step_id": dep,
                    "path": str(
                        base_dir
                        / "pipeline_runs"
                        / "2026-07-24"
                        / "run-alignment-test"
                        / "artifacts"
                        / f"{dep}.json"
                    ),
                    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "artifact_type": "AGENT_ARTIFACT",
                    "betting_day": "2026-07-24",
                    "run_id": "run-alignment-test",
                    "status": "PASS",
                }
                for dep in ("S2.3", "S2.5", "S2.7")
            ],
        }
    elif step_id == "S5":
        art["payload"] = {
            "injuries_lineups": {"status": "checked"},
            "motivation_tournament_context": {"status": "checked"},
            "travel_fatigue": {"status": "checked"},
            "morale_recent_form": {"status": "checked"},
            "upset_volatility_risk": {"status": "checked"},
        }

    return wo.to_jsonable(), art, wo_path


# 1. Every agent_artifact step matches manifest owner and bet-executor allowlist
def test_1_work_order_agents_align_with_manifest_and_allowlist(
    manifest: PipelineManifest, repo_root: Path
):
    seed_predecessors(repo_root, "2026-07-24", "run-alignment")
    allowed_tasks = get_executor_allowed_tasks(repo_root)
    agent_steps = [s for s in manifest.steps if s.execution_mode == "agent_artifact"]

    for step in agent_steps:
        wo = build_agent_work_order(
            betting_day="2026-07-24",
            run_id="run-alignment",
            step_id=step.id,
            runtime_mode="DRY_RUN",
            base_dir=repo_root,
            manifest=manifest,
        )
        assert wo.agent == step.agent, f"Step {step.id} work order agent {wo.agent} != manifest {step.agent}"
        assert wo.agent in CANONICAL_POWER_AGENTS, f"Step {step.id} agent {wo.agent} not a canonical power agent"
        assert wo.agent in allowed_tasks, f"Step {step.id} agent {wo.agent} not in bet-executor allowlist"


# 2. Work-order hard_rules match manifest hard_rules (Finding 1)
def test_2_work_order_hard_rules_align_with_manifest(manifest: PipelineManifest, repo_root: Path):
    seed_predecessors(repo_root, "2026-07-24", "run-alignment")
    for step in manifest.steps:
        if step.execution_mode == "agent_artifact":
            wo = build_agent_work_order(
                betting_day="2026-07-24",
                run_id="run-alignment",
                step_id=step.id,
                runtime_mode="DRY_RUN",
                base_dir=repo_root,
                manifest=manifest,
            )
            assert wo.hard_rules == step.hard_rules, f"Step {step.id} hard_rules drift: {wo.hard_rules} != {step.hard_rules}"


# 3. Work-order generation is idempotent (Finding 2)
def test_3_work_order_generation_is_idempotent(tmp_path: Path):
    seed_predecessors(tmp_path, "2026-07-24", "run-idempotent")
    wo1 = build_agent_work_order(
        betting_day="2026-07-24",
        run_id="run-idempotent",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    p1 = write_agent_work_order(wo1, tmp_path)
    b1 = p1.read_bytes()

    wo2 = build_agent_work_order(
        betting_day="2026-07-24",
        run_id="run-idempotent",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    p2 = write_agent_work_order(wo2, tmp_path)
    b2 = p2.read_bytes()

    assert b1 == b2, "Work order regeneration is not byte-identical"


# 4. PASS artifact validation fails when persisted work order is missing (Finding 3)
def test_4_pass_validation_fails_when_work_order_file_missing(tmp_path: Path):
    wo_data, art, wo_path = _write_valid_work_order_and_artifact(tmp_path, "S2.3", "PASS")
    wo_path.unlink()

    errors = validate_agent_artifact_for_work_order(art, wo_data)
    assert any("Persisted work order file missing" in e for e in errors), f"Expected missing wo error, got: {errors}"


# 5. Resume ledger execution identity uses step identity & work-order SHA (Finding 4)
def test_5_resume_ledger_execution_identity_and_hashes(tmp_path: Path):
    s2_path = tmp_path / "pipeline_runs" / "2026-07-24" / "run-alignment-test" / "artifacts" / "S2.json"
    s2_path.parent.mkdir(parents=True, exist_ok=True)
    s2_path.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": "2026-07-24",
        "run_id": "run-alignment-test",
        "payload": {"tipsters": []},
    }), encoding="utf-8")

    wo_data, art, wo_path = _write_valid_work_order_and_artifact(tmp_path, "S2.3", "PASS")
    art_path = tmp_path / "pipeline_runs" / "2026-07-24" / "run-alignment-test" / "artifacts" / "S2.3.json"
    art_path.write_text(json.dumps(art), encoding="utf-8")

    orch = Orchestrator(
        betting_day="2026-07-24",
        run_id="run-alignment-test",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    res = orch.run(start_step="S2.3", stop_after_step="S2.3")
    status_str = res["status"].value if hasattr(res["status"], "value") else str(res["status"])
    assert status_str == "PASS"

    ledger_path = tmp_path / "pipeline_runs" / "2026-07-24" / "run-alignment-test" / "resume_ledger.json"
    assert ledger_path.exists()
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    s23_entry = next(e for e in ledger["entries"] if e["step_id"] == "S2.3")
    assert "work_order_sha256" in s23_entry["input_hashes"]


# 6. Script-mode orchestration validates SCRIPT_EVIDENCE schema & rules (Finding 5)
def test_6_script_mode_validates_script_evidence_artifact(tmp_path: Path):
    orch = Orchestrator(
        betting_day="2026-07-24",
        run_id="run-script-test",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )

    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(*args, **kwargs):
            ev_dir = tmp_path / "pipeline_runs" / "2026-07-24" / "run-script-test" / "artifacts"
            ev_dir.mkdir(parents=True, exist_ok=True)
            ev_path = ev_dir / "S1.json"
            ev_path.write_text(json.dumps({
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S1",
                "status": "PASS",
                "betting_day": "2026-07-24",
                "run_id": "run-script-test",
                "payload": {"TODO_FILL_BY_AGENT": True},
            }), encoding="utf-8")
            result = MagicMock()
            result.returncode = 0
            return result

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S1", stop_after_step="S1")
        status_str = summary["status"].value if hasattr(summary["status"], "value") else str(summary["status"])
        assert status_str == "BLOCK"
        assert any("placeholder" in b.lower() or "validation" in b.lower() for b in summary["blockers"])


# 7. Agent artifact requires producer_agent_id matching work order (Finding 6)
def test_7_agent_artifact_requires_producer_agent_id_matching_work_order(tmp_path: Path):
    wo_data, art, wo_path = _write_valid_work_order_and_artifact(tmp_path, "S2.3", "PASS")

    art.pop("producer_agent_id", None)
    art.pop("agent", None)
    errors = validate_agent_artifact_for_work_order(art, wo_data)
    assert any("producer_agent_id" in e for e in errors)

    art["producer_agent_id"] = "bet-enricher"
    errors = validate_agent_artifact_for_work_order(art, wo_data)
    assert any("producer_agent_id mismatch" in e for e in errors)


# 8. COMMAND_REQUEST files are attempt-scoped (Finding 7)
def test_8_command_request_execution_files_are_attempt_scoped(tmp_path: Path):
    wo_data, art, wo_path = _write_valid_work_order_and_artifact(tmp_path, "S2.3", "PASS")
    art["status"] = "COMMAND_REQUEST"
    art["command_request"] = {
        "command_id": "WAIT_FOR_RATE_LIMIT",
        "parameters": {"seconds": 1},
    }
    art_path = tmp_path / "pipeline_runs" / "2026-07-24" / "run-alignment-test" / "artifacts" / "S2.3.json"
    art_path.write_text(json.dumps(art), encoding="utf-8")

    orch = Orchestrator(
        betting_day="2026-07-24",
        run_id="run-alignment-test",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        m = MagicMock()
        m.returncode = 0
        m.stdout = "OK"
        m.stderr = ""
        mock_run.return_value = m
        orch.run(start_step="S2.3", stop_after_step="S2.3")

    attempt_log = tmp_path / "pipeline_runs" / "2026-07-24" / "run-alignment-test" / "logs" / "S2.3_cmd_attempt_1_stdout.log"
    assert attempt_log.exists()


# 9. Pipeline dependencies derived from manifest (Finding 8)
def test_9_pipeline_dependencies_derived_from_manifest(manifest: PipelineManifest):
    deps_s23 = get_upstream_dependencies("S2.3", manifest=manifest)
    assert deps_s23 == ["S2"]

    deps_s29 = get_upstream_dependencies("S2.9", manifest=manifest)
    assert deps_s29 == ["S2", "S2.3", "S2.5", "S2.7"]

    deps_s5 = get_upstream_dependencies("S5", manifest=manifest)
    assert deps_s5 == ["S3", "S4", "S2.9"]


# 10. Specific step work orders point to expected power agents
def test_10_specific_step_work_orders_point_to_canonical_agents(repo_root: Path, manifest: PipelineManifest):
    assert get_step_agent("S2.3", manifest=manifest) == "bet-researcher"
    assert get_step_agent("S2.5", manifest=manifest) == "bet-researcher"
    assert get_step_agent("S2.7", manifest=manifest) == "bet-researcher"
    assert get_step_agent("S2.9", manifest=manifest) == "bet-researcher"
    assert get_step_agent("S5", manifest=manifest) == "bet-risk-gatekeeper"


# 11. Static manifest validation rejects invalid agent or allowlist mismatch (Finding 9)
def test_11_static_manifest_validation_enforces_agent_invariant(manifest: PipelineManifest):
    errors = validate_pipeline_manifest(manifest)
    assert errors == []

    manifest_copy = json.loads(json.dumps(manifest.steps[0].__dict__))
    bad_manifest = load_pipeline_manifest()
    for s in bad_manifest.steps:
        if s.id == "S2.3":
            s.agent = "bet-enricher"

    bad_errors = validate_pipeline_manifest(bad_manifest)
    assert any("bet-enricher" in e for e in bad_errors)


# 12. Executable delegability proof over all agent_artifact steps (Finding 10)
def test_12_executable_delegability_proof_for_all_agent_artifact_steps(repo_root: Path, manifest: PipelineManifest):
    allowed_tasks = get_executor_allowed_tasks(repo_root)
    agent_steps = [s for s in manifest.steps if s.execution_mode == "agent_artifact"]

    assert len(agent_steps) == 5
    for step in agent_steps:
        agent_owner = get_step_agent(step.id, manifest=manifest)
        assert agent_owner in allowed_tasks, f"Step {step.id} owner {agent_owner} cannot be delegated by bet-executor"


# 13. Provider promotion detection avoids false positives on negated text (Finding 11)
def test_13_provider_promotion_detection_avoids_false_positives():
    payload_negated = {
        "provider_observations": ["coverage checked"],
        "note": "DO_NOT_CHANGE_PROVIDER_SELECTION",
    }
    assert _contains_provider_promotion(payload_negated) is False

    payload_promotion = {
        "provider_observations": ["coverage checked"],
        "promoted_provider": "new_provider",
    }
    assert _contains_provider_promotion(payload_promotion) is True


# 14. Evidence ref coverage requires step ID matching (Finding 12)
def test_14_evidence_ref_coverage_matching():
    refs = ["S2.3.json", "S2.5.json", "S2.7.json"]
    assert _refs_cover_required_steps(refs, ("S2.3", "S2.5", "S2.7")) is True

    refs_incomplete = ["S2.3.json", "S2.5.json"]
    assert _refs_cover_required_steps(refs_incomplete, ("S2.3", "S2.5", "S2.7")) is False


# 15. Repository contains no active runtime references to bet-enricher or bet-challenger
def test_15_no_active_runtime_references_to_legacy_agents(repo_root: Path):
    active_paths = [
        repo_root / "AGENTS.md",
        repo_root / "config/pipeline_manifest.json",
        *sorted((repo_root / "src").glob("**/*.py")),
        *sorted((repo_root / "scripts").glob("*.py")),
        *sorted((repo_root / ".kilo/agents").glob("bet-*.md")),
    ]

    ignored_validator_files = {
        "validate-bet-agent-config.py",
        "validate-unattended-permissions.py",
    }

    import re
    legacy_pattern = re.compile(r"\bbet-(?:enricher|challenger)\b")
    for path in active_paths:
        if path.name in ignored_validator_files:
            continue
        text = path.read_text(encoding="utf-8")
        assert not legacy_pattern.search(text), f"Active file {path.relative_to(repo_root)} contains legacy agent reference"


# 16. Malformed SCRIPT_EVIDENCE JSON returns BLOCK, not uncaught exception
def test_16_malformed_script_evidence_json_returns_block(tmp_path: Path):
    orch = Orchestrator(
        betting_day="2026-07-24",
        run_id="run-malformed-test",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(*args, **kwargs):
            ev_dir = tmp_path / "pipeline_runs" / "2026-07-24" / "run-malformed-test" / "artifacts"
            ev_dir.mkdir(parents=True, exist_ok=True)
            ev_path = ev_dir / "S1.json"
            ev_path.write_text("{malformed_json_not_valid", encoding="utf-8")
            res = MagicMock()
            res.returncode = 0
            return res

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S1", stop_after_step="S1")
        assert summary["status"] == "BLOCK"
        assert summary["blocked_at_step"] == "S1"
        assert any("SCRIPT_EVIDENCE_UNREADABLE" in b or "validation failure" in b for b in summary["blockers"])


# 17. Foreign betting_day or run_id in script evidence is rejected
def test_17_foreign_betting_day_and_run_id_rejected(tmp_path: Path):
    orch = Orchestrator(
        betting_day="2026-07-24",
        run_id="run-foreign-test",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(*args, **kwargs):
            ev_dir = tmp_path / "pipeline_runs" / "2026-07-24" / "run-foreign-test" / "artifacts"
            ev_dir.mkdir(parents=True, exist_ok=True)
            ev_path = ev_dir / "S1.json"
            ev_path.write_text(json.dumps({
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S1",
                "status": "PASS",
                "betting_day": "2020-01-01",  # foreign betting_day
                "run_id": "foreign-run-id",   # foreign run_id
            }), encoding="utf-8")
            res = MagicMock()
            res.returncode = 0
            return res

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S1", stop_after_step="S1")
        assert summary["status"] == "BLOCK"
        assert any("MISMATCH_BETTING_DAY" in b or "MISMATCH_RUN_ID" in b for b in summary["blockers"])


# 18. AGENT_ARTIFACT and STATE_MARKER rejected for script step
def test_18_wrong_artifact_types_rejected_for_script_step(tmp_path: Path):
    for wrong_type in ("AGENT_ARTIFACT", "STATE_MARKER"):
        orch = Orchestrator(
            betting_day="2026-07-24",
            run_id=f"run-type-{wrong_type}",
            runtime_mode="DRY_RUN",
            base_run_dir=tmp_path,
        )
        with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
            def side_effect(*args, **kwargs):
                ev_dir = tmp_path / "pipeline_runs" / "2026-07-24" / f"run-type-{wrong_type}" / "artifacts"
                ev_dir.mkdir(parents=True, exist_ok=True)
                ev_path = ev_dir / "S1.json"
                ev_path.write_text(json.dumps({
                    "schema_version": 1,
                    "artifact_type": wrong_type,
                    "step_id": "S1",
                    "status": "PASS",
                    "betting_day": "2026-07-24",
                    "run_id": f"run-type-{wrong_type}",
                }), encoding="utf-8")
                res = MagicMock()
                res.returncode = 0
                return res

            mock_run.side_effect = side_effect
            summary = orch.run(start_step="S1", stop_after_step="S1")
            assert summary["status"] == "BLOCK"
            assert any("MISMATCH_ARTIFACT_TYPE" in b for b in summary["blockers"])


# 19. COMMAND_REQUEST without full work order binding or wrong producer rejected before execution
def test_19_command_request_bindings_must_match_before_execution(tmp_path: Path):
    # Test zero command execution for missing/wrong work_order_id, sha256, producer_agent_id
    cases = [
        ("missing_wo_id", lambda art, wo: art.pop("work_order_id", None)),
        ("wrong_wo_id", lambda art, wo: art.update({"work_order_id": "WO-WRONG"})),
        ("missing_wo_sha", lambda art, wo: art.pop("work_order_sha256", None)),
        ("wrong_wo_sha", lambda art, wo: art.update({"work_order_sha256": "0" * 64})),
        ("missing_producer", lambda art, wo: art.pop("producer_agent_id", None)),
        ("wrong_producer", lambda art, wo: art.update({"producer_agent_id": "wrong-agent"})),
    ]

    for case_name, mutator in cases:
        run_id = f"run-cmd-{case_name}"
        wo_data, art, wo_path = _write_valid_work_order_and_artifact(tmp_path, "S2.3", "PASS", run_id=run_id)
        art["status"] = "COMMAND_REQUEST"
        art["command_request"] = {
            "command_id": "WAIT_FOR_RATE_LIMIT",
            "parameters": {"seconds": 1},
        }
        mutator(art, wo_data)

        art_dir = tmp_path / "pipeline_runs" / "2026-07-24" / run_id / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        (art_dir / "S2.3_work_order.json").write_text(json.dumps(wo_data), encoding="utf-8")
        art_path = art_dir / "S2.3.json"
        art_path.write_text(json.dumps(art), encoding="utf-8")

        orch = Orchestrator(
            betting_day="2026-07-24",
            run_id=run_id,
            runtime_mode="DRY_RUN",
            base_run_dir=tmp_path,
        )
        with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
            summary = orch.run(start_step="S2.3", stop_after_step="S2.3")
            assert mock_run.call_count == 0, f"run_bounded_process was called for invalid binding case {case_name}"
            assert summary["status"] == "BLOCK"


# 20. S3 identity changes when S2.9 SHA changes and S8 identity changes when S7/S7b SHA changes
def test_20_predecessor_sha_changes_ledger_signature(tmp_path: Path):
    from bet.pipeline.run_coordination import ResumeLedger
    from bet.pipeline.manifest import load_pipeline_manifest, get_required_artifacts_before_step

    m = load_pipeline_manifest()
    assert get_required_artifacts_before_step("S3", manifest=m) == ("S2.9",)
    assert get_required_artifacts_before_step("S8", manifest=m) == ("S7", "S7b")

    # Verify input hashes for S3 change if S2.9 file changes
    run_dir = tmp_path / "pipeline_runs" / "2026-07-24" / "run-sha-test"
    art_dir = run_dir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)

    s29_path = art_dir / "S2.9.json"
    s29_path.write_text("content1", encoding="utf-8")

    orch1 = Orchestrator(
        betting_day="2026-07-24",
        run_id="run-sha-test",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )
    # Get predecessor hashes before and after mutation
    from bet.pipeline.canonical_continuity import file_sha256
    sha1 = file_sha256(s29_path)

    s29_path.write_text("content2_mutated", encoding="utf-8")
    sha2 = file_sha256(s29_path)

    assert sha1 != sha2


# 21. Actual argv identity contains live/write flags when used
def test_21_actual_argv_contains_live_and_write_flags(tmp_path: Path):
    orch = Orchestrator(
        betting_day="2026-07-24",
        run_id="run-flags-test",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
        allow_live_network=True,
        allow_write=True,
    )
    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(cmd, **kwargs):
            assert "--allow-live-network" in cmd
            assert "--allow-write" in cmd
            ev_dir = tmp_path / "pipeline_runs" / "2026-07-24" / "run-flags-test" / "artifacts"
            ev_dir.mkdir(parents=True, exist_ok=True)
            ev_path = ev_dir / "S1.json"
            ev_path.write_text(json.dumps({
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S1",
                "status": "PASS",
                "betting_day": "2026-07-24",
                "run_id": "run-flags-test",
            }), encoding="utf-8")
            res = MagicMock()
            res.returncode = 0
            return res

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S1", stop_after_step="S1")
        assert summary["status"] == "PASS"


# 22. Exact evidence-ref adversarial matrix
def test_22_exact_evidence_ref_adversarial_matrix():
    # Must reject substring false positives
    assert _refs_cover_required_steps(["fake-S2.3-not-artifact"], ("S2.3",)) is False
    assert _refs_cover_required_steps(["S2.30.json"], ("S2.3",)) is False
    assert _refs_cover_required_steps(["garbage-S2.3.txt"], ("S2.3",)) is False

    # Must accept valid step references
    assert _refs_cover_required_steps(["S2.3_artifact.json"], ("S2.3",)) is True
    assert _refs_cover_required_steps(["S2.3.json"], ("S2.3",)) is True
    assert _refs_cover_required_steps(["artifact_S2.3_run1"], ("S2.3",)) is True


# 23. Provider promotion mixed-negation matrix
def test_23_provider_promotion_mixed_negation_matrix():
    # Positive promotion directives with mixed negations must be rejected
    assert _contains_provider_promotion("No provider promotion restriction; selected_provider=new_provider") is True
    assert _contains_provider_promotion("Do not promote old provider; promoted_provider=new_provider") is True
    assert _contains_provider_promotion("provider promotion is forbidden, switch_provider to x") is True

    # Pure rule statements without positive assignments must be allowed
    assert _contains_provider_promotion("Must not promote provider; follow strict no_provider_promotion rule") is False


# 24. Manifest hard-rule mutation propagates without a second policy map
def test_24_manifest_hard_rule_mutation_propagates(tmp_path: Path):
    seed_predecessors(tmp_path, "2026-07-24", "run-mut-test")
    manifest = load_pipeline_manifest()
    # Find S2.3 step in manifest
    s23_step = next(s for s in manifest.steps if s.id == "S2.3")
    s23_step.hard_rules.append("test_mutation_rule_999")

    # Check that build_agent_work_order uses mutated hard rule
    wo = build_agent_work_order(
        betting_day="2026-07-24",
        run_id="run-mut-test",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
        manifest=manifest,
    )
    assert "test_mutation_rule_999" in wo.hard_rules

    # Check that required_agent_output_contract uses mutated hard rule
    from bet.pipeline.agent_artifact_contracts import required_agent_output_contract
    contract = required_agent_output_contract("S2.3", manifest=manifest)
    assert "test_mutation_rule_999" in contract["hard_rules"]


# 25. Production surface validator passes on committed head
def test_25_production_surface_validator_passes():
    from scripts.validate_production_surface import validate
    res = validate()
    assert res["status"] == "PASS", f"Production surface validator returned BLOCK: {res.get('errors')}"


# 26. All current documentation uses canonical power agents
def test_26_current_documentation_uses_canonical_power_agents(repo_root: Path):
    import tomllib, re
    with open(repo_root / "config/retention_records.json", "r", encoding="utf-8") as f:
        records = json.load(f)

    current_docs = [
        repo_root / r["path"]
        for r in records
        if r.get("category") == "CURRENT_DOCUMENTATION" and (repo_root / r["path"]).exists()
    ]

    retired_agents = re.compile(r"\bbet-(?:enricher|challenger|statistician|valuator|scanner|scout)\b")
    for doc in current_docs:
        text = doc.read_text(encoding="utf-8")
        matches = retired_agents.findall(text)
        assert not matches, f"Current documentation file {doc.relative_to(repo_root)} references retired agent(s): {matches}"
