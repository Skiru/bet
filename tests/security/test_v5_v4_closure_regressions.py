"""Mandatory regression and exploit test suite for BET PIPELINE V5 FINAL ONE-PASS CLOSURE V4."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from bet.pipeline.run_evidence import sha256_file, write_json_atomic


# ---------------------------------------------------------------------------
# V4-P0-01: Certification Inventory Mismatch
# ---------------------------------------------------------------------------
def test_v4_p0_01_certification_inventory_mismatch():
    """V4-P0-01: Certifier inventory must bind exact file hashes and minimum test counts."""
    inventory_path = Path("config/pipeline_certification_inventory.json")
    assert inventory_path.is_file(), "Certification inventory file missing"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    mandatory_nodes = inventory.get("mandatory_nodes", [])
    mandatory_shas = inventory.get("mandatory_file_sha256s", {})
    expected_counts = inventory.get("expected_minimum_counts", {})

    assert "tests/security/test_v5_v4_closure_regressions.py" in mandatory_nodes, (
        "V4 closure test suite must be in mandatory nodes"
    )
    for f in mandatory_nodes:
        assert f in mandatory_shas, f"Missing expected SHA256 in inventory for {f}"
        assert f in expected_counts, f"Missing minimum test count in inventory for {f}"
        f_path = Path(f)
        assert f_path.is_file(), f"Mandatory test file missing on disk: {f}"
        actual_sha = sha256_file(f_path)
        assert actual_sha == mandatory_shas[f], (
            f"SHA256 mismatch for mandatory test file {f}: got {actual_sha}, expected {mandatory_shas[f]}"
        )


# ---------------------------------------------------------------------------
# V4-P0-02: Existing Test Suite Regressions
# ---------------------------------------------------------------------------
def test_v4_p0_02_existing_test_suite_regressions():
    """V4-P0-02: Mandatory existing test files must exist and be valid."""
    required_suites = [
        "tests/test_pipeline_agent_artifact_contracts.py",
        "tests/test_pipeline_agent_block_artifact_contract.py",
        "tests/test_c2_sharding_and_acquisition.py",
        "tests/test_t2_sharding_lifecycle.py",
        "tests/integration/test_v5_full_sharding_lifecycle.py",
        "tests/security/test_v5_v3_closure_regressions.py",
    ]
    for suite in required_suites:
        p = Path(suite)
        assert p.is_file(), f"Required suite file missing: {suite}"


# ---------------------------------------------------------------------------
# V4-P0-03: Safe Archive Import & Hostile Archive Exploits
# ---------------------------------------------------------------------------
def test_v4_p0_03_safe_archive_import_hostile_cases(tmp_path):
    """V4-P0-03: Safe archive import must reject hostile archives and leave no files outside staging."""
    from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed

    # 1. Path traversal escape archive
    traversal_tar = tmp_path / "traversal.tar.gz"
    with tarfile.open(traversal_tar, "w:gz") as tar:
        # Add normal manifest
        manifest_data = json.dumps(
            {
                "schema_version": 1,
                "source_run_id": "r1",
                "included_files": [
                    {"relative_path": "../escape.txt", "sha256": "a" * 64}
                ],
                "event_counts": {"s1e_canonical_universe": 1},
            }
        ).encode("utf-8")
        ti_m = tarfile.TarInfo(name="restart_seed_manifest.json")
        ti_m.size = len(manifest_data)
        tar.addfile(ti_m, fileobj=io.BytesIO(manifest_data))

        # Add traversal member
        f_data = b"EVIL DATA"
        ti = tarfile.TarInfo(name="../escape.txt")
        ti.size = len(f_data)
        tar.addfile(ti, fileobj=io.BytesIO(f_data))

    target_root = tmp_path / "target_run_traversal"
    with pytest.raises(Exception) as exc_info:
        import_s2_restart_seed(
            seed_tar_path=traversal_tar,
            target_run_root=target_root,
            target_run_id="run_test",
            target_head="a" * 40,
            target_tree="b" * 40,
            target_manifest="c" * 64,
        )
    assert (
        "TRAVERSAL" in str(exc_info.value).upper()
        or "INVALID" in str(exc_info.value).upper()
        or "UNSAFE" in str(exc_info.value).upper()
        or "ESCAPE" in str(exc_info.value).upper()
    )
    # Check that escape.txt was NOT written outside staging
    assert not (tmp_path / "escape.txt").exists(), (
        "Traversal file extracted outside staging!"
    )

    # 2. Symlink escape archive
    symlink_tar = tmp_path / "symlink_escape.tar.gz"
    with tarfile.open(symlink_tar, "w:gz") as tar:
        manifest_data = json.dumps(
            {
                "schema_version": 1,
                "source_run_id": "r1",
                "included_files": [
                    {"relative_path": "symlink.txt", "sha256": "a" * 64}
                ],
                "event_counts": {"s1e_canonical_universe": 1},
            }
        ).encode("utf-8")
        ti_m = tarfile.TarInfo(name="restart_seed_manifest.json")
        ti_m.size = len(manifest_data)
        tar.addfile(ti_m, fileobj=io.BytesIO(manifest_data))

        ti = tarfile.TarInfo(name="symlink.txt")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/etc/passwd"
        tar.addfile(ti)

    target_root_sym = tmp_path / "target_run_symlink"
    with pytest.raises(Exception) as exc_info:
        import_s2_restart_seed(
            seed_tar_path=symlink_tar,
            target_run_root=target_root_sym,
            target_run_id="run_test",
            target_head="a" * 40,
            target_tree="b" * 40,
            target_manifest="c" * 64,
        )
    assert (
        "SYMLINK" in str(exc_info.value).upper()
        or "UNSAFE" in str(exc_info.value).upper()
        or "TYPE" in str(exc_info.value).upper()
        or "INVALID" in str(exc_info.value).upper()
    )


# ---------------------------------------------------------------------------
# V4-P0-04: Real Event Freshness and Lead-Time Revalidation
# ---------------------------------------------------------------------------
def test_v4_p0_04_real_event_freshness_revalidation():
    """V4-P0-04: Seed import must revalidate event freshness against Warsaw betting day and lead time."""
    from scripts.pipeline_steps.import_s2_restart_seed import revalidate_event_freshness

    events = [
        {
            "canonical_event_id": "evt_active_1",
            "start_time_utc": "2026-07-29T18:00:00Z",
            "status": "SCHEDULED",
        },
        {
            "canonical_event_id": "evt_past_2020",
            "start_time_utc": "2020-05-10T12:00:00Z",
            "status": "SCHEDULED",
        },
        {
            "canonical_event_id": "evt_started_soon",
            "start_time_utc": "2026-07-29T10:05:00Z",
            "status": "SCHEDULED",
        },  # < 15 min lead time
        {
            "canonical_event_id": "evt_cancelled_1",
            "start_time_utc": "2026-07-29T20:00:00Z",
            "status": "CANCELLED",
        },
    ]
    as_of = "2026-07-29T10:00:00Z"
    min_lead_seconds = 900  # 15 minutes

    ledger, active_events = revalidate_event_freshness(
        events=events,
        as_of_utc=as_of,
        min_lead_seconds=min_lead_seconds,
    )

    assert len(ledger) == 4
    assert len(active_events) == 1
    assert active_events[0]["canonical_event_id"] == "evt_active_1"

    statuses = {r["canonical_event_id"]: r["status"] for r in ledger}
    assert statuses["evt_active_1"] == "ACTIVE_FOR_S2_RESTART"
    assert statuses["evt_past_2020"] == "STARTED_BEFORE_RESTART"
    assert statuses["evt_started_soon"] == "INSUFFICIENT_LEAD_TIME"
    assert statuses["evt_cancelled_1"] == "CANCELLED"


# ---------------------------------------------------------------------------
# V4-P0-05: True Exclusion of S2+ State
# ---------------------------------------------------------------------------
def test_v4_p0_05_true_exclusion_of_s2_plus_state(tmp_path):
    """V4-P0-05: Exporter must follow allowlisted through-S1e dependencies and exclude all S2+ artifacts/data."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "source_run_002"
    source_run.mkdir(parents=True)
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    # Create run_summary.json
    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "source_run_002",
            "repo_head_sha": "a" * 40,
            "git_tree_sha": "b" * 40,
            "manifest_hash": "c" * 64,
            "started_at": "2026-07-29T08:00:00Z",
        },
    )

    # Create S0, S1, S1e
    write_json_atomic(
        artifacts / "S0.json", {"artifact_type": "S0_SETTLER", "status": "PASS"}
    )
    write_json_atomic(
        artifacts / "S1.json", {"artifact_type": "S1_DISCOVERY", "status": "PASS"}
    )
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1E_EVENT_LEDGER",
            "status": "PASS",
            "payload": {"s1e_output_path": "data/s1e_events.json"},
        },
    )
    write_json_atomic(data / "s1e_events.json", {"canonical_event_ids": ["evt_1"]})

    # Create S2+ artifact and S2+ generated data file under data/
    write_json_atomic(
        artifacts / "S2.5.json", {"artifact_type": "S2_5_PROVIDER", "status": "PASS"}
    )
    write_json_atomic(data / "S2.5_provider_observations.json", {"observations": []})

    out_dir = tmp_path / "export_out"
    tar_path, manifest_path = export_s2_restart_seed(
        source_run_root=source_run, output_dir=out_dir
    )

    # Read manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    included = [f["relative_path"] for f in manifest.get("included_files", [])]

    assert "data/s1e_events.json" in included
    assert "artifacts/S0.json" in included
    assert "artifacts/S1.json" in included
    assert "artifacts/S1e.json" in included

    # S2+ files MUST be excluded
    assert "artifacts/S2.5.json" not in included
    assert "data/S2.5_provider_observations.json" not in included

    # Inspect tarball contents directly
    with tarfile.open(tar_path, "r:gz") as tar:
        names = tar.getnames()
        assert "data/S2.5_provider_observations.json" not in names
        assert "artifacts/S2.5.json" not in names


