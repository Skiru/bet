#!/usr/bin/env python3
"""Does a football sample corrected for its opponents and domain predict better?

Audit 2026-10-13 B15 with A5 (Part 6 W1, W4, W7). Test registered before the
run in docs/sofa/evidence/sample_opponent_correction_2026-10-13.md.

  history  Test H: one step ahead on the cached history. Each side's last ten
           matches with the statistic (as SAMPLES picks them), read raw (T),
           corrected for the opponent and domain (C - bet.sofa.opponent_
           correction, the code SHEET runs), the opponent alone (O) and the
           domain alone (D). SHEET's centre (K shrink to the league, half the
           rating on a rated market), spread and family; P(OVER) on a 9-line
           ladder, calibrated per market and arm on the matches before the
           cut, log-loss after the cut (lc_all, measure_pooling.calibrated_
           losses); arm - T with a 95% interval from resampling matches.
  gates    Test G: the football rows of real days re-priced in process by
           run_sheet.process_fixture with the switch off and on, the curve's
           confidence, and the shape gates / MODEL_ABOVE_OWN_SAMPLE on the
           raw (off) and corrected (on) sample; removed vs kept legs, settled
           at Superbet's price.

Measurement only: the DB and the history pickle are read, nothing the
pipeline reads is written.

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_sample_opponent_correction.py history \\
        --out data/audit_2026-10-13/b15_history.json
    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_sample_opponent_correction.py gates \\
        --from 2026-10-09 --to 2026-10-12 --out data/audit_2026-10-13/b15_gates.json
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sqlite3
import statistics
import sys
import time
from collections import defaultdict, deque
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from bet.sofa import epochs  # noqa: E402
from bet.sofa.count_dispersion import (  # noqa: E402
    FAMILY_NB,
    Dispersion,
    DispersionTable,
)
from bet.sofa.count_dispersion import load_table as load_dispersion_table  # noqa: E402
from bet.sofa.engine import (  # noqa: E402
    sheet_count_p_raw,
    sheet_predictive_sd,
)
from bet.sofa.football_rating import (  # noqa: E402
    CROSS_RATIO_POWER,
    LINKED_BY_STRENGTH,
    UNLINKED,
    FootballForecast,
    FootballResult,
    RatingBook,
)
from bet.sofa.opponent_correction import SampleCorrector, mode_values  # noqa: E402
from bet.sofa.per_market_k import k_for_market  # noqa: E402

PICKLE = Path("/Users/mkoziol/projects/bet/data/cache/football_history.pkl")
TRAIN_FROM = "2025-10-12"
CUT = "2026-06-09"
EVAL_TO = "2026-10-12"
SAMPLE_N = 10
MIN_SAMPLE = 5
K_SPORT = 15.0
W_RATING = 0.5
P_CLIP = 0.02
REPS = 2000
SEED = 0
ARMS = ("T", "C", "O", "D", "K")
BASES = (
    "corners_for", "corners_1h_for", "corners_2h_for",
    "shots_for", "shots_1h_for", "shots_on_target_for", "shots_on_target_1h_for",
    "fouls_for", "fouls_1h_for", "cards_points_for", "offsides_for",
)
THRESHOLD_PREFIXES = ("corners_", "shots_", "fouls_")


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def load_pickle(path: Path) -> list[FootballResult]:
    _fp, history = pickle.loads(path.read_bytes())
    return list(history)


def total_of(base: str) -> str:
    return base[: -len("_for")] + "_total"


def nb_survivals(mean: float, variance: float, ks: Sequence[int]) -> list[float]:
    """engine.nb_survival at every k of `ks` (ascending) in one pass - the same
    sum, checked against the engine on the first rows of every run."""
    if mean <= 0.0:
        return [0.0 for _ in ks]
    out: list[float] = []
    if variance <= mean * (1.0 + 1e-9):
        term = math.exp(-mean)
        acc = term
        i = 0
        for k in ks:
            if k < 0:
                out.append(1.0)
                continue
            while i < k:
                i += 1
                term *= mean / i
                acc += term
            out.append(max(0.0, 1.0 - min(acc, 1.0)))
        return out
    r = mean * mean / (variance - mean)
    p = r / (r + mean)
    log_p, log_1mp, lgamma_r = math.log(p), math.log1p(-p), math.lgamma(r)
    acc = 0.0
    i = -1
    capped = False
    for k in ks:
        if k < 0:
            out.append(1.0)
            continue
        while i < k and not capped:
            i += 1
            acc += math.exp(math.lgamma(i + r) - lgamma_r - math.lgamma(i + 1)
                            + r * log_p + i * log_1mp)
            if acc >= 1.0:
                capped = True
        out.append(max(0.0, 1.0 - min(acc, 1.0)))
    return out


def ladder_p(
    market: str, centre: float, mean: float, var: float, n: int,
    lines: Sequence[float], disp: Dispersion | None,
) -> list[float]:
    sd = sheet_predictive_sd(market, "football", mean, var, n, centre, disp)
    if disp is not None and disp.family == FAMILY_NB:
        ps = nb_survivals(centre, sd * sd, [math.floor(x) for x in lines])
    else:
        ps = [sheet_count_p_raw(market, centre, sd, x, "OVER", disp) for x in lines]
    return [min(1.0 - P_CLIP, max(P_CLIP, q)) for q in ps]


def lines_for(centre: float) -> list[float]:
    """calibrate_from_cache.lines_for."""
    lowest = max(0, math.floor(centre) - 4)
    return [lowest + 0.5 + step for step in range(9)]


# ---------------------------------------------------------------------------
# Test H
# ---------------------------------------------------------------------------

class Entry:
    __slots__ = ("against", "comp", "eid", "opp", "own")

    def __init__(self, eid: int, opp: int, own: float, against: float,
                 comp: int | None = None) -> None:
        self.eid, self.opp, self.own, self.against = eid, opp, own, against
        self.comp = comp


def arm_values(
    corrector: SampleCorrector, book: RatingBook, team: int, today_opp: int,
    metric: str, sample: Sequence[Entry], total: bool,
    cup_corrector: SampleCorrector | None = None, today_comp: int | None = None,
) -> tuple[list[list[float]], int]:
    """Each arm's values (T, C, O, D, K) and how many observations C moved.
    K is C read by `cup_corrector` (cup_aware: the past match's and today's
    competitions reach the gaps; C when None)."""
    out: list[list[float]] = [[], [], [], [], []]
    moved = 0
    lf0 = corrector._gap(team, today_opp, metric)[1]
    for e in sample:
        raw = e.own + e.against if total else e.own
        out[0].append(raw)
        f = corrector.factors(team, e.opp, today_opp, metric)
        fk = (f if cup_corrector is None else cup_corrector.factors(
            team, e.opp, today_opp, metric, e.comp, today_comp))
        if fk is None:
            out[4].append(raw)
        elif total:
            out[4].append(e.own * fk[0] + e.against * fk[1])
        else:
            out[4].append(e.own * fk[0])
        if f is None:
            out[1].append(raw)
            out[2].append(raw)
            out[3].append(raw)
            continue
        rated = book.teams[(e.opp, metric)]
        linked, lfk = corrector._gap(team, e.opp, metric)
        power = 1.0 if linked else CROSS_RATIO_POWER
        g = lf0 - lfk
        fo, fa = 1.0 / rated.defence ** power, 1.0 / rated.attack ** power
        dg_o, dg_a = math.exp(g), math.exp(-g)
        if total:
            c = e.own * f[0] + e.against * f[1]
            o = e.own * fo + e.against * fa
            d = e.own * dg_o + e.against * dg_a
        else:
            c, o, d = e.own * f[0], e.own * fo, e.own * dg_o
        out[1].append(c)
        out[2].append(o)
        out[3].append(d)
        moved += abs(c - raw) > 1e-9
    return out, moved


def mean_var(values: Sequence[float]) -> tuple[float, float]:
    m = sum(values) / len(values)
    return m, (statistics.variance(values) if len(values) > 1 else 0.0)


def cmd_history(args: argparse.Namespace) -> int:
    from scripts.sofa.measure_pooling import Boot, calibrated_losses

    t0 = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - t0:7.0f}s] {msg}", flush=True)

    history = load_pickle(args.pickle)
    log(f"history {len(history)} matches")
    engine_constants = json.loads(
        (_REPO / "config" / "sofa_engine_constants.json").read_text(encoding="utf-8"))
    table: DispersionTable = load_dispersion_table()
    train_from, cut, eval_to = _ts(args.train_from), _ts(args.cut), _ts(args.to) + 86400
    book = RatingBook(shared_league_link=True)
    cup_comps: frozenset[int] = frozenset()
    if args.cup_strength is not None:
        # epochs.FOOTBALL_CUP_STRENGTH: the book SHEET holds from 2026-10-16
        from bet.sofa.cup_strength import apply as apply_cup
        from bet.sofa.cup_strength import load as load_cup
        cup = load_cup(args.cup_strength)
        apply_cup(book, cup)
        cup_comps = cup.competitions
    bases = tuple(args.bases) if args.bases else BASES
    samples: dict[tuple[int, str], deque[Entry]] = defaultdict(
        lambda: deque(maxlen=SAMPLE_N))
    markets = [m for b in bases for m in (b, total_of(b))]
    m_index = {m: i for i, m in enumerate(markets)}
    rows_p: list[np.ndarray] = []
    rows_o: list[np.ndarray] = []
    meta: dict[str, list[int]] = {k: [] for k in ("ev", "mk", "train", "cross",
                                                   "moved", "n", "cup")}
    se: list[list[float]] = []
    checked = 0
    i = 0
    nh = len(history)
    while i < nh:
        ts = history[i].ts
        j = i
        while j < nh and history[j].ts == ts:
            j += 1
        group = history[i:j]
        if train_from <= ts < eval_to:
            corrector = SampleCorrector(book)
            cup_corrector = SampleCorrector(book, cup_aware=True)
            for r in group:
                if book.link(r.home_id, r.away_id, "goals_for")[0] == UNLINKED:
                    continue
                fc = FootballForecast(book, r.competition_id, r.home_id, r.away_id)
                for base in bases:
                    pair = r.values.get(base)
                    if pair is None:
                        continue
                    sides = []
                    for team, opp, y, reserve, side in (
                        (r.home_id, r.away_id, pair[0], r.home_reserve, "side_a"),
                        (r.away_id, r.home_id, pair[1], r.away_reserve, "side_b"),
                    ):
                        smp = list(samples.get((team, base), ()))
                        sides.append((team, opp, y, reserve, side, smp))
                    rates = book.league_rates(r.competition_id, base)
                    units: list[
                        tuple[str, float, list[list[float]], int, str | None]] = []
                    for team, opp, y, reserve, side, smp in sides:
                        if reserve or len(smp) < MIN_SAMPLE:
                            continue
                        vals, moved = arm_values(corrector, book, team, opp, base,
                                                 smp[::-1], False, cup_corrector,
                                                 r.competition_id)
                        units.append((base, y, vals, moved, side))
                    if all(not s[3] and len(s[5]) >= MIN_SAMPLE for s in sides):
                        a_vals, a_moved = arm_values(
                            corrector, book, sides[0][0], sides[0][1], base,
                            sides[0][5][::-1], True, cup_corrector,
                            r.competition_id)
                        seen = {e.eid for e in sides[0][5]}
                        b_smp = [e for e in sides[1][5][::-1] if e.eid not in seen]
                        b_vals, b_moved = arm_values(
                            corrector, book, sides[1][0], sides[1][1], base,
                            b_smp, True, cup_corrector, r.competition_id)
                        units.append((total_of(base), pair[0] + pair[1],
                                      [a + b for a, b in zip(a_vals, b_vals,
                                                             strict=True)],
                                      a_moved + b_moved, None))
                    status = book.link(r.home_id, r.away_id, base)[0]
                    for market, y, vals, moved, uside in units:
                        n = len(vals[0])
                        if all(v == 0.0 for v in vals[0]):
                            continue
                        if rates is None:
                            prior = None
                        else:
                            prior = (rates[0] + rates[1]) if uside is None else (
                                (rates[0] + rates[1]) / 2.0)
                        k = k_for_market(engine_constants, "football", market, K_SPORT)
                        rated = fc.centre(market, uside)
                        disp = table.read("football", market, r.competition_id)
                        centres, mvs = [], []
                        for arm_vals in vals:
                            mean, var = mean_var(arm_vals)
                            c = (mean if prior is None
                                 else (n * mean + k * prior) / (n + k))
                            if rated is not None:
                                c = W_RATING * rated[0] + (1 - W_RATING) * c
                            centres.append(c)
                            mvs.append((mean, var))
                        lines = lines_for(centres[0])
                        ps = np.empty((len(ARMS), 9), dtype=np.float32)
                        for a in range(len(ARMS)):
                            ps[a] = ladder_p(market, centres[a], mvs[a][0], mvs[a][1],
                                             n, lines, disp)
                        if (checked < 300 and disp is not None
                                and disp.family == FAMILY_NB):
                            sd = sheet_predictive_sd(market, "football", mvs[0][0],
                                                     mvs[0][1], n, centres[0], disp)
                            for x, q in zip(lines, ps[0], strict=True):
                                ref = min(1 - P_CLIP, max(P_CLIP, sheet_count_p_raw(
                                    market, centres[0], sd, x, "OVER", disp)))
                                assert abs(ref - float(q)) < 1e-5, (ref, q)
                            checked += 1
                        rows_p.append(ps)
                        rows_o.append(np.asarray([1 if y > x else 0 for x in lines],
                                                 dtype=np.int8))
                        se.append([(c - y) ** 2 for c in centres])
                        meta["ev"].append(r.event_id)
                        meta["mk"].append(m_index[market])
                        meta["train"].append(1 if ts < cut else 0)
                        meta["cross"].append(1 if status == LINKED_BY_STRENGTH else 0)
                        meta["moved"].append(moved)
                        meta["n"].append(n)
                        meta["cup"].append(1 if r.competition_id in cup_comps
                                           or any(e.comp in cup_comps
                                                  for s in sides for e in s[5])
                                           else 0)
        for r in group:
            for base in bases:
                pair = r.values.get(base)
                if pair is None:
                    continue
                if not r.home_reserve:
                    samples[(r.home_id, base)].append(
                        Entry(r.event_id, r.away_id, pair[0], pair[1],
                              r.competition_id))
                if not r.away_reserve:
                    samples[(r.away_id, base)].append(
                        Entry(r.event_id, r.home_id, pair[1], pair[0],
                              r.competition_id))
            book.update(r)
        if (i // 200_000) != (j // 200_000):
            log(f"match {j}/{nh} rows {len(rows_p)}")
        i = j
    log(f"scored rows {len(rows_p)} (engine check on {checked})")
    p = np.stack(rows_p)
    o = np.stack(rows_o)
    m = {k: np.asarray(v) for k, v in meta.items()}
    train = m["train"] == 1
    loss = {"p": p, "o": o, "hi": np.ones_like(o, dtype=bool)}
    lc_all, _ = calibrated_losses(loss, train, ~train, m["mk"])
    ll = -(o[:, None, :] * np.log(p) + (1 - o[:, None, :]) * np.log(1 - p)).sum(axis=2)
    sea = np.asarray(se)
    ev = ~train
    boot = Boot(m["ev"][ev].astype(np.int64), reps=args.reps, seed=SEED)
    lc_e, ll_e, se_e = lc_all[ev], ll[ev], sea[ev]
    mk_e, cross_e, moved_e = m["mk"][ev], m["cross"][ev], m["moved"][ev]
    cup_e = m["cup"][ev]
    nine = np.full(int(ev.sum()), 9.0)
    ones = np.ones(int(ev.sum()))
    result: dict[str, Any] = {
        "meta": {
            "train_from": args.train_from, "cut": args.cut, "to": args.to,
            "train_rows": int(train.sum()), "eval_rows": int(ev.sum()),
            "eval_matches": int(len(np.unique(m["ev"][ev]))),
            "reps": args.reps, "seed": SEED, "engine_check_rows": checked,
            "history_pickle": str(args.pickle),
        },
        "markets": {},
    }
    for market, mi in m_index.items():
        for label, mask in (("all", mk_e == mi),
                            ("cross", (mk_e == mi) & (cross_e == 1)),
                            ("cup", (mk_e == mi) & (cup_e == 1))):
            if int(mask.sum()) < 50:
                continue
            cell: dict[str, Any] = {
                "rows": int(mask.sum()),
                "matches": int(len(np.unique(m["ev"][ev][mask]))),
                "rows_with_a_moved_obs": int((moved_e[mask] > 0).sum()),
                "T_lc_all": boot.ratio(lc_e[:, 0], nine, mask)["est"],
                "T_ll_all": boot.ratio(ll_e[:, 0], nine, mask)["est"],
            }
            for a, arm in enumerate(ARMS):
                if a == 0:
                    continue
                cell[f"{arm}-T"] = {
                    "lc_all": boot.ratio(lc_e[:, a] - lc_e[:, 0], nine, mask),
                    "ll_all": boot.ratio(ll_e[:, a] - ll_e[:, 0], nine, mask),
                    "se": boot.ratio(se_e[:, a] - se_e[:, 0], ones, mask),
                }
            cell["K-C"] = {
                "lc_all": boot.ratio(lc_e[:, 4] - lc_e[:, 1], nine, mask),
                "ll_all": boot.ratio(ll_e[:, 4] - ll_e[:, 1], nine, mask),
                "se": boot.ratio(se_e[:, 4] - se_e[:, 1], ones, mask),
            }
            result["markets"].setdefault(market, {})[label] = cell
            c = cell["C-T"]["lc_all"]
            log(f"{market:28s} {label:5s} rows {cell['rows']:6d} C-T lc "
                f"{c['est']:+.5f} [{c['lo']:+.5f}; {c['hi']:+.5f}]")
            kc = cell["K-C"]["lc_all"]
            log(f"{'':28s} {label:5s} K-C lc {kc['est']:+.5f} "
                f"[{kc['lo']:+.5f}; {kc['hi']:+.5f}]")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["meta"]))
    return 0


# ---------------------------------------------------------------------------
# Test G
# ---------------------------------------------------------------------------

def enrich(fixture_samples: Any, fixture: Any,
           by_event: dict[int, FootballResult]) -> Any:
    """Fill B13's opponent_id / against into a sample written before 10-13:
    the opponent is the other side of the cached match, `against` its count
    of the same base metric (a ``*_for`` sample only)."""
    from bet.sofa.football_rating import base_metric

    metrics = {}
    for metric, ms in fixture_samples.metrics.items():
        base = base_metric(metric) if metric.endswith("_for") else None

        def fill(obs: Any, team: int) -> Any:
            r = by_event.get(obs.sofascore_event_id)
            if r is None or team not in (r.home_id, r.away_id):
                return obs
            home = r.home_id == team
            update: dict[str, Any] = {"opponent_id": r.away_id if home else r.home_id}
            pair = r.values.get(base) if base else None
            own = None if pair is None else (pair[0] if home else pair[1])
            if pair is not None and own is not None and abs(own - obs.value) < 1e-9:
                update["against"] = float(pair[1] if home else pair[0])
            return obs.model_copy(update=update)

        side_a = [fill(o, fixture.home_entity_id) for o in ms.side_a]
        side_b = [fill(o, fixture.away_entity_id) for o in ms.side_b]
        known = {o.sofascore_event_id: o for o in side_b + side_a}
        h2h = [known.get(o.sofascore_event_id, o) for o in ms.h2h]
        metrics[metric] = ms.model_copy(
            update={"side_a": side_a, "side_b": side_b, "h2h": h2h})
    return fixture_samples.model_copy(update={"metrics": metrics})


def cmd_gates(args: argparse.Namespace) -> int:
    from pydantic import RootModel

    from bet.sofa.confidence import (
        Calibration,
        calibration_path_for,
        line_is_beyond_sample,
        mode_loses,
        model_above_own_sample,
    )
    from bet.sofa.config import SofaConfig
    from bet.sofa.contracts import Fixture, FixtureOffer, FixtureSamples, Veto
    from bet.sofa.derived import load_side_correlations
    from bet.sofa.football_rating import replay
    from bet.sofa.market_mapper import is_derived
    from bet.sofa.players import is_player_metric
    from scripts.sofa.measure_pooling import Boot
    from scripts.sofa.run_sheet import (
        day_league_observations,
        load_baselines,
        load_engine_constants,
        load_reliability,
        load_tennis_tier_baselines,
        process_fixture,
    )

    t0 = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - t0:7.0f}s] {msg}", flush=True)

    config = SofaConfig.from_env()
    history = load_pickle(args.pickle)
    by_event = {r.event_id: r for r in history}
    con = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
    legs: list[dict[str, Any]] = []
    repro: list[float] = []
    coverage: dict[str, int] = defaultdict(int)
    day = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    while day <= end:
        d = day.isoformat()
        day += timedelta(days=1)
        run = Path(config.runs_dir) / d
        if not (run / "05_sheet.json").exists():
            continue
        build_at = datetime.fromisoformat(d).replace(tzinfo=UTC) + timedelta(hours=12)
        fixtures = RootModel[list[Fixture]].model_validate_json(
            (run / "02_fixtures.json").read_bytes()).root
        samples = {s.sofascore_event_id: s for s in RootModel[list[FixtureSamples]]
                   .model_validate_json((run / "03_samples.json").read_bytes()).root}
        offers = RootModel[list[FixtureOffer]].model_validate_json(
            (run / "04_offer.json").read_bytes()).root
        vetoes = (RootModel[list[Veto]].model_validate_json(
            (run / "vetoes.json").read_bytes()).root
            if (run / "vetoes.json").exists() and (run / "vetoes.json").read_bytes()
            else [])
        settled = {
            (int(e), m, s or "", float(ln), dr): (float(p), float(odds), out)
            for e, m, s, ln, dr, p, odds, out in con.execute(
                "SELECT sofascore_event_id, market, subject, line, direction, "
                "p_central, offered_odds, outcome FROM sofa_settled_row "
                "WHERE run_date = ? AND sport = 'football' AND offered_odds "
                "IS NOT NULL AND outcome IN ('WIN', 'LOSS')", (d,))
        }
        book = replay(history, _ts(d), shared_league_link=epochs.link_shared_league(
            d, build_at))
        corrector = SampleCorrector(book)
        fx_by = {f.sofascore_event_id: f for f in fixtures}
        cal = Calibration.load(calibration_path_for(d, build_at))
        stats_only = epochs.stats_only(d, build_at)
        dispersion = (load_dispersion_table()
                      if epochs.count_dispersion_enabled(d, build_at) else None)
        kw: dict[str, Any] = {
            "stats_only": stats_only,
            "rating_prices": False,
            "marginal_centres_on": False,
            "dispersion_table": dispersion,
            "per_market_k_on": epochs.per_market_k_enabled(d, build_at),
        }
        base_args = (load_baselines(config), load_reliability(config),
                     load_engine_constants(config), vetoes, config,
                     load_side_correlations(cards_correlation=False),
                     day_league_observations(fixtures, list(samples.values())))
        tiers = load_tennis_tier_baselines(config)
        n_day = 0
        for offer in offers:
            fx = fx_by.get(offer.sofascore_event_id)
            fs = samples.get(offer.sofascore_event_id)
            if (offer.status == "NO_PRICE" or fx is None or fs is None
                    or fx.sport != "football" or fs.readiness == "BLOCKED"):
                continue
            fs = enrich(fs, fx, by_event)
            fc = FootballForecast(book, fx.competition_id, fx.home_entity_id,
                                  fx.away_entity_id)
            arms = {}
            for arm, corr in (("raw", None), ("corrected", corrector)):
                rows, _ = process_fixture(fx, fs, offer, *base_args, None, fc, tiers,
                                          sample_corrector=corr, **kw)
                arms[arm] = {(r.market, r.subject, r.line, r.direction): r
                             for r in rows
                             if not is_derived(r.market)
                             and not is_player_metric(r.market)}
            for key, raw_row in arms["raw"].items():
                cor_row = arms["corrected"].get(key)
                hit = settled.get((fx.sofascore_event_id, *key))
                if cor_row is None or hit is None:
                    continue
                p_settled, odds, outcome = hit
                repro.append(raw_row.p_central - p_settled)
                coverage["rows"] += 1
                coverage["rows_corrected"] += cor_row.corrected_sample is not None
                market, subject, line, direction = key
                ms = fs.metrics.get(market)
                if ms is None:
                    continue
                if subject:
                    side = _side(subject, fx)
                    side_obs = (ms.side_a if side == "side_a"
                                else ms.side_b if side == "side_b" else [])
                    raw_vals = [o.value for o in side_obs]
                else:
                    seen: set[int] = set()
                    raw_vals = []
                    for lst in (ms.side_a, ms.side_b, ms.h2h):
                        for o in lst:
                            if o.sofascore_event_id not in seen:
                                seen.add(o.sofascore_event_id)
                                raw_vals.append(o.value)
                for arm, row, vals in (
                    ("raw", raw_row, raw_vals),
                    ("corrected", cor_row,
                     list(cor_row.corrected_sample)
                     if cor_row.corrected_sample is not None else raw_vals),
                ):
                    found = cal.realised(market, row.p_central, "football", direction,
                                         None)
                    if found is None:
                        continue
                    conf = found[0]
                    if conf < 0.70 or conf * odds < 0.90:
                        continue
                    gate = None
                    if line_is_beyond_sample(line, direction, vals):
                        gate = "LINE_BEYOND_SAMPLE"
                    elif mode_loses(line, direction, mode_values(
                            {"corrected_sample": vals} if arm == "corrected"
                            and row.corrected_sample is not None else {}, vals)):
                        gate = "MODE_LOSES"
                    elif model_above_own_sample("football", row.p_central, vals, line,
                                                direction, market) is not None:
                        gate = "MODEL_ABOVE_OWN_SAMPLE"
                    legs.append({
                        "date": d, "eid": fx.sofascore_event_id, "market": market,
                        "subject": subject, "line": line, "direction": direction,
                        "arm": arm, "p": row.p_central, "conf": conf, "odds": odds,
                        "won": outcome == "WIN", "gate": gate,
                    })
                    n_day += arm == "raw"
        log(f"{d}: would-print raw {n_day}")
    rp = np.abs(np.asarray(repro))
    out: dict[str, Any] = {
        "meta": {"from": args.start, "to": args.end, "reps": args.reps,
                 "seed": SEED, "rows_joined": coverage["rows"],
                 "rows_with_corrected_sample": coverage["rows_corrected"],
                 "repro_abs_p_diff_median": float(np.median(rp)) if len(rp) else None,
                 "repro_share_within_0.005": float((rp < 0.005).mean())
                 if len(rp) else None},
        "arms": {},
    }
    if legs:
        ev = np.asarray([x["eid"] for x in legs], dtype=np.int64)
        boot = Boot(ev, reps=args.reps, seed=SEED)
        won = np.asarray([x["won"] for x in legs], dtype=float)
        conf_a = np.asarray([x["conf"] for x in legs])
        roi = np.asarray([(x["odds"] - 1.0) if x["won"] else -1.0 for x in legs])
        ones = np.ones(len(legs))
        arm_a = np.asarray([x["arm"] for x in legs])
        gate_a = np.asarray([x["gate"] or "" for x in legs])
        for arm in ("raw", "corrected"):
            am = arm_a == arm
            cell: dict[str, Any] = {"would_print": int(am.sum())}
            for label, mask in (
                ("kept", am & (gate_a == "")),
                ("removed", am & (gate_a != "")),
                *((g, am & (gate_a == g)) for g in (
                    "LINE_BEYOND_SAMPLE", "MODE_LOSES", "MODEL_ABOVE_OWN_SAMPLE")),
            ):
                if not mask.any():
                    cell[label] = {"n": 0}
                    continue
                cell[label] = {
                    "n": int(mask.sum()),
                    "matches": int(len(np.unique(ev[mask]))),
                    "realised_minus_conf": boot.ratio(won - conf_a, ones, mask),
                    "roi": boot.ratio(roi, ones, mask),
                }
            out["arms"][arm] = cell
            log(f"{arm}: " + json.dumps({k: (v if isinstance(v, int) else v.get("n"))
                                         for k, v in cell.items()}))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"summary": out, "legs": legs}, indent=1),
                            encoding="utf-8")
    print(json.dumps(out["meta"]))
    return 0


def _side(subject: str, fixture: Any) -> str | None:
    from scripts.sofa.run_sheet import determine_side

    return determine_side(subject, fixture)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("history")
    h.add_argument("--pickle", type=Path, default=PICKLE)
    h.add_argument("--train-from", default=TRAIN_FROM)
    h.add_argument("--cut", default=CUT)
    h.add_argument("--to", default=EVAL_TO)
    h.add_argument("--reps", type=int, default=REPS)
    h.add_argument("--out", type=Path, default=None)
    h.add_argument("--cup-strength", type=Path, default=None, metavar="CONFIG",
                   help="the book carries the cup league strength of CONFIG "
                   "(config/sofa_cup_strength.json); arm K = C read cup-aware")
    h.add_argument("--bases", nargs="+", default=None,
                   help="only these base metrics (default: all of BASES)")
    g = sub.add_parser("gates")
    g.add_argument("--pickle", type=Path, default=PICKLE)
    g.add_argument("--from", dest="start", default="2026-10-09")
    g.add_argument("--to", dest="end", default="2026-10-12")
    g.add_argument("--reps", type=int, default=REPS)
    g.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if not args.pickle.exists():
        print(f"no history pickle at {args.pickle}", file=sys.stderr)
        return 2
    return int(cmd_history(args) if args.cmd == "history" else cmd_gates(args))


if __name__ == "__main__":
    raise SystemExit(main())
