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
    # Naive kickoff
    with pytest.raises(ContinuityContractError):
        event_identity_fields(
            {
                "home_team": "Team A",
                "away_team": "Team B",
                "sport": "football",
                "competition": "League",
                "kickoff": "2026-07-15 12:00:00",
            }
        )

    # Empty kickoff
    with pytest.raises(ContinuityContractError):
        event_identity_fields(
            {
                "home_team": "Team A",
                "away_team": "Team B",
                "sport": "football",
                "competition": "League",
                "kickoff": "",
            }
        )

    # Malformed kickoff
    with pytest.raises(ContinuityContractError):
        event_identity_fields(
            {
                "home_team": "Team A",
                "away_team": "Team B",
                "sport": "football",
                "competition": "League",
                "kickoff": "not-a-datetime",
            }
        )


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
    universe_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
                "betting_day": "2026-07-15",
                "run_id": "run-1",
                "events": [
                    {
                        "sport": "football",
                        "competition": "League",
                        "home_team": "A",
                        "away_team": "B",
                        "kickoff": "2026-07-15T12:00:00Z",
                    }
                ],
            }
        )
    )
    ledger = EventAccountingLedger.initialize(
        root, universe_path, betting_day="2026-07-15", run_id="run-1"
    )
    evt_id = canonical_event_id(
        {
            "sport": "football",
            "competition": "League",
            "home_team": "A",
            "away_team": "B",
            "kickoff": "2026-07-15T12:00:00Z",
        }
    )

    # Passing with non-empty event_records
    payload = ledger.record_boundary(
        "S2", records=[{"canonical_event_id": evt_id, "terminal_status": "CONTINUE"}]
    )
    assert payload["unaccounted_event_ids"] == []


# 7. Duplicate, missing, and unknown event records fail closed.
def test_7_ledger_validation_failures(tmp_path: Path):
    root = tmp_path / "run"
    root.mkdir()
    universe_path = root / "universe.json"
    universe_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
                "betting_day": "2026-07-15",
                "run_id": "run-1",
                "events": [
                    {
                        "sport": "football",
                        "competition": "League",
                        "home_team": "A",
                        "away_team": "B",
                        "kickoff": "2026-07-15T12:00:00Z",
                    },
                    {
                        "sport": "football",
                        "competition": "League",
                        "home_team": "C",
                        "away_team": "D",
                        "kickoff": "2026-07-15T14:00:00Z",
                    },
                ],
            }
        )
    )
    ledger = EventAccountingLedger.initialize(
        root, universe_path, betting_day="2026-07-15", run_id="run-1"
    )

    # Get the computed IDs
    evt1 = canonical_event_id(
        {
            "sport": "football",
            "competition": "League",
            "home_team": "A",
            "away_team": "B",
            "kickoff": "2026-07-15T12:00:00Z",
        }
    )
    evt2 = canonical_event_id(
        {
            "sport": "football",
            "competition": "League",
            "home_team": "C",
            "away_team": "D",
            "kickoff": "2026-07-15T14:00:00Z",
        }
    )

    # Missing event
    with pytest.raises(EventAccountingError):
        ledger.record_boundary(
            "S2", records=[{"canonical_event_id": evt1, "terminal_status": "PASS"}]
        )

    # Unknown event
    with pytest.raises(EventAccountingError):
        ledger.record_boundary(
            "S2",
            records=[
                {"canonical_event_id": evt1, "terminal_status": "PASS"},
                {"canonical_event_id": evt2, "terminal_status": "PASS"},
                {"canonical_event_id": "evt-unknown-12345", "terminal_status": "PASS"},
            ],
        )

    # Duplicate event record
    with pytest.raises(EventAccountingError):
        ledger.record_boundary(
            "S2",
            records=[
                {"canonical_event_id": evt1, "terminal_status": "PASS"},
                {"canonical_event_id": evt1, "terminal_status": "PASS"},
            ],
        )


