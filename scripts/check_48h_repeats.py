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
import hashlib
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any

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


def _record_pipeline_start(date: str) -> None:
    pass


def _persist_pipeline_handoff(date: str, handoff: dict) -> None:
    pass


class HistoryUnavailableError(Exception):
    pass


class HistoryMalformedError(Exception):
    pass


def _extract_gate_candidates(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        if not payload:
            raise ValueError("zero candidates")
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("zero candidates")
    
    # Check candidates
    for k in ("candidates", "valuations", "analyses"):
        if isinstance(payload.get(k), list):
            return payload[k]
            
    # Check gate_results
    if "gate_results" in payload and isinstance(payload["gate_results"], dict):
        gr = payload["gate_results"]
        res = []
        for k in ("approved", "extended_pool"):
            if isinstance(gr.get(k), list):
                res.extend(gr[k])
        return res
        
    # Check nested payload
    if "payload" in payload and isinstance(payload["payload"], dict):
        return _extract_gate_candidates(payload["payload"])
        
    raise ValueError("zero candidates")


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
                        "days_ago": loss.get("days_ago", 0),
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


def load_recent_losses_snapshot(
    ledger_path: Path,
    hours: int = 48,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    if as_of is None:
        as_of = datetime.now(UTC)
    elif as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    if not ledger_path.exists():
        raise HistoryUnavailableError("BLOCKED_HISTORY_UNAVAILABLE: History source file is missing")

    lookback_start = as_of - timedelta(hours=hours)
    records = []

    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise HistoryMalformedError("History file has no headers")
                
            for idx, row in enumerate(reader):
                # Verify non-empty and well-formed
                if not row.get("betting_day") or not row.get("status") or not row.get("event"):
                    raise HistoryMalformedError(f"Malformed row at index {idx}: missing required fields")

                status = row.get("status", "").strip().lower()
                if status != "loss":
                    continue

                betting_day = row.get("betting_day", "").strip()
                event = row.get("event", "").strip()
                pick_id = row.get("pick_id", "").strip()
                sport = row.get("sport", "").strip()
                market = row.get("market", "").strip()
                selection = row.get("selection", "").strip()

                settled_at_str = row.get("settled_at_utc") or row.get("result_recorded_at_utc") or row.get("settled_at")
                if settled_at_str:
                    try:
                        settled_at = datetime.fromisoformat(settled_at_str)
                        if settled_at.tzinfo is None:
                            settled_at = settled_at.replace(tzinfo=UTC)
                    except ValueError:
                        raise HistoryMalformedError(f"Malformed row at index {idx}: invalid timestamp '{settled_at_str}'")
                else:
                    try:
                        dt = datetime.strptime(betting_day, "%Y-%m-%d")
                        settled_at = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=UTC)
                    except ValueError:
                        raise HistoryMalformedError(f"Malformed row at index {idx}: invalid betting day '{betting_day}'")

                age_seconds = (as_of - settled_at).total_seconds()
                lookback_seconds = hours * 3600
                
                if age_seconds < 0:
                    raise HistoryMalformedError(f"Malformed row at index {idx}: future timestamp '{settled_at.isoformat()}'")

                if age_seconds > lookback_seconds:
                    continue

                teams = _extract_teams_from_event(event)
                records.append({
                    "betting_day": betting_day,
                    "pick_id": pick_id,
                    "event": event,
                    "sport": sport,
                    "market": market,
                    "selection": selection,
                    "settled_at_utc": settled_at.isoformat(),
                    "teams": teams,
                    "teams_normalized": [_normalize_team(t) for t in teams],
                    "market_normalized": _normalize_market(market),
                })
    except (HistoryUnavailableError, HistoryMalformedError):
        raise
    except Exception as exc:
        raise HistoryMalformedError(f"History file read error: {exc}")

    records.sort(key=lambda r: (r["settled_at_utc"], r["pick_id"]))
    records_json = json.dumps(records, sort_keys=True)
    snapshot_sha = hashlib.sha256(records_json.encode("utf-8")).hexdigest()

    return {
        "source_kind": "csv_ledger",
        "source_identity": ledger_path.name,
        "opened_read_only": True,
        "as_of_utc": as_of.isoformat(),
        "lookback_start_utc": lookback_start.isoformat(),
        "query_version": "1.0",
        "policy_version": "1.0",
        "row_count": len(records),
        "records": records,
        "snapshot_sha256": snapshot_sha,
    }


def load_recent_losses(ledger_path: Path, hours: int = 48) -> list[dict]:
    try:
        return load_recent_losses_snapshot(ledger_path, hours)["records"]
    except Exception:
        return []


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

    as_of = datetime.now(UTC)

    # 1. Load recent losses Lookback history with snapshot contract
    try:
        recent_losses_snapshot = load_recent_losses_snapshot(args.ledger, args.hours, as_of=as_of)
        recent_losses = recent_losses_snapshot["records"]
        history_snapshot_sha256 = recent_losses_snapshot["snapshot_sha256"]
    except HistoryUnavailableError as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: {exc}")
        sys.exit(5)
    except HistoryMalformedError as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: Malformed history row: {exc}")
        sys.exit(5)

    if not args.date:
        sys.exit(0)

    # 2. Resolve candidates from S5 predecessor
    try:
        candidates, source_path = load_gate_candidates(args.date, args.input)
    except Exception as exc:
        print(f"repeat guard input missing: {exc}")
        sys.exit(5)

    if not candidates:
        print("repeat guard input empty: candidate list is empty")
        sys.exit(5)

    # Load versioned policy
    policy_path = ROOT_DIR / "config" / "portfolio_policy.json"
    policy = {}
    if policy_path.exists():
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 3. Evaluate Repeat / Portfolio guard logic
    guard_input = PortfolioRepeatGuardInput(
        candidates=candidates,
        history_snapshot=recent_losses_snapshot,
        policy=policy,
        betting_day=args.date,
        run_id=os.environ.get("BET_PIPELINE_RUN_ID", "ad-hoc"),
        source_s5_hash=sha256_file(Path(source_path)) if Path(source_path).exists() else "dummy",
    )
    guard_result = evaluate_portfolio_repeat_guard(guard_input)

    # Determine status
    if guard_result.invalid_input:
        status_verdict = "BLOCK"
        concrete_status = "BLOCKED_INVALID_INPUT"
    elif len(guard_result.accepted) > 0:
        status_verdict = "PASS"
        concrete_status = "READY_FOR_S7"
    else:
        status_verdict = "PASS"  # Legitimate rejections are not failure
        concrete_status = "NO_ACTION_TERMINAL"

    # Build typed output S6_PORTFOLIO_REPEAT_GUARD_V2
    s6_output_data = {
        "schema_version": 1,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "status": status_verdict,
        "concrete_status": concrete_status,
        "betting_day": args.date,
        "run_id": os.environ.get("BET_PIPELINE_RUN_ID", "ad-hoc"),
        "created_at_utc": as_of.isoformat() + "Z",
        "source_step": "S5",
        "source_s5_path": source_path,
        "source_s5_hash": sha256_file(Path(source_path)) if Path(source_path).exists() else "dummy",
        "source_git_sha": repo_head_sha(ROOT_DIR),
        "manifest_sha": manifest_hash(ROOT_DIR),
        "policy_version": policy.get("policy_version", "1.0"),
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

    sys.exit(0 if concrete_status == "READY_FOR_S7" else 1)


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
