#!/usr/bin/env python3
"""Materialize the current-run S1e canonical event universe ledger."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.pipeline.artifact_io import publish_run_artifact
from bet.pipeline.event_accounting import EventAccountingLedger, deduplicate_events
from bet.pipeline.integration_artifacts import script_evidence_path
from bet.pipeline.run_evidence import sha256_file
from bet.pipeline.runtime_modes import parse_runtime_mode
from scripts.pipeline_steps._runner import resolve_child_runtime_env
from scripts.pipeline_steps._script_evidence import write_terminal_script_evidence_or_fail

SCRIPTS: list[str] = []


def _run_file(path: Path, run_root: Path) -> Path:
    resolved = path.resolve(strict=True)
    resolved.relative_to(run_root.resolve(strict=True))
    if not resolved.is_file() or path.is_symlink():
        raise ValueError("S1 source is not a current-run regular file")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description="S1e canonical event universe ledger")
    parser.add_argument("--date", "--betting-day", dest="date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runtime-mode", default="DRY_RUN")
    parser.add_argument("--allow-live-network", action="store_true", default=False)
    parser.add_argument("--allow-write", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()
    mode = parse_runtime_mode(args.runtime_mode)
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ, runtime_mode=mode, betting_day=args.date, run_id=args.run_id, run_root=None
    )
    run_root = Path(child_env["BET_PIPELINE_RUN_ROOT"])
    blocked: list[str] = []
    s1_evidence: Path | None = None
    source_path: Path | None = None
    events: list[dict] = []
    try:
        evidence_candidate = script_evidence_path("S1", child_env)
        if evidence_candidate is None:
            raise ValueError("canonical S1 evidence path unavailable")
        s1_evidence = _run_file(evidence_candidate, run_root)
        evidence = json.loads(s1_evidence.read_text(encoding="utf-8"))
        if any((
            evidence.get("artifact_type") != "SCRIPT_EVIDENCE",
            evidence.get("step_id") != "S1",
            evidence.get("status") != "PASS",
            evidence.get("betting_day") != args.date,
            evidence.get("run_id") != args.run_id,
        )):
            raise ValueError("canonical S1 evidence binding invalid")
        source_value = (evidence.get("payload") or {}).get("market_matrix_path")
        if not isinstance(source_value, str) or not source_value:
            raise ValueError("canonical S1 market matrix binding missing")
        source_path = _run_file(Path(source_value), run_root)
        source = json.loads(source_path.read_text(encoding="utf-8"))
        raw_events = source.get("events")
        if not isinstance(raw_events, list):
            raise ValueError("canonical S1 event list invalid")
        events = deduplicate_events(raw_events)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        blocked.append("BLOCKED_S1E_CANONICAL_S1_INVALID")
        print(f"BLOCKED_S1E_CANONICAL_S1_INVALID: {exc}")

    output = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"{args.date}_s1e_event_universe.json"
    output_sha: str | None = None
    if not blocked:
        artifact = {
            "schema_version": 1,
            "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
            "betting_day": args.date,
            "run_id": args.run_id,
            "source_s1_evidence_path": str(s1_evidence),
            "source_s1_evidence_sha256": sha256_file(s1_evidence),
            "source_s1_path": str(source_path),
            "source_s1_sha256": sha256_file(source_path),
            "after_dedup_count": len(events),
            "canonical_event_ids": [event["canonical_event_id"] for event in events],
            "events": events,
            "zero_event_universe": not events,
            "discovery_attempted": True,
        }
        receipt = publish_run_artifact(
            run_root=run_root,
            target=output,
            payload=artifact,
            betting_day=args.date,
            run_id=args.run_id,
            artifact_type="S1E_EVENT_UNIVERSE_LEDGER",
        )
        output_sha = receipt.sha256
        EventAccountingLedger.initialize(run_root, output, betting_day=args.date, run_id=args.run_id)

    payload = {
        "s1e_json_output": str(output) if not blocked else None,
        "s1e_output_sha256": output_sha,
        "after_dedup_count": len(events),
        "outcome": "NO_ACTION_TERMINAL" if not blocked and not events else ("PASS" if not blocked else "BLOCKED"),
        "runtime_path_source": runtime_path_source,
        "child_run_root": child_env["BET_PIPELINE_RUN_ROOT"],
        "child_artifact_dir": child_env["BET_PIPELINE_ARTIFACT_DIR"],
    }
    write_terminal_script_evidence_or_fail(
        step_id="S1e",
        status="BLOCK" if blocked else "PASS",
        payload=payload,
        sources=("S1:current-run",),
        child_env=child_env,
        blocked_reasons=tuple(blocked),
        no_pick_edge_stake_coupon_emitted=True,
    )
    raise SystemExit(5 if blocked else 0)


if __name__ == "__main__":
    main()
