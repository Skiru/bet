"""Re-grade settled rows whose match data was re-fetched after they were graded.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py  # dry run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py --apply

Why. A settled row is never overwritten (settle.insert_settled_rows): settling
a day twice inserts nothing new. That is right for a forecast and wrong for a
fact that was read off bad data. On 2026-09-28 Sofascore's early snapshots
turned out to be wrong, not just incomplete - event 17059933 was cached with
yellowCards 0-0 and no card incidents, truth 3-3 - and after the cache was
re-fetched, 88 settled card rows on the repaired matches carried the wrong
outcome (20 live, none on a coupon; 68 cache-calibration) and 242 more a wrong
actual_value.

What. Every WIN/LOSS row whose sofa_event_stats.fetched_at is later than its
own settled_at is graded again from the cache, by the code that graded it:
a live row through run_settle's own path (extract_metric, _settle_derived,
the fixture's names for the side), a cache-calibration row through
calibrate_from_cache.match_values (the team id for the side). Only
actual_value, outcome and settled_at change; the forecast (p_central, p_bar,
the sample) is what was believed before the match and stays. A row that now
pushes or can no longer be graded is reported and left alone - removing a
row is not this script's decision.

--apply writes every change, old and new, to runs/sofa/regrade_<ts>.json
first, so it can be undone. No network: the cache is the only input.

Two back-data modes of 2026-10-05 (plan, part 4A):

  --players     live player-prop rows graded again from the cached /lineups
                with SETTLE's squad rule (run_settle._settle_player: only
                the squad SAMPLES matched him in; PLAYER_AMBIGUOUS when the
                other squad holds an equally good name). Flips are applied;
                a row that is now ambiguous is listed and left alone.
  --moved-void  live rows of a match Sofascore started more than 48 h from
                the earliest clock its day held (settle.moved_beyond_void).
                Superbet voided those bets. The row moves to the day the
                match was really played when that day's sheet priced the
                same key (the key is UNIQUE without run_date, so the played
                day's SETTLE could not insert it), else it is deleted. The
                original day's 07_settle_skips.json gets MOVED_BEYOND_VOID
                for the event, so 7c and the ledger read the printed legs as
                a refund. Every printed leg changed is listed.

Without --apply (or with --dry-run) nothing is written.

Exit 0 OK (or nothing to do), 1 when rows were left alone, 2 on failure.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import GapReason
from bet.sofa.db import RetryingConnection
from bet.sofa.listing_index import listed_events_by_id
from bet.sofa.locked_print import kickoff_clocks
from bet.sofa.market_mapper import DERIVED_BASE_TO_SIDE_METRIC, derived_base, is_derived
from bet.sofa.metrics import (
    FOOTBALL_METRICS,
    TENNIS_METRICS,
    extract_flat_statistics,
    extract_metric,
)
from bet.sofa.players import is_player_metric, player_sample_key, squad_statistics
from bet.sofa.settle import MOVED_BEYOND_VOID, moved_beyond_void, settle
from bet.sofa.tennis_score import match_tiebreak_sets
from scripts.sofa.calibrate_from_cache import market_name, match_values
from scripts.sofa.run_settle import (
    _settle_derived,
    _settle_player,
    _subject_is_home,
    load_player_sides,
    player_own_home,
    printed_keys,
    seen_kickoffs,
    skip_totals,
)

CALIBRATION = "cache-calibration"

# A market read off the match's score (goals, goals by half, tennis games per
# set, sets) did not get new data when /statistics and /incidents were
# re-fetched, so a re-grade has nothing new to say about it - and the first
# dry run showed it can still disagree, because SETTLE read the score from the
# /event payload of the day and the cache holds a listing copy (event
# 16378900: settled 1H total 3, the listing says 1H 0-0, 2H 3-4). Neither is
# provably the truth; the row stays as it was graded.
_LISTING_SOURCED = frozenset(
    name
    for name, config in {**FOOTBALL_METRICS, **TENNIS_METRICS}.items()
    if "from_listing" in str(config["sofascore"])
)


def reads_refetched_data(market: str) -> bool:
    """Is this market graded from /statistics or /incidents (what was re-fetched)?"""
    if is_derived(market):
        base = derived_base(market)
        if base is None:
            return False
        side = DERIVED_BASE_TO_SIDE_METRIC.get(base, f"{base}_for")
        return side not in _LISTING_SOURCED
    return market not in _LISTING_SOURCED


def listing_events(
    conn: sqlite3.Connection, wanted: set[int]
) -> dict[int, dict[str, Any]]:
    """The cached listing payload of each wanted event (what the replay read):
    the pages, every kind, and the listed-event index (listing_index.py) -
    calibrate_from_cache replays index-only matches too. First finished page
    copy as before; a newer indexed copy wins."""

    def finished(event: dict[str, Any]) -> dict[str, Any] | None:
        # A match sits in a team's `next` listing too, from before it was
        # played: no score there. Only the finished copy can grade it - the
        # first dry run read 38,972 goal rows as ungradable off the pre-match
        # copy.
        return event if (event.get("status") or {}).get("type") == "finished" else None

    return listed_events_by_id(conn, finished, kinds=None, only=wanted)


def detail_events(
    conn: sqlite3.Connection, wanted: set[int]
) -> dict[int, dict[str, Any]]:
    """The cached /event payload of each wanted event (what SETTLE read)."""
    out: dict[int, dict[str, Any]] = {}
    for eid, detail_json in conn.execute(
        "SELECT sofascore_event_id, detail_json FROM sofa_event_detail"
        " WHERE status_type = 'finished'"
    ):
        if eid in wanted:
            event = (json.loads(detail_json) or {}).get("event")
            if isinstance(event, dict):
                out[int(eid)] = event
    return out


def grade_live(
    row: dict[str, Any],
    event: dict[str, Any],
    fixture: dict[str, Any] | None,
    statistics_json: str | None,
    incidents_json: str | None,
) -> tuple[float, str] | str:
    """(actual, outcome) the way run_settle grades this row, or why not."""
    statistics = json.loads(statistics_json) if statistics_json else None
    incidents = json.loads(incidents_json) if incidents_json else None
    flat = extract_flat_statistics(statistics) if statistics else {}
    if isinstance(flat, GapReason):
        flat = {}
    if is_derived(row["market"]):
        # sided like run_settle: the priced side as fallback (review round 3)
        graded = _settle_derived(row, row["sport"], flat, incidents, event, fixture)
        return graded
    if fixture is None:
        return "NO_FIXTURE"
    is_home = _subject_is_home(row["subject"] or "", fixture)
    if is_home is None:
        return "SUBJECT_NOT_MATCHED"
    value = extract_metric(row["market"], row["sport"], flat, incidents, event, is_home)
    if isinstance(value, GapReason):
        return f"{row['market']}:{value.value}"
    return float(value), settle(float(value), row["line"], row["direction"])


def grade_calibration(
    row: dict[str, Any],
    event: dict[str, Any],
    statistics_json: str | None,
    incidents_json: str | None,
) -> tuple[float, str] | str:
    """(actual, outcome) the way calibrate_from_cache graded this row."""
    values = match_values(event, row["sport"], statistics_json, incidents_json)
    home = (event.get("homeTeam") or {}).get("id")
    away = (event.get("awayTeam") or {}).get("id")
    for base, (h, a) in values.items():
        if row["market"] == market_name(base, "total"):
            actual = h + a
            break
        if row["market"] == market_name(base, "for"):
            if row["subject"] == str(home):
                actual = h
            elif row["subject"] == str(away):
                actual = a
            else:
                return "SUBJECT_NOT_MATCHED"
            break
    else:
        return "VALUE_ABSENT"
    return actual, settle(actual, row["line"], row["direction"])


# Tennis markets a match tiebreak changed (afdb886f): the games counts. A
# row on such a match was graded with the tiebreak's 10 points summed as
# games, whenever its data was fetched - the fetch time says nothing here.
_GAMES_MARKETS = ("games_won_for", "games_total", "handicap_games", "most_games")


def match_tiebreak_events(conn: sqlite3.Connection) -> set[int]:
    """Finished tennis events, in the listing or the /event cache, that had a
    match tiebreak."""
    def had_match_tiebreak(event: dict[str, Any]) -> bool | None:
        home, away = event.get("homeScore") or {}, event.get("awayScore") or {}
        return True if match_tiebreak_sets(home, away) else None

    # The pages (every kind) and the listed-event index (listing_index.py).
    out: set[int] = set(listed_events_by_id(
        conn, had_match_tiebreak, kinds=None,
        like='%"slug": "tennis"%', sport="tennis"))
    # grade_live grades from the /event payload first, and a match can be
    # finished there while every listing copy is still notstarted/inprogress
    # (17175914 and four more on 25-26.09): those rows were missed.
    for eid, detail_json in conn.execute(
        "SELECT sofascore_event_id, detail_json FROM sofa_event_detail"
        " WHERE status_type = 'finished'"
    ):
        try:
            event = (json.loads(detail_json) or {}).get("event") or {}
        except ValueError:
            continue
        home, away = event.get("homeScore") or {}, event.get("awayScore") or {}
        if match_tiebreak_sets(home, away):
            out.add(int(eid))
    return out


def tiebreak_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Live tennis games rows on match-tiebreak events (--match-tiebreak)."""
    wanted = match_tiebreak_events(conn)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""
        SELECT id, run_date, sofascore_event_id, sport, market, subject,
               line, direction, actual_value, outcome, settled_at
        FROM sofa_settled_row
        WHERE sport = 'tennis' AND outcome IN ('WIN', 'LOSS')
          AND run_date != ?
          AND market IN ({",".join("?" * len(_GAMES_MARKETS))})
        """,
        (CALIBRATION, *_GAMES_MARKETS),
    ).fetchall()
    conn.row_factory = None
    return [dict(r) for r in rows if r["sofascore_event_id"] in wanted]


def staff_card_events(conn: sqlite3.Connection) -> set[int]:
    """Events whose cached incidents carry a card shown to staff (a `manager`
    and no `player`) - metrics.calculate_cards_points has ignored those since
    2026-10-02 (Superbet komunikat 06/2022 §2: "Kartki pokazane sztabowi
    szkoleniowemu ... nie będą brane pod uwagę"). One full read of the
    incidents column, filtered by LIKE first."""
    out: set[int] = set()
    for eid, ij in conn.execute(
        "SELECT sofascore_event_id, incidents_json FROM sofa_event_stats"
        " WHERE incidents_json LIKE '%\"manager\"%'"
    ):
        for inc in (json.loads(ij) or {}).get("incidents", []):
            if (
                inc.get("incidentType") == "card"
                and inc.get("manager")
                and not inc.get("player")
                and not inc.get("rescinded")
            ):
                out.add(int(eid))
                break
    return out


def cards_staff_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Card-points rows - live and cache-calibration - on events with a staff
    card (--cards-staff). The grading code changed, not the data, so the
    fetched_at test in candidates() cannot see them. Measured 2026-10-02:
    92 live rows flip on 21 events (34 cards_points_total), 7,296 calibration
    rows; the calibration ones feed the next deliberate refit."""
    wanted = staff_card_events(conn)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, run_date, sofascore_event_id, sport, market, subject,
               line, direction, actual_value, outcome, settled_at
        FROM sofa_settled_row
        WHERE outcome IN ('WIN', 'LOSS') AND market LIKE '%cards_points%'
        """
    ).fetchall()
    conn.row_factory = None
    return [
        dict(r)
        for r in rows
        if r["sofascore_event_id"] in wanted and not is_player_metric(r["market"])
    ]


def candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT r.id, r.run_date, r.sofascore_event_id, r.sport, r.market, r.subject,
               r.line, r.direction, r.actual_value, r.outcome, r.settled_at
        FROM sofa_settled_row r
        JOIN sofa_event_stats s ON s.sofascore_event_id = r.sofascore_event_id
        WHERE julianday(s.fetched_at) > julianday(r.settled_at)
          AND r.outcome IN ('WIN', 'LOSS')
        """
    ).fetchall()
    conn.row_factory = None
    # Player props stay out on purpose. They are graded from the fixture's
    # /lineups (run_settle._settle_player), and lineups are cached forever
    # (samples.fetch_lineups) - nothing re-fetches them, so a newer
    # /statistics fetch says nothing new about a player row. grade_live has
    # no player branch either: it would send the row down the team path and
    # report SUBJECT_NOT_MATCHED. Including them could only produce noise
    # until a lineups re-fetch exists (and a lineup frozen while provisional
    # is a suspicion nobody has measured).
    return [
        dict(r)
        for r in rows
        if not is_player_metric(r["market"]) and reads_refetched_data(r["market"])
    ]


