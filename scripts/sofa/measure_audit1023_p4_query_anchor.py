#!/usr/bin/env python3
"""QUERY_ANCHOR backtest (coverage audit 2026-10-23 P4; read-only evidence).

The rule under test is sport_identity.match_query_anchor: with no side's
resolved id, the query-only team's ONE game at Superbet's start (gender,
not postponed), named as the searched side (>= 90), the opponent agreeing
weakly - VETO by the opponent's own query (TeamResolver.query_ids), then
MUTUAL / NAME (>= 65) / SHARED_WORD.

Measured per sport (hockey, basketball, volleyball) on the latest
SPORT_IDENTITY record of every Superbet event in [--from, --to]:

A. precision with the ids hidden: every IDENTIFIED event, each side in turn
   as the searched one, the opponent's board name as it is, the searched team
   being
   - TRUE: the pinned event's team of that side;
   - QUERY: what TeamResolver.query_id returns for the board name today (an
     impostor when it is another team) - the live situation;
   a pick that is not the pinned event is WRONG.
B. decoy opponent: the TRUE searched team with the opponent's board name
   replaced by every other board team of the same sport, tournament and
   day; any IDENTIFIED is a false acceptance (the anchor's game is real, the
   Superbet pair is not).
C. recall: every NOT_IDENTIFIED query-only record (queried_team_id), the
   rule over the team's known games; a pick checked against what
   SHADOW_SETTLE later found (settled.json) - AGREES / CONTRADICTS / UNKNOWN.

Candidates: every known game of the team (sofa_listed_event and the cached
pages of sofa_entity_events, most recently fetched version of each event).
The name index is the database's whole window (a little hindsight: names
learned later are in it - the veto sees more names than it did live).

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_audit1023_p4_query_anchor.py \\
      [--db-path data/refit_2026-10-23_allin/sofa_copy.db] [--from 2026-10-05] \\
      [--to 2026-10-23] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_identity as si  # noqa: E402
from scripts.sofa.measure_day_anchor import records, settle_found  # noqa: E402

SPORTS = ("hockey", "basketball", "volleyball")
SLUG = {"hockey": "ice-hockey", "basketball": "basketball",
        "volleyball": "volleyball"}


def load_events(conn: sqlite3.Connection, slugs: Iterable[str], since_ts: int,
                teams: set[int]) -> dict[int, list[dict[str, Any]]]:
    """team id -> its known games (event JSON), latest fetched version."""
    best: dict[int, tuple[str, dict[str, Any]]] = {}

    def add(e: Mapping[str, Any], at: str) -> None:
        eid = e.get("id")
        if not isinstance(eid, int):
            return
        h = (e.get("homeTeam") or {}).get("id")
        a = (e.get("awayTeam") or {}).get("id")
        if h not in teams and a not in teams:
            return
        if eid in best and best[eid][0] > at:
            return
        best[eid] = (at, dict(e))

    want = set(slugs)
    for slug, at, txt in conn.execute(
            "SELECT sport, fetched_at, event_json FROM sofa_listed_event "
            "WHERE start_ts >= ?", (since_ts,)):
        if slug in want:
            add(json.loads(txt), str(at))
    ids = sorted(teams)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for at, txt in conn.execute(
                f"SELECT fetched_at, events_json FROM sofa_entity_events "
                f"WHERE sofascore_entity_id IN ({marks})", chunk):
            try:
                events = json.loads(txt).get("events") or []
            except (ValueError, AttributeError):
                continue
            for e in events:
                slug = (((e.get("tournament") or {}).get("category") or {})
                        .get("sport") or {}).get("slug")
                ts = e.get("startTimestamp")
                if slug in want and isinstance(ts, int) and ts >= since_ts:
                    add(e, str(at))
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for _, e in best.values():
        for side in ("homeTeam", "awayTeam"):
            t = (e.get(side) or {}).get("id")
            if t in teams:
                out[t].append(e)
    return out


def board(rec: Mapping[str, Any], team1: str | None = None,
          team2: str | None = None) -> si.BoardEvent:
    t1 = str(rec["team1"]) if team1 is None else team1
    t2 = str(rec["team2"]) if team2 is None else team2
    return si.BoardEvent(str(rec["sport"]), str(rec["superbet_event_id"]),
                         f"{t1}·{t2}", t1, t2, str(rec["kickoff_utc"]),
                         str(rec.get("tournament") or ""),
                         str(rec.get("source_date") or ""))


def side_team(rec: Mapping[str, Any], team1: bool) -> int | None:
    h, a = rec.get("home_id"), rec.get("away_id")
    if not isinstance(h, int) or not isinstance(a, int):
        return None
    home_t1 = bool(rec.get("home_is_team1"))
    return h if home_t1 == team1 else a


def measure(conn: sqlite3.Connection, runs_dir: str, first: str, last: str
            ) -> dict[str, Any]:
    recs = [r for r in records(runs_dir, first, last) if r.get("sport") in SPORTS]
    settled = settle_found(runs_dir)
    now_ts = int(datetime.fromisoformat(last).replace(tzinfo=UTC).timestamp()) + 86400
    resolver = si.TeamResolver(conn, now_ts)
    teams: set[int] = set()
    for r in recs:
        for x in (r.get("home_id"), r.get("away_id"), r.get("queried_team_id")):
            if isinstance(x, int):
                teams.add(x)
    query_cache: dict[tuple[str, str], int | None] = {}

    def query(sport: str, name: str) -> int | None:
        key = (sport, name)
        if key not in query_cache:
            query_cache[key] = resolver.query_id(sport, name)
        return query_cache[key]

    # the impostor ids the query may return
    for r in recs:
        if r["status"] == si.IDENTIFIED:
            for name in (r["team1"], r["team2"]):
                q = query(str(r["sport"]), str(name))
                if q is not None:
                    teams.add(q)
    since = int(datetime.fromisoformat(first).replace(tzinfo=UTC).timestamp()) - 86400
    games = load_events(conn, SLUG.values(), since, teams)
    opp_cache: dict[tuple[str, str], frozenset[int]] = {}

    def opponents(sport: str, name: str) -> frozenset[int]:
        key = (sport, name)
        if key not in opp_cache:
            opp_cache[key] = resolver.query_ids(sport, name)
        return opp_cache[key]

    out: dict[str, Any] = {"from": first, "to": last, "sports": {}}
    for sport in SPORTS:
        rs = [r for r in recs if r["sport"] == sport]
        ident = [r for r in rs if r["status"] == si.IDENTIFIED
                 and isinstance(r.get("sofascore_event_id"), int)]
        sec: dict[str, Any] = {"events": len(rs), "identified": len(ident)}
        a_true: Counter[str] = Counter()
        a_query: Counter[str] = Counter()
        wrong: list[dict[str, Any]] = []
        b_dec: Counter[str] = Counter()
        decoy_acc: list[dict[str, Any]] = []
        # decoy pools: board names of the same tournament / day
        pool: dict[tuple[str, str], list[str]] = defaultdict(list)
        for r in ident:
            k = (str(r.get("tournament")), str(r["kickoff_utc"])[:10])
            pool[k] += [str(r["team1"]), str(r["team2"])]
        for r in ident:
            pinned = int(r["sofascore_event_id"])
            for k_t1 in (True, False):
                ev = board(r)
                own = str(r["team1"] if k_t1 else r["team2"])
                other = str(r["team2"] if k_t1 else r["team1"])
                true_id = side_team(r, k_t1)
                if true_id is None:
                    continue
                opp = opponents(sport, other)
                got = si.match_query_anchor(ev, games.get(true_id, []), true_id,
                                            k_t1, opp)
                if got["status"] == si.IDENTIFIED:
                    ok = int(got["event"]["id"]) == pinned
                    a_true["RIGHT" if ok else "WRONG"] += 1
                    a_true["rule:" + str(got["query_anchor_rule"])] += 1
                    if not ok:
                        wrong.append({"case": "TRUE",
                                      "superbet": r["superbet_event_id"],
                                      "match": r["match_name"], "pinned": pinned,
                                      "picked": got["event"]["id"]})
                else:
                    a_true[str(got["reason"])] += 1
                q = query(sport, own)
                if q is None:
                    a_query["NO_QUERY_ID"] += 1
                else:
                    a_query["IMPOSTOR_ID" if q != true_id else "TRUE_ID"] += 1
                    gq = si.match_query_anchor(ev, games.get(q, []), q, k_t1, opp)
                    if gq["status"] == si.IDENTIFIED:
                        ok = int(gq["event"]["id"]) == pinned
                        a_query["RIGHT" if ok else "WRONG"] += 1
                        if not ok:
                            wrong.append({"case": "QUERY",
                                          "superbet": r["superbet_event_id"],
                                          "match": r["match_name"], "pinned": pinned,
                                          "picked": gq["event"]["id"], "query_id": q,
                                          "true_id": true_id})
                    else:
                        a_query[str(gq["reason"])] += 1
                # B: decoy opponents
                k = (str(r.get("tournament")), str(r["kickoff_utc"])[:10])
                for decoy in sorted(set(pool[k]) - {own, other}):
                    evd = board(r, own if k_t1 else decoy, decoy if k_t1 else own)
                    gd = si.match_query_anchor(evd, games.get(true_id, []), true_id,
                                               k_t1, opponents(sport, decoy))
                    b_dec["tried"] += 1
                    if gd["status"] == si.IDENTIFIED:
                        b_dec["ACCEPTED"] += 1
                        b_dec["rule:" + str(gd["query_anchor_rule"])] += 1
                        decoy_acc.append({"match": r["match_name"], "searched": own,
                                          "decoy": decoy,
                                          "rule": gd["query_anchor_rule"],
                                          "picked": gd["event"]["id"]})
                    else:
                        b_dec[str(gd["reason"])] += 1
        # C: recall on the query-only refusals
        c: Counter[str] = Counter()
        recovered: list[dict[str, Any]] = []
        for r in rs:
            if r["status"] != si.NOT_IDENTIFIED or not r.get("query_only"):
                continue
            q = r.get("queried_team_id")
            if not isinstance(q, int):
                continue
            c["query_only_refused"] += 1
            k_t1 = query(sport, str(r["team1"])) == q
            ev = board(r)
            other = str(r["team2"] if k_t1 else r["team1"])
            got = si.match_query_anchor(ev, games.get(q, []), q, k_t1,
                                        opponents(sport, other))
            if got["status"] != si.IDENTIFIED:
                c[str(got["reason"])] += 1
                continue
            c["RECOVERED"] += 1
            pick = int(got["event"]["id"])
            st = settled.get(str(r["superbet_event_id"])) or {}
            found = st.get("sofascore_event_id")
            verdict = ("UNKNOWN" if not isinstance(found, int)
                       else "AGREES" if found == pick else "CONTRADICTS")
            c[verdict] += 1
            e = got["event"]
            recovered.append({
                "day": str(r["kickoff_utc"])[:10], "match": r["match_name"],
                "sofascore": f"{(e.get('homeTeam') or {}).get('name')} - "
                             f"{(e.get('awayTeam') or {}).get('name')}",
                "picked": pick, "rule": got["query_anchor_rule"],
                "settle": verdict, "settle_id": found})
        sec.update(A_true=dict(a_true), A_query=dict(a_query), wrong=wrong,
                   B_decoy=dict(b_dec), decoy_accepted=decoy_acc[:40],
                   C_recall=dict(c), recovered=recovered)
        out["sports"][sport] = sec
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", default="data/refit_2026-10-23_allin/sofa_copy.db")
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--from", dest="first", default="2026-10-05")
    ap.add_argument("--to", dest="last", default="2026-10-23")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    conn = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    res = measure(conn, args.runs_dir, args.first, args.last)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    for sport, sec in res["sports"].items():
        print(sport, {k: v for k, v in sec.items()
                      if k not in ("wrong", "decoy_accepted", "recovered")})
        for w in sec["wrong"]:
            print("  WRONG", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
