#!/usr/bin/env python3
"""Reserve / youth sides in RESOLVE's search (read-only evidence).

`resolve.search_query` sends Sofascore the cache key with our "(r)" marker
removed, so "Atlas U21" is searched as "atlas" and the senior Atlas FC fills
the candidate list while "Atlas FC U21" (1111909) never reaches it.

Offline (no network): for every board of --from..--to, the football entries
with a side that is not a senior squad (`names.team_levels` != {"S"}), and
how many of them RESOLVE left without a fixture (no 02_fixtures.json row
carries the Superbet id) - per date, and the distinct lost sides.

Live (--live, through the bridge; --offset / --limit keep the series short):
for each distinct lost side, the search RESOLVE sends today and the retry
queries a fix could send, and for each whether a candidate of the side's
squad level (`resolve.squad_level_candidate`) is among the team results of
the sport. A request is a search only - no listing, no cache write. Rows
append to --jsonl so a series resumes where it stopped.

Replay (--replay --db-copy <copy>, never the working database): every lost
board entry with a squad side goes through RESOLVE's own `_resolve_one`
twice on the copy - the retry off, then on (the copy's entity misses
cleared before each pass) - and every pair only the retry finds is listed
with both Superbet and both Sofascore names, for a check by eye: a wrong
pair is a wrong fixture. Rows append to --replay-jsonl.

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_squad_search.py \
      [--from 2026-10-07] [--to 2026-10-21] [--live --offset 0 --limit 40] \
      [--jsonl f] [--md-out f]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.names import normalize_name, team_levels  # noqa: E402
from bet.sofa.resolve import (  # noqa: E402
    candidate_fits,
    search_query,
    squad_level_candidate,
    squad_retry_queries,
)

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_squad_side(name: str) -> bool:
    return team_levels(normalize_name(name)) != frozenset({"S"})


def offline(runs_dir: str, first: str | None, last: str | None,
            sport: str = "football") -> dict[str, Any]:
    per_date: dict[str, dict[str, int]] = {}
    lost_sides: Counter[str] = Counter()
    for d in sorted(p.name for p in Path(runs_dir).iterdir() if _DATE.match(p.name)):
        if (first and d < first) or (last and d > last):
            continue
        board_p = Path(runs_dir) / d / "01_board.json"
        fix_p = Path(runs_dir) / d / "02_fixtures.json"
        if not board_p.exists() or not fix_p.exists():
            continue
        board = json.loads(board_p.read_text(encoding="utf-8"))
        fixtures = json.loads(fix_p.read_text(encoding="utf-8"))
        bridged = {str(i) for f in fixtures for i in f.get("superbet_event_ids", [])}
        row = {"entries": 0, "squad_entries": 0, "lost": 0, "squad_lost": 0}
        for e in board:
            if e.get("sport") != sport:
                continue
            squad = [s for s in (e["side_a"], e["side_b"]) if is_squad_side(s)]
            hit = str(e["superbet_event_id"]) in bridged
            row["entries"] += 1
            row["lost"] += 0 if hit else 1
            if squad:
                row["squad_entries"] += 1
                if not hit:
                    row["squad_lost"] += 1
                    lost_sides.update(squad)
        per_date[d] = row
    return {"per_date": per_date, "lost_sides": dict(lost_sides.most_common())}


def search_row(client: Any, side: str, sport: str = "football") -> dict[str, Any]:
    """What each query's team results hold for this side."""
    norm = normalize_name(side)
    queries = [("plain", search_query(norm))] + [
        (f"retry{i}", q) for i, q in enumerate(squad_retry_queries(side, norm))
    ]
    out: dict[str, Any] = {"side": side, "norm": norm, "queries": {}}
    for label, q in queries:
        data = client.search(q) or {}
        teams = [
            r["entity"] for r in data.get("results", [])
            if r.get("type") == "team"
            and (r.get("entity", {}).get("sport", {}) or {}).get("slug") == sport
        ]
        fits = [t for t in teams if candidate_fits(norm, t, sport)]
        squad = [t for t in fits if squad_level_candidate(norm, t)]
        out["queries"][label] = {
            "q": q,
            "teams": len(teams),
            "fits_top3": [t.get("name") for t in fits[:3]],
            "squad": [(t.get("id"), t.get("name")) for t in squad[:3]],
            "squad_in_top3": any(squad_level_candidate(norm, t) for t in fits[:3]),
        }
    return out


def lost_entries(runs_dir: str, first: str | None, last: str | None,
                 sport: str = "football") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in sorted(p.name for p in Path(runs_dir).iterdir() if _DATE.match(p.name)):
        if (first and d < first) or (last and d > last):
            continue
        board_p = Path(runs_dir) / d / "01_board.json"
        fix_p = Path(runs_dir) / d / "02_fixtures.json"
        if not board_p.exists() or not fix_p.exists():
            continue
        fixtures = json.loads(fix_p.read_text(encoding="utf-8"))
        bridged = {str(i) for f in fixtures for i in f.get("superbet_event_ids", [])}
        for e in json.loads(board_p.read_text(encoding="utf-8")):
            if (e.get("sport") == sport
                    and str(e["superbet_event_id"]) not in bridged
                    and any(is_squad_side(s) for s in (e["side_a"], e["side_b"]))):
                out.append({**e, "date": d})
    return out


