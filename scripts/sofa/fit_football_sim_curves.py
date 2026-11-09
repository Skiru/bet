#!/usr/bin/env python3
"""Fit config/sofa_football_sim_curves.json - the history curves of the
football simulator's keys (epochs.FOOTBALL_SIM; read by CONFIDENCE through
bet.sofa.football_sim_curves) - and, with --backfill-out, the simulator's
graded Superbet lines for the line evidence (football_sim_curves.BACKFILL).

The rule (CLAUDE.md): curves are fitted on the HISTORY of events and
statistics, replayed as of each match with the estimator SHEET prices with
today. Here the estimator is bet.sofa.football_sim through
football_sim_sheet.SimPricer (4,000 paths, seed = event id) on each match's
pure rating centres as of its start (football_sim.walk_forward_centres - the
measurement's walk-forward, ``measure_football_sim.load_forecasts``), and
every key of epochs.FOOTBALL_SIM_MARKETS read for every subject:

  * matches: the timed history (``football_sim.load_minute_history``: a
    cached incident list, a half-time score) between --from and --before
    (default 2026-06-01 .. 2026-10-20: after the window the simulator's
    constants were fitted on, 2025-01-01 .. 2026-05-31, before the Superbet
    hold-out of the wiring 10-20 .. 11-05);
  * rows: a multi-way market one OVER row per subject (one-sided - Superbet
    quotes no complement); the two yes / no markets both directions;
    half_goals_combo every pair of half lines 0.5 / 1.5 / 2.5;
  * graded with football_sim_markets.path_holds on the match's half-time and
    90-minute score (the first goal of the first half from the score when it
    decides it, else the timed goals; a match the goals do not decide gives
    no first_goal_1h row).

Curves exactly as fit_confidence writes them: EDGES, MIN_MARKET_BUCKET for
by_market / by_market_direction, MIN_THIN_BUCKET..MIN_MARKET_BUCKET for
thin_by_market_direction, realised_lo95 the Wilson lower bound; every row in
the top-level curves, a women's match also in by_class.women.

--backfill-out: every path-market price OFFER recorded in
runs/sofa/<d>/unmapped_prices (--backfill-from .. --backfill-to) classified as
OFFER classifies it (football_sim_markets.classify against the board's two
Superbet names), the latest snapshot fetched before the fixture's start per
selection, priced by the simulator on the match's walk-forward centres
(measure_football_sim.load_live_forecasts) and graded by
football_sim_markets.sim_value on the cached event (sofa_event_detail) and
incidents (sofa_event_stats) - exactly what SETTLE will read. A line that
does not grade is left out (its reason counted).

Read-only on the DB (mode=ro). Never the network. --cache-dir holds the
measurement's pickles (minute_history.pkl, forecasts.pkl,
forecasts_live.pkl, history_live.pkl); they are read when present.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_football_sim_curves.py \\
        [--cache-dir data/football_sim_2026-11-06] [--out <json>] \\
        [--backfill-out data/line_evidence/football_sim_lines.jsonl.gz]
"""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_sim_curves as fsc  # noqa: E402
from bet.sofa import football_sim_markets as fsm  # noqa: E402
from bet.sofa import football_sim_sheet as fss  # noqa: E402
from bet.sofa import schedule_term as sterm  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import CLASS_WOMEN, direction_key, match_class  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.football_sim import Centres, MinuteMatch, SimParams  # noqa: E402
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    MIN_THIN_BUCKET,
    bucket_of,
    wilson_lo,
)

DEFAULT_CACHE = _REPO / "data" / "football_sim_2026-11-06"
DEFAULT_FROM = "2026-06-01"
DEFAULT_BEFORE = "2026-10-20"
COMBO_FIT_LINES = (0.5, 1.5, 2.5)


def subjects() -> list[tuple[str, str, str]]:
    """Every (market, subject, direction) a fitted match yields a row of."""
    out: list[tuple[str, str, str]] = []
    for s in fsm.HTFT_SUBJECTS:
        out.append((fsm.HTFT, s, "OVER"))
    for market in (fsm.RESULT_1H, fsm.RESULT_2H):
        out += [(market, s, "OVER") for s in fsm.RESULT_SUBJECTS]
    out += [(fsm.HIGHER_HALF, s, "OVER") for s in fsm.HALF_SUBJECTS]
    out += [(fsm.TEAM_BOTH_HALVES, s, d) for s in fsm.SIDE_SUBJECTS
            for d in ("OVER", "UNDER")]
    out += [(fsm.BTTS_HALVES, s, "OVER") for s in fsm.BTTS_HALVES_SUBJECTS]
    out += [(fsm.BTTS_ANY_HALF, "", d) for d in ("OVER", "UNDER")]
    out += [(fsm.FIRST_GOAL_1H, s, "OVER") for s in fsm.FG1H_SUBJECTS]
    for l1 in COMBO_FIT_LINES:
        for l2 in COMBO_FIT_LINES:
            for a in "OU":
                for b in "OU":
                    out.append((fsm.HALF_GOALS_COMBO, f"{a}{l1:g}/{b}{l2:g}",
                                "OVER"))
    return out


