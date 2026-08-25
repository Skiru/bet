import hashlib
import json
import sqlite3
from pathlib import Path

from bet.db.repositories import EventStageCompletionRepository
from bet.db.schema import init_db
from bet.pipeline.event_runtime_contract import build_participant_identity
from bet.pipeline.event_stage_completion import build_stage_input_fingerprint
from bet.pipeline.launch_bridge import classify_and_persist_runtime_events
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.provider_observation_evidence import (
    persist_provider_observation_with_evidence,
)
from bet.pipeline.receipts import compute_source_manifest_sha256
from bet.pipeline.required_stage_chain import RequiredEventStageChainResolver


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _register_valid_chain(
    conn: sqlite3.Connection,
    tmp_path: Path,
    *,
    event_id: str,
    run_id: str,
    provider_attempt: dict,
) -> tuple[dict[str, Path], dict[str, Path]]:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = load_pipeline_manifest(repo_root / "config/pipeline_manifest.json")
    chain = RequiredEventStageChainResolver().resolve_required_stages(
        manifest=manifest, event_identity=event_id, sport="football"
    )
    code_sha = compute_source_manifest_sha256(repo_root)
    policy_sha = _sha(repo_root / "config/pipeline_manifest.json")
    provider_sha = _sha(repo_root / "config/provider_registry.json")
    model_sha = _sha(repo_root / "config/model_registry.json")
    participant_sha = build_participant_identity("Team A", "Team B").identity_sha256
    base = {
        "canonical_event_id": event_id,
        "fixture_id": int(event_id),
        "provider": provider_attempt["provider"],
        "provider_event_id": provider_attempt["provider_event_id"],
        "canonical_status": provider_attempt["canonical_event_status"],
        "observed_kickoff_utc": provider_attempt["observed_kickoff_utc"],
        "participant_identity_sha256": participant_sha,
        "provider_evidence_sha256": provider_attempt["observation_envelope_sha256"],
        "upstream_revision_hashes": [provider_attempt["observation_envelope_sha256"]],
    }
    artifact_root = tmp_path / "stage-artifacts"
    artifact_root.mkdir(exist_ok=True)
    repository = EventStageCompletionRepository(conn)
    output_hashes = {}
    outputs = {}
    receipts = {}
    chain_ids = set(chain.stage_ids)
    for stage in chain.stages:
        output = artifact_root / f"{event_id}-{stage.stage_id}-output.json"
        output.write_text(json.dumps({"stage": stage.stage_id}), encoding="utf-8")
        output_sha = _sha(output)
        dependencies = {
            dependency: output_hashes.get(dependency)
            for dependency in stage.dependencies
            if dependency in chain_ids
        }
        fingerprint = build_stage_input_fingerprint(
            base_fingerprint_input=base,
            stage=stage,
            required_chain_digest=chain.digest,
            dependency_output_hashes=dependencies,
            code_manifest_sha256=code_sha,
            policy_config_sha256=policy_sha,
            provider_config_sha256=provider_sha,
            model_registry_sha256=model_sha,
        )
        receipt = artifact_root / f"{event_id}-{stage.stage_id}-receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "canonical_event_id": event_id,
                    "stage_id": stage.stage_id,
                    "output_sha256": output_sha,
                    "input_fingerprint": fingerprint,
                    "producer": stage.producer,
                    "run_id": run_id,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        repository.register_completion(
            state={
                "canonical_event_id": event_id,
                "stage_id": stage.stage_id,
                "status": "PASS",
                "input_fingerprint": fingerprint,
                "output_sha256": output_sha,
                "receipt_sha256": _sha(receipt),
                "code_head": "test",
                "source_manifest_sha256": code_sha,
                "model_registry_sha256": model_sha
                if stage.uses_model_registry
                else None,
                "provider_config_sha256": provider_sha
                if stage.uses_provider_config
                else None,
                "run_id": run_id,
                "completed_at": "2027-07-30T11:00:00Z",
                "updated_at": "2027-07-30T11:00:00Z",
            },
            artifact={
                "output_path": str(output),
                "receipt_path": str(receipt),
                "artifact_root": str(artifact_root),
                "stage_contract_version": stage.contract_version,
                "policy_config_sha256": policy_sha
                if stage.uses_policy_config
                else None,
                "producer": stage.producer,
                "dependency_output_hashes_json": json.dumps(
                    dependencies, sort_keys=True
                ),
                "registered_at": "2027-07-30T11:00:00Z",
            },
        )
        output_hashes[stage.stage_id] = output_sha
        outputs[stage.stage_id] = output
        receipts[stage.stage_id] = receipt
    return outputs, receipts


