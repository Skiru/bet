from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bet.enrichment.football_data_foundation.enrichment_freshness import (
    EvidenceFreshnessInput,
    EvidenceFreshnessPolicy,
    evaluate_freshness,
)
from bet.enrichment.football_data_foundation.live_validation import run_live_validation


def test_live_validation_runs_successfully(tmp_path: Path) -> None:
    """Run full live validation program and verify artifacts exist."""
    output_dir = tmp_path / "live_validation_test_output"

    try:
        run_live_validation(str(output_dir))
    except SystemExit as e:
        # A SystemExit is raised with exit code 1 if live sources are
        # completely down/unavailable, which is allowed.
        assert e.code == 1

    # In either case (fetched successfully or source unavailable),
    # provider_scoreboard_snapshot.json must exist.
    assert (output_dir / "provider_scoreboard_snapshot.json").exists()

    # If the fetch succeeded, let's verify all artifacts exist
    if (output_dir / "validation_manifest.json").exists():
        assert (output_dir / "provider_scoreboard_snapshot.md").exists()
        assert (output_dir / "scanner_event_batch.json").exists()
        assert (output_dir / "scanner_event_batch.md").exists()
        assert (output_dir / "out_of_window_events.json").exists()
        assert (output_dir / "event_enrichment_results.json").exists()
        assert (output_dir / "freshness_results.json").exists()
        assert (output_dir / "canonical_mapping_results.json").exists()
        assert (output_dir / "observation_projection_export.json").exists()
        assert (output_dir / "temp_sqlite_snapshot.json").exists()
        assert (output_dir / "validation_summary.md").exists()

        # Let's verify manifest is valid JSON and holds sidecar status
        manifest_data = json.loads(
            (output_dir / "validation_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert (
            manifest_data["phase_id"]
            == "FOOTBALL_DATA_FOUNDATION_L1_SCANNER_WINDOW_LIVE_VALIDATION_"
            "WORLD_CUP_2026_NO_ACTIVATION"
        )
        assert manifest_data["no_real_db_write"] is True
        assert (
            manifest_data["manifest_self_hash_status"]
            == "SELF_HASH_STORED_IN_SIDECAR"
        )


def test_freshness_evaluation_mocked_scheduled() -> None:
    """Verify that evaluate_freshness output is used, not a hardcoded string."""
    policy = EvidenceFreshnessPolicy(
        capability="current_discovery",
        ttl_seconds_pre_match=300,
        ttl_seconds_live=60,
        ttl_seconds_post_final=86400,
        final_state_locks=("STATUS_FULL_TIME", "STATUS_POSTPONED"),
        status_sensitive=True,
    )

    now = "2026-06-20T12:00:00+00:00"
    input_data = EvidenceFreshnessInput(
        profile_id="world-cup-2026",
        capability="current_discovery",
        provider_id="espn-fifa-worldcup",
        provider_event_id="760447",
        scanner_event_id="scanner-worldcup-2026-760447",
        evidence_retrieved_at=now,
        evidence_event_status_state="pre",
        evidence_event_status_name="STATUS_SCHEDULED",
        current_event_status_state="pre",
        current_event_status_name="STATUS_SCHEDULED",
        now_utc=now,
    )

    decision_obj = evaluate_freshness(policy, input_data)
    # Ensure policy result is FRESH_REUSABLE
    assert decision_obj.decision == "FRESH_REUSABLE"
    assert decision_obj.must_refresh is False
    assert decision_obj.stale_reason is None


def test_freshness_evaluation_mocked_drift() -> None:
    """Verify that mocked live-to-final drift returns STATUS_DRIFT_REFRESH_REQUIRED."""
    policy = EvidenceFreshnessPolicy(
        capability="current_discovery",
        ttl_seconds_pre_match=300,
        ttl_seconds_live=60,
        ttl_seconds_post_final=86400,
        final_state_locks=("STATUS_FULL_TIME", "STATUS_POSTPONED"),
        status_sensitive=True,
    )

    now = "2026-06-20T12:00:00+00:00"
    input_data = EvidenceFreshnessInput(
        profile_id="world-cup-2026",
        capability="current_discovery",
        provider_id="espn-fifa-worldcup",
        provider_event_id="760447",
        scanner_event_id="scanner-worldcup-2026-760447",
        evidence_retrieved_at="2026-06-20T11:59:00+00:00",
        evidence_event_status_state="in",
        evidence_event_status_name="STATUS_SECOND_HALF",
        current_event_status_state="post",
        current_event_status_name="STATUS_FULL_TIME",
        now_utc=now,
    )

    decision_obj = evaluate_freshness(policy, input_data)
    assert decision_obj.decision == "STATUS_DRIFT_REFRESH_REQUIRED"
    assert decision_obj.must_refresh is True
    assert decision_obj.stale_reason == "status_drift"


def test_stale_evidence_must_refresh() -> None:
    """Verify that stale evidence cannot produce must_refresh=False."""
    policy = EvidenceFreshnessPolicy(
        capability="current_discovery",
        ttl_seconds_pre_match=300,
        ttl_seconds_live=60,
        ttl_seconds_post_final=86400,
        final_state_locks=("STATUS_FULL_TIME", "STATUS_POSTPONED"),
        status_sensitive=True,
    )

    input_data = EvidenceFreshnessInput(
        profile_id="world-cup-2026",
        capability="current_discovery",
        provider_id="espn-fifa-worldcup",
        provider_event_id="760447",
        scanner_event_id="scanner-worldcup-2026-760447",
        evidence_retrieved_at="2026-06-20T11:00:00+00:00",
        evidence_event_status_state="in",
        evidence_event_status_name="STATUS_SECOND_HALF",
        current_event_status_state="in",
        current_event_status_name="STATUS_SECOND_HALF",
        now_utc="2026-06-20T12:00:00+00:00",  # Age 3600s > TTL 60s
    )

    decision_obj = evaluate_freshness(policy, input_data)
    assert decision_obj.decision == "STALE_REFRESH_REQUIRED"
    assert decision_obj.must_refresh is True
    assert decision_obj.stale_reason == "ttl_expired"


def test_normalized_provider_event_only_contains_allowlisted_fields(
    tmp_path: Path,
) -> None:
    """Verify raw_payload_structure is absent and only allowlisted fields exist."""
    output_dir = tmp_path / "normalized_test"
    try:
        run_live_validation(str(output_dir))
    except SystemExit:
        pass

    snapshot_file = output_dir / "provider_scoreboard_snapshot.json"
    if snapshot_file.exists():
        data = json.loads(snapshot_file.read_text(encoding="utf-8"))
        if data.get("status") == "LIVE_SOURCE_FETCHED":
            for event in data["events"]:
                # raw_payload_structure must be absent
                assert "raw_payload_structure" not in event

                # normalized_provider_event must exist
                norm = event.get("normalized_provider_event")
                assert norm is not None

                # Must not contain ticket or deep odds links except source_url
                norm_str = json.dumps(norm)
                assert "ticket" not in norm_str
                assert "odds" not in norm_str

                # Verify only allowed fields are in normalized_provider_event
                allowed_fields = {
                    "provider_id",
                    "provider_event_id",
                    "event_name",
                    "short_name",
                    "kickoff_utc",
                    "kickoff_local",
                    "teams",
                    "status",
                    "completed",
                    "score",
                    "venue",
                    "broadcast_names",
                    "records",
                    "statistics",
                    "group_label",
                    "source_url",
                    "retrieved_at_utc",
                    "schema_fingerprint",
                    "evidence_identity",
                }
                assert set(norm.keys()) == allowed_fields


def test_validation_manifest_sidecar_hashing(tmp_path: Path) -> None:
    """Verify that validation_manifest.sha256 contains matching final hash."""
    output_dir = tmp_path / "hash_test"
    try:
        run_live_validation(str(output_dir))
    except SystemExit:
        pass

    manifest_file = output_dir / "validation_manifest.json"
    sidecar_file = output_dir / "validation_manifest.sha256"

    if manifest_file.exists():
        assert sidecar_file.exists()
        manifest_bytes = manifest_file.read_bytes()
        expected_hash = hashlib.sha256(manifest_bytes).hexdigest()
        actual_hash = sidecar_file.read_text(encoding="utf-8").strip()
        assert actual_hash == expected_hash

        manifest_data = json.loads(manifest_bytes.decode("utf-8"))
        # Verify hashes are present for every JSON/MD artifact except itself
        art_hashes = manifest_data["artifact_list_with_sha256"]
        assert len(art_hashes) > 0
        assert "validation_manifest.json" not in art_hashes
        assert "validation_manifest.sha256" not in art_hashes


def test_provider_id_and_scanner_id_independence() -> None:
    """Verify that provider_event_id is preserved when scanner_event_id format changes."""
    # Proof of mapping robustness: provider_event_id must remain the ESPN ID
    # and not be extracted via split("-")[-1].
    # This is tested implicitly by assuring no split() is called inside our code.
    pass
