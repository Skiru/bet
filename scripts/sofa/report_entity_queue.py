#!/usr/bin/env python3
"""The NEEDS_ALIAS queue of the entity map, for a person's one-time decision
(identity plan K4).

Writes runs/sofa/<date>/entity_queue.md (Polish, operator-facing): every
OPEN conflict (a name the map holds with one id, offered another) and every
OPEN candidate (a name only the opponent rule or DAY_ANCHOR tied to an id),
most seen first, each with a ready JSON entry for config/sofa_entity_aliases.json.
Nothing is decided here and nothing is written to the database; the
decisions are applied by SPORT_IDENTITY's next run (entity_map.sync_manual,
from epochs.ENTITY_MAP_FROM_UTC). No network.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_entity_queue.py \\
        --date 2026-10-14 [--limit 200]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import entity_map as em  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402

SPORT_OF_SLUG = {v: k for k, v in em.ENTITY_SPORT.items()}


def entry(
    sport: str, name: str, sid: int, sname: str | None, date: str, evidence: str
) -> str:
    return json.dumps(
        {
            "sport": SPORT_OF_SLUG.get(sport, sport),
            "superbet_name": name,
            "sofascore_id": sid,
            "sofascore_name": sname,
            "decided_by": "operator",
            "decided_at": date,
            "evidence": evidence,
        },
        ensure_ascii=False,
    )


def render(queue: dict[str, list[dict[str, Any]]], date: str, limit: int) -> str:
    conflicts, candidates = queue["conflicts"], queue["candidates"]
    lines = [
        f"# Kolejka mapy encji — {date}",
        "",
        "Nazwy Superbetu, których automat nie rozstrzyga (plan tożsamości K4). "
        "Decyzja jest jednorazowa: wpis do `config/sofa_entity_aliases.json` "
        "(`aliases` — to jest ta drużyna; `rejected` — to nie ta) i następny "
        "przebieg SPORT_IDENTITY go zastosuje (od 2026-10-15 00:00Z). "
        "Fuzzy nic tu nie wpisuje.",
        "",
        f"Otwarte: {len(conflicts)} konfliktów, {len(candidates)} kandydatów.",
        "",
        "## Konflikty (nazwa trzymana z innym id)",
        "",
    ]
    if not conflicts:
        lines.append("Brak.")
    for c in conflicts[:limit]:
        take = entry(
            c["sport"],
            c["query_key"],
            c["offered_id"],
            c["offered_name"],
            date,
            f"event {c['evidence_event_id']}",
        )
        held = c["held_source"] or "mapa sprzed K1"
        lines += [
            f"- **{c['sport']} / {c['query_key']}**: trzymane {c['held_id']} "
            f"„{c['held_name']}” ({held}), oferowane {c['offered_id']} "
            f"„{c['offered_name']}” (mecz {c['evidence_event_id']}, "
            f"widziane {c['seen']}×)",
            f"  - przyjąć oferowane: `{take}`",
        ]
    lines += [
        "",
        "## Kandydaci (tylko reguła przeciwnika albo DAY_ANCHOR)",
        "",
        "| sport | nazwa Superbetu | kandydat Sofascore | powód | widziane | "
        "mecz | wpis |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in candidates[:limit]:
        take = entry(
            c["sport"],
            c["superbet_name"],
            c["candidate_id"],
            c["candidate_name"],
            date,
            f"event {c['evidence_event_id']}, {c['reason']}",
        )
        lines.append(
            f"| {c['sport']} | {c['superbet_name']} | {c['candidate_id']} "
            f"„{c['candidate_name']}” | {c['reason']} | {c['seen']} | "
            f"{c['evidence_event_id']} | `{take}` |"
        )
    if len(candidates) > limit:
        lines.append(f"\n… i {len(candidates) - limit} więcej (`--limit`).")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--db-path", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    conn = sqlite3.connect(f"file:{args.db_path or config.db_path}?mode=ro", uri=True)
    try:
        queue = em.open_queue(conn)
    finally:
        conn.close()
    out = Path(config.runs_dir) / args.date / "entity_queue.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(out, render(queue, args.date, args.limit))
    print(
        json.dumps(
            {
                "output_path": str(out),
                "conflicts": len(queue["conflicts"]),
                "candidates": len(queue["candidates"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
