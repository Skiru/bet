#!/usr/bin/env python3
"""Remove a wrong verified team alias from the entity cache (sofa_entity).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/purge_entity_alias.py --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/purge_entity_alias.py
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/purge_entity_alias.py --list-suspects

A verified alias is read before any search, and by SHADOW_SETTLE's
MUTUAL_LISTING as one side's team. Until 2026-10-05 a shadow-sport match
confirmed by the opponent's name alone cached the SEARCHED name as verified:
basketball "u. de santiago" -> 233778 (Universidad Catolica) on 10-04, and
U. De Santiago - Colo Colo was graded as Universidad Catolica - Colo Colo
(17207292, 10-03). Plan 2026-10-05, B2.

Default: exactly that entry (basketball, "u. de santiago", 233778). Another
one with --sport / --query-key / --sofascore-id; the id must match, so an
entry that has since been re-verified to another team is never removed.
--list-suspects prints (read-only) every verified hockey / basketball /
volleyball alias whose name does not pass the matcher's own score against
the team it points to - most are true aliases (an exonym, a sponsor name);
a person decides, one entry at a time.

Offline (the database only). Exit 0 = done or nothing to do, 2 = no database.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, part_score  # noqa: E402

DEFAULT_ENTRY = ("basketball", "u. de santiago", 233778)
SHADOW_SLUGS = ("ice-hockey", "basketball", "volleyball")


def suspects(conn: sqlite3.Connection) -> list[tuple[str, str, int, str, float]]:
    rows = conn.execute(
        "SELECT sport, query_key, sofascore_id, sofascore_name FROM sofa_entity"
        " WHERE status = 'verified' AND sport IN (?, ?, ?)",
        SHADOW_SLUGS,
    ).fetchall()
    out = []
    for sport, key, sid, name in rows:
        score = part_score(str(key), normalize_name(str(name)))
        if score <= NAME_MATCH_THRESHOLD:
            out.append((str(sport), str(key), int(sid), str(name), round(score, 1)))
    return sorted(out, key=lambda r: r[4])


def purge(
    conn: sqlite3.Connection, sport: str, key: str, sid: int, dry_run: bool
) -> list[tuple[str, str, int, str, str]]:
    """The matching rows - deleted unless `dry_run`."""
    rows = conn.execute(
        "SELECT sport, query_key, sofascore_id, sofascore_name, status"
        " FROM sofa_entity WHERE sport = ? AND query_key = ? AND sofascore_id = ?",
        (sport, key, sid),
    ).fetchall()
    if rows and not dry_run:
        conn.execute(
            "DELETE FROM sofa_entity"
            " WHERE sport = ? AND query_key = ? AND sofascore_id = ?",
            (sport, key, sid),
        )
        conn.commit()
    return [(str(a), str(b), int(c), str(d), str(e)) for a, b, c, d, e in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sport", default=DEFAULT_ENTRY[0])
    ap.add_argument("--query-key", default=DEFAULT_ENTRY[1])
    ap.add_argument("--sofascore-id", type=int, default=DEFAULT_ENTRY[2])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-suspects", action="store_true")
    ap.add_argument("--db", help="default: the configured sofa.db")
    args = ap.parse_args(argv)
    db = args.db or SofaConfig.from_env().db_path
    if not Path(db).exists():
        print(f"FAILED: no database at {db}", file=sys.stderr)
        return 2
    if args.list_suspects:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            found = suspects(conn)
        finally:
            conn.close()
        print(f"{len(found)} verified shadow-sport aliases below the name threshold")
        for row in found:
            print(" | ".join(str(x) for x in row))
        return 0
    conn = (
        sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        if args.dry_run
        else sqlite3.connect(db, timeout=60)
    )
    try:
        rows = purge(conn, args.sport, args.query_key, args.sofascore_id, args.dry_run)
    finally:
        conn.close()
    verb = "would remove" if args.dry_run else "removed"
    if not rows:
        print(
            f"nothing to remove: no {args.sport!r} alias {args.query_key!r} -> "
            f"{args.sofascore_id}"
        )
    for row in rows:
        print(f"{verb}: {' | '.join(str(x) for x in row)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