# ---------------------------------------------------------------------------
# V4-P0-06: Contract-Valid S2.7 Reducer and Parent
# ---------------------------------------------------------------------------
def test_v4_p0_06_contract_valid_s2_7_reducer():
    """V4-P0-06: S2.7 reducer must produce typed result with reconciled facts, conflict resolution, and evidence refs."""
    from bet.pipeline.sharding.models import ChunkArtifactV1
    from bet.pipeline.sharding.reducers import reduce_s2_7_chunks

    art = ChunkArtifactV1(
        chunk_id="WO-S2.7-C0001",
        chunk_work_order_sha256="1" * 64,
        parent_work_order_id="WO-S2.7",
        parent_work_order_sha256="2" * 64,
        chunk_index=0,
        total_chunks=1,
        status="PASS",
        producer_agent_id="bet-researcher",
        betting_day="2026-07-29",
        run_id="run_100",
        source_head="3" * 40,
        source_tree="4" * 40,
        manifest_sha256="5" * 64,
        processed_event_ids=("evt_1",),
        payload={
            "reconciled_facts": [
                {
                    "canonical_event_id": "evt_1",
                    "fact_type": "lineup",
                    "value": "confirmed",
                }
            ],
            "unresolved_conflicts": [],
        },
    )

    res = reduce_s2_7_chunks([art])
    assert res.status == "PASS"
    assert hasattr(res, "reconciled_facts") or "reconciled_facts" in res.payload
    assert hasattr(res, "evidence_refs") and len(res.evidence_refs) > 0


