#!/usr/bin/env python3
"""Validate `tipster-reader`'s readings and write TIPSTER_CLAIMS for the day.

Usage:
    python3 scripts/simple/save_tipster_claims.py --date 2026-09-03 \
        --readings /tmp/readings.json

    # or on stdin, which is how the orchestrator usually has it
    python3 scripts/simple/save_tipster_claims.py --date 2026-09-03 -

The agent has no Write tool, by construction: an agent that could write the
artifact it is judged on could quietly launder a bad reading into the coupon.
It returns JSON as text, the orchestrator saves it, and this script is the only
thing that turns it into `<date>_tipster_claims.json`.

**Nothing is trusted.** Every reading must name a pick TIPSTERS actually
collected, with the claim byte-identical, and must use the closed market and
direction vocabulary -- see `bet.simple_stats.tipster_claims`. Readings that
fail are dropped and counted, never repaired.

No network, no DB, no provider calls, no probability computed anywhere. Safe to
re-run: it overwrites one artifact and reads two.

Exit codes: 0 = written, 1 = written but readings were rejected, 2 = bad input.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.simple_stats.artifact_io import write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import TipsterSignalV1  # noqa: E402
from bet.simple_stats.tipster_claims import validate_readings  # noqa: E402


def _extract_json(text: str) -> dict:
    """The agent's object, whether it arrived bare or in a fenced block.

    Tolerated because the agent is instructed to emit one fenced ```json block
    and prose above it, and stripping that here is cheaper than making every
    caller do it. Anything that is not a JSON object with a `readings` list is
    a bad input and says so.
    """
    text = text.strip()
    if "```" in text:
        blocks = []
        parts = text.split("```")
        # Odd indices are inside fences; drop an optional `json` language tag.
        for chunk in parts[1::2]:
            chunk = chunk.strip()
            if chunk.lower().startswith("json"):
                chunk = chunk[4:].strip()
            blocks.append(chunk)
        for chunk in reversed(blocks):
            try:
                parsed = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "readings" in parsed:
                return parsed
        raise ValueError("no fenced JSON object carrying `readings` found")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", required=True, help="Betting day, YYYY-MM-DD")
    parser.add_argument(
        "--readings",
        required=True,
        help="Path to the agent's JSON, or '-' to read it from stdin",
    )
    parser.add_argument("--tipster-signal", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    run_dir = Path(args.output_dir) if args.output_dir else ROOT / "runs" / args.date
    signal_path = Path(args.tipster_signal) if args.tipster_signal else (
        run_dir / f"{args.date}_tipster_signal.json"
    )
    if not signal_path.exists():
        print(
            json.dumps({"error": f"tipster signal not found: {signal_path}"}),
            file=sys.stderr,
        )
        sys.exit(2)

    raw_text = sys.stdin.read() if args.readings == "-" else Path(
        args.readings
    ).read_text(encoding="utf-8")
    try:
        raw = _extract_json(raw_text)
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"unreadable readings: {exc}"}), file=sys.stderr)
        sys.exit(2)

    signal = TipsterSignalV1.model_validate_json(
        signal_path.read_text(encoding="utf-8")
    )
    claims = validate_readings(
        raw, signal, generated_at=datetime.now(timezone.utc).isoformat()
    )

    out_path = run_dir / f"{args.date}_tipster_claims.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out_path, claims.model_dump(mode="json"))

    summary = {
        "step": "simple_stats:TIPSTER_CLAIMS",
        "verdict": "OK" if not claims.readings_rejected else "PARTIAL",
        "metrics": {
            "run_id": claims.run_id,
            "date": claims.date,
            "picks_in_signal": claims.picks_in_signal,
            "readings_accepted": claims.readings_accepted,
            "readings_rejected": claims.readings_rejected,
            "rejected_by_reason": claims.rejected_by_reason,
            "legs_total": claims.legs_total,
            "legs_unreadable": claims.legs_unreadable,
            # How often the agent read a claim differently from the regex path.
            # High is expected and is the reason this step exists; near zero
            # would mean the agent is buying nothing and can be dropped.
            "parser_disagreements": claims.parser_disagreements,
            "output_path": str(out_path),
        },
        "issues": [
            {"level": "warning", "message": f"{count}x rejected: {reason}"}
            for reason, count in claims.rejected_by_reason.items()
        ],
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary, ensure_ascii=False)}")
    sys.exit(1 if claims.readings_rejected else 0)


if __name__ == "__main__":
    main()
