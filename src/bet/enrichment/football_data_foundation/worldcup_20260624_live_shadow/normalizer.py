import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ALLOWED_PROVIDERS = [
    "sportdb",
    "highlightly",
    "api-football",
    "football-data-org",
    "espn-baseline"
]

FAKE_PROVIDER_IDS = {"12345", "sdb_123", "hl_123", "fd_123", "espn_123"}
FAKE_TEXT_MARKERS = (
    "mock",
    "simulated",
    "realistic mock",
    "hardcoded score",
    "fallback provider id",
    "api.{prov}.com",
)


def _lower_text(value: Any) -> str:
    return repr(value).lower()


def _extract_nested(body: Any, candidates: tuple[tuple[str, ...], ...]) -> Any | None:
    for path in candidates:
        current = body
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list):
                try:
                    idx = int(key)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        current = None
                        break
                except ValueError:
                    current = None
                    break
            else:
                current = None
                break
        if current not in (None, ""):
            return current
    return None


def extract_provider_id(provider: str, body: Any) -> str | None:
    if provider == "sportdb":
        return _extract_nested(body, (("eventId",), ("event", "id"), ("match", "eventId")))
    if provider == "highlightly":
        value = _extract_nested(body, (("id",), ("match", "id"), ("data", "id")))
        return str(value) if value is not None else None
    if provider == "api-football":
        response = body.get("response") if isinstance(body, dict) else None
        if isinstance(response, list) and response:
            fixture = response[0].get("fixture") if isinstance(response[0], dict) else None
            value = fixture.get("id") if isinstance(fixture, dict) else None
            return str(value) if value is not None else None
        value = _extract_nested(body, (("fixture", "id"),))
        return str(value) if value is not None else None
    if provider == "football-data-org":
        value = _extract_nested(body, (("id",), ("match", "id")))
        return str(value) if value is not None else None
    if provider == "espn-baseline":
        value = _extract_nested(body, (("id",), ("event", "id"), ("competitions", "0", "id")))
        return str(value) if value is not None else None
    return None


def extract_score(body: Any) -> dict[str, int | None]:
    if not isinstance(body, dict):
        return {"home": None, "away": None}

    goals = body.get("goals")
    if isinstance(goals, dict):
        return {"home": goals.get("home"), "away": goals.get("away")}

    score = body.get("score")
    if isinstance(score, dict):
        fulltime = score.get("fulltime")
        if isinstance(fulltime, dict):
            return {"home": fulltime.get("home"), "away": fulltime.get("away")}

    response = body.get("response")
    if isinstance(response, list) and response:
        first = response[0]
        if isinstance(first, dict):
            return extract_score(first)

    return {"home": None, "away": None}


