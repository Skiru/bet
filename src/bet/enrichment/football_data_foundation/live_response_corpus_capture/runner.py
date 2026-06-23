import datetime
import uuid
from pathlib import Path
from typing import Any, Dict, List
from bet.enrichment.football_data_foundation.live_response_corpus_capture.contracts import (
    LiveCorpusManifest,
    ProviderResponseEnvelope,
    CaptureStatus,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.env_loader import (
    load_project_dotenv,
    get_credential,
    credential_presence_map,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.fixtures import (
    discover_canary_fixtures,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.providers import (
    capture_sportdb,
    capture_football_data_org,
    capture_highlightly,
    capture_api_football,
    capture_espn_baseline,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.sanitizer import (
    write_json,
)


def run_live_response_corpus_capture(corpus_root: Path, max_fixtures: int = 3) -> LiveCorpusManifest:
    """
    Execute the full capture process.
    Discover fixtures, invoke providers, write envelopes and manifest.
    """
    # 1. Setup run_id and run directory
    now_utc = datetime.datetime.utcnow()
    run_id = f"run_{now_utc.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    run_dir = corpus_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 2. Load environment variables
    project_root = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1")
    load_project_dotenv(project_root)
    cred_map = credential_presence_map()

    # Get credentials for our providers
    sportdb_cred = get_credential("SPORTDB_API_KEY")
    fd_cred = get_credential("FOOTBALL_DATA_ORG_KEY", ("FOOTBALL_DATA_API_KEY",))
    hl_cred = get_credential("HIGHLIGHTLY_API_KEY")
    af_cred = get_credential("API_FOOTBALL_KEY", ("API_FOOTBALL_API_KEY",))

    # 3. Discover fixtures
    fixtures = discover_canary_fixtures(max_fixtures)
    fixtures = fixtures[:max_fixtures]

    write_json(run_dir / "fixtures_discovered.json", fixtures)
    files_written = ["fixtures_discovered.json"]

    # 4. Attempt capture per fixture and per provider
    fetched_count = 0
    skipped_count = 0
    failed_count = 0
    provider_count = 5  # We have 5 providers
    mapping_candidates = []

    for fixture in fixtures:
        slug = fixture["fixture_slug"]
        
        # We attempt each provider: sportdb, football_data_org, highlightly, api_football, espn_baseline
        attempts = [
            ("sportdb", capture_sportdb, sportdb_cred),
            ("football-data-org", capture_football_data_org, fd_cred),
            ("highlightly", capture_highlightly, hl_cred),
            ("api-football", capture_api_football, af_cred),
            ("espn-baseline", capture_espn_baseline, None),
        ]
        
        for prov_name, capture_fn, cred in attempts:
            envelopes_or_single = capture_fn(fixture, cred)
            if isinstance(envelopes_or_single, list):
                envelopes = envelopes_or_single
            else:
                envelopes = [envelopes_or_single]
                
            for envelope in envelopes:
                envelope.validate()
                
                # Count statuses
                status = envelope.status
                if status in (CaptureStatus.FETCHED.value, CaptureStatus.DISCOVERY_FETCHED.value):
                    fetched_count += 1
                elif status in (
                    CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
                    CaptureStatus.SKIPPED_PROVIDER_NOT_CONFIGURED.value,
                    CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
                    CaptureStatus.BLOCKED_DISCOVERY_ENDPOINT_UNKNOWN.value,
                    CaptureStatus.DISCOVERY_NO_MATCH_FOUND.value,
                ):
                    skipped_count += 1
                else:
                    failed_count += 1
                    
                # Track mapping candidate if found
                if status == CaptureStatus.DISCOVERY_FETCHED.value and envelope.provider_fixture_id:
                    mapping_candidates.append({
                        "provider": envelope.provider,
                        "fixture_slug": slug,
                        "provider_fixture_id": envelope.provider_fixture_id,
                        "discovered_at_utc": envelope.captured_at_utc,
                    })
                    
                # Determine file path
                if envelope.request_purpose.endswith("discovery") or "discovery" in envelope.request_purpose:
                    rel_envelope_path = f"{prov_name}/{slug}_discovery.json"
                else:
                    rel_envelope_path = f"{prov_name}/{slug}.json"
                    
                write_json(run_dir / rel_envelope_path, envelope.to_dict())
                files_written.append(rel_envelope_path)

    # 5. Write mapping candidates
    write_json(run_dir / "mapping_candidate.json", mapping_candidates)
    files_written.append("mapping_candidate.json")

    # 6. Build and write manifest
    manifest = LiveCorpusManifest(
        run_id=run_id,
        run_started_at_utc=now_utc.isoformat() + "Z",
        target_date_utc=now_utc.strftime("%Y-%m-%d"),
        fixture_count=len(fixtures),
        provider_count=provider_count,
        fetched_count=fetched_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        credentials_present=cred_map,
        files_written=files_written,
        selectable_for_production=False,
    )
    manifest.validate()
    
    write_json(run_dir / "manifest.json", manifest.to_dict())
    files_written.append("manifest.json")

    # 7. Write README.md
    readme_path = run_dir / "README.md"
    readme_content = f"""# Live Response Corpus Run: {run_id}

Run ID: {run_id}
Started At: {now_utc.isoformat()}Z
Target Date: {now_utc.strftime('%Y-%m-%d')}
Discovered Fixtures: {len(fixtures)}
Providers Attempted: {provider_count}
Fetched: {fetched_count}
Skipped/Blocked: {skipped_count}
Failed: {failed_count}

This corpus was captured for football enrichment, isolating real external provider responses from downstream DB/betting decisions.
"""
    readme_path.write_text(readme_content, encoding="utf-8")
    files_written.append("README.md")
    
    # Update manifest with final list of files written
    manifest = LiveCorpusManifest(
        run_id=run_id,
        run_started_at_utc=manifest.run_started_at_utc,
        target_date_utc=manifest.target_date_utc,
        fixture_count=manifest.fixture_count,
        provider_count=manifest.provider_count,
        fetched_count=manifest.fetched_count,
        skipped_count=manifest.skipped_count,
        failed_count=manifest.failed_count,
        credentials_present=manifest.credentials_present,
        files_written=files_written,
        selectable_for_production=False,
    )
    # Write the updated manifest
    write_json(run_dir / "manifest.json", manifest.to_dict())
    
    return manifest
