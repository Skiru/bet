"""A fixture's schedule context, read from listings the pipeline already holds.

2026-10-04, SC Farense - Chaves: the fixture was the make-up of round 5,
postponed on 2026-09-06 after a viral outbreak in Farense's squad (Sofascore
event 16451028, status "postponed", the same two sides in the same
competition). SAMPLES recorded the postponed event only as an
EVENT_NOT_FINISHED gap; nothing said the match was a rescheduled one, how
long either side had been idle, or that the 0-0 a week after the postponement
was played by a convalescent squad. The cause (an illness) is not in any
Sofascore payload; the shape is:

* ``makeup_of`` - a postponed (or abandoned / interrupted) event of the same
  two sides in the same competition, started before this kick-off: the
  fixture is a rescheduled match;
* per side, the days since its last finished competitive match (friendlies
  out, a match without statistics counts - it was played) and how many it
  played in the 7 and 14 days before kick-off.

Read-only: listings from the cache (page 0..4 of kind 'last' and the
listed-event index), never a request. What the flags are worth is measured
by scripts/sofa/measure_sample_composition.py --context before any gate
reads them; until then they are shown, not acted on.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from bet.sofa.comparability import competition_id, is_friendly_event

# Statuses of an event that was due and was not (completely) played.
_NOT_PLAYED = frozenset({"postponed", "canceled", "interrupted", "suspended"})
# A side idle this long has had a break the sample does not describe
# (an international window is ~10-14 days).
LONG_LAYOFF_DAYS = 21
# Three matches inside a week is a congested schedule.
CONGESTED_7D = 3


class SideSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    last_match_utc: datetime | None
    rest_days: float | None
    matches_7d: int
    matches_14d: int


class FixtureSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    makeup_of: int | None
    makeup_postponed_utc: datetime | None
    side_a: SideSchedule
    side_b: SideSchedule

    def flags(self) -> list[str]:
        """Short tags for the sheet, the legs and the PDF."""
        out: list[str] = []
        if self.makeup_of is not None:
            when = (
                self.makeup_postponed_utc.date().isoformat()
                if self.makeup_postponed_utc else "?"
            )
            out.append(f"MAKEUP_FIXTURE(postponed {when}, event {self.makeup_of})")
        for label, side in (("home", self.side_a), ("away", self.side_b)):
            if side.rest_days is not None and side.rest_days >= LONG_LAYOFF_DAYS:
                out.append(f"LONG_LAYOFF({label} {side.rest_days:.0f} d)")
            if side.matches_7d >= CONGESTED_7D:
                out.append(f"CONGESTED({label} {side.matches_7d} in 7 d)")
        return out


def _status(event: Mapping[str, Any]) -> str:
    status = event.get("status")
    return str(status.get("type") or "") if isinstance(status, Mapping) else ""


def _sides(event: Mapping[str, Any]) -> frozenset[Any]:
    home = event.get("homeTeam") or {}
    away = event.get("awayTeam") or {}
    return frozenset((home.get("id"), away.get("id")))


def find_makeup(
    events: Iterable[Mapping[str, Any]],
    home_id: int,
    away_id: int,
    competition: int | None,
    kickoff_ts: int,
    fixture_event_id: int,
    season: int | None = None,
) -> Mapping[str, Any] | None:
    """The newest not-played event of these two sides in this competition
    (and season, when both carry one) before kick-off that the two have not
    played since, or None.

    A postponed meeting is a make-up only while it is still owed: 74% of the
    29,292 not-played events in the index were followed by a finished meeting
    of the same pair in the same competition, and without that check 37% of
    the flags fell on the return fixture or next season's meeting
    (review 2026-10-04).
    """
    pair = frozenset((home_id, away_id))
    rows = [e for e in events if _sides(e) == pair and e.get("id") != fixture_event_id
            and (competition is None or competition_id(e) == competition)]

    def start(e: Mapping[str, Any]) -> int:
        ts = e.get("startTimestamp")
        return int(ts) if isinstance(ts, int) else -1

    played = [start(e) for e in rows
              if _status(e) == "finished" and 0 <= start(e) < kickoff_ts]
    best: Mapping[str, Any] | None = None
    for event in rows:
        ts = start(event)
        if _status(event) not in _NOT_PLAYED or not 0 <= ts < kickoff_ts:
            continue
        event_season = (event.get("season") or {}).get("id")
        if (season is not None and isinstance(event_season, int)
                and event_season != season):
            continue
        if any(ts < p for p in played):
            continue  # played since: the meeting is no longer owed
        if best is None or ts > start(best):
            best = event
    return best


def side_schedule(
    events: Iterable[Mapping[str, Any]], kickoff_ts: int, sport: str = "football"
) -> SideSchedule:
    """Rest and congestion of one side from its listed events."""
    played = sorted(
        {
            int(e["startTimestamp"])
            for e in events
            if _status(e) == "finished"
            and isinstance(e.get("startTimestamp"), int)
            and int(e["startTimestamp"]) < kickoff_ts
            and not is_friendly_event(e, sport)
        }
    )
    last = played[-1] if played else None
    return SideSchedule(
        last_match_utc=datetime.fromtimestamp(last, UTC) if last else None,
        rest_days=round((kickoff_ts - last) / 86400, 1) if last else None,
        matches_7d=sum(1 for t in played if kickoff_ts - t <= 7 * 86400),
        matches_14d=sum(1 for t in played if kickoff_ts - t <= 14 * 86400),
    )


def fixture_schedule(
    side_a_events: Iterable[Mapping[str, Any]],
    side_b_events: Iterable[Mapping[str, Any]],
    home_id: int,
    away_id: int,
    competition: int | None,
    kickoff_ts: int,
    fixture_event_id: int,
    sport: str = "football",
    season: int | None = None,
) -> FixtureSchedule:
    a, b = list(side_a_events), list(side_b_events)
    makeup = find_makeup(
        [*a, *b], home_id, away_id, competition, kickoff_ts, fixture_event_id,
        season,
    )
    postponed = makeup.get("startTimestamp") if makeup else None
    return FixtureSchedule(
        makeup_of=int(makeup["id"]) if makeup else None,
        makeup_postponed_utc=(
            datetime.fromtimestamp(postponed, UTC)
            if isinstance(postponed, int)
            else None
        ),
        side_a=side_schedule(a, kickoff_ts, sport),
        side_b=side_schedule(b, kickoff_ts, sport),
    )
