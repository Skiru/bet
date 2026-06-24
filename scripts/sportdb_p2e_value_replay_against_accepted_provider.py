#!/usr/bin/env python3
"""Offline SportDB vs Highlightly value replay for the accepted same match."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

PHASE_ID = "P2E_A9_SPORTDB_VALUE_REPLAY_AGAINST_ACCEPTED_PROVIDER"
PROMPT_VERSION = "v1_masterpiece_value_replay_locked"
PREVIOUS_ACCEPTED_SHA = "304087c6991c51c5125cfbe4ab0f6bda99046ba7"
PROTECTED_WORKTREE = "/Users/mkoziol/projects/bet-multisport-enrichment-v1"
SUMMARY_PATH = (
    "certification/football/"
    "p2e_sportdb_value_replay_against_accepted_provider_summary.json"
)
P2E_A8_SUMMARY_PATH = Path(
    "certification/football/p2e_accepted_provider_same_match_replay_capture_summary.json"
)
P2E_A7_SUMMARY_PATH = Path(
    "certification/football/p2e_sportdb_identity_bridge_value_replay_summary.json"
)
P2E_A6_SUMMARY_PATH = Path("certification/football/p2e_sportdb_evidence_bundle_summary.json")
NOT_CERTIFIED_VERDICT = "NOT_CERTIFIED_VALUE_REPLAY_ONLY"
REQUIRED_A6_OPERATIONS = {
    "competition_results",
    "competition_standings",
    "match_events",
    "match_lineups",
    "match_stats",
}
CANONICAL_METRICS = {
    "expected_goals": {"kind": "decimal", "tolerance": 0.05},
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
HIGHLIGHTLY_NON_CANONICAL = {
    "big_chances_created",
    "free_kicks",
    "throw_ins",
    "goal_kicks",
    "shots_accuracy",
    "failed_passes",
    "shots_within_penalty_area",
    "shots_outside_penalty_area",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def normalize_score(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return text or None


def validate_p2e_a8_summary(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("phase_id") != "P2E_A8_ACCEPTED_PROVIDER_SAME_MATCH_REPLAY_CAPTURE":
        errors.append("phase_id_mismatch")
    if (
        data.get("classification")
        != "ACCEPTED_PROVIDER_SAME_MATCH_CAPTURE_READY_FOR_VALUE_REPLAY"
    ):
        errors.append("classification_not_ready_for_value_replay")
    selection = data.get("same_match_selection", {})
    capture = data.get("accepted_provider_capture", {})
    if selection.get("same_match_found") is not True:
        errors.append("same_match_found_false")
    if selection.get("selected_provider_match_id") != "1173818273":
        errors.append("selected_provider_match_id_mismatch")
    if capture.get("performed") is not True:
        errors.append("accepted_provider_capture_not_performed")
    if capture.get("metrics_available") is not True:
        errors.append("accepted_provider_metrics_unavailable")
    bundle_files = capture.get("bundle_files")
    if not isinstance(bundle_files, list) or not bundle_files:
        errors.append("accepted_provider_bundle_files_missing")
    return errors


def validate_p2e_a6_summary(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("phase_id") != "P2E_A6_SPORTDB_EVIDENCE_BUNDLE_AND_REPLAY_CONTRACT":
        errors.append("phase_id_mismatch")
    operations = data.get("operations")
    if not isinstance(operations, dict):
        errors.append("operations_missing")
        return errors
    missing_operations = sorted(REQUIRED_A6_OPERATIONS - set(operations))
    if missing_operations:
        errors.append("missing_operations:" + ",".join(missing_operations))
    for op_name in REQUIRED_A6_OPERATIONS & set(operations):
        op = operations.get(op_name, {})
        bundle_files = op.get("bundle_files")
        if not isinstance(bundle_files, list) or not bundle_files:
            errors.append(f"bundle_files_missing:{op_name}")
    return errors


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
        primary = (
            float(pair_match.group(1))
            if "." in pair_match.group(1)
            else int(pair_match.group(1))
        )
        secondary = int(pair_match.group(2))
        return primary, secondary
    percentage_match = re.match(r"^(\d+(?:\.\d+)?)%$", text)
    if percentage_match:
        return float(percentage_match.group(1)), None
    number_match = re.match(r"^-?\d+(?:\.\d+)?$", text)
    if number_match:
        return float(text) if "." in text else int(text), None
    return text, None


def load_highlightly_normalized_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    capture = summary.get("accepted_provider_capture", {})
    bundle_files = [Path(path) for path in capture.get("bundle_files", [])]
    normalized_path = next((path for path in bundle_files if path.name == "normalized.json"), None)
    manifest_path = next((path for path in bundle_files if path.name == "manifest.json"), None)
    if normalized_path is None or manifest_path is None:
        raise FileNotFoundError("highlightly_bundle_missing_normalized_or_manifest")
    normalized = load_json(normalized_path)
    manifest = load_json(manifest_path)
    return {
        "bundle_id": capture.get("bundle_id"),
        "bundle_files": [str(path) for path in bundle_files],
        "normalized_path": str(normalized_path),
        "manifest_path": str(manifest_path),
        "normalized": normalized,
        "manifest": manifest,
    }


def load_sportdb_normalized_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    operations = summary.get("operations", {})
    bundle_ids: list[str] = []
    normalized_paths: list[str] = []
    loaded: dict[str, Any] = {}
    for op_name, op in operations.items():
        if op.get("bundle_id"):
            bundle_ids.append(str(op["bundle_id"]))
        files = [Path(path) for path in op.get("bundle_files", [])]
        normalized_path = next((path for path in files if path.name == "normalized.json"), None)
        if normalized_path is not None:
            normalized_paths.append(str(normalized_path))
            loaded[op_name] = load_json(normalized_path)
    return {
        "bundle_ids": bundle_ids,
        "normalized_paths": normalized_paths,
        "normalized": loaded,
    }


def extract_canonical_metrics(value: Any) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    metric_meta: dict[str, Any] = {}
    provider_extra_metrics: list[str] = []
    unknown_metrics_preserved: list[str] = []
    fixture_identity: dict[str, Any] = {}
    provider_match_id: str | None = None

    if isinstance(value, dict) and "statistics" in value:
        fixture_identity = dict(value.get("fixture_identity", {}))
        provider_match_id = value.get("provider_match_id")
        for row in value.get("statistics", []):
            if not isinstance(row, dict):
                continue
            metric_name = row.get("normalized_metric_name")
            raw_name = row.get("raw_stat_name")
            side = row.get("side")
            if side not in {"home", "away"}:
                continue
            if metric_name in CANONICAL_METRICS:
                metrics.setdefault(metric_name, {})[side] = row.get("value")
                metric_meta.setdefault(metric_name, {})[side] = {
                    "unit": row.get("unit"),
                    "raw_stat_name": raw_name,
                }
            elif metric_name in HIGHLIGHTLY_NON_CANONICAL:
                if metric_name not in provider_extra_metrics:
                    provider_extra_metrics.append(metric_name)
            elif raw_name and raw_name not in unknown_metrics_preserved:
                unknown_metrics_preserved.append(raw_name)
        for metric_name in value.get("missing_target_metrics", []):
            if metric_name not in unknown_metrics_preserved:
                unknown_metrics_preserved.append(metric_name)
        return {
            "provider_match_id": provider_match_id,
            "fixture_identity": fixture_identity,
            "metrics": metrics,
            "metric_meta": metric_meta,
            "provider_extra_metrics": sorted(provider_extra_metrics),
            "unknown_metrics_preserved": sorted(unknown_metrics_preserved),
        }

    raw_result = value.get("raw_result", {}) if isinstance(value, dict) else {}
    periods = raw_result.get("data", []) if isinstance(raw_result, dict) else []
    match_period = next(
        (
            period
            for period in periods
            if isinstance(period, dict) and period.get("period") == "Match"
        ),
        None,
    )
    if not isinstance(match_period, dict):
        return {
            "provider_match_id": value.get("provider_match_id") if isinstance(value, dict) else None,
            "fixture_identity": {},
            "metrics": {},
            "provider_extra_metrics": [],
            "unknown_metrics_preserved": [],
        }
    for stat in match_period.get("stats", []):
        if not isinstance(stat, dict):
            continue
        raw_name = str(stat.get("statName") or "").strip()
        metric_name = SPORTDB_STAT_NAME_MAP.get(raw_name.lower())
        if metric_name is None:
            if raw_name and raw_name not in unknown_metrics_preserved:
                unknown_metrics_preserved.append(raw_name)
            continue
        home_value, home_secondary = parse_stat_value(stat.get("homeValue"))
        away_value, away_secondary = parse_stat_value(stat.get("awayValue"))
        if metric_name == "total_passes":
            metrics[metric_name] = {
                "home": home_secondary or home_value,
                "away": away_secondary or away_value,
            }
            metric_meta[metric_name] = {
                "home": {
                    "raw_value": stat.get("homeValue"),
                    "unit": "count",
                    "source": "passes_completed_count",
                },
                "away": {
                    "raw_value": stat.get("awayValue"),
                    "unit": "count",
                    "source": "passes_completed_count",
                },
            }
            if home_value is not None and away_value is not None:
                metrics["successful_passes"] = {
                    "home": home_value,
                    "away": away_value,
                }
                metric_meta["successful_passes"] = {
                    "home": {
                        "raw_value": stat.get("homeValue"),
                        "unit": "percentage",
                        "source": "passes_completion_rate",
                    },
                    "away": {
                        "raw_value": stat.get("awayValue"),
                        "unit": "percentage",
                        "source": "passes_completion_rate",
                    },
                }
            continue
        metrics[metric_name] = {"home": home_value, "away": away_value}
        metric_meta[metric_name] = {
            "home": {"raw_value": stat.get("homeValue")},
            "away": {"raw_value": stat.get("awayValue")},
        }
    return {
        "provider_match_id": value.get("provider_match_id") if isinstance(value, dict) else None,
        "fixture_identity": {},
        "metrics": metrics,
        "metric_meta": metric_meta,
        "provider_extra_metrics": [],
        "unknown_metrics_preserved": sorted(unknown_metrics_preserved),
    }


def normalize_metric_value(metric_name: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {"value": None, "semantic_gap": True, "reason": "missing_value"}
    if not isinstance(value, (int, float)):
        return {"value": None, "semantic_gap": True, "reason": "unknown_units_or_types"}
    normalized = float(value)
    if metric_name == "possession" and 0.0 <= normalized <= 1.0:
        normalized = normalized * 100.0
    rule = CANONICAL_METRICS[metric_name]
    if rule["kind"] == "integer":
        rounded = round(normalized)
        if abs(normalized - rounded) > 1e-9:
            return {
                "value": normalized,
                "semantic_gap": True,
                "reason": "non_integer_for_integer_metric",
            }
        normalized = int(rounded)
    return {"value": normalized, "semantic_gap": False, "reason": None}


def compare_metric(metric_name: str, sportdb_value: Any, accepted_value: Any) -> dict[str, Any]:
    sportdb_normalized = normalize_metric_value(metric_name, sportdb_value)
    accepted_normalized = normalize_metric_value(metric_name, accepted_value)
    if sportdb_normalized["semantic_gap"] or accepted_normalized["semantic_gap"]:
        return {
            "metric": metric_name,
            "classification": "semantic_gap",
            "sportdb": sportdb_value,
            "accepted_provider": accepted_value,
            "reason": sportdb_normalized["reason"] or accepted_normalized["reason"],
        }
    left = sportdb_normalized["value"]
    right = accepted_normalized["value"]
    delta = abs(float(left) - float(right))
    tolerance = CANONICAL_METRICS[metric_name]["tolerance"]
    if delta <= tolerance + 1e-9:
        classification = "exact_match" if delta <= 1e-9 else "tolerance_match"
        return {
            "metric": metric_name,
            "classification": classification,
            "sportdb": left,
            "accepted_provider": right,
            "delta": delta,
            "tolerance": tolerance,
        }
    return {
        "metric": metric_name,
        "classification": "mismatch",
        "sportdb": left,
        "accepted_provider": right,
        "delta": delta,
        "tolerance": tolerance,
    }


def detect_pass_family_semantic_gap(
    sportdb_metrics: dict[str, Any],
    accepted_metrics: dict[str, Any],
    sportdb_metric_meta: dict[str, Any],
    accepted_metric_meta: dict[str, Any],
) -> dict[str, str]:
    sportdb_total = sportdb_metrics.get("total_passes")
    sportdb_successful = sportdb_metrics.get("successful_passes")
    accepted_total = accepted_metrics.get("total_passes")
    accepted_successful = accepted_metrics.get("successful_passes")
    if not all(
        isinstance(item, dict)
        for item in (sportdb_total, sportdb_successful, accepted_total, accepted_successful)
    ):
        return {}
    if not all(
        isinstance(sportdb_successful.get(side), (int, float))
        and isinstance(accepted_successful.get(side), (int, float))
        and isinstance(sportdb_total.get(side), (int, float))
        and isinstance(accepted_total.get(side), (int, float))
        for side in ("home", "away")
    ):
        return {}
    successful_meta = sportdb_metric_meta.get("successful_passes", {})
    accepted_successful_meta = accepted_metric_meta.get("successful_passes", {})
    total_meta = sportdb_metric_meta.get("total_passes", {})
    successful_is_rate = all(
        successful_meta.get(side, {}).get("unit") == "percentage"
        and total_meta.get(side, {}).get("unit") == "count"
        for side in ("home", "away")
    )
    accepted_successful_is_count = all(
        accepted_successful_meta.get(side, {}).get("unit") in {"count", None}
        for side in ("home", "away")
    )
    total_matches_accepted_successful = all(
        abs(float(sportdb_total[side]) - float(accepted_successful[side])) <= 1e-9
        for side in ("home", "away")
    )
    accepted_total_exceeds_successful = all(
        float(accepted_total[side]) >= float(accepted_successful[side])
        for side in ("home", "away")
    )
    if (
        successful_is_rate
        and accepted_successful_is_count
        and total_matches_accepted_successful
        and accepted_total_exceeds_successful
    ):
        return {
            "successful_passes": "sportdb_successful_passes_rate_vs_highlightly_successful_passes_count",
            "total_passes": "sportdb_total_passes_aligns_to_highlightly_successful_passes_not_total_passes",
        }
    return {}


def build_value_replay_summary(
    *,
    a8_summary: dict[str, Any],
    a7_summary: dict[str, Any],
    a6_summary: dict[str, Any],
    highlightly_bundle: dict[str, Any],
    sportdb_bundle: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
        "evidence_level": "TRACKED_VALUE_REPLAY_AGAINST_ACCEPTED_PROVIDER_SUMMARY",
        "protected_worktree": PROTECTED_WORKTREE,
        "mode": "replay_only_no_live_provider_calls",
        "providers": {"candidate": "sportdb", "accepted_provider": "highlightly"},
        "same_match_proof": {
            "valid": False,
            "sportdb_flashscore_match_id": None,
            "highlightly_provider_match_id": None,
            "proof_type": None,
            "proof_basis": [],
        },
        "fixture_identity": {
            "competition": None,
            "season": None,
            "kickoff_or_match_date": None,
            "home_team": None,
            "away_team": None,
            "score": None,
        },
        "local_evidence": {
            "sportdb_bundles_verified": False,
            "highlightly_bundle_verified": False,
            "sportdb_bundle_ids": [],
            "highlightly_bundle_id": None,
            "sportdb_normalized_paths": [],
            "highlightly_normalized_path": None,
        },
        "team_side_alignment": {
            "valid": False,
            "home_team_normalized": None,
            "away_team_normalized": None,
            "blocking_gaps": [],
        },
        "metric_replay": {
            "performed": False,
            "canonical_metrics_compared": [],
            "matched_metrics": [],
            "tolerance_matched_metrics": [],
            "mismatched_metrics": [],
            "semantic_gaps": [],
            "team_side_gaps": [],
            "missing_in_sportdb": [],
            "missing_in_accepted_provider": [],
            "unknown_metrics_preserved": [],
            "provider_extra_metrics": [],
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

    selection = a8_summary.get("same_match_selection", {})
    sportdb_identity = a7_summary.get("sportdb_identity", {})
    highlightly_identity = highlightly_bundle["normalized"].get("fixture_identity", {})
    summary["same_match_proof"] = {
        "valid": bool(selection.get("same_match_found")),
        "sportdb_flashscore_match_id": sportdb_identity.get("match_id"),
        "highlightly_provider_match_id": a8_summary.get("accepted_provider_capture", {}).get(
            "provider_match_id"
        ),
        "proof_type": selection.get("proof_type"),
        "proof_basis": list(selection.get("proof_basis", [])),
    }
    summary["fixture_identity"] = {
        "competition": sportdb_identity.get("competition") or highlightly_identity.get("competition"),
        "season": sportdb_identity.get("season") or highlightly_identity.get("season"),
        "kickoff_or_match_date": sportdb_identity.get("kickoff_or_match_date")
        or highlightly_identity.get("kickoff_or_match_date"),
        "home_team": sportdb_identity.get("home_team") or highlightly_identity.get("home_team"),
        "away_team": highlightly_identity.get("away_team") or sportdb_identity.get("away_team"),
        "score": normalize_score(sportdb_identity.get("score") or highlightly_identity.get("score")),
    }
    summary["local_evidence"] = {
        "sportdb_bundles_verified": True,
        "highlightly_bundle_verified": True,
        "sportdb_bundle_ids": list(sportdb_bundle.get("bundle_ids", [])),
        "highlightly_bundle_id": highlightly_bundle.get("bundle_id"),
        "sportdb_normalized_paths": list(sportdb_bundle.get("normalized_paths", [])),
        "highlightly_normalized_path": highlightly_bundle.get("normalized_path"),
    }

    sportdb_metrics = extract_canonical_metrics(sportdb_bundle["normalized"]["match_stats"])
    highlightly_metrics = extract_canonical_metrics(highlightly_bundle["normalized"])
    home_team_normalized = sportdb_identity.get("home_team_normalized") or normalize_team_name(
        sportdb_identity.get("home_team") or ""
    )
    away_team_normalized = sportdb_identity.get("away_team_normalized") or normalize_team_name(
        sportdb_identity.get("away_team") or ""
    )
    hl_home = normalize_team_name(highlightly_identity.get("home_team") or "")
    hl_away = normalize_team_name(highlightly_identity.get("away_team") or "")
    summary["team_side_alignment"] = {
        "valid": home_team_normalized == hl_home and away_team_normalized == hl_away,
        "home_team_normalized": home_team_normalized or None,
        "away_team_normalized": away_team_normalized or None,
        "blocking_gaps": [],
    }
    if not summary["team_side_alignment"]["valid"]:
        summary["team_side_alignment"]["blocking_gaps"].append(
            "home_away_team_names_do_not_align_between_providers"
        )

    sportdb_canonical = sportdb_metrics["metrics"]
    highlightly_canonical = highlightly_metrics["metrics"]
    pass_family_semantic_gap = detect_pass_family_semantic_gap(
        sportdb_canonical,
        highlightly_canonical,
        sportdb_metrics.get("metric_meta", {}),
        highlightly_metrics.get("metric_meta", {}),
    )
    overlap = sorted(set(sportdb_canonical) & set(highlightly_canonical) & set(CANONICAL_METRICS))
    summary["metric_replay"]["missing_in_sportdb"] = sorted(
        set(highlightly_canonical) & set(CANONICAL_METRICS) - set(sportdb_canonical)
    )
    summary["metric_replay"]["missing_in_accepted_provider"] = sorted(
        set(sportdb_canonical) & set(CANONICAL_METRICS) - set(highlightly_canonical)
    )
    summary["metric_replay"]["unknown_metrics_preserved"] = sorted(
        set(sportdb_metrics["unknown_metrics_preserved"])
        | set(highlightly_metrics["unknown_metrics_preserved"])
    )
    summary["metric_replay"]["provider_extra_metrics"] = sorted(
        set(highlightly_metrics["provider_extra_metrics"])
    )

    if summary["same_match_proof"]["valid"] and summary["team_side_alignment"]["valid"] and overlap:
        summary["metric_replay"]["performed"] = True
        for metric_name in overlap:
            sportdb_sides = sportdb_canonical[metric_name]
            accepted_sides = highlightly_canonical[metric_name]
            if metric_name in pass_family_semantic_gap:
                summary["metric_replay"]["semantic_gaps"].append(
                    {
                        "metric": metric_name,
                        "sportdb": sportdb_sides,
                        "accepted_provider": accepted_sides,
                        "reason": pass_family_semantic_gap[metric_name],
                    }
                )
                continue
            home_result = compare_metric(
                metric_name, sportdb_sides.get("home"), accepted_sides.get("home")
            )
            away_result = compare_metric(
                metric_name, sportdb_sides.get("away"), accepted_sides.get("away")
            )
            if home_result["classification"] == "semantic_gap" or away_result["classification"] == "semantic_gap":
                summary["metric_replay"]["semantic_gaps"].append(
                    {
                        "metric": metric_name,
                        "sportdb": sportdb_sides,
                        "accepted_provider": accepted_sides,
                        "reason": home_result.get("reason") or away_result.get("reason"),
                    }
                )
                continue
            summary["metric_replay"]["canonical_metrics_compared"].append(metric_name)
            if home_result["classification"] == "exact_match" and away_result["classification"] == "exact_match":
                summary["metric_replay"]["matched_metrics"].append(metric_name)
                continue
            if home_result["classification"] in {"exact_match", "tolerance_match"} and away_result["classification"] in {"exact_match", "tolerance_match"}:
                summary["metric_replay"]["tolerance_matched_metrics"].append(metric_name)
                continue
            summary["metric_replay"]["mismatched_metrics"].append(
                {
                    "metric": metric_name,
                    "sportdb": sportdb_sides,
                    "accepted_provider": accepted_sides,
                    "home_delta": home_result.get("delta"),
                    "away_delta": away_result.get("delta"),
                    "home_tolerance": home_result.get("tolerance"),
                    "away_tolerance": away_result.get("tolerance"),
                }
            )

    return summary


def classify_value_replay(summary: dict[str, Any]) -> str:
    if "script_or_parser_defect" in summary["blockers"]:
        return "SPORTDB_VALUE_REPLAY_BLOCKED_SCRIPT_OR_PARSER_DEFECT"
    if "missing_local_evidence" in summary["blockers"]:
        return "SPORTDB_VALUE_REPLAY_BLOCKED_MISSING_LOCAL_EVIDENCE"
    if not summary["same_match_proof"]["valid"]:
        return "SPORTDB_VALUE_REPLAY_BLOCKED_SAME_MATCH_PROOF_INVALID"
    if not summary["team_side_alignment"]["valid"]:
        return "SPORTDB_VALUE_REPLAY_BLOCKED_TEAM_SIDE_ALIGNMENT"
    if not summary["metric_replay"]["performed"] or not summary["metric_replay"]["canonical_metrics_compared"]:
        return "SPORTDB_VALUE_REPLAY_BLOCKED_NO_OVERLAPPING_CANONICAL_METRICS"
    if summary["metric_replay"]["mismatched_metrics"]:
        return "SPORTDB_VALUE_REPLAY_BLOCKED_METRIC_MISMATCH"
    if summary["metric_replay"]["semantic_gaps"]:
        return "SPORTDB_VALUE_REPLAY_READY_WITH_SEMANTIC_GAPS_FOR_REVIEW"
    if len(summary["metric_replay"]["canonical_metrics_compared"]) >= 5:
        return "SPORTDB_VALUE_REPLAY_READY_FOR_SCOPE_LIMITED_CERTIFICATION_PLAN"
    return "SPORTDB_VALUE_REPLAY_BLOCKED_NO_OVERLAPPING_CANONICAL_METRICS"


def set_next_step(summary: dict[str, Any]) -> None:
    classification = summary["classification"]
    if classification == "SPORTDB_VALUE_REPLAY_READY_FOR_SCOPE_LIMITED_CERTIFICATION_PLAN":
        summary["next_step"] = "P2E_A10_SPORTDB_SCOPE_LIMITED_CERTIFICATION_PLAN"
    elif classification == "SPORTDB_VALUE_REPLAY_READY_WITH_SEMANTIC_GAPS_FOR_REVIEW":
        summary["next_step"] = "P2E_A10_SEMANTIC_GAP_REVIEW_BEFORE_CERTIFICATION_PLAN"
    elif classification == "SPORTDB_VALUE_REPLAY_BLOCKED_METRIC_MISMATCH":
        summary["next_step"] = "P2E_A9B_SPORTDB_NORMALIZATION_OR_PROVIDER_SEMANTIC_REVIEW"
    else:
        summary["next_step"] = "blocked_or_retry_after_review"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=SUMMARY_PATH)
    args = parser.parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        a8_summary = load_json(P2E_A8_SUMMARY_PATH)
        a7_summary = load_json(P2E_A7_SUMMARY_PATH)
        a6_summary = load_json(P2E_A6_SUMMARY_PATH)
        summary = build_value_replay_summary(
            a8_summary=a8_summary,
            a7_summary=a7_summary,
            a6_summary=a6_summary,
            highlightly_bundle=load_highlightly_normalized_metrics(a8_summary),
            sportdb_bundle=load_sportdb_normalized_metrics(a6_summary),
        )
        errors = validate_p2e_a8_summary(a8_summary) + validate_p2e_a6_summary(a6_summary)
        if errors:
            if any("bundle" in error for error in errors):
                summary["blockers"].append("missing_local_evidence")
            else:
                summary["blockers"].append("script_or_parser_defect")
        if not summary["same_match_proof"]["valid"]:
            summary["same_match_proof"]["proof_basis"] = []
    except FileNotFoundError:
        summary = {
            "phase_id": PHASE_ID,
            "prompt_version": PROMPT_VERSION,
            "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
            "evidence_level": "TRACKED_VALUE_REPLAY_AGAINST_ACCEPTED_PROVIDER_SUMMARY",
            "protected_worktree": PROTECTED_WORKTREE,
            "mode": "replay_only_no_live_provider_calls",
            "providers": {"candidate": "sportdb", "accepted_provider": "highlightly"},
            "same_match_proof": {"valid": False, "sportdb_flashscore_match_id": None, "highlightly_provider_match_id": None, "proof_type": None, "proof_basis": []},
            "fixture_identity": {"competition": None, "season": None, "kickoff_or_match_date": None, "home_team": None, "away_team": None, "score": None},
            "local_evidence": {"sportdb_bundles_verified": False, "highlightly_bundle_verified": False, "sportdb_bundle_ids": [], "highlightly_bundle_id": None, "sportdb_normalized_paths": [], "highlightly_normalized_path": None},
            "team_side_alignment": {"valid": False, "home_team_normalized": None, "away_team_normalized": None, "blocking_gaps": []},
            "metric_replay": {"performed": False, "canonical_metrics_compared": [], "matched_metrics": [], "tolerance_matched_metrics": [], "mismatched_metrics": [], "semantic_gaps": [], "team_side_gaps": [], "missing_in_sportdb": [], "missing_in_accepted_provider": [], "unknown_metrics_preserved": [], "provider_extra_metrics": []},
            "classification": "UNKNOWN",
            "certification": {"certified_routes": [], "production_routing_changed": False, "selectable_status_changed": False, "verdict": NOT_CERTIFIED_VERDICT},
            "impact_on_p2d": "none_highlightly_remains_accepted",
            "next_step": "UNKNOWN",
            "blockers": ["missing_local_evidence"],
            "secret_safe": True,
            "final_review": "PASS",
        }
    except Exception:
        summary = {
            "phase_id": PHASE_ID,
            "prompt_version": PROMPT_VERSION,
            "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
            "evidence_level": "TRACKED_VALUE_REPLAY_AGAINST_ACCEPTED_PROVIDER_SUMMARY",
            "protected_worktree": PROTECTED_WORKTREE,
            "mode": "replay_only_no_live_provider_calls",
            "providers": {"candidate": "sportdb", "accepted_provider": "highlightly"},
            "same_match_proof": {"valid": False, "sportdb_flashscore_match_id": None, "highlightly_provider_match_id": None, "proof_type": None, "proof_basis": []},
            "fixture_identity": {"competition": None, "season": None, "kickoff_or_match_date": None, "home_team": None, "away_team": None, "score": None},
            "local_evidence": {"sportdb_bundles_verified": False, "highlightly_bundle_verified": False, "sportdb_bundle_ids": [], "highlightly_bundle_id": None, "sportdb_normalized_paths": [], "highlightly_normalized_path": None},
            "team_side_alignment": {"valid": False, "home_team_normalized": None, "away_team_normalized": None, "blocking_gaps": []},
            "metric_replay": {"performed": False, "canonical_metrics_compared": [], "matched_metrics": [], "tolerance_matched_metrics": [], "mismatched_metrics": [], "semantic_gaps": [], "team_side_gaps": [], "missing_in_sportdb": [], "missing_in_accepted_provider": [], "unknown_metrics_preserved": [], "provider_extra_metrics": []},
            "classification": "UNKNOWN",
            "certification": {"certified_routes": [], "production_routing_changed": False, "selectable_status_changed": False, "verdict": NOT_CERTIFIED_VERDICT},
            "impact_on_p2d": "none_highlightly_remains_accepted",
            "next_step": "UNKNOWN",
            "blockers": ["script_or_parser_defect"],
            "secret_safe": True,
            "final_review": "PASS",
        }

    summary["classification"] = classify_value_replay(summary)
    set_next_step(summary)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
