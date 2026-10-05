#!/usr/bin/env python3
"""Was every settled match the match it claims to be? Offline, read-only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py \\
        --from <d> --to <d> [--sport all]

Plan 2026-10-05, part 4D (D-a). Run in /sofa-day after D-1 is settled and in
/sofa-settle. Reads the measured sports' settled.json + snapshots.jsonl
(hockey, basketball, volleyball, CS2) and, for football and tennis, the
database's sofa_settled_row with the day's 02_fixtures.json and the cached
/event payloads. Writes nothing, asks nothing.

Checks, each a finding:

    ID_USED_TWICE     one Sofascore id counted (SETTLED) for two Superbet
                      events or in two dates' files; football/tennis: one id
                      graded under two run dates
    MOVED_GRADED      |Sofascore start - Superbet's time| > 48 h, and graded
                      (Superbet voids it - Regulamin 5.E.1.a; Everton 09-24)
    NAME_BELOW        a counted record whose board name scores <= 82 against
                      its Sofascore side, on either side, matched by neither
                      a shared word nor MUTUAL_LISTING / TOURNAMENT (which
                      are listed apart, as accepted below the threshold)
    ORIENTATION_IDS   football/tennis: the fixture's team ids are not the
                      cached /event's
    ID_CHANGED        a pinned id that a later search contradicted
    IDENTITY_STATE    a record the identity pass marked (DUPLICATE_*,
                      WITHDRAWN, MOVED_TO, AMBIGUOUS_START) - listed so a
                      person sees what was excluded
    IDENTITY_PENDING  a record the identity pass WOULD mark and that is
                      still counted: the day was settled before 2026-10-05
                      (fix: settle_shadow.py / settle_cs2.py --identity-only)

Exit 0 = no finding, 1 = a finding (all listed), 2 = a crash.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import settle_identity as si  # noqa: E402
from bet.sofa import shadow  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import cs2_day_dir  # noqa: E402
from bet.sofa.resolve import NAME_MATCH_THRESHOLD  # noqa: E402

MEASURED = ("hockey", "basketball", "volleyball", "cs2")
FOOTBALL_TENNIS = ("football", "tennis")
VOID_AFTER_H = 48.0
# Matches confirmed below the name threshold by design (settle_shadow).
BELOW_BY_DESIGN = frozenset({"SHARED_WORD", "MUTUAL_LISTING", "TOURNAMENT"})

Finding = dict[str, Any]


def days(start: str, end: str) -> list[str]:
    a = datetime.strptime(start, "%Y-%m-%d")
    b = datetime.strptime(end, "%Y-%m-%d")
    return [
        (a + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((b - a).days + 1)
    ]


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)


def day_dir_of(runs_dir: str, sport: str) -> Any:
    if sport == "cs2":
        return lambda d: cs2_day_dir(runs_dir, d)
    return lambda d: shadow.shadow_day_dir(runs_dir, sport, d)  # type: ignore[arg-type]


def shift_h(rec: dict[str, Any]) -> float | None:
    gap = rec.get("start_gap_h")
    if isinstance(gap, int | float):
        return float(gap)
    start, kickoff = rec.get("sofascore_start_utc"), rec.get("kickoff_utc")
    if start and kickoff:
        return (_utc(start) - _utc(kickoff)).total_seconds() / 3600
    return None


def audit_measured(runs_dir: str, sport: str, dates: list[str]) -> list[Finding]:
    kind: si.Kind = "cs2" if sport == "cs2" else "shadow"
    day_dir = day_dir_of(runs_dir, sport)
    files = {d: si.load_events(day_dir(d) / shadow.SETTLED_FILE) for d in dates}
    out: list[Finding] = []

    def finding(
        check: str, date: str, eid: str, rec: dict[str, Any], **extra: Any
    ) -> None:
        out.append(
            {
                "sport": sport,
                "check": check,
                "date": date,
                "superbet_event_id": eid,
                "match": rec.get("match_name"),
                "sofascore_event_id": rec.get("sofascore_event_id"),
                "sofascore_match": rec.get("sofascore_match"),
                "state": rec.get("state"),
                **extra,
            }
        )

    by_id: dict[int, list[tuple[str, str]]] = {}
    for date, events in files.items():
        for eid, rec in events.items():
            state = rec.get("state")
            if shadow.is_excluded(state) and state != "ID_CHANGED":
                finding(
                    "IDENTITY_STATE", date, eid, rec, reason=rec.get("identity_reason")
                )
                continue
            if state == "ID_CHANGED" or rec.get("id_changed_to") is not None:
                finding(
                    "ID_CHANGED",
                    date,
                    eid,
                    rec,
                    searched=rec.get("searched_sofascore_event_id")
                    or rec.get("id_changed_to"),
                )
            if state != "SETTLED":
                continue
            sid = rec.get("sofascore_event_id")
            if isinstance(sid, int):
                by_id.setdefault(sid, []).append((date, eid))
            gap = shift_h(rec)
            if gap is not None and abs(gap) > VOID_AFTER_H:
                finding("MOVED_GRADED", date, eid, rec, shift_h=round(gap, 1))
            scores = si.record_name_scores(kind, rec)
            if scores is not None and min(scores.values()) <= NAME_MATCH_THRESHOLD:
                method = rec.get("match_method") or rec.get("match_rule")
                check = (
                    "NAME_BELOW_BY_DESIGN"
                    if method in BELOW_BY_DESIGN
                    else "NAME_BELOW"
                )
                finding(check, date, eid, rec, name_scores=scores, match_method=method)
    for sid, keys in by_id.items():
        if len(keys) > 1:
            for date, eid in keys:
                finding(
                    "ID_USED_TWICE",
                    date,
                    eid,
                    files[date][eid],
                    with_=[f"{d}:{e}" for d, e in keys if (d, e) != (date, eid)],
                )
    # What the identity pass would still change (a day settled before it).
    for date in dates:
        if not files[date]:
            continue
        window = si.window(date)
        snaps = {
            d: si.snapshot_index(day_dir(d) / shadow.SNAPSHOTS_FILE) for d in window
        }
        neighbours = {
            d: files.get(d) or si.load_events(day_dir(d) / shadow.SETTLED_FILE)
            for d in window
        }
        for (d, eid), change in si.plan_identity(kind, neighbours, snaps).items():
            if d != date:
                continue
            rec = files[date][eid]
            if rec.get("state") == "SETTLED" and change.get("state") != "SETTLED":
                finding(
                    "IDENTITY_PENDING",
                    date,
                    eid,
                    rec,
                    would_be=change.get("state"),
                    reason=change.get("identity_reason"),
                )
    return out


def audit_football_tennis(
    runs_dir: str, db_path: str, sport: str, dates: list[str]
) -> list[Finding]:
    out: list[Finding] = []
    if not Path(db_path).exists():
        return [{"sport": sport, "check": "NO_DATABASE", "db": db_path}]
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT run_date, sofascore_event_id, COUNT(*) FROM sofa_settled_row"
            " WHERE sport = ? AND run_date BETWEEN ? AND ?"
            " GROUP BY run_date, sofascore_event_id",
            (sport, dates[0], dates[-1]),
        ).fetchall()
        by_id: dict[int, list[tuple[str, int]]] = {}
        for run_date, sid, n in rows:
            by_id.setdefault(int(sid), []).append((str(run_date), int(n)))
        for sid, seen in by_id.items():
            if len(seen) > 1:
                out.append(
                    {
                        "sport": sport,
                        "check": "ID_USED_TWICE",
                        "sofascore_event_id": sid,
                        "run_dates": seen,
                    }
                )
        for date in dates:
            path = Path(runs_dir) / date / "02_fixtures.json"
            if not path.exists():
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                out.append({"sport": sport, "check": "UNREADABLE", "path": str(path)})
                continue
            fixtures = doc if isinstance(doc, list) else doc.get("fixtures", [])
            graded = {
                sid for sid, seen in by_id.items() if any(d == date for d, _ in seen)
            }
            for fx in fixtures:
                sid = fx.get("sofascore_event_id")
                if fx.get("sport") != sport or sid not in graded:
                    continue
                row = conn.execute(
                    "SELECT detail_json FROM sofa_event_detail"
                    " WHERE sofascore_event_id = ?",
                    (sid,),
                ).fetchone()
                if not row:
                    continue
                detail = (json.loads(row[0]) or {}).get("event") or {}
                start = detail.get("startTimestamp")
                clocks = [
                    _utc(c)
                    for c in (
                        fx.get("kickoff_utc"),
                        fx.get("superbet_kickoff_utc"),
                        fx.get("superbet_kickoff_seen_utc"),
                    )
                    if c
                ]
                if isinstance(start, int) and clocks:
                    gap = (
                        datetime.fromtimestamp(start, UTC) - min(clocks)
                    ).total_seconds()
                    if abs(gap) / 3600 > VOID_AFTER_H:
                        out.append(
                            {
                                "sport": sport,
                                "check": "MOVED_GRADED",
                                "date": date,
                                "sofascore_event_id": sid,
                                "match": (
                                    f"{fx.get('home_name')} - {fx.get('away_name')}"
                                ),
                                "shift_h": round(gap / 3600, 1),
                            }
                        )
                want = (fx.get("home_entity_id"), fx.get("away_entity_id"))
                got = (
                    (detail.get("homeTeam") or {}).get("id"),
                    (detail.get("awayTeam") or {}).get("id"),
                )
                if None not in want and None not in got and want != got:
                    out.append(
                        {
                            "sport": sport,
                            "check": "ORIENTATION_IDS",
                            "date": date,
                            "sofascore_event_id": sid,
                            "fixture_ids": list(want),
                            "event_ids": list(got),
                        }
                    )
    finally:
        conn.close()
    return out


def run(
    runs_dir: str, db_path: str, start: str, end: str, sports: tuple[str, ...]
) -> list[Finding]:
    dates = days(start, end)
    out: list[Finding] = []
    for sport in sports:
        if sport in MEASURED:
            out += audit_measured(runs_dir, sport, dates)
        else:
            out += audit_football_tennis(runs_dir, db_path, sport, dates)
    return out


def is_failure(f: Finding) -> bool:
    """NAME_BELOW_BY_DESIGN is shown, never failed: SHARED_WORD,
    MUTUAL_LISTING and TOURNAMENT are the accepted ways below the threshold."""
    return str(f["check"]) != "NAME_BELOW_BY_DESIGN"


def _main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument(
        "--sport", choices=[*MEASURED, *FOOTBALL_TENNIS, "all"], default="all"
    )
    args = ap.parse_args()
    config = SofaConfig.from_env()
    sports = (*MEASURED, *FOOTBALL_TENNIS) if args.sport == "all" else (args.sport,)
    findings = run(config.runs_dir, config.db_path, args.start, args.end, sports)
    print(f"# Settle identity {args.start}..{args.end} ({', '.join(sports)})\n")
    counts: dict[tuple[str, str], int] = {}
    for f in findings:
        key = (str(f["sport"]), str(f["check"]))
        counts[key] = counts.get(key, 0) + 1
    print("| sport | check | n |\n|---|---|---|")
    for (sport, check), n in sorted(counts.items()):
        print(f"| {sport} | {check} | {n} |")
    print()
    for f in findings:
        print(json.dumps(f, ensure_ascii=False, default=str))
    failing = [f for f in findings if is_failure(f)]
    print(f"\n{len(failing)} finding(s); {len(findings) - len(failing)} shown only")
    return 1 if failing else 0


def main() -> int:
    """An unexpected crash is 2, never read as a finding (1)."""
    try:
        return _main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
