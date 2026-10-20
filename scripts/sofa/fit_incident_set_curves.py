#!/usr/bin/env python3
"""History curves for the football incident markets and the tennis set
markets - fitted, gated on a holdout and STAGED, never installed here.

Plan: docs/sofa/history/PLAN_KRZYWE_NOWE_RYNKI_2026-10-14.md, steps 1-4
(operator's go of 2026-10-14 ~14:45Z). Two groups:

  football_incidents   first_goal (OVER, one-sided, three subjects),
                       red_cards_total / penalties_total (OVER / UNDER,
                       lines 0.5 / 1.5) - bet.sofa.football_incidents
  tennis_sets          set1_won_for / set2_won_for (OVER / UNDER),
                       set_score (OVER, four scores) - bet.sofa.tennis_sets
  card_halves          card points by half (totals / sides, OVER / UNDER;
                       most / handicap OVER), red cards / penalties by side
                       and half, both teams red (OVER / UNDER) -
                       bet.sofa.football_card_halves (2026-10-21; rows from
                       --card-from, the same copy as football_incidents)

1. Copy (CLAUDE.md "Changing the pipeline" 4; pattern
   fit_shot_detail.make_copy): only the tables the replay reads go into
   ``<out-root>/<group>/`` - football: ``sofa_event_stats``' incident lists
   (``incidents.db``) and the football history SHEET parses
   (``data/cache/football_history.pkl``, copied as is); tennis: the tennis
   ``last`` pages of ``sofa_entity_events`` and the tennis rows of the
   listing index (``tennis.db``). An existing copy is reused. The live
   database is opened read-only, once, for the copy.
2. Replay with SHEET's own estimator, as of each match's UTC day (SHEET
   cuts the history at the day it builds):
   - first_goal: ``football_incidents.first_goal_probs`` on the pure rating
     goals centres ``FootballForecast.centre("goals_for", side)`` of the
     book ``replay_football`` builds (shared-league link on, as every day
     since 2026-10-07; no strict league rate), NB r from
     config/sofa_football_result.json. A fixture SHEET would mark
     CROSS_LEAGUE_UNLINKED (CONFIDENCE refuses it) is in the rows, not in a
     curve.
   - red_cards_total / penalties_total: ``IncidentRates.p_over`` of the
     full-feed matches before the day (``load_rates``'s population), lines
     0.5 / 1.5, both directions. Graded only on a full feed - what SETTLE
     grades (``incident_value``: a partial feed is INCIDENTS_PARTIAL_FEED).
   - tennis: ``tennis_sets.set_win_p`` / ``score_probs`` on the HOME
     player's neighbours of ``AsOfRating.model_at(day)`` with the live
     config/tennis_rating.json (measure_tennis_outcome_model variant
     ``live``); completed best-of-three singles, team cups out.
   Every p outside SHEET's [P_FLOOR, P_CEILING] is dropped, as SHEET drops
   it (OUTSIDE_MODEL_RESOLUTION). Rows: ``rows.csv`` (key, p, y, match,
   date, class, ...).
3. Curve: fit_confidence's (EDGES, MIN_MARKET_BUCKET, Wilson lower bound)
   per ``"<market>|<direction>"`` on every row, plus ``by_class`` (football
   ``women``, tennis ``tennis_women``: CONFIDENCE reads a leg of a class
   from the class's own curves only, else NO_CLASS_CURVE) on the class's
   rows. A set winner's OVER is Superbet's first-listed player and UNDER
   the other one; the listing order says nothing about tennis, so both
   direction curves are fitted on both selections of every match (the
   match winner's rule, fit_tennis_winner_curve) and are equal.
4. Gate: a curve fitted on rows before ``--train-before`` (2026-09-01) is
   read on the holdout ``--train-before`` .. ``--holdout-to`` (exclusive,
   2026-10-14): of the holdout selections whose curve value (the train
   bucket's realised_lo95) is >= 0.70, n >= 300 and realised - mean curve
   value >= -2 pp - ONE-SIDED since 2026-10-14 ~18:55Z (operator): only a
   curve that overstates fails; the old two-sided verdict (|gap| <= 2 pp,
   measure_calibration's PASS) is kept as ``two_sided_pass``. A main key
   is judged on the unclassed holdout (the legs that read it), a class key
   on its class. The final curve of a passing key is refitted on every row
   before ``--final-before`` (2026-10-15); a final curve with no bucket
   reaching 0.70 fails the key (it would print nothing).
   ``--regate`` re-decides a saved run from its rows.csv (no copy, no
   replay; the rows hold p as the replay rounded it, so it is exact).

Writes ``<out-root>/<group>/{curves.json,rows.csv,gate_report.md}``.
``curves.json`` = {"target", "fitted_from", "by_market_direction" (passing
keys), "by_class" (passing class keys), "gate" (every key; a class key
as "<class>:<key>")}; the
installer (scripts/sofa/install_new_market_curves.py) merges it. Nothing
under config/ is written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_incident_set_curves.py \\
        [--group football_incidents|tennis_sets|all] \\
        [--out-root data/refit_new_markets_2026-10-15] [--tennis-from 2026-04-01]

Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_card_halves as fch  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import tennis_rating as tr  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.calibration_audit import MAX_GAP, MIN_SETTLED  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    CLASS_TENNIS_TEAM_CUP,
    CLASS_TENNIS_WOMEN,
    CLASS_WOMEN,
    direction_key,
    match_class,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cup_strength import apply as apply_cup_strength  # noqa: E402
from bet.sofa.engine import outside_model_resolution  # noqa: E402
from bet.sofa.football_incidents import (  # noqa: E402
    COUNT_LINES,
    FG_SUBJECTS,
    FIRST_GOAL,
    FIRST_GOAL_AWAY,
    FIRST_GOAL_HOME,
    FIRST_GOAL_NONE,
    PENALTIES,
    RED_CARDS,
    IncidentRates,
    IncidentRecord,
    first_goal_probs,
)
from bet.sofa.football_result import load_config as load_result_config  # noqa: E402
from bet.sofa.listing_index import LISTED_EVENT, LISTING_EVENT  # noqa: E402
from bet.sofa.market_mapper import DERIVED_DRAW_SUBJECT  # noqa: E402
from bet.sofa.tennis_sets import (  # noqa: E402
    SCORES,
    SET1_WON_FOR,
    SET2_WON_FOR,
    SET_SCORE,
    score_probs,
    set_win_p,
)
from scripts.sofa import fit_double_chance_curve as dc_fit  # noqa: E402
from scripts.sofa import new_market_gate as gate_mod  # noqa: E402
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    bucket_of,
    wilson_lo,
)
from scripts.sofa.measure_football_incidents import load_records  # noqa: E402
from scripts.sofa.measure_tennis_outcome_model import (  # noqa: E402
    load as load_tennis,
)
from scripts.sofa.measure_tennis_outcome_model import score_code  # noqa: E402

TARGET = "config/sofa_confidence_calibration.json"
PRINT_FLOOR = 0.70
DAY = 86400
GROUPS = ("football_incidents", "tennis_sets", "card_halves")
# Markets whose OVER and UNDER are one question asked of either player.
SYMMETRIC = frozenset({SET1_WON_FOR, SET2_WON_FOR})
ROW_FIELDS = ("key", "market", "direction", "subject", "line", "p", "y",
              "event_id", "ts", "date", "klass", "link", "competition_id")
_FG_RECORD = {"1": FIRST_GOAL_HOME, "2": FIRST_GOAL_AWAY, "nikt": FIRST_GOAL_NONE}


def note(msg: str) -> None:
    stamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", file=sys.stderr, flush=True)


def day_ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def iso_day(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 1. copies


def _copy(source: str, target: Path, script: str) -> None:
    """Run `script` against the live DB attached read-only as `live` into a
    fresh file, then move it into place (an interrupted copy leaves none)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        conn.execute("ATTACH DATABASE ? AS live", (f"file:{source}?mode=ro",))
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()
    tmp.replace(target)