def replay_entry(config: Any, entry: dict[str, Any]) -> dict[str, Any]:
    """One lost entry through `_resolve_one`, retry off then on (copy only)."""
    import sqlite3
    from unittest import mock

    from bet.sofa import epochs, resolve
    from bet.sofa.cache import SofaCache
    from bet.sofa.client import SofascoreClient
    from bet.sofa.contracts import BoardFixture
    from scripts.sofa.run_resolve import _resolve_one

    bf = BoardFixture.model_validate_json(
        json.dumps({k: v for k, v in entry.items() if k != "date"}))
    client = SofascoreClient(config)
    cache = SofaCache(config)
    row: dict[str, Any] = {"date": entry["date"], "id": entry["superbet_event_id"],
                           "match": entry["match_name"]}
    for label, on in (("off", False), ("on", True)):
        with sqlite3.connect(config.db_path) as conn:
            conn.execute("DELETE FROM sofa_entity_miss")
        patches: list[Any] = (
            [mock.patch.object(epochs, "SQUAD_SEARCH_RETRY_FROM_UTC",
                               datetime(2026, 9, 1, tzinfo=UTC))]
            if on else
            [mock.patch.object(resolve, "squad_retry_queries", lambda *_a: [])]
        )
        for p in patches:
            p.start()
        try:
            resolver = resolve.SofaResolver(config, client, cache)
            out = _resolve_one(bf, resolver, client, cache, "MEASURE")
        finally:
            for p in reversed(patches):
                p.stop()
        f = out.fixture
        row[label] = (None if f is None else {
            "event": f.sofascore_event_id, "home": f.home_name, "away": f.away_name,
            "competition": f.competition_name, "kickoff": f.kickoff_utc.isoformat(),
        }) if out.gap is None else {"gap": str(out.gap)}
    return row


def summarise(rows: list[dict[str, Any]]) -> dict[str, int]:
    s = Counter[str]()
    for r in rows:
        qs = r["queries"]
        plain = qs["plain"]["squad_in_top3"]
        retry = any(v["squad"] for k, v in qs.items() if k != "plain")
        s["sides"] += 1
        s["plain_has_squad"] += plain
        s["retry_has_squad"] += retry
        s["only_retry"] += (not plain) and retry
        s["neither"] += (not plain) and (not retry)
        if "(r)" in r["norm"]:
            s["r_marker_sides"] += 1
            s["r_only_retry"] += (not plain) and retry
    return dict(s)


def render(off: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = ["# Squad sides in RESOLVE's search", "",
             "| date | football entries | lost | squad entries | squad lost |",
             "|---|---|---|---|---|"]
    tot = Counter[str]()
    for d, r in off["per_date"].items():
        lines.append(f"| {d} | {r['entries']} | {r['lost']} | "
                     f"{r['squad_entries']} | {r['squad_lost']} |")
        tot.update(r)
    lines.append(f"| all | {tot['entries']} | {tot['lost']} | "
                 f"{tot['squad_entries']} | {tot['squad_lost']} |")
    lines += ["", f"Distinct lost squad sides: {len(off['lost_sides'])}", ""]
    if rows:
        lines += ["## Live search", "", json.dumps(summarise(rows)), ""]
        for r in rows:
            qs = r["queries"]
            lines.append(
                f"- {r['side']}: plain {qs['plain']['q']!r} squad="
                f"{qs['plain']['squad_in_top3']}; "
                + "; ".join(f"{k} {v['q']!r} -> {v['squad'][:1]}"
                            for k, v in qs.items() if k != "plain"))
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="first", default=None)
    ap.add_argument("--to", dest="last", default=None)
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--jsonl", default=None)
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--db-copy", default=None)
    ap.add_argument("--replay-jsonl", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    if args.replay:
        import dataclasses

        copy = Path(args.db_copy or "")
        if not args.db_copy or not copy.exists() or (
                copy.resolve() == Path(config.db_path).resolve()):
            print("--replay needs --db-copy <a VACUUM INTO copy>", file=sys.stderr)
            return 2
        rconfig = dataclasses.replace(config, db_path=str(copy))
        out_p = Path(args.replay_jsonl) if args.replay_jsonl else None
        done = set()
        if out_p and out_p.exists():
            done = {(r["date"], r["id"]) for r in map(
                json.loads, out_p.read_text(encoding="utf-8").splitlines())}
        todo = [e for e in lost_entries(args.runs_dir or config.runs_dir,
                                        args.first, args.last)
                if (e["date"], e["superbet_event_id"]) not in done]
        for e in todo[args.offset:args.offset + args.limit]:
            row = replay_entry(rconfig, e)
            print(json.dumps(row, ensure_ascii=False))
            if out_p:
                with out_p.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return 0
    off = offline(args.runs_dir or config.runs_dir, args.first, args.last)
    rows: list[dict[str, Any]] = []
    jsonl = Path(args.jsonl) if args.jsonl else None
    if jsonl and jsonl.exists():
        rows = [json.loads(x) for x in jsonl.read_text(encoding="utf-8").splitlines()
                if x.strip()]
    if args.live:
        from bet.sofa.client import SofascoreClient

        client = SofascoreClient(config)
        done = {r["side"] for r in rows}
        sides = [s for s in off["lost_sides"] if s not in done]
        for side in sides[args.offset:args.offset + args.limit]:
            row = search_row(client, side)
            rows.append(row)
            if jsonl:
                with jsonl.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
    md = render(off, rows)
    print(md)
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
