#!/usr/bin/env python3
"""RESOLVE searched anchor: precision backtest (read-only evidence).

The rule under test (resolve.searched_anchor_event +
resolve.searched_anchor_agreement, epochs.FOOTBALL_SEARCHED_ANCHOR_FROM_UTC):
a football board side that is not a verified entity is searched; when one of
its fitting candidates whose own name is the side's (`part_score` >= 90,
same squad level and unmarked "2 / C" word) plays the ONLY game within 60 min
of Superbet's start (two games of two candidates refuse), the game reads the
way Superbet orders the sides, has the board's gender, is not postponed and
its other side is of the opponent's squad level, the game is accepted unless
the opponent's own search names a DIFFERENT team strongly (veto), when that
search lands on the other side (MUTUAL), or `part_score` >= 65, or a shared
distinctive word with both clocks within 15 minutes. The sweep table shows
the opponent rule at other scores, with and without the veto.

Measured on every bridged football fixture of RESOLVE (02_fixtures.json with
its 01_board.json entry), each side in turn as the searched one:

- candidates: the side's true Sofascore team (the bridged event's) plus every
  other team of the listings in the database whose name is the side's
  (`part_score` > 82, `candidate_fits`) - a stand-in for the 3 search results,
  since a search is not cached (impostors make it stricter, never looser);
- HIDDEN: the event choice alone (the opponent's name not read);
- TRUE: the whole rule with the board's own opponent (its own search stood in
  by its true team when that team's name is the opponent's, plus impostors);
- DECOY: the opponent's name replaced by up to 3 other board sides of the same
  Superbet tournament and day (else category) that are bridged and not in the
  game - a wrong-opponent case (Kelantan - Imigresen); every accept is a
  wrong identity. Reported without the veto (names only) and with it (the
  decoy's own search stood in by its true team when its name is strong).

`--gap-diag` / `--gap-classes` (optional, the 2026-10-21 live search replay
of RESOLVE's gaps) run the rule on real search results: F1 recall and the
hazards (Sutton Coldfield Town, Kelantan Red Warrior must be refused).

Events: sofa_listed_event and the cached sofa_entity_events pages of the true
teams, each event its most recently fetched version.

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_searched_anchor.py \
      [--from 2026-10-05] [--to 2026-10-20] [--json-out f] \
      [--gap-diag replay.jsonl --gap-classes final2.json]
"""

from __future__ import annotations

import argparse
import glob
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

from rapidfuzz import fuzz, process  # noqa: E402

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.resolve import (  # noqa: E402
    NAME_MATCH_THRESHOLD,
    _name_parts,
    candidate_fits,
    part_score,
    searched_anchor_agreement,
    searched_anchor_event,
    shadow_opponent_agrees,
    split_match_name,
)

Event = dict[str, Any]
GAP_CLASSES = ("F:OPP_NAME", "F:OPPONENT_DIFFERS")


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC)


def load_bridged(runs: Path, first: str, last: str) -> list[dict[str, Any]]:
    """One row per Superbet football event bridged by RESOLVE (latest run)."""
    board: dict[str, dict[str, Any]] = {}
    for p in sorted(glob.glob(str(runs / "*" / "01_board.json"))):
        for e in json.loads(Path(p).read_text()):
            if e.get("sport") == "football":
                board[str(e["superbet_event_id"])] = e
    rows: dict[str, dict[str, Any]] = {}
    for p in sorted(glob.glob(str(runs / "*" / "02_fixtures.json"))):
        day = Path(p).parent.name
        if day < first or day > last:
            continue
        for f in json.loads(Path(p).read_text()):
            if f.get("sport") != "football":
                continue
            for sb in f["superbet_event_ids"]:
                b = board.get(str(sb))
                if b is None:
                    continue
                a, bb = split_match_name(b["match_name"])
                if not a or not bb:
                    a, bb = b["side_a"], b["side_b"]
                rows[str(sb)] = {
                    "sb": str(sb), "day": day, "side_a": a, "side_b": bb,
                    "kickoff": _ts(str(b["kickoff_utc"])),
                    "tournament_id": b.get("tournament_id"),
                    "category_id": b.get("category_id"),
                    "event_id": int(f["sofascore_event_id"]),
                    "home_id": int(f["home_entity_id"]),
                    "away_id": int(f["away_entity_id"]),
                    "home_name": f["home_name"], "away_name": f["away_name"],
                }
    return list(rows.values())