def copy_football(source: str, history_pkl: Path, out: Path) -> tuple[Path, Path]:
    db, pkl = out / "incidents.db", out / "football_history.pkl"
    if not db.exists():
        note(f"copying incident lists into {db}")
        _copy(source, db, """
            CREATE TABLE sofa_event_stats AS
                SELECT sofascore_event_id, incidents_json
                FROM live.sofa_event_stats WHERE incidents_json IS NOT NULL;
            CREATE INDEX s_id ON sofa_event_stats (sofascore_event_id);
        """)
    if not pkl.exists():
        note(f"copying {history_pkl} into {pkl}")
        tmp = pkl.with_suffix(".tmp")
        shutil.copyfile(history_pkl, tmp)
        tmp.replace(pkl)
    return db, pkl


def copy_tennis(source: str, out: Path) -> Path:
    db = out / "tennis.db"
    if not db.exists():
        note(f"copying tennis listings into {db}")
        _copy(source, db, f"""
            CREATE TABLE sofa_entity_events AS
                SELECT * FROM live.sofa_entity_events
                WHERE kind = 'last'
                  AND events_json LIKE '%"slug": "tennis"%';
            CREATE TABLE {LISTED_EVENT} AS
                SELECT * FROM live.{LISTED_EVENT} WHERE sport = 'tennis';
            CREATE INDEX le_sport ON {LISTED_EVENT} (sport, fetched_at, event_id);
            CREATE INDEX le_id ON {LISTED_EVENT} (event_id);
            CREATE TABLE {LISTING_EVENT} AS
                SELECT m.* FROM live.{LISTING_EVENT} m
                JOIN {LISTED_EVENT} e USING (event_id);
        """)
    return db


# ---------------------------------------------------------------- 2. replays


def _row(key_market: str, direction: str, subject: str, line: float, p: float,
         y: int, event_id: int, ts: int, klass: str, link: str,
         comp: int | str) -> dict[str, Any]:
    return {"key": direction_key(key_market, direction), "market": key_market,
            "direction": direction, "subject": subject, "line": line,
            "p": round(p, 6), "y": y, "event_id": event_id, "ts": ts,
            "date": iso_day(ts), "klass": klass, "link": link,
            "competition_id": comp}


