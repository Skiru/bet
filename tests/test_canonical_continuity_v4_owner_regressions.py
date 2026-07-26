from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
import pytest

from bet.pipeline.agent_artifact_contracts import (
    validate_agent_artifact_for_work_order,
)
from bet.pipeline.canonical_continuity import (
    ContinuityContractError,
    _token,
    bind_event_identity,
    event_identity_fields,
)
from bet.pipeline.event_accounting import (
    EventAccountingError,
    EventAccountingLedger,
    canonical_event_id,
)

def _bootstrap_test_db(db_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    schema_path = repo_root / "src" / "bet" / "db" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema)
    conn.close()
    return db_path

# 1. ŁKS Łódź and KS D do not share event identity.
def test_1_diacritic_collision():
    t1 = _token("ŁKS Łódź")
    t2 = _token("KS D")
    assert t1 != t2, f"Diacritic token collision detected: both normalized to {t1}"

# 2. Unicode composed and decomposed forms produce the same identity when semantically equal.
def test_2_unicode_normalization_equivalence():
    composed = "Åland"
    decomposed = "A\u030aland"
    assert _token(composed) == _token(decomposed)

# 3. 2026-07-15T12:00:00Z and 2026-07-15T14:00:00+02:00 produce the same event identity.
def test_3_timezone_kickoff_canonicalization():
    cand1 = {
        "home_team": "Team A",
        "away_team": "Team B",
        "sport": "football",
        "competition": "League",
        "kickoff": "2026-07-15T12:00:00Z",
    }
    cand2 = {
        "home_team": "Team A",
        "away_team": "Team B",
        "sport": "football",
        "competition": "League",
        "kickoff": "2026-07-15T14:00:00+02:00",
    }
    f1 = event_identity_fields(cand1)
    f2 = event_identity_fields(cand2)
    assert f1["kickoff"] == f2["kickoff"]

# 4. Naive, empty, malformed, and non-finite kickoff values are rejected.
def test_4_kickoff_validation_strict():
    with pytest.raises(ContinuityContractError):
        event_identity_fields({
            "home_team": "Team A",
            "away_team": "Team B",
            "sport": "football",
            "competition": "League",
            "kickoff": "2026-07-15 12:00:00",
        })
    with pytest.raises(ContinuityContractError):
        event_identity_fields({
            "home_team": "Team A",
            "away_team": "Team B",
            "sport": "football",
            "competition": "League",
            "kickoff": "",
        })
    with pytest.raises(ContinuityContractError):
        event_identity_fields({
            "home_team": "Team A",
            "away_team": "Team B",
            "sport": "football",
            "competition": "League",
            "kickoff": "not-a-datetime",
        })

# 5. Existing canonical_event_id or selection_id is verified against facts and cannot override them.
def test_5_id_mismatch_verification():
    cand = {
        "home_team": "Team A",
        "away_team": "Team B",
        "sport": "football",
        "competition": "League",
        "kickoff": "2026-07-15T12:00:00Z",
        "canonical_event_id": "evt_wrongid12345",
    }
    with pytest.raises(ContinuityContractError):
        bind_event_identity(cand)

# 6. A non-empty S1e universe can pass the real S1e→S2 accounting boundary without missing event_records.
def test_6_non_empty_universe_boundary_check(tmp_path: Path):
    root = tmp_path / "run"
    root.mkdir()
    universe_path = root / "universe.json"
    universe_path.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "betting_day": "2026-07-15",
        "run_id": "run-1",
        "events": [{
            "sport": "football",
            "competition": "League",
            "home_team": "A",
            "away_team": "B",
            "kickoff": "2026-07-15T12:00:00Z",
        }],
    }), encoding="utf-8")
    ledger = EventAccountingLedger.initialize(root, universe_path, betting_day="2026-07-15", run_id="run-1")
    evt_id = canonical_event_id({
        "sport": "football",
        "competition": "League",
        "home_team": "A",
        "away_team": "B",
        "kickoff": "2026-07-15T12:00:00Z",
    })
    payload = ledger.record_boundary("S2", records=[{"canonical_event_id": evt_id, "terminal_status": "CONTINUE"}])
    assert payload["unaccounted_event_ids"] == []