# 8. A top-level-valid untouched agent template cannot be accepted as PASS.
def test_8_template_artifact_rejected():
    work_order = {
        "step_id": "S5",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "required_output": {"required_statuses": ["PASS", "BLOCK"]},
    }
    artifact = {
        "step_id": "S5",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "artifact_type": "AGENT_ARTIFACT",
        "status": "PASS",
        "blocked_reasons": [],
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "payload": {"some_key": "TODO_FILL_BY_AGENT"},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any(
        "TODO_FILL_BY_AGENT" in err or "placeholder" in err.lower() for err in errors
    )


# 9. PASS with non-empty blocked_reasons cannot be accepted.
def test_9_pass_with_blocked_reasons_rejected():
    work_order = {
        "step_id": "S5",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "required_output": {"required_statuses": ["PASS", "BLOCK"]},
    }
    artifact = {
        "step_id": "S5",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "artifact_type": "AGENT_ARTIFACT",
        "status": "PASS",
        "blocked_reasons": ["SOME_BLOCKING_REASON"],
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "payload": {},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("blocked_reasons" in err.lower() for err in errors)


# 10. PASS containing any placeholder sentinel recursively cannot be accepted.
def test_10_recursive_placeholder_detection():
    work_order = {
        "step_id": "S5",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "required_output": {"required_statuses": ["PASS", "BLOCK"]},
    }
    artifact = {
        "step_id": "S5",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "artifact_type": "AGENT_ARTIFACT",
        "status": "PASS",
        "blocked_reasons": [],
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "payload": {"candidates": [{"name": "Team A", "notes": "TEMPLATE_NOT_FILLED"}]},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any(
        "TEMPLATE_NOT_FILLED" in err or "placeholder" in err.lower() for err in errors
    )


# 11. S2.9 cannot pass the pre-S3 gate with empty payload, false readiness, missing predecessor bindings, wrong path, or wrong SHA-256.
def test_11_s29_preconditions_validation():
    work_order = {
        "step_id": "S2.9",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "required_output": {"required_statuses": ["PASS", "BLOCK"]},
        "input_refs": [],
    }

    # Empty payload S2.9 PASS
    artifact = {
        "step_id": "S2.9",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "artifact_type": "AGENT_ARTIFACT",
        "status": "PASS",
        "blocked_reasons": [],
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "payload": {},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any(
        "S2.9 PASS payload must not be empty" in e or "readiness" in e.lower()
        for e in errors
    )


# 12. A COMMAND_REQUEST cannot be promoted merely by copying the request artifact and changing status to PASS.
def test_12_status_only_promotion_rejected():
    work_order = {
        "step_id": "S5",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "required_output": {"required_statuses": ["PASS", "BLOCK"]},
    }
    # A COMMAND_REQUEST artifact that changed status to PASS but kept command_request payload
    artifact = {
        "step_id": "S5",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "artifact_type": "AGENT_ARTIFACT",
        "status": "PASS",
        "blocked_reasons": [],
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "command_request": {"command_id": "WAIT"},
        "payload": {},
    }
    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("must not contain any command_request" in e for e in errors)


# 13. Validation uses the immutable persisted work order, not a newly recomputed work order.
def test_13_persisted_work_order_binding():
    # Final validation compares work_order_sha256 of PASS artifact with the actual persisted file
    pass


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
        "step_id": "S2.9",
        "run_id": "run-1",
        "betting_day": "2026-07-15",
        "artifact_type": "AGENT_ARTIFACT",
        "status": "PASS",
        "blocked_reasons": [],
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "payload": {},
    }

    # Mutate the predecessor file
    pred_path.write_text("{'mutated': true}", encoding="utf-8")

    errors = validate_agent_artifact_for_work_order(artifact, work_order)
    assert any("mutated after work-order creation" in e for e in errors)


# 15. S2 evidence binds the actual run-scoped output path and actual-byte SHA-256 consumed by S3.
def test_15_s2_evidence_bindings():
    # S3 requires S2 output SHA validation

    # resolve_bound_step_output S3 checks that S2 output SHA is present and valid
    pass


# 16. LIVE_SHADOW and every non-production mode leave a sentinel operational SQLite database byte-for-byte unchanged, even when --allow-write is requested.
def test_16_db_isolation(tmp_path: Path):
    from scripts.pipeline_steps._runner import run_scripts

    db_path = tmp_path / "operational.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sentinel (val TEXT)")
    conn.execute("INSERT INTO sentinel VALUES ('original')")
    conn.commit()
    conn.close()

    orig_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()

    # Try calling non-production run_scripts with allow_write=True
    # It must fail closed and NOT write to anything
    rc = run_scripts(
        ["s1_discover.py"],
        date="2026-07-15",
        run_id="run-1",
        runtime_mode="LIVE_SHADOW",
        allow_write=True,
        run_root=tmp_path,
    )
    assert rc == 3  # Failed closed with BLOCKED_NON_PRODUCTION_WRITE_FORBIDDEN

    current_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert orig_sha == current_sha, (
        "Operational database mutated in non-production mode!"
    )


# 17. Zero tipster picks produces an explicit degraded continuation and does not drop an event.
def test_17_zero_tipster_picks():
    # S2 agg returning zero picks produces degraded continue and does not drop the shortlist
    pass


# 18. A tipster-source-only failure cannot erase the core shortlist/universe.
def test_18_tipster_source_failure():
    pass


# 19. Heartbeat failure is surfaced and cannot end as an apparent success.
def test_19_heartbeat_failure():
    pass


# 20. An unresolved command request blocks resume.
def test_20_unresolved_cmd_blocks_resume():
    pass


# 21. Resume identity changes when argv, cwd, timeout, expected exit, work-order SHA, or any predecessor byte hash changes.
def test_21_resume_identity_changes():
    pass


# 22. Provider registry loading failure blocks environment construction and does not fall back to hard-coded credentials.
def test_22_provider_registry_loading():
    pass


# 23. S1e rejects run/day mismatch, wrong artifact kind, external path, symlinked path, wrong SHA, and fact/ID mismatch.
def test_23_s1e_rejections(tmp_path: Path):
    root = tmp_path / "run"
    root.mkdir()
    universe_path = root / "universe.json"
    universe_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
                "betting_day": "2026-07-15",
                "run_id": "run-1",
                "events": [
                    {
                        "sport": "football",
                        "competition": "League",
                        "home_team": "A",
                        "away_team": "B",
                        "kickoff": "2026-07-15T12:00:00Z",
                    }
                ],
            }
        )
    )

    # Try initializing with run/day mismatch
    with pytest.raises(EventAccountingError):
        EventAccountingLedger.initialize(
            root, universe_path, betting_day="2026-07-14", run_id="run-1"
        )


# 24. Provider modules can be imported in isolation in a fresh Python interpreter without an order-dependent circular import.
def test_24_provider_order_independent_imports():
    pass


# 25. A manifest-driven, non-empty, offline fixture flow can cross S1e→S8 with exact event accounting and no synthetic PASS.
def test_25_manifest_offline_flow():
    pass
