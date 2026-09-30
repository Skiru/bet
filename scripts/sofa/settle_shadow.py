"""SHADOW_SETTLE - grade a day's hockey / basketball / volleyball snapshots.

Not in `DEFAULT_SEQUENCE`, for SETTLE's reason: it grades a day that is over.
Run it for D-1, and again later - a game still pending is retried:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_shadow.py --date 2026-09-29
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py \\
        --date 2026-09-29 --only SHADOW_SETTLE

Per game it takes the last price seen before the start (SHADOW's snapshots),
finds the game on Sofascore through RESOLVE's own resolver and cache (search
scoped to the sport, events/last page 0, the gender / squad-level gates and
6 h window, the relaxed opponent check, no virtual games; the orientation
refusal is off and `home_is_team1` reads the orientation instead),
asks /event/{id} fresh, and checks the score adds up before grading a line
(src/bet/sofa/shadow.py, build_result). Nothing it writes is read by a stage
that builds the coupon.

Cost: per game, on a cold cache, a search and one events/last page per
candidate (up to three), for team1 and - when team1 misses - team2, plus the
event: ~3-9 requests. On a warm entity cache one listing plus the event. A
day is ~100-190 games; through the bridge a request takes ~1 s sequentially.

Writes runs/sofa/shadow/<sport>/<date>/settled.json. Exit: 0 OK, 1 PARTIAL
(a request failed; rerun later), 2 FAILED (no snapshots at all, or the bridge
refused everything).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from rapidfuzz import fuzz  # noqa: E402

from bet.sofa.cache import SofaCache  # noqa: E402
from bet.sofa.client import SofascoreClient  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import write_atomic  # noqa: E402
from bet.sofa.errors import CircuitOpenError  # noqa: E402
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.resolve import SofaResolver  # noqa: E402
from bet.sofa.shadow import (  # noqa: E402
    SETTLE_AFTER,
    SETTLED_FILE,
    SNAPSHOTS_FILE,
    SPORTS,
    ShadowSport,
    SnapshotEvent,
    SportKey,
    build_player_box,
    build_result,
    event_state,
    is_player_line,
    latest_pre_kickoff,
    settle_event,
    shadow_day_dir,
)
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402

# A fact about the game, never asked again. VOID is the game's own fate;
# GAVE_UP is ours (not graded within GIVE_UP_AFTER), kept apart so the audit
# never reports our lookup failure as Superbet voiding a market.
# A DATA_MISMATCH stays retryable: Sofascore corrects provisional scores
# (2026-09-28).
# NO_PRE_START_PRICE: Sofascore's start was earlier than Superbet's and no
# snapshot predates it - every price we hold was taken in play.
TERMINAL = {"SETTLED", "VOID", "UNUSUAL", "GAVE_UP", "NO_PRE_START_PRICE"}
RETRYABLE = {
    "PENDING",
    "NOT_ON_SOFASCORE",
    "AMBIGUOUS",
    "DATA_MISMATCH",
    "ERROR",
}
# RESOLVE's own margin for a clear reversal; the straight reading must win by
# as much before a team-side line is graded.
ORIENTATION_MARGIN = 20.0
GIVE_UP_AFTER = timedelta(days=7)


def home_is_team1(event: dict[str, Any], team1: str, team2: str) -> bool | None:
    """True when Sofascore's home side is Superbet's team1, None if unclear.

    RESOLVE's orientation gate only refuses a clear reversal (a 20-point
    margin), so a game it accepts can still read either way round - and every
    team total and handicap is graded by side. Here the straight reading must
    win outright; a tie is not graded.
    """
    home = normalize_name((event.get("homeTeam") or {}).get("name") or "")
    away = normalize_name((event.get("awayTeam") or {}).get("name") or "")
    a, b = normalize_name(team1), normalize_name(team2)
    if not home or not away:
        return None
    straight = fuzz.ratio(a, home) + fuzz.ratio(b, away)
    crossed = fuzz.ratio(a, away) + fuzz.ratio(b, home)
    if abs(straight - crossed) < ORIENTATION_MARGIN:
        return None
    return straight > crossed


def find_event(
    resolver: SofaResolver, sport: ShadowSport, ev: SnapshotEvent, kickoff: datetime
) -> dict[str, Any] | str:
    """The Sofascore event of this game, or the state that explains why not.

    Team1 first, then team2 with the roles swapped, as RESOLVE does; the
    board's own order goes in both times. RESOLVE's orientation refusal is
    off: a listing that reads the other way round is still this game, and
    `home_is_team1` grades it from team1's side (with the refusal on, a
    reversed game could never be graded at all). The gender, squad-level
    and 6 h window gates stay; the opponent check is the shadow sports'
    relaxed one (resolve.shadow_opponent_agrees) and virtual games are
    refused (resolve.is_virtual_event). A side that is ambiguous does not
    stop the other side from being tried.
    """
    ambiguous_seen = False
    for side, opponent in ((ev.team1, ev.team2), (ev.team2, ev.team1)):
        _, event, ambiguous = resolver.resolve_entity(
            sport.sofascore_slug,
            side,
            kickoff,
            opponent,
            board_side_a=ev.team1,
            board_side_b=ev.team2,
            record_miss=False,
            check_orientation=False,
        )
        if event:
            return event
        ambiguous_seen = ambiguous_seen or ambiguous
    return "AMBIGUOUS" if ambiguous_seen else "NOT_ON_SOFASCORE"


def settle_one(
    ev: SnapshotEvent,
    sport: ShadowSport,
    resolver: SofaResolver,
    client: SofascoreClient,
    cache: SofaCache | None,
    at: datetime,
    raw: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One game. `raw` is this game's snapshot records, for re-collapsing
    them on Sofascore's clock when the game began before Superbet's."""
    kickoff = datetime.fromisoformat(ev.kickoff_utc.replace("Z", "+00:00"))
    record: dict[str, Any] = {
        "match_name": ev.match_name,
        "kickoff_utc": ev.kickoff_utc,
        "tournament": ev.tournament,
        "priced_sides": len(ev.sides),
    }
    found = find_event(resolver, sport, ev, kickoff)
    if isinstance(found, str):
        return {**record, "state": found}
    record.update(
        {
            "sofascore_event_id": found["id"],
            "sofascore_match": (
                f"{(found.get('homeTeam') or {}).get('name')} - "
                f"{(found.get('awayTeam') or {}).get('name')}"
            ),
            "sofascore_tournament": (found.get("tournament") or {}).get("name"),
        }
    )
    orientation = home_is_team1(found, ev.team1, ev.team2)
    # Unclear orientation still grades the totals, which do not depend on it;
    # every side-dependent line is left out (counted as needs_orientation).
    record["home_is_team1"] = orientation
    record["orientation_unclear"] = orientation is None
    # Fresh, never the cache: a listing's score can be provisional, and a
    # finished payload cached early would be frozen (2026-09-28).
    payload = client.event(int(found["id"])) or {}
    detail = payload.get("event")
    if not isinstance(detail, dict):
        # Never the listing's score in its place: it may be provisional, and
        # a SETTLED is never asked again. Retried on the next run.
        return {**record, "state": "ERROR", "error": "no /event payload"}
    if cache is not None:
        cache.save_event_detail(
            int(found["id"]), payload, (detail.get("status") or {}).get("type")
        )
    state = event_state(detail, sport, kickoff, at)
    if state != "FINISHED":
        # Before the clock check: a postponed game's start may still move, and
        # NO_PRE_START_PRICE is final.
        return {
            **record,
            "state": state,
            "status": (detail.get("status") or {}).get("description"),
        }
    clock = kickoff
    start_ts = detail.get("startTimestamp")
    if isinstance(start_ts, int) and start_ts > 0:
        sofa_start = datetime.fromtimestamp(start_ts, UTC)
        record["sofascore_start_utc"] = sofa_start.isoformat().replace("+00:00", "Z")
        if sofa_start < kickoff and raw is not None:
            # Superbet's clock was late: only a price taken before the real
            # start is a pre-match price (football's earlier-of-two rule).
            clock = sofa_start
            early = latest_pre_kickoff(raw, {ev.superbet_event_id: sofa_start})
            record["started_before_superbet_min"] = round(
                (kickoff - sofa_start).total_seconds() / 60
            )
            # The earlier snapshot replaces the later one whole, so it can
            # hold more sides as well as fewer: both counts, no difference.
            record["priced_sides_superbet_clock"] = len(ev.sides)
            ev = early.get(ev.superbet_event_id) or SnapshotEvent(
                ev.superbet_event_id,
                ev.match_name,
                ev.team1,
                ev.team2,
                ev.kickoff_utc,
                ev.tournament,
            )
            record["priced_sides"] = len(ev.sides)
            if not ev.sides:
                return {**record, "state": "NO_PRE_START_PRICE"}
    result = build_result(detail, sport, orientation is not False)
    if result is None:
        return {
            **record,
            "state": "DATA_MISMATCH",
            "home_score": detail.get("homeScore"),
            "away_score": detail.get("awayScore"),
            "winner_code": detail.get("winnerCode"),
        }
    box = None
    if any(is_player_line(sport.key, ln.market_id) for ln in ev.sides.values()):
        # One request serves every player line of the game; asked fresh, like
        # the event, because a provisional box would be frozen by SETTLED.
        box = build_player_box(client.event_lineups(int(found["id"])), detail, sport)
        record["player_box"] = (
            "missing" if box is None else ("ok" if box.ok else box.reason)
        )
        # A box not published yet, or still provisional, is not a fact about
        # the game: the game is SETTLED for its team lines, and asked again
        # (up to GIVE_UP_AFTER) for its player lines.
        record["player_retry"] = box is None or not box.ok
    graded, counts = settle_event(
        ev, result, sport, totals_only=orientation is None, clock=clock, box=box
    )
    return {
        **record,
        "state": "SETTLED",
        "status": (detail.get("status") or {}).get("description"),
        "t1_periods": list(result.t1_periods),
        "t2_periods": list(result.t2_periods),
        "t1_full": result.t1_full,
        "t2_full": result.t2_full,
        "overtime": result.overtime,
        # The winner as Sofascore decided it: a shootout's deciding goal is
        # not always in `current`, so the score alone cannot say (read back by
        # sport_coupon.grade_coupon).
        "winner": result.winner,
        **counts,
        "graded": graded,
    }


