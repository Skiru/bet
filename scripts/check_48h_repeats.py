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
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.pipeline.canonical_continuity import bind_candidate_identity, validate_exact_partition
from bet.pipeline.artifact_io import (
    ArtifactPublishError,
    publish_immutable_json_blob,
    publish_run_artifact,
)
from bet.pipeline.portfolio_repeat_guard import (
    PortfolioRepeatGuardInput,
    evaluate_portfolio_repeat_guard,
    validate_history_snapshot_schema,
    validate_portfolio_policy_schema,
)
from bet.pipeline.run_evidence import (
    manifest_hash,
    repo_head_sha,
    sha256_file,
)
from bet.pipeline.runtime_paths import is_safe_run_path


class HistoryUnavailableError(Exception):
    pass


class HistoryMalformedError(Exception):
    pass


DEFAULT_LEDGER_PATH = ROOT_DIR / "betting" / "journal" / "picks-ledger.csv"
DATA_DIR = ROOT_DIR / "betting" / "data"
REPEAT_LOSS_STEP = "S6_REPEAT_LOSS_GUARD"


def normalize_team(name: str) -> str:
    from bet.pipeline.portfolio_repeat_guard import _normalize_team
    return _normalize_team(name)


def normalize_market(market: str) -> str:
    from bet.pipeline.portfolio_repeat_guard import _normalize_market
    return _normalize_market(market)


def fuzzy_match(left: str, right: str, threshold: float = 0.75) -> bool:
    return SequenceMatcher(None, str(left), str(right)).ratio() >= threshold


def _extract_gate_candidates(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        candidates = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        inner = payload.get("payload")
        if isinstance(inner, dict):
            return _extract_gate_candidates(inner)
        gate = payload.get("gate_results")
        if isinstance(gate, dict):
            candidates = [
                item
                for key in ("approved", "extended_pool")
                for item in gate.get(key, [])
                if isinstance(item, dict)
            ]
        else:
            candidates = []
            for key in ("candidates", "valuations", "analyses", "accepted"):
                if isinstance(payload.get(key), list):
                    candidates = [item for item in payload[key] if isinstance(item, dict)]
                    break
    else:
        candidates = []
    if not candidates:
        raise ValueError("zero candidates")
    return candidates


def load_recent_losses(
    path: Path = DEFAULT_LEDGER_PATH,
    hours: int = 48,
    *,
    as_of: datetime | None = None,
) -> list[dict[str, Any]]:
    """Compatibility reader for legacy consumers; production S6 uses snapshots."""
    ledger_path = Path(path)
    if not ledger_path.is_file():
        return []
    as_of = as_of or datetime.now(UTC)
    if as_of.tzinfo is None:
        raise HistoryMalformedError("HISTORY_AS_OF_MUST_BE_TIMEZONE_AWARE")
    start = as_of - timedelta(hours=hours)
    losses: list[dict[str, Any]] = []
    with ledger_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("status") or "").strip().casefold() != "loss":
                continue
            timestamp = row.get("settled_at_utc") or row.get("result_recorded_at_utc")
            if timestamp:
                try:
                    settled = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    if settled.tzinfo is None:
                        settled = settled.replace(tzinfo=UTC)
                except ValueError as exc:
                    raise HistoryMalformedError("HISTORY_TIMESTAMP_INVALID") from exc
            else:
                day = row.get("betting_day")
                if not day:
                    raise HistoryMalformedError("HISTORY_TIMESTAMP_MISSING")
                settled = datetime.fromisoformat(f"{day}T23:59:59+00:00")
            if not start <= settled < as_of:
                continue
            event = str(row.get("event") or "")
            from bet.pipeline.portfolio_repeat_guard import _extract_teams_from_event
            teams = _extract_teams_from_event(event)
            losses.append(
                {
                    **row,
                    "teams": teams,
                    "teams_normalized": [normalize_team(team) for team in teams],
                    "market_normalized": normalize_market(row.get("market") or ""),
                    "lost_on": row.get("betting_day") or settled.date().isoformat(),
                }
            )
    return losses


