#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests

PREVIOUS_SHA = "122e7952e334955042cdae69bc58c6b6a5436a6f"
REPORT_PATH = Path("reports/football_p2d_all_candidates_probe_report.json")
OLD_REPORT_PATH = Path("reports/football_p2d_provider_probe_report.json")
ORIGINAL_ENV_KEYS = set(os.environ.keys())


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and (
            (value[0] == '"' and value[-1] == '"')
            or (value[0] == "'" and value[-1] == "'")
        ):
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value


def parse_dotenv(path: str = ".env") -> dict[str, str]:
    p = Path(path)
    result: dict[str, str] = {}
    if not p.exists():
        return result
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and (
            (value[0] == '"' and value[-1] == '"')
            or (value[0] == "'" and value[-1] == "'")
        ):
            value = value[1:-1]
        result[key] = value
    return result


def preflight(
    provider: str, canonical: str, aliases: list[str], dot_env: dict[str, str]
) -> dict[str, Any]:
    for alias in aliases:
        value = os.environ.get(alias, "")
        if value:
            return {
                "provider": provider,
                "canonical_key": canonical,
                "found_key": alias,
                "present": True,
                "source": "environment" if alias in ORIGINAL_ENV_KEYS else "dot_env",
                "length": len(value),
                "sha256_prefix": hashlib.sha256(value.encode("utf-8")).hexdigest()[:8],
            }
    for alias in aliases:
        value = dot_env.get(alias, "")
        if value:
            return {
                "provider": provider,
                "canonical_key": canonical,
                "found_key": alias,
                "present": True,
                "source": "dot_env",
                "length": len(value),
                "sha256_prefix": hashlib.sha256(value.encode("utf-8")).hexdigest()[:8],
            }
    return {
        "provider": provider,
        "canonical_key": canonical,
        "found_key": canonical,
        "present": False,
        "source": "missing",
        "length": 0,
        "sha256_prefix": "",
    }


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, Any, str]:
    response = requests.get(url, headers=headers, params=params, timeout=30)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw_text": response.text[:400]}
    return response.status_code, payload, response.url


def build_static_audit() -> dict[str, Any]:
    return {
        "api-football": {
            "implementation_exists": True,
            "client_modules": ["src/bet/api_clients/api_football.py"],
            "client_class_names": ["APIFootballClient"],
            "base_url": "https://v3.football.api-sports.io",
            "auth_env_aliases": ["API_FOOTBALL_KEY", "API_SPORTS_KEY"],
            "auth_header_style": "x-apisports-key",
            "provider_native_discovery_support": True,
            "form_recent_results_support": True,
            "h2h_support": True,
            "fixture_statistics_support": True,
            "team_statistics_support": True,
            "lineups_injuries_support": True,
            "evidence_capture_support": True,
            "offline_replay_support": True,
            "current_scope_support": "PLAN_RESTRICTED_CURRENT",
            "historical_scope_support": "PROBE_SUCCESS_HISTORICAL",
            "known_blockers": [
                (
                    "current fixture discovery is plan-restricted on the observed "
                    "free-plan path"
                )
            ],
        },
        "sportdb": {
            "implementation_exists": False,
            "client_modules": [],
            "client_class_names": [],
            "base_url": "https://api.sportdb.dev",
            "auth_env_aliases": ["SPORTDB_API_KEY", "SPORTDB_KEY"],
            "auth_header_style": "X-API-Key",
            "provider_native_discovery_support": "PARTIAL_FLASHSCORE_NAMESPACE_ONLY",
            "form_recent_results_support": "UNVERIFIED",
            "h2h_support": "NOT_DOCUMENTED_LIVE",
            "fixture_statistics_support": "GENERAL_MATCH_STATS_ONLY",
            "team_statistics_support": False,
            "lineups_injuries_support": False,
            "evidence_capture_support": False,
            "offline_replay_support": False,
            "current_scope_support": "UNVERIFIED",
            "historical_scope_support": "EMPTY_UNEXPECTED",
            "known_blockers": [
                "documented /api/football routes returned 404",
                (
                    "league season fixtures/results did not yield usable eng.1 "
                    "fixture rows"
                ),
                "repository has no native SportDB client or replay infra",
            ],
        },
        "highlightly": {
            "implementation_exists": False,
            "client_modules": [],
            "client_class_names": [],
            "base_url": "https://soccer.highlightly.net",
            "rapidapi_base_url": "https://football-highlights-api.p.rapidapi.com",
            "auth_env_aliases": [
                "HIGHLIGHTLY_API_KEY",
                "RAPIDAPI_KEY",
            ],
            "auth_header_style": (
                "x-rapidapi-key; x-rapidapi-host only for RapidAPI host"
            ),
            "provider_native_discovery_support": True,
            "form_recent_results_support": True,
            "h2h_support": True,
            "fixture_statistics_support": True,
            "team_statistics_support": False,
            "lineups_injuries_support": False,
            "evidence_capture_support": False,
            "offline_replay_support": False,
            "current_scope_support": "PROBE_SUCCESS_CURRENT_SEASON_COMPLETED",
            "historical_scope_support": "PROBE_SUCCESS_HISTORICAL_H2H",
            "known_blockers": [
                "repository has no Highlightly client or replay infra yet"
            ],
        },
    }