def load_events(
    conn: sqlite3.Connection, lo: int, hi: int, team_ids: set[int]
) -> dict[int, Event]:
    """Event id -> its most recently fetched version, start in [lo, hi]."""
    events: dict[int, Event] = {}
    fetched: dict[int, str] = {}

    def add(e: Event, at: str) -> None:
        eid, ts = e.get("id"), e.get("startTimestamp")
        if not isinstance(eid, int) or not isinstance(ts, int):
            return
        if not lo <= ts <= hi:
            return
        if ((e.get("tournament") or {}).get("category") or {}).get(
                "sport", {}).get("slug", "football") != "football":
            return
        if fetched.get(eid, "") > at:
            return
        fetched[eid] = at
        events[eid] = e

    for sport, at, txt in conn.execute(
        "SELECT sport, fetched_at, event_json FROM sofa_listed_event "
        "WHERE start_ts BETWEEN ? AND ?", (lo, hi)
    ):
        if sport == "football":
            add(json.loads(txt), str(at))
    ids = sorted(team_ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        for at, txt in conn.execute(
            "SELECT fetched_at, events_json FROM sofa_entity_events "
            f"WHERE sofascore_entity_id IN ({marks})", chunk
        ):
            try:
                page = json.loads(txt).get("events") or []
            except (ValueError, AttributeError):
                continue
            for e in page:
                add(e, str(at))
    return events


def _strip(norm: str) -> str:
    return _name_parts(norm)[0] if _name_parts(norm) else norm


class World:
    """Listings by team and the name index the impostors come from."""

    def __init__(self, events: dict[int, Event]) -> None:
        self.by_team: dict[int, list[Event]] = defaultdict(list)
        self.team: dict[int, dict[str, Any]] = {}
        for e in events.values():
            for key in ("homeTeam", "awayTeam"):
                t = e.get(key) or {}
                if isinstance(t.get("id"), int):
                    self.by_team[t["id"]].append(e)
                    self.team.setdefault(t["id"], t)
        self.names: list[str] = []
        self.name_ids: list[list[int]] = []
        seen: dict[str, int] = {}
        for tid, t in self.team.items():
            n = _strip(normalize_name(str(t.get("name") or "")))
            if not n:
                continue
            if n not in seen:
                seen[n] = len(self.names)
                self.names.append(n)
                self.name_ids.append([])
            self.name_ids[seen[n]].append(tid)
        self._imp: dict[str, list[int]] = {}

    def prepare_impostors(self, sides: set[str]) -> None:
        queries = sorted(sides)
        stripped = [_strip(normalize_name(s)) for s in queries]
        found: dict[int, set[int]] = defaultdict(set)
        for scorer in (fuzz.token_set_ratio, fuzz.ratio):
            m = process.cdist(stripped, self.names, scorer=scorer,
                              score_cutoff=NAME_MATCH_THRESHOLD - 10, workers=-1)
            for qi, ni in zip(*m.nonzero(), strict=True):
                found[int(qi)].add(int(ni))
        for qi, side in enumerate(queries):
            norm = normalize_name(side)
            ids: list[int] = []
            for ni in sorted(found.get(qi, ())):
                for tid in self.name_ids[ni]:
                    t = self.team[tid]
                    if (part_score(norm, normalize_name(str(t.get("name") or "")))
                            > NAME_MATCH_THRESHOLD
                            and candidate_fits(norm, t, "football")):
                        ids.append(tid)
            self._imp[side] = ids

    def impostors(self, side: str, true_id: int) -> list[int]:
        return [t for t in self._imp.get(side, []) if t != true_id]

    def entity(self, tid: int, fallback: str = "") -> dict[str, Any]:
        t = self.team.get(tid) or {}
        return {"id": tid, "name": t.get("name") or fallback,
                "gender": t.get("gender")}


# Every anchored game's opponent evidence, by population, for the sweep.
DETAILS: dict[str, list[dict[str, Any]]] = defaultdict(list)
SWEEP_SCORES = (50.0, 60.0, 65.0, 70.0, 75.0, 82.0)


def agreement_detail(
    e: Event, cand: dict[str, Any], ko: datetime, side: str, opponent: str,
    opp_cands: list[dict[str, Any]],
) -> dict[str, Any]:
    """The pieces `searched_anchor_agreement` decides on, kept apart."""
    norm_side, norm_opp = normalize_name(side), normalize_name(opponent)
    home_id = (e.get("homeTeam") or {}).get("id")
    other_key = "awayTeam" if home_id == cand.get("id") else "homeTeam"
    own_key = "homeTeam" if other_key == "awayTeam" else "awayTeam"
    other_id = (e.get(other_key) or {}).get("id")
    other = normalize_name((e.get(other_key) or {}).get("name") or "")
    own = normalize_name((e.get(own_key) or {}).get("name") or "")
    gap = abs(int(e.get("startTimestamp") or 0) - ko.timestamp())
    return {
        "mutual": any(oc.get("id") == other_id for oc in opp_cands),
        "veto": any(oc.get("id") != other_id and (oc.get("verified") or part_score(
            norm_opp, normalize_name(oc.get("name") or "")) > NAME_MATCH_THRESHOLD)
            for oc in opp_cands),
        "score": round(part_score(norm_opp, other), 1),
        "sw": shadow_opponent_agrees(norm_opp, other, gap, norm_side, own),
    }


def accepts(d: dict[str, Any], score: float, shared_word: bool, veto: bool) -> bool:
    if veto and d["veto"]:
        return False
    if d["mutual"]:
        return True
    return bool(d["score"] >= score or (shared_word and d["sw"]))


def sweep_table() -> list[str]:
    lines = ["| opponent rule | " + " | ".join(DETAILS) + " |",
             "|---|" + "---|" * len(DETAILS)]
    for sw in (True, False):
        for t in SWEEP_SCORES:
            for veto in (True, False):
                cells = [str(sum(accepts(d, t, sw, veto) for d in ds))
                         + f"/{len(ds)}" for ds in DETAILS.values()]
                lines.append(f"| score >= {t:g}{' or shared word' if sw else ''}"
                             f"{' + veto' if veto else ''} | " + " | ".join(cells)
                             + " |")
    return lines


def run_rule(
    world: World, row: dict[str, Any], searched_is_a: bool, opponent: str,
    opp_cands: list[dict[str, Any]] | None, population: str = "",
) -> tuple[str, int | None, str | None]:
    """(outcome, picked event id, agreement); opp_cands None = name hidden."""
    side = row["side_a"] if searched_is_a else row["side_b"]
    true_id = row["home_id"] if searched_is_a else row["away_id"]
    true_name = row["home_name"] if searched_is_a else row["away_name"]
    ids = [true_id, *world.impostors(side, true_id)]
    cands = [(world.entity(t, true_name if t == true_id else ""), world.by_team[t])
             for t in ids]
    got = searched_anchor_event(cands, row["kickoff"], side, opponent,
                                row["side_a"], row["side_b"])
    if got is None:
        return "NONE", None, None
    cand, e = got
    if opp_cands is None:
        return "PICK", int(e["id"]), None
    how = searched_anchor_agreement(e, cand, row["kickoff"], side, opponent,
                                    opp_cands)
    if population:
        d = agreement_detail(e, cand, row["kickoff"], side, opponent, opp_cands)
        d["right_event"] = int(e["id"]) == row["event_id"]
        DETAILS[population].append(d)
    if how is None:
        return "REFUSED_OPPONENT", int(e["id"]), None
    return "PICK", int(e["id"]), how


def opponent_search_standin(
    world: World, name: str, true_id: int | None, true_name: str
) -> list[dict[str, Any]]:
    """The opponent's own search, stood in: its true team when its name is
    the board's, plus the impostors (both strong by construction)."""
    out: list[dict[str, Any]] = []
    norm = normalize_name(name)
    if true_id is not None and part_score(norm, normalize_name(true_name)) \
            > NAME_MATCH_THRESHOLD:
        out.append(world.entity(true_id, true_name))
    for t in world.impostors(name, true_id or -1):
        out.append(world.entity(t))
    return out


def bridged_backtest(world: World, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_group: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_group[(r["day"], r["tournament_id"])].append(r)
        by_group[(r["day"], ("cat", r["category_id"]))].append(r)
    res: Counter[str] = Counter()
    wrong: list[dict[str, Any]] = []
    decoy_acc: list[dict[str, Any]] = []
    for r in rows:
        in_event = {r["home_id"], r["away_id"]}
        for searched_is_a in (True, False):
            side = r["side_a"] if searched_is_a else r["side_b"]
            opp = r["side_b"] if searched_is_a else r["side_a"]
            opp_id = r["away_id"] if searched_is_a else r["home_id"]
            opp_name = r["away_name"] if searched_is_a else r["home_name"]
            res["sides"] += 1
            for label, oc in (
                ("hidden", None),
                ("true", opponent_search_standin(world, opp, opp_id, opp_name)),
            ):
                out, eid, how = run_rule(world, r, searched_is_a, opp, oc,
                                         "bridged, true opponent" if oc is not None
                                         else "")
                if out == "PICK":
                    ok = eid == r["event_id"]
                    res[f"{label}:{'correct' if ok else 'WRONG'}"] += 1
                    if ok and how:
                        res[f"{label}:agree:{how}"] += 1
                    if not ok:
                        wrong.append({"variant": label, "side": side, "opp": opp,
                                      "kickoff": r["kickoff"].isoformat(),
                                      "bridged": r["event_id"], "picked": eid})
                else:
                    res[f"{label}:{out}"] += 1
            # Decoys: other bridged board sides of the same tournament / day.
            pool = [x for x in by_group[(r["day"], r["tournament_id"])]
                    if x["sb"] != r["sb"]]
            src = "tournament"
            if not pool:
                pool = [x for x in by_group[(r["day"], ("cat", r["category_id"]))]
                        if x["sb"] != r["sb"]]
                src = "category"
            decoys: list[tuple[str, int, str]] = []
            for x in sorted(pool, key=lambda x: x["sb"]):
                for dn, di, dname in ((x["side_a"], x["home_id"], x["home_name"]),
                                      (x["side_b"], x["away_id"], x["away_name"])):
                    if di in in_event or normalize_name(dn) in (
                            normalize_name(side), normalize_name(opp)):
                        continue
                    decoys.append((dn, di, dname))
            for dn, di, dname in decoys[:3]:
                res[f"decoy[{src}]:tried"] += 1
                for label, oc in (
                    ("noveto", []),
                    ("veto", opponent_search_standin(world, dn, di, dname)),
                ):
                    out, eid, how = run_rule(
                        world, r, searched_is_a, dn, oc,
                        "decoy opponent" if label == "veto" else "")
                    res[f"decoy:{label}:{out}"] += 1
                    if out == "PICK":
                        res[f"decoy:{label}:agree:{how}"] += 1
                        if label == "veto":
                            decoy_acc.append({"side": side, "true_opp": opp,
                                              "decoy": dn, "how": how,
                                              "event": eid})
    return {"counts": dict(sorted(res.items())), "wrong": wrong,
            "decoy_accepts_with_veto": decoy_acc}


def _diag_event(e: dict[str, Any], ko: datetime) -> Event:
    g = "F" if e.get("gender") == "W" else "M"
    return {
        "id": e["id"],
        "startTimestamp": int(ko.timestamp()) + 60 * int(e["dt_min"]),
        "status": {"type": e.get("status")},
        "homeTeam": {"id": e["home_id"], "name": e["home"], "gender": g},
        "awayTeam": {"id": e["away_id"], "name": e["away"], "gender": g},
        "tournament": {"name": e.get("tournament") or ""},
    }


def _diag_cands(d: dict[str, Any], ko: datetime) -> list[tuple[dict[str, Any],
                                                                list[Event]]]:
    out: dict[int, tuple[dict[str, Any], list[Event]]] = {}
    for q in d.get("queries") or []:
        for t in q.get("teams") or []:
            if not t.get("fits") or (t.get("fit_rank") or 99) > 3:
                continue
            ent = {"id": t["id"], "name": t["name"],
                   "gender": "F" if t.get("gender") == "F" else t.get("gender")}
            out.setdefault(t["id"], (ent, [_diag_event(e, ko)
                                           for e in t.get("near") or []]))
    return list(out.values())


def gap_backtest(diag_path: Path, classes_path: Path) -> list[dict[str, Any]]:
    cls = {x["id"]: x for x in json.loads(classes_path.read_text())}
    out: list[dict[str, Any]] = []
    for line in diag_path.read_text().splitlines():
        r = json.loads(line)
        c = cls.get(r["id"])
        if not c or c["final"] not in GAP_CLASSES:
            continue
        ko = _ts(r["kickoff"])
        a, b = split_match_name(r["match"])
        diag = {d["side"]: d for d in r.get("diag") or []}
        verdict: dict[str, Any] = {"id": r["id"], "match": r["match"],
                                   "class": c["final"], "started": c.get("started"),
                                   "pick": None, "how": None, "why": []}
        for side, opp in ((a, b), (b, a)):
            cands = _diag_cands(diag.get(side) or {}, ko)
            got = searched_anchor_event(cands, ko, side, opp, a, b)
            if got is None:
                verdict["why"].append(f"{side}: no single anchored game")
                continue
            cand, e = got
            opp_c = [ent for ent, _ in _diag_cands(diag.get(opp) or {}, ko)]
            how = searched_anchor_agreement(e, cand, ko, side, opp, opp_c)
            d = agreement_detail(e, cand, ko, side, opp, opp_c)
            d["match"] = r["match"]
            DETAILS["hazard" if c["final"] == "F:OPPONENT_DIFFERS"
                    else "F1 gap"].append(d)
            if how is None:
                verdict["why"].append(
                    f"{side}: {e['id']} {e['homeTeam']['name']} - "
                    f"{e['awayTeam']['name']} refused on the opponent")
                continue
            verdict.update(pick=e["id"], how=how, via=side,
                           game=f"{e['homeTeam']['name']} - {e['awayTeam']['name']}")
            break
        out.append(verdict)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--from", dest="first", default="2026-10-05")
    ap.add_argument("--to", dest="last", default="2026-10-20")
    ap.add_argument("--json-out")
    ap.add_argument("--gap-diag")
    ap.add_argument("--gap-classes")
    args = ap.parse_args(argv)
    cfg = SofaConfig.from_env()
    runs = Path(cfg.runs_dir)
    conn = sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True)
    rows = load_bridged(runs, args.first, args.last)
    lo = int((_ts(args.first + "T00:00:00Z") - timedelta(days=2)).timestamp())
    hi = int((_ts(args.last + "T00:00:00Z") + timedelta(days=3)).timestamp())
    ids = {r["home_id"] for r in rows} | {r["away_id"] for r in rows}
    world = World(load_events(conn, lo, hi, ids))
    world.prepare_impostors({r["side_a"] for r in rows} | {r["side_b"] for r in rows})
    report: dict[str, Any] = {"from": args.first, "to": args.last,
                              "fixtures": len(rows)}
    report["bridged"] = bridged_backtest(world, rows)
    if args.gap_diag and args.gap_classes:
        report["gaps"] = gap_backtest(Path(args.gap_diag), Path(args.gap_classes))
    print(f"bridged football fixtures {args.first}..{args.last}: {len(rows)}")
    for k, v in report["bridged"]["counts"].items():
        print(f"  {k}: {v}")
    for w in report["bridged"]["wrong"]:
        print(f"  WRONG {w}")
    for w in report["bridged"]["decoy_accepts_with_veto"]:
        print(f"  DECOY ACCEPTED {w}")
    for g in report.get("gaps", []):
        print(f"  GAP {g['class']} {g['match']}: "
              + (f"PICK {g['pick']} {g.get('game')} ({g['how']})" if g["pick"]
                 else "refused - " + "; ".join(g["why"])))
    print("\n".join(sweep_table()))
    report["sweep"] = sweep_table()
    report["details"] = DETAILS
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
