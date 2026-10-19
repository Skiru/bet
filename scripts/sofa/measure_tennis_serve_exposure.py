#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""Tennis aces / double faults: exposure, tournament and returner centres
against the centre SHEET prices with - measured on the cache replay, main
tour only, at the market-like line (read-only evidence).

Pre-registered in docs/sofa/evidence/tennis_serve_exposure_plan_2026-10-19.md
(arms, metric, population, decision rule fixed before the first run).

Arms (every one: best-of-three, SAMPLES' tennis scoping, the tier prior
run_sheet.sample_centre shrinks toward, SHEET's distribution and spread from
the RAW sample - only the centre differs):

  BASE     the centre SHEET prices with today
  ORACLE   the length-normalised sample's centre x G(match) / G-bar (the true
           games of the match: a ceiling, never shippable)
  EXP      ... x E[G] / G-bar, E[G] the mean games of the rating's neighbours
           (match, set 1, set 2), as of the match's day
  EXP_T    EXP x the tournament's factor: realised over EXP centres of the
           earlier rows of this uniqueTournament, K = 30 rows
  EXP_T_R  EXP_T x the returner's factor (bet.sofa.tennis_aces_opponent; aces)

The sample is normalised to its own mean length before it is averaged
(a_i = x_i G-bar / G_i). Length = the match's (set's) gamesWon sum - the
tie-break counts as a game, as in the neighbours' games, and unlike
serviceGamesTotal, which drops it.

