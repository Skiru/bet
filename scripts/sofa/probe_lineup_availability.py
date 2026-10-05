#!/usr/bin/env python3
"""When does Sofascore publish a match's line-ups and absences before kick-off?

Plan docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md, F3.1. Nothing in the cache
can answer it: every /lineups payload in sofa_event_stats was fetched after
the match (the earliest 2.6 h after kick-off, docs/sofa/evidence/
model_defects_2026-10-05.md), and the one live look on 2026-10-01 asked 9 h
before kick-off and found none. This probe asks /event/{id}/lineups of the
day's matches that start within a window from now, and records what came
back: nothing (404), a provisional or a `confirmed` line-up, how many players
each side lists and how many `missingPlayers` (missing / doubtful).

Run it a few times on a day (e.g. 3 h, 2 h, 1 h and 30 min before a block of
kick-offs); a match already asked less than --min-gap-min ago is skipped, so
each pass adds a new horizon. Rows are appended to
runs/sofa/<date>/lineup_probe.jsonl, and --summary reads that file back into
the availability table per competition and horizon (offline, no request).

Bridge: the same SofascoreClient (token bucket, circuit breaker) as the
pipeline, one request at a time, at most --max-events (default 20, hard cap
60) per pass. A refusal (403) opens the breaker and the pass stops - a signal
to slow down, never to retry harder. Nothing the pipeline reads is written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/probe_lineup_availability.py \\
        --date 2026-10-06 --max-hours 3 --max-events 20 [--dry-run]
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/probe_lineup_availability.py \\
        --date 2026-10-06 --summary

Exit: 0 OK, 1 PARTIAL (a request failed), 2 FAILED (the breaker opened, the
clock is frozen on the real runs dir, or no fixtures file).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.errors import CircuitOpenError, ProviderError  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402

OUT_NAME = "lineup_probe.jsonl"
MAX_EVENTS_CAP = 60
# Horizons of the summary table, hours before kick-off (upper bounds).
HORIZONS: tuple[tuple[float, str], ...] = (
    (0.0, "after start"), (0.5, "0-30 min"), (1.0, "30-60 min"),
    (2.0, "1-2 h"), (3.0, "2-3 h"), (6.0, "3-6 h"), (1e9, "> 6 h"),
)


class LineupClient(Protocol):
    def event_lineups(self, id: int) -> Any | None: ...


@dataclass(frozen=True, slots=True)
class ProbeTarget:
    sofascore_event_id: int
    sport: str
    kickoff_utc: datetime
    competition_id: int | None
    competition_name: str | None
    category_name: str | None


def _parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def day_targets(run_dir: Path) -> list[ProbeTarget]:
    """Every match of the day with a Sofascore id: 02_fixtures.json (football,
    tennis) and sport_fixtures.json (the measured sports, identified only)."""
    out: dict[int, ProbeTarget] = {}
    fixtures = run_dir / "02_fixtures.json"
    if fixtures.exists():
        for fx in json.loads(fixtures.read_text()):
            eid, ko = fx.get("sofascore_event_id"), fx.get("kickoff_utc")
            if isinstance(eid, int) and isinstance(ko, str):
                out[eid] = ProbeTarget(
                    eid, str(fx.get("sport") or ""), _parse_utc(ko),
                    fx.get("competition_id"), fx.get("competition_name"),
                    fx.get("category_name"),
                )
    sports = run_dir / "sport_fixtures.json"
    if sports.exists():
        doc = json.loads(sports.read_text())
        for fx in doc.get("fixtures") or []:
            eid, ko = fx.get("sofascore_event_id"), fx.get("kickoff_utc")
            if isinstance(eid, int) and isinstance(ko, str) and eid not in out:
                out[eid] = ProbeTarget(
                    eid, str(fx.get("sport") or ""), _parse_utc(ko),
                    fx.get("competition_id"), fx.get("tournament"), None,
                )
    return sorted(out.values(), key=lambda t: (t.kickoff_utc, t.sofascore_event_id))


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def select(
    targets: Sequence[ProbeTarget],
    at: datetime,
    *,
    sports: Iterable[str],
    min_hours: float,
    max_hours: float,
    max_events: int,
    previous: Sequence[Mapping[str, Any]] = (),
    min_gap_min: float = 30.0,
) -> list[ProbeTarget]:
    """Matches starting between min_hours and max_hours from `at`, not asked
    in the last `min_gap_min` minutes, soonest first, at most `max_events`."""
    wanted = set(sports)
    last_asked: dict[int, datetime] = {}
    for row in previous:
        eid, when = row.get("sofascore_event_id"), row.get("probed_at_utc")
        if isinstance(eid, int) and isinstance(when, str):
            stamp = _parse_utc(when)
            if eid not in last_asked or stamp > last_asked[eid]:
                last_asked[eid] = stamp
    chosen: list[ProbeTarget] = []
    for t in targets:
        if t.sport not in wanted:
            continue
        hours = (t.kickoff_utc - at).total_seconds() / 3600
        if not min_hours <= hours <= max_hours:
            continue
        asked = last_asked.get(t.sofascore_event_id)
        if asked is not None and (at - asked).total_seconds() < min_gap_min * 60:
            continue
        chosen.append(t)
    return chosen[: max(0, min(max_events, MAX_EVENTS_CAP))]


def summarise_payload(payload: Any) -> dict[str, Any]:
    """What a /lineups answer says about availability (None = 404)."""
    if not isinstance(payload, dict) or not payload:
        return {"status": "NOT_FOUND"}
    out: dict[str, Any] = {"status": "OK", "confirmed": payload.get("confirmed")}
    for side in ("home", "away"):
        block = payload.get(side) or {}
        players = block.get("players") or []
        missing = block.get("missingPlayers")
        out[f"{side}_players"] = len(players)
        out[f"{side}_starters"] = sum(1 for p in players if not p.get("substitute"))
        out[f"{side}_formation"] = block.get("formation")
        out[f"{side}_missing_listed"] = missing is not None
        out[f"{side}_missing"] = sum(
            1 for m in missing or [] if m.get("type") == "missing")
        out[f"{side}_doubtful"] = sum(
            1 for m in missing or [] if m.get("type") == "doubtful")
    return out


def probe(
    client: LineupClient,
    targets: Sequence[ProbeTarget],
    out_path: Path,
    date: str,
    clock: Any = now,
) -> tuple[int, int, bool]:
    """Ask each target once, append one row each. (asked, failed, breaker)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    asked = failed = 0
    for t in targets:
        at = clock()
        row: dict[str, Any] = {
            "date": date,
            "probed_at_utc": at.isoformat().replace("+00:00", "Z"),
            "sofascore_event_id": t.sofascore_event_id,
            "sport": t.sport,
            "competition_id": t.competition_id,
            "competition_name": t.competition_name,
            "category_name": t.category_name,
            "kickoff_utc": t.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "hours_before": round((t.kickoff_utc - at).total_seconds() / 3600, 3),
        }
        try:
            payload = client.event_lineups(t.sofascore_event_id)
        except CircuitOpenError:
            return asked, failed, True
        except ProviderError as exc:
            failed += 1
            row.update({"status": "ERROR", "error": str(exc)})
        else:
            row.update(summarise_payload(payload))
        asked += 1
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return asked, failed, False


