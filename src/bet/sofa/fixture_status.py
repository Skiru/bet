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
unplayed match) first - for the printed matches, the moved clocks and (F0.4)
every match the coming build could print a leg on. Without an answer an
event is UNVERIFIED, with the reason (F0.5): shown, never a refusal.
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

# Why an entry is UNVERIFIED (F0.5, plan 2026-10-05 production grade). The
# PDF said "FIXTURE_CHECK bez mostka" for every one of them; on 10-05 the one
# UNVERIFIED match was asked through a working bridge. A reason is recorded
# from what run_fixture_check.check saw, and the PDF prints it.
NOT_FOUND = "NOT_FOUND"                # 404: Sofascore does not know the id
PROVIDER_REFUSED = "PROVIDER_REFUSED"  # 403 / 429: the provider said no
PROVIDER_ERROR = "PROVIDER_ERROR"      # 5xx, an unexpected HTTP status
BAD_PAYLOAD = "BAD_PAYLOAD"            # HTML for JSON, a payload with no event
NO_BRIDGE = "NO_BRIDGE"                # the request did not complete (transport)
CIRCUIT_OPEN = "CIRCUIT_OPEN"          # the breaker refused to send it
NOT_ASKED = "NOT_ASKED"                # the check stopped at an earlier failure
UNVERIFIED_REASONS = (NOT_FOUND, PROVIDER_REFUSED, PROVIDER_ERROR, BAD_PAYLOAD,
                      NO_BRIDGE, CIRCUIT_OPEN, NOT_ASKED)


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
    candidate_ids: set[int] | None = None,
) -> dict[int, str]:
    """{event id: why} - every printed match, every match whose Superbet
    clock moved more than CLOCK_GAP_MIN from RESOLVE's Sofascore clock, and
    (F0.4) every match a leg of the coming build could be printed on
    (`candidate_ids`, run_fixture_check.candidate_event_ids): K14 caught a
    halted match only after it had been printed once, because the check
    asked nothing about a match no PDF had held yet."""
    out: dict[int, str] = {}
    for fx in fixtures:
        eid = int(fx["sofascore_event_id"])
        gap = clock_gap_min(fx, seen_kickoff.get(eid))
        if gap is not None and gap > CLOCK_GAP_MIN:
            out[eid] = "clock_gap"
        elif eid in printed_ids:
            out[eid] = "printed"
        elif candidate_ids and eid in candidate_ids:
            out[eid] = "candidate"
    return out


# Sofascore tennis status codes of a set in play: 8 = 1st set .. 12 = 5th.
_TENNIS_SET_CODES = range(8, 13)


def real_start(event: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """When a tennis match really began, from /event's `time` block, and how
    sure that is (F0.3): (utc, basis) or (None, None).

    `startTimestamp` is the order of play's time - "not before", or the slot
    of the first match on a court - and on 10-05 it decided "printed before
    its start" for legs whose matches began 20-40 min later or earlier.
    `time.currentPeriodStartTimestamp` is the start of the CURRENT set, and
    `time.periodN` the length of a set already played, in seconds. So:

    * a set in play is code 8 + (n - 1); in the 1st set (code 8) the current
      period's start IS the first point - basis "first_set" (the only exact
      case);
    * in set n > 1, or on a finished / retired match (current = the highest
      `periodN` held, which is the last set played), the start is the
      current set's start minus the lengths of the sets before it - basis
      "derived". Set lengths are play, not the breaks between sets, so this
      is an UPPER bound on the first point, minutes late at most (measured on
      the cache 10-01..10-05: median 8.7-9.4 min after startTimestamp for
      in-progress and finished 2- and 3-set matches alike).

    Never below the real start: an unknown set length is not subtracted
    (fewer sets subtracted = later = still an upper bound). A walkover (91)
    was never played. Only tennis: a football payload has no sets.
    Measured on 10-05: Grenier - Kravchenko (17253654), 1st set, 09:40:52Z;
    Dedura-Palomero - Tarvet (17253481), 2nd set from 09:53:10Z with a 2346 s
    first set, 09:14:04Z - their startTimestamps said 09:40:00Z and 09:10:00Z.
    """
    sport = (((event.get("tournament") or {}).get("category") or {})
             .get("sport") or {}).get("slug")
    if sport != "tennis":
        return None, None
    time = event.get("time") or {}
    cps = time.get("currentPeriodStartTimestamp")
    status = event.get("status") or {}
    code = status.get("code")
    if not isinstance(cps, (int, float)) or code == 91:
        return None, None
    if isinstance(code, int) and code in _TENNIS_SET_CODES:
        current = code - 7
    elif status.get("type") == "inprogress":
        return None, None  # a pause / changeover code: which set is unknown
    else:
        held = [int(k[6:]) for k in time if k.startswith("period") and k[6:].isdigit()]
        current = max(held) if held else 1
    before = 0.0
    for n in range(1, current):
        length = time.get(f"period{n}")
        if not isinstance(length, (int, float)):
            break  # unknown: subtract no more (still an upper bound)
        before += float(length)
    start = datetime.fromtimestamp(float(cps) - before, UTC)
    # Only a 1st set IN PLAY is exact; a finished match's held periods may
    # miss its last set (2 finished matches in the cache had period1 only and
    # a current-period start 39-107 min after their startTimestamp).
    return _z(start), "first_set" if code == 8 else "derived"


def entry_from_payload(
    payload: Mapping[str, Any] | None, why: str, fetched_at: datetime,
    reason: str | None = None,
) -> dict[str, Any]:
    """One fixture_status.json entry from an /event/{id} payload (None: no
    payload - UNVERIFIED, with `reason`, one of UNVERIFIED_REASONS).

    `fetched_at` is when the payload was READ - a cached payload's own fetch
    time, not the time of this check: "notstarted, read at or after t" is the
    lock's evidence that a leg printed at t was printed before its start
    (locked_print.started_by_evidence), and a 60-minute-old cached read
    stamped with the check's time claimed up to an hour it never saw."""
    event = (payload or {}).get("event") if payload else None
    if not isinstance(event, Mapping):
        return {"status": UNVERIFIED, "why": why, "checked_at_utc": _z(fetched_at),
                "reason": reason or (BAD_PAYLOAD if payload else NOT_FOUND)}
    status = event.get("status") or {}
    start = event.get("startTimestamp")
    started, basis = real_start(event)
    return {
        "status": str(status.get("type") or ""),
        "status_code": status.get("code"),
        "status_description": status.get("description"),
        "start_utc": (
            _z(datetime.fromtimestamp(int(start), UTC)) if start is not None else None
        ),
        **({"real_start_utc": started, "real_start_basis": basis} if started else {}),
        "why": why,
        "checked_at_utc": _z(fetched_at),
    }


def unverified_reasons(entries: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """{reason: count} of the UNVERIFIED entries; an entry written before the
    reason was recorded (10-05 morning) counts as UNKNOWN."""
    out: dict[str, int] = {}
    for e in entries:
        if e.get("status") == UNVERIFIED:
            r = str(e.get("reason") or "UNKNOWN")
            out[r] = out.get(r, 0) + 1
    return dict(sorted(out.items()))
