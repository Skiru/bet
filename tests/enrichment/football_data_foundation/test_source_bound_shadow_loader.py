import json
from pathlib import Path
from bet.enrichment.football_data_foundation.source_bound_shadow.loader import load_provider_envelopes, load_mapping_metadata

def make_sample_run(root: Path) -> Path:
    run = root / "run_sample"
    providers = ["sportdb", "highlightly", "api-football", "football-data-org", "espn-baseline"]
    for p in providers:
        (run / p).mkdir(parents=True, exist_ok=True)
    def write(provider: str, name: str, body: object, sha: str = "abc") -> None:
        env = {
            "provider": provider,
            "status": "SUCCESS",
            "source_url": f"https://example.test/{provider}/{name}",
            "body": body,
            "body_sha256": sha + provider + name,
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": False,
        }
        (run / provider / name).write_text(json.dumps(env, sort_keys=True), encoding="utf-8")
    write("sportdb", "match_details.json", {"eventId": "xSUJLPV8", "homeName": "Norway", "awayName": "Senegal"})
    write("highlightly", "match_detail.json", {"id": 1267481035, "homeTeam": {"name": "Norway"}, "awayTeam": {"name": "Senegal"}})
    write("api-football", "fixture.json", {"fixture": {"id": 1489401}})
    write("football-data-org", "match.json", {"id": 537394})
    write("espn-baseline", "summary.json", {"id": "760454"})
    
    # Write metadata files to test skipping
    (run / "manifest.json").write_text("{}", encoding="utf-8")
    (run / "mapping_candidate.json").write_text("[]", encoding="utf-8")
    (run / "capture_verifier_result.json").write_text("{}", encoding="utf-8")
    return run

def test_loader_reads_runs_and_skips_meta_files(tmp_path):
    run_dir = make_sample_run(tmp_path)
    envelopes = load_provider_envelopes([run_dir])
    
    assert len(envelopes) == 5
    providers = {e.provider for e in envelopes}
    assert providers == {"sportdb", "highlightly", "api-football", "football-data-org", "espn-baseline"}
    
    # Ensure meta files are skipped
    paths = {e.path.name for e in envelopes}
    assert "manifest.json" not in paths
    assert "mapping_candidate.json" not in paths
    assert "capture_verifier_result.json" not in paths
