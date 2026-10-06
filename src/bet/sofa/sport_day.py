"""A measured sport's day on disk: the snapshot files SHADOW / CS2 write,
their settled results, and the grading of the coupon's sport legs.

The measured sports (CS2, hockey, basketball, volleyball) keep their own day
directories (runs/sofa/cs2/<d>/, runs/sofa/shadow/<sport>/<d>/). SPORT_IDENTITY
and SPORT_CONFIDENCE read the snapshots from here; coupon_sports grades the
coupon's sport legs with `grade_legs` against the stored results, at the
printed price.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from bet.sofa import cs2, shadow

SportKey = Literal["cs2", "hockey", "basketball", "volleyball"]
SPORT_KEYS: tuple[SportKey, ...] = ("cs2", "hockey", "basketball", "volleyball")

KICKOFF_MARGIN = timedelta(minutes=15)  # as coupon/confidence
MAX_PRICE_AGE = timedelta(hours=3)
# A volleyball leg needs a tournament with a SETTLED event over the last
# SETTLED_LOOKBACK_DAYS settled days (settled_tournaments): Superbet lists
# events Sofascore never has (09-29/30: 30 of 50 settled volleyball events
# were NOT_ON_SOFASCORE), and a leg nobody can grade is not a bet.
SETTLED_TOURNAMENT_SPORTS: tuple[SportKey, ...] = ("volleyball",)
SETTLED_LOOKBACK_DAYS = 14


def day_dir(runs_dir: str, sport: SportKey, date: str) -> Path:
    """The measurement's own day directory - never runs/sofa/<date>/."""
    if sport == "cs2":
        return cs2.cs2_day_dir(runs_dir, date)
    return shadow.shadow_day_dir(runs_dir, sport, date)


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def read_snapshots(
    path: Path, upto_lines: int | None = None
) -> tuple[list[dict[str, Any]], int, int]:
    """(records, lines in the file, unreadable lines).

    Read under a shared lock (run_shadow appends under an exclusive one), and
    a line that does not parse - a crash mid-append - is skipped and counted,
    never fatal: one torn line once stopped every later build of its sport.
    `upto_lines` reads only the file's first N lines - what a build saw.
    """
    if not path.exists():
        return [], 0, 0
    with path.open(encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_SH)
        try:
            text = fh.read()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    lines = text.splitlines()
    # Only whole lines: a last line with no newline is an append in progress
    # (or torn). Counting it would let a replay read a record the build never
    # saw once the write completes.
    if lines and not text.endswith("\n"):
        lines = lines[:-1]
    if upto_lines is not None:
        lines = lines[:upto_lines]
    rows: list[dict[str, Any]] = []
    bad = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            bad += 1
    return rows, len(lines), bad


def load_snapshots(path: Path, upto_lines: int | None = None) -> list[dict[str, Any]]:
    return read_snapshots(path, upto_lines)[0]