SUBJECTS = subjects()


def first_1h_of(m: MinuteMatch) -> str | None:
    """Who scored the first goal of the first half: from the score when it
    decides it, else the timed goals (None: not known)."""
    assert m.ht is not None
    h1, a1 = m.ht
    if h1 + a1 == 0:
        return fsm.FG1H_NONE
    if a1 == 0:
        return "1"
    if h1 == 0:
        return "2"
    if not m.goals:
        return None
    half, _, side = m.goals[0]
    return ("1" if side == 0 else "2") if half == 1 else None


_PARAMS: SimParams | None = None


def _init(params_json: dict[str, Any],
          excluded: frozenset[str] = frozenset()) -> None:
    global _PARAMS, EXCLUDED
    _PARAMS = SimParams.from_json(params_json)
    EXCLUDED = excluded


def centres_of_values(values: Mapping[str, tuple[float, float]],
                      term: sterm.FixtureTerm | None = None) -> Centres | None:
    """The simulator's centres of a match's stored pure rating centres;
    `term` (--schedule-term, epochs.SCHEDULE_TERM) puts exp(t) on the goals
    centres as SHEET's ScheduleTermForecast does (fss.centres_of on the
    wrapped forecast: the cards stay the rating's)."""
    goals = values.get("goals_for")
    if goals is None or min(goals) <= 0:
        return None
    gh, ga = float(goals[0]), float(goals[1])
    if term is not None:
        gh, ga = sterm.ReplayTerms.scaled(gh, ga, term)
    cards = values.get("cards_points_for")
    return Centres(goals=(gh, ga), halves={},
                   cards=None if cards is None or min(cards) <= 0
                   else (float(cards[0]), float(cards[1])))


# --schedule-term: the simulator's 0.60-floor keys keep the uncorrected p
# (config/sofa_schedule_terms.json excluded_markets, pre-registration D13) -
# priced on the job's base centres
EXCLUDED: frozenset[str] = frozenset()


def rows_for(job: tuple[MinuteMatch, Centres] | tuple[MinuteMatch, Centres, Centres]
             ) -> list[dict[str, Any]]:
    """A match's rows. A 3-tuple (match, corrected, base) is a
    --schedule-term job: the markets of EXCLUDED read `base`."""
    m, centres = job[0], job[1]
    base = job[2] if len(job) == 3 else centres
    assert _PARAMS is not None and m.ht is not None
    pricer = fss.SimPricer(_PARAMS)
    base_pricer = fss.SimPricer(_PARAMS) if base != centres else pricer
    first = first_1h_of(m)
    out: list[dict[str, Any]] = []
    for market, subject, direction in SUBJECTS:
        if market in EXCLUDED:
            p = base_pricer.p(m.event_id, base, market, subject, direction)
        else:
            p = pricer.p(m.event_id, centres, market, subject, direction)
        if p is None:
            continue
        held = fsm.path_holds(market, subject, m.ht, m.ft, first)
        if held is None:
            continue
        hit = int(held) if direction == "OVER" else int(not held)
        out.append({"eid": m.event_id, "market": market, "subject": subject,
                    "direction": direction, "p": round(p, 5), "y": hit,
                    "women": m.women, "ts": m.ts})
    return out


Counts = dict[str, dict[int, list[int]]]


def _counts() -> dict[str, Counts]:
    return {"market": defaultdict(lambda: defaultdict(lambda: [0, 0])),
            "direction": defaultdict(lambda: defaultdict(lambda: [0, 0]))}


def add(counts: dict[str, Counts], market: str, direction: str, p: float,
        y: int) -> None:
    b = bucket_of(min(max(p, 0.0), 1.0))
    for cell in (counts["market"][market][b],
                 counts["direction"][direction_key(market, direction)][b]):
        cell[0] += y
        cell[1] += 1