def replay_football(history: Sequence[fr.FootballResult],
                    records: Mapping[int, IncidentRecord], end: int,
                    nb_r: float) -> list[dict[str, Any]]:
    """One row per (match, selection) SHEET would price, as of the match's
    UTC day: the book and the rates hold only earlier days' matches."""
    book = fr.RatingBook(shared_league_link=True)
    book.unit_strength_from_parent = False
    # --cup-strength (epochs.FOOTBALL_CUP_STRENGTH)
    apply_cup_strength(book, dc_fit.CUP)
    rates = IncidentRates({}, {}, {})
    rows: list[dict[str, Any]] = []
    pending: list[fr.FootballResult] = []
    current = -1
    for res in history:
        if res.ts >= end:
            break
        day = res.ts - res.ts % DAY
        if day != current:
            for done in pending:
                book.update(done)
                rec_done = records.get(done.event_id)
                if rec_done is not None and rec_done.full_feed:
                    rates.add(done.competition_id, done.women, rec_done)
            pending = []
            current = day
        pending.append(res)
        rec = records.get(res.event_id)
        if rec is None or res.values.get("goals_for") is None:
            continue
        klass = CLASS_WOMEN if res.women else ""
        fc = fr.FootballForecast(book, res.competition_id, res.home_id, res.away_id)
        home = fc.centre("goals_for", "side_a")
        away = fc.centre("goals_for", "side_b")
        if home is not None and away is not None:
            try:
                probs = first_goal_probs(home[0], away[0], nb_r)
            except ValueError:
                probs = {}
            link = fc.fixture_link() if probs else ""
            for subject in FG_SUBJECTS:
                if subject not in probs or outside_model_resolution(probs[subject]):
                    continue
                rows.append(_row(FIRST_GOAL, "OVER", subject, 0.5, probs[subject],
                                 int(rec.first_goal == _FG_RECORD[subject]),
                                 res.event_id, res.ts, klass, link,
                                 res.competition_id))
        for market, pair in ((RED_CARDS, rec.red_cards), (PENALTIES, rec.penalties)):
            if pair is None:
                continue
            total = pair[0] + pair[1]
            for line in COUNT_LINES:
                p_over = rates.p_over(market, res.competition_id, line)
                if p_over is None:
                    continue
                for direction, p, y in (("OVER", p_over, int(total > line)),
                                        ("UNDER", 1.0 - p_over, int(total < line))):
                    if outside_model_resolution(p):
                        continue
                    rows.append(_row(market, direction, "", line, p, y,
                                     res.event_id, res.ts, klass, "",
                                     res.competition_id))
    return rows


def card_half_keys() -> tuple[str, ...]:
    """Every "<market>|<direction>" key the card-halves replay writes."""
    keys: list[str] = []
    for market in sorted(fch.MARKETS):
        directions = (("OVER",) if market in fch.CARD_JOINT_MARKETS
                      else ("OVER", "UNDER"))
        keys += [direction_key(market, d) for d in directions]
    return tuple(keys)


