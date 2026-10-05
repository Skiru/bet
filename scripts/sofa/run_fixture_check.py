#!/usr/bin/env python3
"""FIXTURE_CHECK - is a printed match still the match RESOLVE froze? (K12, K14)

Reads /event/{id} (bridge; the cache's sofa_event_detail first, 60 min for
an unplayed match) for every match the day's coupon prints and every match
whose Superbet start moved more than 30 min from RESOLVE's Sofascore start,
and writes runs/sofa/<d>/fixture_status.json - the status (postponed /
cancelled / abandoned is FIXTURE_NOT_AS_SCHEDULED in CONFIDENCE) and the
fresh start, which replaces RESOLVE's Sofascore clock for the kickoff gate,
the lock and capture_closing. See bet.sofa.fixture_status.

Run in a rebuild after OFFER and before CONFIDENCE:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>

With no bridge every event is UNVERIFIED (shown, never a refusal) and the
stage exits 1 (PARTIAL); a 403 stops the requests at once (no retry).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import fixture_status as fs  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    coupon_artifact,
    printed_builders,
    printed_singles,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.errors import SofaError  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402


def printed_event_ids(run: Path) -> set[int]:
    path = coupon_artifact(run)
    if not path.exists():
        return set()
    doc = json.loads(path.read_text(encoding="utf-8"))
    ids = {int(s["sofascore_event_id"]) for s in printed_singles(doc)}
    ids |= {int(b["sofascore_event_id"]) for b in printed_builders(doc)}
    return ids


def check(
    targets: dict[int, str], fetch: Any, cached: Any, save: Any
) -> tuple[dict[int, dict[str, Any]], bool]:
    """{event id: entry}, and whether the provider refused (stop at once)."""
    out: dict[int, dict[str, Any]] = {}
    refused = False
    for eid, why in sorted(targets.items()):
        at = now()
        payload = cached(eid)
        if payload is None and not refused:
            try:
                payload = fetch(eid)
            except SofaError as exc:
                # A refusal is a signal to slow down (CLAUDE.md): no retry,
                # the rest stays UNVERIFIED.
                refused = True
                print(f"FIXTURE_CHECK: {type(exc).__name__} on {eid} - the rest "
                      "is UNVERIFIED", file=sys.stderr)
                payload = None
            if payload:
                status = ((payload.get("event") or {}).get("status") or {}).get("type")
                save(eid, payload, status)
        out[eid] = fs.entry_from_payload(payload, why, at)
    return out, refused


def main() -> int:
    set_stage("FIXTURE_CHECK")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    frozen = frozen_clock_refusal(config.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    run = Path(config.runs_dir) / args.date
    fx_path, offer_path = run / "02_fixtures.json", run / "04_offer.json"
    if not fx_path.exists():
        print(f"{fx_path} missing", file=sys.stderr)
        return 2
    fixtures = json.loads(fx_path.read_text(encoding="utf-8"))
    offers = (
        json.loads(offer_path.read_text(encoding="utf-8"))
        if offer_path.exists() else []
    )
    seen = {
        int(o["sofascore_event_id"]): str(o["superbet_kickoff_seen_utc"])
        for o in offers if o.get("superbet_kickoff_seen_utc")
    }
    targets = fs.events_to_check(fixtures, seen, printed_event_ids(run))

    from bet.sofa.cache import SofaCache
    from bet.sofa.client import SofascoreClient

    cache = SofaCache(config)
    client = SofascoreClient(config)
    events, refused = check(
        targets, client.event, cache.get_event_detail, cache.save_event_detail
    )
    unverified = sum(1 for e in events.values() if e["status"] == fs.UNVERIFIED)
    not_sched = {
        eid: e["status"] for eid, e in events.items() if fs.not_as_scheduled(e)
    }
    write_atomic(run / fs.FIXTURE_STATUS_FILE, json.dumps({
        "checked_at_utc": now().isoformat().replace("+00:00", "Z"),
        "events": {str(k): v for k, v in sorted(events.items())},
    }, indent=1, ensure_ascii=False) + "\n")
    print("SOFA_SUMMARY: " + json.dumps({
        "stage": "FIXTURE_CHECK",
        "verdict": "OK" if not unverified else "PARTIAL",
        "metrics": {
            "checked": len(events),
            "printed": sum(1 for e in events.values() if e["why"] == "printed"),
            "clock_gap": sum(1 for e in events.values() if e["why"] == "clock_gap"),
            "unverified": unverified, "provider_refused": refused,
            "not_as_scheduled": not_sched,
        },
        "output_path": str(run / fs.FIXTURE_STATUS_FILE),
    }))
    return 0 if not unverified else 1


if __name__ == "__main__":
    raise SystemExit(main())