def horizon(hours: float) -> str:
    if hours < 0:
        return HORIZONS[0][1]
    for upper, label in HORIZONS[1:]:
        if hours <= upper:
            return label
    return HORIZONS[-1][1]


def availability_table(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Per sport x competition x horizon: asked, any line-up, confirmed,
    missingPlayers listed."""
    cells: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for r in rows:
        if r.get("status") == "ERROR":
            continue
        key = (str(r.get("sport")), str(r.get("competition_name") or "?"),
               horizon(float(r.get("hours_before") or 0.0)))
        c = cells[key]
        c[0] += 1
        if r.get("status") == "OK":
            c[1] += 1
            c[2] += bool(r.get("confirmed"))
            c[3] += bool(r.get("home_missing_listed") or r.get("away_missing_listed"))
    order = {label: i for i, (_, label) in enumerate(HORIZONS)}
    out = [
        "| sport | competition | horizon | asked | line-up | confirmed "
        "| missingPlayers |",
        "|---|---|---|---|---|---|---|",
    ]
    for (sport, comp, hz), (n, ok, conf, miss) in sorted(
        cells.items(), key=lambda kv: (kv[0][0], kv[0][1], order[kv[0][2]])
    ):
        out.append(f"| {sport} | {comp} | {hz} | {n} | {ok} | {conf} | {miss} |")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--runs-dir", default=None,
                    help="default: SOFA_RUNS_DIR / runs/sofa")
    ap.add_argument("--sports", nargs="+", default=["football"])
    ap.add_argument("--min-hours", type=float, default=0.0)
    ap.add_argument("--max-hours", type=float, default=3.0)
    ap.add_argument("--max-events", type=int, default=20)
    ap.add_argument("--min-gap-min", type=float, default=30.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="list the matches a pass would ask; no request")
    ap.add_argument("--summary", action="store_true",
                    help="print the availability table of the day's probe file")
    args = ap.parse_args(argv)

    from bet.sofa.config import SofaConfig

    config = SofaConfig.from_env()
    runs_dir = Path(args.runs_dir or config.runs_dir)
    run_dir = runs_dir / args.date
    out_path = run_dir / OUT_NAME
    if args.summary:
        print("\n".join(availability_table(read_rows(out_path))))
        return 0
    refusal = frozen_clock_refusal(runs_dir)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    targets = day_targets(run_dir)
    if not targets:
        print(f"no fixtures with a Sofascore id under {run_dir}", file=sys.stderr)
        return 2
    chosen = select(
        targets, now(), sports=args.sports, min_hours=args.min_hours,
        max_hours=args.max_hours, max_events=args.max_events,
        previous=read_rows(out_path), min_gap_min=args.min_gap_min,
    )
    print(json.dumps({"date": args.date, "fixtures": len(targets),
                      "to_ask": len(chosen), "out": str(out_path)}), flush=True)
    if args.dry_run or not chosen:
        for t in chosen:
            print(f"  {t.sofascore_event_id} {t.sport} {t.kickoff_utc:%H:%MZ} "
                  f"{t.competition_name}")
        return 0

    from bet.sofa.client import SofascoreClient

    if not config.run_id:
        config = dataclasses.replace(
            config, run_id="probe-lineups-" + now().strftime("%Y%m%dT%H%M%SZ"))
    asked, failed, broke = probe(SofascoreClient(config), chosen, out_path, args.date)
    print(json.dumps({"asked": asked, "failed": failed, "breaker_open": broke}))
    if broke:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
