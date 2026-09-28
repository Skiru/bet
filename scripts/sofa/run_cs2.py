"""CS2 - snapshot Superbet's Counter-Strike 2 lines before each series starts.

Outside `DEFAULT_SEQUENCE`, like BOOSTS: it neither feeds nor gates the
coupon. It records the two-way CS2 lines Superbet posts, at the price of the
moment, so CS2_SETTLE can grade the last pre-start price once the series is
over (see src/bet/sofa/cs2.py for what is measured and why).

Run it several times a day - tier-2 series are priced late and move - and
each run appends; CS2_SETTLE keeps the last price seen before the start.

Cost: one /events/by-date call plus one /events/{id} per not-yet-started CS2
event. Superbet only; no bridge, no Sofascore.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_cs2.py --date 2026-09-28
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py \\
        --date 2026-09-28 --only CS2

Writes runs/sofa/cs2/<date>/snapshots.jsonl. Exit: 0 OK, 1 PARTIAL (an event
fetch failed), 2 FAILED (the board itself could not be read).
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
from bet.sofa.cs2 import (  # noqa: E402
    SNAPSHOTS_FILE,
    SUPERBET_CS2_SPORT_ID,
    cs2_day_dir,
    parse_event,
)
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.superbet import SuperbetClient, odds_items, split_match_name  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402


def tournament_names(client: SuperbetClient) -> dict[str, str]:
    """Superbet's tournament id -> Polish name, or {} if the struct is down."""
    try:
        struct = client._get_json("/v2/pl-PL/struct") or {}
    except Exception:
        return {}
    data = struct.get("data", struct) if isinstance(struct, dict) else {}
    return {
        str(t.get("id")): str((t.get("localNames") or {}).get("pl-PL") or "")
        for t in data.get("tournaments") or []
    }


def snapshot(date: str, client: SuperbetClient, runs_dir: str) -> dict[str, Any]:
    """Append one snapshot of the day's not-yet-started CS2 lines."""
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    try:
        rows = client.events_by_date(
            start, start + timedelta(days=1), offer_state="prematch"
        )
    except Exception as exc:
        return {"verdict": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
    rows = [r for r in rows if r.get("sportId") == SUPERBET_CS2_SPORT_ID]
    names = tournament_names(client) if rows else {}
    at = now()
    fetched_at = at.isoformat().replace("+00:00", "Z")
    out = cs2_day_dir(runs_dir, date) / SNAPSHOTS_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    metrics = {
        "events_on_board": 0,
        "started": 0,
        "events_with_lines": 0,
        "lines": 0,
        "fetch_failed": 0,
    }
    records = []
    for r in rows:
        try:
            kickoff = datetime.fromisoformat(
                str(r.get("utcDate")).replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if kickoff.astimezone(UTC).strftime("%Y-%m-%d") != date:
            continue
        metrics["events_on_board"] += 1
        if kickoff <= at:
            metrics["started"] += 1
            continue
        team1, team2 = split_match_name(r.get("matchName"))
        if not team1 or not team2:
            continue
        event_id = str(r.get("eventId"))
        try:
            payload = client.event_odds(event_id)
        except Exception:
            metrics["fetch_failed"] += 1
            continue
        lines = parse_event(odds_items(payload), event_id, team1, team2)
        if not lines:
            continue
        metrics["events_with_lines"] += 1
        metrics["lines"] += len(lines)
        records.append(
            {
                "fetched_at_utc": fetched_at,
                "superbet_event_id": event_id,
                "match_name": r.get("matchName"),
                "team1": team1,
                "team2": team2,
                "kickoff_utc": kickoff.astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "tournament_id": r.get("tournamentId"),
                "tournament": names.get(str(r.get("tournamentId"))) or None,
                "lines": [ln.as_dict() for ln in lines],
            }
        )
    # One write per snapshot, appended whole: a crash mid-loop loses this
    # snapshot, never corrupts an earlier one.
    if records:
        with out.open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in records))
    verdict = "PARTIAL" if metrics["fetch_failed"] else "OK"
    return {"verdict": verdict, "metrics": metrics, "output_path": str(out)}


def main() -> int:
    set_stage("CS2")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    result = snapshot(args.date, SuperbetClient(), SofaConfig.from_env().runs_dir)
    print("SOFA_SUMMARY: " + json.dumps({"stage": "CS2", **result}), flush=True)
    return {"OK": 0, "PARTIAL": 1}.get(str(result["verdict"]), 2)


if __name__ == "__main__":
    sys.exit(main())