def test_c5_end_to_end_safe_classification(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "runtime.db")
    init_db(conn)
    conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    conn.execute(
        "INSERT INTO teams (id, sport_id, name) "
        "VALUES (1, 1, 'Team A'), (2, 1, 'Team B')"
    )
    fixtures = [
        (1, "p1", "2027-07-30T14:00:00Z", "SCHEDULED"),
        (2, "p2", "2027-07-30T15:00:00Z", "SCHEDULED"),
        (3, "p3", "2027-07-30T16:00:00Z", "POSTPONED"),
        (4, "p4", "2027-07-30T09:00:00Z", "SCHEDULED"),
    ]
    for fixture_id, external_id, kickoff, status in fixtures:
        conn.execute(
            """INSERT INTO fixtures (
               id, external_id, sport_id, home_team_id, away_team_id,
               kickoff, status, source, fetched_at)
               VALUES (?, ?, 1, 1, 2, ?, ?, 'api_football', '2027-07-30T08:00:00Z')""",
            (fixture_id, external_id, kickoff, status),
        )
    conn.commit()

    participant_sha = build_participant_identity("Team A", "Team B").identity_sha256
    attempts = [
        (1, "SUCCESS", "SCHEDULED", "2027-07-30T14:00:00Z"),
        (2, "FAILED", "UNKNOWN", "2027-07-30T15:00:00Z"),
        (3, "SUCCESS", "POSTPONED", "2027-07-30T16:00:00Z"),
        (4, "SUCCESS", "SCHEDULED", "2027-07-30T09:00:00Z"),
    ]
    for fixture_id, request_status, canonical_status, kickoff in attempts:
        persist_provider_observation_with_evidence(
            conn,
            {
                "run_id": "run-c5",
                "phase": "PLAN",
                "attempt_number": 1,
                "canonical_event_id": str(fixture_id),
                "fixture_id": fixture_id,
                "provider": "api_football",
                "provider_event_id": f"p{fixture_id}",
                "attempted_at_utc": "2027-07-30T10:00:00Z",
                "request_status": request_status,
                "raw_provider_status": canonical_status,
                "canonical_event_status": canonical_status,
                "raw_observed_kickoff": kickoff,
                "observed_kickoff_utc": kickoff,
                "observed_home_name": "Team A",
                "observed_away_name": "Team B",
                "participant_identity_sha256": participant_sha,
            },
            tmp_path / "evidence",
        )

    counts = classify_and_persist_runtime_events(
        conn, "2027-07-30", "run-c5", "2027-07-30T10:00:00Z"
    )
    decisions = dict(
        conn.execute(
            "SELECT canonical_event_id, decision "
            "FROM pipeline_runtime_event_selection WHERE run_id = 'run-c5'"
        ).fetchall()
    )
    assert decisions == {
        "1": "ANALYZE_FROM_S2",
        "2": "PROVIDER_RECHECK_REQUIRED",
        "3": "POSTPONED",
        "4": "TIME_EXPIRED_UNCONFIRMED",
    }
    assert sum(counts.values()) == 4


