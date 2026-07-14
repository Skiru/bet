#!/usr/bin/env python3
"""48-hour repeat pick detector — finds same team+market losses in recent history.

Reads picks-ledger.csv and identifies picks in the last 48 hours with the same
team+market combination that resulted in a loss. These are flagged for the S7 gate.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.integration_artifacts import resolve_manifest_step_output
from bet.pipeline.run_evidence import sha256_file, repo_head_sha, manifest_hash, write_json_atomic
from bet.pipeline.portfolio_repeat_guard import (
    PortfolioRepeatGuardInput,
    evaluate_portfolio_repeat_guard,
    _normalize_team,
    _normalize_market,
    _extract_teams_from_event,
    _fuzzy_match,
)

DEFAULT_LEDGER_PATH = ROOT_DIR / "betting" / "journal" / "picks-ledger.csv"

REPEAT_LOSS_STEP = "s7_6_repeat_loss_check"

normalize_team = _normalize_team
normalize_market = _normalize_market
fuzzy_match = _fuzzy_match


def find_repeats(
    check_teams: list[str],
    recent_losses: list[dict],
    check_market: str | None = None,
) -> list[dict]:
    """Find matching team+market combinations in recent losses."""
    warnings = []
    check_teams_norm = [normalize_team(t) for t in check_teams]
    check_market_norm = normalize_market(check_market) if check_market else None

    for loss in recent_losses:
        for check_team in check_teams_norm:
            for loss_team in loss["teams_normalized"]:
                if fuzzy_match(check_team, loss_team):
                    if check_market_norm:
                        if not fuzzy_match(check_market_norm, loss["market_normalized"], 0.6):
                            continue

                    warnings.append({
                        "team": check_team,
                        "matched_team": loss_team,
                        "market": loss["market"],
                        "selection": loss["selection"],
                        "lost_on": loss["betting_day"],
                        "pick_id": loss["pick_id"],
                        "event": loss["event"],
                        "sport": loss["sport"],
                        "days_ago": loss["days_ago"],
                        "action": "HARD REJECT per §7.5 #14",
                    })

    return warnings


def find_repeat_loss_candidates(candidates: list[dict], recent_losses: list[dict]) -> list[dict]:
    findings: list[dict] = []
    seen = set()

    for candidate in candidates:
        market_name = (
            candidate.get("best_market", {}).get("name")
            or candidate.get("market_type")
            or candidate.get("market")
            or ""
        )
        home_team = candidate.get("home_team", "")
        away_team = candidate.get("away_team", "")
        teams = [team for team in (home_team, away_team) if team]
        if not teams or not market_name:
            continue

        matches = find_repeats(teams, recent_losses, market_name)
        for match in matches:
            event_key = f"{normalize_team(home_team)}|{normalize_team(away_team)}"
            match_key = (event_key, normalize_market(market_name), match.get("pick_id", ""))
            if match_key in seen:
                continue
            seen.add(match_key)
            findings.append(
                {
                    "fixture_id": candidate.get("fixture_id"),
                    "sport": candidate.get("sport", ""),
                    "home_team": home_team,
                    "away_team": away_team,
                    "competition": candidate.get("competition", ""),
                    "market_name": market_name,
                    "market_normalized": normalize_market(market_name),
                    "event_key": event_key,
                    "reason": "Same team+market lost within 48h — HARD REJECT",
                    "matched_loss": match,
                    "action": "HARD_REJECT",
                }
            )

    return findings


def load_recent_losses(ledger_path: Path, hours: int = 48) -> list[dict]:
    if not ledger_path.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    losses = []

    with open(ledger_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status", "").strip().lower() != "loss":
                continue

            betting_day = row.get("betting_day", "").strip()
            if not betting_day:
                continue
            try:
                day_dt = datetime.strptime(betting_day, "%Y-%m-%d") + timedelta(hours=23, minutes=59)
            except ValueError:
                continue

            if day_dt < cutoff:
                continue

            event = row.get("event", "").strip()
            teams = _extract_teams_from_event(event)

            losses.append({
                "betting_day": betting_day,
                "pick_id": row.get("pick_id", "").strip(),
                "event": event,
                "sport": row.get("sport", "").strip(),
                "market": row.get("market", "").strip(),
                "selection": row.get("selection", "").strip(),
                "teams": teams,
                "teams_normalized": [_normalize_team(t) for t in teams],
                "market_normalized": _normalize_market(row.get("market", "")),
                "days_ago": (datetime.now() - day_dt).days,
            })

    return losses


def load_gate_candidates(date: str, input_path: Path | None = None) -> tuple[list[dict], str]:
    run_root = os.environ.get("BET_PIPELINE_RUN_ROOT")
    run_id = os.environ.get("BET_PIPELINE_RUN_ID")

    if not run_root or not run_id:
        if input_path and input_path.exists():
            payload = json.loads(input_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                inner_cand = payload.get("candidates") or payload.get("payload", {}).get("candidates")
                if inner_cand:
                    return inner_cand, "input_json"
            return [], "input_json"
        raise ValueError("Missing pipeline environment variables")

    manifest_path = ROOT_DIR / "config" / "pipeline_manifest.json"
    manifest = load_pipeline_manifest(manifest_path)

    try:
        s5_path, s5_data = resolve_manifest_step_output(
            manifest=manifest,
            run_root=run_root,
            step_id="S5",
            betting_day=date,
            run_id=run_id,
            expected_artifact_type="S5_CONTEXT_RISK_CANDIDATE_SET_V2",
        )
    except Exception as exc:
        print(f"repeat guard input missing: failed to resolve S5 input: {exc}")
        sys.exit(5)

    candidates = s5_data.get("payload", {}).get("candidates") or s5_data.get("candidates") or []
    return candidates, str(s5_path)


def main():
    parser = argparse.ArgumentParser(description="Detect 48-hour repeat team+market losses.")
    parser.add_argument("--date", default=None, help="Betting day YYYY-MM-DD")
    parser.add_argument("--input", type=Path, default=None, help="Input path override")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH, help="Path to picks-ledger.csv")
    parser.add_argument("--hours", type=int, default=48, help="Lookback window in hours")
    parser.add_argument("--teams", type=str, default=None, help="Comma-separated team names to check")
    parser.add_argument("--shortlist", type=Path, default=None, help="Path to shortlist markdown")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--output", type=Path, default=None, help="Output path override")
    args = parser.parse_args()

    # Load recent losses Lookback history
    recent_losses = load_recent_losses(args.ledger, args.hours)

    if not args.date:
        # Ad-hoc non-pipeline mode
        sys.exit(0)

    # 1. Resolve candidates from S5 predecessor
    candidates, source_path = load_gate_candidates(args.date, args.input)

    if not candidates:
        print("repeat guard input empty: candidate list is empty")
        sys.exit(5)

    # 2. Evaluate Repeat / Portfolio guard logic
    guard_input = PortfolioRepeatGuardInput(
        candidates=candidates,
        history_snapshot=recent_losses,
        betting_day=args.date,
        run_id=os.environ.get("BET_PIPELINE_RUN_ID", "ad-hoc"),
        source_s5_hash=sha256_file(Path(source_path)) if Path(source_path).exists() else "dummy",
    )
    guard_result = evaluate_portfolio_repeat_guard(guard_input)

    # Determine status
    if guard_result.invalid_input:
        status_verdict = "BLOCK"
    elif len(guard_result.accepted) > 0:
        status_verdict = "PASS"
    else:
        status_verdict = "BLOCK"

    # Build typed output S6_PORTFOLIO_REPEAT_GUARD_V2
    s6_output_data = {
        "schema_version": 1,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "status": status_verdict,
        "betting_day": args.date,
        "run_id": os.environ.get("BET_PIPELINE_RUN_ID", "ad-hoc"),
        "created_at_utc": datetime.utcnow().isoformat() + "Z",
        "source_step": "S5",
        "source_s5_path": source_path,
        "source_s5_hash": sha256_file(Path(source_path)) if Path(source_path).exists() else "dummy",
        "source_git_sha": repo_head_sha(ROOT_DIR),
        "manifest_sha": manifest_hash(ROOT_DIR),
        "policy_version": "1.0",
        "history_snapshot_metadata": guard_result.history_snapshot_metadata,
        "input_candidate_count": len(candidates),
        "accepted": guard_result.accepted,
        "repeat_rejected": guard_result.repeat_rejected,
        "correlation_rejected": guard_result.correlation_rejected,
        "conflict_rejected": guard_result.conflict_rejected,
        "portfolio_rejected": guard_result.portfolio_rejected,
        "invalid_input": guard_result.invalid_input,
        "accounting": guard_result.accounting,
    }

    # Resolve output path
    output_path = args.output
    if not output_path:
        run_data_dir = os.environ.get("BET_PIPELINE_DATA_DIR")
        if run_data_dir:
            output_path = Path(run_data_dir) / f"repeat_loss_handoff_{args.date}.json"
        else:
            output_path = ROOT_DIR / "betting" / "data" / f"repeat_loss_handoff_{args.date}.json"

    # Immutable conflict detection
    if output_path.exists():
        try:
            existing_data = json.loads(output_path.read_text(encoding="utf-8"))
            if existing_data.get("betting_day") != args.date or existing_data.get("run_id") != os.environ.get("BET_PIPELINE_RUN_ID"):
                print("BLOCK: Conflicting immutable output exists")
                sys.exit(5)
        except Exception:
            print("BLOCK: Conflicting immutable output exists")
            sys.exit(5)

    # Write output JSON atomically
    write_json_atomic(output_path, s6_output_data)

    if guard_result.repeat_rejected:
        print("repeat signal conflict: same team+market lost within 48h — HARD REJECT")

    sys.exit(0 if status_verdict == "PASS" else 1)


def load_repeat_loss_handoff(date: str) -> dict | None:
    """Load the canonical S7.6 handoff from pipeline_runs."""
    from bet.db.connection import get_db
    from bet.db.repositories import PipelineRepo

    with get_db() as conn:
        record = PipelineRepo(conn).get_step(date, REPEAT_LOSS_STEP)

    if record is None:
        return None

    if record.get("status") != "completed":
        raise ValueError(
            f"S7.6 handoff for {date} is not complete (status={record.get('status')})"
        )

    payload = record.get("stats")
    if not isinstance(payload, dict):
        raise ValueError(f"Malformed S7.6 handoff for {date}: stats payload missing")
    if payload.get("date") != date:
        raise ValueError(f"Malformed S7.6 handoff for {date}: unexpected payload date")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError(f"Malformed S7.6 handoff for {date}: findings must be a list")
    if not isinstance(payload.get("repeat_loss_count"), int):
        raise ValueError(f"Malformed S7.6 handoff for {date}: repeat_loss_count must be an int")
    if payload.get("repeat_loss_count") != len(findings):
        raise ValueError(f"Malformed S7.6 handoff for {date}: repeat_loss_count does not match findings")
    return payload


if __name__ == "__main__":
    main()