def replay_card_halves(history: Sequence[fr.FootballResult],
                       records: Mapping[int, Any], start: int, end: int
                       ) -> list[dict[str, Any]]:
    """One row per (match, selection) SHEET would price for the card halves
    and the side / half events, as of the match's UTC day (the book and the
    rates hold only earlier days' matches). `records` are
    measure_football_card_halves.CardRec (halves = metrics.
    calculate_cards_points_by_half; events = read_incidents, full feed)."""
    book = fr.RatingBook(shared_league_link=True)
    book.unit_strength_from_parent = False
    apply_cup_strength(book, dc_fit.CUP)
    rates = fch.CardHalfRates()
    rows: list[dict[str, Any]] = []
    pending: list[fr.FootballResult] = []
    current = -1

    def add(market: str, direction: str, subject: str, line: float, p: float,
            y: int, res: fr.FootballResult, klass: str, link: str) -> None:
        if outside_model_resolution(p):
            return
        rows.append(_row(market, direction, subject, line, p, y, res.event_id,
                         res.ts, klass, link, res.competition_id))

    for res in history:
        if res.ts >= end:
            break
        day = res.ts - res.ts % DAY
        if day != current:
            for done in pending:
                book.update(done)
                rd = records.get(done.event_id)
                if rd is None:
                    continue
                if rd.halves is not None:
                    rates.add_cards(done.competition_id, done.women, rd.halves)
                if (rd.reds is not None and rd.reds_1h is not None
                        and rd.pens is not None and rd.pens_1h is not None):
                    rates.add_events(done.competition_id, done.women, rd.reds,
                                     rd.reds_1h, rd.pens, rd.pens_1h)
            pending = []
            current = day
        pending.append(res)
        rec = records.get(res.event_id)
        if rec is None or res.ts < start:
            continue
        klass = CLASS_WOMEN if res.women else ""
        comp = res.competition_id
        if rec.halves is not None and res.values.get("cards_points_for") is not None:
            fc = fr.FootballForecast(book, comp, res.home_id, res.away_id,
                                     rated_scope=fr.RATED_SCOPE_MARKETS)
            ca = fc.centre("cards_points_for", "side_a")
            cb = fc.centre("cards_points_for", "side_b")
            if ca is not None and cb is not None:
                link = fc.fixture_link()
                for half in (1, 2):
                    share = rates.half_share(comp, half)
                    if share is None:
                        continue
                    ya, yb = rec.halves[half - 1]
                    tot_m = fch.CARDS_1H_TOTAL if half == 1 else fch.CARDS_2H_TOTAL
                    for_m = fch.CARDS_1H_FOR if half == 1 else fch.CARDS_2H_FOR
                    most_m = fch.MOST_1H if half == 1 else fch.MOST_2H
                    hcp_m = fch.HCP_1H if half == 1 else fch.HCP_2H
                    cen = (ca[0], cb[0])
                    for line in fch.CARD_TOTAL_LINES[half]:
                        p = fch.card_half_p(tot_m, None, "", line, cen, share)
                        if p is None:
                            continue
                        y = int(ya + yb > line)
                        add(tot_m, "OVER", "", line, p, y, res, klass, link)
                        add(tot_m, "UNDER", "", line, 1 - p, 1 - y, res, klass, link)
                    for side, val in (("side_a", ya), ("side_b", yb)):
                        for line in fch.CARD_SIDE_LINES:
                            p = fch.card_half_p(for_m, side, side, line, cen, share)
                            if p is None:
                                continue
                            y = int(val > line)
                            add(for_m, "OVER", side, line, p, y, res, klass, link)
                            add(for_m, "UNDER", side, line, 1 - p, 1 - y, res,
                                klass, link)
                        for line in fch.HCP_LINES:
                            p = fch.card_half_p(hcp_m, side, side, line, cen, share)
                            if p is None:
                                continue
                            margin = (ya - yb) if side == "side_a" else (yb - ya)
                            add(hcp_m, "OVER", side, line, p, int(margin > -line),
                                res, klass, link)
                    for subject, won in (("1", ya > yb), ("2", yb > ya),
                                         (DERIVED_DRAW_SUBJECT, ya == yb)):
                        p = fch.card_half_p(most_m, None, subject, 0.0, cen, share)
                        if p is not None:
                            add(most_m, "OVER", subject, 0.0, p, int(won), res,
                                klass, link)
        if (rec.reds is None or rec.reds_1h is None or rec.pens is None
                or rec.pens_1h is None):
            continue
        events: list[tuple[str, str, int]] = [
            (fch.RED_1H_TOTAL, "", sum(rec.reds_1h)),
            (fch.PEN_1H_TOTAL, "", sum(rec.pens_1h)),
            (fch.BOTH_RED, "", int(rec.reds[0] >= 1 and rec.reds[1] >= 1)),
        ]
        for i, side in ((0, "side_a"), (1, "side_b")):
            events += [(fch.RED_FOR, side, rec.reds[i]),
                       (fch.RED_1H_FOR, side, rec.reds_1h[i]),
                       (fch.PEN_FOR, side, rec.pens[i]),
                       (fch.PEN_1H_FOR, side, rec.pens_1h[i])]
        for market, subject, value in events:
            for line in fch.EVENT_LINES.get(market, fch.DEFAULT_EVENT_LINES):
                p = rates.p_over(market, comp, line)
                if p is None:
                    continue
                y = int(value > line)
                add(market, "OVER", subject, line, p, y, res, klass, "")
                add(market, "UNDER", subject, line, 1 - p, 1 - y, res, klass, "")
    return rows