def settle_sport(
    sport: ShadowSport,
    date: str,
    resolver: SofaResolver,
    client: SofascoreClient,
    cache: SofaCache | None,
    runs_dir: str,
    at: datetime,
) -> dict[str, Any]:
    day = shadow_day_dir(runs_dir, sport.key, date)
    snaps_path = day / SNAPSHOTS_FILE
    if not snaps_path.exists():
        return {"verdict": "NO_SNAPSHOTS", "metrics": {}}
    snapshots: list[dict[str, Any]] = []
    unreadable = 0
    for line in snaps_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            snap = json.loads(line)
        except ValueError:
            # One torn line (a crash mid-append) must not take the sport's
            # whole day down; it is counted, not guessed at.
            unreadable += 1
            continue
        if isinstance(snap, dict) and "superbet_event_id" in snap:
            snapshots.append(snap)
        else:
            unreadable += 1
    events = latest_pre_kickoff(snapshots)
    raw_by_event: dict[str, list[dict[str, Any]]] = {}
    for snap in snapshots:
        raw_by_event.setdefault(str(snap["superbet_event_id"]), []).append(snap)
    out = day / SETTLED_FILE
    done: dict[str, Any] = (
        json.loads(out.read_text(encoding="utf-8")).get("events", {})
        if out.exists()
        else {}
    )
    metrics: dict[str, Any] = {
        "events": len(events),
        "too_early": 0,
        "kept": 0,
        "errors": 0,
        "graded_sides": 0,
        "settled_now": 0,
        "unreadable_snapshot_lines": unreadable,
    }
    breaker_open = False
    for eid, ev in sorted(events.items(), key=lambda kv: kv[1].kickoff_utc):
        prev = done.get(eid)
        kickoff = datetime.fromisoformat(ev.kickoff_utc.replace("Z", "+00:00"))
        retry_players = bool(
            prev
            and prev["state"] == "SETTLED"
            and prev.get("player_retry")
            and at - kickoff <= GIVE_UP_AFTER
        )
        if prev and prev["state"] in TERMINAL and not retry_players:
            metrics["kept"] += 1
            continue
        if at - kickoff < SETTLE_AFTER:
            metrics["too_early"] += 1
            continue
        if breaker_open:
            metrics["errors"] += 1
            continue
        try:
            record = settle_one(
                ev, sport, resolver, client, cache, at, raw_by_event.get(eid)
            )
        except CircuitOpenError:
            breaker_open = True
            metrics["errors"] += 1
            continue
        except Exception as exc:
            record = {
                "match_name": ev.match_name,
                "kickoff_utc": ev.kickoff_utc,
                "state": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }
        if record["state"] == "ERROR":
            # An exception or an empty /event alike: the run was not clean.
            metrics["errors"] += 1
        if retry_players and record["state"] != "SETTLED":
            # A retry for the player lines only: a failed attempt (a 403, the
            # game no longer in a listing) must never replace the graded
            # team lines already on file (review round 4, 2026-09-29).
            assert prev is not None
            done[eid] = {**prev, "player_retry_last_error": record["state"]}
            continue
        if record["state"] in RETRYABLE and at - kickoff > GIVE_UP_AFTER:
            record = {**record, "state": "GAVE_UP", "gave_up_on": record["state"]}
        done[eid] = record
        metrics["graded_sides"] += len(record.get("graded") or [])
        if record["state"] == "SETTLED":
            metrics["settled_now"] += 1
    states: dict[str, int] = {}
    for rec in done.values():
        states[rec["state"]] = states.get(rec["state"], 0) + 1
    write_atomic(
        out,
        json.dumps(
            {"date": date, "sport": sport.key, "events": done},
            ensure_ascii=False,
            indent=1,
        ),
    )
    attempted = metrics["events"] - metrics["kept"] - metrics["too_early"]
    # This run's, not the file's: games settled by an earlier run are "kept".
    settled_now = metrics["settled_now"]
    if breaker_open and attempted and metrics["errors"] >= attempted:
        verdict = "FAILED"
    elif metrics["errors"] or unreadable or (attempted and not settled_now):
        # Every game tried and none graded is not a clean day, whatever the
        # reason each one gives.
        verdict = "PARTIAL"
    else:
        verdict = "OK"
    return {
        "verdict": verdict,
        "metrics": {**metrics, "states": states},
        "output_path": str(out),
    }