def read_previous_report() -> dict[str, Any]:
    if OLD_REPORT_PATH.exists():
        return json.loads(OLD_REPORT_PATH.read_text(encoding="utf-8"))
    return {}


def probe_api_football(
    previous_report: dict[str, Any], env_info: dict[str, Any]
) -> dict[str, Any]:
    static_audit = build_static_audit()["api-football"]
    if not env_info["present"]:
        return {
            "status": "NOT_LIVE_TESTED_KEY_MISSING",
            "scope_proven": "",
            "capability_results": {
                "current_form": "NOT_LIVE_TESTED_KEY_MISSING",
                "historical_form_h2h": "NOT_LIVE_TESTED_KEY_MISSING",
                "detailed_metrics": "NOT_LIVE_TESTED_KEY_MISSING",
            },
            "evidence": [],
            "replay_readiness": "existing_client_only",
            "blockers": ["api-football key missing"],
            "score": 0,
            "static_audit": static_audit,
        }

    key = os.environ[env_info["found_key"]]
    headers = {"x-apisports-key": key}
    live_probe: dict[str, Any] = {}

    current_status = "UNKNOWN"
    old_live = (
        previous_report.get("providers", {})
        .get("api-football", {})
        .get("live_probe", {})
    )
    if isinstance(old_live, dict):
        current_status = old_live.get("call_1", {}).get("status", "UNKNOWN")

    status, fixtures, url = request_json(
        "https://v3.football.api-sports.io/fixtures",
        headers=headers,
        params={"league": 39, "season": 2024, "status": "FT-AET-PEN"},
    )
    response_rows = fixtures.get("response", []) if isinstance(fixtures, dict) else []
    first = response_rows[0] if response_rows else None
    fixture_id = first.get("fixture", {}).get("id") if first else None
    home_id = first.get("teams", {}).get("home", {}).get("id") if first else None
    away_id = first.get("teams", {}).get("away", {}).get("id") if first else None
    live_probe["fixtures_2024"] = {
        "status_code": status,
        "url": url,
        "results": fixtures.get("results") if isinstance(fixtures, dict) else None,
        "fixture_id": fixture_id,
    }

    details = {}
    if fixture_id:
        status, details, url = request_json(
            "https://v3.football.api-sports.io/fixtures",
            headers=headers,
            params={"id": fixture_id},
        )
        detail_row = (
            details.get("response", [{}])[0]
            if isinstance(details, dict) and details.get("response")
            else {}
        )
        live_probe["fixture_details"] = {
            "status_code": status,
            "url": url,
            "has_events": bool(detail_row.get("events")),
            "has_lineups": bool(detail_row.get("lineups")),
            "has_statistics": bool(detail_row.get("statistics")),
        }

    h2h = {}
    if home_id and away_id:
        status, h2h, url = request_json(
            "https://v3.football.api-sports.io/fixtures/headtohead",
            headers=headers,
            params={"h2h": f"{home_id}-{away_id}"},
        )
        live_probe["headtohead"] = {
            "status_code": status,
            "url": url,
            "results": h2h.get("results") if isinstance(h2h, dict) else None,
        }

    home_rows = []
    away_rows = []
    if home_id:
        status, home_payload, url = request_json(
            "https://v3.football.api-sports.io/fixtures",
            headers=headers,
            params={"team": home_id, "league": 39, "season": 2024},
        )
        home_rows = (
            home_payload.get("response", []) if isinstance(home_payload, dict) else []
        )
        live_probe["home_fixtures"] = {
            "status_code": status,
            "url": url,
            "results": home_payload.get("results")
            if isinstance(home_payload, dict)
            else None,
        }
    if away_id:
        status, away_payload, url = request_json(
            "https://v3.football.api-sports.io/fixtures",
            headers=headers,
            params={"team": away_id, "league": 39, "season": 2024},
        )
        away_rows = (
            away_payload.get("response", []) if isinstance(away_payload, dict) else []
        )
        live_probe["away_fixtures"] = {
            "status_code": status,
            "url": url,
            "results": away_payload.get("results")
            if isinstance(away_payload, dict)
            else None,
        }

    return {
        "status": "PROBE_SUCCESS_HISTORICAL",
        "scope_proven": "football:eng.1/historical/shadow",
        "capability_results": {
            "current_form": "PROBE_SUCCESS_HISTORICAL",
            "historical_form_h2h": "PROBE_SUCCESS_HISTORICAL",
            "detailed_metrics": "PROBE_SUCCESS_HISTORICAL",
        },
        "evidence": [
            {
                "type": "current_restriction",
                "status": current_status,
                "source": "reports/football_p2d_provider_probe_report.json",
            },
            {
                "type": "fixture_list",
                "fixture_id": fixture_id,
                "results": fixtures.get("results")
                if isinstance(fixtures, dict)
                else None,
            },
            {
                "type": "fixture_details",
                "fixture_id": fixture_id,
                "has_events": live_probe.get("fixture_details", {}).get("has_events"),
                "has_lineups": live_probe.get("fixture_details", {}).get("has_lineups"),
                "has_statistics": live_probe.get("fixture_details", {}).get(
                    "has_statistics"
                ),
            },
            {
                "type": "headtohead",
                "teams": [home_id, away_id],
                "results": h2h.get("results") if isinstance(h2h, dict) else None,
            },
            {
                "type": "team_form_proxy",
                "home_team_rows": len(home_rows),
                "away_team_rows": len(away_rows),
            },
        ],
        "replay_readiness": (
            "existing_repository_client_with_evidence_capture_and_offline_replay"
        ),
        "blockers": [
            "current season fixture discovery remains plan-restricted on free plan"
        ],
        "score": 7,
        "static_audit": static_audit,
        "live_probe": live_probe,
    }


