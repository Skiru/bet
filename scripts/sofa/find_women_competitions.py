#!/usr/bin/env python3
"""Write config/sofa_women_competitions.json from the cached listings.

A football competition is women's when at least 80% of its distinct cached
events are women's by resolve.sofascore_gender (the teams' own gender field
first, the competition name as fallback). SHEET reads the list for the
women's global prior: the global pool is ~90% men's football, and a women's
league with no baseline of its own was shrunk toward it at weight 0.71 -
goals_total 3.17 against the women's 3.57, cards points 4.45 against 2.59,
fouls 24.9 against 17.8 (config/sofa_league_baselines.json, 2026-09-30).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_women_competitions.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bet.sofa.atomic import write_atomic
from bet.sofa.listing_index import listed_events_by_id
from bet.sofa.resolve import sofascore_gender

WOMEN_SHARE = 0.8


def classify(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    genders: dict[int, Counter[str]] = defaultdict(Counter)
    names: dict[int, str] = {}
    seen: set[int] = set()
    for event in events:
        eid = event.get("id")
        if not isinstance(eid, int) or eid in seen:
            continue
        seen.add(eid)
        unique = (event.get("tournament") or {}).get("uniqueTournament") or {}
        comp = unique.get("id")
        if isinstance(comp, int):
            genders[comp][sofascore_gender(event)] += 1
            names[comp] = str(unique.get("name") or "")
    women: list[dict[str, Any]] = []
    mixed: list[dict[str, Any]] = []
    for comp, c in sorted(genders.items()):
        if not c["W"]:
            continue
        entry = {"competition_id": comp, "name": names[comp],
                 "women_events": c["W"], "men_events": c["M"]}
        share = c["W"] / (c["W"] + c["M"])
        (women if share >= WOMEN_SHARE else mixed).append(entry)
    return {"women": women, "mixed": mixed}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--out", default="config/sofa_women_competitions.json")
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    try:
        # The pages and the listed-event index (listing_index.py), one copy
        # per event id (classify counts each once): the first page copy, or
        # the index's when it is newer.
        events: list[dict[str, Any]] = list(listed_events_by_id(
            con, lambda e: e, kinds=("last",),
            like='%"slug": "football"%', sport="football").values())
    finally:
        con.close()
    classes = classify(events)
    doc: dict[str, Any] = {
        "_doc": [
            "Football competitions whose cached events are women's "
            "(resolve.sofascore_gender), from sofa_entity_events kind='last'.",
            f"Listed when at least {WOMEN_SHARE:.0%} of its distinct cached "
            "events are women's; `mixed` had some women's events, is for "
            "review, and is NOT read.",
            "Read by scripts/sofa/run_sheet.py for PRIOR_GLOBAL_WOMEN. "
            "Regenerate with scripts/sofa/find_women_competitions.py.",
        ],
        **classes,
    }
    write_atomic(Path(args.out), json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"women": len(classes["women"]),
                      "mixed": len(classes["mixed"]),
                      "output_path": args.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
