#!/usr/bin/env python3
"""Teach the entity map from every day on disk (identity plan K1, once).

SPORT_IDENTITY learns from its own records from K1 on; the days before it
(runs/sofa/*/sport_fixtures.json, 2026-10-05 onwards) are read here by the
same rule (bet.sofa.entity_map.learn_records: a side its own name confirmed
is learned, an opponent-rule side is a NEEDS_ALIAS candidate, a held name
with another id a conflict - never an overwrite) plus the tournament map,
which for football / tennis comes from RESOLVE's days (01_board.json
tournament_id -> 02_fixtures.json competition_id, keyed `id:<superbet id>`).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_entity_map.py \\
        [--dry-run] [--db-path data/sofa.db] [--runs-dir runs/sofa]

--dry-run does every write inside one transaction and rolls it back: the
counts are exactly what --apply would do. --apply first copies sofa_entity
to data/backup_entity_map_<UTC>/sofa_entity.json. No network. Exit 0, or 2
when the database cannot be written.
"""

from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import entity_map as em  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.db import get_connection, migrate  # noqa: E402


def _days(runs_dir: str, name: str) -> list[Path]:
    return [Path(p) for p in sorted(glob.glob(str(Path(runs_dir) / "*" / name)))]


def sport_records(runs_dir: str) -> list[dict[str, Any]]:
    """Every SPORT_IDENTITY record on disk, oldest kickoff first (the map's
    first_seen is then the first day that showed it)."""
    out: list[dict[str, Any]] = []
    for path in _days(runs_dir, "sport_fixtures.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        out += list(doc.get("fixtures") or [])
    return sorted(out, key=lambda r: (str(r.get("kickoff_utc")),
                                      str(r.get("superbet_event_id"))))


def resolve_tournaments(runs_dir: str) -> list[tuple[str, int, int, str | None, int]]:
    """(sport, superbet tournament id, competition id, competition name,
    Sofascore event id) of every football / tennis fixture RESOLVE bridged."""
    board: dict[str, dict[str, Any]] = {}
    for path in _days(runs_dir, "01_board.json"):
        try:
            for e in json.loads(path.read_text(encoding="utf-8")):
                board[str(e["superbet_event_id"])] = e
        except (ValueError, TypeError, KeyError):
            continue
    out = []
    seen: set[tuple[str, int]] = set()
    for path in _days(runs_dir, "02_fixtures.json"):
        try:
            fixtures = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for f in fixtures if isinstance(fixtures, list) else []:
            comp, eid = f.get("competition_id"), f.get("sofascore_event_id")
            if not isinstance(comp, int) or not isinstance(eid, int):
                continue
            for sb in f.get("superbet_event_ids") or []:
                b = board.get(str(sb))
                tid = (b or {}).get("tournament_id")
                if not isinstance(tid, int) or (str(f["sport"]), eid) in seen:
                    continue
                seen.add((str(f["sport"]), eid))
                out.append((str(f["sport"]), tid, comp, f.get("competition_name"), eid))
    return out


def backup(conn: sqlite3.Connection, root: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = root / f"backup_entity_map_{stamp}" / "sofa_entity.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sofa_entity)")]
    rows = [dict(zip(cols, tuple(r), strict=True))
            for r in conn.execute("SELECT * FROM sofa_entity")]
    out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return out


def run(conn: sqlite3.Connection, runs_dir: str, at: str) -> dict[str, Any]:
    by_sport: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in sport_records(runs_dir):
        by_sport[str(r.get("sport"))].append(r)
    report: dict[str, Any] = {}
    for sport, recs in sorted(by_sport.items()):
        report[sport] = em.learn_records(conn, recs, at)
    rows = resolve_tournaments(runs_dir)
    for sport in sorted({r[0] for r in rows}):
        report.setdefault(sport, {})["tournaments"] = em.learn_resolve_tournaments(
            conn, [r for r in rows if r[0] == sport], at)
    report["conflicts"] = [
        dict(zip(("sport", "query_key", "held_id", "held_name", "held_source",
                  "offered_id", "offered_name", "evidence_event_id"), tuple(r),
                 strict=True))
        for r in conn.execute(
            "SELECT sport, query_key, held_id, held_name, held_source, offered_id,"
            " offered_name, evidence_event_id FROM sofa_entity_conflict"
            " WHERE status = 'OPEN' ORDER BY sport, query_key")]
    report["candidates_open"] = conn.execute(
        "SELECT COUNT(*) FROM sofa_entity_candidate WHERE status = 'OPEN'"
    ).fetchone()[0]
    report["tournament_rows"] = dict(conn.execute(
        "SELECT sport, COUNT(*) FROM sofa_tournament_map GROUP BY sport").fetchall())
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--runs-dir", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    db_path = args.db_path or config.db_path
    runs_dir = args.runs_dir or config.runs_dir
    at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        migrate(db_path)
        with get_connection(db_path) as conn:
            if not args.dry_run:
                print(f"backup: {backup(conn, Path(db_path).parent)}")
            report = run(conn, runs_dir, at)
            if args.dry_run:
                conn.rollback()
            else:
                conn.commit()
    except sqlite3.Error as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"dry_run": args.dry_run, **report}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
