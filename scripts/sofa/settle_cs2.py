"""CS2_SETTLE - grade a day's CS2 snapshots against Sofascore's per-map data.

Not in `DEFAULT_SEQUENCE`, for SETTLE's reason: it grades a day that is over.
Run it for D-1 (and again later - a series still pending is retried):

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_cs2.py --date 2026-09-28
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py \\
        --date 2026-09-28 --only CS2_SETTLE

Per series it takes the last price seen before the start (CS2's snapshots),
finds the series on Sofascore through the bridge, rebuilds every map in order
and checks the maps reproduce Sofascore's own series score before grading a
single line. Nothing it writes is read by a stage that builds the coupon.

Cost: per series a search, two listings per candidate (at most four), the
event, its games, and one lineup per map when a player or team-kill line is
priced. ~10-25 requests a series; a day is ~10-15 real series.

Writes runs/sofa/cs2/<date>/settled.json. Exit: 0 OK, 1 PARTIAL (a request
failed; rerun later), 2 FAILED (no snapshots, or the bridge refused all).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.client import SofascoreClient  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import (  # noqa: E402
    SERIES_FAMILIES,
    SETTLE_AFTER,
    SETTLED_FILE,
    SNAPSHOTS_FILE,
    Cs2Line,
    SnapshotEvent,
    build_series,
    cs2_day_dir,
    event_state,
    latest_pre_kickoff,
    pick_event,
    series_only_maps,
    settle_event,
    stats_missing,
    write_atomic,
)
from bet.sofa.cs2_engine import (  # noqa: E402
    UNFITTED,
    build_ratings,
    load_history,
    model_probability,
)
from bet.sofa.cs2_store import is_complete, save_series  # noqa: E402
from bet.sofa.db import get_connection, migrate  # noqa: E402
from bet.sofa.errors import CircuitOpenError  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402

# States that are a fact about the series and are never asked again. VOID is
# the series' own fate (cancelled, or not played within 48 h - Superbet's
# rule); GAVE_UP is ours - we could not grade it within GIVE_UP_AFTER - and
# the two are kept apart so the audit never reports our lookup failure as
# Superbet voiding the market.
TERMINAL = {"SETTLED", "VOID", "UNUSUAL", "GAVE_UP"}
RETRYABLE = {
    "PENDING",
    "STATS_PENDING",
    "NOT_ON_SOFASCORE",
    "AMBIGUOUS",
    "DATA_MISMATCH",
    "ERROR",
}
GIVE_UP_AFTER = timedelta(days=7)
# Per-player rows land after the score; wait this long for them before
# settling what can be settled without them.
STATS_GRACE = timedelta(hours=72)


class Cs2Sofascore:
    """The few Sofascore reads CS2_SETTLE needs, with per-run listing reuse."""

    def __init__(self, client: SofascoreClient) -> None:
        self.client = client
        self._listings: dict[int, list[dict[str, Any]]] = {}

    def _listing(self, team_id: int) -> list[dict[str, Any]]:
        if team_id not in self._listings:
            events: list[dict[str, Any]] = []
            for kind in ("last", "next"):
                data = self.client.entity_events(team_id, kind, 0) or {}
                events.extend(data.get("events") or [])
            self._listings[team_id] = events
        return self._listings[team_id]

    def find(
        self, ev: SnapshotEvent, kickoff: datetime
    ) -> tuple[dict[str, Any], bool] | str:
        """(event, home is team1), or the state that explains why not."""
        ambiguous = False
        for side in (ev.team1, ev.team2):
            found = self.client.search(side) or {}
            teams = [
                r["entity"]
                for r in found.get("results") or []
                if r.get("type") == "team"
                and ((r.get("entity") or {}).get("sport") or {}).get("slug")
                == "esports"
            ][:4]
            pool: dict[int, dict[str, Any]] = {}
            for team in teams:
                for e in self._listing(int(team["id"])):
                    pool[int(e["id"])] = e
            hit = pick_event(list(pool.values()), ev.team1, ev.team2, kickoff)
            if hit == "AMBIGUOUS":
                ambiguous = True
            elif hit is not None:
                return hit
        return "AMBIGUOUS" if ambiguous else "NOT_ON_SOFASCORE"


def _needs_players(ev: SnapshotEvent) -> bool:
    return any(k[0].startswith("player_") or k[0] == "team_kills" for k in ev.sides)


def settle_one(
    ev: SnapshotEvent, sofa: Cs2Sofascore, at: datetime, db_path: str | None = None
) -> dict[str, Any]:
    kickoff = datetime.fromisoformat(ev.kickoff_utc.replace("Z", "+00:00"))
    record: dict[str, Any] = {
        "match_name": ev.match_name,
        "kickoff_utc": ev.kickoff_utc,
        "tournament": ev.tournament,
        "priced_sides": len(ev.sides),
    }
    found = sofa.find(ev, kickoff)
    if isinstance(found, str):
        return {**record, "state": found}
    event, home_is_t1 = found
    record.update(
        {
            "sofascore_event_id": event["id"],
            "sofascore_match": (
                f"{event['homeTeam']['name']} - {event['awayTeam']['name']}"
            ),
            "sofascore_tournament": (event.get("tournament") or {}).get("name"),
            "home_is_team1": home_is_t1,
        }
    )
    detail = (sofa.client.event(int(event["id"])) or {}).get("event") or event
    state = event_state(detail, kickoff, at)
    if state != "FINISHED":
        return {
            **record,
            "state": state,
            "status": (detail.get("status") or {}).get("description"),
        }
    games = (sofa.client.esports_games(int(event["id"])) or {}).get("games") or []
    lineups: dict[int, dict[str, Any] | None] = {}
    if _needs_players(ev):
        for g in games:
            if g.get("hasCompleteStatistics"):
                lineups[int(g["id"])] = sofa.client.esports_game_lineups(int(g["id"]))
    if db_path is not None:
        store_series(event, detail, games, lineups, at, kickoff, db_path, record)
    maps = build_series(detail, games, lineups, home_is_t1)
    if maps is None:
        series = series_only_maps(detail, games, home_is_t1)
        if series is None:
            return {**record, "state": "DATA_MISMATCH", "games": len(games)}
        # Rounds unknown, series score known: grade the series lines only.
        series_ev = replace(
            ev,
            sides={k: ln for k, ln in ev.sides.items() if ln.family in SERIES_FAMILIES},
            fetched_at={
                k: v
                for k, v in ev.fetched_at.items()
                if ev.sides[k].family in SERIES_FAMILIES
            },
        )
        graded, counts = settle_event(series_ev, series)
        return {
            **record,
            "state": "SETTLED",
            "series_only": True,
            "maps": [[m.t1_rounds, m.t2_rounds] for m in series],
            "maps_with_players": 0,
            **counts,
            "graded": graded,
        }
    if stats_missing(ev, maps) and at - kickoff < STATS_GRACE:
        return {**record, "state": "STATS_PENDING", "maps": len(maps)}
    graded, counts = settle_event(ev, maps)
    if db_path is not None:
        try:
            attach_model(graded, ev, event, detail, home_is_t1, kickoff, db_path)
        except Exception as exc:
            # The grade stands without a model number; the audit's model
            # section simply has fewer rows. Never the other way round.
            record["model_error"] = f"{type(exc).__name__}: {exc}"
    return {
        **record,
        "state": "SETTLED",
        "maps": [[m.t1_rounds, m.t2_rounds] for m in maps],
        "maps_with_players": sum(1 for m in maps if m.players),
        **counts,
        "graded": graded,
    }


def store_series(
    event: dict[str, Any],
    detail: dict[str, Any],
    games: list[dict[str, Any]],
    lineups: dict[int, dict[str, Any] | None],
    at: datetime,
    kickoff: datetime,
    db_path: str,
    record: dict[str, Any],
) -> None:
    """The graded series joins the history the backfill keeps.

    Marked complete only when every finished map with statistics had its
    lineup fetched here - settle asks for lineups only when a player line was
    priced, and marking the rest complete would stop the backfill from ever
    fetching them. A failed write is recorded, never turned into a failed
    grade: the store is a by-product of settling, not its purpose.
    """
    fetched = {gid: rows for gid, rows in lineups.items() if rows is not None}
    wanted = {
        int(g["id"])
        for g in games
        if (g.get("status") or {}).get("type") == "finished"
        and g.get("hasCompleteStatistics")
    }
    merged = {**event, **detail}
    # None keeps whatever the store already says (a backfill's complete=1
    # stays); only a run that fetched every lineup may set the flag itself.
    complete: bool | None = (
        is_complete(merged, games, fetched, at - kickoff)
        if wanted <= set(fetched)
        else None
    )
    try:
        with get_connection(db_path) as conn:
            save_series(
                conn,
                merged,
                games,
                fetched,
                at.isoformat().replace("+00:00", "Z"),
                complete,
            )
    except Exception as exc:
        record["store_error"] = f"{type(exc).__name__}: {exc}"


def attach_model(
    graded: list[dict[str, Any]],
    ev: SnapshotEvent,
    event: dict[str, Any],
    detail: dict[str, Any],
    home_is_t1: bool,
    kickoff: datetime,
    db_path: str,
) -> None:
    """Put the engine's pre-match probability beside each graded side.

    History is cut at the earlier of Superbet's kickoff and Sofascore's start,
    and this series is excluded by id - Sofascore lists a series minutes
    before Superbet's time, and a map of the graded series in its own history
    would be the answer read back as a forecast.
    """
    sofa_start = int(event.get("startTimestamp") or kickoff.timestamp())
    before = min(int(kickoff.timestamp()), sofa_start) - 60
    with get_connection(db_path) as conn:
        history = load_history(conn, before, int(event["id"]))
    ratings = build_ratings(history)
    home_id = int((event.get("homeTeam") or {}).get("id") or 0)
    away_id = int((event.get("awayTeam") or {}).get("id") or 0)
    t1_id, t2_id = (home_id, away_id) if home_is_t1 else (away_id, home_id)
    best_of = int(detail.get("bestOf") or event.get("bestOf") or 3)
    for row in graded:
        line = Cs2Line(**{k: row[k] for k in Cs2Line.__dataclass_fields__})
        mp = model_probability(
            line,
            t1_id,
            t2_id,
            ev.team1,
            ev.team2,
            best_of,
            history,
            ratings,
            home_is_t1,
        )
        row["model_p"] = None if mp is None else round(mp.p, 4)
        row["model_n"] = None if mp is None else mp.n
        row["model"] = None if mp is None else mp.model
        row["unfitted_constants"] = list(UNFITTED)


def settle(
    date: str,
    client: SofascoreClient,
    runs_dir: str,
    at: datetime,
    db_path: str | None = None,
) -> dict[str, Any]:
    day = cs2_day_dir(runs_dir, date)
    snaps_path = day / SNAPSHOTS_FILE
    if not snaps_path.exists():
        return {"verdict": "FAILED", "error": f"no {snaps_path}"}
    # One torn line (a crash mid-append) must not take the whole day down;
    # it is skipped, as settle_shadow does.
    snapshots = []
    for line in snaps_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            snapshots.append(json.loads(line))
        except ValueError:
            continue
    events = latest_pre_kickoff(snapshots)
    out = day / SETTLED_FILE
    done: dict[str, Any] = (
        json.loads(out.read_text(encoding="utf-8")).get("events", {})
        if out.exists()
        else {}
    )
    sofa = Cs2Sofascore(client)
    metrics: dict[str, int] = {
        "events": len(events),
        "too_early": 0,
        "kept": 0,
        "errors": 0,
        "graded_sides": 0,
    }
    breaker_open = False
    for eid, ev in sorted(events.items(), key=lambda kv: kv[1].kickoff_utc):
        prev = done.get(eid)
        if prev and prev["state"] in TERMINAL:
            metrics["kept"] += 1
            continue
        kickoff = datetime.fromisoformat(ev.kickoff_utc.replace("Z", "+00:00"))
        if at - kickoff < SETTLE_AFTER:
            metrics["too_early"] += 1
            continue
        if breaker_open:
            metrics["errors"] += 1
            continue
        try:
            record = settle_one(ev, sofa, at, db_path)
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
            metrics["errors"] += 1
        if record["state"] in RETRYABLE and at - kickoff > GIVE_UP_AFTER:
            record = {**record, "state": "GAVE_UP", "gave_up_on": record["state"]}
        done[eid] = record
        metrics["graded_sides"] += len(record.get("graded") or [])
    states: dict[str, int] = {}
    for rec in done.values():
        states[rec["state"]] = states.get(rec["state"], 0) + 1
    write_atomic(
        out, json.dumps({"date": date, "events": done}, ensure_ascii=False, indent=1)
    )
    attempted = metrics["events"] - metrics["kept"] - metrics["too_early"]
    if breaker_open and attempted and metrics["errors"] >= attempted:
        verdict = "FAILED"
    elif metrics["errors"]:
        verdict = "PARTIAL"
    else:
        verdict = "OK"
    return {
        "verdict": verdict,
        "metrics": {**metrics, "states": states},
        "output_path": str(out),
    }


def main() -> int:
    set_stage("CS2_SETTLE")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    config = SofaConfig.from_env()
    migrate(config.db_path)
    result = settle(
        args.date, SofascoreClient(config), config.runs_dir, now(), config.db_path
    )
    print("SOFA_SUMMARY: " + json.dumps({"stage": "CS2_SETTLE", **result}), flush=True)
    return {"OK": 0, "PARTIAL": 1}.get(str(result["verdict"]), 2)


if __name__ == "__main__":
    sys.exit(main())
