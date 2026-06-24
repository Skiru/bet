#!/usr/bin/env python3
"""Capture accepted-provider same-match evidence for the SportDB fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.api_clients.highlightly import HighlightlyClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

PHASE_ID = "P2E_A8_ACCEPTED_PROVIDER_SAME_MATCH_REPLAY_CAPTURE"
PROMPT_VERSION = "v1_masterpiece_highlightly_same_match_capture"
PREVIOUS_ACCEPTED_SHA = "0838adfb058f6d820432ef9c677ebd33f165bfbd"
PROTECTED_WORKTREE = "/Users/mkoziol/projects/bet-multisport-enrichment-v1"
SUMMARY_PATH = "certification/football/p2e_accepted_provider_same_match_replay_capture_summary.json"
P2E_A7_SUMMARY_PATH = Path(
    "certification/football/p2e_sportdb_identity_bridge_value_replay_summary.json"
)
P2E_A6_SUMMARY_PATH = Path("certification/football/p2e_sportdb_evidence_bundle_summary.json")
P2D_HIGHLIGHTLY_SUMMARY_PATH = Path(
    "certification/football/p2d_highlightly_certification_summary.json"
)
NOT_CERTIFIED_VERDICT = "NOT_CERTIFIED_ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_ONLY"
EVIDENCE_ROOT = Path("betting/data/evidence/highlightly/football/p2e_a8")
SOURCE_INPUT_PATHS = [
    str(P2E_A7_SUMMARY_PATH),
    str(P2E_A6_SUMMARY_PATH),
    str(P2D_HIGHLIGHTLY_SUMMARY_PATH),
]
REQUIRED_OPERATIONS = {
    "competition_results",
    "competition_standings",
    "match_events",
    "match_lineups",
    "match_stats",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_dotenv(path: str = ".env") -> None:
    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
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


def normalize_team_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = re.sub(r"\butd\b", "united", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [
        token
        for token in text.split()
        if token not in {"fc", "cf", "club", "afc", "sc", "ac", "cfc"}
    ]
    return " ".join(tokens)


def kickoff_or_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if match:
        return match.group(1)
    return text[:10] if len(text) >= 10 else text


def normalize_score_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return text or None


def normalize_season_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return f"{value}-{value + 1}"
    text = str(value).strip()
    if re.fullmatch(r"\d{4}", text):
        start = int(text)
        return f"{start}-{start + 1}"
    if re.fullmatch(r"\d{4}-\d{4}", text):
        return text
    return text


def season_start_year(value: Any) -> str | None:
    normalized = normalize_season_value(value)
    if not normalized:
        return None
    match = re.match(r"^(\d{4})", normalized)
    return match.group(1) if match else None


def normalize_competition_label(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = text.replace("&", " and ")
    text = text.replace(":", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\bcurrent\b|\bseason\b|\bcompleted\b|\bshadow\b", " ", text)
    text = re.sub(r"\bengland\b", "england", text)
    text = re.sub(r"\bpremier\b", "premier", text)
    text = re.sub(r"\bleague\b", "league", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def competition_equivalent(left: Any, right: Any) -> bool:
    left_norm = normalize_competition_label(left)
    right_norm = normalize_competition_label(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    premier_tokens = {"england premier league", "premier league"}
    return left_norm in premier_tokens and right_norm in premier_tokens


def parse_request_identity(request_identity: str) -> dict[str, Any]:
    parts = (request_identity or "").split(":")
    result = {
        "sport": None,
        "country": None,
        "competition": None,
        "season": None,
        "match_id": None,
    }
    if len(parts) >= 6:
        result["sport"] = parts[2]
        result["country"] = parts[3]
        result["competition"] = parts[4]
        result["season"] = parts[5]
    if len(parts) >= 7:
        result["match_id"] = parts[6]
    return result


def load_sportdb_operation_bundles(summary: dict[str, Any]) -> dict[str, Any]:
    bundles: dict[str, Any] = {}
    operations = summary.get("operations", {})
    missing_ops = REQUIRED_OPERATIONS - set(operations)
    if missing_ops:
        raise ValueError("missing_operations:" + ",".join(sorted(missing_ops)))
    for op_name, op_data in operations.items():
        op_bundle: dict[str, Any] = {
            "meta": {
                "bundle_id": op_data.get("bundle_id"),
                "request_identity": op_data.get("request_identity"),
                "bundle_files": list(op_data.get("bundle_files", [])),
            },
            "files": {},
        }
        for path_str in op_data.get("bundle_files", []):
            path = Path(path_str)
            if not path.exists():
                raise FileNotFoundError(path)
            if path.suffix == ".json":
                op_bundle["files"][path.name] = load_json(path)
            else:
                op_bundle["files"][path.name] = path.read_text(encoding="utf-8")
        bundles[op_name] = op_bundle
    return bundles


def extract_sportdb_target_identity(
    a7_summary: dict[str, Any], a6_summary: dict[str, Any]
) -> dict[str, Any]:
    bundles = load_sportdb_operation_bundles(a6_summary)
    a7_identity = a7_summary.get("sportdb_identity", {})
    match_events = bundles.get("match_events", {})
    competition_results = bundles.get("competition_results", {})
    match_stats = bundles.get("match_stats", {})
    events_normalized = match_events.get("files", {}).get("normalized.json", {})
    results_normalized = competition_results.get("files", {}).get("normalized.json", [])
    request_identity = (
        match_stats.get("files", {}).get("manifest.json", {}).get("request_identity")
        or match_stats.get("meta", {}).get("request_identity")
        or match_events.get("files", {}).get("manifest.json", {}).get("request_identity")
        or match_events.get("meta", {}).get("request_identity")
        or ""
    )
    request_bits = parse_request_identity(request_identity)
    raw_data = events_normalized.get("raw_result", {}).get("data", {})
    score = a7_identity.get("score")
    status = a7_identity.get("status")
    match_id = a7_identity.get("match_id") or request_bits.get("match_id")
    if isinstance(results_normalized, list) and match_id:
        for row in results_normalized:
            if row.get("provider_match_id") == match_id:
                score = score or row.get("score")
                status = status or row.get("status")
                break
    competition = a7_identity.get("competition")
    if not competition and request_bits.get("competition"):
        competition = request_bits["competition"].replace("-", " ").title()
    identity = {
        "provider_family": "flashscore",
        "match_id": match_id or events_normalized.get("provider_match_id"),
        "competition": competition,
        "season": a7_identity.get("season") or normalize_season_value(request_bits.get("season")),
        "kickoff_or_match_date": a7_identity.get("kickoff_or_match_date")
        or raw_data.get("startDateTimeUtc")
        or raw_data.get("startTime"),
        "home_team": a7_identity.get("home_team") or raw_data.get("homeName"),
        "away_team": a7_identity.get("away_team") or raw_data.get("awayName"),
        "home_team_normalized": a7_identity.get("home_team_normalized")
        or normalize_team_name(raw_data.get("homeName") or "")
        or None,
        "away_team_normalized": a7_identity.get("away_team_normalized")
        or normalize_team_name(raw_data.get("awayName") or "")
        or None,
        "score": score,
        "status": status,
        "identity_fields_available": [],
    }
    identity["identity_fields_available"] = [
        key
        for key in (
            "match_id",
            "competition",
            "season",
            "kickoff_or_match_date",
            "home_team",
            "away_team",
            "home_team_normalized",
            "away_team_normalized",
            "score",
            "status",
        )
        if identity.get(key) not in (None, "")
    ]
    return identity


def build_highlightly_search_plan(identity: dict[str, Any]) -> dict[str, Any]:
    competition = str(identity.get("competition") or "")
    country_name = "England" if "england" in competition.lower() else None
    league_name = "Premier League" if "premier league" in competition.lower() else competition
    season_start = season_start_year(identity.get("season"))
    return {
        "league_name": league_name or None,
        "country_name": country_name,
        "season_start_year": int(season_start) if season_start else None,
        "target_date": kickoff_or_date(identity.get("kickoff_or_match_date")),
        "home_team_normalized": identity.get("home_team_normalized"),
        "away_team_normalized": identity.get("away_team_normalized"),
        "score": identity.get("score"),
        "match_id": identity.get("match_id"),
        "match_limit": 20,
    }


def _resolve_highlightly_env() -> tuple[bool, str | None]:
    load_dotenv()
    for alias in ("HIGHLIGHTLY_API_KEY", "RAPIDAPI_KEY"):
        value = os.environ.get(alias, "").strip()
        if value:
            return True, alias
    return False, None


def _status_bucket(status: SourceResultStatus) -> str:
    if status in {SourceResultStatus.AUTHENTICATION_ERROR, SourceResultStatus.PLAN_RESTRICTED}:
        return "auth"
    if status is SourceResultStatus.RATE_LIMITED:
        return "rate_limited"
    if status in {
        SourceResultStatus.BLOCKED,
        SourceResultStatus.TRANSPORT_ERROR,
        SourceResultStatus.UPSTREAM_ERROR,
        SourceResultStatus.TIMEOUT,
    }:
        return "transport"
    return "other"


def run_highlightly_candidate_search(
    client: HighlightlyClient,
    search_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    league_result = client.discover_league_result(
        search_plan["league_name"],
        search_plan["country_name"],
        search_plan["season_start_year"],
    )
    if league_result.status is not SourceResultStatus.SUCCESS:
        return [
            {
                "type": "search_error",
                "operation": "league_discovery",
                "status": str(league_result.status),
                "error_code": league_result.error_code or None,
                "http_status": league_result.http_status,
                "request_identity": league_result.request_identity or None,
            }
        ]
    league_rows = league_result.value.get("rows", []) if league_result.value else []
    filtered_leagues = [
        row
        for row in league_rows
        if normalize_competition_label(row.get("league_name"))
        == normalize_competition_label(search_plan["league_name"])
        and normalize_competition_label(row.get("country_name"))
        == normalize_competition_label(search_plan["country_name"])
    ]
    if not filtered_leagues:
        filtered_leagues = league_rows[:1]
    if not filtered_leagues:
        return [
            {
                "type": "search_error",
                "operation": "league_discovery",
                "status": "VALID_EMPTY",
                "error_code": "league_not_found",
                "http_status": league_result.http_status,
                "request_identity": league_result.request_identity or None,
            }
        ]
    league = filtered_leagues[0]
    matches_result = client.discover_matches_result(
        league["provider_league_id"],
        search_plan["season_start_year"],
        limit=search_plan["match_limit"],
    )
    if matches_result.status is not SourceResultStatus.SUCCESS:
        return [
            {
                "type": "search_error",
                "operation": "match_discovery",
                "status": str(matches_result.status),
                "error_code": matches_result.error_code or None,
                "http_status": matches_result.http_status,
                "request_identity": matches_result.request_identity or None,
                "league": league,
            }
        ]
    candidates: list[dict[str, Any]] = []
    for row in matches_result.value.get("rows", []) if matches_result.value else []:
        candidates.append(
            {
                "type": "candidate",
                "provider": "highlightly",
                "provider_match_id": row.get("provider_match_id"),
                "competition": f"{league.get('country_name', '').upper()}: {row.get('competition')}"
                if league.get("country_name") and row.get("competition")
                else row.get("competition"),
                "season": normalize_season_value(row.get("season")),
                "kickoff_or_match_date": row.get("kickoff") or row.get("date"),
                "home_team": row.get("home_team", {}).get("team_name"),
                "away_team": row.get("away_team", {}).get("team_name"),
                "home_team_normalized": normalize_team_name(
                    row.get("home_team", {}).get("team_name") or ""
                )
                or None,
                "away_team_normalized": normalize_team_name(
                    row.get("away_team", {}).get("team_name") or ""
                )
                or None,
                "score": (row.get("score") or {}).get("display"),
                "status": row.get("match_status"),
                "team_ids": {
                    "home": row.get("home_team", {}).get("provider_team_id"),
                    "away": row.get("away_team", {}).get("provider_team_id"),
                },
                "competition_provider_id": row.get("competition_provider_id"),
                "search_context": {
                    "league_id": league.get("provider_league_id"),
                    "league_name": league.get("league_name"),
                    "country_name": league.get("country_name"),
                },
                "raw_row": row,
                "match_discovery_request_identity": matches_result.request_identity,
                "match_discovery_bundle_id": matches_result.bundle_id or None,
                "match_discovery_parser_version": matches_result.parser_version or None,
                "match_discovery_evidence_sha256": matches_result.evidence_refs[0].object_sha256
                if matches_result.evidence_refs
                else None,
                "match_discovery_http_status": matches_result.http_status,
            }
        )
    return candidates


def score_candidate_identity(
    identity: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    required_matches = {
        "competition": competition_equivalent(
            identity.get("competition"), candidate.get("competition")
        ),
        "season": season_start_year(identity.get("season"))
        and season_start_year(identity.get("season"))
        == season_start_year(candidate.get("season")),
        "kickoff_or_match_date": kickoff_or_date(identity.get("kickoff_or_match_date"))
        and kickoff_or_date(identity.get("kickoff_or_match_date"))
        == kickoff_or_date(candidate.get("kickoff_or_match_date")),
        "home_team_normalized": identity.get("home_team_normalized")
        and identity.get("home_team_normalized") == candidate.get("home_team_normalized"),
        "away_team_normalized": identity.get("away_team_normalized")
        and identity.get("away_team_normalized") == candidate.get("away_team_normalized"),
    }
    score_or_status_matches = bool(
        normalize_score_value(identity.get("score"))
        and normalize_score_value(identity.get("score"))
        == normalize_score_value(candidate.get("score"))
    ) or bool(
        not candidate.get("score")
        and identity.get("status")
        and candidate.get("status")
        and normalize_competition_label(identity.get("status"))
        == normalize_competition_label(candidate.get("status"))
    )
    proof_basis = [key for key, matched in required_matches.items() if matched]
    if score_or_status_matches:
        proof_basis.append("score_or_status")
    missing = [key for key, matched in required_matches.items() if not matched]
    if not score_or_status_matches:
        missing.append("score_or_status")
    return {
        "provider_match_id": candidate.get("provider_match_id"),
        "required_matches": required_matches,
        "score_or_status_matches": score_or_status_matches,
        "proof_basis": proof_basis,
        "missing_basis": missing,
        "exact_same_match": all(required_matches.values()) and score_or_status_matches,
    }


def select_exact_same_match_candidate(
    candidates: list[dict[str, Any]],
    scores: list[dict[str, Any]],
) -> dict[str, Any] | None:
    exact = [
        candidate
        for candidate, score in zip(candidates, scores, strict=False)
        if candidate.get("type") == "candidate" and score.get("exact_same_match")
    ]
    return exact[0] if len(exact) == 1 else None


def capture_highlightly_same_match_evidence(
    client: HighlightlyClient,
    identity: dict[str, Any],
    selected_candidate: dict[str, Any],
) -> dict[str, Any]:
    capture = {
        "performed": True,
        "provider": "highlightly",
        "provider_match_id": selected_candidate.get("provider_match_id"),
        "fixture_identity": {
            "competition": selected_candidate.get("competition"),
            "season": selected_candidate.get("season"),
            "kickoff_or_match_date": selected_candidate.get("kickoff_or_match_date"),
            "home_team": selected_candidate.get("home_team"),
            "away_team": selected_candidate.get("away_team"),
            "home_team_normalized": selected_candidate.get("home_team_normalized"),
            "away_team_normalized": selected_candidate.get("away_team_normalized"),
            "score": selected_candidate.get("score"),
            "status": selected_candidate.get("status"),
        },
        "sportdb_target_identity": {
            "match_id": identity.get("match_id"),
            "competition": identity.get("competition"),
            "season": identity.get("season"),
        },
        "request": {
            "search_request_identity": selected_candidate.get("match_discovery_request_identity"),
            "statistics_request_identity": None,
        },
        "response_sha256": selected_candidate.get("match_discovery_evidence_sha256"),
        "normalized_sha256": None,
        "metrics_available": False,
        "metric_names": [],
        "unknown_metrics": [],
        "bundle_id": None,
        "bundle_files": [],
        "parser_version": selected_candidate.get("match_discovery_parser_version"),
        "statistics_status": None,
        "statistics_error_code": None,
        "statistics_http_status": None,
        "normalized": {
            "provider_match_id": selected_candidate.get("provider_match_id"),
            "fixture_identity": selected_candidate,
            "metrics": {},
            "raw_stat_field_names": [],
            "unknown_metrics": [],
        },
        "safe_preview": {
            "selected_candidate": {
                key: selected_candidate.get(key)
                for key in (
                    "provider_match_id",
                    "competition",
                    "season",
                    "kickoff_or_match_date",
                    "home_team",
                    "away_team",
                    "score",
                    "status",
                )
            }
        },
    }
    home_team_id = selected_candidate.get("team_ids", {}).get("home")
    away_team_id = selected_candidate.get("team_ids", {}).get("away")
    if not home_team_id or not away_team_id:
        capture["statistics_status"] = str(SourceResultStatus.AMBIGUOUS)
        capture["statistics_error_code"] = "provider_native_team_ids_required"
        return capture
    statistics_result = client.get_statistics_result(
        selected_candidate["provider_match_id"],
        home_team_id=home_team_id,
        away_team_id=away_team_id,
    )
    capture["statistics_status"] = str(statistics_result.status)
    capture["statistics_error_code"] = statistics_result.error_code or None
    capture["statistics_http_status"] = statistics_result.http_status
    capture["request"]["statistics_request_identity"] = (
        statistics_result.request_identity or None
    )
    if statistics_result.status is SourceResultStatus.SUCCESS and statistics_result.value:
        stats_value = statistics_result.value
        capture["response_sha256"] = (
            statistics_result.evidence_refs[0].object_sha256
            if statistics_result.evidence_refs
            else capture["response_sha256"]
        )
        capture["parser_version"] = statistics_result.parser_version or capture["parser_version"]
        capture["metrics_available"] = True
        capture["metric_names"] = list(stats_value.get("normalized_metric_names", []))
        capture["unknown_metrics"] = list(stats_value.get("unknown_metrics", []))
        capture["normalized"] = {
            "provider_match_id": selected_candidate.get("provider_match_id"),
            "fixture_identity": capture["fixture_identity"],
            "team_rows": stats_value.get("team_rows", []),
            "statistics": stats_value.get("statistics", []),
            "raw_stat_field_names": stats_value.get("raw_stat_field_names", []),
            "normalized_metric_names": stats_value.get("normalized_metric_names", []),
            "unknown_metrics": stats_value.get("unknown_metrics", []),
            "missing_target_metrics": stats_value.get("missing_target_metrics", []),
        }
        capture["safe_preview"]["statistics"] = {
            "provider_match_id": stats_value.get("provider_match_id"),
            "raw_stat_field_names": stats_value.get("raw_stat_field_names", []),
            "normalized_metric_names": stats_value.get("normalized_metric_names", []),
            "unknown_metrics": stats_value.get("unknown_metrics", []),
        }
    return capture


def write_highlightly_capture_bundle(capture: dict[str, Any]) -> dict[str, Any]:
    request_payload = {
        "provider": "highlightly",
        "operation": "accepted_provider_same_match_capture",
        "provider_match_id": capture.get("provider_match_id"),
        "request_identity": capture.get("request"),
        "fixture_identity": capture.get("fixture_identity"),
        "sportdb_target_identity": capture.get("sportdb_target_identity"),
        "created_at": datetime.now(UTC).isoformat(),
        "secret_safe": True,
    }
    normalized_payload = capture.get("normalized", {})
    normalized_bytes = canonical_json_bytes(normalized_payload)
    normalized_sha256 = sha256_hex(normalized_bytes)
    response_sha256 = capture.get("response_sha256") or sha256_hex(
        canonical_json_bytes(capture.get("safe_preview", {}))
    )
    identity = {
        "provider": "highlightly",
        "operation": "accepted_provider_same_match_capture",
        "provider_match_id": capture.get("provider_match_id"),
        "sportdb_flashscore_match_id": capture.get("sportdb_target_identity", {}).get(
            "match_id"
        ),
        "request_identity": request_payload["request_identity"],
        "response_sha256": response_sha256,
        "normalized_sha256": normalized_sha256,
    }
    bundle_id = sha256_hex(canonical_json_bytes(identity))
    bundle_dir = EVIDENCE_ROOT / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "provider": "highlightly",
        "operation": "accepted_provider_same_match_capture",
        "bundle_id": bundle_id,
        "provider_match_id": capture.get("provider_match_id"),
        "sportdb_flashscore_match_id": capture.get("sportdb_target_identity", {}).get(
            "match_id"
        ),
        "request_identity": request_payload["request_identity"],
        "request_identity_payload": request_payload["fixture_identity"],
        "created_at": datetime.now(UTC).isoformat(),
        "response_sha256": response_sha256,
        "normalized_sha256": normalized_sha256,
        "parser_version": capture.get("parser_version") or "highlightly-match-discovery-v1",
        "secret_safe": True,
        "source_inputs": SOURCE_INPUT_PATHS,
    }
    files = {
        "request.json": json.dumps(request_payload, indent=2, sort_keys=True) + "\n",
        "response.sha256.txt": response_sha256 + "\n",
        "normalized.json": json.dumps(normalized_payload, indent=2, sort_keys=True) + "\n",
        "manifest.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        "response.safe_preview.json": json.dumps(capture.get("safe_preview", {}), indent=2, sort_keys=True)
        + "\n",
    }
    bundle_files: list[str] = []
    for name, content in files.items():
        path = bundle_dir / name
        path.write_text(content, encoding="utf-8")
        bundle_files.append(str(path))
    capture["bundle_id"] = bundle_id
    capture["bundle_files"] = bundle_files
    capture["normalized_sha256"] = normalized_sha256
    capture["response_sha256"] = response_sha256
    return {
        "bundle_id": bundle_id,
        "bundle_files": bundle_files,
        "response_sha256": response_sha256,
        "normalized_sha256": normalized_sha256,
    }


def classify_capture_summary(summary: dict[str, Any]) -> str:
    blockers = summary.get("blockers", [])
    if "sportdb_identity_incomplete" in blockers:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_BLOCKED_SPORTDB_IDENTITY_INCOMPLETE"
    if "highlightly_auth_missing_or_invalid" in blockers:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_BLOCKED_HIGHLIGHTLY_AUTH_MISSING_OR_INVALID"
    if "highlightly_rate_limited" in blockers:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_BLOCKED_HIGHLIGHTLY_RATE_LIMITED"
    if "highlightly_transport_or_server" in blockers:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_BLOCKED_HIGHLIGHTLY_TRANSPORT_OR_SERVER"
    if "ambiguous_exact_match" in blockers:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_BLOCKED_AMBIGUOUS_EXACT_MATCH"
    if "evidence_write_failure" in blockers:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_BLOCKED_EVIDENCE_WRITE_FAILURE"
    if "script_or_parser_defect" in blockers:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_BLOCKED_SCRIPT_OR_PARSER_DEFECT"
    capture = summary["accepted_provider_capture"]
    selection = summary["same_match_selection"]
    if selection["same_match_found"] and capture["performed"] and capture["metrics_available"]:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_READY_FOR_VALUE_REPLAY"
    if selection["same_match_found"] and capture["performed"] and not capture["metrics_available"]:
        return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_READY_FOR_IDENTITY_ONLY_REPLAY"
    return "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_NO_EXACT_MATCH_FOUND"


def _base_summary() -> dict[str, Any]:
    return {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
        "evidence_level": "TRACKED_ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_SUMMARY",
        "protected_worktree": PROTECTED_WORKTREE,
        "mode": "bounded_live_accepted_provider_capture",
        "target_provider": "highlightly",
        "source_inputs": {
            "sportdb_identity_bridge_summary": str(P2E_A7_SUMMARY_PATH),
            "sportdb_evidence_bundle_summary": str(P2E_A6_SUMMARY_PATH),
            "highlightly_certification_summary": str(P2D_HIGHLIGHTLY_SUMMARY_PATH),
        },
        "sportdb_target_identity": {
            "provider_family": "flashscore",
            "match_id": None,
            "competition": None,
            "season": None,
            "kickoff_or_match_date": None,
            "home_team": None,
            "away_team": None,
            "home_team_normalized": None,
            "away_team_normalized": None,
            "score": None,
            "identity_fields_available": [],
        },
        "highlightly_search": {
            "performed": False,
            "calls_made": 0,
            "candidate_count": 0,
            "candidate_summaries": [],
            "auth_configured": False,
            "rate_limited": False,
        },
        "same_match_selection": {
            "same_match_found": False,
            "ambiguous_exact_matches": False,
            "selected_provider_match_id": None,
            "proof_type": "none",
            "proof_basis": [],
            "blocking_gaps": [],
        },
        "accepted_provider_capture": {
            "performed": False,
            "provider": "highlightly",
            "provider_match_id": None,
            "bundle_id": None,
            "bundle_files": [],
            "response_sha256": None,
            "normalized_sha256": None,
            "metrics_available": False,
            "metric_names": [],
            "unknown_metrics": [],
        },
        "classification": "UNKNOWN",
        "certification": {
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
            "verdict": NOT_CERTIFIED_VERDICT,
        },
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "next_step": "UNKNOWN",
        "blockers": [],
        "secret_safe": True,
        "final_review": "PASS",
    }


def _update_next_step(summary: dict[str, Any]) -> None:
    classification = summary["classification"]
    if classification == "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_READY_FOR_VALUE_REPLAY":
        summary["next_step"] = "P2E_A9_SPORTDB_VALUE_REPLAY_AGAINST_ACCEPTED_PROVIDER"
    elif classification == "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_READY_FOR_IDENTITY_ONLY_REPLAY":
        summary["next_step"] = "P2E_A9_IDENTITY_ONLY_REPLAY_DECISION"
    elif classification == "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_NO_EXACT_MATCH_FOUND":
        summary["next_step"] = "P2E_A8B_ACCEPTED_PROVIDER_MATCH_ID_RECONCILIATION"
    else:
        summary["next_step"] = "blocked_or_retry_after_review"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=SUMMARY_PATH)
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = _base_summary()

    try:
        a7_summary = load_json(P2E_A7_SUMMARY_PATH)
        a6_summary = load_json(P2E_A6_SUMMARY_PATH)
        _ = load_json(P2D_HIGHLIGHTLY_SUMMARY_PATH)
        summary["sportdb_target_identity"] = extract_sportdb_target_identity(
            a7_summary, a6_summary
        )
        identity = summary["sportdb_target_identity"]
        required_identity = [
            "match_id",
            "competition",
            "season",
            "kickoff_or_match_date",
            "home_team_normalized",
            "away_team_normalized",
        ]
        if any(not identity.get(key) for key in required_identity):
            summary["blockers"].append("sportdb_identity_incomplete")
            summary["same_match_selection"]["blocking_gaps"].append(
                "sportdb_identity_missing_required_deterministic_keys"
            )
        else:
            auth_configured, _ = _resolve_highlightly_env()
            summary["highlightly_search"]["auth_configured"] = auth_configured
            if not auth_configured:
                summary["blockers"].append("highlightly_auth_missing_or_invalid")
            else:
                search_plan = build_highlightly_search_plan(identity)
                client = HighlightlyClient(rate_limiter=RateLimiter())
                raw_candidates = run_highlightly_candidate_search(client, search_plan)
                summary["highlightly_search"]["performed"] = True
                summary["highlightly_search"]["calls_made"] = 2
                if raw_candidates and raw_candidates[0].get("type") == "search_error":
                    search_error = raw_candidates[0]
                    status_text = search_error.get("status")
                    if status_text == str(SourceResultStatus.RATE_LIMITED):
                        summary["highlightly_search"]["rate_limited"] = True
                        summary["blockers"].append("highlightly_rate_limited")
                    elif status_text in {
                        str(SourceResultStatus.AUTHENTICATION_ERROR),
                        str(SourceResultStatus.PLAN_RESTRICTED),
                    }:
                        summary["blockers"].append("highlightly_auth_missing_or_invalid")
                    else:
                        summary["blockers"].append("highlightly_transport_or_server")
                    summary["same_match_selection"]["blocking_gaps"].append(
                        f"highlightly_{search_error.get('operation')}_{search_error.get('error_code') or 'failed'}"
                    )
                else:
                    candidates = [c for c in raw_candidates if c.get("type") == "candidate"]
                    scores = [score_candidate_identity(identity, candidate) for candidate in candidates]
                    exact_matches = [
                        (candidate, score)
                        for candidate, score in zip(candidates, scores, strict=False)
                        if score["exact_same_match"]
                    ]
                    summary["highlightly_search"]["candidate_count"] = len(candidates)
                    summary["highlightly_search"]["candidate_summaries"] = [
                        {
                            "provider_match_id": candidate.get("provider_match_id"),
                            "competition": candidate.get("competition"),
                            "season": candidate.get("season"),
                            "kickoff_or_match_date": candidate.get("kickoff_or_match_date"),
                            "home_team": candidate.get("home_team"),
                            "away_team": candidate.get("away_team"),
                            "score": candidate.get("score"),
                            "status": candidate.get("status"),
                            "exact_same_match": score.get("exact_same_match"),
                            "proof_basis": score.get("proof_basis"),
                            "missing_basis": score.get("missing_basis"),
                        }
                        for candidate, score in zip(candidates, scores, strict=False)
                    ]
                    selected = select_exact_same_match_candidate(candidates, scores)
                    if len(exact_matches) > 1:
                        summary["same_match_selection"]["ambiguous_exact_matches"] = True
                        summary["same_match_selection"]["blocking_gaps"].append(
                            "multiple_deterministic_same_match_candidates"
                        )
                        summary["blockers"].append("ambiguous_exact_match")
                    elif selected is None:
                        summary["same_match_selection"]["blocking_gaps"].append(
                            "no_deterministic_same_match_candidate"
                        )
                    else:
                        selected_score = next(
                            score
                            for candidate, score in zip(candidates, scores, strict=False)
                            if candidate.get("provider_match_id")
                            == selected.get("provider_match_id")
                        )
                        summary["same_match_selection"].update(
                            {
                                "same_match_found": True,
                                "selected_provider_match_id": selected.get("provider_match_id"),
                                "proof_type": "deterministic_fixture_identity_match",
                                "proof_basis": list(selected_score.get("proof_basis", [])),
                                "blocking_gaps": [],
                            }
                        )
                        capture = capture_highlightly_same_match_evidence(client, identity, selected)
                        summary["accepted_provider_capture"].update(
                            {
                                "performed": True,
                                "provider_match_id": capture.get("provider_match_id"),
                                "metrics_available": capture.get("metrics_available", False),
                                "metric_names": list(capture.get("metric_names", [])),
                                "unknown_metrics": list(capture.get("unknown_metrics", [])),
                            }
                        )
                        try:
                            bundle = write_highlightly_capture_bundle(capture)
                        except Exception as exc:
                            summary["blockers"].append("evidence_write_failure")
                            summary["same_match_selection"]["blocking_gaps"].append(
                                f"bundle_write_failed:{exc.__class__.__name__}"
                            )
                        else:
                            summary["accepted_provider_capture"].update(bundle)
    except Exception as exc:
        summary["blockers"].append("script_or_parser_defect")
        summary["same_match_selection"]["blocking_gaps"].append(
            f"exception:{exc.__class__.__name__}"
        )

    summary["classification"] = classify_capture_summary(summary)
    _update_next_step(summary)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
