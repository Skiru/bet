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
from bet.enrichment.football_data_foundation.live_response_corpus_capture.http_capture import (
    safe_http_get,
    safe_http_post,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.sanitizer import (
    write_json,
    sanitize_json_body,
    compute_body_sha256,
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


def run_freemium_rescue_capture(corpus_root: Path) -> LiveCorpusManifest:
    """
    Execute the freemium rescue capture for SportDB, Highlightly, and ESPN.
    This is PASS A.2, isolating external live response rescue from DB mutations or production decisions.
    """
    import json
    import uuid
    from bet.enrichment.football_data_foundation.live_response_corpus_capture.verifier import verify_run_directory

    now_utc = datetime.datetime.utcnow()
    run_id = f"run_{now_utc.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    run_dir = corpus_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    project_root = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1")
    load_project_dotenv(project_root)
    cred_map = credential_presence_map()

    sportdb_cred = get_credential("SPORTDB_API_KEY")
    hl_cred = get_credential("HIGHLIGHTLY_API_KEY")

    files_written = []
    fetched_count = 0
    skipped_count = 0
    failed_count = 0
    mapping_candidates = []

    # Target info
    target_slug = "worldcup2026-norway-senegal"
    now_str = now_utc.isoformat() + "Z"

    # --- 1. SportDB Rescue ---
    sportdb_status = "SKIPPED_CREDENTIALS_MISSING"
    sportdb_envelope = None

    if not sportdb_cred:
        sportdb_envelope = ProviderResponseEnvelope(
            provider="sportdb",
            status="SKIPPED_CREDENTIALS_MISSING",
            fixture_slug=target_slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="sportdb_rest_football_live_probe",
            request_attempted=False,
            network_used=False,
            rescue_attempt=True,
            rescue_provider="sportdb",
            rescue_endpoint_family="football_live",
            selectable_for_production=False,
        )
        skipped_count += 1
    else:
        # Call GET https://api.sportdb.dev/api/football/live
        url = "https://api.sportdb.dev/api/football/live"
        headers = {
            "X-API-Key": sportdb_cred,
            "Accept": "application/json",
        }
        status_code, resp_body, err = safe_http_get(url, headers=headers, timeout=15.0)

        if err:
            sportdb_status = "RESCUE_FAILED_HTTP"
            sportdb_envelope = ProviderResponseEnvelope(
                provider="sportdb",
                status="RESCUE_FAILED_HTTP",
                fixture_slug=target_slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="sportdb_rest_football_live_probe",
                request_attempted=True,
                network_used=True,
                status_code=status_code,
                error=err,
                rescue_attempt=True,
                rescue_provider="sportdb",
                rescue_endpoint_family="football_live",
                selectable_for_production=False,
            )
            failed_count += 1
        elif status_code == 200:
            try:
                sanitized = sanitize_json_body(resp_body)
                sha = compute_body_sha256(sanitized)
                
                # Check for Norway vs Senegal in the live matches
                matches = []
                if isinstance(sanitized, list):
                    matches = sanitized
                elif isinstance(sanitized, dict):
                    matches = sanitized.get("matches") or sanitized.get("games") or sanitized.get("data") or []
                
                sportdb_match_id = None
                if isinstance(matches, list):
                    for m in matches:
                        if not isinstance(m, dict):
                            continue
                        h_team = str(m.get("home_team") or m.get("homeTeam") or m.get("home") or "").lower()
                        a_team = str(m.get("away_team") or m.get("awayTeam") or m.get("away") or "").lower()
                        if ("norway" in h_team and "senegal" in a_team) or ("senegal" in h_team and "norway" in a_team):
                            sportdb_match_id = str(m.get("id") or m.get("match_id") or m.get("matchId") or "")
                            break

                if sportdb_match_id:
                    sportdb_status = "RESCUE_FETCHED"
                    mapping_candidates.append({
                        "provider": "sportdb",
                        "fixture_slug": target_slug,
                        "provider_fixture_id": sportdb_match_id,
                        "discovered_at_utc": now_str,
                        "rescue_attempt": True,
                    })
                    
                    # Call at most one detail endpoint
                    detail_url = f"https://api.sportdb.dev/api/match/{sportdb_match_id}"
                    det_status_code, det_body, det_err = safe_http_get(detail_url, headers=headers, timeout=15.0)
                    if det_status_code == 200 and not det_err:
                        try:
                            det_sanitized = sanitize_json_body(det_body)
                            det_sha = compute_body_sha256(det_sanitized)
                            det_rel_path = f"sportdb/{target_slug}_rescue_detail.json"
                            det_envelope = ProviderResponseEnvelope(
                                provider="sportdb",
                                status="RESCUE_FETCHED",
                                fixture_slug=target_slug,
                                source_url=detail_url,
                                captured_at_utc=now_str,
                                request_purpose="sportdb_rest_match_detail_by_provider_id",
                                request_attempted=True,
                                network_used=True,
                                status_code=det_status_code,
                                body=det_sanitized,
                                body_sha256=det_sha,
                                provider_fixture_id=sportdb_match_id,
                                provider_mapping_status="MAPPED",
                                rescue_attempt=True,
                                rescue_provider="sportdb",
                                rescue_endpoint_family="match_detail",
                                selectable_for_production=False,
                            )
                            det_envelope.validate()
                            write_json(run_dir / det_rel_path, det_envelope.to_dict())
                            files_written.append(det_rel_path)
                            fetched_count += 1
                        except Exception:
                            pass
                else:
                    sportdb_status = "RESCUE_NO_MATCH_FOUND"

                sportdb_envelope = ProviderResponseEnvelope(
                    provider="sportdb",
                    status=sportdb_status,
                    fixture_slug=target_slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="sportdb_rest_football_live_probe",
                    request_attempted=True,
                    network_used=True,
                    status_code=status_code,
                    body=sanitized,
                    body_sha256=sha,
                    rescue_attempt=True,
                    rescue_provider="sportdb",
                    rescue_endpoint_family="football_live",
                    selectable_for_production=False,
                )
                if sportdb_status == "RESCUE_FETCHED":
                    fetched_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                sportdb_status = "RESCUE_FAILED_PARSE"
                sportdb_envelope = ProviderResponseEnvelope(
                    provider="sportdb",
                    status="RESCUE_FAILED_PARSE",
                    fixture_slug=target_slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="sportdb_rest_football_live_probe",
                    request_attempted=True,
                    network_used=True,
                    status_code=status_code,
                    error=f"SportDB parse error: {str(e)}",
                    rescue_attempt=True,
                    rescue_provider="sportdb",
                    rescue_endpoint_family="football_live",
                    selectable_for_production=False,
                )
                failed_count += 1
        else:
            sportdb_status = "RESCUE_FAILED_HTTP"
            sportdb_envelope = ProviderResponseEnvelope(
                provider="sportdb",
                status="RESCUE_FAILED_HTTP",
                fixture_slug=target_slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="sportdb_rest_football_live_probe",
                request_attempted=True,
                network_used=True,
                status_code=status_code,
                error=f"HTTP non-200: {status_code}",
                rescue_attempt=True,
                rescue_provider="sportdb",
                rescue_endpoint_family="football_live",
                selectable_for_production=False,
            )
            failed_count += 1

    if sportdb_envelope:
        sportdb_envelope.validate()
        sportdb_rel_path = f"sportdb/{target_slug}_rescue_live.json"
        write_json(run_dir / sportdb_rel_path, sportdb_envelope.to_dict())
        files_written.append(sportdb_rel_path)

    # --- 2. Highlightly Rescue ---
    hl_envelope = None
    if not hl_cred:
        hl_envelope = ProviderResponseEnvelope(
            provider="highlightly",
            status="SKIPPED_CREDENTIALS_MISSING",
            fixture_slug=target_slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="highlightly_rescue_probe",
            request_attempted=False,
            network_used=False,
            rescue_attempt=True,
            rescue_provider="highlightly",
            rescue_endpoint_family=None,
            selectable_for_production=False,
        )
        skipped_count += 1
    else:
        hl_envelope = ProviderResponseEnvelope(
            provider="highlightly",
            status="RESCUE_BLOCKED_ENDPOINT_UNAVAILABLE",
            fixture_slug=target_slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="highlightly_rescue_probe",
            request_attempted=True,
            network_used=False,
            error="highlightly_base_url_or_auth_header_not_available_in_repo_or_docs",
            rescue_attempt=True,
            rescue_provider="highlightly",
            rescue_endpoint_family=None,
            selectable_for_production=False,
        )
        skipped_count += 1

    if hl_envelope:
        hl_envelope.validate()
        hl_rel_path = f"highlightly/{target_slug}_rescue.json"
        write_json(run_dir / hl_rel_path, hl_envelope.to_dict())
        files_written.append(hl_rel_path)

    # --- 3. ESPN Baseline Rescue ---
    espn_envelope = None
    espn_status = "RESCUE_FAILED_HTTP"
    espn_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?limit=950&dates=20260622-20260623"
    
    espn_status_code, espn_body, espn_err = safe_http_get(espn_url, timeout=15.0)

    if espn_err:
        espn_envelope = ProviderResponseEnvelope(
            provider="espn-baseline",
            status="RESCUE_FAILED_HTTP",
            fixture_slug=target_slug,
            source_url=espn_url,
            captured_at_utc=now_str,
            request_purpose="espn_fifa_world_scoreboard_rescue",
            request_attempted=True,
            network_used=True,
            status_code=espn_status_code,
            error=espn_err,
            rescue_attempt=True,
            rescue_provider="espn-baseline",
            rescue_endpoint_family="scoreboard",
            selectable_for_production=False,
            unofficial_shadow_baseline=True,
        )
        failed_count += 1
    elif espn_status_code == 200:
        try:
            espn_sanitized = sanitize_json_body(espn_body)
            espn_sha = compute_body_sha256(espn_sanitized)
            
            espn_event_id = None
            events = []
            if isinstance(espn_sanitized, dict):
                events = espn_sanitized.get("events") or []
            
            if isinstance(events, list):
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    comps = ev.get("competitions") or []
                    for comp in comps:
                        if not isinstance(comp, dict):
                            continue
                        competitors = comp.get("competitors") or []
                        has_norway = False
                        has_senegal = False
                        for competitor in competitors:
                            if not isinstance(competitor, dict):
                                continue
                            team = competitor.get("team") or {}
                            name = str(team.get("name") or "").lower()
                            abbrev = str(team.get("abbreviation") or "").lower()
                            displayName = str(team.get("displayName") or "").lower()
                            
                            if "norway" in name or "nor" in abbrev or "norway" in displayName:
                                has_norway = True
                            if "senegal" in name or "sen" in abbrev or "senegal" in displayName:
                                has_senegal = True
                        
                        if has_norway and has_senegal:
                            espn_event_id = str(ev.get("id") or "")
                            break
                    if espn_event_id:
                        break

            if espn_event_id:
                espn_status = "RESCUE_FETCHED"
                mapping_candidates.append({
                    "provider": "espn-baseline",
                    "fixture_slug": target_slug,
                    "provider_fixture_id": espn_event_id,
                    "discovered_at_utc": now_str,
                    "rescue_attempt": True,
                })
                
                # Fetch summary endpoint
                summary_url = f"http://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={espn_event_id}"
                sum_status_code, sum_body, sum_err = safe_http_get(summary_url, timeout=15.0)
                if sum_status_code == 200 and not sum_err:
                    try:
                        sum_sanitized = sanitize_json_body(sum_body)
                        sum_sha = compute_body_sha256(sum_sanitized)
                        sum_rel_path = f"espn-baseline/{target_slug}_rescue_summary.json"
                        sum_envelope = ProviderResponseEnvelope(
                            provider="espn-baseline",
                            status="RESCUE_FETCHED",
                            fixture_slug=target_slug,
                            source_url=summary_url,
                            captured_at_utc=now_str,
                            request_purpose="espn_soccer_summary_rescue",
                            request_attempted=True,
                            network_used=True,
                            status_code=sum_status_code,
                            body=sum_sanitized,
                            body_sha256=sum_sha,
                            provider_fixture_id=espn_event_id,
                            provider_mapping_status="MAPPED",
                            rescue_attempt=True,
                            rescue_provider="espn-baseline",
                            rescue_endpoint_family="summary",
                            selectable_for_production=False,
                            unofficial_shadow_baseline=True,
                        )
                        sum_envelope.validate()
                        write_json(run_dir / sum_rel_path, sum_envelope.to_dict())
                        files_written.append(sum_rel_path)
                        fetched_count += 1
                    except Exception:
                        pass
            else:
                espn_status = "RESCUE_NO_MATCH_FOUND"

            espn_envelope = ProviderResponseEnvelope(
                provider="espn-baseline",
                status=espn_status,
                fixture_slug=target_slug,
                source_url=espn_url,
                captured_at_utc=now_str,
                request_purpose="espn_fifa_world_scoreboard_rescue",
                request_attempted=True,
                network_used=True,
                status_code=espn_status_code,
                body=espn_sanitized,
                body_sha256=espn_sha,
                rescue_attempt=True,
                rescue_provider="espn-baseline",
                rescue_endpoint_family="scoreboard",
                selectable_for_production=False,
                unofficial_shadow_baseline=True,
            )
            if espn_status == "RESCUE_FETCHED":
                fetched_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            espn_envelope = ProviderResponseEnvelope(
                provider="espn-baseline",
                status="RESCUE_FAILED_PARSE",
                fixture_slug=target_slug,
                source_url=espn_url,
                captured_at_utc=now_str,
                request_purpose="espn_fifa_world_scoreboard_rescue",
                request_attempted=True,
                network_used=True,
                status_code=espn_status_code,
                error=f"ESPN parse error: {str(e)}",
                rescue_attempt=True,
                rescue_provider="espn-baseline",
                rescue_endpoint_family="scoreboard",
                selectable_for_production=False,
                unofficial_shadow_baseline=True,
            )
            failed_count += 1
    else:
        espn_envelope = ProviderResponseEnvelope(
            provider="espn-baseline",
            status="RESCUE_FAILED_HTTP",
            fixture_slug=target_slug,
            source_url=espn_url,
            captured_at_utc=now_str,
            request_purpose="espn_fifa_world_scoreboard_rescue",
            request_attempted=True,
            network_used=True,
            status_code=espn_status_code,
            error=f"HTTP non-200: {espn_status_code}",
            rescue_attempt=True,
            rescue_provider="espn-baseline",
            rescue_endpoint_family="scoreboard",
            selectable_for_production=False,
            unofficial_shadow_baseline=True,
        )
        failed_count += 1

    if espn_envelope:
        espn_envelope.validate()
        espn_rel_path = f"espn-baseline/{target_slug}_rescue_scoreboard.json"
        write_json(run_dir / espn_rel_path, espn_envelope.to_dict())
        files_written.append(espn_rel_path)

    # --- 4. Write Mapping Candidates ---
    write_json(run_dir / "mapping_candidate.json", mapping_candidates)
    files_written.append("mapping_candidate.json")

    # --- 5. Manifest ---
    manifest = LiveCorpusManifest(
        run_id=run_id,
        run_started_at_utc=now_str,
        target_date_utc="2026-06-23",
        fixture_count=1,
        provider_count=3,
        fetched_count=fetched_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        credentials_present=cred_map,
        files_written=[],
        selectable_for_production=False,
    )
    manifest_dict = manifest.to_dict()
    manifest_dict["previous_referenced_run_id"] = "run_20260623_100018_fe9167"
    manifest_dict["rescue_run"] = True

    write_json(run_dir / "manifest.json", manifest_dict)
    files_written.append("manifest.json")

    # --- 6. README.md ---
    readme_path = run_dir / "README.md"
    readme_content = f"""# Live Response Corpus Rescue Run: {run_id}

This run is a dedicated freemium/shadow integration rescue capture (PASS A.2).
Target Fixture: {target_slug} (Norway vs Senegal, 2026-06-23)

Previous run referenced: `run_20260623_100018_fe9167`. This run does not modify it.

This is a rescue capture phase only, isolating external live response rescue from DB mutations or final enrichment.

Fetched: {fetched_count}
Skipped/Blocked: {skipped_count}
Failed: {failed_count}
"""
    readme_path.write_text(readme_content, encoding="utf-8")
    files_written.append("README.md")

    # Update manifest file list
    manifest_dict["files_written"] = sorted(files_written)
    write_json(run_dir / "manifest.json", manifest_dict)

    # --- 7. Run Verifier and Write verifier result JSON ---
    verifier_result = verify_run_directory(run_dir)
    write_json(run_dir / "capture_verifier_result.json", verifier_result)

    return manifest
