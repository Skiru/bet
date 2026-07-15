import datetime
from typing import Any, Dict, Union, List
from bet.enrichment.football_data_foundation.live_response_corpus_capture.contracts import (
    ProviderResponseEnvelope,
    CaptureStatus,
    Provider,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.http_capture import safe_http_get, safe_http_post
from bet.enrichment.football_data_foundation.live_response_corpus_capture.sanitizer import (
    sanitize_json_body,
    compute_body_sha256,
)

# Registry for mapped provider fixture IDs. Keep it strictly non-fake.
PROVIDER_FIXTURE_MAPPINGS: Dict[str, Dict[str, Union[str, None]]] = {
    "worldcup2026-norway-senegal": {
        "sportdb": None,
        "football-data-org": None,
        "highlightly": None,
        "api-football": None,
        "espn-baseline": None,
    }
}


def get_mapped_id(fixture_slug: str, provider_key: str) -> str | None:
    """
    Retrieve mapped provider fixture ID for a given slug and provider.
    """
    return PROVIDER_FIXTURE_MAPPINGS.get(fixture_slug, {}).get(provider_key)


def find_matching_football_data_org_id(data: Any, home_team: str, away_team: str) -> str | None:
    if not isinstance(data, dict):
        return None
    matches = data.get("matches")
    if not isinstance(matches, list):
        return None
    
    h_clean = home_team.lower().strip()
    a_clean = away_team.lower().strip()
    
    for m in matches:
        if not isinstance(m, dict):
            continue
        h_info = m.get("homeTeam") or {}
        a_info = m.get("awayTeam") or {}
        h_name = str(h_info.get("name") or "").lower()
        a_name = str(a_info.get("name") or "").lower()
        
        if (h_clean in h_name or h_name in h_clean) and (a_clean in a_name or a_name in a_clean):
            m_id = m.get("id")
            if m_id is not None:
                return str(m_id)
    return None


def find_matching_api_football_id(data: Any, home_team: str, away_team: str) -> str | None:
    if not isinstance(data, dict):
        return None
    response_list = data.get("response")
    if not isinstance(response_list, list):
        return None
        
    h_clean = home_team.lower().strip()
    a_clean = away_team.lower().strip()
    
    for item in response_list:
        if not isinstance(item, dict):
            continue
        teams = item.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        h_name = str(home.get("name") or "").lower()
        a_name = str(away.get("name") or "").lower()
        
        if (h_clean in h_name or h_name in h_clean) and (a_clean in a_name or a_name in a_clean):
            fixture_info = item.get("fixture") or {}
            f_id = fixture_info.get("id")
            if f_id is not None:
                return str(f_id)
    return None


def capture_sportdb(fixture: Dict[str, Any], credential_value: str | None) -> List[ProviderResponseEnvelope]:
    slug = fixture["fixture_slug"]
    now_str = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    
    if not credential_value:
        return [ProviderResponseEnvelope(
            provider=Provider.SPORTDB.value,
            status=CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="mcp_live_or_match_search_discovery",
            request_attempted=False,
            network_used=False,
        )]
        
    mapped_id = get_mapped_id(slug, "sportdb")
    if not mapped_id:
        disc_env = ProviderResponseEnvelope(
            provider=Provider.SPORTDB.value,
            status=CaptureStatus.BLOCKED_DISCOVERY_ENDPOINT_UNKNOWN.value,
            fixture_slug=slug,
            source_url="https://api.sportdb.dev/mcp/",
            captured_at_utc=now_str,
            request_purpose="mcp_live_or_match_search_discovery",
            request_attempted=False,
            network_used=False,
            error="SportDB MCP JSON-RPC tool name for discovery is unknown",
        )
        det_env = ProviderResponseEnvelope(
            provider=Provider.SPORTDB.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            request_attempted=False,
            network_used=False,
        )
        return [disc_env, det_env]
        
    url = "https://api.sportdb.dev/mcp/"
    try:
        headers = {
            "X-API-Key": credential_value,
            "Accept": "application/json",
        }
        body = {
            "jsonrpc": "2.0",
            "id": "capture-1",
            "method": "call_tool",
            "params": {"name": "get_match_by_id", "arguments": {"match_id": mapped_id}},
        }
        status_code, resp_body, err = safe_http_post(url, headers=headers, json_data=body, timeout=10.0)
        
        if err:
            return [ProviderResponseEnvelope(
                provider=Provider.SPORTDB.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                status_code=status_code,
                error=err,
            )]
            
        if status_code == 200:
            try:
                sanitized = sanitize_json_body(resp_body)
                sha = compute_body_sha256(sanitized)
                return [ProviderResponseEnvelope(
                    provider=Provider.SPORTDB.value,
                    status=CaptureStatus.FETCHED.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="fixture_detail",
                    status_code=status_code,
                    body=sanitized,
                    body_sha256=sha,
                    provider_fixture_id=mapped_id,
                    provider_mapping_status="MAPPED",
                )]
            except Exception as e:
                return [ProviderResponseEnvelope(
                    provider=Provider.SPORTDB.value,
                    status=CaptureStatus.FAILED_PARSE.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="fixture_detail",
                    status_code=status_code,
                    error=f"JSON parse error: {str(e)}",
                )]
        else:
            return [ProviderResponseEnvelope(
                provider=Provider.SPORTDB.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                status_code=status_code,
                error=f"HTTP error {status_code}",
            )]
    except Exception as e:
        return [ProviderResponseEnvelope(
            provider=Provider.SPORTDB.value,
            status=CaptureStatus.FAILED_PROVIDER_ERROR.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            error=f"Provider exception: {str(e)}",
        )]


def capture_football_data_org(fixture: Dict[str, Any], credential_value: str | None) -> List[ProviderResponseEnvelope]:
    slug = fixture["fixture_slug"]
    now_str = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    
    if not credential_value:
        return [ProviderResponseEnvelope(
            provider=Provider.FOOTBALL_DATA_ORG.value,
            status=CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="date_range_match_discovery",
            request_attempted=False,
            network_used=False,
        )]
        
    mapped_id = get_mapped_id(slug, "football-data-org")
    discovery_env = None
    
    if not mapped_id:
        kickoff = fixture.get("kickoff_at") or ""
        date = kickoff[:10] if kickoff else "2026-06-23"
        url = f"https://api.football-data.org/v4/matches?dateFrom={date}&dateTo={date}"
        headers = {"X-Auth-Token": credential_value, "Accept": "application/json"}
        
        status_code, body, err = safe_http_get(url, headers=headers, timeout=10.0)
        
        if err:
            discovery_env = ProviderResponseEnvelope(
                provider=Provider.FOOTBALL_DATA_ORG.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="date_range_match_discovery",
                status_code=status_code,
                error=err,
            )
        elif status_code == 200:
            try:
                sanitized = sanitize_json_body(body)
                sha = compute_body_sha256(sanitized)
                discovered_id = find_matching_football_data_org_id(sanitized, fixture.get("home_team", ""), fixture.get("away_team", ""))
                
                if discovered_id:
                    mapped_id = discovered_id
                    discovery_env = ProviderResponseEnvelope(
                        provider=Provider.FOOTBALL_DATA_ORG.value,
                        status=CaptureStatus.DISCOVERY_FETCHED.value,
                        fixture_slug=slug,
                        source_url=url,
                        captured_at_utc=now_str,
                        request_purpose="date_range_match_discovery",
                        status_code=status_code,
                        body=sanitized,
                        body_sha256=sha,
                        provider_fixture_id=discovered_id,
                        provider_mapping_status="MAPPED",
                    )
                else:
                    discovery_env = ProviderResponseEnvelope(
                        provider=Provider.FOOTBALL_DATA_ORG.value,
                        status=CaptureStatus.DISCOVERY_NO_MATCH_FOUND.value,
                        fixture_slug=slug,
                        source_url=url,
                        captured_at_utc=now_str,
                        request_purpose="date_range_match_discovery",
                        status_code=status_code,
                        body=sanitized,
                        body_sha256=sha,
                        provider_mapping_status="MISSING",
                    )
            except Exception as e:
                discovery_env = ProviderResponseEnvelope(
                    provider=Provider.FOOTBALL_DATA_ORG.value,
                    status=CaptureStatus.FAILED_PARSE.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="date_range_match_discovery",
                    status_code=status_code,
                    error=f"Sanitization/parse exception: {str(e)}",
                )
        else:
            discovery_env = ProviderResponseEnvelope(
                provider=Provider.FOOTBALL_DATA_ORG.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="date_range_match_discovery",
                status_code=status_code,
                error=f"HTTP non-200: {status_code}",
            )
            
    if mapped_id:
        url = f"https://api.football-data.org/v4/matches/{mapped_id}"
        headers = {"X-Auth-Token": credential_value, "Accept": "application/json"}
        status_code, body, err = safe_http_get(url, headers=headers, timeout=10.0)
        
        if err:
            det_env = ProviderResponseEnvelope(
                provider=Provider.FOOTBALL_DATA_ORG.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                error=err,
                provider_fixture_id=mapped_id,
                provider_mapping_status="MAPPED",
            )
        elif status_code == 200:
            try:
                sanitized = sanitize_json_body(body)
                sha = compute_body_sha256(sanitized)
                det_env = ProviderResponseEnvelope(
                    provider=Provider.FOOTBALL_DATA_ORG.value,
                    status=CaptureStatus.FETCHED.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="fixture_detail",
                    status_code=status_code,
                    body=sanitized,
                    body_sha256=sha,
                    provider_fixture_id=mapped_id,
                    provider_mapping_status="MAPPED",
                )
            except Exception as e:
                det_env = ProviderResponseEnvelope(
                    provider=Provider.FOOTBALL_DATA_ORG.value,
                    status=CaptureStatus.FAILED_PARSE.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="fixture_detail",
                    status_code=status_code,
                    error=f"Sanitization/parse exception: {str(e)}",
                    provider_fixture_id=mapped_id,
                    provider_mapping_status="MAPPED",
                )
        else:
            det_env = ProviderResponseEnvelope(
                provider=Provider.FOOTBALL_DATA_ORG.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                status_code=status_code,
                error=f"HTTP non-200: {status_code}",
                provider_fixture_id=mapped_id,
                provider_mapping_status="MAPPED",
            )
    else:
        det_env = ProviderResponseEnvelope(
            provider=Provider.FOOTBALL_DATA_ORG.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            request_attempted=False,
            network_used=False,
        )
        
    return [discovery_env, det_env] if discovery_env else [det_env]


def capture_highlightly(fixture: Dict[str, Any], credential_value: str | None) -> List[ProviderResponseEnvelope]:
    slug = fixture["fixture_slug"]
    now_str = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    
    if not credential_value:
        return [ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="bounded_match_search_discovery",
            request_attempted=False,
            network_used=False,
        )]
        
    mapped_id = get_mapped_id(slug, "highlightly")
    if not mapped_id:
        disc_env = ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.BLOCKED_DISCOVERY_ENDPOINT_UNKNOWN.value,
            fixture_slug=slug,
            source_url="https://soccer.highlightly.net/matches",
            captured_at_utc=now_str,
            request_purpose="bounded_match_search_discovery",
            request_attempted=False,
            network_used=False,
            error="Highlightly endpoint not known with confidence",
        )
        det_env = ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            request_attempted=False,
            network_used=False,
        )
        return [disc_env, det_env]
        
    url = f"https://soccer.highlightly.net/matches/{mapped_id}"
    headers = {"x-rapidapi-key": credential_value, "Accept": "application/json"}
    status_code, body, err = safe_http_get(url, headers=headers, timeout=10.0)
    
    if err:
        return [ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            error=err,
            provider_fixture_id=mapped_id,
            provider_mapping_status="MAPPED",
        )]
        
    if status_code == 200:
        try:
            sanitized = sanitize_json_body(body)
            sha = compute_body_sha256(sanitized)
            return [ProviderResponseEnvelope(
                provider=Provider.HIGHLIGHTLY.value,
                status=CaptureStatus.FETCHED.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                status_code=status_code,
                body=sanitized,
                body_sha256=sha,
                provider_fixture_id=mapped_id,
                provider_mapping_status="MAPPED",
            )]
        except Exception as e:
            return [ProviderResponseEnvelope(
                provider=Provider.HIGHLIGHTLY.value,
                status=CaptureStatus.FAILED_PARSE.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                status_code=status_code,
                error=f"Sanitization exception: {str(e)}",
                provider_fixture_id=mapped_id,
                provider_mapping_status="MAPPED",
            )]
    else:
        return [ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            status_code=status_code,
            error=f"HTTP non-200: {status_code}",
            provider_fixture_id=mapped_id,
            provider_mapping_status="MAPPED",
        )]


