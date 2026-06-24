from pathlib import Path
import tempfile
import json
import sqlite3
from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.activation_bridge import run_activation_bridge
from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.normalizer import normalize_fixture_snapshot

def write_valid_fetched_envelope(cache_dir: Path, provider: str, slug: str) -> None:
    envelope = {
        "fixture_slug": slug,
        "provider": provider,
        "request_purpose": f"{provider}_fixture_detail_capture",
        "source_url": f"https://api.{provider}.dev/v1/detail",
        "status": "FETCHED",
        "status_code": 200,
        "body": {"eventId": "999999", "response": [{"goals": {"home": 2, "away": 1}}]},
        "body_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "captured_at_utc": "2026-06-24T12:00:00Z",
        "sanitized": True,
        "headers_redacted": True,
        "secrets_stored": False,
        "network_used": True,
        "provider_fixture_id": "999999"
    }
    prov_dir = cache_dir / "cache" / provider
    prov_dir.mkdir(parents=True, exist_ok=True)
    (prov_dir / f"{slug}.json").write_text(json.dumps(envelope))


def test_activation_bridge_writes_compatible_artifacts() -> None:
    # TEST-009: activation bridge writes source-bound-compatible artifacts.
    # TEST-010: activation bridge supports generic ActivationPolicy expected_score=None.
    project_root = Path(".")
    fixture_slug = "worldcup2026-switzerland-canada"
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        run_dir = Path(tmp_dir) / "run_test"
        shadow_artifacts_root = run_dir / "shadow_artifacts"
        
        # Write 5 FETCHED envelopes to satisfy activation bridge requirements
        write_valid_fetched_envelope(run_dir, "api-football", fixture_slug)
        write_valid_fetched_envelope(run_dir, "sportdb", fixture_slug)
        write_valid_fetched_envelope(run_dir, "highlightly", fixture_slug)
        write_valid_fetched_envelope(run_dir, "football-data-org", fixture_slug)
        write_valid_fetched_envelope(run_dir, "espn-baseline", fixture_slug)
        
        # Build normalized snapshot
        snapshot = normalize_fixture_snapshot(
            fixture_slug=fixture_slug,
            home_team="Switzerland",
            away_team="Canada",
            group="B",
            kickoff_utc="2026-06-24T21:00:00Z",
            cache_dir=run_dir,
            run_id="run_test_123"
        )
        
        # Modify facts to have correct file path format
        for fact in snapshot["facts"]:
            fact["source_file"] = f"reports/football_data_foundation/worldcup_20260624_live_shadow/run_test/cache/{fact['source']}/{fixture_slug}.json"

        # Execute bridge
        res = run_activation_bridge(
            project_root=project_root,
            fixture_slug=fixture_slug,
            snapshot=snapshot,
            sqlite_path=run_dir / "temp.sqlite",
            shadow_artifacts_root=shadow_artifacts_root,
            commit_sha="87184fe"
        )
        
        assert res["status"] == "ACTIVATION_CANDIDATE_SHADOW_ONLY"
        
        # Verify artifact files exist under shadow_artifacts
        fixture_underscored = fixture_slug.replace("-", "_")
        dest_dir = shadow_artifacts_root / fixture_underscored
        
        assert (dest_dir / "source_bound_shadow_snapshot.json").exists()
        assert (dest_dir / "source_bound_shadow.sqlite").exists()
        assert (dest_dir / "source_bound_verifier_result.json").exists()
        assert (dest_dir / "provider_fact_counts.json").exists()
        assert (dest_dir / "public_artifact_proof.json").exists()
        
        # Verify SQLite table schema
        con = sqlite3.connect(dest_dir / "source_bound_shadow.sqlite")
        try:
            tables = {row[0] for row in con.execute("select name from sqlite_master where type='table'")}
            assert "facts" in tables
            assert "provider_ids" in tables
            assert "snapshot_metadata" in tables
            assert "conflicts" in tables
        finally:
            con.close()
