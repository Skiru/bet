#!/usr/bin/env python3
"""Measure the football rating's domain rule: the modal league vs the league
a side plays now.

football_rating.RatingBook.domain is a side's modal league unit of its last
TEAM_COMP_MEMORY (40) matches inside LINK_WINDOW_S (365 days), so a promoted
or relegated side keeps its old league for ~18-20 matches (2026-10-29: Arka,
Betclic 1. Liga from 2026-07-24, still Ekstraklasa 202:21 vs 229:12;
Deportivo, LaLiga from 2026-08-17, still LaLiga 2) and Arka - Stal, both of
229, was priced as a cross-league pair. Candidates, each replayed over the
same history and scored one step ahead (every match forecast before its own
update, as SHEET's book stands before the day):

  * ``cur<D>``: RatingBook.current_league_domain with DOMAIN_ACTIVE_S = D
    days - the league unit (non-knockout matches) of the side's newest season
    with the most matches among those played in the last D days, once it has
    LINK_MIN_MATCHES; the modal rule otherwise;
  * ``modal<W>x<M>``: the modal rule with LINK_WINDOW_S = W days and
    TEAM_COMP_MEMORY = M matches (the grid of
    docs/sofa/evidence/model_defects_2026-10-05.md).

Per metric (goals_for, corners_for, cards_points_for, shots_for) a side's
count is scored by the Poisson log-loss of the rating's expected count
(FootballRatingBook.expected through link(), as SHEET reads it); goals also
by the 1X2 log-loss of the NB score grid (football_result). Only matches the
rating prices in both arms (not UNLINKED, both sides past MIN_TEAM_MATCHES)
are compared; a match one arm leaves UNLINKED is counted apart. Differences
are candidate minus base (negative = the candidate is better) with a 95%
interval from resampling matches, on:

  * ``all``: every compared match of the window;
  * ``changed``: a side's domain differs between the arms;
  * ``moved20``: the first 20 matches of a side after the candidate's domain
    moved from one competition to another (promoted / relegated sides, read
    off the candidate's own past only).

The grid is chosen on --select-from .. --select-to and confirmed on
--test-from .. --cut (out of sample). Read only: the history comes from
football_rating.load_history on the given DB (a COPY - the pickle is written
next to it); nothing else is written but --json-out.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_rating_domain.py \\
        --db-path data/refit_2026-10-30/sofa.db --json-out <f>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from bet.sofa import football_rating as fr
from bet.sofa.cup_strength import load as load_cup
from bet.sofa.football_result import count_pmf, load_config, market_probs, score_grid

METRICS = ("goals_for", "corners_for", "cards_points_for", "shots_for")
MOVED_N = 20
# domains whose strength the report prints (goals_for)
WATCHED = {229: "Betclic 1. Liga", 202: "Ekstraklasa", 8: "LaLiga",
           54: "LaLiga 2"}
Arr = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Arm:
    name: str
    current_league: bool = False
    active_days: int = 60
    window_days: int = 365
    memory: int = 40


def arms() -> list[Arm]:
    out = [Arm("base")]
    out += [Arm(f"cur{d}", True, active_days=d) for d in (30, 60, 90)]
    for w in (180, 365, 730):
        for m in (20, 40, 80):
            if (w, m) != (365, 40):
                out.append(Arm(f"modal{w}x{m}", window_days=w, memory=m))
    return out


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def _poisson_nll(y: float, mu: float) -> float:
    mu = max(mu, 1e-9)
    return mu - y * math.log(mu) + math.lgamma(y + 1)


def walk(history: Iterable[fr.FootballResult], arm: Arm, start: int, cut: int,
         intl: frozenset[int], eta: dict[str, float]) -> dict[str, Any]:
    """One arm over the history: per (event, metric) priced in [start, cut)
    its status, both sides' expected counts and domains, the moved flag."""
    saved = (fr.LINK_WINDOW_S, fr.TEAM_COMP_MEMORY, fr.DOMAIN_ACTIVE_S)
    fr.LINK_WINDOW_S = arm.window_days * 86400
    fr.TEAM_COMP_MEMORY = arm.memory
    fr.DOMAIN_ACTIVE_S = arm.active_days * 86400
    try:
        book = fr.RatingBook(shared_league_link=True)
        # as SHEET builds it today (epochs.unit_strength_from_parent is off)
        book.unit_strength_from_parent = False
        book.cup_competitions = intl
        book.cup_eta = dict(eta)
        book.current_league_domain = arm.current_league
        rows: dict[tuple[int, str], tuple[str, float, float, float, float]] = {}
        doms: dict[int, tuple[int | None, int | None]] = {}
        last_dom: dict[int, int | None] = {}
        moved_left: dict[int, int] = defaultdict(int)
        moved: set[int] = set()
        # a kick-off group is priced before any of it is fed
        # (measure_cup_supremacy_shrink.knockout_rows): no match sees a result
        # of its own kick-off
        pending: list[fr.FootballResult] = []
        for r in history:
            if r.ts >= cut:
                break
            if pending and r.ts != pending[0].ts:
                for g in pending:
                    book.update(g)
                pending.clear()
            if r.women or r.home_reserve or r.away_reserve:
                pending.append(r)
                continue
            dh, da = book.domain(r.home_id), book.domain(r.away_id)
            for team, d in ((r.home_id, dh), (r.away_id, da)):
                old = last_dom.get(team)
                if (d is not None and old is not None
                        and book.unit_competition(d) != book.unit_competition(old)):
                    moved_left[team] = MOVED_N
                last_dom[team] = d
            if r.ts >= start:
                doms[r.event_id] = (dh, da)
                if moved_left[r.home_id] > 0 or moved_left[r.away_id] > 0:
                    moved.add(r.event_id)
                for m in METRICS:
                    if m not in r.values or any(
                            book.team_matches(t, m) < fr.MIN_TEAM_MATCHES
                            for t in (r.home_id, r.away_id)):
                        continue
                    status, lf = book.link(r.home_id, r.away_id, m,
                                           r.competition_id)
                    exp = book.expected(r.competition_id, r.home_id, r.away_id,
                                        m, lf, cross=status != fr.LINKED)
                    if exp is None:
                        continue
                    vh, va = r.values[m]
                    rows[(r.event_id, m)] = (status, exp[0], exp[1], vh, va)
            for team in (r.home_id, r.away_id):
                if moved_left[team] > 0:
                    moved_left[team] -= 1
            pending.append(r)
        for g in pending:
            book.update(g)
        sigma = {
            name: (round(book.strength[(c, "goals_for")].sigma, 4),
                   book.strength[(c, "goals_for")].n)
            for c, name in WATCHED.items() if (c, "goals_for") in book.strength}
        strong = [s.sigma for (c, m), s in book.strength.items()
                  if m == "goals_for" and s.n >= fr.MIN_STRENGTH_LINKS]
        return {"rows": rows, "doms": doms, "moved": moved, "sigma": sigma,
                "mean_abs_sigma": round(float(np.mean(np.abs(strong))), 4)
                if strong else None, "domains_with_strength": len(strong)}
    finally:
        fr.LINK_WINDOW_S, fr.TEAM_COMP_MEMORY, fr.DOMAIN_ACTIVE_S = saved


