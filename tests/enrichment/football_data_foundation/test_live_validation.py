from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import bet.enrichment.football_data_foundation.active_enrichment as active_enrichment
from bet.enrichment.football_data_foundation.active_enrichment import (
    ActiveEnrichmentResult,
)
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

    # In either case, provider_scoreboard_snapshot.json must exist.
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
    """Verify that mocked live-to-final drift returns
    LIVE_STATUS_SENSITIVE_REFRESH_REQUIRED.
    """
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
    assert decision_obj.decision == "LIVE_STATUS_SENSITIVE_REFRESH_REQUIRED"
    assert decision_obj.must_refresh is True
    assert decision_obj.stale_reason == "STATUS_DRIFT_REFRESH_REQUIRED"


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
    assert decision_obj.decision == "LIVE_STATUS_SENSITIVE_REFRESH_REQUIRED"
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


def test_source_byte_integrity() -> None:
    """Verify that source files are strictly LF-only and have no CR/CRLF."""
    paths = [
        "src/bet/enrichment/football_data_foundation/live_validation.py",
        "tests/enrichment/football_data_foundation/test_live_validation.py",
    ]
    for path_str in paths:
        path = Path(path_str)
        assert path.exists()
        content = path.read_bytes()
        assert b"\r" not in content
        assert b"\r\n" not in content


def _generate_mock_espn_payload(num_events: int = 6) -> dict[str, Any]:
    events = []
    matches = [
        ("760447", "Netherlands", "NED", "Sweden", "SWE"),
        ("760448", "Germany", "GER", "Ivory Coast", "CIV"),
        ("760446", "Ecuador", "ECU", "Curacao", "CUW"),
        ("760449", "Tunisia", "TUN", "Japan", "JPN"),
        ("760453", "Spain", "ESP", "Saudi Arabia", "KSA"),
        ("760451", "Belgium", "BEL", "Iran", "IRN"),
    ]
    for i in range(min(num_events, 6)):
        p_id, h_name, h_code, a_name, a_code = matches[i]
        events.append(
            {
                "id": p_id,
                "date": "2026-06-20T17:00:00Z",
                "name": f"{h_name} vs {a_name}",
                "shortName": f"{h_code} vs {a_code}",
                "competitions": [
                    {
                        "status": {
                            "type": {
                                "name": "STATUS_SCHEDULED",
                                "state": "pre",
                                "completed": False,
                            }
                        },
                        "venue": {
                            "fullName": "Some Stadium",
                            "address": {
                                "city": "Some City",
                                "country": "Some Country",
                            },
                        },
                        "broadcasts": [{"names": ["ESPN"]}],
                        "competitors": [
                            {
                                "homeAway": "home",
                                "team": {
                                    "displayName": h_name,
                                    "abbreviation": h_code,
                                },
                                "records": [{"summary": "1-0-0"}],
                            },
                            {
                                "homeAway": "away",
                                "team": {
                                    "displayName": a_name,
                                    "abbreviation": a_code,
                                },
                                "records": [{"summary": "0-1-0"}],
                            },
                        ],
                    }
                ],
            }
        )
    return {"events": events}


