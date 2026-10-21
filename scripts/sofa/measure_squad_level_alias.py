#!/usr/bin/env python3
"""RESOLVE squad-level alias: precision backtest and F2 recall (read-only).

The rule under test (resolve.squad_level_alias_event,
epochs.FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC): when nothing matched a football
pair by name, the searched candidates' listings plus up to 3 search results
of an alias level (`squad_alias_candidate`) are read for the ONE game within
60 min of Superbet's start whose two sides are the board's two sides by name
with the level words removed (`level_free_name`, `part_score` > 82 each) and
by one pair-consistent level shift (`squad_level_shift`: U19 <-> U20 one year
apart, a reserve side <-> U19..U23, Sofascore's trailing "2" = reserve; never
the senior squad; both board sides below senior must shift alike; the
searched side's own name >= 90), F25 order, board gender, not postponed. Two
such games refuse. The game is vetoed when a team the opponent's own search
names (stood in here by the opponent's true team and its namesakes) plays
another game within 60 min (`squad_alias_veto`); a vetoed game is counted
apart, right or wrong.

Precision on RESOLVE's bridged football fixtures (02_fixtures.json with the
01_board.json entry, as scripts/sofa/measure_searched_anchor.py loads them),
each side in turn as the searched one. Candidates = the side's true team
(only when RESOLVE could hold it: `candidate_fits` or `squad_alias_candidate`)
plus every other team of the database's listings that the alias would take
(`squad_alias_candidate`: same club by name, alias-able level - the club's
other youth / reserve squads, the collision the rule must refuse):

- AS_IS: the board's own names;
- SHIFTED: both sides of a youth / reserve fixture relabelled on the board to
  every level the alias lets name the Sofascore level ("Roma U19 - Lazio U19"
  played as "Roma U20 - Lazio U20", "Roma U18 - ...", "Roma II - ..."): the
  situation the rule exists for, the true game the only right answer;
- ONE_SIDED: a fixture of a youth / reserve side against a senior side, the
  non-senior side relabelled likewise;
- HALF_SHIFTED: only one of two non-senior sides relabelled - must refuse
  (pair consistency), a pick is counted;
- DECOY: SHIFTED with the opponent replaced by up to 3 other bridged board
  sides of the same Superbet tournament and day (relabelled the same way):
  every accept is a wrong identity. Beside it, the ordinary name gate
  (`SofaResolver.match_quality`) on the same decoys with the board
  unshifted - the rate production already runs at.

Recall (--gap-diag replay.jsonl --gap-classes final2.json, the 2026-10-21
live search replay of RESOLVE's gaps): the F:LEVEL_MAP entries through the
rule on the real search results, side A then side B as RESOLVE asks; a pick
is compared with the game the replay names. `--loose` also reports the
variant without pair consistency (each side alias-able on its own).

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_squad_level_alias.py \\
      [--from 2026-10-05] [--to 2026-10-20] [--db-path data/sofa.db] \\
      [--runs-dir runs/sofa] [--json-out f] \\
      [--gap-diag replay.jsonl --gap-classes final2.json] [--loose]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from rapidfuzz import fuzz, process  # noqa: E402

import bet.sofa.resolve as resolve  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.resolve import (  # noqa: E402
    NAME_MATCH_THRESHOLD,
    SofaResolver,
    candidate_fits,
    football_squad_levels,
    level_free_name,
    part_score,
    split_match_name,
    squad_alias_candidate,
    squad_alias_veto,
    squad_level_alias,
    squad_level_alias_event,
)
from scripts.sofa.measure_searched_anchor import (  # noqa: E402
    _diag_event,
    _ts,
    load_bridged,
    load_events,
)

Event = dict[str, Any]
GAP_CLASS = "F:LEVEL_MAP"
LEVELS = ("R", "U17", "U18", "U19", "U20", "U21", "U22", "U23")
SENIOR = frozenset({"S"})

_WOMEN_SUFFIX = re.compile(r"\s*\((?:k|w|f)\)\s*$", re.IGNORECASE)
_RAW_LEVEL = re.compile(
    r"\s*\(r\)\s*$|\s+(?:ii|b|reserves?|u-?\d{2}|2)\s*$", re.IGNORECASE)


def relabel(raw: str, level: str) -> str:
    """The board name with its level marker replaced by `level` ("R" is
    written "II"); the women's marker kept."""
    women = _WOMEN_SUFFIX.search(raw)
    base = raw[: women.start()] if women else raw
    while True:
        stripped = _RAW_LEVEL.sub("", base).strip()
        if stripped == base:
            break
        base = stripped
    out = f"{base} {'II' if level == 'R' else level}"
    return f"{out} {women.group(0).strip()}" if women else out