def curve(counts: dict[int, list[int]], floor: int,
          below: int | None = None) -> dict[str, dict[str, Any]]:
    """fit_confidence.main's curve(): one bucket per EDGES cell."""
    out: dict[str, dict[str, Any]] = {}
    for b, (k, n) in sorted(counts.items()):
        if n < floor or (below is not None and n >= below):
            continue
        out[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"] = {
            "n": n, "realised": round(k / n, 4),
            "realised_lo95": round(wilson_lo(k, n), 4)}
    return out


def sections(counts: dict[str, Counts]) -> dict[str, Any]:
    by_market, by_dir = counts["market"], counts["direction"]
    return {
        "by_market": {m: c for m, cs in sorted(by_market.items())
                      if (c := curve(cs, MIN_MARKET_BUCKET))},
        "by_market_direction": {k: c for k, cs in sorted(by_dir.items())
                                if (c := curve(cs, MIN_MARKET_BUCKET))},
        "thin_by_market_direction": {
            k: c for k, cs in sorted(by_dir.items())
            if (c := curve(cs, MIN_THIN_BUCKET, below=MIN_MARKET_BUCKET))},
    }


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True,
                              cwd=_REPO).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _pickle(path: Path) -> Any:
    with path.open("rb") as fh:
        return pickle.load(fh)


# --- backfill: the Superbet lines of the path markets ---------------------------


def _board_sides(run_dir: Path) -> dict[str, tuple[str, str]]:
    path = run_dir / "01_board.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc if isinstance(doc, list) else doc.get(
        "fixtures", doc.get("events", []))
    return {str(e["superbet_event_id"]): (str(e.get("side_a") or ""),
                                          str(e.get("side_b") or ""))
            for e in entries if isinstance(e, dict) and e.get("superbet_event_id")}