def find_repeats(teams: list[str], losses: list[dict[str, Any]], market: str) -> list[dict[str, Any]]:
    normalized_market = normalize_market(market)
    result: list[dict[str, Any]] = []
    for loss in losses:
        if normalize_market(loss.get("market") or "") != normalized_market:
            continue
        loss_teams = loss.get("teams_normalized")
        if not isinstance(loss_teams, list):
            loss_teams = [
                loss.get("team_normalized")
                or normalize_team(loss.get("team") or "")
            ]
        if any(
            fuzzy_match(normalize_team(team), str(loss_team))
            for team in teams
            for loss_team in loss_teams
        ):
            result.append(loss)
    return result


def find_repeat_loss_candidates(
    candidates: list[dict[str, Any]], losses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for candidate in candidates:
        best = candidate.get("best_market") if isinstance(candidate.get("best_market"), dict) else {}
        market = candidate.get("market") or candidate.get("market_type") or best.get("name") or ""
        matches = find_repeats(
            [candidate.get("home_team") or "", candidate.get("away_team") or ""],
            losses,
            market,
        )
        if matches:
            findings.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "fixture_id": candidate.get("fixture_id"),
                    "home_team": candidate.get("home_team"),
                    "away_team": candidate.get("away_team"),
                    "event_key": f"{normalize_team(candidate.get('home_team') or '')}|{normalize_team(candidate.get('away_team') or '')}",
                    "market_name": market,
                    "market_normalized": normalize_market(market),
                    "matches": matches,
                }
            )
    return findings


def load_repeat_loss_handoff(date: str) -> dict[str, Any] | None:
    path = Path(os.environ.get("BET_PIPELINE_DATA_DIR", ROOT_DIR / "betting" / "data")) / f"repeat_loss_handoff_{date}.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(value, dict):
            value["artifact_path"] = str(path)
            return value

    # Read-only compatibility fallback for the pre-canonical coupon builder.
    # Strict S7 consumes the hash-bound S6 artifact directly and never reaches it.
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo

        with get_db() as connection:
            repository = PipelineRepo(connection)
            for step in (REPEAT_LOSS_STEP, "s7_6_repeat_loss_check"):
                receipt = repository.get_step(date, step)
                if receipt and receipt.get("status") == "completed":
                    stats = receipt.get("stats")
                    if isinstance(stats, dict):
                        return stats
    except Exception:
        return None
    return None