@contextmanager
def dir_lock(directory: Path) -> Iterator[None]:
    """One writer per directory at a time (the ledger: the 05:15Z loop and a
    /sofa-day run may both record the same day)."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def latest_events(sport: SportKey, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    if sport == "cs2":
        return dict(cs2.latest_pre_kickoff(snapshots))
    return dict(shadow.latest_pre_kickoff(snapshots))


def prev_date(date: str) -> str:
    return (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )


def settled_tournaments(runs_dir: str, sport: SportKey, date: str) -> list[str]:
    """Tournaments with at least one SETTLED event over the last
    SETTLED_LOOKBACK_DAYS settled days strictly before `date`."""
    names: set[str] = set()
    day = date
    for _ in range(SETTLED_LOOKBACK_DAYS):
        day = prev_date(day)
        settled = load_settled(runs_dir, sport, day)
        for ev in ((settled or {}).get("events") or {}).values():
            if ev.get("state") == "SETTLED" and ev.get("tournament"):
                names.add(str(ev["tournament"]))
    return sorted(names)


def load_settled(runs_dir: str, sport: SportKey, date: str) -> dict[str, Any] | None:
    path = day_dir(runs_dir, sport, date) / cs2.SETTLED_FILE
    if not path.exists():
        return None
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def settled_for(
    runs_dir: str, sport: SportKey, dates: set[str]
) -> dict[str, dict[str, Any] | None]:
    """settled.json of each date, and of every date a record there MOVED_TO
    (shadow.MOVED_TO_PREFIX) - what grade_legs follows a moved event to."""
    out: dict[str, dict[str, Any] | None] = {}
    todo = set(dates)
    while todo:
        date = todo.pop()
        if date in out:
            continue
        out[date] = doc = load_settled(runs_dir, sport, date)
        for ev in ((doc or {}).get("events") or {}).values():
            target = shadow.moved_to_date(ev.get("state"))
            if target is not None and target not in out:
                todo.add(target)
    return out


LEG_KEY = (
    "superbet_event_id",
    "market_id",
    "family",
    "period",
    "map_nr",
    "subject",
    "line",
    "side",
)


def _leg_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(k) for k in LEG_KEY)


# SETTLE's final states other than SETTLED / VOID / AWARDED: the event will
# not be graded (shadow.TERMINAL, one set for every measured sport since
# 2026-10-05 - the identity states included). Everything else is asked again,
# so the leg is still pending. MOVED_TO:<date> is followed to that date's file.
TERMINAL_UNGRADED = shadow.TERMINAL - {"SETTLED", "VOID", "AWARDED", shadow.MOVED_TO}
# SETTLE gives up on an event it could not grade within this long of its start
# (settle_shadow / settle_cs2 GIVE_UP_AFTER) - but only if it is ever run on
# that date again, and the daily loops settle D and D-1 only. So a
# NOT_ON_SOFASCORE leg stayed PENDING for ever (2026-10-01: 6 of the 09-30
# volleyball coupon's 8 legs). The coupon's grader applies the same deadline
# itself: past it, a leg still waiting is NOT_GRADED:GAVE_UP.
GIVE_UP_AFTER = timedelta(days=7)


def _stored_winner(ev: dict[str, Any]) -> Literal["T1", "T2"] | None:
    """Sofascore's winner as SHADOW_SETTLE stored it (since 2026-09-30), else
    from the score where the score can tell (never after a shootout)."""
    if ev.get("winner") in ("T1", "T2"):
        return ev["winner"]  # type: ignore[no-any-return]
    if ev.get("status") == "AP":
        return None
    if ev.get("overtime"):
        a, b = ev["t1_full"], ev["t2_full"]
    else:
        a, b = sum(ev["t1_periods"]), sum(ev["t2_periods"])
    return None if a == b else ("T1" if a > b else "T2")


def _grade_leg(sport: SportKey, leg: dict[str, Any], ev: dict[str, Any]) -> str:
    """One leg against a SETTLED event's stored result."""
    if sport == "cs2":
        maps = [cs2.MapResult(int(a), int(b), {}) for a, b in ev.get("maps") or []]
        if not maps:
            return "UNGRADEABLE"
        if int(leg.get("map_nr") or 0) and cs2.map_not_played(
            int(leg["map_nr"]), maps
        ):
            # The series ended before this map (a 2-0 has no map 3): a
            # refund, as Superbet settles it (C4) - also on a series graded
            # from its score alone, whose map count is the series score's.
            return "VOID"
        # Settled from the series score alone (cs2.series_only_maps): its
        # placeholder rounds answer the series families and nothing else.
        if ev.get("series_only") and leg["family"] not in cs2.SERIES_FAMILIES:
            return "UNGRADEABLE"
        line = cs2.Cs2Line(
            leg["superbet_event_id"],
            leg["family"],
            int(leg.get("map_nr") or 0),
            str(leg.get("subject") or ""),
            leg.get("line"),
            leg["side"],
            float(leg["odds"]),
        )
        actual = cs2.actual_value(line, maps, leg["team1"], leg["team2"])
        return "UNGRADEABLE" if actual is None else cs2.grade(line, actual)
    spec_sport = shadow.SPORTS[sport]
    spec = shadow.MARKETS[sport].get(int(leg.get("market_id") or 0))
    if spec is None:
        return "UNGRADEABLE"
    if ev.get("orientation_unclear") and (
        spec.kind not in shadow.ORIENTATION_FREE or spec.team is not None
    ):
        return "UNGRADEABLE"
    result = shadow.GameResult(
        tuple(ev["t1_periods"]),
        tuple(ev["t2_periods"]),
        int(ev["t1_full"]),
        int(ev["t2_full"]),
        _stored_winner(ev),
        bool(ev.get("overtime")),
    )
    sline = shadow.ShadowLine(
        leg["superbet_event_id"],
        int(leg["market_id"]),
        leg["family"],
        int(leg.get("period") or 0),
        str(leg.get("subject") or ""),
        leg.get("line"),
        leg["side"],
        float(leg["odds"]),
    )
    actual = shadow.actual_value(sline, result, spec_sport)
    if actual is None:
        return "UNGRADEABLE"
    return shadow.grade(sline, actual, spec.kind == "three_way")


