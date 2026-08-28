#!/usr/bin/env python
"""Delete cached provider data that predates the checks which would have caught it.

A fix to a client does not fix what that client already wrote to disk. On
2026-08-28 the tennis providers were repaired; the cache underneath them still
held what the broken versions had cached, and a "from scratch" run would have
read it straight back:

  * ``tennis-abstract/player/*.json`` written before the identity check carry no
    ``proved_name``, so there is no record of whose page they came from. That
    matters because tennisabstract answers 200 for a player it does not have on
    the route asked and serves Benoit Paire's page instead. Measured on this
    repo's own cache: **72 different players -- all women -- shared one
    identical 1073-row table** whose most frequent opponents were Pablo Carreno
    Busta, Stan Wawrinka, Richard Gasquet and Gilles Simon. That is Paire's ATP
    career, filed under 72 WTA names.
  * ``espn/tennis/*/athlete_fixtures/`` (the v1 key) holds rows with two display
    names and no participant ids, so nothing can say which side the player was
    on. The consumer now refuses those rather than guessing, which turns a
    silent wrong opponent into a silent absence -- better, but still nothing.
  * ``sackmann/`` is cached output from an upstream that no longer exists.

The client-side guards already refuse all three: an entry without
``proved_name`` is re-fetched, and the ESPN key was versioned. This script is
about the disk rather than the code -- so that "rerun today from scratch" means
it, so nothing else that walks the cache can find them, and so the evidence is
reported out loud once before it is destroyed.

Dry run by default. Nothing is deleted without ``--apply``.

    .venv/bin/python scripts/simple/purge_unproven_cache.py
    .venv/bin/python scripts/simple/purge_unproven_cache.py --apply

Exit codes: 0 nothing to purge (or purged), 1 unproven entries found in a dry
run, 2 the run could not be completed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO_ROOT / "betting" / "data" / "stats_cache"


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _scan_tennis_abstract() -> tuple[list[Path], list[str]]:
    """Player pages with no record of whose page they were."""
    root = CACHE_ROOT / "tennis-abstract" / "player"
    if not root.is_dir():
        return [], []

    unproven: list[Path] = []
    tables: dict[str, list[str]] = {}
    for path in sorted(root.glob("*.json")):
        data = _load(path)
        if data is None:
            unproven.append(path)
            continue
        if data.get("proved_name"):
            continue  # written by the current client, identity on the record
        unproven.append(path)
        matches = data.get("matches") or []
        if not matches:
            continue
        digest = hashlib.sha256(
            json.dumps(matches, sort_keys=True, default=str).encode()
        ).hexdigest()
        tables.setdefault(digest, []).append(path.stem)

    # The shared-table report is the whole point of doing this loudly. One
    # match table under many names is not a cache that went stale, it is a
    # cache that was never about those players.
    notes: list[str] = []
    for digest, names in sorted(tables.items(), key=lambda kv: -len(kv[1])):
        if len(names) < 2:
            continue
        sample = _load(root / f"{names[0]}.json") or {}
        rows = sample.get("matches") or []
        opponents = Counter(
            row.get("opp") for row in rows if isinstance(row, dict) and row.get("opp")
        )
        top = ", ".join(name for name, _ in opponents.most_common(4))
        notes.append(
            f"{len(names)} players share one identical {len(rows)}-row table "
            f"({digest[:12]}); its most frequent opponents are {top}. "
            f"First few: {', '.join(sorted(names)[:6])}"
        )
    return unproven, notes


def _scan_espn_v1() -> list[Path]:
    """Athlete history rows from before participant ids were emitted."""
    root = CACHE_ROOT / "espn" / "tennis"
    if not root.is_dir():
        return []
    # Only the unversioned directory: athlete_fixtures_v2 is the current shape.
    return sorted(
        path for path in root.glob("*/athlete_fixtures") if path.is_dir()
    )


def _scan_sackmann() -> list[Path]:
    root = CACHE_ROOT / "sackmann"
    return [root] if root.is_dir() else []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually delete (default: report only)")
    args = parser.parse_args()

    if not CACHE_ROOT.is_dir():
        print(f"no cache at {CACHE_ROOT.relative_to(REPO_ROOT)}: nothing to do")
        return 0

    ta_files, ta_notes = _scan_tennis_abstract()
    espn_dirs = _scan_espn_v1()
    sackmann_dirs = _scan_sackmann()

    print("Cache entries written before the checks that would have caught them:\n")
    print(f"  tennis-abstract players without an identity proof : {len(ta_files)}")
    for note in ta_notes:
        print(f"      ! {note}")
    espn_count = sum(len(list(d.glob('*.json'))) for d in espn_dirs)
    print(f"  espn tennis athlete_fixtures (v1, no participant ids): "
          f"{espn_count} in {len(espn_dirs)} directories")
    sack_count = sum(1 for d in sackmann_dirs for _ in d.rglob("*") if _.is_file())
    print(f"  sackmann (upstream repositories no longer exist)   : {sack_count}")

    total = len(ta_files) + espn_count + sack_count
    if not total:
        print("\nnothing to purge -- the cache is all post-fix.")
        return 0

    if not args.apply:
        print(
            f"\n{total} entries would be deleted. Nothing was touched: this is a "
            f"dry run.\nRe-run with --apply to purge before a from-scratch day."
        )
        return 1

    removed = 0
    for path in ta_files:
        path.unlink(missing_ok=True)
        removed += 1
    for directory in (*espn_dirs, *sackmann_dirs):
        removed += sum(1 for _ in directory.rglob("*") if _.is_file())
        shutil.rmtree(directory, ignore_errors=True)

    print(
        f"\npurged {removed} entries. The next run re-fetches them, and every "
        f"tennis-abstract page it writes will carry the name the site gave for "
        f"the player."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