def settle(
    date: str,
    resolver: SofaResolver,
    client: SofascoreClient,
    cache: SofaCache | None,
    runs_dir: str,
    at: datetime,
    sports: tuple[SportKey, ...] = tuple(SPORTS),
) -> dict[str, Any]:
    per_sport = {
        key: settle_sport(SPORTS[key], date, resolver, client, cache, runs_dir, at)
        for key in sports
    }
    # A sport with no snapshots is a quiet day for that sport, not a fault;
    # nothing settled anywhere is.
    verdicts = [r["verdict"] for r in per_sport.values()]
    if all(v in ("FAILED", "NO_SNAPSHOTS") for v in verdicts):
        verdict = "FAILED"
    elif any(v in ("FAILED", "PARTIAL") for v in verdicts):
        verdict = "PARTIAL"
    else:
        verdict = "OK"
    return {"verdict": verdict, "metrics": per_sport}


def main() -> int:
    set_stage("SHADOW_SETTLE")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--sport", choices=list(SPORTS), action="append")
    args = parser.parse_args()
    config = SofaConfig.from_env()
    client = SofascoreClient(config)
    cache = SofaCache(config)
    resolver = SofaResolver(config, client, cache)
    sports = tuple(args.sport) if args.sport else tuple(SPORTS)
    result = settle(args.date, resolver, client, cache, config.runs_dir, now(), sports)
    print(
        "SOFA_SUMMARY: " + json.dumps({"stage": "SHADOW_SETTLE", **result}),
        flush=True,
    )
    return {"OK": 0, "PARTIAL": 1}.get(str(result["verdict"]), 2)


if __name__ == "__main__":
    sys.exit(main())