Curves per arm, fitted on train rows (emit-from .. cut), read on test rows
(from cut): the bucket realised rate per market x direction (x women's class),
once over the whole replayed ladder (what CONFIDENCE reads today) and once
over the market-like lines only. The market-like line of a (match, market,
player) is the one line of the arms' common grid where the arms' mean p OVER
is nearest 0.5 - symmetric in the arms. Reported per market family, arm minus
BASE: calibrated log-loss at the market line [95% over matches], and at
calibrated confidence >= 0.70 at the market line: n, confidence, realised.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_serve_exposure.py \\
        [--emit-from 2024-07-01] [--cut 2026-01-01] [--played-cache f.pkl] \\
        [--md-out f] [--json-out f]
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pickle
import random
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import scripts.sofa.calibrate_from_cache as cc
from bet.sofa.comparability import MatchKind
from bet.sofa.confidence import match_class
from bet.sofa.config import SofaConfig
from bet.sofa.tennis_prior import TIER_PRIOR_METRICS, load_tier_baselines, tier_prior
from bet.sofa.tennis_rating import tier_group
from scripts.sofa.fit_confidence import bucket_of

ARMS = ("BASE", "ORACLE", "EXP", "EXP_T", "EXP_T_R")
# serve base -> the length base its exposure reads
SERVE = {
    "aces": "games", "double_faults": "games",
    "aces_set1": "games_set1", "aces_set2": "games_set2",
    "double_faults_set1": "games_set1", "double_faults_set2": "games_set2",
}
FAMILY = {
    "aces_for": "asy mecz", "aces_total": "asy mecz",
    "aces_set1_for": "asy sety", "aces_set1_total": "asy sety",
    "aces_set2_for": "asy sety", "aces_set2_total": "asy sety",
    "double_faults_for": "PB mecz", "double_faults_total": "PB mecz",
    "double_faults_set1_for": "PB sety", "double_faults_set1_total": "PB sety",
    "double_faults_set2_for": "PB sety", "double_faults_set2_total": "PB sety",
}
K_TOURNAMENT = 30.0
MIN_BUCKET = 50
FLOOR = 0.70
Key = tuple[int, str, str, float, str]  # event, market, subject, line, direction


def load_played(db: Path, cache: Path | None) -> list[cc.Played]:
    if cache is not None and cache.exists():
        with cache.open("rb") as fh:
            out: list[cc.Played] = pickle.load(fh)
        return out
    played = cc.load_cache(db, tennis_sets=True, tennis_serve=True, sports=("tennis",))
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("wb") as fh:
            pickle.dump(played, fh)
    return played


def expected_games(fc: Any) -> dict[str, float]:
    """The rating neighbours' mean games: match, set 1, set 2."""
    pool = fc.neighbours_home
    if not pool:
        return {}
    return {
        "games": statistics.fmean(o.games_for + o.games_against for o in pool),
        "games_set1": statistics.fmean(sum(o.set1) for o in pool),
        "games_set2": statistics.fmean(sum(o.set2) for o in pool),
    }


class Replay:
    def __init__(self, played: list[cc.Played], rating: cc.RatingReplay,
                 emit_from: int) -> None:
        self.played = played
        self.rating = rating
        self.emit_from = emit_from
        self.baselines = cc.load_baselines()
        self.constants = cc._load_engine_constants()
        self.k = cc.k_centre_for("tennis", self.constants)
        self.tiers = load_tier_baselines()
        cc.TENNIS_ACES_TIERS = self.tiers
        cc.TENNIS_SAMPLE_SCOPE = True
        # event -> {length base: total games}
        self.length: dict[int, dict[str, float]] = {}
        for m in played:
            self.length[m.event_id] = {
                b: v[0] + v[1] for b, v in m.values.items()
                if b in ("games", "games_set1", "games_set2")}
        # arm -> key -> p ; key -> (won, ts, women class, tier)
        self.p: dict[str, dict[Key, float]] = {a: {} for a in ARMS}
        self.won: dict[Key, bool] = {}
        self.ts: dict[int, int] = {}
        self.klass: dict[int, str] = {}
        # (uniqueTournament, aces|double_faults) -> [sum realised, sum EXP centre, rows]
        self.tour: dict[tuple[int, str], list[float]] = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        self.coverage: collections.Counter[str] = collections.Counter()

    def centre(self, match: cc.Played, market: str, sample: list[float]) -> float:
        """run_sheet.sample_centre's tennis centre: the tier prior where one
        is fitted (best of three, TIER_PRIOR_METRICS), else the replay's."""
        t = match.tennis
        tier = (tier_prior(self.tiers, market, t.category_name, t.ground_type)
                if t is not None and market in TIER_PRIOR_METRICS else None)
        if tier is None:
            return float(cc.shrunk_centre(match, market, sample, self.baselines,
                                          self.constants))
        w = len(sample) / (len(sample) + self.k)
        return w * statistics.fmean(sample) + (1 - w) * tier[0]

    def run(self) -> None:
        history: dict[tuple[int, str], list[cc.Past]] = collections.defaultdict(list)
        t0 = time.time()
        for i, match in enumerate(self.played):
            if i % 20000 == 0:
                print(f"  {i:,}/{len(self.played):,} matches, {len(self.won):,} keys, "
                      f"{time.time() - t0:.0f}s", file=sys.stderr, flush=True)
            t = match.tennis
            if match.kind != MatchKind.FRIENDLY and t is not None:
                if (match.timestamp >= self.emit_from and t.best_of == 3
                        and tier_group(t.category_name) == "TOUR"
                        and any(b in match.values for b in SERVE)):
                    self.emit(match, history)
            if match.kind == MatchKind.FRIENDLY:
                continue
            for base, (hv, av) in match.values.items():
                fmt = None if t is None else t.best_of
                surf = None if t is None else t.ground_type
                total = hv + av
                history[(match.home_id, base)].append(cc.Past(
                    match.timestamp, match.event_id, hv, total, match.competition_id,
                    match.kind == MatchKind.REGULAR, "home", match.away_id, fmt, surf))
                history[(match.away_id, base)].append(cc.Past(
                    match.timestamp, match.event_id, av, total, match.competition_id,
                    match.kind == MatchKind.REGULAR, "away", match.home_id, fmt, surf))

    def emit(self, match: cc.Played, history: dict[tuple[int, str], list[cc.Past]]) -> None:
        t = match.tennis
        assert t is not None
        fc = self.rating.forecast(match)
        eg = expected_games(fc) if fc is not None else {}
        self.coverage["matches"] += 1
        self.coverage["rated" if eg else "unrated"] += 1
        self.ts[match.event_id] = match.timestamp
        klass = match_class("tennis", t.category_name)
        if klass:
            self.klass[match.event_id] = klass
        realised_rows: list[tuple[str, float, float]] = []
        for base, gbase in SERVE.items():
            if base not in match.values:
                continue
            hv, av = match.values[base]
            g_match = self.length.get(match.event_id, {}).get(gbase)
            for_m, tot_m = cc.market_name(base, "for"), cc.market_name(base, "total")
            hrec = cc.recent_for(history[(match.home_id, base)], for_m, None, t)
            arec = cc.recent_for(history[(match.away_id, base)], for_m, None, t)
            cases: list[tuple[str, str, float, list[cc.Past], str | None]] = [
                (for_m, str(match.home_id), hv, hrec, "side_a"),
                (for_m, str(match.away_id), av, arec, "side_b")]
            htot = cc.recent_for(history[(match.home_id, base)], tot_m, None, t)
            atot = cc.recent_for(history[(match.away_id, base)], tot_m, None, t)
            if len(htot) >= cc.MIN_SAMPLE and len(atot) >= cc.MIN_SAMPLE:
                seen: set[int] = set()
                pool: list[cc.Past] = []
                for p in (*htot, *atot):
                    if p.event_id not in seen:
                        seen.add(p.event_id)
                        pool.append(p._replace(own=p.total))
                cases.append((tot_m, "", hv + av, pool, None))
            for market, subject, actual, rec, side in cases:
                if len(rec) < cc.MIN_SAMPLE:
                    continue
                raw = [p.own for p in rec]
                lens = [self.length.get(p.event_id, {}).get(gbase) for p in rec]
                known = [g for g in lens if g]
                if not known:
                    continue
                gbar = statistics.fmean(known)
                adj = [x * gbar / g if g else x for x, g in zip(raw, lens, strict=True)]
                base_c = self.centre(match, market, raw)
                norm_c = self.centre(match, market, adj)
                centres = {"BASE": base_c}
                centres["ORACLE"] = norm_c * (g_match / gbar) if g_match else base_c
                e = eg.get(gbase)
                centres["EXP"] = norm_c * (e / gbar) if e else base_c
                fam = "aces" if base.startswith("aces") else "double_faults"
                s = self.tour[(match.competition_id or -1, fam)]
                f_t = ((s[0] + K_TOURNAMENT * (s[1] / s[2])) / (s[1] + K_TOURNAMENT * (s[1] / s[2]))
                       if s[2] > 0 and s[1] > 0 else 1.0)
                centres["EXP_T"] = centres["EXP"] * f_t
                f_r = (cc.tennis_aces_multiplier(match, market, side, history, None, self.constants)
                       if fam == "aces" else None)
                centres["EXP_T_R"] = centres["EXP_T"] * (f_r if f_r else 1.0)
                if market.endswith("_for"):
                    realised_rows.append((fam, actual, centres["EXP"]))
                self.settle(match, market, subject, actual, raw, centres)
        # the tournament's book learns only after the match is settled
        for fam, actual, c in realised_rows:
            s = self.tour[(match.competition_id or -1, fam)]
            s[0] += actual
            s[1] += c
            s[2] += 1

    def settle(self, match: cc.Played, market: str, subject: str, actual: float,
               raw: list[float], centres: dict[str, float]) -> None:
        per_arm: dict[str, dict[tuple[float, str], tuple[float, bool]]] = {}
        def fixed(value: float) -> Callable[[float], float]:
            return lambda _c: value
        for arm, c in centres.items():
            rows = cc._settle_centred(match, market, subject, actual, raw, self.baselines,
                                      self.constants, None, fixed(c))
            per_arm[arm] = {(r.line, r.direction): (r.p_central, r.won) for r in rows}
        common = set.intersection(*(set(v) for v in per_arm.values()))
        for line, direction in common:
            key = (match.event_id, market, subject, line, direction)
            self.won[key] = per_arm["BASE"][(line, direction)][1]
            for arm in ARMS:
                self.p[arm][key] = per_arm[arm][(line, direction)][0]


def market_lines(rep: Replay) -> set[Key]:
    """One line per (event, market, subject): arms' mean p OVER nearest 0.5."""
    best: dict[tuple[int, str, str], tuple[float, float]] = {}
    for key in rep.won:
        ev, market, subject, line, direction = key
        if direction != "OVER":
            continue
        mean_p = statistics.fmean(rep.p[a][key] for a in ARMS)
        g = (ev, market, subject)
        d = abs(mean_p - 0.5)
        if g not in best or d < best[g][0]:
            best[g] = (d, line)
    out: set[Key] = set()
    for (ev, market, subject), (_, line) in best.items():
        out.add((ev, market, subject, line, "OVER"))
        out.add((ev, market, subject, line, "UNDER"))
    return out


def curve_key(key: Key, klass: dict[int, str]) -> str:
    c = klass.get(key[0])
    return f"{c + ':' if c else ''}{key[1]}|{key[4]}"


def fit(rep: Replay, arm: str, keys: Sequence[Key]) -> dict[str, dict[int, float]]:
    cnt: dict[str, dict[int, list[int]]] = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for k in keys:
        c = cnt[curve_key(k, rep.klass)][bucket_of(rep.p[arm][k])]
        c[0] += int(rep.won[k])
        c[1] += 1
    return {ck: {b: kn[0] / kn[1] for b, kn in v.items() if kn[1] >= MIN_BUCKET} for ck, v in cnt.items()}


def ll(p: float, won: bool) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -math.log(p if won else 1 - p)


def boot(diffs: dict[int, list[float]], b: int = 1000) -> tuple[float, float, float]:
    keys = list(diffs)
    if not keys:
        return (float("nan"),) * 3
    tot = sum(sum(v) for v in diffs.values())
    n = sum(len(v) for v in diffs.values())
    rng = random.Random(7)
    stats = []
    for _ in range(b):
        s = m = 0.0
        for k in (rng.choice(keys) for _ in keys):
            s += sum(diffs[k])
            m += len(diffs[k])
        stats.append(s / m)
    stats.sort()
    return tot / n, stats[int(0.025 * b)], stats[int(0.975 * b) - 1]


def boot_gap(xs: list[tuple[int, float, bool]], b: int = 1000) -> tuple[float, float, float]:
    by: dict[int, list[float]] = collections.defaultdict(list)
    for ev, p, w in xs:
        by[ev].append(float(w) - p)
    return boot(by, b)


def superbet_check(rep: Replay, db: Path, runs: Path, first: str, last: str,
                   before: int) -> tuple[list[str], dict[str, Any]]:
    """The arms on Superbet's settled serve lines (sofa_settled_row, run date in
    [first, last], WIN / LOSS, a price): the replay's p of each arm at the very
    line, calibrated by the market-line curve fitted on every replay row before
    `before`; legs at calibrated p >= 0.70 and p x odds >= 0.90 (the coupon's
    floor and x, no line evidence, no margin / freshness gates)."""
    import sqlite3
    from datetime import date, timedelta
    d0, d1 = date.fromisoformat(first), date.fromisoformat(last)
    import unicodedata

    def fold(name: object) -> str:
        text = str(name or "").lower().replace("ł", "l").replace("đ", "d")
        return "".join(c for c in unicodedata.normalize("NFKD", text)
                       if not unicodedata.combining(c))
    side_of: dict[tuple[int, str], str] = {}
    for n in range((d1 - d0).days + 1):
        path = runs / (d0 + timedelta(n)).isoformat() / "02_fixtures.json"
        if not path.exists():
            continue
        for fx in json.loads(path.read_text(encoding="utf-8")):
            if fx.get("sport") != "tennis":
                continue
            eid = int(fx["sofascore_event_id"])
            side_of[(eid, fold(fx.get("home_name")))] = "home"
            side_of[(eid, fold(fx.get("away_name")))] = "away"
    teams = {m.event_id: (m.home_id, m.away_id) for m in rep.played}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT sofascore_event_id, market, subject, line, direction, offered_odds, outcome "
        "FROM sofa_settled_row WHERE sport = 'tennis' AND run_date BETWEEN ? AND ? "
        "AND outcome IN ('WIN','LOSS') AND offered_odds IS NOT NULL", (first, last)).fetchall()
    con.close()
    mkt = market_lines(rep)
    train = [k for k in rep.won if rep.ts[k[0]] < before and k in mkt]
    curves = {a: fit(rep, a, train) for a in ARMS}
    joined: list[tuple[Key, float, bool]] = []
    miss: collections.Counter[str] = collections.Counter()
    for eid, market, subject, line, direction, odds, outcome in rows:
        if market not in FAMILY:
            continue
        if market.endswith("_for"):
            side = side_of.get((eid, fold(subject)))
            if side is None or eid not in teams:
                miss["no side"] += 1
                continue
            subj = str(teams[eid][0 if side == "home" else 1])
        else:
            subj = ""
        key = (eid, market, subj, float(line), direction)
        if key not in rep.won:
            miss["not replayed"] += 1
            continue
        if rep.won[key] != (outcome == "WIN"):
            miss["grade differs"] += 1
            continue
        joined.append((key, float(odds), outcome == "WIN"))
    out = ["", f"## Linie Superbetu {first}..{last} (krzywa z linii rynkowych, fit na replayu < {first})", "",
           f"Dołączone linie: {len(joined):,}; pominięte: {dict(miss)}", "",
           "| rodzina | ramię | linie | mecze | dLL vs BASE [95%] | nogi >=0.70 i x>=0.90 | mecze | pewność | trafione | luka [95%] | 1/kurs | ROI |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    rep_out: dict[str, Any] = {"joined": len(joined), "missing": dict(miss), "families": {}}
    for fam in sorted(set(FAMILY.values())):
        items = [j for j in joined if FAMILY[j[0][1]] == fam]
        if not items:
            continue

        def calp(a: str, k: Key) -> tuple[float, bool]:
            curve = curves[a].get(curve_key(k, rep.klass), {})
            b = bucket_of(rep.p[a][k])
            if b in curve:
                return curve[b], True
            if not curve:
                return rep.p[a][k], False
            return curve[min(curve, key=lambda x: (abs(x - b), x > b))], False
        for a in ARMS:
            d: dict[int, list[float]] = collections.defaultdict(list)
            legs: list[tuple[int, float, float, bool]] = []
            for k, odds, won in items:
                (pa, fitted), (pb, _) = calp(a, k), calp("BASE", k)
                d[k[0]].append(ll(pa, won) - ll(pb, won))
                if fitted and pa >= FLOOR and pa * odds >= 0.90:
                    legs.append((k[0], pa, odds, won))
            dll = boot(d) if a != "BASE" else (0.0, 0.0, 0.0)
            if legs:
                gap = boot_gap([(e, p, w) for e, p, _, w in legs])
                n = len(legs)
                conf = statistics.fmean(p for _, p, _, _ in legs)
                hit = statistics.fmean(float(w) for *_, w in legs)
                inv = statistics.fmean(1 / o for _, _, o, _ in legs)
                roi = statistics.fmean((o - 1) if w else -1.0 for _, _, o, w in legs)
                tail = (f"{n} | {len({e for e, *_ in legs})} | {conf:.3f} | {hit:.3f} | "
                        f"{gap[0]*100:+.1f} pp [{gap[1]*100:+.1f}, {gap[2]*100:+.1f}] | {inv:.3f} | {roi*100:+.1f}%")
            else:
                tail = "0 | - | - | - | - | - | -"
            out.append(f"| {fam} | {a} | {len(items):,} | {len(d)} | "
                       + ("-" if a == "BASE" else f"{dll[0]:+.4f} [{dll[1]:+.4f}, {dll[2]:+.4f}]")
                       + f" | {tail} |")
            rep_out["families"].setdefault(fam, {})[a] = {"dll": dll, "legs": tail}
    return out, rep_out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--emit-from", default="2024-07-01")
    ap.add_argument("--cut", default="2026-01-01")
    ap.add_argument("--played-cache", default=None)
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--superbet-from", default=None,
                    help="also: the arms on Superbet's settled serve lines from this run date "
                    "(curves fitted on every replay row before it)")
    ap.add_argument("--superbet-to", default=None)
    ap.add_argument("--runs-dir", default="runs/sofa")
    args = ap.parse_args(argv)
    db = Path(args.db_path or SofaConfig.from_env().db_path)

    def ts(d: str) -> int:
        return int(datetime.fromisoformat(d).replace(tzinfo=UTC).timestamp())
    emit_from, cut = ts(args.emit_from), ts(args.cut)
    t0 = time.time()
    played = load_played(db, Path(args.played_cache) if args.played_cache else None)
    print(f"tennis matches held: {len(played):,} ({time.time() - t0:.0f}s)", file=sys.stderr)
    rating = cc.RatingReplay.from_db(db, scoped=True)
    if rating is None:
        raise SystemExit("no tennis rating coefficients")
    rep = Replay(played, rating, emit_from)
    rep.run()
    print(f"replay done: {len(rep.won):,} keys, coverage {dict(rep.coverage)} "
          f"({time.time() - t0:.0f}s)", file=sys.stderr)

    mkt = market_lines(rep)
    train_all = [k for k in rep.won if rep.ts[k[0]] < cut]
    train_mkt = [k for k in train_all if k in mkt]
    test_mkt = [k for k in rep.won if rep.ts[k[0]] >= cut and k in mkt]
    curves = {(a, kind): fit(rep, a, keys) for a in ARMS
              for kind, keys in (("ladder", train_all), ("market", train_mkt))}

    def cal(a: str, kind: str, k: Key) -> tuple[float, bool]:
        """(calibrated p, own bucket fitted). CONFIDENCE never falls back to
        the raw p (Calibration.realised refuses the leg): a bucket the fit
        did not fill reads the nearest fitted bucket of the key for the
        log-loss, and a leg off a fitted bucket never counts at >= 0.70."""
        curve = curves[(a, kind)].get(curve_key(k, rep.klass), {})
        b = bucket_of(rep.p[a][k])
        if b in curve:
            return curve[b], True
        if not curve:
            return rep.p[a][k], False
        near = min(curve, key=lambda x: (abs(x - b), x > b))
        return curve[near], False

    report: dict[str, Any] = {"emit_from": args.emit_from, "cut": args.cut,
                              "coverage": dict(rep.coverage), "families": {}}
    out = [f"# Asy / PB: ekspozycja, turniej, returnujący - replay TOUR, train {args.emit_from}..{args.cut}, test od {args.cut}", "",
           f"Pokrycie: {dict(rep.coverage)}; klucze test na linii rynkowej: {len(test_mkt):,}", ""]
    fams = sorted(set(FAMILY.values()))
    for kind in ("market", "ladder"):
        out += [f"## Krzywa: {'z linii rynkowych' if kind == 'market' else 'z całej drabinki (jak dziś)'}", "",
                "| rodzina | ramię | wiersze | mecze | dLL vs BASE [95%] | >=0.70: n / pewność / zrealizowane | luka [95%] |",
                "|---|---|---|---|---|---|---|"]
        for fam in fams:
            keys = [k for k in test_mkt if FAMILY[k[1]] == fam]
            if not keys:
                continue
            for a in ARMS:
                d: dict[int, list[float]] = collections.defaultdict(list)
                top: list[tuple[int, float, bool]] = []
                for k in keys:
                    (pa, fitted), (pb, _) = cal(a, kind, k), cal("BASE", kind, k)
                    d[k[0]].append(ll(pa, rep.won[k]) - ll(pb, rep.won[k]))
                    if pa >= FLOOR and fitted:
                        top.append((k[0], pa, rep.won[k]))
                dll = boot(d) if a != "BASE" else (0.0, 0.0, 0.0)
                gap = boot_gap(top) if top else (float("nan"),) * 3
                ttxt = (f"{len(top)} / {statistics.fmean(p for _, p, _ in top):.3f} / "
                        f"{statistics.fmean(float(w) for _, _, w in top):.3f}") if top else "0"
                out.append(f"| {fam} | {a} | {len(keys):,} | {len(d):,} | "
                           + ("-" if a == "BASE" else f"{dll[0]:+.5f} [{dll[1]:+.5f}, {dll[2]:+.5f}]")
                           + f" | {ttxt} | "
                           + ("-" if not top else f"{gap[0]*100:+.1f} pp [{gap[1]*100:+.1f}, {gap[2]*100:+.1f}]")
                           + " |")
                report["families"].setdefault(kind, {}).setdefault(fam, {})[a] = {
                    "rows": len(keys), "matches": len(d), "dll": dll, "top": ttxt, "gap": gap}
        out.append("")
    if args.superbet_from and args.superbet_to:
        sb_text, sb_rep = superbet_check(rep, db, Path(args.runs_dir), args.superbet_from,
                                         args.superbet_to, ts(args.superbet_from))
        out += sb_text
        report["superbet"] = sb_rep
    text = "\n".join(out)
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