def day_lines(run_dir: Path, counts: Counter[str]) -> Iterator[dict[str, Any]]:
    """The path-market selections of one day's unmapped prices: the latest
    snapshot fetched before the fixture's start, with the rung's other side
    for the two-sided markets."""
    fixtures = {int(f["sofascore_event_id"]): f for f in json.loads(
        (run_dir / "02_fixtures.json").read_text(encoding="utf-8"))
        if f.get("sport") == "football"}
    sides = _board_sides(run_dir)
    latest: dict[tuple[int, str, str, str], tuple[str, float, str]] = {}
    for f in sorted((run_dir / "unmapped_prices").glob("2026*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                if '"marketName"' not in line:
                    continue
                d = json.loads(line)
                eid = d.get("sofascore_event_id")
                fx = fixtures.get(eid) if isinstance(eid, int) else None
                if fx is None:
                    continue
                board = sides.get(str(d.get("superbet_event_id")))
                if board is None:
                    continue
                got = fsm.classify(d.get("marketName"), d.get("name"), board)
                if got is None:
                    continue
                counts["classified"] += 1
                price = d.get("price")
                fetched = str(d.get("fetched_at_utc") or "")
                if (not isinstance(price, int | float) or price <= 1.0
                        or d.get("status") not in (None, "active")):
                    counts["inactive_or_no_price"] += 1
                    continue
                if not fetched or fetched >= str(fx.get("kickoff_utc") or ""):
                    counts["fetched_after_start"] += 1
                    continue
                market, subject, _, direction = got
                key = (int(eid), market, subject, direction)
                if key not in latest or latest[key][0] <= fetched:
                    latest[key] = (fetched, float(price), str(d["superbet_event_id"]))
    for (eid, market, subject, direction), (fetched, price, sb) in latest.items():
        fx = fixtures[eid]
        other = None
        if market in fsm.TWO_SIDED:
            opp = latest.get((eid, market, subject,
                              "UNDER" if direction == "OVER" else "OVER"))
            other = None if opp is None or opp[0] != fetched else opp[1]
        yield {"day": run_dir.name, "eid": eid, "market": market,
               "subject": subject, "direction": direction, "odds": price,
               "counter_odds": other, "fetched_at_utc": fetched,
               "kickoff_utc": fx.get("kickoff_utc"),
               "klass": match_class("football", fx.get("competition_name"),
                                    sides.get(sb), fx.get("competition_id")),
               "competition_id": fx.get("competition_id")}


def _price_job(job: tuple[int, Centres, list[tuple[str, str, str]]]
               ) -> tuple[int, dict[tuple[str, str, str], float]]:
    eid, centres, wanted = job
    assert _PARAMS is not None
    pricer = fss.SimPricer(_PARAMS)
    out: dict[tuple[str, str, str], float] = {}
    for market, subject, direction in wanted:
        p = pricer.p(eid, centres, market, subject, direction)
        if p is not None:
            out[(market, subject, direction)] = p
    return eid, out


def backfill(args: argparse.Namespace, params: SimParams) -> dict[str, Any]:
    from bet.sofa.settle import is_completed_event, settle_completed

    runs = Path(args.runs_dir)
    days = sorted(d.name for d in runs.iterdir()
                  if d.is_dir() and len(d.name) == 10 and d.name[4] == "-"
                  and args.backfill_from <= d.name <= args.backfill_to
                  and (d / "unmapped_prices").is_dir()
                  and (d / "02_fixtures.json").exists())
    counts: Counter[str] = Counter()
    lines = [r for day in days for r in day_lines(runs / day, counts)]
    forecasts: dict[int, dict[str, tuple[float, float]]] = _pickle(
        Path(args.cache_dir) / "forecasts_live.pkl")
    wanted: dict[int, set[tuple[str, str, str]]] = defaultdict(set)
    for r in lines:
        wanted[r["eid"]].add((r["market"], r["subject"], r["direction"]))
    jobs = []
    for eid, sel in wanted.items():
        c = centres_of_values(forecasts.get(eid) or {})
        if c is None:
            counts["no_centres"] += len(sel)
            continue
        jobs.append((eid, c, sorted(sel)))
    priced: dict[int, dict[tuple[str, str, str], float]] = {}
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init,
                             initargs=(params.to_json(),)) as pool:
        for eid, got in pool.map(_price_job, jobs, chunksize=8):
            priced[eid] = got
    conn = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 60000")
    out_rows: list[dict[str, Any]] = []
    try:
        for r in lines:
            p = priced.get(r["eid"], {}).get((r["market"], r["subject"],
                                              r["direction"]))
            if p is None:
                counts["not_priced"] += 1
                continue
            det = conn.execute(
                "SELECT detail_json FROM sofa_event_detail "
                "WHERE sofascore_event_id = ?", (r["eid"],)).fetchone()
            event = (json.loads(det[0]) or {}).get("event") if det else None
            if not event:
                counts["no_event"] += 1
                continue
            if not is_completed_event(event) or not settle_completed(event):
                counts["not_completed_or_awarded"] += 1
                continue
            st = conn.execute(
                "SELECT incidents_json FROM sofa_event_stats "
                "WHERE sofascore_event_id = ?", (r["eid"],)).fetchone()
            incidents = json.loads(st[0]) if st and st[0] else None
            value = fsm.sim_value(r["market"], r["subject"], event,
                                  incidents if isinstance(incidents, dict) else None)
            if isinstance(value, str):
                counts[f"ungraded:{value}"] += 1
                continue
            hit = int(value > 0.5) if r["direction"] == "OVER" else int(value < 0.5)
            out_rows.append({**r, "p": round(p, 5), "y": hit})
            counts["graded"] += 1
    finally:
        conn.close()
    out_path = Path(args.backfill_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for row in out_rows:
            fh.write(json.dumps(row) + "\n")
    tmp.replace(out_path)
    return {"days": [days[0], days[-1]] if days else None,
            "lines": len(out_rows), "events": len(priced),
            "counts": dict(sorted(counts.items()))}


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--db-path", default=str(_REPO / "data" / "sofa.db"))
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ap.add_argument("--from", dest="from_day", default=DEFAULT_FROM)
    ap.add_argument("--before", default=DEFAULT_BEFORE)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=str(config_path(fsc.FILE)))
    ap.add_argument("--rows-out", default=None)
    ap.add_argument("--backfill-out", default=None,
                    help="write the graded Superbet lines of the path markets "
                    "(football_sim_curves.BACKFILL) instead of fitting curves")
    ap.add_argument("--backfill-from", default="2026-10-14")
    ap.add_argument("--backfill-to", default="2026-11-05")
    ap.add_argument("--runs-dir", default=str(_REPO / "runs" / "sofa"))
    ap.add_argument("--schedule-term", action="store_true", help=(
        "curves: the goals centres x exp(t) of the as-of schedule features "
        "(epochs.SCHEDULE_TERM; calendar from --db-path), the 0.60-floor keys "
        "of config/sofa_schedule_terms.json on the uncorrected centres"))
    args = ap.parse_args()
    if args.schedule_term and args.backfill_out:
        print("REFUSED: --schedule-term fits curves; the backfill is not "
              "wired to it", file=sys.stderr)
        return 2

    params = fss.load_params()
    if params is None:
        print(json.dumps({"stage": "FIT_FOOTBALL_SIM_CURVES", "verdict": "FAILED",
                          "reason": f"no {fss.PARAMS_FILE}"}))
        return 2
    if args.backfill_out:
        got = backfill(args, params)
        print(json.dumps({"stage": "FOOTBALL_SIM_BACKFILL", "verdict": "OK",
                          **got, "output_path": args.backfill_out}))
        return 0

    cache = Path(args.cache_dir)
    minutes: list[MinuteMatch] = _pickle(cache / "minute_history.pkl")
    forecasts: dict[int, dict[str, tuple[float, float]]] = _pickle(
        cache / "forecasts.pkl")
    lo, hi = _ts(args.from_day), _ts(args.before)
    replay = (sterm.load_replay_terms(args.db_path) if args.schedule_term
              else None)
    excluded = (frozenset(replay.terms.excluded_markets) if replay is not None
                else frozenset())
    jobs: list[Any] = []
    for m in minutes:
        if not (lo <= m.ts < hi) or m.ht is None:
            continue
        values = forecasts.get(m.event_id) or {}
        c = centres_of_values(values)
        if c is None:
            continue
        if replay is None:
            jobs.append((m, c))
            continue
        term = replay.of_result(m)
        corrected = centres_of_values(values, term)
        assert corrected is not None
        jobs.append((m, corrected, c))
    every, women = _counts(), _counts()
    n_rows = 0
    sink = gzip.open(args.rows_out, "wt", encoding="utf-8") if args.rows_out else None
    try:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_init,
                                 initargs=(params.to_json(), excluded)) as pool:
            for i, chunk in enumerate(pool.map(rows_for, jobs, chunksize=32)):
                for r in chunk:
                    add(every, r["market"], r["direction"], r["p"], r["y"])
                    if r["women"]:
                        add(women, r["market"], r["direction"], r["p"], r["y"])
                    if sink is not None:
                        sink.write(json.dumps(r) + "\n")
                n_rows += len(chunk)
                if (i + 1) % 5000 == 0:
                    print(f"{i + 1} / {len(jobs)} matches, {n_rows} rows",
                          flush=True)
    finally:
        if sink is not None:
            sink.close()
    doc: dict[str, Any] = {
        "_doc": (
            "History curves of the football simulator's keys "
            "(epochs.FOOTBALL_SIM_MARKETS), read by CONFIDENCE only under "
            "epochs.FOOTBALL_SIM (bet.sofa.football_sim_curves): the only "
            "curves of these keys. Fitted by "
            "scripts/sofa/fit_football_sim_curves.py on the simulator's "
            "walk-forward over the Sofascore history (centres as of each "
            "match), in fit_confidence's format (realised_lo95 = Wilson lower "
            "bound)."),
        "fitted_from": {
            "estimator": "bet.sofa.football_sim via football_sim_sheet "
                         f"(sims {fss.SIMS}, seed = event id, "
                         f"params {params.fitted_to})",
            "history": "football_sim.load_minute_history (a half-time score; "
                       "centres football_sim.walk_forward_centres)",
            "cache_dir": str(cache),
            "window": [args.from_day, args.before],
            "matches": len(jobs),
            "rows": n_rows,
            "subjects": "every subject; half_goals_combo lines "
                        f"{list(COMBO_FIT_LINES)}",
            "min_market_bucket": MIN_MARKET_BUCKET,
            "min_thin_bucket": MIN_THIN_BUCKET,
            "classes": {CLASS_WOMEN: "a women's match (football_rating women)"},
            "code_commit": _commit(),
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            **({} if replay is None else {
                "schedule_term": {**replay.stamp(args.db_path),
                                  "excluded_markets_uncorrected": sorted(excluded)},
                "replay_rules": {"flags": ["--schedule-term"]}}),
        },
        **sections(every),
        "by_class": {CLASS_WOMEN: sections(women)},
    }
    write_atomic(Path(args.out), json.dumps(doc, indent=1) + "\n")
    print(json.dumps({"stage": "FIT_FOOTBALL_SIM_CURVES", "verdict": "OK",
                      "metrics": {"matches": len(jobs), "rows": n_rows},
                      "keys": len(doc["by_market_direction"]),
                      "output_path": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
