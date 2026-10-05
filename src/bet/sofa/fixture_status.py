"""Is a fixture still the fixture RESOLVE froze? (plan 2026-10-05, K12 + K14)

Two facts RESOLVE freezes in 02_fixtures.json go stale during the day, and
both were seen on 10-05:

* the start (K12). Shanghai: RESOLVE read 06:20Z, Superbet moved the match
  to 07:30Z; a rebuild at 06:12Z refused Cui, Vukic and Svrcina's singles as
  "starting soon" and their closing prices were taken ~80 min early. The
  earliest clock stays the gate's rule (it protects against a late clock),
  but RESOLVE's Sofascore clock is replaced by a fresh `/event/{id}`
  `startTimestamp` where one was read - only for the matches whose
  Superbet clock (superbet_kickoff_seen_utc) has moved more than
  CLOCK_GAP_MIN from it.
* the status (K14). A printed match postponed, cancelled or abandoned after
  the print is not a bet to make: CONFIDENCE refuses it as
  FIXTURE_NOT_AS_SCHEDULED. A leg already locked (its match had started) stays
  and is settled as a refund by SETTLE.

The check is its own step (scripts/sofa/run_fixture_check.py, stage
FIXTURE_CHECK), not part of OFFER, which asks Superbet only. It asks
Sofascore - through the bridge, the cache (sofa_event_detail, 60 min for an
unplayed match) first - for the printed matches and the moved clocks only.
With no bridge an event is UNVERIFIED: shown, never a refusal.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FIXTURE_STATUS_FILE = "fixture_status.json"
# Sofascore status.type values of a match that will not be played as
# scheduled. A match that kicked off and was halted (interrupted 80,
# suspended 81, willcontinue 140) is not one either: El Porvenir - Canuelas,
# 10-05, was halted at 0-0 on 10-03 and re-dated with status "interrupted",
# and passed the gate as an ordinary pre-match fixture. "delayed" (61, start
# delayed) has not started and stays out.
NOT_AS_SCHEDULED = frozenset({
    "postponed", "canceled", "cancelled", "abandoned",
    "interrupted", "suspended", "willcontinue",
})
# A fresh status of a match that had not begun when it was read (the lock's
# "printed before its start", locked_print.printed_after_its_start).
# "canceled" is not here: Sofascore files an abandoned match (code 90) under
# it too, after a kickoff.
NOT_YET_STARTED = frozenset({"notstarted", "delayed", "postponed"})
CLOCK_GAP_MIN = 30.0
UNVERIFIED = "UNVERIFIED"


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _z(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def load(run_dir: Path) -> dict[int, dict[str, Any]]:
    """runs/sofa/<d>/fixture_status.json by event id; none is no check."""
    path = Path(run_dir) / FIXTURE_STATUS_FILE
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in (doc.get("events") or {}).items()}


def refreshed_start(entry: Mapping[str, Any] | None) -> str | None:
    """The fresh Sofascore start an entry carries, if it was read."""
    if not entry or entry.get("status") == UNVERIFIED:
        return None
    start = entry.get("start_utc")
    return str(start) if start else None


def not_as_scheduled(
    entry: Mapping[str, Any] | None, resolve_status: str | None = None
) -> str | None:
    """The status that makes a fixture not the one scheduled, else None:
    the fresh check where there is one, else RESOLVE's status."""
    status = None
    if entry and entry.get("status") not in (None, UNVERIFIED):
        status = str(entry["status"])
    elif resolve_status:
        status = resolve_status
    return status if status in NOT_AS_SCHEDULED else None


def clock_gap_min(fixture: Mapping[str, Any], seen_kickoff: str | None) -> float | None:
    """Minutes between RESOLVE's Sofascore clock and Superbet's latest one."""
    ko = fixture.get("kickoff_utc")
    if not ko or not seen_kickoff:
        return None
    return abs((_utc(str(seen_kickoff)) - _utc(str(ko))).total_seconds()) / 60.0


def events_to_check(
    fixtures: Iterable[Mapping[str, Any]],
    seen_kickoff: Mapping[int, str],
    printed_ids: set[int],
) -> dict[int, str]:
    """{event id: why} - every printed match, and every match whose Superbet
    clock moved more than CLOCK_GAP_MIN from RESOLVE's Sofascore clock."""
    out: dict[int, str] = {}
    for fx in fixtures:
        eid = int(fx["sofascore_event_id"])
        gap = clock_gap_min(fx, seen_kickoff.get(eid))
        if gap is not None and gap > CLOCK_GAP_MIN:
            out[eid] = "clock_gap"
        elif eid in printed_ids:
            out[eid] = "printed"
    return out


def entry_from_payload(
    payload: Mapping[str, Any] | None, why: str, fetched_at: datetime
) -> dict[str, Any]:
    """One fixture_status.json entry from an /event/{id} payload (None: the
    request could not be made - UNVERIFIED)."""
    event = (payload or {}).get("event") if payload else None
    if not isinstance(event, Mapping):
        return {"status": UNVERIFIED, "why": why, "checked_at_utc": _z(fetched_at)}
    status = event.get("status") or {}
    start = event.get("startTimestamp")
    return {
        "status": str(status.get("type") or ""),
        "status_code": status.get("code"),
        "status_description": status.get("description"),
        "start_utc": (
            _z(datetime.fromtimestamp(int(start), UTC)) if start is not None else None
        ),
        "why": why,
        "checked_at_utc": _z(fetched_at),
    }
