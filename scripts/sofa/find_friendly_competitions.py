#!/usr/bin/env python3
"""Candidates for config/sofa_friendly_competitions.json, from the cache.

The friendly list is keyed on the uniqueTournament id and every entry is
reviewed (the config's `_doc`). A pre-season tournament slipped past it on
2026-10-04 ("Torneio de Verao Povoa de Varzim", 36573, in Chaves' sample as a
competitive match) because nothing ever proposed it: the old review read only
competitions NAMED "friendly". This script proposes by SHAPE as well, and
proposes; a person decides.

A football club competition is a candidate when it is not already in the
config (`excluded` or `allowed`) and either

  * its name says so (friendly / pre-season / exhibition / testimonial /
    legends / all-star / summer series, any language Sofascore uses), or
  * it is shaped like an invitational tournament in every cached season:
    every season played inside --max-span-days, no club with more than
    --max-team-matches matches in it, clubs (not national teams), and the
    clubs' own leagues (each club's most frequent other competition)
    are at least two different ones - a domestic cup final is one league's
    clubs, a pre-season tournament mixes leagues.

Writes the candidates with one verbatim example event each (the evidence
format of docs/sofa/evidence/friendly_competitions_*.json). Read-only on the
DB.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_friendly_competitions.py \\
        --out docs/sofa/evidence/friendly_candidates_<date>.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.comparability import FRIENDLIES_PATH, fold

NAME_MARKERS = re.compile(
    r"\b(friendl(y|ies)|amistos[oa]s?|amichevol[ei]|freundschaft|pre-?season|"
    r"pretemporada|pre-?temporada|exhibition|testimonial|legends|all-?star|"
    r"summer (series|cup|tournament)|torneio de verao|torneo de verano|"
    r"trofeo de verano|copa de verano|memorial)\b"
)


def reviewed_ids(path: Path = FRIENDLIES_PATH) -> set[int]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: set[int] = set()
    for key in ("excluded", "allowed"):
        for entry in raw.get(key) or []:
            if isinstance(entry, dict) and isinstance(entry.get("competition_id"), int):
                out.add(entry["competition_id"])
    return out


def is_named_friendly(name: str) -> bool:
    return bool(NAME_MARKERS.search(fold(name)))


def shaped_like_invitational(
    seasons: dict[Any, list[tuple[int, int, int]]],
    home_league: dict[int, int | None],
    max_span_days: int,
    max_team_matches: int,
) -> bool:
    """``seasons``: season -> [(ts, home_id, away_id)]."""
    leagues: set[int] = set()
    for matches in seasons.values():
        stamps = [m[0] for m in matches]
        if (max(stamps) - min(stamps)) / 86400 > max_span_days:
            return False
        per_team = Counter(t for m in matches for t in m[1:])
        if max(per_team.values()) > max_team_matches:
            return False
        leagues |= {lg for t in per_team if (lg := home_league.get(t)) is not None}
    return len(leagues) >= 2


def scan(db: Path, max_span_days: int, max_team_matches: int) -> list[dict[str, Any]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    known = reviewed_ids()
    meta: dict[int, dict[str, Any]] = {}
    seasons: dict[int, dict[Any, list[tuple[int, int, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    team_comps: dict[int, Counter[int]] = defaultdict(Counter)
    national: dict[int, bool] = {}
    for (js,) in con.execute(
        "SELECT event_json FROM sofa_listed_event WHERE sport = 'football'"
    ):
        e = json.loads(js)
        t = e.get("tournament") or {}
        u = t.get("uniqueTournament") or {}
        cid, ts = u.get("id"), e.get("startTimestamp")
        try:
            home, away = int(e["homeTeam"]["id"]), int(e["awayTeam"]["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(cid, int) or not isinstance(ts, int):
            continue
        team_comps[home][cid] += 1
        team_comps[away][cid] += 1
        national[cid] = national.get(cid, False) or bool(e["homeTeam"].get("national"))
        seasons[cid][(e.get("season") or {}).get("id")].append((ts, home, away))
        if cid not in meta:
            meta[cid] = {
                "competition_id": cid,
                "name": u.get("name"),
                "slug": u.get("slug"),
                "category": (u.get("category") or {}).get("name"),
                "example_event": {
                    "id": e.get("id"),
                    "home": e["homeTeam"].get("name"),
                    "away": e["awayTeam"].get("name"),
                    "startTimestamp": ts,
                    "tournament_name": t.get("name"),
                    "season": (e.get("season") or {}).get("name"),
                    "season_editor": (e.get("season") or {}).get("editor"),
                    "userCount": u.get("userCount"),
                },
            }

    def home_league(team: int, exclude: int) -> int | None:
        other = [(n, c) for c, n in team_comps[team].items() if c != exclude]
        return max(other)[1] if other else None

    out: list[dict[str, Any]] = []
    for cid, info in meta.items():
        if cid in known or national.get(cid):
            continue
        named = is_named_friendly(str(info["name"] or ""))
        teams = {t for ms in seasons[cid].values() for m in ms for t in m[1:]}
        shaped = shaped_like_invitational(
            seasons[cid], {t: home_league(t, cid) for t in teams},
            max_span_days, max_team_matches,
        )
        if named or shaped:
            n_events = sum(len(v) for v in seasons[cid].values())
            out.append({**info, "n_events": n_events,
                        "why": "name" if named else "shape"})
    out.sort(key=lambda c: -c["n_events"])
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=Path("data/sofa.db"))
    ap.add_argument("--max-span-days", type=int, default=21)
    ap.add_argument("--max-team-matches", type=int, default=4)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"no DB at {args.db}", file=sys.stderr)
        return 2
    found = scan(args.db, args.max_span_days, args.max_team_matches)
    doc = {
        "_doc": [
            "Football competitions proposed by "
            "scripts/sofa/find_friendly_competitions.py "
            f"({datetime.now(UTC).date().isoformat()}): not in the friendly "
            "config, and friendly-named or shaped like an invitational "
            "tournament. CANDIDATES, not decisions - review each before "
            "promoting it to the config.",
        ],
        "competitions": found,
    }
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    for c in found:
        print(f"{c['n_events']:6d} {c['competition_id']:7d} [{c['why']}] "
              f"{c['name']} ({c['category']})")
    print(f"{len(found)} candidates", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
