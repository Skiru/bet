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


def _candidate_id(candidate: dict[str, Any], index: int) -> str:
    value = candidate.get("candidate_id") or candidate.get("fixture_id")
    return str(value) if value not in (None, "") else f"s7-candidate-{index}"


def _load_s7(child_env: dict[str, str], day: str, run_id: str) -> tuple[Path, Path, list[dict[str, Any]], str]:
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
    s7_outcome = s7_data.get("outcome") or s7_data.get("status") or "BLOCKED"
    if s7_outcome == "READY_FOR_PRICED_REVIEW":
        approved = s7_data.get("priced_approved") or []
    elif s7_outcome == "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW":
        approved = s7_data.get("analytical_approved") or []
    elif s7_outcome == "NO_ACTION_TERMINAL":
        approved = []
    elif s7_outcome == "BLOCKED":
        raise ValueError("S7 is BLOCKED: cannot load candidates")
    else:
        approved = s7_data.get("approved") or (s7_data.get("gate_results") or {}).get("approved") or []
    evidence_path = run_root / "artifacts" / "S7.json"
    return evidence_path, output_path, approved, s7_outcome


def _build_cards(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        cards.append(
            {
                "quote_card_id": f"quote-card-{candidate_id}",
                "source_candidate_id": candidate_id,
                "canonical_event_id": candidate.get("canonical_event_id") or candidate.get("fixture_id") or candidate.get("event_id"),
                "event": candidate.get("event") or f"{candidate.get('home_team')} vs {candidate.get('away_team')}",
                "sport": candidate.get("sport"),
                "competition": candidate.get("competition"),
                "participants": candidate.get("participants"),
                "start_time": candidate.get("start_time") or candidate.get("scheduled_time") or candidate.get("kickoff"),
                "requested_market": market.get("name") or candidate.get("requested_market") or candidate.get("market_label") or candidate.get("market"),
                "requested_selection": candidate.get("selection") or candidate.get("pick"),
                "requested_line": candidate.get("line") if candidate.get("line") is not None else market.get("line"),
                "model_probability": candidate.get("model_probability"),
                "fair_odds": candidate.get("fair_odds"),
                "minimum_acceptable_quote": candidate.get("minimum_acceptable_human_quote") or candidate.get("minimum_acceptable_quote"),
                "confidence_uncertainty": candidate.get("probability_confidence") or candidate.get("probability_uncertainty_grade"),
                "supporting_stats_summary": candidate.get("supporting_stats") or candidate.get("supporting_stats_summary"),
                "source_gaps": candidate.get("source_gaps") or [],
                "counter_evidence": candidate.get("counter_evidence") or [],
                "risk_flags": candidate.get("risk_flags") or [],
                "pricing_status": candidate.get("pricing_status") or "UNPRICED",
                "provider_failure_degradation_summary": candidate.get("provider_failure_degradation_summary") or candidate.get("pricing_missing_reasons"),
                "point_in_time_timestamps": candidate.get("probability_as_of") or candidate.get("odds_as_of"),
                "source_s3_hash": candidate.get("probability_input_sha256") or candidate.get("source_s3_sha256"),
                "source_s4_hash": candidate.get("source_s4_sha256") or candidate.get("input_s4_hash"),
                "source_s5_hash": candidate.get("source_s5_sha256") or candidate.get("input_s5_hash"),
                "source_s7_hash": candidate.get("source_s7_sha256") or candidate.get("input_s7_hash"),
                "manual_operator": "SUPERBET",
                "mapping_confidence": "UNVERIFIED",
                "mapping_ambiguity": "HUMAN_CHECK_REQUIRED",
                **{field: None for field in BLANK_OPERATOR_FIELDS},
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
    try:
        s7_evidence, s7_output, candidates, s7_outcome = _load_s7(child_env, args.date, args.run_id)
        cards = _build_cards(candidates)
    except FileNotFoundError as exc:
        blocked.append("BLOCKED_S7B_CANONICAL_S7_MISSING")
        print(f"BLOCKED_S7B_CANONICAL_S7_MISSING: {exc}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        blocked.append("BLOCKED_S7B_CANONICAL_S7_INVALID")
        print(f"BLOCKED_S7B_CANONICAL_S7_INVALID: {exc}")

    outcome = "BLOCKED" if blocked else ("NO_ACTION_TERMINAL" if s7_outcome == "NO_ACTION_TERMINAL" or not cards else "READY_FOR_MANUAL_MAPPING")
    output_path = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"{args.date}_s7b_superbet_manual_mapping.json"
    output_sha256: str | None = None
    if not blocked:
        output_artifact = {
                "schema_version": 1,
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