def replay_tennis(history: Sequence[tr.TennisResult],
                  meta: Mapping[int, tuple[str, str]], start: int, end: int
                  ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    loaded = tr.load_coefficients()
    if loaded is None:
        raise RuntimeError("no config/tennis_rating.json")
    coefficients, cfg = loaded
    rating = tr.AsOfRating(history, coefficients, cfg["features"], True,
                           cfg.get("tier_start"))
    rows: list[dict[str, Any]] = []
    skips: dict[str, int] = defaultdict(int)
    for r in history:
        if r.ts < start:
            continue
        if r.ts >= end:
            break
        day = r.ts - r.ts % DAY
        cat = meta.get(r.event_id, ("", ""))[0]
        klass = match_class("tennis", cat)
        if klass == CLASS_TENNIS_TEAM_CUP:
            skips["team_cup"] += 1
            continue
        if not r.completed:
            skips["not_completed"] += 1
            continue
        won = max(sum(a > b for a, b in r.sets), sum(b > a for a, b in r.sets))
        if won != 2 or len(r.sets) > 3:
            skips["best_of_five"] += 1
            continue
        fc = rating.model_at(day).forecast(
            r.home_id, r.away_id, cat, r.surface, datetime.fromtimestamp(r.ts, UTC))
        if fc is None or not fc.neighbours_home:
            skips["unrated"] += 1
            continue
        pool = fc.neighbours_home
        k = klass or ""
        for idx, market in ((1, SET1_WON_FOR), (2, SET2_WON_FOR)):
            p_home = set_win_p(pool, idx)
            if p_home is None:
                continue
            games = r.sets[idx - 1]
            y_home = int(games[0] > games[1])
            for direction, p, y in (("OVER", p_home, y_home),
                                    ("UNDER", 1.0 - p_home, 1 - y_home)):
                if outside_model_resolution(p):
                    continue
                rows.append(_row(market, direction, "home", 0.5, p, y,
                                 r.event_id, r.ts, k, fc.table_scope, r.tier))
        probs = score_probs(pool)
        if probs is not None:
            code = score_code(r.sets)
            for i, score in enumerate(SCORES):
                p = probs[score]
                if outside_model_resolution(p):
                    continue
                rows.append(_row(SET_SCORE, "OVER", f"home {score}", 0.5, p,
                                 int(i == code), r.event_id, r.ts, k,
                                 fc.table_scope, r.tier))
    return rows, dict(skips)


# ---------------------------------------------------------------- 3. curves


def selections(rows: Iterable[Mapping[str, Any]], key: str
               ) -> list[tuple[float, int]]:
    """(p, y) of the rows a key's curve is fitted on: its own rows, or for a
    symmetric market the rows of both directions."""
    market = key.split("|", 1)[0]
    if market in SYMMETRIC:
        return [(float(r["p"]), int(r["y"])) for r in rows if r["market"] == market]
    return [(float(r["p"]), int(r["y"])) for r in rows if r["key"] == key]


def fit_curve(sel: Sequence[tuple[float, int]],
              floor: int = MIN_MARKET_BUCKET) -> dict[str, dict[str, Any]]:
    """fit_confidence.curve: bucket -> n, realised, realised_lo95."""
    hits: dict[int, list[int]] = defaultdict(list)
    for p, y in sel:
        hits[bucket_of(min(max(p, 0.0), 1.0))].append(y)
    out: dict[str, dict[str, Any]] = {}
    for b, ys in sorted(hits.items()):
        if len(ys) < floor:
            continue
        k, n = sum(ys), len(ys)
        out[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"] = {
            "n": n, "realised": round(k / n, 4),
            "realised_lo95": round(wilson_lo(k, n), 4)}
    return out


def curve_at(curve: Mapping[str, Mapping[str, Any]], p: float) -> float | None:
    """Calibration._find: the bucket's realised_lo95 at p, or None."""
    for key, entry in curve.items():
        lo, hi = (float(x) for x in key.split("-"))
        if lo <= p < hi:
            return float(entry["realised_lo95"])
    return None


def gate(train: Sequence[tuple[float, int]], holdout: Sequence[tuple[float, int]]
         ) -> dict[str, Any]:
    """The registered bar: holdout selections whose train-curve value is >=
    PRINT_FLOOR, |realised - mean curve value| <= MAX_GAP with n >=
    MIN_SETTLED."""
    curve = fit_curve(train)
    by_bucket: dict[str, list[tuple[float, float, int]]] = defaultdict(list)
    for p, y in holdout:
        conf = curve_at(curve, p)
        if conf is None or conf < PRINT_FLOOR:
            continue
        b = bucket_of(p)
        by_bucket[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"].append((p, conf, y))

    def cell(xs: Sequence[tuple[float, float, int]]) -> dict[str, Any]:
        n = len(xs)
        conf = sum(c for _, c, _ in xs) / n
        real = sum(y for _, _, y in xs) / n
        return {"n": n, "mean_p": round(sum(p for p, _, _ in xs) / n, 4),
                "curve": round(conf, 4), "realised": round(real, 4),
                "gap_pp": round(100.0 * (real - conf), 2)}

    everything = [x for xs in by_bucket.values() for x in xs]
    pooled = cell(everything) if everything else None
    n = len(everything)
    gap = (sum(y - c for _, c, y in everything) / n) if everything else None
    two_sided = gate_mod.two_sided_pass(n, gap)
    if gap is None or n < MIN_SETTLED:
        passed, reason = False, f"n < {MIN_SETTLED}"
    elif not gate_mod.one_sided_pass(n, gap):
        passed, reason = False, f"overstates: gap < -{100.0 * MAX_GAP:g} pp"
    else:
        passed, reason = True, "PASS"
    return {"pass": passed, "reason": reason, "rule": gate_mod.RULE,
            "two_sided_pass": two_sided, "train_n": len(train),
            "holdout_n": len(holdout), "ge_070": pooled,
            "buckets": {k: cell(v) for k, v in sorted(by_bucket.items())},
            "train_curve": curve}


def build(rows: Sequence[Mapping[str, Any]], keys: Sequence[str],
          classes: Sequence[str], train_before: int, holdout_to: int,
          final_before: int, curve_rows: Any) -> dict[str, Any]:
    """Gate every key (main and per class) and refit the passing ones."""
    usable = [r for r in rows if curve_rows(r)]
    train = [r for r in usable if int(r["ts"]) < train_before]
    hold = [r for r in usable if train_before <= int(r["ts"]) < holdout_to]
    final = [r for r in usable if int(r["ts"]) < final_before]
    out: dict[str, Any] = {"by_market_direction": {}, "by_class": {}, "gate": {}}
    for key in keys:
        g = gate(selections(train, key),
                 selections([r for r in hold if not r["klass"]], key))
        g["symmetric"] = key.split("|", 1)[0] in SYMMETRIC
        out["gate"][key] = g
        if g["pass"]:
            curve = fit_curve(selections(final, key))
            if _final_ok(g, curve):
                out["by_market_direction"][key] = curve
    for klass in classes:
        def of(rs: Sequence[Mapping[str, Any]], k: str = klass
               ) -> list[Mapping[str, Any]]:
            return [r for r in rs if r["klass"] == k]
        for key in keys:
            g = gate(selections(of(train), key), selections(of(hold), key))
            g["symmetric"] = key.split("|", 1)[0] in SYMMETRIC
            out["gate"][f"{klass}:{key}"] = g
            if g["pass"]:
                curve = fit_curve(selections(of(final), key))
                if _final_ok(g, curve):
                    section = out["by_class"].setdefault(
                        klass, {"by_market_direction": {}})
                    section["by_market_direction"][key] = curve
    return out


def _final_ok(g: dict[str, Any], curve: Mapping[str, Mapping[str, Any]]) -> bool:
    """new_market_gate.require_final in this script's verdict shape."""
    if not gate_mod.final_reaches_floor(curve):
        g["pass"] = False
        g["reason"] = f"final curve has no bucket with realised_lo95 >= {PRINT_FLOOR}"
    return bool(g["pass"])


# ---------------------------------------------------------------- report


def render(group: str, doc: Mapping[str, Any]) -> str:
    ff = doc["fitted_from"]
    lines = [
        f"# Bramka krzywych: {group}", "",
        f"Trening: wiersze przed {ff['train_before']}; holdout "
        f"{ff['train_before']} .. {ff['holdout_to']} (wyłącznie); krzywa "
        f"końcowa: wiersze przed {ff['final_before']}. Bramka (jednostronna, "
        "decyzja operatora 2026-10-14): selekcje holdoutu z wartością krzywej "
        "treningowej (realised_lo95 kubełka) >= 0,70, n >= "
        f"{MIN_SETTLED}, realizacja - średnia wartość krzywej >= "
        f"-{100 * MAX_GAP:g} pp (odpada tylko zawyżająca krzywa); kolumna "
        "„dwustronna” = dawna reguła |luka| <= 2 pp, tylko dla porównania. "
        "Klucz główny oceniany na holdoucie bez klasy, klucz klasy na jej "
        "holdoucie.", "",
        f"Wiersze: {ff['rows']}; użyte w krzywych: {ff['curve_rows']}.", "",
        "| klasa | klucz | n trening | n holdout >= 0,70 | krzywa | realizacja "
        "| luka pp | wynik | dwustronna |", "|---|---|---|---|---|---|---|---|---|"]

    def line(klass: str, key: str, g: Mapping[str, Any]) -> str:
        c = g["ge_070"]
        two = "PASS" if g.get("two_sided_pass") else "FAIL"
        if c is None:
            return (f"| {klass} | {key} | {g['train_n']} | 0 | - | - | - | "
                    f"FAIL ({g['reason']}) | {two} |")
        return (f"| {klass} | {key} | {g['train_n']} | {c['n']} | "
                f"{c['curve']:.4f} | {c['realised']:.4f} | {c['gap_pp']:+.2f} | "
                f"{'PASS' if g['pass'] else 'FAIL'} ({g['reason']}) | {two} |")

    def split(gk: str) -> tuple[str, str]:
        klass, _, key = gk.rpartition(":")
        return klass or "-", key

    for gk, g in doc["gate"].items():
        lines.append(line(*split(gk), g))
    lines += ["", "## Kubełki holdoutu (>= 0,70)", ""]
    for gk, g in doc["gate"].items():
        if not g["buckets"]:
            continue
        lines += [f"**{' '.join(split(gk))}**", "",
                  "| kubełek | n | śr. p | krzywa | realizacja | luka pp |",
                  "|---|---|---|---|---|---|"]
        for b, c in g["buckets"].items():
            lines.append(f"| {b} | {c['n']} | {c['mean_p']:.4f} | "
                         f"{c['curve']:.4f} | {c['realised']:.4f} | "
                         f"{c['gap_pp']:+.2f} |")
        lines.append("")
    passing = list(doc["by_market_direction"])
    lines += ["## Krzywe końcowe (tylko przechodzące klucze)", "",
              f"by_market_direction: {', '.join(passing) or 'brak'}"]
    for klass, sec in doc["by_class"].items():
        lines.append(f"by_class.{klass}: "
                     f"{', '.join(sec['by_market_direction']) or 'brak'}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_group(out: Path, group: str, rows: list[dict[str, Any]],
                built: dict[str, Any], stamp: dict[str, Any]) -> dict[str, Any]:
    with (out / "rows.csv.tmp").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ROW_FIELDS))
        w.writeheader()
        w.writerows(rows)
    (out / "rows.csv.tmp").replace(out / "rows.csv")
    doc = {"target": TARGET, "fitted_from": stamp, **built}
    write_atomic(out / "curves.json", json.dumps(doc, indent=1) + "\n")
    write_atomic(out / "gate_report.md", render(group, doc))
    return doc


