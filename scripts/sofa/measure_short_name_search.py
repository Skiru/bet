#!/usr/bin/env python3
"""RESOLVE short-name search: precision backtest and F3 recall (read-only
evidence for epochs.FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC).

The rule under test (bet.sofa.short_name_search): a football pair that the
normal search, the reserve retry and the searched anchor left without a
fixture is searched again by each side's longest words
(`short_name_queries`); a result counts for a side only when it is a football
team of the side's gender / squad level holding the query as a whole word,
the same unmarked squad words, the query not a word of the other side
(`short_candidate_fits`). A game is accepted only when side A's candidates
(normal search or short) hold its home team and side B's its away team,
within 60 min of Superbet's start, gender, levels, not postponed, the ONE such
game, and at least one side came through a short query
(`short_name_pair_event`).

Precision, on every bridged football fixture of RESOLVE (02_fixtures.json
with its 01_board.json entry); a short query's results stood in by EVERY team
of the listings in the database that `short_candidate_fits` admits (a
superset of the 3 search results - more impostors, never fewer), the normal
search by the true team:

- TRUE: both sides with their true team + short impostors;
- SHORT_ONLY: no normal search, only the short stand-ins (the true team
  only when its own name holds the query);
- HIDE_A / HIDE_B / HIDE_BOTH: the true team of a side removed from its
  candidates entirely (Sofascore's search missed it) - every accept is a
  wrong identity;
- DECOY: side B's name replaced by up to 3 other bridged board sides of the
  same Superbet tournament and day (else category), each with its own true
  team + short impostors - every accept is a wrong identity.

`--live-f3 final2.json` replays RESOLVE's `_resolve_one` (switch on, the
reserve retry and searched anchor on, entity misses deleted) on a COPY of the
database (`--db-copy`, never data/sofa.db) for the 22 F3 entries of the
2026-10-21 gap classification, through the bridge (one entry at a time;
`ensure_bridge.py` first). Counts the searches each pair cost.

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_short_name_search.py \\
      [--from 2026-10-05] [--to 2026-10-20] [--json-out f] \\
      [--live-f3 final2.json --db-copy copy.db [--limit 40]]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.short_name_search import (  # noqa: E402
    _words,
    short_candidate_fits,
    short_name_pair_event,
    short_name_queries,
)
from scripts.sofa.measure_searched_anchor import (  # noqa: E402
    _ts,
    load_bridged,
    load_events,
)

Event = dict[str, Any]
Listing = tuple[dict[str, Any], list[Event]]


class World:
    """Every listed football team, its games, and a word index."""

    def __init__(self, events: dict[int, Event]) -> None:
        self.by_team: dict[int, list[Event]] = defaultdict(list)
        self.team: dict[int, dict[str, Any]] = {}
        for e in events.values():
            for key in ("homeTeam", "awayTeam"):
                t = e.get(key) or {}
                if isinstance(t.get("id"), int):
                    self.by_team[t["id"]].append(e)
                    self.team.setdefault(t["id"], {
                        **t, "sport": {"slug": "football"}})
        self.by_word: dict[str, set[int]] = defaultdict(set)
        for tid, t in self.team.items():
            for w in _words(normalize_name(str(t.get("name") or ""))):
                self.by_word[w].add(tid)

    def entity(self, tid: int, fallback: str = "") -> dict[str, Any]:
        t = self.team.get(tid) or {}
        return {"id": tid, "name": t.get("name") or fallback,
                "gender": t.get("gender"), "sport": {"slug": "football"}}

    def short(self, side: str, other: str) -> set[int]:
        """The short queries' stand-in: every team the rule would admit."""
        norm, norm_o = normalize_name(side), normalize_name(other)
        out: set[int] = set()
        for q in short_name_queries(norm):
            for tid in self.by_word.get(q, ()):
                if short_candidate_fits(norm, norm_o, q, self.team[tid]):
                    out.add(tid)
        return out

    def listings(self, ids: set[int], names: dict[int, str]) -> list[Listing]:
        return [(self.entity(t, names.get(t, "")), self.by_team.get(t, []))
                for t in sorted(ids)]


def judge(
    world: World, row: dict[str, Any], side_b: str,
    a_normal: set[int], a_short: set[int], b_normal: set[int], b_short: set[int],
) -> tuple[str, int | None]:
    names = {row["home_id"]: row["home_name"], row["away_id"]: row["away_name"]}
    ca = world.listings(a_normal | a_short, names)
    cb = world.listings(b_normal | b_short, names)
    e = short_name_pair_event(ca, cb, row["kickoff"], row["side_a"], side_b)
    if e is None:
        return "NONE", None
    home = (e.get("homeTeam") or {}).get("id")
    away = (e.get("awayTeam") or {}).get("id")
    if home not in a_short and away not in b_short:
        return "NO_SHORT_SIDE", None
    return "PICK", int(e["id"])