def test_c5_end_to_end_full_required_chain_is_reused(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "complete.db")
    init_db(conn)
    conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    conn.execute(
        "INSERT INTO teams (id, sport_id, name) "
        "VALUES (1, 1, 'Team A'), (2, 1, 'Team B')"
    )
    conn.execute(
        """INSERT INTO fixtures (
           id, external_id, sport_id, home_team_id, away_team_id,
           kickoff, status, source, fetched_at)
           VALUES (1, 'p1', 1, 1, 2, '2027-07-30T14:00:00Z',
                   'SCHEDULED', 'api_football', '2027-07-30T08:00:00Z')"""
    )
    conn.commit()
    participant_sha = build_participant_identity("Team A", "Team B").identity_sha256
    attempt_id = persist_provider_observation_with_evidence(
        conn,
        {
            "run_id": "run-complete",
            "phase": "PLAN",
            "attempt_number": 1,
            "canonical_event_id": "1",
            "fixture_id": 1,
            "provider": "api_football",
            "provider_event_id": "p1",
            "attempted_at_utc": "2027-07-30T09:00:00Z",
            "request_status": "SUCCESS",
            "raw_provider_status": "NS",
            "canonical_event_status": "SCHEDULED",
            "raw_observed_kickoff": "2027-07-30T14:00:00Z",
            "observed_kickoff_utc": "2027-07-30T14:00:00Z",
            "observed_home_name": "Team A",
            "observed_away_name": "Team B",
            "participant_identity_sha256": participant_sha,
        },
        tmp_path / "evidence",
    )
    conn.row_factory = sqlite3.Row
    attempt = dict(
        conn.execute(
            "SELECT * FROM pipeline_provider_observation_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()
    )
    outputs, receipts = _register_valid_chain(
        conn,
        tmp_path,
        event_id="1",
        run_id="run-complete",
        provider_attempt=attempt,
    )
    counts = classify_and_persist_runtime_events(
        conn, "2027-07-30", "run-complete", "2027-07-30T10:00:00Z"
    )
    assert counts["ALREADY_VALID_COMPLETE"] == 1
    decision = conn.execute(
        "SELECT decision FROM pipeline_runtime_event_selection WHERE run_id = ?",
        ("run-complete",),
    ).fetchone()[0]
    assert decision == "ALREADY_VALID_COMPLETE"

    last_stage = next(reversed(outputs))
    original_output = outputs[last_stage].read_text(encoding="utf-8")
    outputs[last_stage].write_text('{"tampered":true}', encoding="utf-8")
    counts = classify_and_persist_runtime_events(
        conn, "2027-07-30", "run-complete", "2027-07-30T10:00:00Z"
    )
    assert counts["ANALYZE_FROM_S2"] == 1

    outputs[last_stage].write_text(original_output, encoding="utf-8")
    receipts[last_stage].unlink()
    counts = classify_and_persist_runtime_events(
        conn, "2027-07-30", "run-complete", "2027-07-30T10:00:00Z"
    )
    assert counts["ANALYZE_FROM_S2"] == 1

    def persist_current_attempt(number: int, request: str, status: str) -> None:
        persist_provider_observation_with_evidence(
            conn,
            {
                "run_id": "run-complete",
                "phase": "PLAN",
                "attempt_number": number,
                "canonical_event_id": "1",
                "fixture_id": 1,
                "provider": "api_football",
                "provider_event_id": "p1",
                "attempted_at_utc": f"2027-07-30T09:0{number}:00Z",
                "request_status": request,
                "raw_provider_status": status,
                "canonical_event_status": status,
                "raw_observed_kickoff": "2027-07-30T14:00:00Z",
                "observed_kickoff_utc": "2027-07-30T14:00:00Z",
                "observed_home_name": "Team A",
                "observed_away_name": "Team B",
                "participant_identity_sha256": participant_sha,
            },
            tmp_path / "evidence",
        )

    persist_current_attempt(2, "FAILED", "UNKNOWN")
    counts = classify_and_persist_runtime_events(
        conn, "2027-07-30", "run-complete", "2027-07-30T10:00:00Z"
    )
    assert counts["PROVIDER_RECHECK_REQUIRED"] == 1

    persist_current_attempt(3, "SUCCESS", "POSTPONED")
    counts = classify_and_persist_runtime_events(
        conn, "2027-07-30", "run-complete", "2027-07-30T10:00:00Z"
    )
    assert counts["POSTPONED"] == 1

    persist_current_attempt(4, "SUCCESS", "AWARDED_TERMINAL")
    counts = classify_and_persist_runtime_events(
        conn, "2027-07-30", "run-complete", "2027-07-30T10:00:00Z"
    )
    assert counts["AWARDED_TERMINAL"] == 1