_SELECT_ROW = """
    SELECT id, run_date, sofascore_event_id, sport, market, subject,
           line, direction, actual_value, outcome, settled_at
    FROM sofa_settled_row
"""


def _day_json(runs_dir: Path, day: str, name: str) -> Any:
    path = runs_dir / day / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _fixtures(runs_dir: Path, day: str) -> dict[int, dict[str, Any]]:
    doc = _day_json(runs_dir, day, "02_fixtures.json")
    return {int(f["sofascore_event_id"]): f for f in doc or [] if isinstance(f, dict)}


def player_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Live player-prop rows (--players)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        _SELECT_ROW + " WHERE run_date != ? AND outcome IN ('WIN', 'LOSS')"
        " AND market LIKE 'player_%'",
        (CALIBRATION,),
    ).fetchall()
    conn.row_factory = None
    return [dict(r) for r in rows if is_player_metric(r["market"])]


def regrade_players(
    conn: sqlite3.Connection, runs_dir: Path
) -> tuple[list[dict[str, Any]], Counter[str], list[dict[str, Any]]]:
    """(changes, tally, rows left) for --players: every live player row graded
    again from the cached /lineups with SETTLE's squad rule (A2)."""
    rows = player_candidates(conn)
    events = {r["sofascore_event_id"] for r in rows}
    cached = {
        int(eid): (sj, lj)
        for eid, sj, lj in conn.execute(
            "SELECT sofascore_event_id, statistics_json, lineups_json"
            " FROM sofa_event_stats"
        )
        if eid in events
    }
    details = detail_events(conn, events)
    missing = events - set(details)
    listings = listing_events(conn, missing) if missing else {}
    fixtures: dict[str, dict[int, dict[str, Any]]] = {}
    sides: dict[str, dict[tuple[int, str], str]] = {}
    changes: list[dict[str, Any]] = []
    left: list[dict[str, Any]] = []
    tally: Counter[str] = Counter()
    for row in rows:
        eid = row["sofascore_event_id"]
        day = row["run_date"]
        if day not in fixtures:
            fixtures[day] = _fixtures(runs_dir, day)
            sides[day] = load_player_sides(runs_dir / day)
        event = details.get(eid) or listings.get(eid)
        sj, lj = cached.get(eid, (None, None))
        lineups = json.loads(lj) if lj else None
        if event is None or not lineups:
            reason = "NO_EVENT" if event is None else "PLAYER_NO_LINEUPS"
            tally[f"left:{reason}"] += 1
            continue
        statistics = json.loads(sj) if sj else None
        squads = {
            True: squad_statistics(lineups, is_home=True, statistics=statistics),
            False: squad_statistics(lineups, is_home=False, statistics=statistics),
        }
        side = sides[day].get(
            (eid, player_sample_key(row["market"], row["subject"] or ""))
        )
        own = player_own_home(side, fixtures[day].get(eid), event)
        graded = _settle_player(row, squads, own)
        if isinstance(graded, str):
            reason = graded.split(":")[-1]
            tally[f"left:{reason}"] += 1
            left.append({**row, "reason": reason, "sample_side": side})
            continue
        actual, outcome = graded
        if outcome not in ("WIN", "LOSS"):
            tally["left:PUSH"] += 1
            left.append({**row, "reason": "PUSH", "sample_side": side})
            continue
        if actual == row["actual_value"] and outcome == row["outcome"]:
            tally["unchanged"] += 1
            continue
        kind = "outcome_flipped" if outcome != row["outcome"] else "actual_changed"
        tally[kind] += 1
        changes.append(_change(row, actual, outcome))
    return changes, tally, left