def bridged_backtest(world: World, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_group: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_group[(r["day"], r["tournament_id"])].append(r)
        by_group[(r["day"], ("cat", r["category_id"]))].append(r)
    res: Counter[str] = Counter()
    wrong: list[dict[str, Any]] = []
    queries_per_pair: list[int] = []
    for r in rows:
        a, b = r["side_a"], r["side_b"]
        ta, tb = r["home_id"], r["away_id"]
        sa, sb = world.short(a, b), world.short(b, a)
        queries_per_pair.append(len(short_name_queries(normalize_name(a)))
                                + len(short_name_queries(normalize_name(b))))
        res["fixtures"] += 1
        res["true_a_by_short"] += ta in sa
        res["true_b_by_short"] += tb in sb
        variants = {
            "TRUE": ({ta}, sa, {tb}, sb),
            "SHORT_ONLY": (set(), sa, set(), sb),
            "HIDE_A": (set(), sa - {ta}, {tb}, sb),
            "HIDE_B": ({ta}, sa, set(), sb - {tb}),
            "HIDE_BOTH": (set(), sa - {ta}, set(), sb - {tb}),
        }
        for label, (an, ash, bn, bsh) in variants.items():
            out, eid = judge(world, r, b, an, ash, bn, bsh)
            if out == "PICK":
                ok = eid == r["event_id"] and label in ("TRUE", "SHORT_ONLY")
                res[f"{label}:{'correct' if ok else 'WRONG'}"] += 1
                if not ok:
                    wrong.append({"variant": label, "match": f"{a} v {b}",
                                  "kickoff": r["kickoff"].isoformat(),
                                  "bridged": r["event_id"], "picked": eid,
                                  "game": _game(world, eid)})
            else:
                res[f"{label}:{out}"] += 1
        pool = [x for x in by_group[(r["day"], r["tournament_id"])]
                if x["sb"] != r["sb"]]
        if not pool:
            pool = [x for x in by_group[(r["day"], ("cat", r["category_id"]))]
                    if x["sb"] != r["sb"]]
        decoys: list[tuple[str, int]] = []
        for x in sorted(pool, key=lambda x: x["sb"]):
            for dn, di in ((x["side_a"], x["home_id"]), (x["side_b"], x["away_id"])):
                if di in (ta, tb) or normalize_name(dn) in (
                        normalize_name(a), normalize_name(b)):
                    continue
                decoys.append((dn, di))
        for dn, di in decoys[:3]:
            res["DECOY:tried"] += 1
            out, eid = judge(world, r, dn, {ta}, sa, {di}, world.short(dn, a))
            if out == "PICK":
                res["DECOY:WRONG"] += 1
                wrong.append({"variant": "DECOY", "match": f"{a} v {dn}",
                              "true_opp": b, "kickoff": r["kickoff"].isoformat(),
                              "bridged": r["event_id"], "picked": eid,
                              "game": _game(world, eid)})
            else:
                res[f"DECOY:{out}"] += 1
    qn = Counter(queries_per_pair)
    return {"counts": dict(sorted(res.items())), "wrong": wrong,
            "short_queries_per_pair": dict(sorted(qn.items()))}


def _game(world: World, eid: int | None) -> str:
    for evs in world.by_team.values():
        for e in evs:
            if e.get("id") == eid:
                return (f"{(e.get('homeTeam') or {}).get('name')} - "
                        f"{(e.get('awayTeam') or {}).get('name')}")
    return ""


def unbridged_per_day(runs: Path, first: str, last: str) -> dict[str, int]:
    """Football board entries of a day no fixture bridged (the pairs the
    short step would be asked for, before 'started' and 'ambiguous')."""
    out: dict[str, int] = {}
    for d in sorted(p.name for p in runs.iterdir() if p.is_dir()):
        if d < first or d > last:
            continue
        bp, fp = runs / d / "01_board.json", runs / d / "02_fixtures.json"
        if not bp.exists() or not fp.exists():
            continue
        bridged = {str(s) for f in json.loads(fp.read_text())
                   for s in f.get("superbet_event_ids") or []}
        out[d] = sum(1 for e in json.loads(bp.read_text())
                     if e.get("sport") == "football"
                     and str(e["superbet_event_id"]) not in bridged)
    return out


def live_f3(config: SofaConfig, classes: Path, limit: int) -> list[dict[str, Any]]:
    """The F3 entries through `_resolve_one` with the switch on (DB copy)."""
    from unittest import mock

    from bet.sofa import epochs, resolve
    from bet.sofa.cache import SofaCache
    from bet.sofa.client import SofascoreClient
    from bet.sofa.contracts import BoardFixture
    from scripts.sofa.run_resolve import _resolve_one

    if Path(config.db_path).resolve() == (_ROOT / "data" / "sofa.db").resolve() \
            or Path(config.db_path).name == "sofa.db":
        raise SystemExit("--db-copy must be a copy, never data/sofa.db")
    wanted = {x["id"]: x for x in json.loads(classes.read_text())
              if str(x["final"]).startswith("T:")}
    runs = Path(config.runs_dir)
    board: dict[str, dict[str, Any]] = {}
    for x in wanted.values():
        for e in json.loads((runs / x["day"] / "01_board.json").read_text()):
            if str(e["superbet_event_id"]) == x["id"]:
                board[x["id"]] = e
    client = SofascoreClient(config)
    cache = SofaCache(config)
    on = datetime(2026, 10, 1, tzinfo=UTC)
    searches: list[str] = []
    real_search = client.search

    listings: list[int] = []
    real_listing = client.entity_events

    def counted(q: str, **kw: Any) -> Any:
        searches.append(q)
        return real_search(q, **kw)

    def counted_listing(entity_id: int, *a: Any, **kw: Any) -> Any:
        listings.append(entity_id)
        return real_listing(entity_id, *a, **kw)

    rows: list[dict[str, Any]] = []
    for sid, x in list(wanted.items())[:limit]:
        bf = BoardFixture.model_validate_json(json.dumps(board[sid]))
        with sqlite3.connect(config.db_path) as conn:
            conn.execute("DELETE FROM sofa_entity_miss")
        searches.clear()
        listings.clear()
        patches: list[Any] = [mock.patch.object(epochs, name, on) for name in (
            "FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC", "SQUAD_SEARCH_RETRY_FROM_UTC",
            "FOOTBALL_SEARCHED_ANCHOR_FROM_UTC", "ENTITY_MISS_PER_DAY_FROM_UTC")]
        patches.append(mock.patch.object(client, "search", counted))
        patches.append(mock.patch.object(client, "entity_events", counted_listing))
        for p in patches:
            p.start()
        try:
            resolver = resolve.SofaResolver(config, client, cache)
            out = _resolve_one(bf, resolver, client, cache, "MEASURE")
        finally:
            for p in reversed(patches):
                p.stop()
        f = out.fixture
        expected = int(str(x["ex"]).split()[0])
        a, b = str(x["match"]).split("·")
        shorts = set(short_name_queries(normalize_name(a))) | set(
            short_name_queries(normalize_name(b)))
        row = {"id": sid, "day": x["day"], "match": x["match"], "class": x["final"],
               "expected": expected, "expected_game": str(x["ex"]).split(" ", 1)[1],
               "searches": len(searches), "queries": list(searches),
               "short_searches": sum(q in shorts for q in searches),
               "listing_requests": len(listings)}
        if f is None:
            row["outcome"] = f"GAP:{out.gap}"
        else:
            row.update(picked=f.sofascore_event_id, rule=f.match_rule,
                       identity=f.identity, game=f"{f.home_name} - {f.away_name}",
                       outcome=("CORRECT" if f.sofascore_event_id == expected
                                else "WRONG"))
        print(json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--from", dest="first", default="2026-10-05")
    ap.add_argument("--to", dest="last", default="2026-10-20")
    ap.add_argument("--db-path", help="read-only source (default SofaConfig)")
    ap.add_argument("--runs-dir")
    ap.add_argument("--json-out")
    ap.add_argument("--live-f3")
    ap.add_argument("--db-copy")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)
    cfg = SofaConfig.from_env()
    if args.runs_dir:
        cfg = dataclasses.replace(cfg, runs_dir=args.runs_dir)
    if args.db_path:
        cfg = dataclasses.replace(cfg, db_path=args.db_path)
    report: dict[str, Any] = {"from": args.first, "to": args.last}
    if args.live_f3:
        if not args.db_copy:
            raise SystemExit("--live-f3 needs --db-copy")
        live_cfg = dataclasses.replace(cfg, db_path=args.db_copy)
        rows = live_f3(live_cfg, Path(args.live_f3), args.limit)
        report["f3"] = rows
        print(Counter(r["outcome"] for r in rows))
    else:
        runs = Path(cfg.runs_dir)
        conn = sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True)
        rows_b = load_bridged(runs, args.first, args.last)
        lo = int((_ts(args.first + "T00:00:00Z") - timedelta(days=2)).timestamp())
        hi = int((_ts(args.last + "T00:00:00Z") + timedelta(days=3)).timestamp())
        ids = {r["home_id"] for r in rows_b} | {r["away_id"] for r in rows_b}
        world = World(load_events(conn, lo, hi, ids))
        report["fixtures"] = len(rows_b)
        report["bridged"] = bridged_backtest(world, rows_b)
        report["unbridged_per_day"] = unbridged_per_day(runs, args.first, args.last)
        print(f"bridged football fixtures {args.first}..{args.last}: {len(rows_b)}")
        for k, v in report["bridged"]["counts"].items():
            print(f"  {k}: {v}")
        print("  short queries per pair: "
              f"{report['bridged']['short_queries_per_pair']}")
        for w in report["bridged"]["wrong"]:
            print(f"  WRONG {w}")
        print(f"  unbridged football board entries per day: "
              f"{report['unbridged_per_day']}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