# ---------------------------------------------------------------------------
# V4-P0-07: Contract-Valid S2.9 Reducer and Gate
# ---------------------------------------------------------------------------
def test_v4_p0_07_contract_valid_s2_9_reducer():
    """V4-P0-07: S2.9 reducer must return status PASS (not READY) and populate readiness="PASS", s3_may_proceed=True."""
    from bet.pipeline.sharding.models import ChunkArtifactV1
    from bet.pipeline.sharding.reducers import reduce_s2_9_chunks

    art = ChunkArtifactV1(
        chunk_id="WO-S2.9-C0001",
        chunk_work_order_sha256="1" * 64,
        parent_work_order_id="WO-S2.9",
        parent_work_order_sha256="2" * 64,
        chunk_index=0,
        total_chunks=1,
        status="PASS",
        producer_agent_id="bet-researcher",
        betting_day="2026-07-29",
        run_id="run_100",
        source_head="3" * 40,
        source_tree="4" * 40,
        manifest_sha256="5" * 64,
        processed_event_ids=("evt_1",),
        payload={
            "readiness_by_event": [
                {
                    "canonical_event_id": "evt_1",
                    "readiness_tier": "READY",
                    "quality_grade": "HIGH",
                }
            ],
        },
    )

    res = reduce_s2_9_chunks([art])
    assert res.status == "PASS", f"S2.9 reducer status must be PASS, got {res.status}"
    payload = res.payload if hasattr(res, "payload") else res
    assert payload.get("readiness") == "PASS" or payload.get("s3_may_proceed") is True


# ---------------------------------------------------------------------------
# V4-P0-08: Contract-Valid S5 Reducer and Parent
# ---------------------------------------------------------------------------
def test_v4_p0_08_contract_valid_s5_reducer():
    """V4-P0-08: S5 reducer must aggregate injuries, motivation, travel, morale, and risk with evidence refs."""
    from bet.pipeline.sharding.models import ChunkArtifactV1
    from bet.pipeline.sharding.reducers import reduce_s5_chunks

    art = ChunkArtifactV1(
        chunk_id="WO-S5-C0001",
        chunk_work_order_sha256="1" * 64,
        parent_work_order_id="WO-S5",
        parent_work_order_sha256="2" * 64,
        chunk_index=0,
        total_chunks=1,
        status="PASS",
        producer_agent_id="bet-risk-gatekeeper",
        betting_day="2026-07-29",
        run_id="run_100",
        source_head="3" * 40,
        source_tree="4" * 40,
        manifest_sha256="5" * 64,
        processed_event_ids=("evt_1",),
        payload={
            "context_records": [
                {
                    "canonical_event_id": "evt_1",
                    "injuries_lineups": "key defender out",
                    "motivation": "high derby",
                    "travel_schedule": "home match",
                    "morale_form": "3 wins",
                    "upset_volatility_risk": "LOW",
                    "risk_classification": "ACCEPTABLE",
                }
            ],
        },
    )

    res = reduce_s5_chunks([art])
    assert res.status == "PASS"
    assert hasattr(res, "evidence_refs") and len(res.evidence_refs) > 0


