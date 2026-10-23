#!/usr/bin/env python3
"""P3 / K7 of the coverage audit 2026-10-23 (B1), football part: a thin
footballer's starts for other teams, found by player id
(epochs.PLAYER_HISTORY_ANY_TEAM_FROM_UTC). Read-only evidence.

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p3_any_team_football.py \\
        --db-path data/refit_2026-10-23_allin/sofa_copy.db \\
        --from 2026-08-01 --to 2026-10-20 \\
        [--json-out rows.json]

The history replay of measure_player_coverage.window (starts only, his
starts in the side's newest matches, match_player per squad, the side found
more often, the installed curve through Calibration.realised, p as the
replay prices it - the sample mean, no share / stretch, for every group
alike). Per starter of a finished target match and lineup metric:

  BASE - >= min_sample starts in the side's newest sample_n: today's row;
  ANY  - fewer than min_sample starts in the side's newest 20 (the coverage
         window fails), topped up with his starts for PEER teams (opponents
         in the side's sample proper - its newest sample_n; each peer's
         matches through samples.peer_history, the live acceptance, one row
         per (match, peer), a provisional statistics row read as none),
         matched by his Sofascore player id (samples.any_team_sample), newest
         sample_n, at least min_sample. His id and the matches excluded from
         the top-up come from the window live reads him over: the 20 when
         they hold more of his starts than the 10, else the 10
         (samples.coverage_player_samples, `used`).

Histories are built with the coverage audit's sample rules as live from
2026-10-24 (finish_history conflict_cut, CONFLICT_CUT_FRIENDLY_IDS).

Reported per market / direction on rows at confidence >= 0.70: realised
minus confidence with a match bootstrap, ANY minus BASE; and how many
thin starters the peers reach at all.
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bet.sofa.cache import is_provisional  # noqa: E402
from bet.sofa.confidence import Calibration, calibration_path_for  # noqa: E402
from bet.sofa.contracts import GapReason  # noqa: E402
from bet.sofa.listing_index import entity_indexed_events  # noqa: E402
from bet.sofa.players import (  # noqa: E402
    extract_player_metric,
    match_player,
    player_id_of,
    squad_statistics,
    started,
)
from bet.sofa.samples import (  # noqa: E402
    CONFLICT_CUT_FRIENDLY_IDS,
    PEER_LISTING_LIMIT,
    _competition_id,
    finish_history,
    peer_history,
)
from bet.sofa.settle import settle  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402
from scripts.sofa import measure_player_coverage as mpc  # noqa: E402

METRICS = ("player_shots_for", "player_shots_on_target_for", "player_fouls_for",
           "player_tackles_for", "player_assists_for", "player_offsides_for")
SAMPLE_N = 10
MIN_SAMPLE = 5
WIDE_N = 20
FLOOR = 0.70


def run(db: str, lo: str, hi: str, runs_dir: Path) -> tuple[list[dict[str, Any]],
                                                            dict[str, int]]:
    cal = Calibration.load(calibration_path_for(hi))
    ladder = {m: v for m, v in cfc.printed_player_ladder(runs_dir).items()
              if m in METRICS}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    lo_ts = int(datetime.fromisoformat(lo).replace(tzinfo=UTC).timestamp())
    hi_ts = int(datetime.fromisoformat(hi).replace(tzinfo=UTC).timestamp()) + 86400
    targets = mpc._targets(con, lo_ts, hi_ts)
    print(f"targets {len(targets)}", file=sys.stderr)
    cache: collections.OrderedDict[tuple[int, bool], dict[bool, Any]] = (
        collections.OrderedDict())
    counts: collections.Counter[str] = collections.Counter()
    at = datetime.now(UTC)

    def squads_of(event_id: int, kickoff_ts: int | None = None) -> dict[bool, Any]:
        """Both squads; with ``kickoff_ts`` a provisional statistics row is
        read as none (cache.get_event_stats(kickoff_ts=...), the peers')."""
        key = (event_id, kickoff_ts is not None)
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        found = con.execute(
            "SELECT statistics_json, lineups_json, fetched_at FROM sofa_event_stats "
            "WHERE sofascore_event_id = ?", (event_id,)).fetchone()
        stats = json.loads(found[0]) if found and found[0] else None
        if (found and kickoff_ts is not None
                and is_provisional(found[0], found[2], kickoff_ts, at)):
            stats = None
        lineups = json.loads(found[1]) if found and found[1] else None
        both = {h: squad_statistics(lineups, is_home=h, statistics=stats,
                                    player_id=True) for h in (True, False)}
        cache[key] = both
        if len(cache) > 40_000:
            cache.popitem(last=False)
        return both

    def history_of(entity: int, kickoff: int, comp: int | None,
                   event: dict[str, Any], n: int) -> list[dict[str, Any]]:
        admitted = [
            p for p in entity_indexed_events(con, entity, "last", kickoff,
                                             cfc.PLAYER_HISTORY_LISTED)
            if cfc.admitted_football_event(p, entity, kickoff)
            and not cfc.is_same_match(p, event)
            and _competition_id(p) not in CONFLICT_CUT_FRIENDLY_IDS
        ]
        return finish_history(admitted, entity, "football", comp, kickoff, n,
                              conflict_cut=True)

    def peer_squads(own: int, recent: list[dict[str, Any]], kickoff: int,
                    exclude: set[int]) -> list[tuple[int, int, Any]]:
        peers: list[int] = []
        for past in recent:
            h = (past.get("homeTeam") or {}).get("id")
            a = (past.get("awayTeam") or {}).get("id")
            other = a if h == own else h
            if isinstance(other, int) and other != own and other not in peers:
                peers.append(other)
        out: list[tuple[int, int, Any]] = []
        seen: set[tuple[int, int]] = set()
        for peer in peers:
            listed = entity_indexed_events(con, peer, "last", kickoff,
                                           PEER_LISTING_LIMIT)
            for ev in peer_history(listed, peer, kickoff, conflict_cut=True):
                eid = int(ev["id"])
                start = int(ev["startTimestamp"])
                if eid in exclude or (eid, peer) in seen:
                    continue
                seen.add((eid, peer))
                home = (ev.get("homeTeam") or {}).get("id") == peer
                sq = squads_of(eid, start)[home]
                if sq:
                    out.append((eid, start, sq))
        return out

    out: list[dict[str, Any]] = []
    for k, event in enumerate(targets):
        if k % 500 == 0:
            print(f"{k}/{len(targets)} rows {len(out)} {dict(counts)}",
                  file=sys.stderr, flush=True)
        kickoff = int(event["startTimestamp"])
        comp = _competition_id(event)
        hist: dict[bool, list[tuple[int, int, Any]]] = {}
        recent_of: dict[bool, list[dict[str, Any]]] = {}
        proper_of: dict[bool, list[dict[str, Any]]] = {}
        entity_of: dict[bool, int] = {}
        for is_home in (True, False):
            entity = int(((event.get("homeTeam" if is_home else "awayTeam"))
                          or {}).get("id") or 0)
            entity_of[is_home] = entity
            recent = history_of(entity, kickoff, comp, event, WIDE_N)
            recent_of[is_home] = recent
            proper_of[is_home] = history_of(entity, kickoff, comp, event,
                                            SAMPLE_N)
            hist[is_home] = [
                (idx, int(past["id"]),
                 squads_of(int(past["id"]))[
                     (past.get("homeTeam") or {}).get("id") == entity])
                for idx, past in enumerate(recent)
            ]
        target = squads_of(int(event["id"]))
        both = set(target.get(True) or {}) & set(target.get(False) or {})
        peers_cache: dict[tuple[bool, bool], list[tuple[int, int, Any]]] = {}
        for is_home in (True, False):
            squad = target.get(is_home)
            if not squad:
                continue
            for name, stats in sorted(squad.items()):
                if stats.get("minutesPlayed") is None or started(stats) is False:
                    continue
                if name in both:
                    continue
                matched = {s: [(idx, eid, sq, match_player(name, sq) if sq else None)
                               for idx, eid, sq in h] for s, h in hist.items()}
                for metric, lines in ladder.items():
                    actual = extract_player_metric(metric, stats)
                    if isinstance(actual, GapReason):
                        continue
                    vals: dict[bool, list[tuple[int, int, float]]] = {}
                    for s, items in matched.items():
                        got = []
                        for idx, eid, sq, key in items:
                            if key is None or started(sq[key]) is False:
                                continue
                            v = extract_player_metric(metric, sq[key],
                                                      woodwork_once=True)
                            if not isinstance(v, GapReason):
                                got.append((idx, eid, v))
                        vals[s] = got
                    n10 = {s: sum(1 for i, _, _ in v if i < SAMPLE_N)
                           for s, v in vals.items()}
                    n20 = {s: len(v) for s, v in vals.items()}
                    group: str | None = None
                    sample: list[float] = []
                    if (n10[True] != n10[False]
                            and (n10[True] > n10[False]) == is_home
                            and n10[is_home] >= MIN_SAMPLE):
                        group = "BASE"
                        sample = [v for i, _, v in vals[is_home] if i < SAMPLE_N]
                    elif (n20[is_home] > n20[not is_home]
                          and n20[is_home] < MIN_SAMPLE):
                        counts[f"thin:{metric}"] += 1
                        # live reads him over the 20 only when they hold more
                        # of his starts than the 10 (coverage_player_samples)
                        wide = n20[is_home] > n10[is_home]
                        scope = SAMPLE_N if not wide else WIDE_N
                        ids = {player_id_of(sq[key]) for idx, _, sq, key in
                               matched[is_home]
                               if key is not None and idx < scope}
                        ids.discard(None)
                        if len(ids) != 1:
                            continue
                        pid = next(iter(ids))
                        if (is_home, wide) not in peers_cache:
                            own_ids = {int(p["id"]) for p in (
                                recent_of[is_home] if wide
                                else proper_of[is_home])}
                            peers_cache[(is_home, wide)] = peer_squads(
                                entity_of[is_home], proper_of[is_home],
                                kickoff, own_ids | {int(event["id"])})
                        foreign: list[tuple[int, float]] = []
                        taken: set[int] = set()
                        for f_eid, start, sq in peers_cache[(is_home, wide)]:
                            if f_eid in taken:
                                continue
                            hits = [st for st in sq.values()
                                    if player_id_of(st) == pid]
                            if len(hits) != 1:
                                continue
                            v = extract_player_metric(metric, hits[0],
                                                      woodwork_once=True)
                            if isinstance(v, GapReason) or started(hits[0]) is False:
                                continue
                            taken.add(f_eid)
                            foreign.append((start, v))
                        own = [(int(recent_of[is_home][i]["startTimestamp"]), v)
                               for i, _, v in vals[is_home]
                               if wide or i < SAMPLE_N]
                        merged = sorted(own + foreign, reverse=True)[:SAMPLE_N]
                        if not foreign:
                            continue
                        counts[f"peer_found:{metric}"] += 1
                        if len(merged) < MIN_SAMPLE:
                            continue
                        group = "ANY"
                        sample = [v for _, v in merged]
                    if group is None:
                        continue
                    for line in lines:
                        for direction in mpc.DIRECTIONS:
                            p = mpc._p(metric, sample, line, direction)
                            if p is None:
                                continue
                            outcome = settle(actual, line, direction)
                            if outcome not in ("WIN", "LOSS"):
                                continue
                            hit = cal.realised(metric, p, "football", direction,
                                               None)
                            out.append({
                                "event_id": int(event["id"]), "market": metric,
                                "direction": direction, "line": line,
                                "group": group, "n": len(sample), "p": p,
                                "confidence": None if hit is None else float(hit[0]),
                                "won": outcome == "WIN"})
    con.close()
    return out, dict(counts)


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    printable = [r for r in rows if r["confidence"] is not None
                 and r["confidence"] >= FLOOR]
    res: dict[str, Any] = {
        "rows": dict(collections.Counter(r["group"] for r in rows)),
        "printable": dict(collections.Counter(r["group"] for r in printable)),
        "any_players_matches": len({r["event_id"] for r in rows
                                    if r["group"] == "ANY"}),
    }
    keys = sorted({(r["market"], r["direction"]) for r in printable})
    for key in [*keys, ("ALL", "ALL")]:
        scope = [r for r in printable
                 if key == ("ALL", "ALL") or (r["market"], r["direction"]) == key]
        g = [r for r in scope if r["group"] == "ANY"]
        b = [r for r in scope if r["group"] == "BASE"]
        if not g:
            continue
        entry: dict[str, Any] = {"any_rows": len(g),
                                 "any_matches": len({r["event_id"] for r in g}),
                                 "any_gap": [round(x, 4) for x in mpc._boot_gap(g)]}
        if b:
            entry["base_rows"] = len(b)
            entry["base_gap"] = [round(x, 4) for x in mpc._boot_gap(b)]
            entry["any_minus_base"] = [round(x, 4) for x in mpc._boot_diff(g, b)]
        res[f"{key[0]}|{key[1]}"] = entry
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--from", dest="lo", default="2026-08-01")
    ap.add_argument("--to", dest="hi", default="2026-10-20")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs" / "sofa"))
    ap.add_argument("--json-out")
    ap.add_argument("--rows-in")
    args = ap.parse_args()
    if args.rows_in:
        doc = json.loads(Path(args.rows_in).read_text())
        rows, counts = doc["rows"], doc["counts"]
    else:
        rows, counts = run(args.db_path, args.lo, args.hi, Path(args.runs_dir))
        if args.json_out:
            Path(args.json_out).write_text(json.dumps({"rows": rows,
                                                       "counts": counts}))
    print(json.dumps({"counts": counts, **report(rows)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
