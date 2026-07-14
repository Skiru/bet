#!/usr/bin/env python3
"""48-hour repeat pick detector — finds same team+market losses in recent history.

Reads s6_history_snapshot.json and identifies picks in the last 48 hours with the same
team+market combination that resulted in a loss. These are flagged for the S7 gate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.pipeline.integration_artifacts import resolve_manifest_step_output
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.portfolio_repeat_guard import (
    PortfolioRepeatGuardInput,
    _extract_teams_from_event,
    _normalize_market,
    _normalize_team,
    evaluate_portfolio_repeat_guard,
    validate_history_snapshot_schema,
    validate_portfolio_policy_schema,
)
from bet.pipeline.run_evidence import (
    manifest_hash,
    repo_head_sha,
    sha256_file,
    write_json_atomic,
)
from bet.pipeline.runtime_paths import is_safe_run_path

DEFAULT_LEDGER_PATH = ROOT_DIR / "betting" / "journal" / "picks-ledger.csv"


class HistoryUnavailableError(Exception):
    pass


class HistoryMalformedError(Exception):
    pass


def load_recent_losses_snapshot(
    ledger_path: Path,
    hours: int = 48,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Load lookback loss records exactly once from CSV and freeze as snapshot."""
    if as_of is None:
        as_of = datetime.now(UTC)
    elif as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    if not ledger_path.exists():
        raise HistoryUnavailableError("BLOCKED_HISTORY_UNAVAILABLE: History source file is missing")

    lookback_start = as_of - timedelta(hours=hours)
    records = []

    try:
        with open(ledger_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise HistoryMalformedError("HISTORY_TIMESTAMP_INVALID: History file has no headers")

            for idx, row in enumerate(reader):
                if not row.get("betting_day") or not row.get("status") or not row.get("event"):
                    raise HistoryMalformedError(f"HISTORY_TIMESTAMP_INVALID: Malformed row at index {idx}: missing required fields")

                status = row.get("status", "").strip().lower()
                if status != "loss":
                    continue

                betting_day = row.get("betting_day", "").strip()
                event = row.get("event", "").strip()
                pick_id = row.get("pick_id", "").strip()
                sport = row.get("sport", "").strip()
                market = row.get("market", "").strip()
                selection = row.get("selection", "").strip()

                settled_at_str = row.get("settled_at_utc") or row.get("result_recorded_at_utc")
                if not settled_at_str:
                    raise HistoryMalformedError(f"HISTORY_TIMESTAMP_MISSING: Missing exact loss timestamp in row {idx}")

                try:
                    settled_at = datetime.fromisoformat(settled_at_str)
                    if settled_at.tzinfo is None:
                        settled_at = settled_at.replace(tzinfo=UTC)
                except ValueError:
                    raise HistoryMalformedError(f"HISTORY_TIMESTAMP_INVALID: Invalid timestamp format '{settled_at_str}' in row {idx}")

                # Guarantee correct subtraction in UTC for Warsaw DST boundaries
                as_of_utc = as_of.astimezone(UTC)
                settled_at_utc = settled_at.astimezone(UTC)
                age_seconds = (as_of_utc - settled_at_utc).total_seconds()
                lookback_seconds = hours * 3600

                if age_seconds < 0:
                    raise HistoryMalformedError(f"HISTORY_TIMESTAMP_INVALID: Future timestamp '{settled_at.isoformat()}' in row {idx}")

                # Half-open lookback filter [lookback_start, as_of)
                if age_seconds >= lookback_seconds:
                    continue

                teams = _extract_teams_from_event(event)
                records.append({
                    "betting_day": betting_day,
                    "pick_id": pick_id,
                    "event": event,
                    "sport": sport,
                    "market": market,
                    "selection": selection,
                    "settled_at_utc": settled_at_utc.isoformat(),
                    "teams": teams,
                    "teams_normalized": [_normalize_team(t) for t in teams],
                    "market_normalized": _normalize_market(market),
                })
    except (HistoryUnavailableError, HistoryMalformedError):
        raise
    except Exception as exc:
        raise HistoryMalformedError(f"HISTORY_TIMESTAMP_INVALID: History file read error: {exc}")

    records.sort(key=lambda r: (r["settled_at_utc"], r["pick_id"]))
    records_json = json.dumps(records, sort_keys=True)
    snapshot_sha = hashlib.sha256(records_json.encode("utf-8")).hexdigest()

    return {
        "schema_version": 1,
        "artifact_type": "S6_HISTORY_SNAPSHOT_V1",
        "as_of_utc": as_of.isoformat(),
        "lookback_start_utc": lookback_start.isoformat(),
        "boundary_policy": "half_open_inclusive_start",
        "source_identity": ledger_path.name,
        "opened_read_only": True,
        "query_version": "1.0",
        "policy_version": "1.0",
        "row_count": len(records),
        "records": records,
        "snapshot_sha256": snapshot_sha,
    }


def publish_immutable_or_reuse(target: Path, canonical_payload: dict[str, Any]) -> str:
    """Publishes a payload atomically and immutably, or reuses it if identical."""
    proposed_str = json.dumps(canonical_payload, sort_keys=True)
    proposed_hash = hashlib.sha256(proposed_str.encode("utf-8")).hexdigest()

    if target.exists():
        try:
            existing_data = json.loads(target.read_text(encoding="utf-8"))
            existing_str = json.dumps(existing_data, sort_keys=True)
            existing_hash = hashlib.sha256(existing_str.encode("utf-8")).hexdigest()
        except Exception:
            existing_hash = ""

        if existing_hash == proposed_hash:
            return "idempotent_reuse"
        else:
            raise ValueError(f"IMMUTABLE_ARTIFACT_CONFLICT: Conflicting immutable file exists at '{target}'")

    write_json_atomic(target, canonical_payload)
    return "atomic_create"


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
    parser.add_argument("--output", type=Path, default=None, help="Output path override")
    parser.add_argument("--history-snapshot", type=Path, default=None, help="Path to frozen history snapshot JSON")
    parser.add_argument("--history-snapshot-sha256", type=str, default=None, help="SHA-256 hash of frozen history snapshot JSON")
    parser.add_argument("--as-of-utc", type=str, default=None, help="Timezone-aware timestamp override")
    parser.add_argument("--policy", type=Path, default=None, help="Path to validated policy JSON")
    parser.add_argument("--policy-sha256", type=str, default=None, help="SHA-256 hash of validated policy JSON")
    args = parser.parse_args()

    run_root_raw = os.environ.get("BET_PIPELINE_RUN_ROOT") or str(ROOT_DIR)

    # Resolve and validate as_of timestamp
    if args.as_of_utc:
        try:
            as_of = datetime.fromisoformat(args.as_of_utc)
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=UTC)
        except Exception:
            print("BLOCK: Invalid --as-of-utc format")
            sys.exit(5)
    else:
        as_of = datetime.now(UTC)

    # 1. Load lookback history snapshot
    if args.history_snapshot:
        # Strict run path validation
        if not is_safe_run_path(args.history_snapshot, run_root_raw):
            print(f"BLOCK: history snapshot path is outside run root: {args.history_snapshot}")
            sys.exit(5)

        # Hash verification
        actual_sha = sha256_file(args.history_snapshot)
        if args.history_snapshot_sha256 and args.history_snapshot_sha256 != actual_sha:
            print(f"BLOCK: history snapshot hash mismatch: expected {args.history_snapshot_sha256}, got {actual_sha}")
            sys.exit(5)

        try:
            recent_losses_snapshot = json.loads(args.history_snapshot.read_text(encoding="utf-8"))
            history_obj = validate_history_snapshot_schema(recent_losses_snapshot)
        except Exception as exc:
            print(f"BLOCKED_HISTORY_UNAVAILABLE: Failed to validate history snapshot: {exc}")
            sys.exit(5)
    else:
        # Loading from raw CSV ledger directly (fallback/wrapper scenario)
        try:
            recent_losses_snapshot = load_recent_losses_snapshot(args.ledger, args.hours, as_of=as_of)
            history_obj = validate_history_snapshot_schema(recent_losses_snapshot)
        except HistoryUnavailableError as exc:
            print(f"BLOCKED_HISTORY_UNAVAILABLE: {exc}")
            sys.exit(5)
        except HistoryMalformedError as exc:
            print(f"BLOCKED_HISTORY_UNAVAILABLE: {exc}")
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

    # 3. Load validated policy
    if args.policy:
        if not is_safe_run_path(args.policy, run_root_raw) and args.policy != ROOT_DIR / "config" / "portfolio_policy.json":
            print(f"BLOCK: policy path is outside run root: {args.policy}")
            sys.exit(5)

        # Hash verification
        actual_sha = sha256_file(args.policy)
        if args.policy_sha256 and args.policy_sha256 != actual_sha:
            print(f"BLOCK: policy hash mismatch: expected {args.policy_sha256}, got {actual_sha}")
            sys.exit(5)

        try:
            p_data = json.loads(args.policy.read_text(encoding="utf-8"))
            policy_obj = validate_portfolio_policy_schema(p_data, actual_sha)
        except Exception as exc:
            print(f"BLOCKED_POLICY_INVALID: Failed to validate policy: {exc}")
            sys.exit(5)
    else:
        policy_path = ROOT_DIR / "config" / "portfolio_policy.json"
        p_data = {}
        p_sha = ""
        if policy_path.exists():
            try:
                p_sha = sha256_file(policy_path)
                p_data = json.loads(policy_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        try:
            policy_obj = validate_portfolio_policy_schema(p_data, p_sha)
        except Exception as exc:
            print(f"BLOCKED_POLICY_INVALID: {exc}")
            sys.exit(5)

    # 4. Evaluate Repeat / Portfolio guard logic
    guard_input = PortfolioRepeatGuardInput(
        candidates=candidates,
        history_snapshot=history_obj,
        policy=policy_obj,
        betting_day=args.date,
        run_id=os.environ.get("BET_PIPELINE_RUN_ID", "ad-hoc"),
        source_s5_hash=sha256_file(Path(source_path)) if Path(source_path).exists() else "dummy",
    )

    try:
        guard_result = evaluate_portfolio_repeat_guard(guard_input)
    except Exception as exc:
        print(f"BLOCKED_INVALID_INPUT: {exc}")
        sys.exit(5)

    # Determine status
    if guard_result.invalid_input:
        status_verdict = "BLOCK"
        concrete_status = "BLOCKED_INVALID_INPUT"
    elif len(guard_result.accepted) > 0:
        status_verdict = "PASS"
        concrete_status = "READY_FOR_S7"
    else:
        status_verdict = "PASS"
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
        "policy_version": policy_obj.policy_version,
        "history_snapshot_metadata": guard_result.history_snapshot_metadata,
        "input_candidate_count": len(candidates),
        "accepted": guard_result.accepted,
        "repeat_rejected": guard_result.repeat_rejected,
        "duplicate_rejected": guard_result.duplicate_rejected,
        "conflict_rejected": guard_result.conflict_rejected,
        "correlation_rejected": guard_result.correlation_rejected,
        "portfolio_rejected": guard_result.portfolio_rejected,
        "concentration_rejected": guard_result.concentration_rejected,
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

    # Immutable conflict detection and atomic publication
    try:
        publish_immutable_or_reuse(output_path, s6_output_data)
    except Exception as exc:
        print(f"BLOCK: Conflicting immutable output exists: {exc}")
        sys.exit(5)

    if guard_result.repeat_rejected:
        print("repeat signal conflict: same team+market lost within 48h — HARD REJECT")

    sys.exit(0 if concrete_status == "READY_FOR_S7" else 1)


if __name__ == "__main__":
    main()
