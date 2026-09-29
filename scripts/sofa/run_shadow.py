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

Writes runs/sofa/shadow/<sport>/<date>/snapshots.jsonl. Exit: 0 OK,
1 PARTIAL (an event fetch failed), 2 FAILED (the board could not be read).
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

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.shadow import (  # noqa: E402
    SNAPSHOTS_FILE,
    SPORT_BY_SUPERBET_ID,
    SPORTS,
    SportKey,
    parse_event,
    shadow_day_dir,
)
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.superbet import SuperbetClient, odds_items, split_match_name  # noqa: E402
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
) -> dict[str, Any]:
    """Append one snapshot of the day's not-yet-started lines, per sport,
    plus the next day's that start within the horizon."""
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    next_day = (start + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        rows = client.events_by_date(
            start, start + timedelta(days=1) + horizon, offer_state="prematch"
        )
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
    for r in rows:
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
        except Exception:
            m["fetch_failed"] += 1
            continue
        fetched_at = stamp()
        lines = parse_event(odds_items(payload), sport.key, event_id, team1, team2)
        if not lines:
            continue
        if day == date:
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
        with paths[key].open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in recs))
    failed = sum(m["fetch_failed"] for m in metrics.values())
    return {
        "verdict": "PARTIAL" if failed else "OK",
        "metrics": metrics,
        "output_path": str(Path(runs_dir) / "shadow"),
    }


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
    )
    print("SOFA_SUMMARY: " + json.dumps({"stage": "SHADOW", **result}), flush=True)
    return {"OK": 0, "PARTIAL": 1}.get(str(result["verdict"]), 2)


if __name__ == "__main__":
    sys.exit(main())