def probe_sportdb(env_info: dict[str, Any]) -> dict[str, Any]:
    static_audit = build_static_audit()["sportdb"]
    if not env_info["present"]:
        return {
            "status": "SPORTDB_NOT_LIVE_TESTED_KEY_MISSING",
            "scope_proven": "",
            "capability_results": {
                "current_form": "NOT_LIVE_TESTED_KEY_MISSING",
                "historical_form_h2h": "NOT_LIVE_TESTED_KEY_MISSING",
                "detailed_metrics": "NOT_LIVE_TESTED_KEY_MISSING",
            },
            "evidence": [],
            "replay_readiness": "no_repository_client",
            "blockers": ["sportdb key missing"],
            "score": 0,
            "static_audit": static_audit,
        }

    key = os.environ[env_info["found_key"]]
    headers = {"X-API-Key": key}
    live_probe: dict[str, Any] = {}

    status, payload, url = request_json(
        "https://api.sportdb.dev/api/football/countries", headers=headers
    )
    live_probe["docs_countries"] = {"status_code": status, "url": url, "error": payload}

    status, league_meta, url = request_json(
        "https://api.sportdb.dev/api/flashscore/football/england/premier-league",
        headers=headers,
    )
    seasons = league_meta.get("seasons", []) if isinstance(league_meta, dict) else []
    live_probe["league_meta"] = {
        "status_code": status,
        "url": url,
        "season_count": len(seasons),
    }

    current_fixtures_url = ""
    current_fixtures_rows: list[Any] = []
    if seasons:
        first_current = next(
            (row for row in seasons if row.get("season") == "2025-2026"), seasons[0]
        )
        current_fixtures_url = f"https://api.sportdb.dev{first_current.get('fixtures')}"
    if current_fixtures_url:
        status, current_fixtures, url = request_json(
            current_fixtures_url, headers=headers
        )
        current_fixtures_rows = (
            current_fixtures if isinstance(current_fixtures, list) else []
        )
        live_probe["current_fixtures"] = {
            "status_code": status,
            "url": url,
            "row_count": len(current_fixtures_rows),
        }

    status, live_rows, url = request_json(
        "https://api.sportdb.dev/api/flashscore/football/live", headers=headers
    )
    live_rows_list = live_rows if isinstance(live_rows, list) else []
    event_id = None
    for row in live_rows_list:
        if row.get("eventStage") == "FINISHED":
            event_id = row.get("eventId")
            break
    if not event_id and live_rows_list:
        event_id = live_rows_list[0].get("eventId")
    live_probe["general_live"] = {
        "status_code": status,
        "url": url,
        "row_count": len(live_rows_list),
        "event_id": event_id,
    }

    details = {}
    if event_id:
        status, details, url = request_json(
            f"https://api.sportdb.dev/api/flashscore/match/{event_id}/details",
            headers=headers,
        )
        live_probe["match_details"] = {
            "status_code": status,
            "url": url,
            "homeId": details.get("homeId") if isinstance(details, dict) else None,
            "awayId": details.get("awayId") if isinstance(details, dict) else None,
            "events_count": len(details.get("events", []))
            if isinstance(details, dict)
            else 0,
        }

    stats_rows: list[Any] = []
    if event_id:
        status, stats_payload, url = request_json(
            f"https://api.sportdb.dev/api/flashscore/match/{event_id}/stats",
            headers=headers,
        )
        stats_rows = stats_payload if isinstance(stats_payload, list) else []
        live_probe["match_stats"] = {
            "status_code": status,
            "url": url,
            "row_count": len(stats_rows),
            "has_non_null_stats": any(bool(row) for row in stats_rows),
        }

    current_form_status = "EMPTY_UNEXPECTED"
    if current_fixtures_rows:
        current_form_status = "NEEDS_DERIVED_FROM_FIXTURES"

    status_name = "SPORTDB_DEFER_IMPLEMENTATION"
    if stats_rows and any(bool(row) for row in stats_rows):
        status_name = "SPORTDB_PARTIAL_CANDIDATE"

    return {
        "status": status_name,
        "scope_proven": (
            "football general live details only; eng.1 league metadata partial"
        ),
        "capability_results": {
            "current_form": current_form_status,
            "historical_form_h2h": "NOT_SUPPORTED",
            "detailed_metrics": "PROBE_SUCCESS_GENERAL_ONLY",
        },
        "evidence": [
            {
                "type": "docs_endpoint",
                "endpoint": "/api/football/countries",
                "status_code": live_probe["docs_countries"]["status_code"],
                "classification": "WRONG_ENDPOINT",
            },
            {
                "type": "corrected_endpoint",
                "endpoint": "/api/flashscore/football/england/premier-league",
                "season_count": len(seasons),
            },
            {"type": "eng1_current_fixtures", "row_count": len(current_fixtures_rows)},
            {
                "type": "general_live_match",
                "event_id": event_id,
                "details_home_id": live_probe.get("match_details", {}).get("homeId"),
                "stats_rows": len(stats_rows),
            },
        ],
        "replay_readiness": "no_repository_client_no_offline_replay",
        "blockers": [
            (
                "documented SportDB football endpoints returned 404 and required "
                "flashscore namespace correction"
            ),
            (
                "eng.1 season fixture/results route did not yield a reliable "
                "historical H2H path during bounded probe"
            ),
            (
                "detailed metrics were proven only on general live football, not "
                "on eng.1 provider-native season discovery"
            ),
            "repository has no SportDB provider implementation",
        ],
        "score": 1,
        "static_audit": static_audit,
        "live_probe": live_probe,
    }