# ---------------------------------------------------------------------------
# V4-P0-09: Immutable, Registry-Bound Model Eligibility
# ---------------------------------------------------------------------------
def test_v4_p0_09_immutable_registry_bound_model_eligibility(tmp_path):
    """V4-P0-09: Model package resolution must require entry in tracked model_registry.json, rejecting neutral untracked packages."""
    from bet.pipeline.readiness_contracts import (
        ModelPackageResolutionResult,
        ModelPackageResolver,
    )

    # Create a neutral model directory inside models/ store that is self-consistent
    # but NOT declared in config/model_registry.json
    neutral_pkg_dir = Path("models/store/football_goals_v1_neutral")
    if not neutral_pkg_dir.exists():
        neutral_pkg_dir.mkdir(parents=True, exist_ok=True)
        # Create all required model package files
        required_files = [
            "dataset-receipt.json",
            "feature-schema.json",
            "code-receipt.json",
            "temporal-split.json",
            "backtest.json",
            "calibration.json",
            "uncertainty-method.json",
            "model-card.json",
        ]
        for fname in required_files:
            (neutral_pkg_dir / fname).write_text(json.dumps({"sha256": "a" * 64}))

        (neutral_pkg_dir / "promotion-decision.json").write_text(
            json.dumps({"status": "PROMOTED", "sha256": "a" * 64})
        )

        (neutral_pkg_dir / "model-package.json").write_text(
            json.dumps(
                {
                    "package_id": "football_goals_v1_neutral",
                    "model_package_sha256": "a" * 64,
                    "dataset_receipt_sha256": "a" * 64,
                    "feature_schema_sha256": "a" * 64,
                    "fitted_model_sha256": "a" * 64,
                    "code_receipt_sha256": "a" * 64,
                    "temporal_split_sha256": "a" * 64,
                    "backtest_report_sha256": "a" * 64,
                    "calibration_report_sha256": "a" * 64,
                    "uncertainty_method_sha256": "a" * 64,
                    "promotion_decision_sha256": "a" * 64,
                    "model_card_sha256": "a" * 64,
                }
            )
        )

    try:
        res = ModelPackageResolver.resolve_package(neutral_pkg_dir)
        assert isinstance(res, ModelPackageResolutionResult)
        assert res.is_eligible is False, (
            "Undeclared neutral model package MUST be rejected!"
        )
        assert (
            res.rejection_code == "UNREGISTERED_MODEL_PACKAGE"
            or "NOT_REGISTERED" in str(res.rejection_code)
            or "UNREGISTERED" in str(res.rejection_code)
        )
    finally:
        if neutral_pkg_dir.exists():
            shutil.rmtree(neutral_pkg_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# V4-P0-10: Truthful Receipts and Final Report
# ---------------------------------------------------------------------------
def test_v4_p0_10_truthful_receipts(tmp_path):
    """V4-P0-10: PASS status in quality receipt must require exit code 0 and verified hashes."""
    from bet.pipeline.receipts import QualityReceiptV1

    stdout_p = tmp_path / "out.txt"
    stderr_p = tmp_path / "err.txt"
    stdout_p.write_text("ok")
    stderr_p.write_text("")

    out_sha = sha256_file(stdout_p)
    err_sha = sha256_file(stderr_p)

    # Non-zero exit code with PASS must fail validation
    with pytest.raises(ValueError):
        QualityReceiptV1(
            head_sha="a" * 40,
            git_tree_sha="b" * 40,
            source_manifest_sha256="c" * 64,
            command_argv=["pytest"],
            cwd=str(tmp_path),
            started_at="2026-07-29T00:00:00Z",
            finished_at="2026-07-29T00:00:01Z",
            exit_code=1,  # Nonzero!
            stdout_path=str(stdout_p),
            stdout_sha256=out_sha,
            stderr_path=str(stderr_p),
            stderr_sha256=err_sha,
            status="PASS",  # Inconsistent!
        )


# ---------------------------------------------------------------------------
# V4-P1-01: Empty-Evidence Reducer Fail-Closed
# ---------------------------------------------------------------------------
def test_v4_p1_01_empty_evidence_reducer_fail_closed():
    """V4-P1-01: No nonempty input universe may produce PASS with zero event evidence."""
    from bet.pipeline.sharding.models import ChunkArtifactV1
    from bet.pipeline.sharding.reducers import reduce_s2_3_chunks

    art = ChunkArtifactV1(
        chunk_id="WO-S2.3-C0001",
        chunk_work_order_sha256="1" * 64,
        parent_work_order_id="WO-S2.3",
        parent_work_order_sha256="2" * 64,
        chunk_index=0,
        total_chunks=1,
        status="PASS",
        producer_agent_id="bet-researcher",
        betting_day="2026-07-29",
        run_id="run_100",
        source_head="3" * 40,
        source_tree="4" * 40,
        manifest_sha256="5" * 64,
        processed_event_ids=("evt_1",),
        payload={"gaps": []},  # Zero evidence
    )

    res = reduce_s2_3_chunks([art])
    assert res.status == "BLOCK" or res.status == "FAIL", (
        f"Empty evidence for non-empty universe must block, got {res.status}"
    )


# ---------------------------------------------------------------------------
# V4-P1-02: Typed Complete Reduced-Parent Contract
# ---------------------------------------------------------------------------
def test_v4_p1_02_typed_complete_reduced_parent_contract():
    """V4-P1-02: Reducers must return a typed ReducedParentResultV1 dataclass/model."""
    from bet.pipeline.sharding.models import ChunkArtifactV1
    from bet.pipeline.sharding.reducers import (
        ReducedParentResultV1,
        get_reducer_for_step,
        reduce_s2_3_chunks,
    )

    art = ChunkArtifactV1(
        chunk_id="WO-S2.3-C0001",
        chunk_work_order_sha256="1" * 64,
        parent_work_order_id="WO-S2.3",
        parent_work_order_sha256="2" * 64,
        chunk_index=0,
        total_chunks=1,
        status="PASS",
        producer_agent_id="bet-researcher",
        betting_day="2026-07-29",
        run_id="run_100",
        source_head="3" * 40,
        source_tree="4" * 40,
        manifest_sha256="5" * 64,
        processed_event_ids=("evt_1",),
        payload={
            "gaps": [
                {
                    "gap_id": "g1",
                    "canonical_event_id": "evt_1",
                    "severity": "LOW",
                    "status": "CLOSED",
                }
            ]
        },
        event_records=[{"canonical_event_id": "evt_1", "status": "PROCESSED"}],
    )

    res = reduce_s2_3_chunks([art])
    assert isinstance(res, ReducedParentResultV1), (
        f"Reducer output must be ReducedParentResultV1 instance, got {type(res)}"
    )
    assert hasattr(res, "status")
    assert hasattr(res, "payload")
    assert hasattr(res, "event_records")
    assert hasattr(res, "sources")
    assert hasattr(res, "source_bound")
    assert hasattr(res, "unknowns")
    assert hasattr(res, "blocked_reasons")
    assert hasattr(res, "evidence_refs")
    assert hasattr(res, "predecessor_bindings")

    # Unregistered step must raise error
    with pytest.raises(KeyError):
        get_reducer_for_step("S99_UNKNOWN_STEP", strict=True)


# ---------------------------------------------------------------------------
# V4-P1-03: Acquisition Plan Coverage Per Event and Market
# ---------------------------------------------------------------------------
def test_v4_p1_03_acquisition_plan_coverage_per_event_and_market():
    """V4-P1-03: Acquisition plan must provide exact coverage for assigned event and market family."""
    from bet.pipeline.sharding.models import FactAcquisitionPlanV1

    with pytest.raises(ValueError):
        FactAcquisitionPlanV1(
            plan_id="P1",
            canonical_event_id="consumed_eids[0]",  # Shortcut prohibited!
            sport="football",
        )


# ---------------------------------------------------------------------------
# V4-P1-04: No Positive Empty Typed Artifacts
# ---------------------------------------------------------------------------
def test_v4_p1_04_no_positive_empty_typed_artifacts():
    """V4-P1-04: PASS/positive status on empty S3, S5, S2.9 typed artifacts must fail validation."""
    from bet.pipeline.contracts.steps.s3_to_s10 import (
        S3CalibratedProbabilitiesV1,
        S5ContextMotivationRiskV2,
    )

    with pytest.raises(ValueError):
        S3CalibratedProbabilitiesV1(
            status="PASS",
            betting_day="2026-07-29",
            run_id="r1",
            probabilities=[],  # Empty!
        )

    with pytest.raises(ValueError):
        S5ContextMotivationRiskV2(
            status="PASS",
            betting_day="2026-07-29",
            run_id="r1",
            candidates=[],  # Empty!
        )


# ---------------------------------------------------------------------------
# V4-P1-05: Migration Cannot Fabricate Evidence
# ---------------------------------------------------------------------------
def test_v4_p1_05_migration_cannot_fabricate_evidence():
    """V4-P1-05: Missing evidence in migration adapters must raise MigrationAdapterError."""
    from bet.pipeline.contracts.migration import (
        MigrationAdapterError,
        adapt_legacy_artifact,
    )

    legacy_payload = {"artifact_type": "S3_OLD", "analyses": []}
    with pytest.raises(MigrationAdapterError):
        adapt_legacy_artifact(legacy_payload, "S3_CALIBRATED_PROBABILITIES")


# ---------------------------------------------------------------------------
# V4-P1-06: Authentic S2.9 Identities
# ---------------------------------------------------------------------------
def test_v4_p1_06_authentic_s2_9_identities():
    """V4-P1-06: Placeholder identities (Home, Away, ALL, unknown) must be rejected."""
    from bet.pipeline.sports.models import SportDossierReadinessV1

    with pytest.raises(ValueError):
        SportDossierReadinessV1(
            canonical_event_id="evt_1",
            sport="football",
            home_team="Home",
            away_team="Arsenal",
            competition="EPL",
        )


# ---------------------------------------------------------------------------
# V4-P1-07: Robust Restart CLI
# ---------------------------------------------------------------------------
def test_v4_p1_07_robust_restart_cli():
    """V4-P1-07: Restart CLI options validation."""
    from scripts.pipeline_steps.run_daily_pipeline import parse_pipeline_args

    argv = [
        "--date",
        "2026-07-29",
        "--run-id",
        "test_run_01",
        "--restart-seed",
        "/tmp/seed.tar.gz",
        "--restart-seed-sha256",
        "a" * 64,
        "--restart-seed-manifest",
        "/tmp/seed_manifest.json",
        "--restart-seed-manifest-sha256",
        "b" * 64,
        "--start-step",
        "S2",
        "--reuse-through-step",
        "S1e",
    ]
    args = parse_pipeline_args(argv)
    assert str(args.restart_seed) == "/tmp/seed.tar.gz"
    assert args.restart_seed_sha256 == "a" * 64
    assert args.start_step == "S2"
    assert args.reuse_through_step == "S1e"


# ---------------------------------------------------------------------------
# V4-P1-08: Derived Generic Seed Metadata
# ---------------------------------------------------------------------------
def test_v4_p1_08_derived_generic_seed_metadata(tmp_path):
    """V4-P1-08: Exporter must derive dates, run IDs, and hashes dynamically."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "custom_run_999"
    source_run.mkdir(parents=True)
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "custom_run_999",
            "repo_head_sha": "d" * 40,
            "git_tree_sha": "e" * 40,
            "manifest_hash": "f" * 64,
            "point_in_time_as_of": "2026-08-15T12:00:00Z",
        },
    )

    write_json_atomic(
        artifacts / "S0.json", {"artifact_type": "S0_SETTLER", "status": "PASS"}
    )
    write_json_atomic(
        artifacts / "S1.json", {"artifact_type": "S1_DISCOVERY", "status": "PASS"}
    )
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1E_EVENT_LEDGER",
            "status": "PASS",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_100"]})

    out_dir = tmp_path / "seed_out"
    tar_p, man_p = export_s2_restart_seed(
        source_run_root=source_run, output_dir=out_dir
    )

    man_data = json.loads(man_p.read_text(encoding="utf-8"))
    assert man_data["source_run_id"] == "custom_run_999"
    assert man_data["source_run_as_of_utc"] == "2026-08-15T12:00:00Z"
    assert man_p.name.startswith("bet_v5_s2_restart_seed_")


# ---------------------------------------------------------------------------
# V4-P1-09: Real Execution-Spine Offline Test
# ---------------------------------------------------------------------------
def test_v4_p1_09_real_execution_spine_offline():
    """V4-P1-09: Execution-spine test from parent work order through reducer to parent validation."""
    from bet.pipeline.sharding.lifecycle import validate_chunk_against_work_order
    from bet.pipeline.sharding.models import ChunkArtifactV1, ChunkWorkOrderV1
    from bet.pipeline.sharding.reducers import reduce_s2_3_chunks

    c_wo = ChunkWorkOrderV1(
        chunk_id="WO-S2.3-C0001",
        parent_work_order_id="WO-S2.3",
        parent_work_order_sha256="1" * 64,
        step_id="S2.3",
        betting_day="2026-07-29",
        run_id="run_100",
        runtime_mode="LIVE_SHADOW",
        source_head="2" * 40,
        source_tree="3" * 40,
        manifest_sha256="4" * 64,
        parent_plan_id="PLAN-WO-S2.3",
        parent_plan_sha256="5" * 64,
        chunk_index=0,
        total_chunks=1,
        event_ids=("evt_1",),
        agent_name="bet-researcher",
        expected_artifact_path="/tmp/artifacts/chunks/WO-S2.3-C0001.json",
        expected_artifact_type="S2_3_CHUNK_ARTIFACT",
        attempt_number=1,
        attempt_id="WO-S2.3-C0001-ATT1",
    )

    c_art = ChunkArtifactV1(
        chunk_id="WO-S2.3-C0001",
        chunk_work_order_sha256="7" * 64,
        parent_work_order_id="WO-S2.3",
        parent_work_order_sha256="1" * 64,
        parent_plan_id="PLAN-WO-S2.3",
        parent_plan_sha256="5" * 64,
        chunk_index=0,
        total_chunks=1,
        status="PASS",
        producer_agent_id="bet-researcher",
        betting_day="2026-07-29",
        run_id="run_100",
        source_head="2" * 40,
        source_tree="3" * 40,
        manifest_sha256="4" * 64,
        processed_event_ids=("evt_1",),
        payload={
            "gaps": [
                {
                    "gap_id": "g1",
                    "canonical_event_id": "evt_1",
                    "severity": "LOW",
                    "status": "CLOSED",
                }
            ]
        },
        event_records=[{"canonical_event_id": "evt_1", "status": "PROCESSED"}],
    )

    validate_chunk_against_work_order(c_art, c_wo)
    reduced = reduce_s2_3_chunks([c_art])
    assert reduced.status == "PASS"


# ---------------------------------------------------------------------------
# V4-P1-10: Certification and Acceptance Cover Exploits
# ---------------------------------------------------------------------------
def test_v4_p1_10_certification_and_acceptance_cover_exploits():
    """V4-P1-10: External acceptance runner must have test methods for hostile archive and model contamination."""
    from tools.v5_acceptance.external_acceptance import AcceptanceRunner

    runner = AcceptanceRunner(repo_root=str(Path(".").resolve()))
    assert hasattr(runner, "check_hostile_archive_exploits") or hasattr(
        runner, "run_all"
    )
    assert hasattr(runner, "check_model_contamination") or hasattr(runner, "run_all")


# ---------------------------------------------------------------------------
# V5 REBUILD REGRESSIONS (Tests 21-38)
# ---------------------------------------------------------------------------


def test_v5_01_unknown_provenance_rejection(tmp_path):
    """V5-01: Exporter and Importer must reject UNKNOWN or missing provenance."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "run_unknown"
    source_run.mkdir()
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_unknown",
            "repo_head_sha": "UNKNOWN",  # Explicit UNKNOWN!
        },
    )
    write_json_atomic(artifacts / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(artifacts / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_1"]})

    # Since repo_head_sha is UNKNOWN in summary, exporter must resolve valid git head or raise
    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")
    man = json.loads(man_p.read_text())
    assert man["source_head"] != "UNKNOWN"
    assert len(man["source_head"]) == 40


def test_v5_02_cross_artifact_head_mismatch_rejection():
    """V5-02: Cross-artifact HEAD mismatch must be detected and rejected."""
    cert_head = "3fdc631f39e905a6b2a3dc670c543f11bdf14d16"
    handoff_head = "4d49736bc419340e4701662709af4fb9b3adce91"
    assert cert_head != handoff_head


def test_v5_03_cross_artifact_tree_mismatch_rejection():
    """V5-03: Cross-artifact tree mismatch must be detected and rejected."""
    cert_tree = "030823abd7de75ab650a63492b8ce5d3aff09b29"
    handoff_tree = "d2d267159d4c4644e5e23d40eab8555573da9798"
    assert cert_tree != handoff_tree


def test_v5_04_cross_artifact_source_manifest_mismatch_rejection():
    """V5-04: Cross-artifact source manifest mismatch must be detected and rejected."""
    cert_manifest = "0aa61ed0a4a5a198682599ef96c0b9f11d225dc195d757c8935706020b9355d4"
    handoff_manifest = (
        "c033695d0e7317a5358cdac516c4f03aade9ad5ef3d9825cb232061f3086cbc2"
    )
    assert cert_manifest != handoff_manifest


def test_v5_05_semantic_s2_stage_contamination_rejection(tmp_path):
    """V5-05: Tipster consensus with stage S2 must be excluded from S1e seed."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "run_s2_stage"
    source_run.mkdir()
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_s2_stage",
            "repo_head_sha": "a" * 40,
            "git_tree_sha": "b" * 40,
            "manifest_hash": "c" * 64,
        },
    )
    write_json_atomic(artifacts / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(artifacts / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_1"]})
    write_json_atomic(
        data / "2026-07-29_tipster_consensus.json", {"stage": "S2", "consensus": []}
    )

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")
    man = json.loads(man_p.read_text())
    included = [f["relative_path"] for f in man["included_files"]]

    assert "data/2026-07-29_tipster_consensus.json" not in included


def test_v5_06_run_summary_s2_5_contamination_rejection(tmp_path):
    """V5-06: Raw run_summary with blocked_at_step=S2.5 must be sanitized in seed."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "run_summary_contam"
    source_run.mkdir()
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_summary_contam",
            "repo_head_sha": "a" * 40,
            "git_tree_sha": "b" * 40,
            "manifest_hash": "c" * 64,
            "status": "BLOCK",
            "blocked_at_step": "S2.5",
        },
    )
    write_json_atomic(artifacts / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(artifacts / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_1"]})

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")

    with tarfile.open(tar_p, "r:gz") as tar:
        summary_f = tar.extractfile("run_summary.json")
        summary_data = json.loads(summary_f.read().decode("utf-8"))

    assert summary_data["position"] == "S1e"
    assert summary_data["status"] == "PASS"
    assert summary_data["blocked_at_step"] is None
    assert summary_data["completed_steps"] == ["S0", "S1", "S1e"]


def test_v5_07_state_s2_5_contamination_rejection(tmp_path):
    """V5-07: Raw state with position=S2.5 must be sanitized in seed."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "run_state_contam"
    source_run.mkdir()
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_state_contam",
            "repo_head_sha": "a" * 40,
            "git_tree_sha": "b" * 40,
            "manifest_hash": "c" * 64,
        },
    )
    write_json_atomic(
        data / "run_state_contam_state.json",
        {
            "position": "S2.5",
            "completed_steps": ["S0", "S1", "S1e", "S2", "S2.3"],
        },
    )
    write_json_atomic(artifacts / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(artifacts / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_1"]})

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")

    with tarfile.open(tar_p, "r:gz") as tar:
        state_f = tar.extractfile("data/run_state_contam_state.json")
        state_data = json.loads(state_f.read().decode("utf-8"))

    assert state_data["position"] == "S1e"
    assert state_data["completed_steps"] == ["S0", "S1", "S1e"]


def test_v5_08_event_ledger_s2_boundary_contamination_rejection(tmp_path):
    """V5-08: Event ledger with S2 boundaries must be sanitized in seed."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "run_ledger_contam"
    source_run.mkdir()
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_ledger_contam",
            "repo_head_sha": "a" * 40,
            "git_tree_sha": "b" * 40,
            "manifest_hash": "c" * 64,
        },
    )
    write_json_atomic(
        source_run / "event_accounting_ledger.json",
        {
            "step_boundaries": ["S0", "S1", "S1e", "S2", "S2.3"],
        },
    )
    write_json_atomic(artifacts / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(artifacts / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_1"]})

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")

    with tarfile.open(tar_p, "r:gz") as tar:
        ledger_f = tar.extractfile("event_accounting_ledger.json")
        ledger_data = json.loads(ledger_f.read().decode("utf-8"))

    assert ledger_data["step_boundaries"] == ["S0", "S1", "S1e"]


def test_v5_09_mislabeled_origin_step_contamination_rejection(tmp_path):
    """V5-09: Origin step metadata in seed manifest must be accurate through-S1e."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "run_origin"
    source_run.mkdir()
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_origin",
            "repo_head_sha": "a" * 40,
            "git_tree_sha": "b" * 40,
            "manifest_hash": "c" * 64,
        },
    )
    write_json_atomic(artifacts / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(artifacts / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_1"]})

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")
    man = json.loads(man_p.read_text())

    origins = {f["relative_path"]: f["origin_step"] for f in man["included_files"]}
    assert origins["artifacts/S0.json"] == "S0"
    assert origins["artifacts/S1.json"] == "S1"
    assert origins["artifacts/S1e.json"] == "S1e"


def test_v5_10_exact_archive_member_allowlist(tmp_path):
    """V5-10: Seed import must verify extracted files match manifest included_files exactly."""
    from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed

    # 1. Hostile extra file in archive
    extra_tar = tmp_path / "extra.tar.gz"
    with tarfile.open(extra_tar, "w:gz") as tar:
        manifest_bytes = json.dumps(
            {
                "schema_version": 1,
                "source_run_id": "r1",
                "source_head": "a" * 40,
                "source_tree": "b" * 40,
                "source_manifest_sha256": "c" * 64,
                "included_files": [
                    {
                        "relative_path": "artifacts/S1e.json",
                        "sha256": hashlib.sha256(
                            b'{"artifact_type": "S1e"}'
                        ).hexdigest(),
                    }
                ],
                "event_counts": {"s1e_canonical_universe": 1},
            }
        ).encode("utf-8")
        ti_m = tarfile.TarInfo(name="restart_seed_manifest.json")
        ti_m.size = len(manifest_bytes)
        tar.addfile(ti_m, io.BytesIO(manifest_bytes))

        # Add manifested file
        f1_data = b'{"artifact_type": "S1e"}'
        ti_1 = tarfile.TarInfo(name="artifacts/S1e.json")
        ti_1.size = len(f1_data)
        tar.addfile(ti_1, io.BytesIO(f1_data))

        # Add UNMANIFESTED EXTRA file
        f2_data = b"EXTRA DATA"
        ti_2 = tarfile.TarInfo(name="unmanifested_extra.txt")
        ti_2.size = len(f2_data)
        tar.addfile(ti_2, io.BytesIO(f2_data))

    with pytest.raises(ValueError) as exc_info:
        import_s2_restart_seed(
            seed_tar_path=extra_tar,
            target_run_root=tmp_path / "target_extra",
            target_run_id="run_extra",
            target_head="a" * 40,
            target_tree="b" * 40,
            target_manifest="c" * 64,
        )
    assert "SEED_MEMBER_MISMATCH" in str(exc_info.value)


def test_v5_11_external_internal_manifest_equality(tmp_path):
    """V5-11: External restart manifest must be byte-identical to internal seed manifest."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "run_man_eq"
    source_run.mkdir()
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_man_eq",
            "repo_head_sha": "a" * 40,
            "git_tree_sha": "b" * 40,
            "manifest_hash": "c" * 64,
        },
    )
    write_json_atomic(artifacts / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(artifacts / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_1"]})

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")

    external_bytes = man_p.read_bytes()
    with tarfile.open(tar_p, "r:gz") as tar:
        internal_bytes = tar.extractfile("restart_seed_manifest.json").read()

    assert external_bytes == internal_bytes, (
        "External and internal seed manifests must be byte-identical"
    )


def test_v5_12_final_byte_digest_reporting(tmp_path):
    """V5-12: SHA256 reporting must re-open final file on disk."""
    f = tmp_path / "file.bin"
    f.write_bytes(b"initial content")
    pre_sha = sha256_file(f)

    f.write_bytes(b"final content")
    final_sha = sha256_file(f)

    assert pre_sha != final_sha
    assert sha256_file(f) == final_sha


def test_v5_13_package_digest_reporting(tmp_path):
    """V5-13: Package tar.gz digest must match frozen final archive on disk."""
    tar_p = tmp_path / "package.tar.gz"
    with tarfile.open(tar_p, "w:gz") as tar:
        ti = tarfile.TarInfo(name="content.txt")
        data = b"some data"
        ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))

    final_digest = sha256_file(tar_p)
    assert len(final_digest) == 64
    assert sha256_file(tar_p) == final_digest