def loose_shift(norm_side: str, own: str, norm_opp: str, other: str) -> str | None:
    """The variant without pair consistency: each side alias-able alone."""
    bs, es = football_squad_levels(norm_side), football_squad_levels(own)
    bo, eo = football_squad_levels(norm_opp), football_squad_levels(other)
    if bs == SENIOR and bo == SENIOR:
        return None

    def ok(b: frozenset[str], e: frozenset[str]) -> bool:
        if b == SENIOR:
            return e == SENIOR
        return any(squad_level_alias(x, y) for x in b for y in e)

    return "LOOSE" if ok(bs, es) and ok(bo, eo) else None


@contextmanager
def shift_rule(
    rule: Callable[[str, str, str, str], str | None] | None,
) -> Iterator[None]:
    saved = resolve.squad_level_shift
    if rule is not None:
        resolve.squad_level_shift = rule  # type: ignore[assignment]
    try:
        yield
    finally:
        resolve.squad_level_shift = saved


class AliasWorld:
    """Listings by team and the alias impostors (the club's other squads)."""

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
            n = level_free_name(normalize_name(str(t.get("name") or "")))
            if not n:
                continue
            if n not in seen:
                seen[n] = len(self.names)
                self.names.append(n)
                self.name_ids.append([])
            self.name_ids[seen[n]].append(tid)
        self._near: dict[str, list[int]] = {}

    def prepare(self, sides: set[str]) -> None:
        """For every level-free board name, the teams whose level-free name is
        near it (the alias filter itself runs per relabelled name)."""
        queries = sorted({level_free_name(normalize_name(s)) for s in sides} - {""})
        found: dict[int, set[int]] = defaultdict(set)
        for scorer in (fuzz.token_set_ratio, fuzz.ratio):
            m = process.cdist(queries, self.names, scorer=scorer,
                              score_cutoff=NAME_MATCH_THRESHOLD - 10, workers=-1)
            for qi, ni in zip(*m.nonzero(), strict=True):
                found[int(qi)].add(int(ni))
        for qi, q in enumerate(queries):
            self._near[q] = [tid for ni in sorted(found.get(qi, ()))
                             for tid in self.name_ids[ni]]

    def entity(self, tid: int, fallback: str = "") -> dict[str, Any]:
        t = self.team.get(tid) or {}
        return {"id": tid, "name": t.get("name") or fallback, "gender": t.get("gender")}

    def candidates(self, side: str, true_id: int, true_name: str,
                   for_veto: bool = False,
                   ) -> tuple[list[tuple[dict[str, Any], list[Event]]], bool]:
        """(candidates with listings, whether the true team is among them).
        `for_veto`: the opponent's search stood in - its same-level namesakes
        too (`candidate_fits`), as `_squad_level_alias` takes them."""
        norm = normalize_name(side)
        out: list[tuple[dict[str, Any], list[Event]]] = []
        true_ent = self.entity(true_id, true_name)
        has_true = (squad_alias_candidate(norm, true_ent)
                    or candidate_fits(norm, true_ent, "football"))
        if has_true:
            out.append((true_ent, self.by_team[true_id]))
        free = level_free_name(norm)
        for tid in self._near.get(free, []):
            if tid == true_id:
                continue
            ent = self.entity(tid)
            if squad_alias_candidate(norm, ent) or (
                    for_veto and candidate_fits(norm, ent, "football")
                    and part_score(free, level_free_name(normalize_name(
                        str(ent.get("name") or "")))) > NAME_MATCH_THRESHOLD):
                out.append((ent, self.by_team[tid]))
        return out, has_true


