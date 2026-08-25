#!/usr/bin/env python3
"""S0 — Settlement step wrapper. Runs `scripts/settle_on_finish.py`."""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

try:
    from scripts.pipeline_steps._runner import run_scripts
except Exception:
    # Allow running this file directly (not as a package module)
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._runner import run_scripts

from bet.pipeline.integration_artifacts import write_script_evidence

CONTROLLED_OUTPUT_REASONS: tuple[tuple[str, str], ...] = (
    (r"\b(BLOCKED_[A-Z0-9_]+)\b", "TOKEN"),
    (r"no pending (?:picks|coupons)", "BLOCKED_NO_SETTLEMENT_DATA"),
    (r"nothing to settle", "BLOCKED_NO_SETTLEMENT_DATA"),
    (r"no settlement data", "BLOCKED_SETTLEMENT_DATA_UNAVAILABLE"),
    (r"settlement data unavailable", "BLOCKED_SETTLEMENT_DATA_UNAVAILABLE"),
    (r"live source unavailable", "BLOCKED_LIVE_SOURCE_UNAVAILABLE"),
    (r"provider unavailable", "BLOCKED_LIVE_SOURCE_UNAVAILABLE"),
)


def _payload(*, rc: int, runtime_mode: str, dry_run: bool, allow_write: bool, allow_live_network: bool) -> dict[str, object]:
    return {
        "settle_on_finish_rc": rc,
        "runtime_mode": runtime_mode,
        "dry_run": dry_run,
        "allow_write": allow_write,
        "allow_live_network": allow_live_network,
        "settlement_execution": "sandboxed_live_shadow_or_dry_run",
        "production_write": False,
    }


def _write_terminal_evidence(*, status: str, payload: dict[str, object], blocked_reasons: tuple[str, ...] = ()) -> Path:
    evidence_path = write_script_evidence(
        "S0",
        status=status,
        payload=payload,
        sources=("scripts/settle_on_finish.py",),
        evidence_refs=(),
        environ=os.environ,
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
        blocked_reasons=blocked_reasons,
    )
    if evidence_path is None:
        print("S0 wrapper failed closed: runtime context missing for canonical S0 script evidence", file=sys.stderr)
        raise SystemExit(70)
    return evidence_path


def _controlled_block_reasons(output: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for pattern, reason in CONTROLLED_OUTPUT_REASONS:
        if reason == "TOKEN":
            reasons.extend(re.findall(pattern, output))
            continue
        if re.search(pattern, output, flags=re.IGNORECASE):
            reasons.append(reason)
    deduped = tuple(dict.fromkeys(reasons))
    return deduped


def _replay_output(output: str) -> None:
    if output:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")


def main() -> None:
    p = argparse.ArgumentParser(description="S0 Settlement wrapper")
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    captured_stdout = io.StringIO()
    try:
        with redirect_stdout(captured_stdout):
            rc = run_scripts(
                ["settle_on_finish.py"],
                date=args.date,
                dry_run=args.dry_run,
                allow_write=args.allow_write,
                date_arg="--betting-day",
                runtime_mode=args.runtime_mode,
                betting_day=args.date,
                run_id=args.run_id,
                allow_live_network=args.allow_live_network,
            )
    except SystemExit:
        raise
    except Exception as exc:
        print(f"S0 wrapper runtime failure: {exc}", file=sys.stderr)
        _write_terminal_evidence(
            status="FAILED",
            payload={
                **_payload(
                    rc=-1,
                    runtime_mode=args.runtime_mode,
                    dry_run=args.dry_run,
                    allow_write=args.allow_write,
                    allow_live_network=args.allow_live_network,
                ),
                "error": str(exc),
            },
            blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
        )
        raise SystemExit(1) from exc

    output = captured_stdout.getvalue()
    _replay_output(output)

    payload = _payload(
        rc=rc,
        runtime_mode=args.runtime_mode,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        allow_live_network=args.allow_live_network,
    )

    if rc == 0:
        _write_terminal_evidence(status="PASS", payload=payload)
        raise SystemExit(0)

    blocked_reasons = _controlled_block_reasons(output)
    if blocked_reasons:
        _write_terminal_evidence(status="BLOCK", payload=payload, blocked_reasons=blocked_reasons)
        raise SystemExit(rc)

    _write_terminal_evidence(
        status="FAILED",
        payload=payload,
        blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
    )
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
