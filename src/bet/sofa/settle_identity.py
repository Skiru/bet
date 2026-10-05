"""Which Superbet event a measured sport's Sofascore match belongs to.

The shadow sports (hockey, basketball, volleyball) and CS2 start from a
Superbet event and look its match up on Sofascore by name; football and
tennis start from Sofascore's id and never reach this module. Once a day's
settle has found its matches, this pass reads the sport's settled.json files
of D-1..D+1 with their snapshot files and marks every record whose identity
is in doubt - a doubt grades nothing (plan 2026-10-05, part 0 and 4B/4C):

- MOVED_TO:<date>  the same Superbet event is in two dates' snapshot files
  (its kickoff crossed midnight UTC; basketball 15132383 was graded in both
  10-02 and 10-03). The record of the file holding the event's LAST snapshot
  is kept; the other is moved there, and counted once.
- WITHDRAWN  Superbet stopped quoting the event more than 2 h before its
  start and the same pair was later quoted under another Superbet id.
- DUPLICATE_SUPERBET_TEAM  one team name in two Superbet events whose starts
  are less than 3 h apart (CS2 10-05: Vitality Academy in two series at
  10:30Z). Which of them Sofascore's match is cannot be told, so both go.
- DUPLICATE_SOFASCORE_ID  two Superbet events settled to one Sofascore id
  (volleyball 16885527, 10-01: "Texas A&m Aggies" and "Texas AM Commerce
  Lions", both against New Orleans). The record in which BOTH names pass the
  threshold, and of those the one quoted last, is kept; every other is a
  duplicate (`duplicate_of`). None passing both: all are duplicates.

The pass is a pure function of the files: a record it marked keeps the state
settle gave it in `pre_identity_state`, and goes back to it when the doubt is
gone (a later file settles the other way). Old records without the new
fields read as before: name scores are derived from `match_name` and
`sofascore_match` when `name_scores` is absent.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from bet.sofa.cs2 import esports_name, esports_score, file_lock, write_atomic
from bet.sofa.names import normalize_name
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, part_score
from bet.sofa.shadow import (
    MOVED_TO_PREFIX,
    base_state,
)

Kind = Literal["shadow", "cs2"]

# A withdrawn event stopped being quoted this long before its start.
WITHDRAWN_BEFORE = timedelta(hours=2)
# One team in two events this close together is one game listed twice, or two
# rosters under one name - either way the match cannot be told (C5).
TEAM_CLASH = timedelta(hours=3)
# The fields the pass writes; reverted with the state when the doubt is gone.
IDENTITY_FIELDS = (
    "pre_identity_state",
    "identity_reason",
    "duplicate_of",
    "withdrawn_for",
    "duplicate_team",
    "duplicate_team_events",
    "moved_from_state",
)
IDENTITY_STATES = frozenset(
    {"DUPLICATE_SOFASCORE_ID", "WITHDRAWN", "DUPLICATE_SUPERBET_TEAM", "MOVED_TO"}
)


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)


def iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- names --------------------------------------------------------------------


def team_key(kind: Kind, name: str) -> str:
    """A team name folded as the sport's matcher folds it."""
    return esports_name(name) if kind == "cs2" else normalize_name(name)


def name_score(kind: Kind, board: str, sofascore: str) -> float:
    """The matcher's own score of one board name against one Sofascore side."""
    if kind == "cs2":
        return float(esports_score(esports_name(board), esports_name(sofascore)))
    return float(part_score(normalize_name(board), normalize_name(sofascore)))


def pair_scores(
    kind: Kind,
    team1: str,
    team2: str,
    home: str,
    away: str,
    home_is_team1: bool | None,
) -> dict[str, float]:
    """Each board side against the Sofascore side it was graded as (D-b).
    Orientation unknown: the better of the two readings."""
    straight = (name_score(kind, team1, home), name_score(kind, team2, away))
    crossed = (name_score(kind, team1, away), name_score(kind, team2, home))
    if home_is_team1 is None:
        pick = straight if sum(straight) >= sum(crossed) else crossed
    else:
        pick = straight if home_is_team1 else crossed
    return {"team1": round(pick[0], 1), "team2": round(pick[1], 1)}


def split_board(match_name: str) -> tuple[str, str]:
    parts = [p.strip() for p in str(match_name or "").split("·")]
    return (parts[0], parts[1]) if len(parts) == 2 else ("", "")


