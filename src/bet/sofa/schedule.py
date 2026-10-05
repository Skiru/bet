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

from bet.sofa.comparability import (
    MatchKind,
    competition_id,
    is_friendly_event,
    match_kind,
)
from bet.sofa.epochs import model_fixes_enabled

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
    # League matches of ANOTHER league of the fixture's country among the
    # side's newest ten, for a side new to the fixture's league this season
    # (promoted / relegated) - see other_division_matches. 0 = none or not
    # computed (it is computed only from epochs.MODEL_FIXES_FROM_UTC).
    other_division: int = 0


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
            if side.other_division:
                out.append(
                    f"OTHER_DIVISION_SAMPLE({label} {side.other_division}/"
                    f"{OTHER_DIVISION_WINDOW} from another league of its country)"
                )
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


def _category_name(event: Mapping[str, Any]) -> str:
    tournament = event.get("tournament")
    if not isinstance(tournament, Mapping):
        return ""
    category = tournament.get("category")
    return str(category.get("name") or "") if isinstance(category, Mapping) else ""


def other_division_matches(
    events: Iterable[Mapping[str, Any]],
    competition: int | None,
    category_name: str | None,
    season: int | None,
    kickoff_ts: int,
    sport: str = "football",
) -> int:
    """League matches of another league of the fixture's country among the
    side's newest OTHER_DIVISION_WINDOW, when the side is new to the
    fixture's league this season (promoted or relegated); else 0.

    "New" = the side has history from before this season and none of it is a
    league match of the fixture's competition - so a split season (Apertura /
    Clausura are two competitions of one country) and a domestic second
    competition do not read as a move between divisions. The season starts at
    the side's first match of the fixture's competition in `season` (the
    fixture itself when there is none yet).
    """
    if sport != "football" or competition is None or not category_name:
        return 0
    played = sorted(
        (e for e in events
         if _status(e) == "finished" and isinstance(e.get("startTimestamp"), int)
         and int(e["startTimestamp"]) < kickoff_ts and not is_friendly_event(e, sport)),
        key=lambda e: -int(e["startTimestamp"]),
    )
    newest = played[:OTHER_DIVISION_WINDOW]
    other = sum(
        1 for e in newest
        if competition_id(e) != competition
        and _category_name(e) == category_name
        and match_kind(e, sport) is MatchKind.REGULAR
    )
    if other < OTHER_DIVISION_MIN:
        return 0
    this_season = [
        int(e["startTimestamp"]) for e in played
        if competition_id(e) == competition
        and (e.get("season") or {}).get("id") == season
    ]
    start = min(this_season) if this_season else kickoff_ts
    earlier = [e for e in played if int(e["startTimestamp"]) < start]
    if not earlier:
        return 0  # no history before this season: nothing says "new"
    if any(competition_id(e) == competition
           and match_kind(e, sport) is MatchKind.REGULAR for e in earlier):
        return 0
    return other


# The promotion / relegation note (09-25 defect F5, Zaragoza 6/10, Girona
# 4/10 matches from another division). Measured 2026-10-05 on every cached
# REGULAR league match 2025-08-01..2026-10-03 (scripts/sofa/
# measure_model_defects.py promotion): 3.4% of goals_for cases are such a
# side, and its sample mean is off - residual actual - sample mean goals_for
# -0.214 [-0.235; -0.190], corners_for -0.206 [-0.294; -0.115], fouls_for
# +0.318 [+0.155; +0.488]. Dropping the other division's matches from the
# sample does NOT fix it out of sample (goals_for log-loss -0.0078 [-0.0160;
# +0.0002], corners_for +0.0207 [+0.0085; +0.0345] worse), so the sample is
# left as it is and the side is shown, never gated.
OTHER_DIVISION_WINDOW = 10
OTHER_DIVISION_MIN = 3


def side_schedule(
    events: Iterable[Mapping[str, Any]], kickoff_ts: int, sport: str = "football",
    other_division: int = 0,
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
        other_division=other_division,
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
    category_name: str | None = None,
) -> FixtureSchedule:
    """`category_name` (the fixture's country) feeds the other-division note,
    which is computed only from epochs.MODEL_FIXES_FROM_UTC (disabled until
    the next refit; the note is shown, never gated)."""
    a, b = list(side_a_events), list(side_b_events)
    fixes = model_fixes_enabled()

    def other(events: list[Any]) -> int:
        if not fixes:
            return 0
        return other_division_matches(
            events, competition, category_name, season, kickoff_ts, sport)

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
        side_a=side_schedule(a, kickoff_ts, sport, other(a)),
        side_b=side_schedule(b, kickoff_ts, sport, other(b)),
    )
