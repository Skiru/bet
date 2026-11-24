"""A re-fetched finished /event never degrades the cached score.

Sofascore rewrites a finished match's half score after the match: days
later the first half reads 0-0 (or is gone) and ``period2`` holds the whole
match, while the goal list keeps its minutes. ``SofaCache.save_event_detail``
replaced the row on every fetch (INSERT OR REPLACE), and SETTLE re-fetches
/event for every event of a day it settles - each morning's resettle sweep
re-settles past days - so a good payload graded once was overwritten by the
degraded one and the regrade flipped correct half rows on it (2026-11-24:
81 half rows on 15 events, 11-12..11-24; 16435127 Albania U21 - Andorra U21
graded on period1 3-1 at 11-21, re-fetched on 11-22 as 0-0).

``guard_scores`` decides which score a finished re-fetch keeps:

- the 90-minute / final score changed (``current`` / ``normaltime``): the
  new payload, whole - a correction is Sofascore's to make;
- the new score lost a field the old one had (a ``periodN`` / ``normaltime``
  gone): the old score (``LOST_SCORE_FIELDS``);
- football, the first half differs: the goal incidents' own first-half
  score (``metrics.goal_incidents_half_time``) decides - the old score when
  it agrees with them and the new does not (``HALF_CONTRADICTS_GOALS``); no
  reading of the goals: the old score only when the new half is the rewrite's
  signature (0-0, period2 = the match) and the old one was consistent
  (``HALF_ZEROED``); otherwise the new.

Only ``homeScore`` / ``awayScore`` are kept from the old payload; everything
else is the new one's, with ``score_guard`` recording the refused score.
Pure; the cache reads the old row and the cached incidents.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from bet.sofa.metrics import goal_incidents_half_time

LOST_SCORE_FIELDS = "LOST_SCORE_FIELDS"
HALF_CONTRADICTS_GOALS = "HALF_CONTRADICTS_GOALS"
HALF_ZEROED = "HALF_ZEROED"
_FINAL_KEYS = ("current", "normaltime")


def _event(detail: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    event = (detail or {}).get("event")
    return event if isinstance(event, Mapping) else None


def _finished(event: Mapping[str, Any]) -> bool:
    return (event.get("status") or {}).get("type") == "finished"


def _sides(event: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    home = event.get("homeScore")
    away = event.get("awayScore")
    return (home if isinstance(home, Mapping) else {},
            away if isinstance(away, Mapping) else {})


def _number(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _half(event: Mapping[str, Any], key: str) -> tuple[int, int] | None:
    home, away = _sides(event)
    h, a = _number(home.get(key)), _number(away.get(key))
    if h is None or a is None:
        return None
    return h, a


def _sport(event: Mapping[str, Any]) -> str:
    return str((((event.get("tournament") or {}).get("category") or {})
                .get("sport") or {}).get("slug") or "")


def _consistent(event: Mapping[str, Any]) -> bool:
    for side in _sides(event):
        p1, p2 = _number(side.get("period1")), _number(side.get("period2"))
        full = _number(side.get("normaltime"))
        if p1 is None or p2 is None or full is None or p1 + p2 != full:
            return False
    return True


def _reason(old: Mapping[str, Any], new: Mapping[str, Any],
            incidents: Mapping[str, Any] | None) -> str | None:
    old_sides, new_sides = _sides(old), _sides(new)
    for o, n in zip(old_sides, new_sides, strict=True):
        for key in _FINAL_KEYS:
            if o.get(key) is not None and n.get(key) is not None \
                    and o.get(key) != n.get(key):
                return None  # the match's score itself changed
    for o, n in zip(old_sides, new_sides, strict=True):
        for key, value in o.items():
            if value is None:
                continue
            if (key.startswith("period") or key in _FINAL_KEYS) and n.get(key) is None:
                return LOST_SCORE_FIELDS
    if _sport(new) != "football":
        return None
    old_half, new_half = _half(old, "period1"), _half(new, "period1")
    if old_half is None or new_half is None or old_half == new_half:
        return None
    goals = goal_incidents_half_time(new, incidents)
    if goals is not None:
        return HALF_CONTRADICTS_GOALS if old_half == goals != new_half else None
    if new_half == (0, 0) and _half(new, "period2") == _half(new, "normaltime") \
            and _consistent(old):
        return HALF_ZEROED
    return None


def guard_scores(
    old_detail: Mapping[str, Any] | None,
    new_detail: dict[str, Any],
    incidents: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """(the payload to cache, the reason the old score was kept or None).

    Only a finished payload replacing a finished one is judged."""
    old, new = _event(old_detail), _event(new_detail)
    if old is None or new is None or not _finished(old) or not _finished(new):
        return new_detail, None
    reason = _reason(old, new, incidents)
    if reason is None:
        return new_detail, None
    kept = copy.deepcopy(new_detail)
    event = kept["event"]
    refused = {"homeScore": event.get("homeScore"), "awayScore": event.get("awayScore")}
    event["homeScore"] = copy.deepcopy(old.get("homeScore"))
    event["awayScore"] = copy.deepcopy(old.get("awayScore"))
    kept["score_guard"] = {"reason": reason, "refused": refused}
    return kept, reason