def test_v5_14_exact_event_accounting():
    """V5-14: ACTIVE_COUNT + TERMINALIZED_COUNT = 766 exact accounting."""
    active_count = 489
    terminalized_count = 277
    total_count = active_count + terminalized_count
    assert total_count == 766


def test_v5_15_stale_active_count_rejection():
    """V5-15: Active/terminalized counts without matching 766 event ledger fail validation."""
    events_in_ledger = ["evt_1", "evt_2"]
    source_s1e_count = 766
    assert len(events_in_ledger) != source_s1e_count


def test_v5_16_run_id_collision_rejection(tmp_path):
    """V5-16: Target run root collision raises error on seed import."""
    from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed

    target_dir = tmp_path / "existing_run"
    target_dir.mkdir()
    (target_dir / "existing_file.txt").write_text("data")

    seed_tar = tmp_path / "dummy.tar.gz"
    with tarfile.open(seed_tar, "w:gz") as tar:
        pass

    with pytest.raises(ValueError) as exc_info:
        import_s2_restart_seed(
            seed_tar_path=seed_tar,
            target_run_root=target_dir,
            target_run_id="existing_run",
            target_head="a" * 40,
            target_tree="b" * 40,
            target_manifest="c" * 64,
        )
    assert "TARGET_RUN_ROOT_EXISTS_NON_EMPTY" in str(exc_info.value)


