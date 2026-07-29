from typing import Any, Dict, List, Optional
from .contracts import NormalizedFact
from .loader import ProviderEnvelope
from .provider_normalizers import (
    normalize_api_football,
    normalize_football_data_org,
    normalize_espn_baseline,
    normalize_sportdb,
    normalize_highlightly,
)

def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)

def _provider_id_keys(provider: str) -> List[str]:
    if provider == "sportdb":
        return ["eventId", "id", "matchId"]
    if provider == "highlightly":
        return ["id", "matchId"]
    if provider == "api-football":
        return ["fixture.id", "id"]
    if provider == "football-data-org":
        return ["id"]
    if provider == "espn-baseline":
        return ["id", "eventId"]
    return ["id"]

def _find_provider_id(provider: str, body: Any) -> Optional[str]:
    if not body:
        return None
    for node in _walk(body):
        if not isinstance(node, dict):
            continue
        for key in _provider_id_keys(provider):
            if "." in key:
                parent, child = key.split(".", 1)
                nested = node.get(parent)
                if isinstance(nested, dict) and nested.get(child) is not None:
                    return str(nested[child])
            elif node.get(key) is not None:
                return str(node[key])
    return None

def normalize_envelope(env: ProviderEnvelope, provider_match_id: Optional[str] = None) -> List[NormalizedFact]:
    # Check valid status
    valid_statuses = {"SUCCESS", "DISCOVERY_FETCHED", "FETCHED", "RESCUE_FETCHED"}
    if env.status not in valid_statuses:
        return []

    valid_providers = {"sportdb", "highlightly", "api-football", "football-data-org", "espn-baseline"}
    if env.provider not in valid_providers:
        return []

    # If no provider_match_id was passed, try to extract it from the body
    if not provider_match_id:
        provider_match_id = _find_provider_id(env.provider, env.body)

    # If still not found, check if it's in the filename or URL (as fallback)
    if not provider_match_id and env.source_url:
        for part in env.source_url.split("/"):
            if part.isdigit() or (env.provider == "sportdb" and len(part) == 8 and part.isalnum()):
                provider_match_id = part
                break

    facts: List[NormalizedFact] = []
    if env.provider == "api-football":
        facts = normalize_api_football(env, provider_match_id)
    elif env.provider == "football-data-org":
        facts = normalize_football_data_org(env, provider_match_id)
    elif env.provider == "espn-baseline":
        facts = normalize_espn_baseline(env, provider_match_id)
    elif env.provider == "sportdb":
        facts = normalize_sportdb(env, provider_match_id)
    elif env.provider == "highlightly":
        facts = normalize_highlightly(env, provider_match_id)

    return facts