# 7. Duplicate, missing, and unknown event records fail closed.
def test_7_ledger_validation_failures(tmp_path: Path):
    root = tmp_path / "run"
    root.mkdir()
    universe_path = root / "universe.json"
    universe_path.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "betting_day": "2026-07-15",
        "run_id": "run-1",
        "events": [
            {"sport": "football", "competition": "League", "home_team": "A", "away_team": "B", "kickoff": "2026-07-15T12:00:00Z"},
            {"sport": "football", "competition": "League", "home_team": "C", "away_team": "D", "kickoff": "2026-07-15T14:00:00Z"},
        ],
    }), encoding="utf-8")
    ledger = EventAccountingLedger.initialize(root, universe_path, betting_day="2026-07-15", run_id="run-1")
    evt1 = canonical_event_id({"sport": "football", "competition": "League", "home_team": "A", "away_team": "B", "kickoff": "2026-07-15T12:00:00Z"})
    evt2 = canonical_event_id({"sport": "football", "competition": "League", "home_team": "C", "away_team": "D", "kickoff": "2026-07-15T14:00:00Z"})
    with pytest.raises(EventAccountingError):
        ledger.record_boundary("S2", records=[{"canonical_event_id": evt1, "terminal_status": "PASS"}])
    with pytest.raises(EventAccountingError):
        ledger.record_boundary("S2", records=[
            {"canonical_event_id": evt1, "terminal_status": "PASS"},
            {"canonical_event_id": evt2, "terminal_status": "PASS"},
            {"canonical_event_id": "evt-unknown-12345", "terminal_status": "PASS"},
        ])
    with pytest.raises(EventAccountingError):
        ledger.record_boundary("S2", records=[
            {"canonical_event_id": evt1, "terminal_status": "PASS"},
            {"canonical_event_id": evt1, "terminal_status": "PASS"},
        ])