def test_live_validation_success_path(tmp_path: Path) -> None:
    """Verify that when all 6 expected events succeed, verdict is PASS."""
    output_dir = tmp_path / "success_path"

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_payload = _generate_mock_espn_payload(6)
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_response):
        run_live_validation(str(output_dir))

    manifest = json.loads(
        (output_dir / "validation_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["selected_event_count"] == 6

    summary = (output_dir / "validation_summary.md").read_text(encoding="utf-8")
    assert "LIVE_VALIDATION_PASS" in summary


def test_failed_closed_verdict_blocked(tmp_path: Path) -> None:
    """Verify failed-closed active enrichment results block validation PASS.

    If all events are ENRICH_FAILED_CLOSED, the verdict must be a partial/blocked
    fact extraction gap rather than a PASS.
    """
    output_dir = tmp_path / "failed_closed"

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_payload = _generate_mock_espn_payload(6)
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")

    original_enrich = (
        active_enrichment.ActiveEnrichmentOrchestrator.enrich_event
    )

    def mock_enrich(self, request):
        res = original_enrich(self, request)
        return ActiveEnrichmentResult(
            profile_id=res.profile_id,
            scanner_event_id=res.scanner_event_id,
            canonical_match_identity=res.canonical_match_identity,
            status="ENRICH_FAILED_CLOSED",
            fetch_decisions=res.fetch_decisions,
            facts=(),
            evidence_refs=res.evidence_refs,
            unavailable_capabilities=res.unavailable_capabilities,
            conflict_diagnostics=res.conflict_diagnostics,
            production_betting_decision=res.production_betting_decision,
        )

    with patch("urllib.request.urlopen", return_value=mock_response), patch.object(
        active_enrichment.ActiveEnrichmentOrchestrator,
        "enrich_event",
        mock_enrich,
    ):
        run_live_validation(str(output_dir))

    summary = (output_dir / "validation_summary.md").read_text(encoding="utf-8")
    assert "LIVE_VALIDATION_PARTIAL_ENRICHMENT_FACT_EXTRACTION_GAP" in summary


def test_all_facts_zero_cannot_pass(tmp_path: Path) -> None:
    """Verify that if all events have facts=0, verdict is blocked/partial."""
    output_dir = tmp_path / "zero_facts"

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_payload = _generate_mock_espn_payload(6)
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")

    original_enrich = (
        active_enrichment.ActiveEnrichmentOrchestrator.enrich_event
    )

    def mock_enrich(self, request):
        res = original_enrich(self, request)
        return ActiveEnrichmentResult(
            profile_id=res.profile_id,
            scanner_event_id=res.scanner_event_id,
            canonical_match_identity=res.canonical_match_identity,
            status=res.status,
            fetch_decisions=res.fetch_decisions,
            facts=(),
            evidence_refs=res.evidence_refs,
            unavailable_capabilities=res.unavailable_capabilities,
            conflict_diagnostics=res.conflict_diagnostics,
            production_betting_decision=res.production_betting_decision,
        )

    with patch("urllib.request.urlopen", return_value=mock_response), patch.object(
        active_enrichment.ActiveEnrichmentOrchestrator,
        "enrich_event",
        mock_enrich,
    ):
        run_live_validation(str(output_dir))

    summary = (output_dir / "validation_summary.md").read_text(encoding="utf-8")
    assert "LIVE_VALIDATION_PARTIAL_ENRICHMENT_FACT_EXTRACTION_GAP" in summary


def test_partial_fact_coverage_produces_partial(tmp_path: Path) -> None:
    """Verify that if fewer than 6 events are returned, it produces PARTIAL."""
    output_dir = tmp_path / "partial"

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_payload = _generate_mock_espn_payload(3)  # only 3 events
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_response):
        run_live_validation(str(output_dir))

    manifest = json.loads(
        (output_dir / "validation_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["selected_event_count"] == 3

    summary = (output_dir / "validation_summary.md").read_text(encoding="utf-8")
    assert (
        "LIVE_VALIDATION_PARTIAL_ENRICHMENT_FACT_EXTRACTION_GAP" in summary
        or "LIVE_VALIDATION_PARTIAL" in summary
    )


def test_provider_event_id_explicit_and_not_parsed(tmp_path: Path) -> None:
    """Verify provider_event_id is explicit and not parsed from scanner_event_id."""
    output_dir = tmp_path / "explicit_prov_id"

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_payload = _generate_mock_espn_payload(1)
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_response):
        run_live_validation(str(output_dir))

    enrich_results_file = output_dir / "event_enrichment_results.json"
    assert enrich_results_file.exists()
    enrich_data = json.loads(enrich_results_file.read_text(encoding="utf-8"))

    assert enrich_data[0]["provider_event_id"] == "760447"

    prov_id_facts = [
        f
        for f in enrich_data[0]["facts"]
        if f["fact_name"] == "provider_event_id"
    ]
    assert len(prov_id_facts) == 1
    assert prov_id_facts[0]["fact_value_text"] == "760447"


def test_status_in_summary_comes_from_normalized_event(tmp_path: Path) -> None:
    """Verify status in summary comes from normalized event."""
    output_dir = tmp_path / "status_summary"

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_payload = _generate_mock_espn_payload(1)
    mock_payload["events"][0]["competitions"][0]["status"]["type"][
        "name"
    ] = "STATUS_IN_PROGRESS"
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_response):
        run_live_validation(str(output_dir))

    summary = (output_dir / "validation_summary.md").read_text(encoding="utf-8")
    assert "STATUS_IN_PROGRESS" in summary


def test_key_artifacts_lf_byte_integrity(tmp_path: Path) -> None:
    """Verify all generated artifacts are strictly LF-only and <= 240 char line length.

    Checks JSON, MD, and SHA256 artifacts for proper Unix line endings
    and correct max line length.
    """
    output_dir = tmp_path / "byte_integrity"

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_payload = _generate_mock_espn_payload(6)
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_response):
        run_live_validation(str(output_dir))

    (output_dir / "l1c3_false_raw_pass_review.md").write_text(
        "# fake review\n", encoding="utf-8"
    )

    for path in output_dir.glob("*"):
        if path.suffix not in {".json", ".md", ".sha256"}:
            continue
        data = path.read_bytes()
        assert b"\r" not in data
        lines = data.split(b"\n")
        max_line_len = max(len(line) for line in lines)
        assert (
            max_line_len <= 240
        ), f"{path} has line with length {max_line_len} > 240"