def _change(row: dict[str, Any], actual: float, outcome: str) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_date": row["run_date"],
        "event_id": row["sofascore_event_id"],
        "market": row["market"],
        "subject": row["subject"],
        "line": row["line"],
        "direction": row["direction"],
        "old_actual": row["actual_value"],
        "new_actual": actual,
        "old_outcome": row["outcome"],
        "new_outcome": outcome,
        "old_settled_at": row["settled_at"],
    }


def _key(row: dict[str, Any]) -> tuple[int, str, str, float, str]:
    return (
        int(row["sofascore_event_id"]),
        str(row["market"]),
        str(row.get("subject") or ""),
        float(row["line"]),
        str(row["direction"]),
    )


def moved_void_plan(
    conn: sqlite3.Connection, runs_dir: Path
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """(actions, tally) for --moved-void. One action per live row of a match
    Sofascore started more than VOID_AFTER from the earliest clock of the
    row's own day: `move` to the day it was played (that day's sheet priced
    the key) or `delete`. Each action carries the full row (the undo copy)
    and whether the original day's PDFs printed the leg."""
    conn.row_factory = sqlite3.Row
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM sofa_settled_row WHERE run_date != ?", (CALIBRATION,)
        ).fetchall()
    ]
    conn.row_factory = None
    events = {r["sofascore_event_id"] for r in rows}
    details = detail_events(conn, events)
    missing = events - set(details)
    listings = listing_events(conn, missing) if missing else {}

    fixtures: dict[str, dict[int, dict[str, Any]]] = {}
    seen: dict[str, dict[int, str]] = {}
    priced: dict[str, set[tuple[int, str, str, float, str]]] = {}
    printed: dict[str, set[tuple[int, str, str, float, str]]] = {}

    def load(day: str) -> None:
        if day in fixtures:
            return
        fixtures[day] = _fixtures(runs_dir, day)
        seen[day] = seen_kickoffs(runs_dir / day)
        sheet = _day_json(runs_dir, day, "05_sheet.json") or []
        priced[day] = {
            _key(r) for r in sheet if isinstance(r, dict) and r.get("offered_odds")
        }
        printed[day] = (
            printed_keys(runs_dir / day) if (runs_dir / day).exists() else set()
        )

    actions: list[dict[str, Any]] = []
    tally: Counter[str] = Counter()
    for row in sorted(rows, key=lambda r: (r["run_date"], r["sofascore_event_id"])):
        eid = int(row["sofascore_event_id"])
        day = str(row["run_date"])
        event = details.get(eid) or listings.get(eid)
        if event is None:
            tally["left:NO_EVENT"] += 1
            continue
        load(day)
        fixture = fixtures[day].get(eid)
        if fixture is None:
            tally["left:NO_FIXTURE"] += 1
            continue
        if not moved_beyond_void(event, kickoff_clocks(fixture, seen[day].get(eid))):
            continue
        start = datetime.fromtimestamp(int(event["startTimestamp"]), UTC).date()
        target = None
        for offset in (0, -1, 1):
            cand = (start + timedelta(days=offset)).isoformat()
            if cand == day:
                continue
            load(cand)
            cand_fixture = fixtures[cand].get(eid)
            if (
                _key(row) in priced[cand]
                and cand_fixture is not None
                and not moved_beyond_void(
                    event, kickoff_clocks(cand_fixture, seen[cand].get(eid))
                )
            ):
                target = cand
                break
        action = "move" if target else "delete"
        tally[action] += 1
        actions.append(
            {
                "action": action,
                "id": row["id"],
                "run_date": day,
                "to_run_date": target,
                "event_id": eid,
                "market": row["market"],
                "subject": row["subject"],
                "line": row["line"],
                "direction": row["direction"],
                "outcome": row["outcome"],
                "printed": _key(row) in printed[day],
                "printed_on_target": bool(target)
                and _key(row) in printed[target or ""],
                "row": row,
            }
        )
    return actions, tally