def run_one(world: AliasWorld, row: dict[str, Any], searched_is_a: bool,
            side_a: str, side_b: str, opp_team: tuple[int, str] | None = None,
            ) -> tuple[str, int | None, str | None]:
    """("PICK" / "VETOED" / "NONE...", event id, shift). `opp_team`: the
    board opponent's true Sofascore team (default: the bridged other side);
    its search, which the veto reads, is stood in by it and its namesakes."""
    side, opp = (side_a, side_b) if searched_is_a else (side_b, side_a)
    true_id = row["home_id"] if searched_is_a else row["away_id"]
    true_name = row["home_name"] if searched_is_a else row["away_name"]
    cands, has_true = world.candidates(side, true_id, true_name)
    got = squad_level_alias_event(cands, row["kickoff"], side, opp, side_a, side_b)
    if got is None:
        return ("NONE" if has_true else "NONE_NO_TRUE_CANDIDATE"), None, None
    if opp_team is None:
        opp_team = ((row["away_id"], row["away_name"]) if searched_is_a
                    else (row["home_id"], row["home_name"]))
    opp_cands, _ = world.candidates(opp, opp_team[0], opp_team[1], for_veto=True)
    if squad_alias_veto(got[1], row["kickoff"], opp_cands):
        return "VETOED", int(got[1]["id"]), got[2]
    return "PICK", int(got[1]["id"]), got[2]


def exact_gate(world: AliasWorld, row: dict[str, Any], searched_is_a: bool,
               side_a: str, side_b: str) -> tuple[str, int | None]:
    """The ordinary name gate (SofaResolver.match_quality, football) on the
    searched side's true team's listing - the baseline the decoys are read
    against."""
    side, opp = (side_a, side_b) if searched_is_a else (side_b, side_a)
    true_id = row["home_id"] if searched_is_a else row["away_id"]
    hits = {int(e["id"]) for e in world.by_team[true_id]
            if SofaResolver.match_quality(
                None, e, row["kickoff"], normalize_name(opp),  # type: ignore[arg-type]
                sport="football", superbet_side_a=side_a,
                superbet_side_b=side_b) is not None}
    if len(hits) == 1:
        return "PICK", next(iter(hits))
    return ("AMBIGUOUS" if hits else "NONE"), None


def _levels(name: str) -> frozenset[str]:
    return football_squad_levels(normalize_name(name))


