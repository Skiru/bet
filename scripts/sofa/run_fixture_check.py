#!/usr/bin/env python3
"""FIXTURE_CHECK - is a printed match still the match RESOLVE froze? (K12, K14)

Reads /event/{id} (bridge; the cache's sofa_event_detail first, 60 min for
an unplayed match) for every match the day's coupon prints or ever printed
(the print history, F0.1), every match whose Superbet start moved more than
30 min from RESOLVE's Sofascore start, and (F0.4) every match the coming
build could print a fresh leg on - so a halted or postponed match is caught
before its FIRST print, not only after it. Writes
runs/sofa/<d>/fixture_status.json - the status (postponed / cancelled /
abandoned / interrupted is FIXTURE_NOT_AS_SCHEDULED in CONFIDENCE), the
fresh start, which replaces RESOLVE's Sofascore clock for the kickoff gate,
the lock and capture_closing, and a tennis match's real first point
(F0.3). See bet.sofa.fixture_status.

Run in a rebuild after OFFER and before CONFIDENCE:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>

Without an answer an event is UNVERIFIED (shown, never a refusal) with the
reason - 404, refused, no bridge, not asked (F0.5) - and the stage exits 1
(PARTIAL); a failed request stops the requests at once (no retry), the rest
is NOT_ASKED.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import fixture_status as fs  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    COUPON_ARTIFACT,
    SHEET_SPORTS,
    coupon_artifact,
    printed_builders,
    printed_singles,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.errors import CircuitOpenError, SofaError, TransportError  # noqa: E402
from bet.sofa.locked_print import (  # noqa: E402
    history_event_ids,
    kickoff_clocks,
    print_history,
)
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402

# More candidate matches than this are not asked (NOT_ASKED, on the PDF):
# a bound on one rebuild's requests. 10-05 had 145 fixtures with a priced
# sheet row; printed matches and moved clocks are never capped.
MAX_CANDIDATES = 250


def printed_event_ids(run: Path) -> set[int]:
    """The matches of the coupon artifact and of every printed render (the
    print history, PRINTED_MANIFEST on a day before it): the lock judges
    "printed before its start" on the fresh start of a leg the operator
    holds on paper even after a rebuild or a later render took it off
    (10-05: Grenier, Bronzetti - Crawley, twelve tennis legs)."""
    ids = history_event_ids(print_history(run))
    path = coupon_artifact(run)
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
        ids |= {int(s["sofascore_event_id"]) for s in printed_singles(doc)}
        ids |= {int(b["sofascore_event_id"]) for b in printed_builders(doc)}
    return ids


def candidate_event_ids(
    run: Path,
    fixtures: list[Mapping[str, Any]],
    seen_kickoff: Mapping[int, str],
    at: datetime,
) -> list[int]:
    """F0.4: every football / tennis match the coming CONFIDENCE could print
    a fresh leg on, nearest start first: a leg of 08_confidence.json or
    11_coupon.json (singles, builders, their legs, the legs a read removed -
    a read can change), and every fixture with a priced 05_sheet.json row
    whose earliest clock is still ahead (CONFIDENCE prints only priced rows
    of matches not under way; a started match's printed legs are asked as
    printed). A superset of the next print, cheap: one cached request each."""
    ids: set[int] = set()
    for name in ("08_confidence.json", "11_coupon.json"):
        path = run / name
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for key in ("singles", "builders", "legs", "removed_by_reads"):
            ids |= {int(x["sofascore_event_id"]) for x in doc.get(key) or []
                    if str(x.get("sport") or "football") in SHEET_SPORTS
                    and x.get("sofascore_event_id") is not None}
    by_id = {int(f["sofascore_event_id"]): f for f in fixtures}
    sheet = run / "05_sheet.json"
    if sheet.exists():
        doc = json.loads(sheet.read_text(encoding="utf-8"))
        rows = doc if isinstance(doc, list) else doc.get("rows") or []
        for r in rows:
            eid = int(r["sofascore_event_id"])
            if r.get("offered_odds") is None or eid in ids or eid not in by_id:
                continue
            clocks = kickoff_clocks(by_id[eid], seen_kickoff.get(eid))
            if clocks and min(clocks) > at:
                ids.add(eid)

    def start(eid: int) -> str:
        fx = by_id.get(eid)
        clocks = kickoff_clocks(fx, seen_kickoff.get(eid)) if fx else []
        return min(clocks).isoformat() if clocks else "9999"

    return sorted(ids, key=lambda e: (start(e), e))


def sport_event_ids(run: Path, at: datetime) -> dict[int, datetime]:
    """{pinned Sofascore id: start} of every measured-sport event (hockey,
    basketball, volleyball, CS2) the coming build could print a leg on or a
    print holds (K14 for the sports): a sport leg of 08_confidence_sports.json
    or 11_coupon.json (singles, legs, the legs a read removed), of any render
    of the print history, and every IDENTIFIED event of sport_fixtures.json
    (SPORT_IDENTITY's pin) whose earliest start is still ahead - the
    superset of what SPORT_CONFIDENCE, which runs after this check, can print.
    /event/{id} answers for every one of them, CS2 included (settle_cs2 and
    settle_shadow grade the pinned ids through the same route)."""
    from bet.sofa.coupon_sports import SPORT_FIXTURES_FILE, is_measured

    def _t(raw: Any) -> datetime | None:
        return (datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if raw else None)

    out: dict[int, datetime] = {}

    def add(eid: Any, start: Any) -> None:
        if eid is None:
            return
        t = _t(start) or datetime.max.replace(tzinfo=at.tzinfo)
        out[int(eid)] = min(t, out.get(int(eid), t))

    for name in ("08_confidence_sports.json", COUPON_ARTIFACT):
        path = run / name
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for key in ("singles", "legs", "removed_by_reads"):
            for x in doc.get(key) or []:
                if is_measured(x):
                    add(x.get("sofascore_event_id"), x.get("kickoff_utc"))
    for render in print_history(run):
        for x in printed_singles(render):
            if is_measured(x):
                add(x.get("sofascore_event_id"), x.get("kickoff_utc"))
    path = run / SPORT_FIXTURES_FILE
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
        for f in doc.get("fixtures") or []:
            if f.get("status") != "IDENTIFIED" or f.get("sofascore_event_id") is None:
                continue
            starts = [t for t in (_t(f.get("kickoff_utc")),
                                  _t(f.get("sofascore_start_utc"))) if t]
            if starts and min(starts) > at:
                add(f["sofascore_event_id"], min(starts).isoformat())
    return out


def failure_reason(exc: BaseException) -> str:
    """fixture_status.UNVERIFIED_REASONS from what the client raised
    (bet.sofa.client._execute: 404 returns None and never gets here)."""
    if isinstance(exc, CircuitOpenError):
        return fs.CIRCUIT_OPEN
    if isinstance(exc, TransportError):
        return fs.NO_BRIDGE
    msg = str(exc)
    if msg.startswith(("HTTP 403", "HTTP 429")):
        return fs.PROVIDER_REFUSED
    if msg.startswith(("HTTP 5", "Unexpected HTTP")):
        return fs.PROVIDER_ERROR
    if msg.startswith("HTML instead of JSON"):
        return fs.BAD_PAYLOAD
    # "Network error after retry", "Unexpected error": the request did not
    # complete - the bridge or the connection, not Sofascore's answer.
    return fs.NO_BRIDGE


Cached = Callable[[int], Any]


def check(
    targets: dict[int, str], fetch: Any, cached: Cached, save: Any
) -> tuple[dict[int, dict[str, Any]], bool]:
    """{event id: entry}, and whether a request failed (stop at once).

    Targets are asked in their order (printed and moved clocks first).
    `cached(eid)` is a payload, or (payload, fetched_at) - the entry is
    dated by when its payload was read - or None."""
    out: dict[int, dict[str, Any]] = {}
    stopped = False
    for eid, why in targets.items():
        at = now()
        hit = cached(eid)
        payload, reason = hit, None
        if isinstance(hit, tuple):
            payload, at = hit
        if payload is None and stopped:
            reason = fs.NOT_ASKED
        elif payload is None:
            at = now()
            try:
                payload = fetch(eid)
                if payload is None:
                    reason = fs.NOT_FOUND
            except SofaError as exc:
                # A refusal is a signal to slow down (CLAUDE.md): no retry,
                # the rest stays UNVERIFIED (NOT_ASKED).
                stopped = True
                reason = failure_reason(exc)
                print(f"FIXTURE_CHECK: {type(exc).__name__} ({exc}) on {eid} - "
                      "the rest is UNVERIFIED", file=sys.stderr)
                payload = None
            if payload:
                status = ((payload.get("event") or {}).get("status") or {}).get("type")
                save(eid, payload, status)
        out[eid] = fs.entry_from_payload(payload, why, at, reason)
    return out, stopped


def targets_for(
    run: Path,
    fixtures: list[Mapping[str, Any]],
    offers: list[Mapping[str, Any]],
    at: datetime,
    max_candidates: int = MAX_CANDIDATES,
) -> tuple[dict[int, str], list[int]]:
    """(targets in the order to ask, candidates over the cap - NOT_ASKED)."""
    seen = {
        int(o["sofascore_event_id"]): str(o["superbet_kickoff_seen_utc"])
        for o in offers if o.get("superbet_kickoff_seen_utc")
    }
    candidates = candidate_event_ids(run, fixtures, seen, at)
    sports = sport_event_ids(run, at)
    targets = fs.events_to_check(
        fixtures, seen, printed_event_ids(run), set(candidates), sports)
    rank = {eid: i for i, eid in enumerate(candidates)}
    # A sport candidate after the football / tennis ones, nearest start first
    # (the cap bounds both together; a printed sport leg is never capped).
    for i, eid in enumerate(sorted((e for e in sports if e not in rank),
                                   key=lambda e: (sports[e], e))):
        rank[eid] = len(candidates) + i
    ordered = dict(sorted(
        targets.items(),
        key=lambda kv: (kv[1] == "candidate", rank.get(kv[0], -1), kv[0])))
    asked = [e for e, why in ordered.items() if why == "candidate"]
    over = asked[max_candidates:]
    for eid in over:
        del ordered[eid]
    return ordered, over


def main() -> int:
    set_stage("FIXTURE_CHECK")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    ap.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES,
                    help="candidate matches asked at most (printed and moved "
                         "clocks are always asked)")
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
    targets, over_cap = targets_for(run, fixtures, offers, now(),
                                    args.max_candidates)
    sport_ids = set(sport_event_ids(run, now()))

    from bet.sofa.cache import SofaCache
    from bet.sofa.client import SofascoreClient

    cache = SofaCache(config)
    client = SofascoreClient(config)
    events, stopped = check(
        targets, client.event, cache.get_event_detail_dated, cache.save_event_detail
    )
    for eid in over_cap:
        events[eid] = fs.entry_from_payload(None, "candidate", now(), fs.NOT_ASKED)
    unverified = sum(1 for e in events.values() if e["status"] == fs.UNVERIFIED)
    not_sched = {
        eid: e["status"] for eid, e in events.items() if fs.not_as_scheduled(e)
    }
    write_atomic(run / fs.FIXTURE_STATUS_FILE, json.dumps({
        "checked_at_utc": now().isoformat().replace("+00:00", "Z"),
        "events": {str(k): v for k, v in sorted(events.items())},
    }, indent=1, ensure_ascii=False) + "\n")
    reasons = fs.unverified_reasons(events.values())
    print("SOFA_SUMMARY: " + json.dumps({
        "stage": "FIXTURE_CHECK",
        "verdict": "OK" if not unverified else "PARTIAL",
        "metrics": {
            "checked": len(events),
            "printed": sum(1 for e in events.values() if e["why"] == "printed"),
            "clock_gap": sum(1 for e in events.values() if e["why"] == "clock_gap"),
            "candidate": sum(1 for e in events.values() if e["why"] == "candidate"),
            "candidates_over_cap": len(over_cap),
            "sport_events": sum(1 for eid in events if eid in sport_ids),
            "unverified": unverified, "unverified_reasons": reasons,
            "stopped": stopped,
            "provider_refused": reasons.get(fs.PROVIDER_REFUSED, 0) > 0,
            "not_as_scheduled": not_sched,
        },
        "output_path": str(run / fs.FIXTURE_STATUS_FILE),
    }))
    return 0 if not unverified else 1


if __name__ == "__main__":
    raise SystemExit(main())