def load_recent_losses_snapshot(
    ledger_path: Path, hours: int = 48, as_of: datetime | None = None
) -> dict[str, Any]:
    """Create the strict, hash-bound half-open history snapshot."""
    if as_of is None:
        raise ValueError("BLOCKED_RUN_AS_OF_BINDING_MISMATCH")
    if as_of.tzinfo is None:
        raise ValueError("BLOCKED_RUN_AS_OF_BINDING_MISMATCH")
    if not Path(ledger_path).is_file():
        raise HistoryUnavailableError("BLOCKED_HISTORY_UNAVAILABLE")
    start = as_of - timedelta(hours=hours)
    records: list[dict[str, Any]] = []
    with Path(ledger_path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise HistoryMalformedError("HISTORY_TIMESTAMP_INVALID")
        for index, row in enumerate(reader):
            if str(row.get("status") or "").strip().casefold() != "loss":
                continue
            timestamp = row.get("settled_at_utc") or row.get("result_recorded_at_utc")
            if not timestamp:
                raise HistoryMalformedError(f"HISTORY_TIMESTAMP_MISSING: row {index}")
            try:
                settled = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HistoryMalformedError(f"HISTORY_TIMESTAMP_INVALID: row {index}") from exc
            if settled.tzinfo is None:
                raise HistoryMalformedError(f"HISTORY_TIMESTAMP_INVALID: row {index}")
            if settled > as_of:
                raise HistoryMalformedError(f"HISTORY_TIMESTAMP_INVALID: future row {index}")
            if not start <= settled < as_of:
                continue
            records.append({**row, "settled_at_utc": settled.astimezone(UTC).isoformat()})
    records.sort(key=lambda item: (item["settled_at_utc"], item.get("pick_id") or ""))
    snapshot_sha = hashlib.sha256(json.dumps(records, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "artifact_type": "S6_HISTORY_SNAPSHOT_V1",
        "as_of_utc": as_of.astimezone(UTC).isoformat(),
        "lookback_start_utc": start.astimezone(UTC).isoformat(),
        "boundary_policy": "[lookback_start_utc,as_of_utc)",
        "source_identity": Path(ledger_path).name,
        "opened_read_only": True,
        "query_version": "2.0",
        "policy_version": "1.0",
        "records": records,
        "row_count": len(records),
        "snapshot_sha256": snapshot_sha,
    }


def _record_pipeline_start(date: str) -> None:
    """Record the bounded legacy adapter receipt (never used by strict S6)."""
    from bet.db.connection import get_db
    from bet.db.repositories import PipelineRepo

    with get_db() as connection:
        PipelineRepo(connection).start_step(date, REPEAT_LOSS_STEP)


def _persist_pipeline_handoff(date: str, payload: dict[str, Any]) -> None:
    """Persist the legacy dry-run receipt for consumers that still read the DB."""
    from bet.db.connection import get_db
    from bet.db.repositories import PipelineRepo

    with get_db() as connection:
        PipelineRepo(connection).complete_step(date, REPEAT_LOSS_STEP, payload)


def publish_immutable_or_reuse(target: Path, canonical_payload: dict[str, Any]) -> str:
    """Publish with a real create-if-absent operation safe under concurrency."""
    run_root = Path(os.environ["BET_PIPELINE_RUN_ROOT"])
    if not all(
        key in canonical_payload
        for key in ("schema_version", "artifact_type", "betting_day", "run_id")
    ):
        receipt = publish_immutable_json_blob(
            run_root=run_root,
            target=target,
            payload=canonical_payload,
        )
        return "idempotent_reuse" if receipt.already_present else "atomic_create"
    try:
        receipt = publish_run_artifact(
            run_root=run_root,
            target=target,
            payload=canonical_payload,
            betting_day=str(canonical_payload["betting_day"]),
            run_id=str(canonical_payload["run_id"]),
            artifact_type=str(canonical_payload["artifact_type"]),
            immutable=True,
        )
    except ArtifactPublishError as exc:
        raise ValueError(f"IMMUTABLE_ARTIFACT_CONFLICT: {exc}") from exc
    return "idempotent_reuse" if receipt.already_present else "atomic_create"


def main():
    parser = argparse.ArgumentParser(description="Strict S6 Repeat Detector Worker.")
    parser.add_argument("--date", help="Betting day YYYY-MM-DD")
    parser.add_argument("--run-id")
    parser.add_argument("--run-as-of-utc")
    parser.add_argument("--validated-s5", type=Path)
    parser.add_argument("--validated-s5-sha256")
    parser.add_argument("--history-snapshot", type=Path)
    parser.add_argument("--history-snapshot-sha256")
    parser.add_argument("--policy-snapshot", type=Path)
    parser.add_argument("--policy-snapshot-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker-contract-version")
    parser.add_argument("--input", type=Path, help="Legacy dry-run input adapter")
    parser.add_argument("--ledger", type=Path, help="Legacy dry-run ledger adapter")
    parser.add_argument("--format", choices=("json",), help=argparse.SUPPRESS)

    # If any required arg is missing or invalid, fail closed as of REQ-V6-WORKER-001
    try:
        args = parser.parse_args()
    except SystemExit:
        print("BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING")
        sys.exit(5)

    legacy_input = args.input
    if legacy_input is None and args.ledger is not None and args.date:
        legacy_input = DATA_DIR / f"{args.date}_s7_gate_results.json"

    if legacy_input is not None and args.validated_s5 is None:
        runtime_mode = str(os.environ.get("BET_PIPELINE_RUNTIME_MODE") or "DRY_RUN").upper()
        protected_roots = (
            ROOT_DIR / "betting" / "data",
            ROOT_DIR / "betting" / "journal",
            ROOT_DIR / "reports",
            ROOT_DIR / "src",
            ROOT_DIR / "config",
        )
        resolved_input = legacy_input.resolve(strict=False)
        if runtime_mode != "DRY_RUN" or any(
            resolved_input == root.resolve() or resolved_input.is_relative_to(root.resolve())
            for root in protected_roots
        ):
            print("BLOCKED_LEGACY_REPEAT_ADAPTER_PATH_OR_MODE")
            sys.exit(5)
        try:
            if not args.date:
                raise ValueError("date is required")
            _record_pipeline_start(args.date)
            payload = json.loads(legacy_input.read_text(encoding="utf-8"))
            candidates = _extract_gate_candidates(payload)
            legacy_as_of = datetime.fromisoformat(f"{args.date}T00:00:00+00:00") + timedelta(days=1)
            losses = load_recent_losses(
                args.ledger or DEFAULT_LEDGER_PATH,
                hours=48,
                as_of=legacy_as_of,
            )
            raw_findings = find_repeat_loss_candidates(candidates, losses)
            findings = [
                {
                    **finding,
                    "action": "HARD_REJECT",
                    "matched_loss": finding["matches"][0],
                }
                for finding in raw_findings
            ]
            output_path = args.output or DATA_DIR / f"repeat_loss_handoff_{args.date}.json"
            output = {
                "schema_version": 1,
                "artifact_type": "LEGACY_S6_REPEAT_HANDOFF",
                "date": args.date,
                "step": "s7_6_repeat_loss_check",
                "window_hours": 48,
                "candidate_source": "json",
                "artifact_path": str(output_path),
                "checked_candidates_count": len(candidates),
                "recent_losses_count": len(losses),
                "clear": not findings,
                "repeat_loss_count": len(findings),
                "findings": findings,
                "checked_at": datetime.now(UTC).isoformat(),
            }
            from bet.pipeline.run_evidence import write_json_atomic
            write_json_atomic(output_path, output)
            _persist_pipeline_handoff(args.date, output)
        except Exception as exc:
            print(f"BLOCKED_LEGACY_REPEAT_ADAPTER_INVALID: {exc}")
            sys.exit(5)
        sys.exit(1 if findings else 0)

    run_root_raw = os.environ.get("BET_PIPELINE_RUN_ROOT")
    if not run_root_raw:
        print("BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING: Missing run root environment")
        sys.exit(5)

    # Validate that run ID is not ad-hoc
    if not args.run_id or args.run_id in ("ad-hoc", "dummy", "placeholder", ""):
        print("BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING: Invalid or ad-hoc run ID")
        sys.exit(5)

    # Check that all strict arguments are populated and valid
    for name, val in [
        ("date", args.date),
        ("run_as_of_utc", args.run_as_of_utc),
        ("validated_s5", args.validated_s5),
        ("validated_s5_sha256", args.validated_s5_sha256),
        ("history_snapshot", args.history_snapshot),
        ("history_snapshot_sha256", args.history_snapshot_sha256),
        ("policy_snapshot", args.policy_snapshot),
        ("policy_snapshot_sha256", args.policy_snapshot_sha256),
        ("output", args.output),
        ("worker_contract_version", args.worker_contract_version),
    ]:
        if not val or val in ("dummy", "dummy_s5_hash", "placeholder", ""):
            print(f"BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING: {name} is missing or has dummy value")
            sys.exit(5)

    if args.worker_contract_version != "1.0":
        print("BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING: Invalid worker contract version")
        sys.exit(5)

    # Require every path to be inside the exact current run root
    for path_arg in (args.validated_s5, args.history_snapshot, args.policy_snapshot, args.output):
        if not is_safe_run_path(path_arg, run_root_raw):
            print(f"BLOCK: path is outside run root: {path_arg}")
            sys.exit(5)

    # Validate all supplied hashes
    for path, expected_hash, name in [
        (args.validated_s5, args.validated_s5_sha256, "S5"),
        (args.history_snapshot, args.history_snapshot_sha256, "History snapshot"),
        (args.policy_snapshot, args.policy_snapshot_sha256, "Policy snapshot"),
    ]:
        if not path.exists():
            print(f"BLOCK: {name} path does not exist")
            sys.exit(5)
        actual = sha256_file(path)
        if actual != expected_hash:
            print(f"BLOCK: {name} hash mismatch. Expected {expected_hash}, got {actual}")
            sys.exit(5)

    # Load S5 candidates
    try:
        s5_data = json.loads(args.validated_s5.read_text(encoding="utf-8"))
        raw_candidates = s5_data.get("payload", {}).get("candidates") or s5_data.get("candidates") or []
        candidates = [bind_candidate_identity(candidate) for candidate in raw_candidates]
        if not candidates:
            print("repeat guard input empty: candidate list is empty")
            sys.exit(5)
    except Exception as exc:
        print(f"BLOCKED_INVALID_INPUT: Failed to parse S5: {exc}")
        sys.exit(5)

    # Load frozen snapshots
    try:
        recent_losses_snapshot = json.loads(args.history_snapshot.read_text(encoding="utf-8"))
        history_obj = validate_history_snapshot_schema(recent_losses_snapshot)
    except Exception as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: Failed to validate history snapshot: {exc}")
        sys.exit(5)

    try:
        p_data = json.loads(args.policy_snapshot.read_text(encoding="utf-8"))
        policy_obj = validate_portfolio_policy_schema(p_data, args.policy_snapshot_sha256)
    except Exception as exc:
        print(f"BLOCKED_POLICY_INVALID: Failed to validate policy: {exc}")
        sys.exit(5)

    # Calculate run clock
    try:
        as_of = datetime.fromisoformat(args.run_as_of_utc.replace("Z", "+00:00"))
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=UTC)
    except Exception:
        print("BLOCK: Invalid --run-as-of-utc format")
        sys.exit(5)

    guard_input = PortfolioRepeatGuardInput(
        candidates=candidates,
        history_snapshot=history_obj,
        policy=policy_obj,
        betting_day=args.date,
        run_id=args.run_id,
        source_s5_hash=args.validated_s5_sha256,
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

    # Build S6 output dictionary with strict worker fields
    s6_output_data = {
        "schema_version": 2,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "status": status_verdict,
        "concrete_status": concrete_status,
        "betting_day": args.date,
        "run_id": args.run_id,
        "created_at_utc": as_of.isoformat().replace("+00:00", "Z"),
        "source_step": "S5",
        "source_s5_path": str(args.validated_s5),
        "source_s5_sha256": args.validated_s5_sha256,
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

        # New contract-mandated fields
        "worker_contract_version": args.worker_contract_version,
        "worker_script_sha256": sha256_file(Path(__file__)),
        "validated_inputs": {
            "s5_hash": args.validated_s5_sha256,
            "history_hash": args.history_snapshot_sha256,
            "policy_hash": args.policy_snapshot_sha256,
        },
        "run_as_of_utc": args.run_as_of_utc,
        "result_sha256_precursor": hashlib.sha256(json.dumps(guard_result.accepted, sort_keys=True).encode("utf-8")).hexdigest(),
    }

    s6_output_data["accounting"] = validate_exact_partition(
        candidates,
        {
            "accepted": guard_result.accepted,
            "repeat_rejected": guard_result.repeat_rejected,
            "duplicate_rejected": guard_result.duplicate_rejected,
            "conflict_rejected": guard_result.conflict_rejected,
            "correlation_rejected": guard_result.correlation_rejected,
            "concentration_rejected": guard_result.concentration_rejected,
            "invalid_input": guard_result.invalid_input,
        },
    )

    # Immutable conflict detection and atomic publication
    try:
        publish_immutable_or_reuse(args.output, s6_output_data)
    except Exception as exc:
        print(f"BLOCK: Conflicting immutable output exists: {exc}")
        sys.exit(5)

    if guard_result.repeat_rejected:
        print("repeat signal conflict: same team+market lost within 48h — HARD REJECT")

    sys.exit(0 if status_verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