def run_football(args: argparse.Namespace, source: str) -> dict[str, Any]:
    out = Path(args.out_root) / "football_incidents"
    db, pkl = copy_football(source, Path(args.history), out)
    import pickle
    _fp, history = pickle.loads(pkl.read_bytes())
    history = list(history)
    note(f"football history {len(history)} matches")
    final_before = day_ts(args.final_before)
    wanted = {r.event_id: r.values["goals_for"] for r in history
              if "goals_for" in r.values and r.ts < final_before}
    records = load_records(str(db), wanted)
    nb_r = load_result_config().nb_r
    rows = replay_football(history, records, final_before, nb_r)
    note(f"football rows {len(rows)}")
    keys = (direction_key(FIRST_GOAL, "OVER"),
            direction_key(RED_CARDS, "OVER"), direction_key(RED_CARDS, "UNDER"),
            direction_key(PENALTIES, "OVER"), direction_key(PENALTIES, "UNDER"))

    usable = football_usable
    built = build(rows, keys, (CLASS_WOMEN,), day_ts(args.train_before),
                  day_ts(args.holdout_to), final_before, usable)
    stamp = {
        "script": "scripts/sofa/fit_incident_set_curves.py",
        "group": "football_incidents",
        "db_path": str(db), "history_pickle": str(pkl),
        "history_pickle_source_mtime_utc": datetime.fromtimestamp(
            Path(args.history).stat().st_mtime, UTC).isoformat(timespec="seconds"),
        "source_db": source,
        "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "train_before": args.train_before, "holdout_to": args.holdout_to,
        "final_before": args.final_before,
        "first_row_date": min((r["date"] for r in rows), default=None),
        "rows": len(rows), "curve_rows": sum(1 for r in rows if usable(r)),
        "incident_records": len(records),
        "estimator": ("football_incidents.first_goal_probs on "
                      "FootballForecast.centre(goals_for) of the day-cut "
                      f"RatingBook (shared league link), NB r {nb_r}; "
                      "IncidentRates.p_over of full-feed matches before the day "
                      "(BASE_M 30, MIN_GENDER_MATCHES 200), lines 0.5 / 1.5"),
        "excluded_from_curves": "first_goal rows of an UNLINKED fixture "
                                "(CONFIDENCE refuses CROSS_LEAGUE_UNLINKED)",
        "unfitted_constants": ["FOOTBALL_INCIDENT_BASE_M"],
        "min_market_bucket": MIN_MARKET_BUCKET,
    }
    return write_group(out, "football_incidents", rows, built, stamp)