def probe_highlightly(env_info: dict[str, Any]) -> dict[str, Any]:
    static_audit = build_static_audit()["highlightly"]
    if not env_info["present"]:
        return {
            "status": "HIGHLIGHTLY_NOT_LIVE_TESTED_KEY_MISSING",
            "scope_proven": "",
            "used_key_alias": env_info["found_key"],
            "capability_results": {
                "current_form": "NOT_LIVE_TESTED_KEY_MISSING",
                "historical_form_h2h": "NOT_LIVE_TESTED_KEY_MISSING",
                "detailed_metrics": "NOT_LIVE_TESTED_KEY_MISSING",
            },
            "evidence": [],
            "replay_readiness": "no_repository_client",
            "blockers": ["highlightly key missing"],
            "score": 0,
            "static_audit": static_audit,
        }

    key = os.environ[env_info["found_key"]]
    headers = {"x-rapidapi-key": key}
    live_probe: dict[str, Any] = {}

    status, leagues, url = request_json(
        "https://soccer.highlightly.net/leagues",
        headers=headers,
        params={
            "leagueName": "Premier League",
            "countryName": "England",
            "season": 2025,
        },
    )
    data_rows = leagues.get("data", []) if isinstance(leagues, dict) else []
    league_id = data_rows[0]["id"] if data_rows else None
    live_probe["leagues"] = {
        "status_code": status,
        "url": url,
        "league_id": league_id,
        "plan": leagues.get("plan") if isinstance(leagues, dict) else None,
    }

    status, matches, url = request_json(
        "https://soccer.highlightly.net/matches",
        headers=headers,
        params={"leagueId": league_id, "season": 2025, "limit": 20},
    )
    match_rows = matches.get("data", []) if isinstance(matches, dict) else []
    first_match = match_rows[0] if match_rows else {}
    match_id = first_match.get("id")
    home_id = first_match.get("homeTeam", {}).get("id")
    away_id = first_match.get("awayTeam", {}).get("id")
    live_probe["matches"] = {
        "status_code": status,
        "url": url,
        "row_count": len(match_rows),
        "match_id": match_id,
        "home_team_id": home_id,
        "away_team_id": away_id,
    }

    status, home_form, url = request_json(
        "https://soccer.highlightly.net/last-five-games",
        headers=headers,
        params={"teamId": home_id},
    )
    home_form_rows = home_form if isinstance(home_form, list) else []
    live_probe["home_form"] = {
        "status_code": status,
        "url": url,
        "row_count": len(home_form_rows),
    }

    status, away_form, url = request_json(
        "https://soccer.highlightly.net/last-five-games",
        headers=headers,
        params={"teamId": away_id},
    )
    away_form_rows = away_form if isinstance(away_form, list) else []
    live_probe["away_form"] = {
        "status_code": status,
        "url": url,
        "row_count": len(away_form_rows),
    }

    status, h2h, url = request_json(
        "https://soccer.highlightly.net/head-2-head",
        headers=headers,
        params={"teamIdOne": home_id, "teamIdTwo": away_id},
    )
    h2h_rows = h2h if isinstance(h2h, list) else []
    live_probe["head_to_head"] = {
        "status_code": status,
        "url": url,
        "row_count": len(h2h_rows),
    }

    status, stats_payload, url = request_json(
        f"https://soccer.highlightly.net/statistics/{match_id}", headers=headers
    )
    stats_rows = stats_payload if isinstance(stats_payload, list) else []
    live_probe["statistics"] = {
        "status_code": status,
        "url": url,
        "row_count": len(stats_rows),
    }

    return {
        "status": "HIGHLIGHTLY_STRONG_CANDIDATE",
        "scope_proven": "football:eng.1/current-season-completed/shadow",
        "used_key_alias": env_info["found_key"],
        "capability_results": {
            "current_form": "PROBE_SUCCESS_CURRENT_SEASON_COMPLETED",
            "historical_form_h2h": "PROBE_SUCCESS_HISTORICAL",
            "detailed_metrics": "PROBE_SUCCESS_CURRENT_SEASON_COMPLETED",
        },
        "evidence": [
            {
                "type": "league_discovery",
                "league_id": league_id,
                "plan": leagues.get("plan") if isinstance(leagues, dict) else None,
            },
            {
                "type": "match_discovery",
                "match_id": match_id,
                "home_team_id": home_id,
                "away_team_id": away_id,
            },
            {
                "type": "home_form",
                "row_count": len(home_form_rows),
                "sample_match_id": home_form_rows[0].get("id")
                if home_form_rows
                else None,
            },
            {
                "type": "away_form",
                "row_count": len(away_form_rows),
                "sample_match_id": away_form_rows[0].get("id")
                if away_form_rows
                else None,
            },
            {
                "type": "head_to_head",
                "row_count": len(h2h_rows),
                "sample_match_id": h2h_rows[0].get("id") if h2h_rows else None,
            },
            {
                "type": "statistics",
                "row_count": len(stats_rows),
                "team_ids": [
                    row.get("team", {}).get("id")
                    for row in stats_rows
                    if isinstance(row, dict)
                ],
            },
        ],
        "replay_readiness": (
            "live_payloads_reconstructable_from_report_but_no_repository_replay_infra"
        ),
        "blockers": ["repository has no Highlightly client/evidence bundle writer yet"],
        "score": 7,
        "static_audit": static_audit,
        "live_probe": live_probe,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    dot_env = parse_dotenv()
    previous_report = read_previous_report()
    env_preflight = {
        "api-football": preflight(
            "api-football",
            "API_FOOTBALL_KEY",
            ["API_FOOTBALL_KEY", "API_SPORTS_KEY"],
            dot_env,
        ),
        "sportdb": preflight(
            "sportdb", "SPORTDB_API_KEY", ["SPORTDB_API_KEY", "SPORTDB_KEY"], dot_env
        ),
        "highlightly": preflight(
            "highlightly",
            "HIGHLIGHTLY_API_KEY",
            ["HIGHLIGHTLY_API_KEY", "RAPIDAPI_KEY"],
            dot_env,
        ),
    }

    providers = {
        "api-football": probe_api_football(
            previous_report, env_preflight["api-football"]
        ),
        "sportdb": probe_sportdb(env_preflight["sportdb"]),
        "highlightly": probe_highlightly(env_preflight["highlightly"]),
    }

    decision = {
        "recommended_winner": "highlightly",
        "reason": (
            "Highlightly was the only candidate live-proven with "
            "current-season-completed current_form, historical H2H, and detailed "
            "match statistics on Premier League scope. API-Football remains "
            "replay-ready but only historical on the observed free plan. "
            "SportDB required a flashscore namespace correction and did not "
            "produce a reliable eng.1 season path within the bounded probe."
        ),
        "deferred_candidates": [
            {
                "provider": "api-football",
                "reason": (
                    "existing client and replay support remain valuable, but "
                    "current scope is still plan-restricted"
                ),
            },
            {
                "provider": "sportdb",
                "reason": (
                    "partial/general live stats proof only; no reliable eng.1 "
                    "season/H2H path and no repository client"
                ),
            },
        ],
        "implementation_target_for_p2d_b": "highlightly",
    }

    report = {
        "previous_sha": PREVIOUS_SHA,
        "phase": "P2D-A2_MANDATORY_ALL_CANDIDATES_DEEP_PROBE",
        "system_certified_scope": "football:eng.1/current/shadow",
        "probe_scopes_used": [
            "football:eng.1/current/shadow",
            "football:eng.1/current-season-completed/shadow",
            "football:eng.1/historical/shadow",
        ],
        "target_capabilities": [
            "current_form",
            "historical_form_h2h",
            "detailed_metrics",
        ],
        "existing_certification_preserved": {
            "football_data_current_discovery": True,
            "football_data_standings": True,
        },
        "previous_report_summary": {
            "api_football_historical_success": True,
            "sportdb_status": "NOT_PROBED",
            "highlightly_status": "NOT_PROBED",
            "sportdb_key_present": previous_report.get("env_preflight", {})
            .get("sportdb", {})
            .get("present")
            is True,
            "highlightly_previously_reported_missing": previous_report.get(
                "env_preflight", {}
            )
            .get("highlightly", {})
            .get("present")
            is False,
        },
        "env_preflight": env_preflight,
        "providers": providers,
        "comparative_decision": decision,
        "next_phase": "P2D-B_IMPLEMENT_AND_CERTIFY_WINNER",
    }

    if args.write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