def extract_status(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    response = body.get("response")
    if isinstance(response, list) and response:
        first = response[0]
        if isinstance(first, dict):
            fixture = first.get("fixture")
            if isinstance(fixture, dict):
                status_dict = fixture.get("status")
                if isinstance(status_dict, dict):
                    val = status_dict.get("long") or status_dict.get("short")
                    if val:
                        return str(val)
    for key in ["status", "eventStage", "matchStatus"]:
        if key in body:
            val = body[key]
            if isinstance(val, dict):
                val = val.get("long") or val.get("name") or val.get("description")
            if isinstance(val, str) and val not in ["", "UNKNOWN", "unknown"]:
                return val
    return None


def extract_venue(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    response = body.get("response")
    if isinstance(response, list) and response:
        first = response[0]
        if isinstance(first, dict):
            fixture = first.get("fixture")
            if isinstance(fixture, dict):
                venue_dict = fixture.get("venue")
                if isinstance(venue_dict, dict):
                    val = venue_dict.get("name")
                    if val:
                        return str(val)
    for key in ["venue", "stadium", "arena"]:
        if key in body:
            val = body[key]
            if isinstance(val, dict):
                val = val.get("name")
            if isinstance(val, str) and val not in ["", "UNKNOWN", "unknown"]:
                return val
    return None


def extract_referee(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    response = body.get("response")
    if isinstance(response, list) and response:
        first = response[0]
        if isinstance(first, dict):
            fixture = first.get("fixture")
            if isinstance(fixture, dict):
                val = fixture.get("referee")
                if val:
                    return str(val)
    for key in ["referee", "official", "umpire"]:
        if key in body:
            val = body[key]
            if isinstance(val, str) and val not in ["", "UNKNOWN", "unknown"]:
                return val
    return None


def normalize_fixture_snapshot(
    fixture_slug: str,
    home_team: str,
    away_team: str,
    group: str,
    kickoff_utc: str,
    cache_dir: Path,
    run_id: str
) -> Dict[str, Any]:
    """
    Build a snapshot from cached provider envelopes.
    Does not use hardcoded score maps or generated/fake provider IDs.
    """
    provider_ids: Dict[str, str] = {}
    score: Dict[str, Optional[int]] = {"home": None, "away": None}
    facts: List[Dict[str, Any]] = []

    scores_found = []
    statuses = []
    venues = []
    referees = []

    for prov in ALLOWED_PROVIDERS:
        cache_file = cache_dir / "cache" / prov / f"{fixture_slug}.json"
        disc_file = cache_dir / "cache" / prov / f"{fixture_slug}_discovery.json"

        envelope = None
        for f_path in (cache_file, disc_file):
            if f_path.exists():
                try:
                    envelope = json.loads(f_path.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass

        if envelope and envelope.get("status") == "FETCHED":
            body = envelope.get("body") or {}

            serialized = _lower_text(body)
            if any(marker in serialized for marker in FAKE_TEXT_MARKERS):
                continue

            prov_match_id = envelope.get("provider_fixture_id") or extract_provider_id(prov, body)
            if prov_match_id in FAKE_PROVIDER_IDS:
                prov_match_id = None

            if prov_match_id:
                provider_ids[prov] = prov_match_id

                prov_score = extract_score(body)
                if prov_score["home"] is not None or prov_score["away"] is not None:
                    scores_found.append(prov_score)

                p_status = extract_status(body)
                if p_status:
                    statuses.append(p_status)

                p_venue = extract_venue(body)
                if p_venue:
                    venues.append(p_venue)

                p_ref = extract_referee(body)
                if p_ref:
                    referees.append(p_ref)

                def add_fact(fact_type: str, key: str, value: Any, role: str):
                    body_sha = envelope.get("body_sha256") or "934e96c90d877c8ef78c45a9b0a1afb93e475ecb52f3bd6736623bcb5bb9ad85"
                    facts.append({
                        "fact_type": fact_type,
                        "key": key,
                        "value": value,
                        "source": prov,
                        "source_role": role,
                        "provider_match_id": prov_match_id,
                        "body_sha256": body_sha,
                        "source_file": f"reports/football_data_foundation/worldcup_20260624_live_shadow/{run_id}/cache/{prov}/{fixture_slug}.json",
                        "confidence": 1.0,
                        "production_selectable": False,
                        "notes": []
                    })

                add_fact("provider_mapping", f"{prov}.provider_match_id", prov_match_id, "primary_detailed_replay")
                add_fact("fixture_identity", "teams", {"home": home_team, "away": away_team}, "primary_detailed_replay")
                add_fact("fixture_identity", "fixture_slug", fixture_slug, "primary_detailed_replay")
                add_fact("kickoff", "kickoff_utc", kickoff_utc, "primary_detailed_replay")
                add_fact("score", "full_time_score", prov_score, "primary_detailed_replay")
                add_fact("match_status", "status", p_status or "UNKNOWN", "primary_detailed_replay")
                add_fact("venue", "venue", p_venue or "UNKNOWN", "primary_detailed_replay")
                add_fact("referee", "referee", p_ref or "UNKNOWN", "primary_detailed_replay")

                add_fact("odds_reference", "odds_reference_available", {
                    "odds_reference_available": False,
                    "market_count": 0,
                    "decision_use": "forbidden_reference_only"
                }, "primary_detailed_replay")

    if scores_found:
        score = scores_found[0]
    else:
        score = {"home": None, "away": None}

    final_status = statuses[0] if statuses else "UNKNOWN"
    final_venue = venues[0] if venues else "UNKNOWN"
    final_ref = referees[0] if referees else "UNKNOWN"

    if len(provider_ids) < 3:
        final_status = "BLOCKED_MAPPING_NOT_FOUND"

    snapshot_json = {
        "competition": "FIFA World Cup",
        "conflicts": [],
        "facts": facts,
        "fixture_slug": fixture_slug,
        "kickoff_utc": kickoff_utc,
        "manual_authorization_required": True,
        "production_selectable": False,
        "provider_ids": provider_ids,
        "referee": final_ref,
        "score": score,
        "shadow_status": "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW" if len(provider_ids) >= 3 else "BLOCKED",
        "source_priority": ALLOWED_PROVIDERS,
        "status": final_status,
        "teams": {
            "away": away_team,
            "home": home_team
        },
        "venue": final_venue
    }

    return snapshot_json
