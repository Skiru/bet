"""CS2 shadow measurement - prices now, results later, never a coupon.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/cs2_shadow.py snapshot [--date D]
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/cs2_shadow.py settle   [--date D]
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/cs2_shadow.py report \
        [--from D --to D]

snapshot  asks Superbet (not Sofascore) for every CS2 event on D that has not
          started and appends its two-way lines to snapshots.jsonl. Run it
          several times a day; settle grades the last price seen before start.
settle    finds each started event on Sofascore through the bridge and grades
          its lines from the per-map scores and per-map player rows.
report    per market family: settled lines, the devigged price's mean against
          the hit rate, Brier, and the flat return of staking every side.

Files live in runs/sofa/cs2/<date>/, beside the pipeline and never inside a
day's own directory. See src/bet/sofa/cs2.py for why this exists.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bet.sofa.client import SofascoreClient  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import (  # noqa: E402
    SOFASCORE_CS_CATEGORY,
    SUPERBET_CS2_SPORT_ID,
    Cs2Line,
    MapResult,
    actual_value,
    build_map_result,
    fair_probability,
    grade,
    parse_event,
)
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, name_score  # noqa: E402
from bet.sofa.superbet import SuperbetClient, odds_items, split_match_name  # noqa: E402

API = "https://api.sofascore.com/api/v1"
MATCH_WINDOW = timedelta(hours=6)
# A best-of-three runs ~2.5 h; settle waits this long after the start.
SETTLE_AFTER = timedelta(hours=4)


def day_dir(date: str) -> Path:
    base = Path(os.environ.get("SOFA_RUNS_DIR", "runs/sofa")) / "cs2" / date
    base.mkdir(parents=True, exist_ok=True)
    return base


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)


# --- snapshot ---------------------------------------------------------------


def snapshot(date: str) -> int:
    client = SuperbetClient()
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    rows = [
        r
        for r in client.events_by_date(
            start, start + timedelta(days=1), offer_state="all"
        )
        if r.get("sportId") == SUPERBET_CS2_SPORT_ID
    ]
    now = datetime.now(UTC)
    fetched_at = now.isoformat().replace("+00:00", "Z")
    out = day_dir(date) / "snapshots.jsonl"
    events_seen = with_lines = lines_total = 0
    with out.open("a", encoding="utf-8") as fh:
        for r in rows:
            kickoff = _utc(str(r.get("utcDate")))
            if kickoff.strftime("%Y-%m-%d") != date:
                continue
            events_seen += 1
            if kickoff <= now:
                continue
            team1, team2 = split_match_name(r.get("matchName"))
            if not team1 or not team2:
                continue
            event_id = str(r.get("eventId"))
            lines = parse_event(
                odds_items(client.event_odds(event_id)), event_id, team1, team2
            )
            if not lines:
                continue
            with_lines += 1
            lines_total += len(lines)
            fh.write(
                json.dumps(
                    {
                        "fetched_at_utc": fetched_at,
                        "superbet_event_id": event_id,
                        "match_name": r.get("matchName"),
                        "team1": team1,
                        "team2": team2,
                        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
                        "tournament_id": r.get("tournamentId"),
                        "lines": [ln.as_dict() for ln in lines],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(
        json.dumps(
            {
                "stage": "CS2_SNAPSHOT",
                "date": date,
                "events_on_board": events_seen,
                "events_with_lines": with_lines,
                "lines": lines_total,
                "output_path": str(out),
            }
        )
    )
    return 0


# --- settle -----------------------------------------------------------------


def _latest_before_kickoff(date: str) -> dict[str, dict[str, Any]]:
    """Per event: its meta, and every line at the last price seen pre-start."""
    path = day_dir(date) / "snapshots.jsonl"
    events: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return events
    for raw in path.read_text(encoding="utf-8").splitlines():
        snap = json.loads(raw)
        if _utc(snap["fetched_at_utc"]) >= _utc(snap["kickoff_utc"]):
            continue
        ev = events.setdefault(snap["superbet_event_id"], {**snap, "by_side": {}})
        # A rescheduled match keeps the kickoff of its latest listing.
        ev["kickoff_utc"] = snap["kickoff_utc"]
        for d in snap["lines"]:
            key = (d["family"], d["map_nr"], d["subject"], d["line"], d["side"])
            prev = ev["by_side"].get(key)
            if prev is None or prev[0] <= snap["fetched_at_utc"]:
                ev["by_side"][key] = (snap["fetched_at_utc"], d)
    return events


class SofaCs2:
    def __init__(self, client: SofascoreClient) -> None:
        self.client = client
        self._listings: dict[int, list[dict[str, Any]]] = {}

    def _events(self, team_id: int) -> list[dict[str, Any]]:
        if team_id not in self._listings:
            events: list[dict[str, Any]] = []
            for kind in ("last", "next"):
                data = self.client.entity_events(team_id, kind, 0)
                events.extend((data or {}).get("events") or [])
            self._listings[team_id] = [
                e
                for e in events
                if ((e.get("tournament") or {}).get("category") or {}).get("name")
                == SOFASCORE_CS_CATEGORY
            ]
        return self._listings[team_id]

    def resolve(
        self, team1: str, team2: str, kickoff: datetime
    ) -> tuple[dict[str, Any], bool] | None:
        """(Sofascore event, whether its home side is Superbet's team1)."""
        for side, other in ((team1, team2), (team2, team1)):
            found = self.client.search(normalize_name(side)) or {}
            candidates = [
                r["entity"]
                for r in found.get("results") or []
                if r.get("type") == "team"
                and ((r.get("entity") or {}).get("sport") or {}).get("slug")
                == "esports"
            ][:4]
            want = normalize_name(other)
            for cand in candidates:
                for e in self._events(int(cand["id"])):
                    start = datetime.fromtimestamp(
                        int(e.get("startTimestamp") or 0), UTC
                    )
                    if abs(start - kickoff) > MATCH_WINDOW:
                        continue
                    home = normalize_name(e["homeTeam"]["name"])
                    away = normalize_name(e["awayTeam"]["name"])
                    if (
                        max(name_score(want, home), name_score(want, away))
                        <= NAME_MATCH_THRESHOLD
                    ):
                        continue
                    t1 = normalize_name(team1)
                    return e, name_score(t1, home) >= name_score(t1, away)
        return None

    def maps(
        self, event_id: int, home_is_t1: bool, need_players: bool
    ) -> tuple[str, list[MapResult]]:
        detail = (self.client.event(event_id) or {}).get("event") or {}
        status = str((detail.get("status") or {}).get("type") or "unknown")
        if status != "finished":
            return status, []
        games = (
            self.client._execute(f"{API}/event/{event_id}/esports-games") or {}
        ).get("games") or []
        games = sorted(games, key=lambda g: int(g.get("startTimestamp") or 0))
        out: list[MapResult] = []
        for g in games:
            lineups = None
            if need_players and g.get("hasCompleteStatistics"):
                lineups = self.client._execute(f"{API}/esports-game/{g['id']}/lineups")
            result = build_map_result(g, lineups, home_is_t1)
            if result is not None:
                out.append(result)
        return status, out


def settle(date: str) -> int:
    events = _latest_before_kickoff(date)
    sofa = SofaCs2(SofascoreClient(SofaConfig.from_env()))
    now = datetime.now(UTC)
    settled_path = day_dir(date) / "settled.json"
    previous = (
        json.loads(settled_path.read_text(encoding="utf-8"))
        if settled_path.exists()
        else {}
    )
    done: dict[str, Any] = previous.get("events", {})
    counts: dict[str, int] = defaultdict(int)
    for event_id, ev in events.items():
        if event_id in done and done[event_id]["state"] in (
            "SETTLED",
            "NOT_ON_SOFASCORE",
        ):
            counts["already"] += 1
            continue
        kickoff = _utc(ev["kickoff_utc"])
        if now - kickoff < SETTLE_AFTER:
            counts["too_early"] += 1
            continue
        record: dict[str, Any] = {
            "match_name": ev["match_name"],
            "kickoff_utc": ev["kickoff_utc"],
            "tournament_id": ev.get("tournament_id"),
        }
        hit = sofa.resolve(ev["team1"], ev["team2"], kickoff)
        if hit is None:
            record["state"] = "NOT_ON_SOFASCORE"
            done[event_id] = record
            counts["not_on_sofascore"] += 1
            continue
        sofa_event, home_is_t1 = hit
        lines = {k: d for k, (_, d) in ev["by_side"].items()}
        need_players = any(
            d["family"].startswith("player_") or d["family"] == "team_kills"
            for d in lines.values()
        )
        status, maps = sofa.maps(int(sofa_event["id"]), home_is_t1, need_players)
        record.update(
            {
                "sofascore_event_id": sofa_event["id"],
                "sofascore_match": (
                    f"{sofa_event['homeTeam']['name']} - "
                    f"{sofa_event['awayTeam']['name']}"
                ),
                "sofascore_tournament": (sofa_event.get("tournament") or {}).get(
                    "name"
                ),
                "home_is_team1": home_is_t1,
                "status": status,
                "maps": len(maps),
                "maps_with_players": sum(1 for m in maps if m.players),
            }
        )
        if status != "finished" or not maps:
            record["state"] = "NOT_FINISHED" if status != "finished" else "NO_MAP_DATA"
            done[event_id] = record
            counts[record["state"].lower()] += 1
            continue
        graded = []
        for key, d in lines.items():
            partner_side = {"OVER": "UNDER", "UNDER": "OVER", "T1": "T2", "T2": "T1"}[
                d["side"]
            ]
            partner = lines.get((key[0], key[1], key[2], key[3], partner_side))
            if partner is None:
                continue
            line = Cs2Line(**d)
            actual = actual_value(line, maps, ev["team1"], ev["team2"])
            if actual is None:
                counts["line_ungradeable"] += 1
                continue
            outcome = grade(line, actual)
            if outcome == "VOID":
                continue
            graded.append(
                {
                    **d,
                    "partner_odds": partner["odds"],
                    "fair_p": fair_probability(line, partner["odds"]),
                    "actual": actual,
                    "outcome": outcome,
                }
            )
        record.update({"state": "SETTLED", "graded": graded})
        done[event_id] = record
        counts["settled"] += 1
        counts["graded_sides"] += len(graded)
    settled_path.write_text(
        json.dumps({"date": date, "events": done}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "stage": "CS2_SETTLE",
                "date": date,
                "events_snapshotted": len(events),
                **counts,
                "output_path": str(settled_path),
            }
        )
    )
    return 0