def capture_api_football(fixture: Dict[str, Any], credential_value: str | None) -> List[ProviderResponseEnvelope]:
    slug = fixture["fixture_slug"]
    now_str = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    
    if not credential_value:
        return [ProviderResponseEnvelope(
            provider=Provider.API_FOOTBALL.value,
            status=CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="date_fixture_discovery",
            request_attempted=False,
            network_used=False,
        )]
        
    mapped_id = get_mapped_id(slug, "api-football")
    discovery_env = None
    
    if not mapped_id:
        kickoff = fixture.get("kickoff_at") or ""
        date = kickoff[:10] if kickoff else "2026-06-23"
        url = f"https://v3.football.api-sports.io/fixtures?date={date}"
        headers = {"x-apisports-key": credential_value, "Accept": "application/json"}
        
        status_code, body, err = safe_http_get(url, headers=headers, timeout=10.0)
        
        if err:
            discovery_env = ProviderResponseEnvelope(
                provider=Provider.API_FOOTBALL.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="date_fixture_discovery",
                status_code=status_code,
                error=err,
            )
        elif status_code == 200:
            try:
                sanitized = sanitize_json_body(body)
                sha = compute_body_sha256(sanitized)
                discovered_id = find_matching_api_football_id(sanitized, fixture.get("home_team", ""), fixture.get("away_team", ""))
                
                if discovered_id:
                    mapped_id = discovered_id
                    discovery_env = ProviderResponseEnvelope(
                        provider=Provider.API_FOOTBALL.value,
                        status=CaptureStatus.DISCOVERY_FETCHED.value,
                        fixture_slug=slug,
                        source_url=url,
                        captured_at_utc=now_str,
                        request_purpose="date_fixture_discovery",
                        status_code=status_code,
                        body=sanitized,
                        body_sha256=sha,
                        provider_fixture_id=discovered_id,
                        provider_mapping_status="MAPPED",
                    )
                else:
                    discovery_env = ProviderResponseEnvelope(
                        provider=Provider.API_FOOTBALL.value,
                        status=CaptureStatus.DISCOVERY_NO_MATCH_FOUND.value,
                        fixture_slug=slug,
                        source_url=url,
                        captured_at_utc=now_str,
                        request_purpose="date_fixture_discovery",
                        status_code=status_code,
                        body=sanitized,
                        body_sha256=sha,
                        provider_mapping_status="MISSING",
                    )
            except Exception as e:
                discovery_env = ProviderResponseEnvelope(
                    provider=Provider.API_FOOTBALL.value,
                    status=CaptureStatus.FAILED_PARSE.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="date_fixture_discovery",
                    status_code=status_code,
                    error=f"Sanitization exception: {str(e)}",
                )
        else:
            discovery_env = ProviderResponseEnvelope(
                provider=Provider.API_FOOTBALL.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="date_fixture_discovery",
                status_code=status_code,
                error=f"HTTP non-200: {status_code}",
            )
            
    if mapped_id:
        url = f"https://v3.football.api-sports.io/fixtures?id={mapped_id}"
        headers = {"x-apisports-key": credential_value, "Accept": "application/json"}
        status_code, body, err = safe_http_get(url, headers=headers, timeout=10.0)
        
        if err:
            det_env = ProviderResponseEnvelope(
                provider=Provider.API_FOOTBALL.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                error=err,
                provider_fixture_id=mapped_id,
                provider_mapping_status="MAPPED",
            )
        elif status_code == 200:
            try:
                sanitized = sanitize_json_body(body)
                sha = compute_body_sha256(sanitized)
                det_env = ProviderResponseEnvelope(
                    provider=Provider.API_FOOTBALL.value,
                    status=CaptureStatus.FETCHED.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="fixture_detail",
                    status_code=status_code,
                    body=sanitized,
                    body_sha256=sha,
                    provider_fixture_id=mapped_id,
                    provider_mapping_status="MAPPED",
                )
            except Exception as e:
                det_env = ProviderResponseEnvelope(
                    provider=Provider.API_FOOTBALL.value,
                    status=CaptureStatus.FAILED_PARSE.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=now_str,
                    request_purpose="fixture_detail",
                    status_code=status_code,
                    error=f"Sanitization exception: {str(e)}",
                    provider_fixture_id=mapped_id,
                    provider_mapping_status="MAPPED",
                )
        else:
            det_env = ProviderResponseEnvelope(
                provider=Provider.API_FOOTBALL.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                status_code=status_code,
                error=f"HTTP non-200: {status_code}",
                provider_fixture_id=mapped_id,
                provider_mapping_status="MAPPED",
            )
    else:
        det_env = ProviderResponseEnvelope(
            provider=Provider.API_FOOTBALL.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            request_attempted=False,
            network_used=False,
        )
        
    return [discovery_env, det_env] if discovery_env else [det_env]


