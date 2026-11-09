#!/usr/bin/env python3
"""The schedule term's corrected p of every settled Superbet line of its keys
before the switch (epochs.SCHEDULE_TERM; bet.sofa.schedule_term_evidence.
BACKFILL), so fit_line_evidence.py reads those keys' line evidence at the p
their switch-day rows carry - the pattern of the tennis point model and the
volleyball rally model (backfill_vb_point_p.py).

Two populations, both as of each match (no look-ahead: each side's schedule
features from the listed calendar before the kick-off, read with SHEET's own
functions - ``schedule_term.ReplayTerms``: ``side_features`` +
``fixture_term`` on one calendar of every listed football event, the
installed coefficients of config/sofa_schedule_terms.json, the fixture's
national flag and season from the day's 02_fixtures.json):

* ``sheet``: every settled sheet row (07_settled.json, WIN / LOSS, priced)
  of epochs.SCHEDULE_TERM_MARKETS of the days FIRST_DAY .. the switch's first
  whole day (exclusive) and --before. SHEET's estimator of the row (1X2 /
  DNB / double chance / score markets: NB goals; first goal: the NB race;
  the simulator's keys: football_sim_sheet.SimPricer) on the row's noted
  pure centres (05_sheet.json notes, 3 dp) gives the term's move, and the
  corrected p = the row's p_central + f(centres x exp(t)) - f(centres)
  (the delta carries the term; the noted centres are rounded, so the base
  is the row's own p, never a re-price). t = 0 (national fixture, a side
  without coverage) = the row's p_central. A corrected p outside the model's
  resolution (SHEET would write no row) or a row whose note does not parse
  is left out (counted).
* ``sim_lines``: football_sim_curves.BACKFILL's graded Superbet lines of the
  simulator's in-scope keys (the four 0.60-floor keys excluded), priced
  exactly as that backfill was - SimPricer on the match's walk-forward pure
  centres (``--sim-cache-dir``/forecasts_live.pkl) - with the goals centres
  x exp(t). Each line's uncorrected re-price is compared with its stored p
  (``parity`` in the table).

Incremental: a day whose 07_settled.json is unchanged since it was read is
not read again, a key once priced stays as priced; a changed coefficient
file, simulator parameters or simulator backfill re-prices its section.

Read-only on the DB (mode=ro; default the working DB, --db-path a copy).
Never the network.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_schedule_term_p.py \\
        --before <D> [--db-path <copy>] [--rebuild] [--dry-run] [--workers 8]

Run by refresh_line_evidence.py (step 1c) while epochs.SCHEDULE_TERM is on
for <D>. Exit 0 OK, 2 FAILED.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pickle
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa import football_sim_curves as fsc  # noqa: E402
from bet.sofa import football_sim_sheet as fss  # noqa: E402
from bet.sofa import schedule_term as sterm  # noqa: E402
from bet.sofa import schedule_term_evidence as ste  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.engine import outside_model_resolution  # noqa: E402
from bet.sofa.football_1x2_dnb import probabilities as p1x2  # noqa: E402
from bet.sofa.football_1x2_dnb import row_p as p1x2_row  # noqa: E402
from bet.sofa.football_incidents import first_goal_probs  # noqa: E402
from bet.sofa.football_result import result_probs  # noqa: E402
from bet.sofa.football_score_markets import MARKETS as SCORE_MARKETS  # noqa: E402
from bet.sofa.football_score_markets import row_p as score_row_p  # noqa: E402
from bet.sofa.football_score_markets import score_grid  # noqa: E402
from bet.sofa.football_sim import Centres, SimParams  # noqa: E402

# The first day with settled rows of the term's keys (double chance from
# 2026-10-14); earlier days hold none.
FIRST_DAY = "2026-10-13"
DEFAULT_SIM_CACHE = _REPO / "data" / "football_sim_2026-11-06"
P_DIGITS = 4  # SHEET's p_central
SIM_LINE_DIGITS = 5  # football_sim_curves.BACKFILL's p
# Bumped when the simulator lines' pricing changes (re-prices that section).
SIM_LINES_CODE = 2

# The notes SHEET writes on the rows (run_sheet: dc_note, result_1x2_dnb_note,
# score_market_note, incident_note; football_sim_sheet.note).
RE_PURE = re.compile(r"pure rating centres home ([\d.]+) / away ([\d.]+)")
RE_R = re.compile(r"NB goals \(r ([\d.]+)\)")
RE_SIM = re.compile(r"pure rating goals centres home ([\d.]+) / away ([\d.]+), "
                    r"card points (default|([\d.]+) / ([\d.]+))")


# --- pricing (SHEET's estimators, run_sheet's row functions' arithmetic) --------


@lru_cache(maxsize=4096)
def _probs(lh: float, la: float, r: float) -> dict[str, float]:
    return result_probs(lh, la, r)


@lru_cache(maxsize=4096)
def _p1x2(lh: float, la: float, r: float) -> dict[str, float]:
    return p1x2(lh, la, r)


@lru_cache(maxsize=1024)
def _grid(lh: float, la: float, r: float) -> Any:
    return score_grid(lh, la, r)


@lru_cache(maxsize=4096)
def _first_goal(lh: float, la: float, r: float, exact: bool) -> dict[str, float]:
    return first_goal_probs(lh, la, r, exact=exact)


def nb_p(market: str, subject: str, line: float, direction: str,
         lh: float, la: float, r: float, first_goal_exact: bool = False
         ) -> float | None:
    """The p SHEET's row function writes (before rounding) for one NB-priced
    row of the term's keys on goals centres `lh` / `la`; None when SHEET
    prices no such row."""
    if market == "double_chance":
        return _probs(lh, la, r).get(subject) if direction == "OVER" else None
    if market in ("result_1x2", "draw_no_bet"):
        return p1x2_row(market, subject, direction, _p1x2(lh, la, r))
    if market in SCORE_MARKETS:
        if direction != "OVER":
            return None
        return score_row_p(market, subject, line, _grid(lh, la, r))
    if market == "first_goal":
        if direction != "OVER":
            return None
        return _first_goal(lh, la, r, first_goal_exact).get(subject)
    return None


@dataclass(frozen=True)
class Noted:
    """A row's noted pure centres (3 dp; the simulator's card points 2 dp)."""

    lh: float
    la: float
    r: float | None = None
    cards: tuple[float, float] | None = None
    sim: bool = False


def noted(market: str, notes: list[str] | None) -> Noted | None:
    text = " | ".join(str(n) for n in notes or [])
    if market in epochs.FOOTBALL_SIM_MARKETS:
        m = RE_SIM.search(text)
        if m is None:
            return None
        cards = (None if m.group(3) == "default"
                 else (float(m.group(4)), float(m.group(5))))
        return Noted(float(m.group(1)), float(m.group(2)), None, cards, True)
    m, r = RE_PURE.search(text), RE_R.search(text)
    if m is None or r is None:
        return None
    return Noted(float(m.group(1)), float(m.group(2)), float(r.group(1)))


def corrected(p_row: float, base: float, moved: float,
              digits: int = P_DIGITS) -> float | None:
    """The row's p moved by the term (the delta of one estimator on the
    same centres); None when SHEET would write no such row."""
    p = p_row + (moved - base)
    if outside_model_resolution(p):
        return None
    return round(p, digits)


def term_args(fx: Mapping[str, Any]) -> tuple[int, int, int, int, int | None,
                                              int | None, bool]:
    """ReplayTerms.term's arguments from a 02_fixtures.json fixture - the
    FixtureKey run_sheet.load_schedule_terms builds."""
    kick = datetime.fromisoformat(str(fx["kickoff_utc"]).replace("Z", "+00:00"))
    return (int(fx["sofascore_event_id"]), int(kick.timestamp()),
            int(fx["home_entity_id"]), int(fx["away_entity_id"]),
            None if fx.get("competition_id") is None else int(fx["competition_id"]),
            None if fx.get("season_id") is None else int(fx["season_id"]),
            bool(fx.get("national_teams")))


# --- the simulator in worker processes -----------------------------------------

_SIM_PARAMS: Any = None
SIMS = fss.SIMS  # SHEET's paths per fixture


def _init(params_json: dict[str, Any]) -> None:
    global _SIM_PARAMS
    _SIM_PARAMS = SimParams.from_json(params_json)


SimJob = tuple[int, Centres, Centres, list[tuple[str, str, str]]]


def _sim_job(job: SimJob) -> tuple[int, dict[tuple[str, str, str],
                                             tuple[float | None, float | None]]]:
    """(event, {selection: (p on `base`, p on `moved`)}) - two pricers, so
    neither re-simulates the other (SimPricer caches per event)."""
    eid, base, moved, wanted = job
    assert _SIM_PARAMS is not None
    b, m = (fss.SimPricer(_SIM_PARAMS, sims=SIMS),
            fss.SimPricer(_SIM_PARAMS, sims=SIMS))
    out = {}
    for market, subject, direction in wanted:
        out[(market, subject, direction)] = (
            b.p(eid, base, market, subject, direction),
            m.p(eid, moved, market, subject, direction))
    return eid, out


def run_sims(jobs: list[SimJob], params: Any, workers: int
             ) -> dict[int, dict[tuple[str, str, str],
                                 tuple[float | None, float | None]]]:
    if not jobs:
        return {}
    if workers <= 1:
        _init(params.to_json())
        return dict(_sim_job(j) for j in jobs)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                             initargs=(params.to_json(),)) as pool:
        return dict(pool.map(_sim_job, jobs, chunksize=8))


def scaled(c: Centres, term: sterm.FixtureTerm) -> Centres:
    gh, ga = sterm.ReplayTerms.scaled(c.goals[0], c.goals[1], term)
    return Centres(goals=(gh, ga), halves={}, cards=c.cards)


# --- the sheet rows --------------------------------------------------------------


def _fingerprint(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def days_to_read(runs_dir: Path, before: str, switch_day: str | None,
                 seen: Mapping[str, str]) -> list[str]:
    """The days FIRST_DAY .. min(before, switch_day) (exclusive) with a
    settled sheet whose 07_settled.json changed since it was read."""
    if switch_day is None:
        return []
    end = min(before, switch_day)
    out = []
    for d in sorted(p.name for p in runs_dir.iterdir() if p.is_dir()):
        if not (len(d) == 10 and d[4] == "-" and FIRST_DAY <= d < end):
            continue
        settled = runs_dir / d / "07_settled.json"
        if not (settled.exists() and (runs_dir / d / "05_sheet.json").exists()):
            continue
        if seen.get(d) != _fingerprint(settled):
            out.append(d)
    return out


def settled_scope(settled: list[Mapping[str, Any]], day: str,
                  have: Mapping[str, float]) -> dict[str, Mapping[str, Any]]:
    """key -> settled row of the term's keys still to price (WIN / LOSS,
    priced, not in the table)."""
    scope = ste.markets()
    out: dict[str, Mapping[str, Any]] = {}
    for r in settled:
        if (r.get("sport") != ste.SPORT or r.get("market") not in scope
                or r.get("outcome") not in ("WIN", "LOSS")
                or r.get("p_central") is None or not r.get("offered_odds")
                or not r.get("direction")):
            continue
        key = ste.sheet_key(day, r["sofascore_event_id"], str(r["market"]),
                            r.get("subject"), r.get("line"), str(r["direction"]))
        if key not in have:
            out[key] = r
    return out


TermOf = Callable[[str, int], sterm.FixtureTerm | None]


def price_day(day: str, want: Mapping[str, Mapping[str, Any]],
              sheet_rows: list[Mapping[str, Any]], term_of: TermOf,
              params: Any, workers: int, counts: Counter[str],
              parity: dict[str, float]) -> dict[str, float]:
    """The corrected p of the day's wanted rows."""
    notes: dict[str, list[str]] = {}
    for r in sheet_rows:
        if r.get("sport") != ste.SPORT or r.get("market") not in ste.markets():
            continue
        key = ste.sheet_key(day, r["sofascore_event_id"], str(r["market"]),
                            r.get("subject"), r.get("line"), str(r["direction"]))
        if key in want:
            notes[key] = list(r.get("notes") or [])
    exact = epochs.first_goal_nb_exact(day)
    out: dict[str, float] = {}
    sim_want: dict[int, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    sim_centres: dict[int, tuple[Centres, Centres]] = {}
    for key, r in want.items():
        eid = int(r["sofascore_event_id"])
        term = term_of(day, eid)
        if term is None:
            counts["sheet:no_fixture"] += 1
            continue
        counts[f"sheet:status:{term.status}"] += 1
        p_row = float(r["p_central"])
        if not term.moves:
            out[key] = p_row  # t = 0: SHEET's row is the uncorrected one
            counts["sheet:t0"] += 1
            continue
        nt = noted(str(r["market"]), notes.get(key))
        if nt is None:
            counts["sheet:no_note" if key not in notes else "sheet:unparsed"] += 1
            continue
        market, subject = str(r["market"]), str(r.get("subject") or "")
        direction, line = str(r["direction"]), float(r["line"])
        if nt.sim:
            base_c = Centres(goals=(nt.lh, nt.la), halves={}, cards=nt.cards)
            sim_centres[eid] = (base_c, scaled(base_c, term))
            sim_want[eid].append((key, r))
            continue
        assert nt.r is not None
        mh, ma = sterm.ReplayTerms.scaled(nt.lh, nt.la, term)
        try:
            base = nb_p(market, subject, line, direction, nt.lh, nt.la, nt.r, exact)
            moved = nb_p(market, subject, line, direction, mh, ma, nt.r, exact)
        except ValueError:
            counts["sheet:not_priced"] += 1
            continue
        if base is None or moved is None:
            counts["sheet:not_priced"] += 1
            continue
        parity["sheet_nb_reprice_max"] = max(
            parity.get("sheet_nb_reprice_max", 0.0), abs(round(base, P_DIGITS) - p_row))
        got = corrected(p_row, base, moved)
        if got is None:
            counts["sheet:outside_resolution"] += 1
            continue
        out[key] = got
        counts["sheet:priced_nb"] += 1
    if sim_want:
        if params is None:
            counts["sheet:sim_no_params"] += sum(len(v) for v in sim_want.values())
        else:
            jobs: list[SimJob] = [
                (eid, *sim_centres[eid],
                 sorted({(str(r["market"]), str(r.get("subject") or ""),
                          str(r["direction"])) for _, r in rows}))
                for eid, rows in sim_want.items()]
            sims = run_sims(jobs, params, workers)
            for eid, rows in sim_want.items():
                for key, r in rows:
                    base_p, moved_p = sims.get(eid, {}).get(
                        (str(r["market"]), str(r.get("subject") or ""),
                         str(r["direction"])), (None, None))
                    if base_p is None or moved_p is None:
                        counts["sheet:sim_not_priced"] += 1
                        continue
                    p_row = float(r["p_central"])
                    parity["sheet_sim_reprice_max"] = max(
                        parity.get("sheet_sim_reprice_max", 0.0),
                        abs(round(base_p, P_DIGITS) - p_row))
                    got = corrected(p_row, base_p, moved_p)
                    if got is None:
                        counts["sheet:outside_resolution"] += 1
                        continue
                    out[key] = got
                    counts["sheet:priced_sim"] += 1
    return out


# --- the simulator's backfilled lines -------------------------------------------


def price_sim_lines(lines: Sequence[Mapping[str, Any]], forecasts: Mapping[int, Any],
                    term_of: TermOf, params: Any, workers: int,
                    counts: Counter[str], parity: dict[str, float]
                    ) -> dict[str, float]:
    """football_sim_curves.BACKFILL's in-scope lines at the simulator's p on
    the corrected exact centres (the floor keys are never in the table)."""
    scope = ste.sim_markets()
    want: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    centres: dict[int, tuple[Centres, Centres]] = {}
    out: dict[str, float] = {}
    for r in lines:
        if str(r["market"]) not in scope:
            continue
        eid = int(r["eid"])
        term = term_of(str(r["day"]), eid)
        if term is None:
            counts["sim_lines:no_fixture"] += 1
            continue
        counts[f"sim_lines:status:{term.status}"] += 1
        key = ste.sim_line_key(str(r["day"]), eid, str(r["market"]),
                               r.get("subject"), str(r["direction"]))
        if not term.moves:
            out[key] = float(r["p"])
            counts["sim_lines:t0"] += 1
            continue
        values = forecasts.get(eid) or {}
        goals = values.get("goals_for")
        if goals is None or min(goals) <= 0:
            counts["sim_lines:no_centres"] += 1
            continue
        cards = values.get("cards_points_for")
        base = Centres(goals=(float(goals[0]), float(goals[1])), halves={},
                       cards=None if cards is None or min(cards) <= 0
                       else (float(cards[0]), float(cards[1])))
        centres[eid] = (base, scaled(base, term))
        want[eid].append(r)
    if want and params is None:
        counts["sim_lines:no_params"] += sum(len(v) for v in want.values())
        return out
    jobs: list[SimJob] = [
        (eid, *centres[eid], sorted({(str(r["market"]), str(r.get("subject") or ""),
                                      str(r["direction"])) for r in rows}))
        for eid, rows in want.items()]
    sims = run_sims(jobs, params, workers)
    for eid, rows in want.items():
        for r in rows:
            base_p, moved_p = sims.get(eid, {}).get(
                (str(r["market"]), str(r.get("subject") or ""), str(r["direction"])),
                (None, None))
            if base_p is None or moved_p is None:
                counts["sim_lines:not_priced"] += 1
                continue
            parity["sim_lines_reprice_max"] = max(
                parity.get("sim_lines_reprice_max", 0.0),
                abs(round(base_p, SIM_LINE_DIGITS) - float(r["p"])))
            # football_sim_curves.BACKFILL keeps every graded line whatever
            # its p (no resolution cut there), so neither does its correction
            out[ste.sim_line_key(str(r["day"]), eid, str(r["market"]),
                                 r.get("subject"), str(r["direction"]))] = round(
                moved_p, SIM_LINE_DIGITS)
            counts["sim_lines:priced"] += 1
    return out


# --- main ----------------------------------------------------------------------


class Terms:
    """Each (day, event)'s term from the day's 02_fixtures.json and one
    ReplayTerms calendar (loaded on first use)."""

    def __init__(self, runs_dir: Path, db_path: str) -> None:
        self.runs_dir, self.db_path = runs_dir, db_path
        self._replay: sterm.ReplayTerms | None = None
        self._fixtures: dict[str, dict[int, Mapping[str, Any]]] = {}
        self._cache: dict[tuple[str, int], sterm.FixtureTerm | None] = {}

    def replay(self) -> sterm.ReplayTerms:
        if self._replay is None:
            print(f"calendar: reading the listed football events of {self.db_path}",
                  file=sys.stderr, flush=True)
            self._replay = sterm.load_replay_terms(self.db_path)
        return self._replay

    def fixtures(self, day: str) -> dict[int, Mapping[str, Any]]:
        if day not in self._fixtures:
            path = self.runs_dir / day / "02_fixtures.json"
            rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            self._fixtures[day] = {int(f["sofascore_event_id"]): f for f in rows
                                   if f.get("sport") == ste.SPORT}
        return self._fixtures[day]

    def __call__(self, day: str, eid: int) -> sterm.FixtureTerm | None:
        if (day, eid) not in self._cache:
            fx = self.fixtures(day).get(eid)
            if fx is None or fx.get("home_entity_id") is None \
                    or fx.get("away_entity_id") is None:
                self._cache[(day, eid)] = None
            else:
                e, ts, h, a, comp, season, national = term_args(fx)
                self._cache[(day, eid)] = self.replay().term(
                    e, ts, h, a, comp, season, national)
        return self._cache[(day, eid)]


def write(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True)
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--before", required=True, help="settled days strictly before")
    ap.add_argument("--db-path", default=None,
                    help="the calendar's DB (read-only; default the working DB)")
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--out", default=str(ste.BACKFILL))
    ap.add_argument("--sim-cache-dir", default=str(DEFAULT_SIM_CACHE))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rebuild", action="store_true",
                    help="price every line again (the table is replaced)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(args.runs_dir or config.runs_dir)
    db_path = args.db_path or config.db_path
    switch_day = ste.first_whole_day()
    out_path = Path(args.out)
    cfg_sha = _sha(config_path(sterm.CONFIG_FILE))
    params = fss.load_params()
    params_sha = _sha(config_path(fss.PARAMS_FILE))
    sim_src_sha = _sha(fsc.BACKFILL)

    old = None if args.rebuild else ste.read_doc(out_path)
    if old is not None and old.get("config_sha256") != cfg_sha:
        print("config/sofa_schedule_terms.json changed: re-pricing everything",
              file=sys.stderr)
        old = None
    sheet: dict[str, float] = dict((old or {}).get("sheet") or {})
    seen: dict[str, str] = dict((old or {}).get("days") or {})
    sim_lines: dict[str, float] = dict((old or {}).get("sim_lines") or {})
    sim_fp = {"params_sha256": params_sha, "source_sha256": sim_src_sha,
              "code": SIM_LINES_CODE}
    sim_stale = old is None or old.get("sim_lines_from") != sim_fp
    counts: Counter[str] = Counter()
    parity: dict[str, float] = {}
    terms = Terms(runs_dir, db_path)

    for day in days_to_read(runs_dir, args.before, switch_day, seen):
        settled_path = runs_dir / day / "07_settled.json"
        fp = _fingerprint(settled_path)
        want = settled_scope(json.loads(settled_path.read_text(encoding="utf-8")),
                             day, sheet)
        if want:
            rows = json.loads((runs_dir / day / "05_sheet.json")
                              .read_text(encoding="utf-8"))
            got = price_day(day, want, rows if isinstance(rows, list)
                            else rows.get("rows") or [], terms, params,
                            args.workers, counts, parity)
            del rows
            sheet.update(got)
            counts["sheet:wanted"] += len(want)
        seen[day] = fp
        print(f"{day}: wanted {len(want)}, table {len(sheet)}", file=sys.stderr,
              flush=True)

    if sim_stale and switch_day is not None:
        lines = [r for r in fsc.load_backfill()
                 if str(r["day"]) < min(args.before, switch_day)]
        forecasts: Mapping[int, Any] = {}
        cache = Path(args.sim_cache_dir) / "forecasts_live.pkl"
        if cache.exists():
            with cache.open("rb") as fh:
                forecasts = pickle.load(fh)
        else:
            print(f"WARN no {cache}: the simulator's backfilled lines are not "
                  "re-priced (no evidence for them)", file=sys.stderr)
        sim_lines = price_sim_lines(lines, forecasts, terms, params,
                                    args.workers, counts, parity)

    doc: dict[str, Any] = {
        "schema": ste.SCHEMA,
        "rule": epochs.SCHEDULE_TERM,
        "switch_first_whole_day": switch_day,
        "built_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "built_through": max(seen) if seen else None,
        "config_sha256": cfg_sha,
        "calendar_db": str(db_path),
        "days": dict(sorted(seen.items())),
        "sim_lines_from": sim_fp,
        "counts_last_run": dict(sorted(counts.items())),
        "parity_last_run": {k: round(v, 6) for k, v in sorted(parity.items())},
        "statuses_last_run": (dict(sorted(terms._replay.statuses.items()))
                              if terms._replay is not None else {}),
        "unfitted_constants": list(sterm.UNFITTED_CONSTANTS),
        "sheet": sheet,
        "sim_lines": sim_lines,
    }
    summary = {k: v for k, v in doc.items() if k not in ("sheet", "sim_lines", "days")}
    summary.update({"sheet_rows": len(sheet), "sim_lines": len(sim_lines),
                    "days": len(seen)})
    print(json.dumps(summary, indent=1))
    if not args.dry_run:
        write(out_path, doc)
        print(f"written {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - exit code contract: 2 on a crash
        print(f"BACKFILL_SCHEDULE_TERM_P_FAILED: {exc!r}", file=sys.stderr)
        sys.exit(2)
