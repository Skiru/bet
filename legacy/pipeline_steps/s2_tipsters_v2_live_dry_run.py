#!/usr/bin/env python3
"""Ad-hoc CLI for a live tipster dry-run. Thin wrapper; no logic of its own.

Everything this used to implement -- the review gate, entrypoint resolution,
fetch/parse orchestration -- now lives in :mod:`bet.tipsters.live`, because the
production pipeline has to call it and shelling out to a file under ``legacy/``
to feed a production column would make the quarantine meaningless. Two CLIs
over one implementation:

* ``scripts/simple/run_tipsters.py`` -- the betting-day step. Compliance gate
  only, no bypass, output feeds the stats sheet's agreement column.
* this script -- the operator's "are the scrapers still alive" tool. Keeps the
  ``--operator-risk-json`` escape hatch, whose own acknowledgement file states
  the run "may ignore robots.txt" and "is not production-grade or certified".
  That is why the pipeline path does not expose it.

Still compliance-first: no stealth, no CAPTCHA/Cloudflare bypass, no auth, no
premium, no private APIs, no bookmaker redirects. Output is evidence, never a bet.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bet.tipsters.contracts import ExtractionResult  # noqa: E402
from bet.tipsters.handoff import write_handoff_artifact  # noqa: E402
from bet.tipsters.live import (  # noqa: E402
    fetch_extract_source,
    load_review_file,
    resolve_target_entrypoints,
    review_allows_source,
    review_gate_details,
)
from bet.tipsters.source_registry import CERTIFIED_SHADOW_SOURCE_IDS, SOURCES  # noqa: E402
from bet.tipsters.storage import build_payload, persist_sqlite, write_json_artifact  # noqa: E402

# Re-exported under their historical private name so callers and tests that grew
# up against this script keep working after the move.
_review_gate_details = review_gate_details

__all__ = [
    "_review_gate_details",
    "review_gate_details",
    "review_allows_source",
    "resolve_target_entrypoints",
    "fetch_extract_source",
    "main",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Run date in YYYY-MM-DD")
    parser.add_argument("--terms-reviewed-json", required=True, type=Path, help="Local JSON documenting robots/terms/public-only review per source")
    parser.add_argument("--source", action="append", choices=list(SOURCES.keys()), help="Source id to live dry-run. Repeatable. Defaults to forebet+predictz.")
    parser.add_argument("--max-pages-per-source", type=int, default=1, help="Hard cap including entrypoint and discovered detail pages")
    parser.add_argument("--timeout-seconds", type=float, default=12.0)
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--sqlite-db", type=Path, default=None)
    parser.add_argument("--handoff-out", type=Path, default=None)
    parser.add_argument("--include-certified-shadow", action="store_true")
    parser.add_argument("--require-at-least-one-pick", action="store_true", help="Exit non-zero when total_picks is zero")
    parser.add_argument("--operator-risk-json", type=Path, help="Local operator-risk JSON ack file")
    parser.add_argument("--allow-operator-risk-public-read", action="store_true")
    parser.add_argument("--combine-certified-and-risk", action="store_true")
    args = parser.parse_args()

    if args.allow_operator_risk_public_read and not args.operator_risk_json:
        print("[live-dry-run] ERROR: --allow-operator-risk-public-read requires --operator-risk-json PATH")
        return 2

    operator_risk_data = None
    if args.operator_risk_json:
        if not args.operator_risk_json.exists():
            print(f"[live-dry-run] ERROR: operator-risk file does not exist: {args.operator_risk_json}")
            return 2
        try:
            operator_risk_data = json.loads(args.operator_risk_json.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[live-dry-run] ERROR: Failed to parse operator-risk JSON: {exc}")
            return 2

    if operator_risk_data and not args.allow_operator_risk_public_read:
        print("[live-dry-run] info: --operator-risk-json provided without --allow-operator-risk-public-read; operator-risk sources will NOT be fetched.")
        operator_risk_data = None

    review_data = load_review_file(args.terms_reviewed_json)
    source_ids_list = list(args.source) if args.source else ["forebet", "predictz"]
    if args.include_certified_shadow:
        for cid in CERTIFIED_SHADOW_SOURCE_IDS:
            if cid not in source_ids_list:
                source_ids_list.append(cid)

    compliant = [sid for sid in source_ids_list if review_gate_details(review_data, sid)["allowed"]]
    risky = [sid for sid in source_ids_list if sid not in compliant]

    if risky and not args.allow_operator_risk_public_read:
        print(f"[live-dry-run] Skipping operator-risk sources because operator-risk mode is disabled: {risky}")
        source_ids_list = compliant
        risky = []

    if compliant and risky and not args.combine_certified_and_risk:
        print("[live-dry-run] ERROR: Combined run of compliant and operator-risk sources requires --combine-certified-and-risk")
        return 2

    started = datetime.now(timezone.utc).isoformat()
    print(f"[live-dry-run] started_at_utc={started} sources={','.join(source_ids_list)} max_pages_per_source={args.max_pages_per_source}")

    all_results: list[ExtractionResult] = []
    for source_id in source_ids_list:
        all_results.extend(
            fetch_extract_source(
                source_id,
                review_data=review_data,
                max_pages=max(1, args.max_pages_per_source),
                timeout=args.timeout_seconds,
                max_bytes=args.max_bytes,
                date_str=args.date,
                verbose=True,
                operator_risk_data=operator_risk_data,
            )
        )

    out = args.out or Path("betting/data") / f"{args.date}_tipster_consensus_v2_live_dry_run.json"
    write_json_artifact(all_results, out)

    if args.handoff_out:
        write_handoff_artifact(build_payload(all_results), args.handoff_out)
        print(f"[live-dry-run] wrote handoff to={args.handoff_out}")

    sqlite_counts = persist_sqlite(all_results, args.sqlite_db) if args.sqlite_db else None

    total_picks = sum(r.pick_count for r in all_results)
    sources_with_picks = len({r.source_id for r in all_results if r.pick_count > 0})
    print(f"[live-dry-run] wrote={out} results={len(all_results)} total_picks={total_picks} sources_with_picks={sources_with_picks}")
    if sqlite_counts:
        print(f"[live-dry-run] sqlite persisted picks={sqlite_counts['picks']} consensus={sqlite_counts['consensus']} db={args.sqlite_db}")
    print("[live-dry-run] decision_boundary=evidence_only_not_a_bet; no EV/stake/coupon/final recommendation produced")
    return 1 if args.require_at_least_one_pick and total_picks == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