def capture_espn_baseline(fixture: Dict[str, Any], credential_value: str | None = None) -> List[ProviderResponseEnvelope]:
    slug = fixture["fixture_slug"]
    now_str = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    
    mapped_id = get_mapped_id(slug, "espn-baseline")
    
    if not mapped_id:
        disc_env = ProviderResponseEnvelope(
            provider=Provider.ESPN_BASELINE.value,
            status=CaptureStatus.SKIPPED_PROVIDER_NOT_CONFIGURED.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="espn_discovery",
            request_attempted=False,
            network_used=False,
        )
        det_env = ProviderResponseEnvelope(
            provider=Provider.ESPN_BASELINE.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            request_attempted=False,
            network_used=False,
        )
        return [disc_env, det_env]
        
    url = f"http://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={mapped_id}"
    status_code, body, err = safe_http_get(url, timeout=10.0)
    
    if err:
        return [ProviderResponseEnvelope(
            provider=Provider.ESPN_BASELINE.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            error=err,
            provider_fixture_id=mapped_id,
            provider_mapping_status="MAPPED",
        )]
        
    if status_code == 200:
        try:
            sanitized = sanitize_json_body(body)
            sha = compute_body_sha256(sanitized)
            return [ProviderResponseEnvelope(
                provider=Provider.ESPN_BASELINE.value,
                status=CaptureStatus.FETCHED.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                status_code=status_code,
                body=sanitized,
                body_sha256=sha,
                provider_fixture_id=mapped_id,
                provider_mapping_status="MAPPED",
            )]
        except Exception as e:
            return [ProviderResponseEnvelope(
                provider=Provider.ESPN_BASELINE.value,
                status=CaptureStatus.FAILED_PARSE.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=now_str,
                request_purpose="fixture_detail",
                status_code=status_code,
                error=f"Sanitization exception: {str(e)}",
                provider_fixture_id=mapped_id,
                provider_mapping_status="MAPPED",
            )]
    else:
        return [ProviderResponseEnvelope(
            provider=Provider.ESPN_BASELINE.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=now_str,
            request_purpose="fixture_detail",
            status_code=status_code,
            error=f"HTTP non-200: {status_code}",
            provider_fixture_id=mapped_id,
            provider_mapping_status="MAPPED",
        )]