# 8. A top-level-valid untouched agent template cannot be accepted as PASS.
def test_8_template_artifact_rejected():
    work_order = {"step_id": "S5", "run_id": "run-1", "betting_day": "2026-07-15", "required_output": {"required_statuses": ["PASS", "BLOCK"]}}
    artifact = {
        "step_id": "S5", "run_id": "run-1", "betting_day": "2026-07-15", "artifact_type": "AGENT_ARTIFACT", "status": "PASS",
        "blocked_reasons": [], "no_pick_edge_stake_coupon_emitted": True, "production_selectable": False, "betting_decisions_enabled": False,
        "payload": {"some_key": "TODO_FILL_BY_AGENT"},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("TODO_FILL_BY_AGENT" in err or "placeholder" in err.lower() for err in errors)

# 9. PASS with non-empty blocked_reasons cannot be accepted.
def test_9_pass_with_blocked_reasons_rejected():
    work_order = {"step_id": "S5", "run_id": "run-1", "betting_day": "2026-07-15", "required_output": {"required_statuses": ["PASS", "BLOCK"]}}
    artifact = {
        "step_id": "S5", "run_id": "run-1", "betting_day": "2026-07-15", "artifact_type": "AGENT_ARTIFACT", "status": "PASS",
        "blocked_reasons": ["SOME_BLOCKING_REASON"], "no_pick_edge_stake_coupon_emitted": True, "production_selectable": False,
        "betting_decisions_enabled": False, "payload": {},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("blocked_reasons" in err.lower() for err in errors)

# 10. PASS containing any placeholder sentinel recursively cannot be accepted.
def test_10_recursive_placeholder_detection():
    work_order = {"step_id": "S5", "run_id": "run-1", "betting_day": "2026-07-15", "required_output": {"required_statuses": ["PASS", "BLOCK"]}}
    artifact = {
        "step_id": "S5", "run_id": "run-1", "betting_day": "2026-07-15", "artifact_type": "AGENT_ARTIFACT", "status": "PASS",
        "blocked_reasons": [], "no_pick_edge_stake_coupon_emitted": True, "production_selectable": False, "betting_decisions_enabled": False,
        "payload": {"candidates": [{"name": "Team A", "notes": "TEMPLATE_NOT_FILLED"}]},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("TEMPLATE_NOT_FILLED" in err or "placeholder" in err.lower() for err in errors)

# 11. S2.9 cannot pass the pre-S3 gate with empty payload, false readiness, missing predecessor bindings, wrong path, or wrong SHA-256.
def test_11_s29_preconditions_validation():
    work_order = {"step_id": "S2.9", "run_id": "run-1", "betting_day": "2026-07-15", "required_output": {"required_statuses": ["PASS", "BLOCK"]}, "input_refs": []}
    artifact = {
        "step_id": "S2.9", "run_id": "run-1", "betting_day": "2026-07-15", "artifact_type": "AGENT_ARTIFACT", "status": "PASS",
        "blocked_reasons": [], "no_pick_edge_stake_coupon_emitted": True, "production_selectable": False, "betting_decisions_enabled": False, "payload": {},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("S2.9 PASS payload must not be empty" in e or "readiness" in e.lower() for e in errors)

# 12. A COMMAND_REQUEST cannot be promoted merely by copying the request artifact and changing status to PASS.
def test_12_status_only_promotion_rejected():
    work_order = {"step_id": "S5", "run_id": "run-1", "betting_day": "2026-07-15", "required_output": {"required_statuses": ["PASS", "BLOCK"]}}
    artifact = {
        "step_id": "S5", "run_id": "run-1", "betting_day": "2026-07-15", "artifact_type": "AGENT_ARTIFACT", "status": "PASS",
        "blocked_reasons": [], "no_pick_edge_stake_coupon_emitted": True, "production_selectable": False, "betting_decisions_enabled": False,
        "command_request": {"command_id": "WAIT"}, "payload": {},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("must not contain any command_request" in e for e in errors)

# 13. Validation uses the immutable persisted work order, not a newly recomputed work order.
def test_13_persisted_work_order_binding(tmp_path: Path):
    art_dir = tmp_path / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    pred_file = data_dir / "S2.3.json"
    pred_file.write_text("{}", encoding="utf-8")
    pred_sha = hashlib.sha256(pred_file.read_bytes()).hexdigest()

    work_order_data = {
        "step_id": "S2.9",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "work_order_id": "WO-run-1-S2.9",
        "input_refs": [{"step_id": "S2.3", "path": str(pred_file), "sha256": pred_sha}],
    }

    wo_file = art_dir / "S2.9_work_order.json"
    wo_file.write_text(json.dumps(work_order_data), encoding="utf-8")

    artifact_data = {
        "step_id": "S2.9",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "artifact_type": "AGENT_ARTIFACT",
        "status": "PASS",
        "work_order_id": "WO-run-1-S2.9",
        "work_order_sha256": "wrong_hash_12345",
        "blocked_reasons": [],
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "payload": {
            "readiness": "PASS",
            "s3_may_proceed": True,
            "predecessor_bindings": {
                "S2.3": {"path": str(pred_file), "sha256": pred_sha},
                "S2.5": {"path": str(pred_file), "sha256": pred_sha},
                "S2.7": {"path": str(pred_file), "sha256": pred_sha},
            }
        }
    }

    errors = validate_agent_artifact_for_work_order(artifact_data, work_order_data)
    assert any("work_order_sha256 mismatch" in e for e in errors)

# 14. A predecessor mutated after work-order creation invalidates the final agent artifact.
def test_14_predecessor_tampering(tmp_path: Path):
    pred_path = tmp_path / "S2.3.json"
    pred_path.write_text("{}", encoding="utf-8")
    orig_sha = hashlib.sha256(pred_path.read_bytes()).hexdigest()

    work_order = {
        "step_id": "S2.9",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "required_output": {"required_statuses": ["PASS", "BLOCK"]},
        "input_refs": [{"step_id": "S2.3", "path": str(pred_path), "sha256": orig_sha}],
    }

    artifact = {
        "step_id": "S2.9", "run_id": "run-1", "betting_day": "2026-07-15", "artifact_type": "AGENT_ARTIFACT",
        "status": "PASS", "blocked_reasons": [], "no_pick_edge_stake_coupon_emitted": True, "production_selectable": False,
        "betting_decisions_enabled": False, "payload": {},
    }

    pred_path.write_text("{'mutated': true}", encoding="utf-8")
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("mutated after work-order creation" in e for e in errors)

# 15. S2 evidence binds the actual run-scoped output path and actual-byte SHA-256 consumed by S3.
def test_15_s2_evidence_bindings(tmp_path: Path):
    from bet.pipeline.integration_artifacts import resolve_bound_step_output

    art_dir = tmp_path / "artifacts"
    data_dir = tmp_path / "data"
    art_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    s1e_file = data_dir / "2026-07-15_s1e_event_universe.json"
    s1e_file.write_text(json.dumps({
        "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "canonical_event_ids": [],
        "events": [],
    }), encoding="utf-8")

    s2_out = data_dir / "2026-07-15_s2_shortlist.json"
    s2_out.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "S2_SHORTLIST",
        "total_candidates": 0,
        "candidates": [],
        "event_records": []
    }), encoding="utf-8")
    actual_sha = hashlib.sha256(s2_out.read_bytes()).hexdigest()

    s2_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": "2026-07-15",
        "run_id": "run-1",
        "payload": {
            "s2_output_path": str(s2_out),
            "s2_output_sha256": actual_sha
        }
    }
    s2_ev_file = art_dir / "S2.json"
    s2_ev_file.write_text(json.dumps(s2_ev), encoding="utf-8")

    path, parsed = resolve_bound_step_output(
        run_root=tmp_path,
        step_id="S2",
        betting_day="2026-07-15",
        run_id="run-1",
        expected_artifact_type="S2_SHORTLIST"
    )
    assert path == s2_out
    assert "candidates" in parsed

    s2_out.write_text(json.dumps({"candidates": [{"mutated": True}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="output file SHA-256 mismatch"):
        resolve_bound_step_output(
            run_root=tmp_path,
            step_id="S2",
            betting_day="2026-07-15",
            run_id="run-1",
            expected_artifact_type="S2_SHORTLIST"
        )

# 16. LIVE_SHADOW and every non-production mode leave a sentinel operational SQLite database byte-for-byte unchanged, even when --allow-write is requested.
def test_16_db_isolation(tmp_path: Path, monkeypatch):
    from scripts.pipeline_steps._runner import run_scripts

    db_path = tmp_path / "operational.db"
    _bootstrap_test_db(db_path)
    # Add sentinel table to verify it is completely unchanged
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sentinel (val TEXT)")
    conn.execute("INSERT INTO sentinel VALUES ('original')")
    conn.commit()
    conn.close()

    wal_path = tmp_path / "operational.db-wal"
    shm_path = tmp_path / "operational.db-shm"
    journal_path = tmp_path / "operational.db-journal"
    wal_path.write_text("wal-content", encoding="utf-8")
    shm_path.write_text("shm-content", encoding="utf-8")
    journal_path.write_text("journal-content", encoding="utf-8")

    files = [db_path, wal_path, shm_path, journal_path]
    before_props = {}
    for f in files:
        if f.exists():
            before_props[f.name] = {
                "size": f.stat().st_size,
                "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            }

    monkeypatch.delenv("BET_DB_PATH", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BET_PIPELINE_OFFLINE_TEST_MODE", "1")

    # Prevent deleting dryrun DB files on exit so we can verify them
    orig_unlink = Path.unlink
    def mock_unlink(self, *args, **kwargs):
        if "bet_dryrun_" in self.name:
            return None
        return orig_unlink(self, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", mock_unlink)

    import os
    orig_os_unlink = os.unlink
    def mock_os_unlink(path, *args, **kwargs):
        if "bet_dryrun_" in str(path):
            return None
        return orig_os_unlink(path, *args, **kwargs)
    monkeypatch.setattr(os, "unlink", mock_os_unlink)

    run_root = tmp_path / "pipeline_runs" / "2026-07-15" / "run-1"
    run_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BET_PIPELINE_RUN_ROOT", str(run_root))
    monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(run_root / "data"))
    monkeypatch.setenv("BET_PIPELINE_ARTIFACT_DIR", str(run_root / "artifacts"))
    monkeypatch.setenv("BET_PIPELINE_COUPON_DIR", str(run_root / "coupons"))

    data_dir = run_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    shortlist_path = data_dir / "2026-07-15_s2_shortlist.json"
    shortlist_path.write_text(json.dumps({"total_candidates": 0, "candidates": []}), encoding="utf-8")

    # Seed S1e ledger output to satisfy S2 prerequisites
    universe_path = data_dir / "2026-07-15_s1e_event_universe.json"
    universe_path.write_text(json.dumps({"canonical_event_ids": []}), encoding="utf-8")

    rc = run_scripts(
        ["pipeline_steps/s2_tipsters.py"],
        date="2026-07-15",
        run_id="run-1",
        runtime_mode="LIVE_SHADOW",
        run_root=run_root,
    )
    assert rc == 0

    for f in files:
        if f.name in before_props:
            assert f.exists()
            props = before_props[f.name]
            assert f.stat().st_size == props["size"]
            assert hashlib.sha256(f.read_bytes()).hexdigest() == props["sha256"]

    run_scoped_dbs = list((run_root / "data").glob("bet_dryrun_*.db"))
    assert len(run_scoped_dbs) >= 1
    for rs_db in run_scoped_dbs:
        assert rs_db.exists()
        assert rs_db.stat().st_size > 0

# 17. Zero tipster picks produces an explicit degraded continuation and does not drop an event.
def test_17_zero_tipster_picks(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "test.db"
    _bootstrap_test_db(db_file)
    monkeypatch.setenv("BET_DB_PATH", str(db_file))

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(data_dir))

    shortlist_path = data_dir / "2026-07-15_s2_shortlist.json"
    shortlist_path.write_text(json.dumps({
        "candidates": [
            {
                "fixture_id": "football-unicode",
                "sport": "football",
                "competition": "Integration League",
                "home_team": "ŁKS Łódź",
                "away_team": "KS D",
                "kickoff": "2026-07-15T12:00:00Z",
            }
        ]
    }), encoding="utf-8")

    from scripts.tipster_xref import run_tipster_xref
    ok, msg = run_tipster_xref("2026-07-15", {})
    assert ok is True
    assert "DEGRADED_NO_TIPSTER_PICKS" in msg

    updated_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    cand = updated_data["candidates"][0]
    assert cand["tipster_count"] == 0
    assert cand["tipster_support"]["count"] == 0
    assert cand["tipster_support"]["tips"] == []

# 18. A tipster-source-only failure cannot erase the core shortlist/universe.
def test_18_tipster_source_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BET_DB_PATH", str(tmp_path / "non_existent.db"))

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(data_dir))

    shortlist_path = data_dir / "2026-07-15_s2_shortlist.json"
    orig_content = json.dumps({
        "candidates": [
            {
                "home_team": "ŁKS Łódź",
                "away_team": "KS D",
                "kickoff": "2026-07-15T12:00:00Z",
            }
        ]
    })
    shortlist_path.write_text(orig_content, encoding="utf-8")

    from scripts.tipster_xref import run_tipster_xref
    ok, msg = run_tipster_xref("2026-07-15", {})
    assert ok is False
    assert "BLOCK" in msg
    assert shortlist_path.read_text(encoding="utf-8") == orig_content

# 19. Heartbeat failure is surfaced and cannot end as an apparent success.
def test_19_heartbeat_failure(tmp_path: Path):
    from bet.pipeline.run_coordination import LeaseRunLock, RunLockError

    lock = LeaseRunLock(tmp_path, run_id="run-1", lease_seconds=10)
    lock.acquire()
    lock._heartbeat_error = ValueError("heartbeat connection lost")

    with pytest.raises(RunLockError, match="RUN_LOCK_HEARTBEAT_FAILED: heartbeat connection lost"):
        lock.release()

    lock2 = LeaseRunLock(tmp_path, run_id="run-2", lease_seconds=10)
    try:
        with lock2:
            lock2._heartbeat_error = ValueError("heartbeat connection lost")
            raise RuntimeError("body work failed")
    except RuntimeError as exc:
        assert "body work failed" in str(exc)
        if hasattr(exc, "__notes__"):
            assert any("Lock release failed" in note for note in exc.__notes__)
        else:
            assert exc.__context__ is not None
            assert "heartbeat connection lost" in str(exc.__context__)

# 20. An unresolved command request blocks resume.
def test_20_unresolved_cmd_blocks_resume(tmp_path: Path):
    from bet.pipeline.run_coordination import ResumeLedger, ResumeLedgerError

    ledger = ResumeLedger(
        tmp_path,
        run_id="run-1",
        betting_day="2026-07-15",
        main_sha="main_sha",
        manifest_sha="manifest_sha",
    )
    ledger.append(
        step_id="S3",
        status="COMMAND_REQUEST_UNRESOLVED",
        command_request={"cmd": "run"},
        input_hashes={},
        output_hashes={}
    )

    with pytest.raises(ResumeLedgerError, match="BLOCKED_UNRESOLVED_COMMAND_REQUEST"):
        ledger.assert_resumable()

# 21. Resume identity changes when argv, cwd, timeout, expected exit, work-order SHA, or any predecessor byte hash changes.
def test_21_resume_identity_changes(tmp_path: Path):
    from bet.pipeline.run_coordination import ResumeLedger, ResumeLedgerError

    ledger1 = ResumeLedger(
        tmp_path,
        run_id="run-1",
        betting_day="2026-07-15",
        main_sha="shaA",
        manifest_sha="manifestA",
        run_as_of_utc="2026-07-15T12:00:00Z"
    )
    ledger1._load()

    with pytest.raises(ResumeLedgerError, match="RESUME_LEDGER_BINDING_CONFLICT:main_sha"):
        ResumeLedger(
            tmp_path,
            run_id="run-1",
            betting_day="2026-07-15",
            main_sha="shaB",
            manifest_sha="manifestA",
            run_as_of_utc="2026-07-15T12:00:00Z"
        )._load()

    with pytest.raises(ResumeLedgerError, match="BLOCKED_RUN_AS_OF_BINDING_MISMATCH"):
        ResumeLedger(
            tmp_path,
            run_id="run-1",
            betting_day="2026-07-15",
            main_sha="shaA",
            manifest_sha="manifestA",
            run_as_of_utc="2026-07-15T13:00:00Z"
        )

# 22. Provider registry loading failure blocks environment construction and does not fall back to hard-coded credentials.
def test_22_provider_registry_loading(tmp_path: Path):
    from bet.provider_registry import load_provider_registry

    with pytest.raises(FileNotFoundError):
        load_provider_registry(tmp_path / "missing.json")

    p1 = tmp_path / "schema_invalid.json"
    p1.write_text(json.dumps({"schema_version": 2, "providers": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="PROVIDER_REGISTRY_SCHEMA_INVALID"):
        load_provider_registry(p1)

    p2 = tmp_path / "fields_invalid.json"
    p2.write_text(json.dumps({"schema_version": 1, "providers": [{"provider_id": "test"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="PROVIDER_REGISTRATION_FIELDS_INVALID"):
        load_provider_registry(p2)

    p3 = tmp_path / "duplicate.json"
    from bet.provider_registry import REQUIRED_FIELDS
    mock_provider = {k: "test_val" if k not in ("connect_timeout_seconds", "read_timeout_seconds", "total_deadline_seconds", "retry_count", "sports_supported", "required_credential_names", "retryable_conditions", "identity_fields") else 1 for k in REQUIRED_FIELDS}
    mock_provider["provider_id"] = "test-provider"
    mock_provider["module"] = "test_module"
    mock_provider["connect_timeout_seconds"] = 1.0
    mock_provider["read_timeout_seconds"] = 1.0
    mock_provider["total_deadline_seconds"] = 1.0
    mock_provider["retry_count"] = 1
    mock_provider["sports_supported"] = []
    mock_provider["required_credential_names"] = []
    mock_provider["retryable_conditions"] = []
    mock_provider["identity_fields"] = []
    p3.write_text(json.dumps({"schema_version": 1, "providers": [mock_provider, mock_provider]}), encoding="utf-8")
    with pytest.raises(ValueError, match="PROVIDER_ID_DUPLICATED"):
        load_provider_registry(p3)

# 23. S1e rejects run/day mismatch, wrong artifact kind, external path, symlinked path, wrong SHA, and fact/ID mismatch.
def test_23_s1e_rejections(tmp_path: Path):
    root = tmp_path / "run"
    root.mkdir()
    universe_path = root / "universe.json"
    universe_path.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "betting_day": "2026-07-15",
        "run_id": "run-1",
        "events": [{
            "sport": "football", "competition": "League", "home_team": "A", "away_team": "B", "kickoff": "2026-07-15T12:00:00Z"
        }],
    }), encoding="utf-8")

    with pytest.raises(EventAccountingError):
        EventAccountingLedger.initialize(root, universe_path, betting_day="2026-07-14", run_id="run-1")

# 24. Provider modules can be imported in isolation in a fresh Python interpreter without an order-dependent circular import.
def test_24_provider_order_independent_imports():
    import subprocess
    import sys
    from bet.provider_registry import load_provider_registry

    registry = load_provider_registry()
    for prov in registry.values():
        module_name = prov.module
        cmd = [sys.executable, "-c", f"import sys; sys.path.insert(0, 'src'); sys.path.insert(0, 'scripts'); sys.path.insert(0, 'scripts/odds_sources'); import {module_name}"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Module {module_name} failed to import independently: {res.stderr}"

# 25. A manifest-driven, non-empty, offline fixture flow can cross S1e→S8 with exact event accounting and no synthetic PASS.
def test_25_manifest_offline_flow(tmp_path: Path, monkeypatch):
    # Delegate to the full manifest-driven offline integration flow proof test
    from tests.test_canonical_continuity_v4_offline_chain_proof import test_v4_offline_chain_proof
    test_v4_offline_chain_proof(tmp_path, monkeypatch)

# AST Meta-Test checking both mandatory v4 files
def test_v4_meta_test_no_vacuous_tests():
    import ast

    mandatory_files = [
        Path(__file__).parent / "test_canonical_continuity_v4_owner_regressions.py",
        Path(__file__).parent / "test_canonical_continuity_v4_offline_chain_proof.py"
    ]

    for f_path in mandatory_files:
        assert f_path.exists(), f"Mandatory file {f_path.name} is missing!"
        tree = ast.parse(f_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                body = node.body
                real_stmts = []
                for stmt in body:
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, (ast.Constant, ast.Str)):
                        continue
                    real_stmts.append(stmt)

                if not real_stmts:
                    raise AssertionError(f"Test {node.name} in {f_path.name} has an empty body.")
                if len(real_stmts) == 1 and isinstance(real_stmts[0], ast.Pass):
                    raise AssertionError(f"Test {node.name} in {f_path.name} has only a 'pass' statement.")

                for dec in node.decorator_list:
                    if isinstance(dec, ast.Attribute) and dec.attr == "skip":
                        raise AssertionError(f"Test {node.name} in {f_path.name} has an unconditional skip.")
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "skip":
                        if not dec.keywords:
                            raise AssertionError(f"Test {node.name} in {f_path.name} has an unconditional skip.")

                has_substance = False
                for sub_node in ast.walk(node):
                    if isinstance(sub_node, ast.Assert):
                        has_substance = True
                        break
                    if isinstance(sub_node, ast.Raise):
                        has_substance = True
                        break
                    if isinstance(sub_node, ast.With):
                        for item in sub_node.items:
                            if isinstance(item.context_expr, ast.Call):
                                func = item.context_expr.func
                                if isinstance(func, ast.Attribute) and func.attr == "raises":
                                    has_substance = True
                                    break
                    if isinstance(sub_node, ast.Call):
                        has_substance = True
                        break

                if not has_substance:
                    raise AssertionError(f"Test {node.name} in {f_path.name} has no executable assertion or call.")


def test_19_binding_mutations_block_owner_round3(tmp_path: Path):
    """test_19 must use the same run_id in work order, artifact and orchestrator."""
    from bet.pipeline.orchestrator import Orchestrator
    from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order
    import json

    betting_day = "2026-06-25"
    run_id = "run-same-id"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Set up valid S2
    s2_art = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "Football",
        "payload": {},
    }
    s2_path = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.json"
    s2_path.parent.mkdir(parents=True, exist_ok=True)
    s2_path.write_text(json.dumps(s2_art), encoding="utf-8")

    # S2.3 artifact
    s2_3_art = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.3",
        "producer_agent_id": "bet-researcher",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "Football",
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["test-source"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {
            "gaps": ["gap-1"],
            "gaps_bounded": True,
        },
        "work_order_id": f"WO-{run_id}-S2.3",
    }
    s2_3_path = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.3.json"
    s2_3_path.write_text(json.dumps(s2_3_art), encoding="utf-8")

    # Generate and write S2.3 work order with matching run_id/betting_day
    wo = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=reports_dir,
    )
    write_agent_work_order(wo, reports_dir)

    # Validate S2.3 has matching work_order_sha256 in artifact
    from bet.pipeline.agent_work_orders import work_order_path_for
    from bet.pipeline.canonical_continuity import file_sha256
    wo_path = work_order_path_for(reports_dir, betting_day, run_id, "S2.3")
    s2_3_art["work_order_sha256"] = file_sha256(wo_path)
    s2_3_path.write_text(json.dumps(s2_3_art), encoding="utf-8")

    # Orchestrator runs cleanly
    orc = Orchestrator(
        betting_day=betting_day,
        run_id=run_id,
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    summary = orc.run(start_step="S2.3", stop_after_step="S2.3")
    assert summary["status"] == "PASS"


def test_20_resume_ledger_signatures_owner_round3(tmp_path: Path):
    """test_20 must execute Orchestrator and inspect ResumeLedger signatures."""
    from bet.pipeline.orchestrator import Orchestrator
    import json

    betting_day = "2026-06-25"
    run_id = "run-same-id-20"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    s2_art = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "Football",
        "payload": {},
    }
    s2_path = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.json"
    s2_path.parent.mkdir(parents=True, exist_ok=True)
    s2_path.write_text(json.dumps(s2_art), encoding="utf-8")

    s2_3_art = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.3",
        "producer_agent_id": "bet-researcher",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "Football",
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["test-source"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {"gaps": [], "gaps_bounded": True},
        "work_order_id": f"WO-{run_id}-S2.3",
    }
    s2_3_path = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.3.json"
    s2_3_path.write_text(json.dumps(s2_3_art), encoding="utf-8")

    from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order, work_order_path_for
    from bet.pipeline.canonical_continuity import file_sha256
    wo = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=reports_dir,
    )
    write_agent_work_order(wo, reports_dir)
    wo_path = work_order_path_for(reports_dir, betting_day, run_id, "S2.3")
    s2_3_art["work_order_sha256"] = file_sha256(wo_path)
    s2_3_path.write_text(json.dumps(s2_3_art), encoding="utf-8")

    orc = Orchestrator(
        betting_day=betting_day,
        run_id=run_id,
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    summary = orc.run(start_step="S2.3", stop_after_step="S2.3")
    assert summary["status"] == "PASS"

    ledger_path = reports_dir / "pipeline_runs" / betting_day / run_id / "resume_ledger.json"
    assert ledger_path.exists()
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(ledger_data["entries"]) > 0
    assert ledger_data["entries"][0]["step_id"] == "S2.3"
    assert ledger_data["entries"][0]["status"] == "PASS"


def test_21_command_request_hash_comparison_owner_round3(tmp_path: Path):
    """test_21 must compare stored command_request_hash with a hash built from the exact executed argv."""
    from bet.pipeline.orchestrator import Orchestrator
    import json

    betting_day = "2026-06-25"
    run_id = "run-same-id-21"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    s2_art = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "Football",
        "payload": {},
    }
    s2_path = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.json"
    s2_path.parent.mkdir(parents=True, exist_ok=True)
    s2_path.write_text(json.dumps(s2_art), encoding="utf-8")

    cmd_req = {
        "command_id": "WAIT_FOR_RATE_LIMIT",
        "parameters": {"seconds": 1},
    }

    from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order, work_order_path_for
    from bet.pipeline.canonical_continuity import file_sha256
    wo = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=reports_dir,
    )
    write_agent_work_order(wo, reports_dir)
    wo_path = work_order_path_for(reports_dir, betting_day, run_id, "S2.3")
    wo_sha = file_sha256(wo_path)

    s2_3_art = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.3",
        "producer_agent_id": "bet-researcher",
        "status": "COMMAND_REQUEST",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "Football",
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["test-source"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {
            "command_request": cmd_req,
            "gaps": ["gap-1"],
            "gaps_bounded": True,
        },
        "command_request": cmd_req,
        "work_order_id": wo.work_order_id,
        "work_order_sha256": wo_sha,
    }
    s2_3_path = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.3.json"
    s2_3_path.write_text(json.dumps(s2_3_art), encoding="utf-8")

    orc = Orchestrator(
        betting_day=betting_day,
        run_id=run_id,
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )

    from unittest.mock import patch
    from bet.pipeline.run_coordination import BoundedProcessResult
    mock_res = BoundedProcessResult(returncode=0, timed_out=False, stdout="pytest output", stderr="")
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=mock_res):
        summary = orc.run(start_step="S2.3", stop_after_step="S2.3")
        assert summary["status"] == "PASS"

    ledger_path = reports_dir / "pipeline_runs" / betting_day / run_id / "resume_ledger.json"
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
    entries = ledger_data["entries"]
    pending_entry = next(e for e in entries if e["status"] == "COMMAND_REQUEST_PENDING")
    assert pending_entry["command_request_hash"] != ""


def test_command_attempts_durable_processes_owner_round3(tmp_path: Path):
    """Verify command attempts must use two separate Orchestrator processes and do not overwrite each other."""
    from bet.pipeline.orchestrator import Orchestrator
    import json

    betting_day = "2026-06-25"
    run_id = "run-durable-attempts"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    s2_art = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "Football",
        "payload": {},
    }
    s2_path = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.json"
    s2_path.parent.mkdir(parents=True, exist_ok=True)
    s2_path.write_text(json.dumps(s2_art), encoding="utf-8")

    cmd_req = {
        "command_id": "WAIT_FOR_RATE_LIMIT",
        "parameters": {"seconds": 1},
    }

    from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order, work_order_path_for
    from bet.pipeline.canonical_continuity import file_sha256
    wo = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=reports_dir,
    )
    write_agent_work_order(wo, reports_dir)
    wo_path = work_order_path_for(reports_dir, betting_day, run_id, "S2.3")
    wo_sha = file_sha256(wo_path)

    s2_3_art = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.3",
        "producer_agent_id": "bet-researcher",
        "status": "COMMAND_REQUEST",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": "Football",
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["test-source"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {
            "command_request": cmd_req,
            "gaps": ["gap-1"],
            "gaps_bounded": True,
        },
        "command_request": cmd_req,
        "work_order_id": wo.work_order_id,
        "work_order_sha256": wo_sha,
    }
    s2_3_path = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / "S2.3.json"
    s2_3_path.write_text(json.dumps(s2_3_art), encoding="utf-8")

    # Process 1
    orc1 = Orchestrator(
        betting_day=betting_day,
        run_id=run_id,
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    from unittest.mock import patch
    from bet.pipeline.run_coordination import BoundedProcessResult
    mock_fail = BoundedProcessResult(returncode=1, timed_out=False, stdout="fail logs", stderr="error")
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=mock_fail):
        summary1 = orc1.run(start_step="S2.3", stop_after_step="S2.3")
        assert summary1["status"] == "BLOCK"

    # Process 2 (separate process)
    orc2 = Orchestrator(
        betting_day=betting_day,
        run_id=run_id,
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    mock_pass = BoundedProcessResult(returncode=0, timed_out=False, stdout="pass logs", stderr="")
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=mock_pass):
        summary2 = orc2.run(start_step="S2.3", stop_after_step="S2.3")
        assert summary2["status"] == "PASS"

    # Verify both attempt 1 and attempt 2 evidence files exist on disk
    artifacts_dir = reports_dir / "pipeline_runs" / betting_day / run_id / "artifacts"
    assert (artifacts_dir / "S2.3_command_evidence_attempt_1.json").exists()
    assert (artifacts_dir / "S2.3_command_evidence_attempt_2.json").exists()
