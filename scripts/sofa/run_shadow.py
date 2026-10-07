"""SHADOW - snapshot Superbet's hockey, basketball and volleyball lines.

Outside `DEFAULT_SEQUENCE`, like CS2: it neither feeds nor gates the coupon.
It records the two-way lines Superbet posts at the price of the moment, so
SHADOW_SETTLE can grade the last pre-start price once the game is over (see
src/bet/sofa/shadow.py for what is measured and why).

Run it several times a day; each run appends. An event is fetched when it
starts within --horizon-h hours (the price nearest the start is the one that
is graded) or when no earlier run today has recorded it at all (so an event
priced once and never again still has a price). An event of the NEXT day that
starts within the horizon is fetched too, into that day's file: late North
American games start after 00:00Z, before the next day's own loop is running.

Cost: one /events/by-date call plus one /events/{id} per event in scope,
sequential. Superbet only; no bridge, no Sofascore.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_shadow.py --date 2026-09-29
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py \\
        --date 2026-09-29 --only SHADOW

Writes runs/sofa/shadow/<sport>/<date>/snapshots.jsonl and, for basketball
and hockey player lines, the player model's pre-game forecast beside it in
player_model.jsonl (bet.sofa.player_model; read-only database, no request; a
measurement read by SHADOW_SETTLE and measure_player_props.py only). The
forecast runs after the snapshot is written and can never fail or change it.
Exit: 0 OK,
1 PARTIAL (an event fetch failed), 2 FAILED (the board could not be read).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import append_records  # noqa: E402
from bet.sofa.errors import CircuitOpenError  # noqa: E402
from bet.sofa.shadow import (  # noqa: E402
    SNAPSHOTS_FILE,
    SPORT_BY_SUPERBET_ID,
    SPORTS,
    SportKey,
    parse_event,
    shadow_day_dir,
)
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.superbet import (  # noqa: E402
    SuperbetClient,
    odds_items,
    snapshot_verdict,
    split_match_name,
)
from bet.sofa.timeutil import now  # noqa: E402
from scripts.sofa.run_cs2 import tournament_names  # noqa: E402

DEFAULT_HORIZON_H = 3.0


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def recorded_events(path: Path) -> set[str]:
    """Superbet event ids an earlier snapshot of the day already holds."""
    if not path.exists():
        return set()
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                seen.add(str(json.loads(line)["superbet_event_id"]))
            except (ValueError, KeyError):
                continue
    return seen


def snapshot(
    date: str,
    client: SuperbetClient,
    runs_dir: str,
    horizon: timedelta = timedelta(hours=DEFAULT_HORIZON_H),
    at: datetime | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Append one snapshot of the day's not-yet-started lines, per sport,
    plus the next day's that start within the horizon. With `db_path`, then
    the player model's pre-game forecasts (forecast_players)."""
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    next_day = (start + timedelta(days=1)).strftime("%Y-%m-%d")
    # The window runs to the horizon from NOW once the day is over: the loop's
    # snapshots after midnight must see the next morning's early games (the
    # fixed "day + horizon" end stopped at 03:00Z D+1 - review round 4).
    window_end = max(start + timedelta(days=1), at or now()) + horizon
    try:
        rows = client.events_by_date(start, window_end, offer_state="prematch")
    except Exception as exc:
        return {"verdict": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
    rows = [r for r in rows if r.get("sportId") in SPORT_BY_SUPERBET_ID]
    names = tournament_names(client) if rows else {}
    # Each record is stamped when its own event was asked, not when the loop
    # began: a game that starts while the loop runs must not carry a stamp
    # from before its start on a price taken after it. A fixed `at` (tests)
    # stamps every record with it.
    fixed = at

    def stamp() -> str:
        return _iso(fixed if fixed is not None else now())

    at = at or now()
    metrics: dict[str, dict[str, int]] = {
        key: {
            "events_on_board": 0,
            "started": 0,
            "out_of_horizon": 0,
            "events_with_lines": 0,
            "lines": 0,
            "fetch_failed": 0,
            "next_day_events_with_lines": 0,
        }
        for key in SPORTS
    }
    paths = {
        (key, day): shadow_day_dir(runs_dir, key, day) / SNAPSHOTS_FILE
        for key in SPORTS
        for day in (date, next_day)
    }
    seen = {k: recorded_events(p) for k, p in paths.items()}
    records: dict[tuple[SportKey, str], list[dict[str, Any]]] = {k: [] for k in paths}
    fetched_ok = 0
    not_reached = 0
    for index, r in enumerate(rows):
        sport = SPORT_BY_SUPERBET_ID[int(r["sportId"])]
        m = metrics[sport.key]
        try:
            kickoff = datetime.fromisoformat(
                str(r.get("utcDate")).replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError:
            continue
        day = kickoff.strftime("%Y-%m-%d")
        if day == next_day:
            # Only what starts within the horizon; the rest is that day's own
            # loop's to record.
            if kickoff <= at or kickoff - at > horizon:
                continue
        elif day != date:
            continue
        else:
            m["events_on_board"] += 1
            if kickoff <= at:
                m["started"] += 1
                continue
        event_id = str(r.get("eventId"))
        if kickoff - at > horizon and event_id in seen[(sport.key, day)]:
            m["out_of_horizon"] += 1
            continue
        team1, team2 = split_match_name(r.get("matchName"))
        if not team1 or not team2:
            continue
        try:
            payload = client.event_odds(event_id)
        except CircuitOpenError:
            # Superbet refused enough in a row (F6.1): nobody else is asked
            # this snapshot; the loop's next snapshot tries again.
            not_reached = len(rows) - index
            break
        except Exception:
            m["fetch_failed"] += 1
            continue
        fetched_ok += 1
        fetched_at = stamp()
        lines = parse_event(odds_items(payload), sport.key, event_id, team1, team2)
        if not lines and event_id not in seen[(sport.key, day)]:
            continue
        # An event already on file that now quotes nothing gets an empty
        # record: the last record replaces every earlier one whole
        # (latest_pre_kickoff), so its old price stops being "the last
        # pre-start price". Review 2026-10-04: games were graded on prices
        # 628-707 minutes old because nothing newer was ever written.
        if not lines:
            m["emptied"] = m.get("emptied", 0) + 1
        elif day == date:
            m["events_with_lines"] += 1
            m["lines"] += len(lines)
        else:
            m["next_day_events_with_lines"] += 1
        records[(sport.key, day)].append(
            {
                "fetched_at_utc": fetched_at,
                "superbet_event_id": event_id,
                "match_name": r.get("matchName"),
                "team1": team1,
                "team2": team2,
                "kickoff_utc": _iso(kickoff),
                "tournament_id": r.get("tournamentId"),
                "tournament": names.get(str(r.get("tournamentId"))) or None,
                "lines": [ln.as_dict() for ln in lines],
            }
        )
    for key, recs in records.items():
        if not recs:
            continue
        paths[key].parent.mkdir(parents=True, exist_ok=True)
        # One append per sport per snapshot: a crash mid-loop loses this
        # snapshot, never corrupts an earlier one.
        # Two loops can append to one day's file (D-1's covers the next day's
        # early games while D's runs): append_records locks, keeps lines whole.
        append_records(paths[key], recs)
    failed = sum(m["fetch_failed"] for m in metrics.values())
    result: dict[str, Any] = {
        "verdict": snapshot_verdict(failed, fetched_ok, not_reached),
        "breaker_open": bool(not_reached),
        "board_rows_not_reached": not_reached,
        "metrics": metrics,
        "output_path": str(Path(runs_dir) / "shadow"),
    }
    if db_path is not None:
        # After every snapshot is on disk, and outside the verdict: the
        # measurement's model never fails or alters the snapshot.
        try:
            result["player_model"] = forecast_players(
                records, runs_dir, db_path, stamp(), at
            )
        except Exception as exc:
            result["player_model"] = {"error": f"{type(exc).__name__}: {exc}"}
    return result


def pinned_teams(runs_dir: str, sport: str, day: str) -> dict[str, tuple[int, int]]:
    """Superbet event id -> (team1, team2) Sofascore ids of every game
    SPORT_IDENTITY IDENTIFIED in runs/sofa/<d>/sport_fixtures.json, d = the
    snapshot's day and its neighbours (a loop pins D and D+1)."""

    from bet.sofa import sport_identity as si

    base = datetime.strptime(day, "%Y-%m-%d")
    out: dict[str, tuple[int, int]] = {}
    for delta in (-1, 0, 1):
        d = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
        doc = si.load_fixtures(Path(runs_dir) / d / si.FIXTURES_FILE)
        for (sp, sb_id), fx in si.fixtures_by_event(doc).items():
            if sp != sport or fx.get("status") != si.IDENTIFIED:
                continue
            home, away = int(fx["home_id"]), int(fx["away_id"])
            out[str(sb_id)] = (home, away) if fx.get("home_is_team1") else (away, home)
    return out


def forecast_players(
    records: dict[tuple[SportKey, str], list[dict[str, Any]]],
    runs_dir: str,
    db_path: str,
    computed_at: str,
    at: datetime,
) -> dict[str, Any]:
    """Append the player model's forecast for this snapshot's player lines
    to <sport>/<date>/player_model.jsonl, once per (snapshot, line, side),
    and only when the line side's number moved since the last row written.
    Never raises: a failure is counted per sport and the rest goes on."""
    out: dict[str, Any] = {}
    # Imported here, not at the top: a broken model module must cost the
    # forecast, never the snapshot that runs before it.
    import bet.sofa.player_model as player_model

    for (key, day), recs in records.items():
        if key not in player_model.MODEL_SPORTS or not recs:
            continue
        tag = f"{key}/{day}"
        try:
            path = shadow_day_dir(runs_dir, key, day) / player_model.PLAYER_MODEL_FILE
            written = player_model.read_forecasts(path)
            done = {player_model.forecast_key(r) for r in written}
            # A line side whose number has not moved since the last row
            # written for it is not written again (player_model.
            # forecast_signature): the file grew by every line every snapshot.
            last = player_model.last_signatures(written)
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
            try:
                rows = player_model.forecast_records(
                    conn,
                    key,
                    SPORTS[key].sofascore_slug,
                    recs,
                    computed_at,
                    done,
                    int(at.timestamp()),
                    last,
                    pinned_teams(runs_dir, key, day),
                )
            finally:
                conn.close()
            append_records(path, rows)
            out[tag] = {
                "rows": len(rows),
                "with_p": sum(1 for r in rows if r.get("model_p") is not None),
            }
        except Exception as exc:
            out[tag] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def main() -> int:
    set_stage("SHADOW")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"))
    parser.add_argument("--horizon-h", type=float, default=DEFAULT_HORIZON_H)
    args = parser.parse_args()
    result = snapshot(
        args.date,
        SuperbetClient(),
        SofaConfig.from_env().runs_dir,
        timedelta(hours=args.horizon_h),
        db_path=SofaConfig.from_env().db_path,
    )
    print("SOFA_SUMMARY: " + json.dumps({"stage": "SHADOW", **result}), flush=True)
    return {"OK": 0, "PARTIAL": 1}.get(str(result["verdict"]), 2)


if __name__ == "__main__":
    sys.exit(main())
