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

Exit 0 OK (or nothing to do), 1 when rows were left alone, 2 on failure.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import GapReason
from bet.sofa.db import RetryingConnection
from bet.sofa.market_mapper import DERIVED_BASE_TO_SIDE_METRIC, derived_base, is_derived
from bet.sofa.metrics import (
    FOOTBALL_METRICS,
    TENNIS_METRICS,
    extract_flat_statistics,
    extract_metric,
)
from bet.sofa.players import is_player_metric
from bet.sofa.settle import settle
from bet.sofa.tennis_score import match_tiebreak_sets
from scripts.sofa.calibrate_from_cache import market_name, match_values
from scripts.sofa.run_settle import _settle_derived, _subject_is_home

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
    """The cached listing payload of each wanted event (what the replay read)."""
    out: dict[int, dict[str, Any]] = {}
    for (events_json,) in conn.execute("SELECT events_json FROM sofa_entity_events"):
        try:
            events = json.loads(events_json).get("events", [])
        except ValueError:
            continue
        for event in events:
            eid = event.get("id")
            # A match sits in a team's `next` listing too, from before it was
            # played: no score there. Only the finished copy can grade it -
            # the first dry run read 38,972 goal rows as ungradable off the
            # pre-match copy.
            finished = (event.get("status") or {}).get("type") == "finished"
            if isinstance(eid, int) and eid in wanted and eid not in out and finished:
                out[eid] = event
    return out


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
        graded = _settle_derived(row, row["sport"], flat, incidents, event)
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
    out: set[int] = set()
    for (events_json,) in conn.execute(
        "SELECT events_json FROM sofa_entity_events"
        " WHERE events_json LIKE '%\"slug\": \"tennis\"%'"
    ):
        try:
            events = json.loads(events_json).get("events", [])
        except ValueError:
            continue
        for event in events:
            eid = event.get("id")
            if not isinstance(eid, int) or eid in out:
                continue
            home, away = event.get("homeScore") or {}, event.get("awayScore") or {}
            if match_tiebreak_sets(home, away):
                out.add(eid)
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


def regrade(
    conn: sqlite3.Connection, runs_dir: Path, *, match_tiebreak: bool = False
) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows = tiebreak_candidates(conn) if match_tiebreak else candidates(conn)
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write; default dry run")
    parser.add_argument(
        "--match-tiebreak",
        action="store_true",
        help="re-grade live tennis games rows on matches with a 10-point match "
        "tiebreak (graded before afdb886f with its points summed as games)",
    )
    args = parser.parse_args()
    config = SofaConfig.from_env()
    at = datetime.now(UTC)
    try:
        # RetryingConnection: a busy COMMIT is retried, as everywhere else.
        conn = sqlite3.connect(
            config.db_path, timeout=30.0, factory=RetryingConnection
        )
        changes, tally = regrade(
            conn, Path(config.runs_dir), match_tiebreak=args.match_tiebreak
        )
    except (sqlite3.Error, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2

    by_day = Counter(
        (c["run_date"], "flip" if c["old_outcome"] != c["new_outcome"] else "actual")
        for c in changes
    )
    metrics: dict[str, Any] = {
        "applied": args.apply,
        "tally": dict(tally),
        "by_day": {f"{d}:{k}": n for (d, k), n in sorted(by_day.items())},
    }
    if args.apply and changes:
        log = Path(config.runs_dir) / f"regrade_{at:%Y%m%dT%H%M%SZ}.json"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(changes, indent=1, ensure_ascii=False) + "\n")
        stamp = at.isoformat()
        with conn:
            conn.executemany(
                "UPDATE sofa_settled_row SET actual_value = ?, outcome = ?,"
                " settled_at = ? WHERE id = ?",
                [(c["new_actual"], c["new_outcome"], stamp, c["id"]) for c in changes],
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
