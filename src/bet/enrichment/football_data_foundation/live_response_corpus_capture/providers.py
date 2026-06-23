import datetime
import requests
from typing import Any, Dict, Union
from bet.enrichment.football_data_foundation.live_response_corpus_capture.contracts import (
    ProviderResponseEnvelope,
    CaptureStatus,
    Provider,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.http_capture import safe_http_get
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


def capture_sportdb(fixture: Dict[str, Any], credential_value: str | None) -> ProviderResponseEnvelope:
    slug = fixture["fixture_slug"]
    if not credential_value:
        return ProviderResponseEnvelope(
            provider=Provider.SPORTDB.value,
            status=CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
    mapped_id = get_mapped_id(slug, "sportdb")
    if not mapped_id:
        return ProviderResponseEnvelope(
            provider=Provider.SPORTDB.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
    
    url = "https://api.sportdb.dev/mcp/"
    try:
        headers = {
            "X-API-Key": credential_value,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "jsonrpc": "2.0",
            "id": "capture-1",
            "method": "call_tool",
            "params": {"name": "get_match_by_id", "arguments": {"match_id": mapped_id}},
        }
        response = requests.post(url, json=body, headers=headers, timeout=10.0)
        status_code = response.status_code
        if status_code == 200:
            try:
                resp_body = response.json()
                sanitized = sanitize_json_body(resp_body)
                sha = compute_body_sha256(sanitized)
                return ProviderResponseEnvelope(
                    provider=Provider.SPORTDB.value,
                    status=CaptureStatus.FETCHED.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                    status_code=status_code,
                    body=sanitized,
                    body_sha256=sha,
                )
            except Exception as e:
                return ProviderResponseEnvelope(
                    provider=Provider.SPORTDB.value,
                    status=CaptureStatus.FAILED_PARSE.value,
                    fixture_slug=slug,
                    source_url=url,
                    captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                    status_code=status_code,
                    error=f"JSON parse error: {str(e)}",
                )
        else:
            return ProviderResponseEnvelope(
                provider=Provider.SPORTDB.value,
                status=CaptureStatus.FAILED_HTTP.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                error=f"HTTP error {status_code}",
            )
    except Exception as e:
        return ProviderResponseEnvelope(
            provider=Provider.SPORTDB.value,
            status=CaptureStatus.FAILED_PROVIDER_ERROR.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            error=f"Provider exception: {str(e)}",
        )


def capture_football_data_org(fixture: Dict[str, Any], credential_value: str | None) -> ProviderResponseEnvelope:
    slug = fixture["fixture_slug"]
    if not credential_value:
        return ProviderResponseEnvelope(
            provider=Provider.FOOTBALL_DATA_ORG.value,
            status=CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
    mapped_id = get_mapped_id(slug, "football-data-org")
    if not mapped_id:
        return ProviderResponseEnvelope(
            provider=Provider.FOOTBALL_DATA_ORG.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
    
    url = f"https://api.football-data.org/v4/matches/{mapped_id}"
    headers = {"X-Auth-Token": credential_value, "Accept": "application/json"}
    status_code, body, err = safe_http_get(url, headers=headers, timeout=10.0)
    
    if err:
        return ProviderResponseEnvelope(
            provider=Provider.FOOTBALL_DATA_ORG.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            error=err,
        )
        
    if status_code == 200:
        try:
            sanitized = sanitize_json_body(body)
            sha = compute_body_sha256(sanitized)
            return ProviderResponseEnvelope(
                provider=Provider.FOOTBALL_DATA_ORG.value,
                status=CaptureStatus.FETCHED.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                body=sanitized,
                body_sha256=sha,
            )
        except Exception as e:
            return ProviderResponseEnvelope(
                provider=Provider.FOOTBALL_DATA_ORG.value,
                status=CaptureStatus.FAILED_PARSE.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                error=f"Sanitization/parse exception: {str(e)}",
            )
    else:
        return ProviderResponseEnvelope(
            provider=Provider.FOOTBALL_DATA_ORG.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            status_code=status_code,
            error=f"HTTP non-200: {status_code}",
        )


def capture_highlightly(fixture: Dict[str, Any], credential_value: str | None) -> ProviderResponseEnvelope:
    slug = fixture["fixture_slug"]
    if not credential_value:
        return ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
    mapped_id = get_mapped_id(slug, "highlightly")
    if not mapped_id:
        return ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
        
    url = f"https://soccer.highlightly.net/matches/{mapped_id}"
    headers = {"x-rapidapi-key": credential_value, "Accept": "application/json"}
    status_code, body, err = safe_http_get(url, headers=headers, timeout=10.0)
    
    if err:
        return ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            error=err,
        )
        
    if status_code == 200:
        try:
            sanitized = sanitize_json_body(body)
            sha = compute_body_sha256(sanitized)
            return ProviderResponseEnvelope(
                provider=Provider.HIGHLIGHTLY.value,
                status=CaptureStatus.FETCHED.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                body=sanitized,
                body_sha256=sha,
            )
        except Exception as e:
            return ProviderResponseEnvelope(
                provider=Provider.HIGHLIGHTLY.value,
                status=CaptureStatus.FAILED_PARSE.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                error=f"Sanitization exception: {str(e)}",
            )
    else:
        return ProviderResponseEnvelope(
            provider=Provider.HIGHLIGHTLY.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            status_code=status_code,
            error=f"HTTP non-200: {status_code}",
        )


def capture_api_football(fixture: Dict[str, Any], credential_value: str | None) -> ProviderResponseEnvelope:
    slug = fixture["fixture_slug"]
    if not credential_value:
        return ProviderResponseEnvelope(
            provider=Provider.API_FOOTBALL.value,
            status=CaptureStatus.SKIPPED_CREDENTIALS_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
    mapped_id = get_mapped_id(slug, "api-football")
    if not mapped_id:
        return ProviderResponseEnvelope(
            provider=Provider.API_FOOTBALL.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
        
    url = f"https://v3.football.api-sports.io/fixtures?id={mapped_id}"
    headers = {"x-apisports-key": credential_value, "Accept": "application/json"}
    status_code, body, err = safe_http_get(url, headers=headers, timeout=10.0)
    
    if err:
        return ProviderResponseEnvelope(
            provider=Provider.API_FOOTBALL.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            error=err,
        )
        
    if status_code == 200:
        try:
            sanitized = sanitize_json_body(body)
            sha = compute_body_sha256(sanitized)
            return ProviderResponseEnvelope(
                provider=Provider.API_FOOTBALL.value,
                status=CaptureStatus.FETCHED.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                body=sanitized,
                body_sha256=sha,
            )
        except Exception as e:
            return ProviderResponseEnvelope(
                provider=Provider.API_FOOTBALL.value,
                status=CaptureStatus.FAILED_PARSE.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                error=f"Sanitization exception: {str(e)}",
            )
    else:
        return ProviderResponseEnvelope(
            provider=Provider.API_FOOTBALL.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            status_code=status_code,
            error=f"HTTP non-200: {status_code}",
        )


def capture_espn_baseline(fixture: Dict[str, Any], credential_value: str | None = None) -> ProviderResponseEnvelope:
    slug = fixture["fixture_slug"]
    mapped_id = get_mapped_id(slug, "espn-baseline")
    if not mapped_id:
        return ProviderResponseEnvelope(
            provider=Provider.ESPN_BASELINE.value,
            status=CaptureStatus.BLOCKED_PROVIDER_MAPPING_MISSING.value,
            fixture_slug=slug,
            source_url=None,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
        )
        
    url = f"http://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={mapped_id}"
    status_code, body, err = safe_http_get(url, timeout=10.0)
    
    if err:
        return ProviderResponseEnvelope(
            provider=Provider.ESPN_BASELINE.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            error=err,
        )
        
    if status_code == 200:
        try:
            sanitized = sanitize_json_body(body)
            sha = compute_body_sha256(sanitized)
            return ProviderResponseEnvelope(
                provider=Provider.ESPN_BASELINE.value,
                status=CaptureStatus.FETCHED.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                body=sanitized,
                body_sha256=sha,
            )
        except Exception as e:
            return ProviderResponseEnvelope(
                provider=Provider.ESPN_BASELINE.value,
                status=CaptureStatus.FAILED_PARSE.value,
                fixture_slug=slug,
                source_url=url,
                captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
                status_code=status_code,
                error=f"Sanitization exception: {str(e)}",
            )
    else:
        return ProviderResponseEnvelope(
            provider=Provider.ESPN_BASELINE.value,
            status=CaptureStatus.FAILED_HTTP.value,
            fixture_slug=slug,
            source_url=url,
            captured_at_utc=datetime.datetime.utcnow().isoformat() + "Z",
            status_code=status_code,
            error=f"HTTP non-200: {status_code}",
        )