def mark_moved_in_skips(runs_dir: Path, actions: list[dict[str, Any]]) -> list[str]:
    """Write MOVED_BEYOND_VOID into each original day's 07_settle_skips.json
    for the events moved (counted per row). Returns the files changed."""
    per_day: dict[str, Counter[int]] = {}
    for a in actions:
        per_day.setdefault(a["run_date"], Counter())[int(a["event_id"])] += 1
    changed: list[str] = []
    for day, counts in sorted(per_day.items()):
        path = runs_dir / day / "07_settle_skips.json"
        doc = _day_json(runs_dir, day, "07_settle_skips.json")
        if not isinstance(doc, dict):
            doc = {"date": day, "skipped_events": []}
        events = {
            int(e["sofascore_event_id"]): e
            for e in doc.get("skipped_events") or []
            if isinstance(e, dict)
        }
        for eid, n in counts.items():
            entry = events.setdefault(eid, {"sofascore_event_id": eid, "skipped": {}})
            skipped = dict(entry.get("skipped") or {})
            skipped[MOVED_BEYOND_VOID] = max(int(skipped.get(MOVED_BEYOND_VOID, 0)), n)
            entry["skipped"] = skipped
        doc["skipped_events"] = [events[k] for k in sorted(events)]
        doc["skipped"] = skip_totals(doc["skipped_events"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        changed.append(str(path))
    return changed


def regrade(
    conn: sqlite3.Connection,
    runs_dir: Path,
    *,
    match_tiebreak: bool = False,
    cards_staff: bool = False,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    if cards_staff:
        rows = cards_staff_candidates(conn)
    elif match_tiebreak:
        rows = tiebreak_candidates(conn)
    else:
        rows = candidates(conn)
    events = {r["sofascore_event_id"] for r in rows}
    cached = {
        int(eid): (sj, ij)
        for eid, sj, ij in conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json"
            " FROM sofa_event_stats"
        )
        if eid in events
    }
    listings = listing_events(conn, events)
    details = detail_events(conn, events)
    fixtures: dict[str, dict[int, dict[str, Any]]] = {}

    changes: list[dict[str, Any]] = []
    tally: Counter[str] = Counter()
    for row in rows:
        eid = row["sofascore_event_id"]
        # A tiebreak candidate may have no /statistics at all - its games
        # came from the listing, which is exactly the path that was wrong.
        sj, ij = cached.get(eid, (None, None))
        if row["run_date"] == CALIBRATION:
            event = listings.get(eid)
            if event is None:
                tally["left:NO_EVENT"] += 1
                continue
            graded = grade_calibration(row, event, sj, ij)
        else:
            event = details.get(eid) or listings.get(eid)
            if event is None:
                tally["left:NO_EVENT"] += 1
                continue
            day = row["run_date"]
            if day not in fixtures:
                path = runs_dir / day / "02_fixtures.json"
                fixtures[day] = (
                    {f["sofascore_event_id"]: f for f in json.loads(path.read_text())}
                    if path.exists()
                    else {}
                )
            graded = grade_live(row, event, fixtures[day].get(eid), sj, ij)
        if isinstance(graded, str):
            tally[f"left:{graded.split(':')[-1]}"] += 1
            continue
        actual, outcome = graded
        if outcome not in ("WIN", "LOSS"):
            tally["left:PUSH"] += 1
            continue
        if actual == row["actual_value"] and outcome == row["outcome"]:
            tally["unchanged"] += 1
            continue
        kind = "outcome_flipped" if outcome != row["outcome"] else "actual_changed"
        tally[kind] += 1
        changes.append(
            {
                "id": row["id"],
                "run_date": row["run_date"],
                "event_id": eid,
                "market": row["market"],
                "subject": row["subject"],
                "line": row["line"],
                "direction": row["direction"],
                "old_actual": row["actual_value"],
                "new_actual": actual,
                "old_outcome": row["outcome"],
                "new_outcome": outcome,
                "old_settled_at": row["settled_at"],
            }
        )
    return changes, tally


def _apply_moved_void(
    conn: sqlite3.Connection,
    runs_dir: Path,
    actions: list[dict[str, Any]],
    at: datetime,
) -> dict[str, Any]:
    """Write the undo copy first, then the original days' skip files, then
    the database: move a row's run_date or delete it."""
    log = runs_dir / f"regrade_{at:%Y%m%dT%H%M%SZ}.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    before: dict[str, Any] = {}
    for day in sorted({a["run_date"] for a in actions}):
        before[day] = _day_json(runs_dir, day, "07_settle_skips.json")
    log.write_text(
        json.dumps(
            {"mode": "moved-void", "actions": actions, "skips_before": before},
            indent=1,
            ensure_ascii=False,
            default=str,
        )
        + "\n"
    )
    skip_files = mark_moved_in_skips(runs_dir, actions)
    with conn:
        conn.executemany(
            "UPDATE sofa_settled_row SET run_date = ? WHERE id = ?",
            [(a["to_run_date"], a["id"]) for a in actions if a["action"] == "move"],
        )
        conn.executemany(
            "DELETE FROM sofa_settled_row WHERE id = ?",
            [(a["id"],) for a in actions if a["action"] == "delete"],
        )
    return {"log": str(log), "skip_files": skip_files}


def printed_lines(actions: list[dict[str, Any]]) -> list[str]:
    """The printed legs a --moved-void changes, one line each, for the report."""
    out = []
    for a in actions:
        if not (a["printed"] or a["printed_on_target"]):
            continue
        if a["action"] == "move":
            where = f"moved to {a['to_run_date']}"
            if a["printed_on_target"]:
                where += " (printed there too)"
        else:
            where = "deleted"
        out.append(
            f"PRINTED {a['run_date']} event={a['event_id']} {a['market']} "
            f"{a['subject'] or ''} {a['direction']} {a['line']:g} was {a['outcome']}"
            f" -> REFUND; row {where}"
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write; default dry run")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="report only (the default; explicit for scripted calls)",
    )
    kind = parser.add_mutually_exclusive_group()
    kind.add_argument(
        "--match-tiebreak",
        action="store_true",
        help="re-grade live tennis games rows on matches with a 10-point match "
        "tiebreak (graded before afdb886f with its points summed as games)",
    )
    kind.add_argument(
        "--cards-staff",
        action="store_true",
        help="re-grade card-points rows (live and cache-calibration) on events "
        "with a card shown to staff, which Superbet does not count (2026-10-02)",
    )
    kind.add_argument(
        "--players",
        action="store_true",
        help="re-grade live player-prop rows from the cached /lineups, matched "
        "only in the squad SAMPLES found the player in (2026-10-05)",
    )
    kind.add_argument(
        "--moved-void",
        action="store_true",
        help="live rows of a match moved more than 48 h from its day's earliest "
        "clock: move to the played day if that day's sheet priced the key, "
        "else delete; mark MOVED_BEYOND_VOID in the original day's skips "
        "(2026-10-05)",
    )
    args = parser.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir)
    at = datetime.now(UTC)
    left_rows: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    try:
        # RetryingConnection: a busy COMMIT is retried, as everywhere else.
        conn = sqlite3.connect(
            config.db_path, timeout=30.0, factory=RetryingConnection
        )
        if args.moved_void:
            actions, tally = moved_void_plan(conn, runs_dir)
        elif args.players:
            changes, tally, left_rows = regrade_players(conn, runs_dir)
        else:
            changes, tally = regrade(
                conn,
                runs_dir,
                match_tiebreak=args.match_tiebreak,
                cards_staff=args.cards_staff,
            )
    except (sqlite3.Error, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2

    metrics: dict[str, Any] = {"applied": args.apply, "tally": dict(tally)}
    if args.moved_void:
        moves = Counter((a["run_date"], a["action"]) for a in actions)
        metrics["by_day"] = {f"{d}:{k}": n for (d, k), n in sorted(moves.items())}
        printed = printed_lines(actions)
        metrics["printed_changed"] = len(printed)
        for line in printed:
            print(line)
        if args.apply and actions:
            metrics.update(_apply_moved_void(conn, runs_dir, actions, at))
    else:
        by_day = Counter(
            (c["run_date"], "flip" if c["old_outcome"] != c["new_outcome"]
             else "actual")
            for c in changes
        )
        metrics["by_day"] = {f"{d}:{k}": n for (d, k), n in sorted(by_day.items())}
        if args.players:
            for c in changes:
                print(
                    f"PLAYER {c['run_date']} event={c['event_id']} {c['market']} "
                    f"{c['subject']} {c['direction']} {c['line']:g}: "
                    f"{c['old_outcome']} ({c['old_actual']:g}) -> "
                    f"{c['new_outcome']} ({c['new_actual']:g})"
                )
            for r in left_rows:
                if r["reason"] == "PLAYER_AMBIGUOUS":
                    print(
                        f"LEFT {r['run_date']} event={r['sofascore_event_id']} "
                        f"{r['market']} {r['subject']}: PLAYER_AMBIGUOUS "
                        f"(graded {r['outcome']}, left alone)"
                    )
        if args.apply and changes:
            log = runs_dir / f"regrade_{at:%Y%m%dT%H%M%SZ}.json"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(json.dumps(changes, indent=1, ensure_ascii=False) + "\n")
            stamp = at.isoformat()
            with conn:
                conn.executemany(
                    "UPDATE sofa_settled_row SET actual_value = ?, outcome = ?,"
                    " settled_at = ? WHERE id = ?",
                    [
                        (c["new_actual"], c["new_outcome"], stamp, c["id"])
                        for c in changes
                    ],
                )
            metrics["log"] = str(log)
    conn.close()
    left = sum(n for k, n in tally.items() if k.startswith("left:"))
    verdict = "PARTIAL" if left else "OK"
    print(
        "SOFA_SUMMARY: "
        + json.dumps({"stage": "REGRADE", "verdict": verdict, "metrics": metrics})
    )
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
