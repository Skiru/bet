#!/usr/bin/env python3
"""Offline SportDB identity bridge and value replay assessment."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

PHASE_ID = "P2E_A7_SPORTDB_IDENTITY_BRIDGE_AND_VALUE_REPLAY"
PROMPT_VERSION = "v3_masterpiece_protected_worktree_identity_bridge_replay"
PREVIOUS_ACCEPTED_SHA = "a9a31d1121030ade20b9dbddafd7cf861bdb887a"
PROTECTED_WORKTREE = "/Users/mkoziol/projects/bet-multisport-enrichment-v1"
SUMMARY_PATH = "certification/football/p2e_sportdb_identity_bridge_value_replay_summary.json"
P2E_A6_SUMMARY_PATH = Path("certification/football/p2e_sportdb_evidence_bundle_summary.json")
NOT_CERTIFIED_VERDICT = "NOT_CERTIFIED_IDENTITY_BRIDGE_VALUE_REPLAY_ONLY"
ALLOWED_CLASSIFICATIONS = {
    "SPORTDB_IDENTITY_BRIDGE_READY_FOR_SCOPE_LIMITED_CERTIFICATION_PLAN",
    "SPORTDB_IDENTITY_BRIDGE_READY_BUT_VALUE_REPLAY_BLOCKED_NO_ACCEPTED_SAME_MATCH_EVIDENCE",
    "SPORTDB_IDENTITY_BRIDGE_BLOCKED_MISSING_LOCAL_SPORTDB_EVIDENCE_BUNDLES",
    "SPORTDB_IDENTITY_BRIDGE_BLOCKED_INVALID_P2E_A6_SUMMARY",
    "SPORTDB_IDENTITY_BRIDGE_BLOCKED_NO_SPORTDB_MATCH_IDENTITY",
    "SPORTDB_IDENTITY_BRIDGE_BLOCKED_ACCEPTED_PROVIDER_EVIDENCE_ABSENT",
    "SPORTDB_IDENTITY_BRIDGE_BLOCKED_SCRIPT_OR_PARSER_DEFECT",
}
REQUIRED_OPERATIONS = {
    "competition_results",
    "competition_standings",
    "match_events",
    "match_lineups",
    "match_stats",
}
CANONICAL_METRICS = {
    "expected_goals": {"kind": "decimal", "tolerance": 0.01},
    "shots_on_goal": {"kind": "integer", "tolerance": 0.0},
    "shots_off_target": {"kind": "integer", "tolerance": 0.0},
    "blocked_shots": {"kind": "integer", "tolerance": 0.0},
    "total_shots": {"kind": "integer", "tolerance": 0.0},
    "corners": {"kind": "integer", "tolerance": 0.0},
    "yellow_cards": {"kind": "integer", "tolerance": 0.0},
    "red_cards": {"kind": "integer", "tolerance": 0.0},
    "fouls": {"kind": "integer", "tolerance": 0.0},
    "offsides": {"kind": "integer", "tolerance": 0.0},
    "possession": {"kind": "percentage", "tolerance": 0.5},
    "goalkeeper_saves": {"kind": "integer", "tolerance": 0.0},
    "total_passes": {"kind": "integer", "tolerance": 0.0},
    "successful_passes": {"kind": "integer", "tolerance": 0.0},
}
SPORTDB_STAT_NAME_MAP = {
    "expected goals (xg)": "expected_goals",
    "shots on target": "shots_on_goal",
    "shots off target": "shots_off_target",
    "blocked shots": "blocked_shots",
    "total shots": "total_shots",
    "corner kicks": "corners",
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
    "fouls": "fouls",
    "offsides": "offsides",
    "ball possession": "possession",
    "goalkeeper saves": "goalkeeper_saves",
    "passes": "total_passes",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_p2e_a6_summary(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("phase_id") != "P2E_A6_SPORTDB_EVIDENCE_BUNDLE_AND_REPLAY_CONTRACT":
        errors.append("phase_id_mismatch")
    operations = data.get("operations")
    if not isinstance(operations, dict):
        errors.append("operations_missing")
        return errors
    missing_operations = sorted(REQUIRED_OPERATIONS - set(operations))
    if missing_operations:
        errors.append("missing_operations:" + ",".join(missing_operations))
    for op_name in REQUIRED_OPERATIONS & set(operations):
        op = operations.get(op_name, {})
        bundle_files = op.get("bundle_files")
        if not isinstance(bundle_files, list) or not bundle_files:
            errors.append(f"bundle_files_missing:{op_name}")
        if op.get("bundle_id") in (None, ""):
            errors.append(f"bundle_id_missing:{op_name}")
        if op.get("request_identity") in (None, ""):
            errors.append(f"request_identity_missing:{op_name}")
    return errors


def load_sportdb_operation_bundles(summary: dict[str, Any]) -> dict[str, Any]:
    bundles: dict[str, Any] = {}
    for op_name, op_data in summary.get("operations", {}).items():
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
                op_bundle["files"][path.name] = json.loads(load_text(path))
            else:
                op_bundle["files"][path.name] = load_text(path)
        bundles[op_name] = op_bundle
    return bundles


def normalize_team_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = re.sub(r"\butd\b", "united", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token not in {"fc", "cf", "club"}]
    return " ".join(tokens)


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


def extract_sportdb_match_identity(bundles: dict[str, Any]) -> dict[str, Any]:
    match_events = bundles.get("match_events", {})
    match_stats = bundles.get("match_stats", {})
    competition_results = bundles.get("competition_results", {})
    mapping_summary = bundles.get("__aux__", {}).get("mapping_summary", {})

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
    data = events_normalized.get("raw_result", {}).get("data", {}) if isinstance(events_normalized, dict) else {}
    finished_probe = mapping_summary.get("finished_match_probe", {})
    selected_raw = finished_probe.get("selected_match_raw", {})

    score = None
    status = None
    match_id = request_bits.get("match_id") or events_normalized.get("provider_match_id")
    for row in results_normalized if isinstance(results_normalized, list) else []:
        if row.get("provider_match_id") == match_id:
            score = row.get("score")
            status = row.get("status")
            break

    competition = request_bits.get("competition")
    if selected_raw.get("tournamentName"):
        competition = selected_raw["tournamentName"]

    kickoff = selected_raw.get("startDateTimeUtc") or selected_raw.get("startUtime")
    home_team = data.get("homeName") or selected_raw.get("homeName") or selected_raw.get("homeFirstName")
    away_team = data.get("awayName") or selected_raw.get("awayName") or selected_raw.get("awayFirstName")
    identity = {
        "provider_family": "flashscore",
        "match_id": match_id,
        "competition": competition,
        "season": request_bits.get("season") or finished_probe.get("selected_season"),
        "kickoff_or_match_date": kickoff,
        "home_team": home_team,
        "away_team": away_team,
        "home_team_normalized": normalize_team_name(home_team or "") or None,
        "away_team_normalized": normalize_team_name(away_team or "") or None,
        "score": score,
        "status": status or selected_raw.get("eventStage") or finished_probe.get("selected_match_status"),
        "identity_fields_available": [],
    }
    identity["identity_fields_available"] = [
        key for key in (
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
        ) if identity.get(key)
    ]
    return identity


def extract_highlightly_candidate_from_report(path: Path, data: Any) -> dict[str, Any]:
    highlightly = data.get("providers", {}).get("highlightly", {}) if isinstance(data, dict) else {}
    live_probe = highlightly.get("live_probe", {}) if isinstance(highlightly, dict) else {}
    competition = None
    season = None
    matches_url = live_probe.get("matches", {}).get("url")
    if isinstance(matches_url, str):
        league_match = re.search(r"leagueId=(\d+)", matches_url)
        season_match = re.search(r"season=(\d{4})", matches_url)
        competition = f"highlightly_league_id:{league_match.group(1)}" if league_match else None
        season = season_match.group(1) if season_match else None
    return {
        "path": str(path),
        "provider": "highlightly",
        "provider_match_id": live_probe.get("matches", {}).get("match_id") or highlightly.get("evidence", [{}])[1].get("match_id") if isinstance(highlightly.get("evidence"), list) and len(highlightly.get("evidence")) > 1 else None,
        "competition": competition,
        "season": season,
        "kickoff_or_match_date": None,
        "home_team": None,
        "away_team": None,
        "home_team_normalized": None,
        "away_team_normalized": None,
        "score": None,
        "status": None,
        "metrics": {},
        "unknown_metrics": [],
        "semantics": {},
        "proof_hints": [],
    }


def extract_candidate_match_identity(path: Path, data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and data.get("provider") == "highlightly":
        return {
            "path": str(path),
            "provider": "highlightly",
            "provider_match_id": data.get("provider_native_ids", {}).get("match_id"),
            "competition": data.get("scope") or data.get("certified_scope"),
            "season": None,
            "kickoff_or_match_date": None,
            "home_team": None,
            "away_team": None,
            "home_team_normalized": None,
            "away_team_normalized": None,
            "score": None,
            "status": None,
            "metrics": {},
            "unknown_metrics": list(data.get("raw_stat_field_names", []) or []),
            "semantics": {},
            "proof_hints": [],
        }
    if isinstance(data, dict) and isinstance(data.get("providers"), dict) and "highlightly" in data["providers"]:
        return extract_highlightly_candidate_from_report(path, data)
    return {
        "path": str(path),
        "provider": None,
        "provider_match_id": None,
        "competition": None,
        "season": None,
        "kickoff_or_match_date": None,
        "home_team": None,
        "away_team": None,
        "home_team_normalized": None,
        "away_team_normalized": None,
        "score": None,
        "status": None,
        "metrics": {},
        "unknown_metrics": [],
        "semantics": {},
        "proof_hints": [],
    }


def discover_accepted_provider_evidence(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not root.exists():
        return candidates
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        candidate = extract_candidate_match_identity(path, data)
        if candidate.get("provider") in {"highlightly", "api-football", "espn", "football-data"}:
            candidates.append(candidate)
    return candidates


def values_equal(left: Any, right: Any) -> bool:
    return left is not None and right is not None and left == right


def kickoff_or_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if re.fullmatch(r"\d{10}", text):
        return text
    if "T" in text:
        return text.split("T", 1)[0]
    return text[:10]


def compare_identity(sportdb_identity: dict[str, Any], candidate_identity: dict[str, Any]) -> dict[str, Any]:
    proof_basis: list[str] = []
    proof_type = "none"
    same_match_proof_available = False
    if sportdb_identity.get("match_id") and candidate_identity.get("bridge_map"):
        bridge_map = candidate_identity["bridge_map"]
        if bridge_map.get("sportdb_match_id") == sportdb_identity["match_id"] and bridge_map.get("accepted_provider_match_id") == candidate_identity.get("provider_match_id"):
            proof_type = "exact_provider_id_bridge"
            proof_basis = [
                f"sportdb_match_id:{sportdb_identity['match_id']}",
                f"accepted_provider_match_id:{candidate_identity['provider_match_id']}",
            ]
            same_match_proof_available = True

    required_identity = {
        "competition": bool(sportdb_identity.get("competition") and candidate_identity.get("competition") and sportdb_identity.get("competition") == candidate_identity.get("competition")),
        "season": bool(sportdb_identity.get("season") and candidate_identity.get("season") and sportdb_identity.get("season") == candidate_identity.get("season")),
        "kickoff_or_match_date": bool(kickoff_or_date(sportdb_identity.get("kickoff_or_match_date")) and kickoff_or_date(sportdb_identity.get("kickoff_or_match_date")) == kickoff_or_date(candidate_identity.get("kickoff_or_match_date"))),
        "home_team_normalized": values_equal(sportdb_identity.get("home_team_normalized"), candidate_identity.get("home_team_normalized")),
        "away_team_normalized": values_equal(sportdb_identity.get("away_team_normalized"), candidate_identity.get("away_team_normalized")),
    }
    score_or_status_matches = (
        values_equal(sportdb_identity.get("score"), candidate_identity.get("score"))
        or (
            not candidate_identity.get("score")
            and values_equal(sportdb_identity.get("status"), candidate_identity.get("status"))
        )
    )
    if not same_match_proof_available and all(required_identity.values()) and score_or_status_matches:
        proof_type = "deterministic_fixture_identity_match"
        proof_basis = [key for key, matched in required_identity.items() if matched]
        proof_basis.append("score_or_status")
        same_match_proof_available = True

    if not same_match_proof_available and candidate_identity.get("explicit_same_fixture"):
        explicit = candidate_identity["explicit_same_fixture"]
        if all(
            values_equal(sportdb_identity.get(key), explicit.get(key))
            for key in ("competition", "season", "score")
        ) and values_equal(sportdb_identity.get("home_team_normalized"), explicit.get("home_team_normalized")) and values_equal(sportdb_identity.get("away_team_normalized"), explicit.get("away_team_normalized")) and kickoff_or_date(sportdb_identity.get("kickoff_or_match_date")) == kickoff_or_date(explicit.get("kickoff_or_match_date")):
            proof_type = "existing_accepted_replay_bundle_same_fixture"
            proof_basis = ["explicit_same_fixture_bundle"]
            same_match_proof_available = True

    return {
        "candidate_path": candidate_identity.get("path"),
        "provider": candidate_identity.get("provider"),
        "same_match_proof_available": same_match_proof_available,
        "proof_type": proof_type,
        "proof_basis": proof_basis,
        "required_identity_matches": required_identity,
        "score_or_status_matches": score_or_status_matches,
    }


def extract_sportdb_metrics(bundles: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    metrics: dict[str, Any] = {}
    unknown_metrics: list[str] = []
    normalized = bundles.get("match_stats", {}).get("files", {}).get("normalized.json", {})
    raw_result = normalized.get("raw_result", {}) if isinstance(normalized, dict) else {}
    periods = raw_result.get("data", []) if isinstance(raw_result, dict) else []
    match_period = None
    for period in periods:
        if period.get("period") == "Match":
            match_period = period
            break
    if not isinstance(match_period, dict):
        return metrics, unknown_metrics
    for stat in match_period.get("stats", []):
        raw_name = (stat.get("statName") or "").strip()
        canonical = SPORTDB_STAT_NAME_MAP.get(raw_name.lower())
        if canonical is None:
            if raw_name and raw_name not in unknown_metrics:
                unknown_metrics.append(raw_name)
            continue
        if canonical == "total_passes":
            home_value, home_secondary = parse_stat_value(stat.get("homeValue"))
            away_value, away_secondary = parse_stat_value(stat.get("awayValue"))
            metrics[canonical] = {"home": home_secondary or home_value, "away": away_secondary or away_value}
            if home_value is not None and away_value is not None:
                metrics["successful_passes"] = {"home": home_value, "away": away_value}
            continue
        home_value, _ = parse_stat_value(stat.get("homeValue"))
        away_value, _ = parse_stat_value(stat.get("awayValue"))
        metrics[canonical] = {"home": home_value, "away": away_value}
    return metrics, unknown_metrics


def parse_stat_value(value: Any) -> tuple[Any, Any]:
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return value, None
    text = str(value).strip()
    if not text:
        return None, None
    pair_match = re.match(r"^(\d+(?:\.\d+)?)%?\s*\((\d+)/(\d+)\)$", text)
    if pair_match:
        primary = float(pair_match.group(1)) if "." in pair_match.group(1) else int(pair_match.group(1))
        secondary = int(pair_match.group(2))
        return primary, secondary
    percentage_match = re.match(r"^(\d+(?:\.\d+)?)%$", text)
    if percentage_match:
        return float(percentage_match.group(1)), None
    number_match = re.match(r"^-?\d+(?:\.\d+)?$", text)
    if number_match:
        return float(text) if "." in text else int(text), None
    return text, None


def build_identity_bridge_assessment(
    sportdb_identity: dict[str, Any],
    accepted_provider_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    best_match: dict[str, Any] | None = None
    comparisons: list[dict[str, Any]] = []
    for candidate in accepted_provider_candidates:
        comparison = compare_identity(sportdb_identity, candidate)
        comparisons.append(comparison)
        if comparison["same_match_proof_available"] and best_match is None:
            best_match = {**candidate, "comparison": comparison}

    blocking_gaps: list[str] = []
    if not sportdb_identity.get("match_id"):
        blocking_gaps.append("sportdb_flashscore_match_id_missing")
    if not sportdb_identity.get("home_team_normalized") or not sportdb_identity.get("away_team_normalized"):
        blocking_gaps.append("sportdb_team_identity_incomplete")
    if not sportdb_identity.get("kickoff_or_match_date"):
        blocking_gaps.append("sportdb_kickoff_timestamp_or_match_date_missing")
    if not accepted_provider_candidates:
        blocking_gaps.append("accepted_provider_evidence_absent")
    elif best_match is None:
        blocking_gaps.append("accepted_provider_same_match_proof_absent")

    comparison = best_match.get("comparison") if best_match else None
    return {
        "same_match_proof_available": bool(comparison and comparison["same_match_proof_available"]),
        "proof_type": comparison["proof_type"] if comparison else "none",
        "proof_basis": comparison["proof_basis"] if comparison else [],
        "direct_value_replay_allowed": bool(comparison and comparison["same_match_proof_available"]),
        "blocking_gaps": blocking_gaps,
        "recommended_next_bridge_keys": [
            "competition_scope",
            "season",
            "kickoff_timestamp_or_match_date",
            "home_team_normalized",
            "away_team_normalized",
            "score",
            "accepted_provider_match_id",
            "sportdb_flashscore_match_id",
        ],
        "selected_candidate_path": best_match.get("path") if best_match else None,
        "selected_candidate_provider": best_match.get("provider") if best_match else None,
        "candidate_comparisons": comparisons,
    }


def compare_metric_values(metric_name: str, sportdb_value: Any, candidate_value: Any) -> dict[str, Any]:
    rule = CANONICAL_METRICS[metric_name]
    if sportdb_value is None or candidate_value is None:
        return {
            "metric": metric_name,
            "matched": False,
            "reason": "missing_side_value",
            "semantic_gap": True,
        }
    if not isinstance(sportdb_value, (int, float)) or not isinstance(candidate_value, (int, float)):
        return {
            "metric": metric_name,
            "matched": False,
            "reason": "unknown_units_or_types",
            "semantic_gap": True,
        }
    delta = abs(float(sportdb_value) - float(candidate_value))
    matched = delta <= (rule["tolerance"] + 1e-9)
    return {
        "metric": metric_name,
        "matched": matched,
        "delta": delta,
        "tolerance": rule["tolerance"],
        "semantic_gap": False,
    }


def build_value_replay(
    sportdb_identity: dict[str, Any],
    sportdb_metrics: dict[str, Any],
    sportdb_unknown_metrics: list[str],
    accepted_provider_candidates: list[dict[str, Any]],
    bridge_assessment: dict[str, Any],
) -> dict[str, Any]:
    if not bridge_assessment.get("direct_value_replay_allowed"):
        return {
            "performed": False,
            "accepted_provider": None,
            "accepted_provider_evidence_path": None,
            "metrics_compared": [],
            "metrics_matched": [],
            "metric_mismatches": [],
            "semantic_gaps": [],
            "unknown_metrics_preserved": sorted(set(sportdb_unknown_metrics)),
        }

    selected = None
    for candidate in accepted_provider_candidates:
        if candidate.get("path") == bridge_assessment.get("selected_candidate_path"):
            selected = candidate
            break
    if selected is None:
        return {
            "performed": False,
            "accepted_provider": None,
            "accepted_provider_evidence_path": None,
            "metrics_compared": [],
            "metrics_matched": [],
            "metric_mismatches": [],
            "semantic_gaps": [],
            "unknown_metrics_preserved": sorted(set(sportdb_unknown_metrics)),
        }

    metrics_compared: list[str] = []
    metrics_matched: list[str] = []
    metric_mismatches: list[dict[str, Any]] = []
    semantic_gaps: list[dict[str, Any]] = []
    candidate_metrics = selected.get("metrics", {})
    semantics = selected.get("semantics", {})
    for metric_name in sorted(set(sportdb_metrics) & set(candidate_metrics) & set(CANONICAL_METRICS)):
        sportdb_sides = sportdb_metrics[metric_name]
        candidate_sides = candidate_metrics[metric_name]
        metrics_compared.append(metric_name)
        if semantics.get(metric_name) == "unknown":
            semantic_gaps.append({
                "metric": metric_name,
                "reason": "provider_semantics_unknown",
            })
            continue
        side_results = [
            compare_metric_values(metric_name, sportdb_sides.get("home"), candidate_sides.get("home")),
            compare_metric_values(metric_name, sportdb_sides.get("away"), candidate_sides.get("away")),
        ]
        if any(result["semantic_gap"] for result in side_results):
            semantic_gaps.append({
                "metric": metric_name,
                "reason": side_results[0].get("reason") or side_results[1].get("reason"),
            })
            continue
        if all(result["matched"] for result in side_results):
            metrics_matched.append(metric_name)
            continue
        metric_mismatches.append({
            "metric": metric_name,
            "sportdb": sportdb_sides,
            "accepted_provider": candidate_sides,
            "home_delta": side_results[0].get("delta"),
            "away_delta": side_results[1].get("delta"),
        })

    return {
        "performed": True,
        "accepted_provider": selected.get("provider"),
        "accepted_provider_evidence_path": selected.get("path"),
        "metrics_compared": metrics_compared,
        "metrics_matched": metrics_matched,
        "metric_mismatches": metric_mismatches,
        "semantic_gaps": semantic_gaps,
        "unknown_metrics_preserved": sorted(set(sportdb_unknown_metrics + list(selected.get("unknown_metrics", [])))),
    }


def classify_identity_bridge_replay(
    validation_errors: list[str],
    sportdb_identity: dict[str, Any],
    accepted_provider_candidates: list[dict[str, Any]],
    bridge_assessment: dict[str, Any],
    value_replay: dict[str, Any],
) -> str:
    if validation_errors:
        return "SPORTDB_IDENTITY_BRIDGE_BLOCKED_INVALID_P2E_A6_SUMMARY"
    if not sportdb_identity.get("match_id") or not sportdb_identity.get("home_team_normalized") or not sportdb_identity.get("away_team_normalized"):
        return "SPORTDB_IDENTITY_BRIDGE_BLOCKED_NO_SPORTDB_MATCH_IDENTITY"
    if not accepted_provider_candidates:
        return "SPORTDB_IDENTITY_BRIDGE_BLOCKED_ACCEPTED_PROVIDER_EVIDENCE_ABSENT"
    if bridge_assessment.get("same_match_proof_available") and bridge_assessment.get("direct_value_replay_allowed") and value_replay.get("performed") and value_replay.get("metrics_compared") and not value_replay.get("metric_mismatches"):
        return "SPORTDB_IDENTITY_BRIDGE_READY_FOR_SCOPE_LIMITED_CERTIFICATION_PLAN"
    if not bridge_assessment.get("same_match_proof_available") and not bridge_assessment.get("direct_value_replay_allowed"):
        return "SPORTDB_IDENTITY_BRIDGE_READY_BUT_VALUE_REPLAY_BLOCKED_NO_ACCEPTED_SAME_MATCH_EVIDENCE"
    return "SPORTDB_IDENTITY_BRIDGE_BLOCKED_SCRIPT_OR_PARSER_DEFECT"


def build_summary(out_path: Path) -> dict[str, Any]:
    p2e_a6_summary = load_json(P2E_A6_SUMMARY_PATH)
    validation_errors = validate_p2e_a6_summary(p2e_a6_summary)
    bundles = load_sportdb_operation_bundles(p2e_a6_summary)
    bundles.setdefault("__aux__", {})["mapping_summary"] = load_json(
        Path("certification/football/p2e_sportdb_mcp_football_mapping_summary.json")
    )
    sportdb_identity = extract_sportdb_match_identity(bundles)
    sportdb_metrics, sportdb_unknown_metrics = extract_sportdb_metrics(bundles)

    roots = [
        Path("certification/football"),
        Path("reports"),
        Path("data/evidence"),
        Path("betting/data/evidence"),
    ]
    accepted_provider_candidates: list[dict[str, Any]] = []
    scanned_roots: list[str] = []
    seen_paths: set[str] = set()
    for root in roots:
        scanned_roots.append(str(root))
        for candidate in discover_accepted_provider_evidence(root):
            candidate_path = candidate.get("path")
            if candidate_path and candidate_path not in seen_paths:
                seen_paths.add(candidate_path)
                accepted_provider_candidates.append(candidate)

    bridge_assessment = build_identity_bridge_assessment(sportdb_identity, accepted_provider_candidates)
    value_replay = build_value_replay(
        sportdb_identity,
        sportdb_metrics,
        sportdb_unknown_metrics,
        accepted_provider_candidates,
        bridge_assessment,
    )
    classification = classify_identity_bridge_replay(
        validation_errors,
        sportdb_identity,
        accepted_provider_candidates,
        bridge_assessment,
        value_replay,
    )
    next_step = {
        "SPORTDB_IDENTITY_BRIDGE_READY_FOR_SCOPE_LIMITED_CERTIFICATION_PLAN": "P2E_A8_SPORTDB_SCOPE_LIMITED_CERTIFICATION_PLAN",
        "SPORTDB_IDENTITY_BRIDGE_READY_BUT_VALUE_REPLAY_BLOCKED_NO_ACCEPTED_SAME_MATCH_EVIDENCE": "P2E_A8_ACCEPTED_PROVIDER_SAME_MATCH_REPLAY_CAPTURE",
    }.get(classification, "blocked_or_retry_after_review")

    summary = {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
        "evidence_level": "TRACKED_IDENTITY_BRIDGE_VALUE_REPLAY_SUMMARY",
        "provider": "sportdb",
        "mode": "replay_only_no_live_provider_calls",
        "protected_worktree": PROTECTED_WORKTREE,
        "source_inputs": {
            "sportdb_evidence_bundle_summary": str(P2E_A6_SUMMARY_PATH),
            "sportdb_evidence_bundles_local_verified": True,
            "accepted_provider_evidence_roots_scanned": scanned_roots,
        },
        "sportdb_identity": {
            "provider_family": sportdb_identity.get("provider_family", "flashscore"),
            "match_id": sportdb_identity.get("match_id"),
            "competition": sportdb_identity.get("competition"),
            "season": sportdb_identity.get("season"),
            "kickoff_or_match_date": sportdb_identity.get("kickoff_or_match_date"),
            "home_team": sportdb_identity.get("home_team"),
            "away_team": sportdb_identity.get("away_team"),
            "home_team_normalized": sportdb_identity.get("home_team_normalized"),
            "away_team_normalized": sportdb_identity.get("away_team_normalized"),
            "score": sportdb_identity.get("score"),
            "identity_fields_available": sportdb_identity.get("identity_fields_available", []),
        },
        "accepted_provider_candidates": accepted_provider_candidates,
        "identity_bridge_assessment": {
            key: bridge_assessment[key]
            for key in (
                "same_match_proof_available",
                "proof_type",
                "proof_basis",
                "direct_value_replay_allowed",
                "blocking_gaps",
                "recommended_next_bridge_keys",
            )
        },
        "value_replay": value_replay,
        "classification": classification,
        "certification": {
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
            "verdict": NOT_CERTIFIED_VERDICT,
        },
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "next_step": next_step,
        "blockers": validation_errors,
        "secret_safe": True,
        "final_review": "PASS",
    }
    if classification not in ALLOWED_CLASSIFICATIONS:
        summary["classification"] = "SPORTDB_IDENTITY_BRIDGE_BLOCKED_SCRIPT_OR_PARSER_DEFECT"
        summary["next_step"] = "blocked_or_retry_after_review"
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=SUMMARY_PATH)
    args = parser.parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = build_summary(out_path)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