# --- report -----------------------------------------------------------------


def report(date_from: str, date_to: str) -> int:
    d, end = (
        datetime.strptime(date_from, "%Y-%m-%d"),
        datetime.strptime(date_to, "%Y-%m-%d"),
    )
    states: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    while d <= end:
        path = day_dir(d.strftime("%Y-%m-%d")) / "settled.json"
        if path.exists():
            for ev in json.loads(path.read_text(encoding="utf-8"))["events"].values():
                states[ev["state"]] += 1
                rows.extend(ev.get("graded") or [])
        d += timedelta(days=1)
    print(f"CS2 shadow {date_from}..{date_to}")
    print("events:", dict(states))
    if not rows:
        print("no graded lines yet")
        return 0
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[r["family"]].append(r)
    by["ALL"] = rows
    print(
        f"{'family':22} {'sides':>6} {'fair p':>7} {'hit':>6} {'gap pp':>7} "
        f"{'Brier':>6} {'ROI':>7} {'margin':>7}"
    )
    for fam, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        rs = [r for r in rs if r["fair_p"] is not None]
        if not rs:
            continue
        n = len(rs)
        wins = [1.0 if r["outcome"] == "WIN" else 0.0 for r in rs]
        fair = sum(r["fair_p"] for r in rs) / n
        hit = sum(wins) / n
        brier = sum((r["fair_p"] - w) ** 2 for r, w in zip(rs, wins)) / n
        roi = sum((r["odds"] - 1.0) if w else -1.0 for r, w in zip(rs, wins)) / n
        margins = sorted(1 / r["odds"] + 1 / r["partner_odds"] - 1 for r in rs)
        print(
            f"{fam:22} {n:6d} {fair:7.3f} {hit:6.3f} "
            f"{100 * (hit - fair):+7.1f} {brier:6.3f} "
            f"{100 * roi:+6.1f}% {100 * margins[n // 2]:6.1f}%"
        )
    print("\nROI is flat, one unit on every graded side. Both sides of a line are in,")
    print("so ALL is roughly minus the margin by construction; the families and the")
    print("gap between fair p and hit are what the measurement is for.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    for name in ("snapshot", "settle"):
        p = sub.add_parser(name)
        p.add_argument("--date", default=today)
    p = sub.add_parser("report")
    p.add_argument("--from", dest="date_from", default=today)
    p.add_argument("--to", dest="date_to", default=today)
    args = ap.parse_args()
    if args.cmd == "snapshot":
        return snapshot(args.date)
    if args.cmd == "settle":
        return settle(args.date)
    return report(args.date_from, args.date_to)


if __name__ == "__main__":
    raise SystemExit(main())