def run_card_halves(args: argparse.Namespace, source: str) -> dict[str, Any]:
    from scripts.sofa.measure_football_card_halves import (
        load_records as load_card_records,
    )
    out = Path(args.out_root) / "card_halves"
    out.mkdir(parents=True, exist_ok=True)
    # the football_incidents copy: incident lists + the history pickle
    db, pkl = copy_football(source, Path(args.history),
                            Path(args.out_root) / "football_incidents")
    import pickle
    _fp, history = pickle.loads(pkl.read_bytes())
    history = list(history)
    note(f"football history {len(history)} matches")
    final_before = day_ts(args.final_before)
    records = load_card_records(str(db), history)
    rows = replay_card_halves(history, records, day_ts(args.card_from), final_before)
    note(f"card-halves rows {len(rows)}")
    keys = card_half_keys()
    built = build(rows, keys, (CLASS_WOMEN,), day_ts(args.train_before),
                  day_ts(args.holdout_to), final_before, football_usable)
    stamp = {
        "script": "scripts/sofa/fit_incident_set_curves.py",
        "group": "card_halves",
        "db_path": str(db), "history_pickle": str(pkl),
        "history_pickle_source_mtime_utc": datetime.fromtimestamp(
            Path(args.history).stat().st_mtime, UTC).isoformat(timespec="seconds"),
        "source_db": source,
        "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows_from": args.card_from,
        "train_before": args.train_before, "holdout_to": args.holdout_to,
        "final_before": args.final_before,
        "first_row_date": min((r["date"] for r in rows), default=None),
        "rows": len(rows), "curve_rows": sum(1 for r in rows if football_usable(r)),
        "incident_records": len(records),
        "estimator": ("football_card_halves.card_half_p: NB card points per "
                      "side on FootballForecast.centre(cards_points_for) of the "
                      "day-cut RatingBook (shared league link, cup strength, "
                      "rated scope) x CardHalfRates.half_share (SHARE_M "
                      f"{fch.SHARE_M:g}), r {fch.HALF_NB_R}; events "
                      "CardHalfRates.p_over (BASE_M 30, MIN_GENDER_MATCHES 200)"),
        "excluded_from_curves": "card rows of an UNLINKED fixture "
                                "(CONFIDENCE refuses CROSS_LEAGUE_UNLINKED)",
        "unfitted_constants": list(fch.UNFITTED_CONSTANTS),
        "min_market_bucket": MIN_MARKET_BUCKET,
    }
    return write_group(out, "card_halves", rows, built, stamp)