def _boot(by_match: dict[int, float], n_boot: int = 2000, seed: int = 7
          ) -> list[float] | None:
    if not by_match:
        return None
    v = np.fromiter(by_match.values(), dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    means = v[idx].mean(axis=1)
    return [round(float(v.mean()), 5), round(float(np.quantile(means, 0.025)), 5),
            round(float(np.quantile(means, 0.975)), 5), len(v)]


def _result_nll(mu_h: Arr, mu_a: Arr, x: Arr, y: Arr, r_nb: float) -> Arr:
    grid = score_grid(count_pmf(mu_h, r_nb), count_pmf(mu_a, r_nb))
    p = market_probs(grid)
    res = np.where(x > y, 0, np.where(x == y, 1, 2))
    got = p[np.arange(len(x)), res]
    return np.asarray(-np.log(np.maximum(got, 1e-12)), dtype=float)


def compare(base: dict[str, Any], cand: dict[str, Any], lo: int, hi: int,
            ts_of: dict[int, int], r_nb: float) -> dict[str, Any]:
    """candidate minus base per metric and population, inside [lo, hi)."""
    out: dict[str, Any] = {}
    statuses: dict[str, Counter[str]] = {"base": Counter(), "cand": Counter()}
    for (eid, m), row in base["rows"].items():
        if lo <= ts_of[eid] < hi and m == "goals_for":
            statuses["base"][row[0]] += 1
    for (eid, m), row in cand["rows"].items():
        if lo <= ts_of[eid] < hi and m == "goals_for":
            statuses["cand"][row[0]] += 1
    out["goals_for_status"] = {k: dict(v) for k, v in statuses.items()}
    for m in METRICS:
        pops: dict[str, dict[int, float]] = {
            "all": {}, "changed": {}, "moved20": {}}
        goals: list[tuple[int, float, float, float, float, float, float]] = []
        one_unlinked = 0
        for (eid, metric), b in base["rows"].items():
            if metric != m or not lo <= ts_of[eid] < hi:
                continue
            c = cand["rows"].get((eid, m))
            if c is None:
                continue
            if (b[0] == fr.UNLINKED) != (c[0] == fr.UNLINKED):
                one_unlinked += 1
                continue
            if b[0] == fr.UNLINKED:
                continue
            d = (_poisson_nll(c[3], c[1]) + _poisson_nll(c[4], c[2])
                 - _poisson_nll(b[3], b[1]) - _poisson_nll(b[4], b[2])) / 2
            pops["all"][eid] = d
            if base["doms"].get(eid) != cand["doms"].get(eid):
                pops["changed"][eid] = d
            if eid in cand["moved"]:
                pops["moved20"][eid] = d
            if m == "goals_for":
                goals.append((eid, b[1], b[2], c[1], c[2], b[3], b[4]))
        cell: dict[str, Any] = {"one_arm_unlinked": one_unlinked}
        for name, values in pops.items():
            cell[name] = _boot(values)
        if goals:
            g = np.array([t[1:] for t in goals], dtype=float)
            d1x2 = (_result_nll(g[:, 2], g[:, 3], g[:, 4], g[:, 5], r_nb)
                    - _result_nll(g[:, 0], g[:, 1], g[:, 4], g[:, 5], r_nb))
            ids = [t[0] for t in goals]
            by = dict(zip(ids, d1x2.tolist(), strict=True))
            cell["1x2"] = {
                "all": _boot(by),
                "changed": _boot({e: v for e, v in by.items()
                                  if e in pops["changed"]}),
                "moved20": _boot({e: v for e, v in by.items()
                                  if e in pops["moved20"]}),
            }
        out[m] = cell
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-path", required=True,
                    help="a COPY of data/sofa.db (the history pickle is "
                    "written next to it)")
    ap.add_argument("--start", default="2025-07-01",
                    help="first match scored (the select window's start)")
    ap.add_argument("--select-to", default="2026-07-01")
    ap.add_argument("--cut", default="2026-10-29",
                    help="the test window ends before this day")
    ap.add_argument("--arms", nargs="*", default=None,
                    help="arm names to run (default every arm)")
    ap.add_argument("--awarded-excluded", action="store_true",
                    help="drop results awarded at the table, as SHEET from "
                    "2026-10-30")
    ap.add_argument("--json-out", required=True)
    args = ap.parse_args(argv)
    db = Path(args.db_path)
    history = fr.load_history(db, db.parent / "cache")
    if args.awarded_excluded:
        history = fr.without_awarded(history)
    # the walk reads four metrics: a lighter book, the same domains
    history = [replace(r, values={m: v for m, v in r.values.items()
                                  if m in METRICS}) for r in history]
    ts_of = {r.event_id: r.ts for r in history}
    cup = load_cup()
    r_nb = load_config().nb_r
    start, sel, cut = _ts(args.start), _ts(args.select_to), _ts(args.cut)
    chosen = [a for a in arms() if args.arms is None or a.name in args.arms
              or a.name == "base"]
    print(f"{len(history)} results; arms {[a.name for a in chosen]}",
          file=sys.stderr, flush=True)
    base = walk(history, chosen[0], start, cut, cup.competitions, dict(cup.eta))
    report: dict[str, Any] = {
        "db_path": str(db), "start": args.start, "select_to": args.select_to,
        "cut": args.cut, "awarded_excluded": bool(args.awarded_excluded),
        "metrics": list(METRICS), "r_nb": r_nb,
        "base": {"sigma": base["sigma"], "mean_abs_sigma": base["mean_abs_sigma"],
                 "domains_with_strength": base["domains_with_strength"]},
        "arms": {}}
    for arm in chosen[1:]:
        t0 = datetime.now(UTC)
        cand = walk(history, arm, start, cut, cup.competitions, dict(cup.eta))
        report["arms"][arm.name] = {
            "arm": arm.__dict__,
            "sigma": cand["sigma"], "mean_abs_sigma": cand["mean_abs_sigma"],
            "domains_with_strength": cand["domains_with_strength"],
            "select": compare(base, cand, start, sel, ts_of, r_nb),
            "test": compare(base, cand, sel, cut, ts_of, r_nb),
        }
        Path(args.json_out).write_text(json.dumps(report, indent=1))
        print(f"{arm.name} done in {(datetime.now(UTC) - t0).seconds}s",
              file=sys.stderr, flush=True)
    Path(args.json_out).write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
