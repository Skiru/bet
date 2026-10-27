"""The operator's kickoff window as read requests (`/sofa-analyze ... okno 14-17`).

The C3 read set is the day's 20 best-value matches; an operator who plays a
window of hours wants that window read instead. This picks the window's
`top` best matches by the same order - `confidence.read_value` of a match's
best unlocked printed single - every one when fewer are left, and writes each
as a whole-match `read_requests.json` entry (a `group_key` with no market
covers every market of the match, `confidence.request_covers`). Nothing new
reaches C3 but the operator's own channel; a request is never a verdict.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any

from bet.sofa.confidence import (
    MIN_MINUTES_TO_KICKOFF,
    group_key,
    printed_singles,
    read_value,
)

TOP = 20
# The analysts skip a match inside the coupon's kickoff margin
# (MIN_MINUTES_TO_KICKOFF) at their decision point, and a part takes time to
# read: 0.6-8.6 min a part on 2026-10-27 (5 parts, <= 86 legs). A match
# closer than both when asked for would only come back unread (10-27: three
# 13:00Z matches asked at 12:48Z, skipped by their analysts at 12:50-12:55Z).
READ_ALLOWANCE = datetime.timedelta(minutes=15)
START_MARGIN = datetime.timedelta(minutes=MIN_MINUTES_TO_KICKOFF) + READ_ALLOWANCE


def _utc(raw: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))


def window_events(
    artifact: Mapping[str, Any],
    lo: datetime.datetime,
    hi: datetime.datetime,
    now: datetime.datetime,
    top: int = TOP,
) -> list[tuple[str, float, dict[str, Any]]]:
    """The window's best matches: (group_key, value, best leg), best first.

    A match counts when its printed kickoff is in [lo, hi) and more than
    START_MARGIN ahead of `now`; it is ranked by its best unlocked printed
    single (a match with locked legs only prints as it is - nothing to
    read). Ties keep the coupon's order."""
    best: dict[str, tuple[float, dict[str, Any]]] = {}
    for leg in printed_singles(dict(artifact)):
        if leg.get("locked") or not leg.get("kickoff_utc"):
            continue
        start = _utc(str(leg["kickoff_utc"]))
        if not (lo <= start < hi) or start <= now + START_MARGIN:
            continue
        g, v = group_key(leg), read_value(leg)
        if g not in best or v > best[g][0]:
            best[g] = (v, leg)
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
    return [(g, v, leg) for g, (v, leg) in ranked[:top]]


def window_requests(
    events: list[tuple[str, float, dict[str, Any]]],
    existing: list[dict[str, Any]],
    now: datetime.datetime,
    label: str,
) -> list[dict[str, Any]]:
    """The new whole-match requests; a match already asked for whole is
    skipped (the file is appended to, never rewritten)."""
    asked = {r.get("group_key") for r in existing
             if r.get("group_key") is not None and r.get("market") is None}
    at = now.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [{"group_key": g, "requested_by": "operator", "at_utc": at,
             "window": label}
            for g, _, _ in events if g not in asked]
