from pathlib import Path
import tempfile
import json
import sqlite3
from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.activation_bridge import run_activation_bridge
from bet.enrichment.football_data_foundation.worldcup_20260624_live_shadow.normalizer import normalize_fixture_snapshot

def test_activation_bridge_writes_compatible_artifacts() -> None:
    # TEST-009: activation bridge writes source-bound-compatible artifacts.
    # TEST-010: activation bridge supports generic ActivationPolicy expected_score=None.
    project_root = Path(".")
    fixture_slug = "worldcup2026-switzerland-canada"
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        run_dir = Path(tmp_dir) / "run_test"
        shadow_artifacts_root = run_dir / "shadow_artifacts"
        
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