def bridged_backtest(world: AliasWorld, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_group: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_group[(r["day"], r["tournament_id"])].append(r)
    res: Counter[str] = Counter()
    wrong: list[dict[str, Any]] = []
    shifts: Counter[str] = Counter()

    def record(pop: str, r: dict[str, Any], a: str, b: str, searched_is_a: bool,
               out: str, eid: int | None, shift: str | None,
               decoy: bool = False) -> None:
        if out == "VETOED":
            ok = eid == r["event_id"] and not decoy
            res[f"{pop}:VETOED({'right' if ok else 'wrong'} game)"] += 1
            return
        if out != "PICK":
            res[f"{pop}:{out}"] += 1
            return
        ok = eid == r["event_id"] and not decoy
        res[f"{pop}:{'correct' if ok else 'WRONG'}"] += 1
        if ok:
            shifts[f"{pop}:{shift}"] += 1
        else:
            wrong.append({"population": pop, "board": f"{a} - {b}",
                          "searched": a if searched_is_a else b,
                          "kickoff": r["kickoff"].isoformat(),
                          "bridged": r["event_id"],
                          "bridged_names": f"{r['home_name']} - {r['away_name']}",
                          "picked": eid, "shift": shift})

    for r in rows:
        lh, la = _levels(r["home_name"]), _levels(r["away_name"])
        res["fixtures"] += 1
        for searched_is_a in (True, False):
            out, eid, shift = run_one(world, r, searched_is_a, r["side_a"], r["side_b"])
            record("as_is", r, r["side_a"], r["side_b"], searched_is_a, out, eid, shift)
        if lh == SENIOR and la == SENIOR:
            continue
        both = lh != SENIOR and la != SENIOR
        res["fixtures_youth_or_reserve:" + ("both" if both else "one")] += 1
        target = (lh & la) if both else (lh if lh != SENIOR else la)
        baseline_done = False
        for level in LEVELS:
            if level in target or not any(squad_level_alias(level, t) for t in target):
                continue
            if both:
                a, b = relabel(r["side_a"], level), relabel(r["side_b"], level)
                pop = "shifted"
            elif lh != SENIOR:
                a, b, pop = relabel(r["side_a"], level), r["side_b"], "one_sided"
            else:
                a, b, pop = r["side_a"], relabel(r["side_b"], level), "one_sided"
            if (_levels(a) if (both or lh != SENIOR) else _levels(b)) != {level}:
                res[f"{pop}:relabel_failed"] += 1
                continue
            for searched_is_a in (True, False):
                out, eid, shift = run_one(world, r, searched_is_a, a, b)
                record(pop, r, a, b, searched_is_a, out, eid, shift)
            if both:
                # Only one side relabelled: pair consistency must refuse.
                for ha, hb in ((relabel(r["side_a"], level), r["side_b"]),
                               (r["side_a"], relabel(r["side_b"], level))):
                    for searched_is_a in (True, False):
                        out, eid, shift = run_one(world, r, searched_is_a, ha, hb)
                        record("half_shifted", r, ha, hb, searched_is_a, out, eid,
                               shift)
                # Decoy opponents of the same tournament and day.
                in_event = {r["home_id"], r["away_id"]}
                decoys: list[tuple[str, int, str]] = []
                for x in sorted(by_group[(r["day"], r["tournament_id"])],
                                key=lambda x: x["sb"]):
                    if x["sb"] == r["sb"]:
                        continue
                    for dn, d_id, dname in (
                            (x["side_a"], x["home_id"], x["home_name"]),
                            (x["side_b"], x["away_id"], x["away_name"])):
                        if d_id not in in_event:
                            decoys.append((dn, d_id, dname))
                for dn, d_id, dname in decoys[:3]:
                    dl = relabel(dn, level)
                    for searched_is_a in (True, False):
                        da, db = (a, dl) if searched_is_a else (dl, b)
                        out, eid, shift = run_one(world, r, searched_is_a, da, db,
                                                  (d_id, dname))
                        record("decoy", r, da, db, searched_is_a, out, eid, shift,
                               decoy=True)
                if not baseline_done:
                    # The ordinary gate on the same decoys, board unshifted.
                    baseline_done = True
                    for dn, _d_id, _dname in decoys[:3]:
                        for searched_is_a in (True, False):
                            da, db = ((r["side_a"], dn) if searched_is_a
                                      else (dn, r["side_b"]))
                            got, _eid = exact_gate(world, r, searched_is_a, da, db)
                            res[f"decoy_exact_gate_baseline:{got}"] += 1
    return {"counts": dict(sorted(res.items())), "wrong": wrong,
            "shifts": dict(sorted(shifts.items()))}


def _gap_cands(d: dict[str, Any], ko: datetime) -> list[tuple[dict[str, Any],
                                                               list[Event]]]:
    """RESOLVE's candidates from one side's replayed searches: the first 3
    fitting results (as resolve_entity tries them), then up to 3 alias
    candidates in search order (`_squad_level_alias`)."""
    norm = normalize_name(d.get("side") or "")
    teams: list[dict[str, Any]] = []
    seen: set[int] = set()
    for q in d.get("queries") or []:
        for t in q.get("teams") or []:
            if t["id"] not in seen:
                seen.add(t["id"])
                teams.append(t)
    out: list[tuple[dict[str, Any], list[Event]]] = []
    tried: set[int] = set()

    def ent(t: dict[str, Any]) -> dict[str, Any]:
        return {"id": t["id"], "name": t["name"], "gender": t.get("gender")}

    for t in teams:
        if t.get("fits") and (t.get("fit_rank") or 99) <= 3:
            out.append((ent(t), [_diag_event(e, ko) for e in t.get("near") or []]))
            tried.add(t["id"])
    extra = 0
    for t in teams:
        if extra < 3 and t["id"] not in tried and squad_alias_candidate(norm, ent(t)):
            out.append((ent(t), [_diag_event(e, ko) for e in t.get("near") or []]))
            tried.add(t["id"])
            extra += 1
    return out


def _gap_veto_cands(d: dict[str, Any], ko: datetime) -> list[tuple[dict[str, Any],
                                                                    list[Event]]]:
    """The opponent's own search as `_squad_level_alias` reads it: the plain
    query's first 3 results that fit or are alias candidates."""
    norm = normalize_name(d.get("side") or "")
    out: list[tuple[dict[str, Any], list[Event]]] = []
    for q in d.get("queries") or []:
        if q.get("label") != "plain":
            continue
        for t in q.get("teams") or []:
            e = {"id": t["id"], "name": t["name"], "gender": t.get("gender")}
            if len(out) < 3 and (t.get("fits") or squad_alias_candidate(norm, e)):
                out.append((e, [_diag_event(x, ko) for x in t.get("near") or []]))
    return out


def gap_recall(diag_path: Path, classes_path: Path) -> list[dict[str, Any]]:
    cls = {x["id"]: x for x in json.loads(classes_path.read_text())}
    out: list[dict[str, Any]] = []
    for line in diag_path.read_text().splitlines():
        r = json.loads(line)
        c = cls.get(r["id"])
        if not c or c["final"] != GAP_CLASS:
            continue
        ko = _ts(r["kickoff"])
        a, b = split_match_name(r["match"])
        diag = {d["side"]: d for d in r.get("diag") or []}
        expected = int(str(c.get("ex") or "0").split()[0] or 0)
        v: dict[str, Any] = {"id": r["id"], "match": r["match"], "expected": expected,
                             "expected_game": c.get("ex"), "started": c.get("started"),
                             "pick": None, "shift": None}
        v["vetoed"] = []
        for side, opp in ((a, b), (b, a)):
            got = squad_level_alias_event(_gap_cands(diag.get(side) or {}, ko), ko,
                                          side, opp, a, b)
            if got is not None and squad_alias_veto(
                    got[1], ko, _gap_veto_cands(diag.get(opp) or {}, ko)):
                v["vetoed"].append(f"{side}: {got[1]['id']}")
                continue
            if got is not None:
                v.update(pick=int(got[1]["id"]), shift=got[2], via=side,
                         game=f"{got[1]['homeTeam']['name']} - "
                              f"{got[1]['awayTeam']['name']}")
                break
        v["verdict"] = ("REFUSED" if v["pick"] is None
                        else "correct" if v["pick"] == expected else "WRONG")
        out.append(v)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("--from", dest="first", default="2026-10-05")
    ap.add_argument("--to", dest="last", default="2026-10-20")
    ap.add_argument("--db-path")
    ap.add_argument("--runs-dir")
    ap.add_argument("--json-out")
    ap.add_argument("--gap-diag")
    ap.add_argument("--gap-classes")
    ap.add_argument("--loose", action="store_true")
    ap.add_argument("--skip-bridged", action="store_true")
    args = ap.parse_args(argv)
    report: dict[str, Any] = {"from": args.first, "to": args.last}
    variants: list[tuple[str, Any]] = [("pair_consistent", None)]  # the rule
    if args.loose:
        variants.append(("loose", loose_shift))
    if not args.skip_bridged:
        cfg = SofaConfig.from_env()
        runs = Path(args.runs_dir or cfg.runs_dir)
        db = args.db_path or cfg.db_path
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = load_bridged(runs, args.first, args.last)
        lo = int((_ts(args.first + "T00:00:00Z") - timedelta(days=2)).timestamp())
        hi = int((_ts(args.last + "T00:00:00Z") + timedelta(days=3)).timestamp())
        ids = {r["home_id"] for r in rows} | {r["away_id"] for r in rows}
        world = AliasWorld(load_events(conn, lo, hi, ids))
        sides = {r["side_a"] for r in rows} | {r["side_b"] for r in rows}
        world.prepare(sides)
        report["fixtures"] = len(rows)
        for name, rule in variants:
            with shift_rule(rule):
                report[f"bridged:{name}"] = bridged_backtest(world, rows)
            b = report[f"bridged:{name}"]
            print(f"[{name}] bridged football fixtures {args.first}..{args.last}: "
                  f"{len(rows)}")
            for k, v in b["counts"].items():
                print(f"  {k}: {v}")
            for k, v in b["shifts"].items():
                print(f"  shift {k}: {v}")
            for w in b["wrong"]:
                print(f"  WRONG {w}")
    if args.gap_diag and args.gap_classes:
        for name, rule in variants:
            with shift_rule(rule):
                gaps = gap_recall(Path(args.gap_diag), Path(args.gap_classes))
            report[f"gaps:{name}"] = gaps
            print(f"[{name}] F2 recall: " + ", ".join(
                f"{k} {v}" for k, v in Counter(g["verdict"] for g in gaps).items()))
            for g in gaps:
                print(f"  {g['verdict']:8} {g['match']}: "
                      + (f"{g['pick']} {g.get('game')} ({g['shift']})" if g["pick"]
                         else f"expected {g['expected_game']}"))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