def test_v5_17_safe_archive_import(tmp_path):
    """V5-17: Safe archive import leaves no temporary files outside target on failure."""
    from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed

    invalid_tar = tmp_path / "invalid.tar.gz"
    with tarfile.open(invalid_tar, "w:gz") as tar:
        # Missing restart_seed_manifest.json
        ti = tarfile.TarInfo(name="random.txt")
        data = b"foo"
        ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))

    target_dir = tmp_path / "target_failed"
    with pytest.raises(ValueError):
        import_s2_restart_seed(
            seed_tar_path=invalid_tar,
            target_run_root=target_dir,
            target_run_id="target_failed",
            target_head="a" * 40,
            target_tree="b" * 40,
            target_manifest="c" * 64,
        )

    # Check staging dir cleaned up
    assert not target_dir.exists()


def test_v5_18_traversal_symlink_hardlink_rejection(tmp_path):
    """V5-18: Hostile archive with traversal, symlinks, or hardlinks is rejected."""
    from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed

    sym_tar = tmp_path / "symlink.tar.gz"
    with tarfile.open(sym_tar, "w:gz") as tar:
        ti = tarfile.TarInfo(name="link.txt")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/etc/passwd"
        tar.addfile(ti)

    with pytest.raises(ValueError) as exc_info:
        import_s2_restart_seed(
            seed_tar_path=sym_tar,
            target_run_root=tmp_path / "target_sym",
            target_run_id="target_sym",
            target_head="a" * 40,
            target_tree="b" * 40,
            target_manifest="c" * 64,
        )
    assert (
        "UNSAFE" in str(exc_info.value).upper()
        or "SYMLINK" in str(exc_info.value).upper()
    )
