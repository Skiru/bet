#!/usr/bin/env python3
"""S8 current-run non-executable Superbet manual quote pack."""
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


def _s8_output_path(data_dir: Path, betting_day: str, _runtime_mode: object | None = None) -> Path:
    return data_dir / f"{betting_day}_s8_superbet_manual_quote_pack.json"


def _load_canonical_s7b(child_env: dict[str, str], day: str, run_id: str) -> tuple[Path, Path, dict[str, Any]]:
    from bet.pipeline.integration_artifacts import resolve_bound_step_output
    run_root = Path(child_env["BET_PIPELINE_RUN_ROOT"])
    output_path, mapping = resolve_bound_step_output(
        run_root=run_root,
        step_id="S7b",
        betting_day=day,
        run_id=run_id,
        expected_artifact_type="S7B_SUPERBET_MANUAL_MAPPING",
    )
    evidence_path = run_root / "artifacts" / "S7b.json"
    return evidence_path, output_path, mapping


def _validate_mapping(mapping: dict[str, Any], day: str, run_id: str) -> tuple[str, list[dict[str, Any]]]:
    if (
        mapping.get("schema_version") != 1
        or mapping.get("artifact_type") != "S7B_SUPERBET_MANUAL_MAPPING"
        or mapping.get("betting_day") != day
        or mapping.get("run_id") != run_id
        or mapping.get("operator_workflow") != "SUPERBET_MANUAL_BET_BUILDER"
        or mapping.get("operator_availability_asserted") is not False
    ):
        raise ValueError("S7b manual mapping contract is invalid")
    status = mapping.get("status")
    cards = mapping.get("mapping_suggestions")
    if status not in {"READY_FOR_MANUAL_MAPPING", "NO_ACTION_TERMINAL"} or not isinstance(cards, list):
        raise ValueError("S7b manual mapping status is invalid")
    if status == "NO_ACTION_TERMINAL" and cards:
        raise ValueError("NO_ACTION_TERMINAL cannot contain quote cards")
    if status == "READY_FOR_MANUAL_MAPPING" and not cards:
        raise ValueError("manual mapping readiness requires quote cards")
    if mapping.get("approved_candidate_count") != len(cards) or mapping.get("represented_candidate_count") != len(cards):
        raise ValueError("S7b candidate accounting is incomplete")

    card_ids: set[str] = set()
    source_ids: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError("S7b quote card must be an object")
        card_id = card.get("quote_card_id")
        source_id = card.get("source_candidate_id")
        if not isinstance(card_id, str) or not card_id or not isinstance(source_id, str) or not source_id:
            raise ValueError("S7b quote card identity is incomplete")
        if card_id in card_ids or source_id in source_ids:
            raise ValueError("S7b quote card identity is duplicated")
        card_ids.add(card_id)
        source_ids.add(source_id)
        if card.get("manual_operator") != "SUPERBET" or card.get("mapping_ambiguity") in (None, ""):
            raise ValueError("S7b quote card mapping semantics are incomplete")
        if any(card.get(field) not in (None, "") for field in BLANK_OPERATOR_FIELDS):
            raise ValueError("S7b quote card illegally contains a human operator value")
        if any(card.get(field) is not False for field in ("operator_availability_asserted", "executable_coupon", "betting_valid", "can_place_bet_now")):
            raise ValueError("S7b quote card violates the operator boundary")
    return status, cards


def main() -> None:
    parser = argparse.ArgumentParser(description="S8 manual Superbet quote-pack publisher")
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
    mapping_status = "BLOCKED"
    s7b_evidence: Path | None = None
    s7b_output: Path | None = None
    try:
        s7b_evidence, s7b_output, mapping = _load_canonical_s7b(child_env, args.date, args.run_id)
        mapping_status, cards = _validate_mapping(mapping, args.date, args.run_id)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        blocked.append("BLOCKED_S8_CANONICAL_S7B_INVALID")
        print(f"BLOCKED_S8_CANONICAL_S7B_INVALID: {exc}")

    outcome = "BLOCKED" if blocked else (
        "NO_ACTION_TERMINAL" if mapping_status == "NO_ACTION_TERMINAL" else "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW"
    )
    ready_for_human_gate = outcome == "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW" and bool(cards)
    output_path = _s8_output_path(Path(child_env["BET_PIPELINE_DATA_DIR"]), args.date, mode)
    output_sha256: str | None = None
    if not blocked:
        output_artifact = {
                "schema_version": 1,
                "artifact_type": "S8_SUPERBET_MANUAL_QUOTE_PACK",
                "status": outcome,
                "betting_day": args.date,
                "run_id": args.run_id,
                "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
                "source_s7b_evidence_path": str(s7b_evidence),
                "source_s7b_evidence_sha256": sha256_file(s7b_evidence),
                "source_s7b_output_path": str(s7b_output),
                "source_s7b_output_sha256": sha256_file(s7b_output),
                "quote_card_count": len(cards),
                "quote_cards": cards,
                "idea_groups": [],
                "analytical_status": "READY" if cards else "NO_ACTION",
                "pricing_status": "UNPRICED",
                "risk_status": "ACCEPTABLE_FOR_MANUAL_QUOTE" if cards else "NO_ACTION",
                "final_status": outcome,
                "ev_available": False,
                "kelly_available": False,
                "stake_available": False,
                "combined_bookmaker_odds": None,
                "requires_human_gate": bool(cards),
                "ready_for_human_gate": ready_for_human_gate,
                "ready_for_production_execution": False,
                "production_selectable": False,
                "production_coupon_write": False,
                "executable_coupon": False,
                "betting_valid": False,
                "can_place_bet_now": False,
                "operator_availability_asserted": False,
                "operator_automation_enabled": False,
        }
        receipt = publish_run_artifact(
            run_root=Path(child_env["BET_PIPELINE_RUN_ROOT"]),
            target=output_path,
            payload=output_artifact,
            betting_day=args.date,
            run_id=args.run_id,
            artifact_type="S8_SUPERBET_MANUAL_QUOTE_PACK",
        )
        output_sha256 = receipt.sha256

    payload = {
        "s8_input_path": str(s7b_output) if s7b_output else None,
        "s8_quote_pack_path": str(output_path) if not blocked else None,
        "s8_quote_pack_sha256": output_sha256,
        "quote_card_count": len(cards),
        "outcome": outcome,
        "requires_human_gate": bool(cards) and not blocked,
        "ready_for_human_gate": ready_for_human_gate,
        "ready_for_production_execution": False,
        "production_coupon_write": False,
        "executable_coupon": False,
        "betting_valid": False,
        "can_place_bet_now": False,
        "runtime_path_source": runtime_path_source,
        "child_run_root": child_env["BET_PIPELINE_RUN_ROOT"],
        "child_artifact_dir": child_env["BET_PIPELINE_ARTIFACT_DIR"],
    }
    write_terminal_script_evidence_or_fail(
        step_id="S8",
        status="BLOCK" if blocked else "PASS",
        payload=payload,
        sources=("manual:SUPERBET",),
        child_env=child_env,
        blocked_reasons=tuple(blocked),
        no_pick_edge_stake_coupon_emitted=True,
        extra_top_level_fields={"production_coupon_write": False},
    )
    raise SystemExit(5 if blocked else 0)


if __name__ == "__main__":
    main()
