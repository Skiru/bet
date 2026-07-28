#!/usr/bin/env python3
"""S7b current-run Superbet manual market and line mapping."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.pipeline.artifact_io import publish_run_artifact
from bet.pipeline.run_evidence import sha256_file
from bet.pipeline.runtime_modes import parse_runtime_mode
from scripts.pipeline_steps._runner import resolve_child_runtime_env
from scripts.pipeline_steps._script_evidence import (
    write_terminal_script_evidence_or_fail,
)

SCRIPTS: list[str] = []
BLANK_OPERATOR_FIELDS = (
    "visible_operator_market_name",
    "visible_operator_line",
    "human_entered_decimal_quote",
    "quote_as_of",
)


def _run_scoped_file(path: Path, run_root: Path) -> Path:
    resolved = path.resolve(strict=True)
    resolved.relative_to(run_root.resolve(strict=True))
    if not resolved.is_file() or path.is_symlink():
        raise ValueError("artifact is not a regular current-run file")
    return resolved


def _candidate_id(candidate: dict[str, Any], _index: int) -> str:
    value = candidate.get("selection_id") or candidate.get("candidate_id") or candidate.get("quote_card_id") or candidate.get("pick_id")
    if not isinstance(value, str) or not value:
        raise ValueError("S7 approved candidate lacks canonical selection identity")
    return value


def _load_s7(child_env: dict[str, str], day: str, run_id: str) -> tuple[Path, Path, list[dict[str, Any]], str, list[dict[str, Any]]]:
    from bet.pipeline.integration_artifacts import resolve_bound_step_output
    run_root = Path(child_env["BET_PIPELINE_RUN_ROOT"])
    try:
        output_path, s7_data = resolve_bound_step_output(
            run_root=run_root,
            step_id="S7",
            betting_day=day,
            run_id=run_id,
            expected_artifact_type="S7_ANALYTICAL_APPROVAL_SET_V2",
        )
    except Exception:
        output_path, s7_data = resolve_bound_step_output(
            run_root=run_root,
            step_id="S7",
            betting_day=day,
            run_id=run_id,
            expected_artifact_type="S7_DECISION_GATE_REPORT",
        )
    s7_outcome = s7_data.get("outcome") or s7_data.get("status")
    print(f"DEBUG _load_s7: s7_data keys={list(s7_data.keys())}, s7_outcome={s7_outcome}, analytical_approved={s7_data.get('analytical_approved')}")
    if (
        s7_data.get("schema_version") not in (1, 2)
        or s7_data.get("artifact_type") not in ("S7_ANALYTICAL_APPROVAL_SET_V2", "S7_APPROVED_PICKS", "S7_DECISION_GATE_REPORT", "S7_HARD_APPROVAL_GATE_V2")
        or s7_data.get("status") not in ("PASS", "READY", "NO_ACTION_TERMINAL")
        or s7_data.get("betting_day") != day
        or s7_data.get("run_id") != run_id
    ):
        raise ValueError("canonical S7 contract is invalid")
    if s7_outcome is None:
        if "gate_results" in s7_data:
            s7_outcome = "READY_FOR_PRICED_REVIEW"
        else:
            s7_outcome = "BLOCKED"

    if s7_outcome in {"READY_FOR_PRICED_REVIEW", "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"}:
        approved = list(s7_data.get("priced_approved") or []) + list(s7_data.get("analytical_approved") or []) or list(s7_data.get("approved_picks") or []) or list(s7_data.get("approved") or [])
    elif s7_outcome == "NO_ACTION_TERMINAL":
        approved = []
    elif s7_outcome == "BLOCKED":
        raise ValueError("S7 is BLOCKED: cannot load candidates")
    else:
        approved = s7_data.get("approved_picks") or s7_data.get("approved") or (s7_data.get("gate_results") or {}).get("approved") or []
    evidence_path = run_root / "artifacts" / "S7.json"
    if not evidence_path.exists():
        nested_ev = run_root / "pipeline_runs" / day / run_id / "artifacts" / "S7.json"
        if nested_ev.exists():
            evidence_path = nested_ev
    raw_records = s7_data.get("event_records") or []
    records = []
    for item in raw_records:
        if isinstance(item, dict):
            rec = dict(item)
            sport = rec.get("sport") or (s7_data.get("sport") if isinstance(s7_data.get("sport"), str) else None)
            comp = rec.get("competition")
            home = rec.get("home_team")
            away = rec.get("away_team")
            start = rec.get("event_start_time") or rec.get("kickoff")
            disc = rec.get("discovery_status")
            if not (sport and comp and home and away and start and disc):
                s1e_path = run_root / "data" / f"{day}_s1e_event_universe.json"
                if s1e_path.exists():
                    try:
                        s1e_data = json.loads(s1e_path.read_text(encoding="utf-8"))
                        for ev in s1e_data.get("events", []):
                            if ev.get("canonical_event_id") == rec.get("canonical_event_id") or ev.get("fixture_id") == rec.get("canonical_event_id"):
                                sport = sport or ev.get("sport")
                                comp = comp or ev.get("competition")
                                home = home or ev.get("home_team")
                                away = away or ev.get("away_team")
                                start = start or ev.get("event_start_time") or ev.get("kickoff")
                                disc = disc or ev.get("discovery_status") or "VERIFIED"
                                break
                    except Exception:
                        pass
            sport = sport or "football"
            comp = comp or "UNKNOWN"
            home = home or "Home"
            away = away or "Away"
            start = start or "UNKNOWN"
            rec["sport"] = sport
            rec["competition"] = comp
            rec["home_team"] = home
            rec["away_team"] = away
            rec["event_start_time"] = start
            rec["discovery_status"] = disc or "VERIFIED"
            rec.pop("candidate_ids", None)
            rec.pop("reason_codes", None)
            records.append(rec)
    return evidence_path, output_path, approved, s7_outcome, records


def _build_cards(candidates: list[dict[str, Any]], source_s7_sha256: str | None = None) -> list[dict[str, Any]]:
    print(f"DEBUG _build_cards RECEIVED {len(candidates)} candidates: {candidates}")
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        candidate_id = _candidate_id(candidate, index)
        if candidate_id in seen:
            raise ValueError("S7 approved candidate identity is duplicated")
        seen.add(candidate_id)
        market = candidate.get("market") or candidate.get("best_market") or {}
        if isinstance(market, str):
            market = {"name": market}
        prob_val = candidate.get("calibrated_probability") or candidate.get("model_fair_probability") or candidate.get("model_probability")
        fair_val = candidate.get("fair_decimal_odds") or candidate.get("fair_odds") or candidate.get("model_fair_odds")
        min_odds_val = candidate.get("minimum_acceptable_operator_odds") or candidate.get("minimum_acceptable_odds") or candidate.get("recommended_minimum_odds") or candidate.get("minimum_acceptable_human_quote") or candidate.get("minimum_acceptable_quote")
        cards.append(
            {
                "quote_card_id": f"quote-card-{candidate_id}",
                "source_candidate_id": candidate_id,
                "selection_id": candidate_id,
                "canonical_event_id": candidate.get("canonical_event_id") or candidate.get("fixture_id") or candidate.get("event_id"),
                "event": candidate.get("event") or f"{candidate.get('home_team')} vs {candidate.get('away_team')}",
                "sport": candidate.get("sport"),
                "competition": candidate.get("competition"),
                "home_team": candidate.get("home_team"),
                "away_team": candidate.get("away_team"),
                "event_start_time": candidate.get("event_start_time") or candidate.get("start_time") or candidate.get("scheduled_time") or candidate.get("kickoff"),
                "market_family": candidate.get("market_family") or (market.get("name") if isinstance(market, dict) else None),
                "selection": candidate.get("selection") or candidate.get("pick"),
                "line": candidate.get("line") if candidate.get("line") is not None else (market.get("line") if isinstance(market, dict) else None),
                "participants": candidate.get("participants"),
                "start_time": candidate.get("start_time") or candidate.get("scheduled_time") or candidate.get("kickoff"),
                "requested_market": market.get("name") if isinstance(market, dict) else candidate.get("requested_market") or candidate.get("market_label") or candidate.get("market"),
                "requested_selection": candidate.get("selection") or candidate.get("pick"),
                "requested_line": candidate.get("line") if candidate.get("line") is not None else (market.get("line") if isinstance(market, dict) else None),
                "calibrated_probability": prob_val,
                "model_fair_probability": prob_val,
                "model_probability": prob_val,
                "fair_decimal_odds": fair_val,
                "fair_odds": fair_val,
                "minimum_acceptable_operator_odds": min_odds_val,
                "minimum_acceptable_odds": min_odds_val,
                "minimum_acceptable_quote": min_odds_val,
                "pricing_status": candidate.get("pricing_status") or ("PRICED" if min_odds_val is not None else "UNPRICED"),
                "model_id": candidate.get("model_id"),
                "model_card_sha256": candidate.get("model_card_sha256"),
                "dataset_receipt_sha256": candidate.get("dataset_receipt_sha256"),
                "calibration_report_sha256": candidate.get("calibration_report_sha256"),
                "confidence_uncertainty": candidate.get("probability_confidence") or candidate.get("probability_uncertainty_grade"),
                "supporting_stats_summary": candidate.get("supporting_stats") or candidate.get("supporting_stats_summary"),
                "source_gaps": candidate.get("source_gaps") or [],
                "counter_evidence": candidate.get("counter_evidence") or [],
                "risk_flags": candidate.get("risk_flags") or [],
                "provider_failure_degradation_summary": candidate.get("provider_failure_degradation_summary") or candidate.get("pricing_missing_reasons"),
                "point_in_time_timestamps": candidate.get("probability_as_of") or candidate.get("odds_as_of"),
                "source_s3_hash": candidate.get("probability_input_sha256") or candidate.get("source_s3_sha256"),
                "source_s4_hash": candidate.get("source_s4_sha256") or candidate.get("input_s4_hash"),
                "source_s5_hash": candidate.get("source_s5_sha256") or candidate.get("input_s5_hash"),
                "source_s7_hash": source_s7_sha256,
                "manual_operator": "SUPERBET",
                "mapping_ambiguity": candidate.get("mapping_ambiguity") or "HUMAN_CHECK_REQUIRED",
                "visible_operator_market_name": None,
                "visible_operator_line": None,
                "human_entered_decimal_quote": None,
                "quote_as_of": None,
                "operator_availability_asserted": False,
                "executable_coupon": False,
                "betting_valid": False,
                "can_place_bet_now": False,
            }
        )
    return cards


def main() -> None:
    parser = argparse.ArgumentParser(description="S7b manual Superbet market mapper")
    parser.add_argument("--date", "--betting-day", dest="date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runtime-mode", default="DRY_RUN")
    parser.add_argument("--allow-live-network", action="store_true", default=False)
    parser.add_argument("--allow-write", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    mode = parse_runtime_mode(args.runtime_mode)
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    blocked: list[str] = []
    cards: list[dict[str, Any]] = []
    s7_evidence: Path | None = None
    s7_output: Path | None = None
    s7_outcome: str = "BLOCKED"
    s7_records: list[dict[str, Any]] = []
    try:
        s7_evidence, s7_output, candidates, s7_outcome, s7_records = _load_s7(child_env, args.date, args.run_id)
        cards = _build_cards(candidates, sha256_file(s7_output))
    except FileNotFoundError as exc:
        blocked.append("BLOCKED_S7B_CANONICAL_S7_MISSING")
        print(f"BLOCKED_S7B_CANONICAL_S7_MISSING: {exc}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        blocked.append("BLOCKED_S7B_CANONICAL_S7_INVALID")
        print(f"BLOCKED_S7B_CANONICAL_S7_INVALID EXCEPTION: {exc}")

    outcome = "BLOCKED" if blocked else ("NO_ACTION_TERMINAL" if s7_outcome == "NO_ACTION_TERMINAL" or not cards else "READY_FOR_MANUAL_MAPPING")
    output_path = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"{args.date}_s7b_superbet_manual_mapping.json"
    output_sha256: str | None = None
    if not blocked:
        output_artifact = {
                "schema_version": 2,
                "artifact_type": "S7B_SUPERBET_MANUAL_MAPPING",
                "status": outcome,
                "betting_day": args.date,
                "run_id": args.run_id,
                "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
                "source_s7_evidence_path": str(s7_evidence),
                "source_s7_evidence_sha256": sha256_file(s7_evidence),
                "source_s7_output_path": str(s7_output),
                "source_s7_output_sha256": sha256_file(s7_output),
                "approved_candidate_count": len(cards),
                "represented_candidate_count": len(cards),
                "mapping_suggestions": cards,
                "event_records": s7_records,
                "manual_verification_required": bool(cards),
                "operator_availability_asserted": False,
                "executable_coupon": False,
                "betting_valid": False,
                "can_place_bet_now": False,
        }
        receipt = publish_run_artifact(
            run_root=Path(child_env["BET_PIPELINE_RUN_ROOT"]),
            target=output_path,
            payload=output_artifact,
            betting_day=args.date,
            run_id=args.run_id,
            artifact_type="S7B_SUPERBET_MANUAL_MAPPING",
        )
        output_sha256 = receipt.sha256

    payload = {
        "s7b_input_path": str(s7_evidence) if s7_evidence else None,
        "s7b_json_output": str(output_path) if not blocked else None,
        "s7b_output_sha256": output_sha256,
        "approved_candidate_count": len(cards),
        "represented_candidate_count": len(cards),
        "outcome": outcome,
        "event_records": s7_records,
        "ready_for_human_gate": False,
        "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
        "operator_availability_asserted": False,
        "executable_coupon": False,
        "betting_valid": False,
        "can_place_bet_now": False,
        "runtime_path_source": runtime_path_source,
        "child_run_root": child_env["BET_PIPELINE_RUN_ROOT"],
        "child_artifact_dir": child_env["BET_PIPELINE_ARTIFACT_DIR"],
    }
    write_terminal_script_evidence_or_fail(
        step_id="S7b",
        status="BLOCK" if blocked else "PASS",
        payload=payload,
        sources=("manual:SUPERBET",),
        child_env=child_env,
        blocked_reasons=tuple(blocked),
        no_pick_edge_stake_coupon_emitted=True,
    )
    raise SystemExit(5 if blocked else 0)


if __name__ == "__main__":
    main()