def split_sofascore(match: str) -> tuple[str, str]:
    parts = str(match or "").split(" - ", 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ("", "")


def record_name_scores(kind: Kind, rec: dict[str, Any]) -> dict[str, float] | None:
    """The record's stored `name_scores`, else derived from its names (an old
    record); None when it names no Sofascore match."""
    stored = rec.get("name_scores")
    if isinstance(stored, dict) and {"team1", "team2"} <= set(stored):
        return {"team1": float(stored["team1"]), "team2": float(stored["team2"])}
    team1 = rec.get("team1") or split_board(rec.get("match_name") or "")[0]
    team2 = rec.get("team2") or split_board(rec.get("match_name") or "")[1]
    listed = split_sofascore(rec.get("sofascore_match") or "")
    home = rec.get("sofascore_home") or listed[0]
    away = rec.get("sofascore_away") or listed[1]
    if not (team1 and team2 and home and away):
        return None
    orientation = rec.get("home_is_team1")
    return pair_scores(
        kind,
        str(team1),
        str(team2),
        str(home),
        str(away),
        orientation if isinstance(orientation, bool) else None,
    )


def both_names_pass(kind: Kind, rec: dict[str, Any]) -> bool:
    scores = record_name_scores(kind, rec)
    return scores is not None and min(scores.values()) > NAME_MATCH_THRESHOLD


# --- snapshots ----------------------------------------------------------------


@dataclass
class SnapInfo:
    """One Superbet event as one date's snapshot file saw it."""

    first: str
    last: str
    kickoff: str  # the latest record's
    team1: str
    team2: str


def snapshot_index(path: Path) -> dict[str, SnapInfo]:
    """Every event of a snapshot file: first and last record, latest kickoff.
    A torn line is skipped, a missing file is {}."""
    out: dict[str, SnapInfo] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            snap = json.loads(line)
        except ValueError:
            continue
        if not isinstance(snap, dict) or "superbet_event_id" not in snap:
            continue
        eid = str(snap["superbet_event_id"])
        at = str(snap.get("fetched_at_utc") or "")
        if not at:
            continue
        info = out.get(eid)
        if info is None:
            out[eid] = SnapInfo(
                at,
                at,
                str(snap.get("kickoff_utc") or ""),
                str(snap.get("team1") or ""),
                str(snap.get("team2") or ""),
            )
            continue
        if _utc(at) < _utc(info.first):
            info.first = at
        if _utc(at) >= _utc(info.last):
            info.last = at
            info.kickoff = str(snap.get("kickoff_utc") or info.kickoff)
            info.team1 = str(snap.get("team1") or info.team1)
            info.team2 = str(snap.get("team2") or info.team2)
    return out


# --- the pass -----------------------------------------------------------------


Change = dict[str, Any]


def _settle_state(rec: dict[str, Any]) -> str:
    """The state settle gave the record, before any identity mark."""
    return str(rec.get("pre_identity_state") or rec.get("state"))


def plan_identity(
    kind: Kind,
    files: dict[str, dict[str, dict[str, Any]]],
    snaps: dict[str, dict[str, SnapInfo]],
) -> dict[tuple[str, str], Change]:
    """{(date, superbet id): {"state": new state, extra fields}} for every
    record whose identity state should change - a mark, or a revert to its
    `pre_identity_state`. `files`: date -> settled events; `snaps`: date ->
    snapshot_index of that date's file."""
    desired: dict[tuple[str, str], Change] = {}

    # 1. MOVED_TO: the same Superbet id in two dates' snapshot files.
    home_date: dict[str, str] = {}
    for date, index in snaps.items():
        for eid, info in index.items():
            best = home_date.get(eid)
            if best is None or (_utc(info.last), date) > (
                _utc(snaps[best][eid].last),
                best,
            ):
                home_date[eid] = date
    for date, events in files.items():
        for eid in events:
            target = home_date.get(eid)
            if target is not None and target != date and eid in snaps.get(date, {}):
                desired[(date, eid)] = {
                    "state": MOVED_TO_PREFIX + target,
                    "identity_reason": (
                        f"the event's last snapshot is in {target}'s file"
                    ),
                }

    # The live view of every event: its home date's snapshot.
    live = {eid: snaps[d][eid] for eid, d in home_date.items()}

    # 2. WITHDRAWN: quoted no more > 2 h before its start, the same pair
    #    quoted later under another id.
    pairs: dict[frozenset[str], list[str]] = {}
    for eid, info in live.items():
        pair = frozenset({team_key(kind, info.team1), team_key(kind, info.team2)})
        if len(pair) == 2:
            pairs.setdefault(pair, []).append(eid)
    withdrawn: dict[str, str] = {}
    for ids in pairs.values():
        if len(ids) < 2:
            continue
        for a in ids:
            ia = live[a]
            if _utc(ia.kickoff) - _utc(ia.last) <= WITHDRAWN_BEFORE:
                continue
            later = [
                b
                for b in ids
                if b != a
                and _utc(live[b].last) > _utc(ia.last)
                and abs(_utc(live[b].kickoff) - _utc(ia.kickoff)) < TEAM_CLASH
            ]
            if later:
                withdrawn[a] = max(later, key=lambda b: _utc(live[b].last))

    # 3. DUPLICATE_SUPERBET_TEAM: one team in two events < 3 h apart.
    by_team: dict[str, list[str]] = {}
    for eid, info in live.items():
        if eid in withdrawn:
            continue
        for name in {team_key(kind, info.team1), team_key(kind, info.team2)}:
            if name:
                by_team.setdefault(name, []).append(eid)
    clash: dict[str, tuple[str, set[str]]] = {}
    for name, ids in by_team.items():
        for a in ids:
            near = {
                b
                for b in ids
                if b != a
                and abs(_utc(live[b].kickoff) - _utc(live[a].kickoff)) < TEAM_CLASH
            }
            if near:
                first_name, seen = clash.get(a, (name, set()))
                clash[a] = (first_name, seen | near)

    # The record each event settles in: its home date's, else any.
    rec_of: dict[str, dict[str, Any]] = {}
    for date, events in files.items():
        for eid, rec in events.items():
            if eid not in rec_of or home_date.get(eid) == date:
                rec_of[eid] = rec

    def confident(eid: str) -> int | None:
        rec = rec_of.get(eid)
        sid = None if rec is None else rec.get("sofascore_event_id")
        if rec is None or not isinstance(sid, int) or not both_names_pass(kind, rec):
            return None
        return sid

    def told_apart(a: str, b: str) -> bool:
        """Two events of one team that each settled to its OWN Sofascore
        match with both names above the threshold: no doubt which is which
        (measured 10-01..10-04: 68 CS2 series of BO1 gauntlets - Glitch in
        five series inside three hours on 10-02 - would otherwise go)."""
        sa, sb = confident(a), confident(b)
        return sa is not None and sb is not None and sa != sb

    for date, events in files.items():
        for eid, rec in events.items():
            if (date, eid) in desired:
                continue
            # A record that found no match grades nothing already and stays
            # retryable; only a found match is put in doubt.
            doubtful: set[str] = set()
            if eid in clash and isinstance(rec.get("sofascore_event_id"), int):
                doubtful = {b for b in clash[eid][1] if not told_apart(eid, b)}
            if eid in withdrawn:
                desired[(date, eid)] = {
                    "state": "WITHDRAWN",
                    "withdrawn_for": withdrawn[eid],
                    "identity_reason": (
                        "last quoted more than 2 h before its start; the same "
                        f"pair later quoted as {withdrawn[eid]}"
                    ),
                }
            elif doubtful:
                name = clash[eid][0]
                desired[(date, eid)] = {
                    "state": "DUPLICATE_SUPERBET_TEAM",
                    "duplicate_team": name,
                    "duplicate_team_events": sorted(doubtful),
                    "identity_reason": (
                        f"{name!r} is in another Superbet event less than 3 h away"
                    ),
                }

    # 4. DUPLICATE_SOFASCORE_ID among the rest.
    by_sofa: dict[int, list[tuple[str, str]]] = {}
    for date, events in files.items():
        for eid, rec in events.items():
            if (date, eid) in desired:
                continue
            sid = rec.get("sofascore_event_id")
            if isinstance(sid, int):
                by_sofa.setdefault(sid, []).append((date, eid))

    def last_seen(where: tuple[str, str]) -> tuple[datetime, str]:
        seen = live.get(where[1])
        at = _utc(seen.last) if seen else datetime.min.replace(tzinfo=UTC)
        return (at, where[0])

    for sid, keys in by_sofa.items():
        if len({eid for _, eid in keys}) < 2:
            continue
        passing = [k for k in keys if both_names_pass(kind, files[k[0]][k[1]])]
        winner = max(passing, key=last_seen) if passing else None
        for where in keys:
            if winner is not None and where[1] == winner[1]:
                continue
            seen_info = live.get(where[1])
            if (
                winner is not None
                and seen_info is not None
                and _utc(seen_info.kickoff) - _utc(seen_info.last) > WITHDRAWN_BEFORE
                and last_seen(winner)[0] > _utc(seen_info.last)
            ):
                desired[where] = {
                    "state": "WITHDRAWN",
                    "withdrawn_for": winner[1],
                    "identity_reason": (
                        "last quoted more than 2 h before its start; Sofascore "
                        f"match {sid} is {winner[1]}'s"
                    ),
                }
                continue
            desired[where] = {
                "state": "DUPLICATE_SOFASCORE_ID",
                "duplicate_of": None if winner is None else winner[1],
                "identity_reason": (
                    f"Sofascore match {sid} is also "
                    + ", ".join(sorted({e for _, e in keys if e != where[1]}))
                    + ("" if winner else "; no record passes both names")
                ),
            }

    changes: dict[tuple[str, str], Change] = {}
    for date, events in files.items():
        for eid, rec in events.items():
            want = desired.get((date, eid))
            marked = "pre_identity_state" in rec
            if want is None:
                if marked:
                    changes[(date, eid)] = {"state": rec["pre_identity_state"]}
                continue
            if marked and all(rec.get(k) == v for k, v in want.items()):
                continue
            changes[(date, eid)] = want
    return changes


def apply_change(rec: dict[str, Any], change: Change) -> dict[str, Any]:
    """The record with one change of plan_identity laid over it."""
    out = {k: v for k, v in rec.items() if k not in IDENTITY_FIELDS}
    settle_state = _settle_state(rec)
    if set(change) == {"state"}:
        out["state"] = settle_state  # the doubt is gone: back to settle's state
        return out
    out.update(change)
    out["pre_identity_state"] = settle_state
    if base_state(change["state"]) == "MOVED_TO":
        out["moved_from_state"] = settle_state
    return out


def load_events(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    events = doc.get("events") if isinstance(doc, dict) else None
    return events if isinstance(events, dict) else {}


def window(date: str) -> list[str]:
    day = datetime.strptime(date, "%Y-%m-%d")
    return [(day + timedelta(days=n)).strftime("%Y-%m-%d") for n in (-1, 0, 1)]


Snaps = dict[str, dict[str, SnapInfo]]


def snaps_window(date: str) -> list[str]:
    """D-2..D+2: every date a record of D-1..D+1 (the files a settle of D
    rewrites) can have moved to or from. With D-1..D+1 only, a settle of D-2
    rewrote D-1 without seeing D's snapshot and reverted D-1's MOVED_TO:D
    every morning - the game was counted on both days again (review
    2026-10-05)."""
    day = datetime.strptime(date, "%Y-%m-%d")
    return [(day + timedelta(days=n)).strftime("%Y-%m-%d") for n in range(-2, 3)]


def load_snaps(date: str, day_dir: Callable[[str], Path], snapshots_file: str) -> Snaps:
    """The snapshot index of every date a record of `date`'s window can
    involve (snaps_window)."""
    return {d: snapshot_index(day_dir(d) / snapshots_file) for d in snaps_window(date)}


def _files(
    date: str,
    today: dict[str, dict[str, Any]],
    day_dir: Callable[[str], Path],
    settled_file: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        d: today if d == date else load_events(day_dir(d) / settled_file)
        for d in window(date)
    }


def reconcile(
    kind: Kind,
    date: str,
    events: dict[str, dict[str, Any]],
    day_dir: Callable[[str], Path],
    settled_file: str,
    snaps: Snaps,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """`date`'s events with the identity pass applied (in memory - the caller
    writes them, under its own lock), and the count of changes per state."""
    counts: dict[str, int] = {}
    changes = plan_identity(kind, _files(date, events, day_dir, settled_file), snaps)
    out = dict(events)
    for (d, eid), change in changes.items():
        if d != date:
            continue
        out[eid] = apply_change(out[eid], change)
        key = base_state(out[eid]["state"])
        counts[key] = counts.get(key, 0) + 1
    return out, counts


def reconcile_neighbours(
    kind: Kind,
    date: str,
    events: dict[str, dict[str, Any]],
    day_dir: Callable[[str], Path],
    settled_file: str,
    snaps: Snaps,
) -> dict[str, int]:
    """D-1's and D+1's settled.json reconciled on disk against `date`'s
    `events`, each re-read and written under its own lock. Called after the
    caller released its own: locks are never nested, so two settles of
    neighbouring days cannot deadlock. Counts keyed "<date>:<state>"."""
    counts: dict[str, int] = {}
    for d in window(date):
        if d == date:
            continue
        path = day_dir(d) / settled_file
        if not path.exists():
            continue
        with file_lock(path):
            files = _files(date, events, day_dir, settled_file)
            fresh = plan_identity(kind, files, snaps)
            mine = {eid: c for (dd, eid), c in fresh.items() if dd == d}
            if not mine:
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            for eid, change in mine.items():
                doc["events"][eid] = apply_change(doc["events"][eid], change)
                key = f"{d}:{base_state(doc['events'][eid]['state'])}"
                counts[key] = counts.get(key, 0) + 1
            write_atomic(path, json.dumps(doc, ensure_ascii=False, indent=1))
    return counts