def _priced_in_play(leg: dict[str, Any], ev: dict[str, Any]) -> bool:
    start = ev.get("sofascore_start_utc")
    priced = leg.get("price_fetched_at_utc")
    return bool(start and priced) and _utc(str(priced)) >= _utc(str(start))


def grade_legs(
    coupon: dict[str, Any],
    settled_by_date: dict[str, dict[str, Any] | None],
    at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Each printed leg graded at the PRINTED price, from the stored result of
    the file its event settles into (`source_date`, else the coupon's date).

    WIN / LOSS / VOID (a push, or a map / set never played); UNGRADEABLE when
    the result cannot answer the line (an ambiguous overtime, an unclear
    orientation); VOID when SETTLE voided the event; NOT_GRADED:<state> for
    an event SETTLE gave up on; IN_PLAY_PRICE when the printed price was
    taken after Sofascore's real start; PENDING / PENDING:<state> until it
    is settled - and, when `at` is given, NOT_GRADED:GAVE_UP once a leg
    still waiting is more than GIVE_UP_AFTER past its kickoff. Where the
    measurement graded the same side too, a disagreement is MISMATCH - it
    means one of the two graders is wrong, and neither result is counted.
    """
    sport: SportKey = coupon["sport"]
    out: list[dict[str, Any]] = []
    for leg in coupon.get("legs", []):
        source = leg.get("source_date") or coupon["date"]
        events = (settled_by_date.get(source) or {}).get("events") or {}
        ev = events.get(leg["superbet_event_id"])
        hops = 0
        while ev is not None and shadow.moved_to_date(ev.get("state")) and hops < 3:
            # The event's record moved to the file of its last snapshot (B4):
            # the leg is graded there, at its own printed price.
            target = shadow.moved_to_date(ev.get("state"))
            assert target is not None
            moved = (settled_by_date.get(target) or {}).get("events") or {}
            ev = moved.get(leg["superbet_event_id"]) or {
                "state": "PENDING",
                "moved_to": target,
            }
            hops += 1
        if ev is None:
            outcome = "PENDING"
        elif ev.get("state") == "SETTLED" and _priced_in_play(leg, ev):
            # the printed price was taken after the game really began: not a
            # pre-match price, never counted (the measurement's
            # NO_PRE_START_PRICE)
            outcome = "IN_PLAY_PRICE"
        elif ev.get("state") == "SETTLED":
            outcome = _grade_leg(sport, leg, ev)
            if outcome == "UNGRADEABLE" and sport == "cs2" and ev.get("pending_sides"):
                # CS2_SETTLE graded part of the series and asks again for the
                # rest (series_only round scores, late player rows): not yet
                # an answer, so pending until the record is final or the
                # leg passes GIVE_UP_AFTER below.
                outcome = f"PENDING:{ev.get('pending_reason') or 'PARTIAL'}"
            measured = {_leg_key(r): r["outcome"] for r in ev.get("graded") or []}
            other = measured.get(_leg_key(leg))
            if other is not None and outcome in ("WIN", "LOSS") and other != outcome:
                outcome = "MISMATCH"
        elif ev.get("state") in ("VOID", "AWARDED"):
            # An awarded match / walkover is no result: the stake comes back.
            outcome = "VOID"
        elif ev.get("state") in TERMINAL_UNGRADED:
            outcome = f"NOT_GRADED:{ev.get('state')}"
        else:  # a state SETTLE asks again (settle_shadow / settle_cs2 RETRYABLE)
            outcome = f"PENDING:{ev.get('state')}"
        if (
            at is not None
            and outcome.startswith("PENDING")
            and at - _utc(leg["kickoff_utc"]) > GIVE_UP_AFTER
        ):
            outcome = "NOT_GRADED:GAVE_UP"
        out.append({**leg, "outcome": outcome})
    return out