def run_tennis(args: argparse.Namespace, source: str) -> dict[str, Any]:
    out = Path(args.out_root) / "tennis_sets"
    db = copy_tennis(source, out)
    history, meta = load_tennis(str(db))
    note(f"tennis history {len(history)} matches")
    final_before = day_ts(args.final_before)
    rows, skips = replay_tennis(history, meta, day_ts(args.tennis_from), final_before)
    note(f"tennis rows {len(rows)}, skips {skips}")
    keys = (direction_key(SET1_WON_FOR, "OVER"), direction_key(SET1_WON_FOR, "UNDER"),
            direction_key(SET2_WON_FOR, "OVER"), direction_key(SET2_WON_FOR, "UNDER"),
            direction_key(SET_SCORE, "OVER"))
    built = build(rows, keys, (CLASS_TENNIS_WOMEN,), day_ts(args.train_before),
                  day_ts(args.holdout_to), final_before, lambda r: True)
    loaded = tr.load_coefficients()
    stamp = {
        "script": "scripts/sofa/fit_incident_set_curves.py",
        "group": "tennis_sets", "db_path": str(db), "source_db": source,
        "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "window": [args.tennis_from, args.final_before],
        "train_before": args.train_before, "holdout_to": args.holdout_to,
        "final_before": args.final_before, "rows": len(rows),
        "curve_rows": len(rows), "matches": len({r["event_id"] for r in rows}),
        "skips": skips,
        "features": list(loaded[1]["features"]) if loaded else [],
        "estimator": ("tennis_sets.set_win_p / score_probs on the HOME "
                      "player's neighbours of AsOfRating.model_at(day) "
                      "(scoped table, tier start, live config/tennis_rating.json)"),
        "symmetric": sorted(SYMMETRIC),
        "min_market_bucket": MIN_MARKET_BUCKET,
    }
    return write_group(out, "tennis_sets", rows, built, stamp)


_INT_FIELDS = ("y", "event_id", "ts")


def read_rows(path: Path) -> list[dict[str, Any]]:
    """rows.csv as the replay wrote it (p float, y / event_id / ts int)."""
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            row: dict[str, Any] = dict(r)
            row["p"] = float(r["p"])
            row["line"] = float(r["line"])
            for f in _INT_FIELDS:
                row[f] = int(r[f])
            rows.append(row)
    return rows


GROUP_KEYS = {
    "football_incidents": (
        (direction_key(FIRST_GOAL, "OVER"), direction_key(RED_CARDS, "OVER"),
         direction_key(RED_CARDS, "UNDER"), direction_key(PENALTIES, "OVER"),
         direction_key(PENALTIES, "UNDER")), (CLASS_WOMEN,)),
    "tennis_sets": (
        (direction_key(SET1_WON_FOR, "OVER"), direction_key(SET1_WON_FOR, "UNDER"),
         direction_key(SET2_WON_FOR, "OVER"), direction_key(SET2_WON_FOR, "UNDER"),
         direction_key(SET_SCORE, "OVER")), (CLASS_TENNIS_WOMEN,)),
    "card_halves": (card_half_keys(), (CLASS_WOMEN,)),
}


def football_usable(r: Mapping[str, Any]) -> bool:
    return bool(r["link"] != fr.UNLINKED)


def regate(out_root: Path, group: str) -> dict[str, Any]:
    """Re-decide a saved run from its rows.csv under today's gate."""
    out = out_root / group
    old = json.loads((out / "curves.json").read_text(encoding="utf-8"))
    stamp = old["fitted_from"]
    rows = read_rows(out / "rows.csv")
    keys, classes = GROUP_KEYS[group]
    usable = (football_usable if group in ("football_incidents", "card_halves")
              else (lambda r: True))
    built = build(rows, keys, classes, day_ts(stamp["train_before"]),
                  day_ts(stamp["holdout_to"]), day_ts(stamp["final_before"]),
                  usable)
    stamp["regated"] = {
        "at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "rule": gate_mod.RULE, "from": "rows.csv",
        "previous_pass": sorted(k for k, g in old["gate"].items() if g.get("pass"))}
    doc = {"target": TARGET, "fitted_from": stamp, **built}
    write_atomic(out / "curves.json", json.dumps(doc, indent=1) + "\n")
    write_atomic(out / "gate_report.md", render(group, doc))
    return doc


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--group", default="all", choices=(*GROUPS, "all"))
    ap.add_argument("--out-root", default="data/refit_new_markets_2026-10-15")
    ap.add_argument("--history", default="data/cache/football_history.pkl")
    ap.add_argument("--train-before", default="2026-09-01")
    ap.add_argument("--holdout-to", default="2026-10-14")
    ap.add_argument("--final-before", default="2026-10-15")
    ap.add_argument("--tennis-from", default="2026-04-01")
    ap.add_argument("--card-from", default="2025-08-01",
                    help="card_halves: the first day a row is written")
    ap.add_argument("--regate", action="store_true",
                    help="no copy, no replay: re-gate the saved rows.csv")
    ap.add_argument("--cup-strength", nargs="?", const="", default=None,
                    metavar="CONFIG", help="the football book with the cup "
                    "league strength (fit_double_chance_curve.set_cup)")
    args = ap.parse_args(argv)
    dc_fit.set_cup(args.cup_strength)
    if args.regate:
        result = {}
        for group in GROUPS:
            if args.group in (group, "all"):
                doc = regate(Path(args.out_root), group)
                result[group] = {k: g["pass"] for k, g in doc["gate"].items()}
        print(json.dumps(result, indent=1))
        return 0
    source = str(SofaConfig.from_env().db_path)
    t0 = time.time()
    summary: dict[str, Any] = {}
    for group in GROUPS:
        if args.group not in (group, "all"):
            continue
        runner = {"football_incidents": run_football, "tennis_sets": run_tennis,
                  "card_halves": run_card_halves}[group]
        doc = runner(args, source)
        summary[group] = {k: g["pass"] for k, g in doc["gate"].items()}
        note(f"{group} done ({time.time() - t0:.0f}s)")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise SystemExit(2) from exc
