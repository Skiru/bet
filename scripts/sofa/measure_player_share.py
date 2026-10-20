"""Measure the footballer share model (epochs.FOOTBALL_PLAYER_SHARE) on the
history - read-only evidence, never a fit that ships by itself.

Today (arm A) a footballer's centre is the mean of his starts in his side's
last ``sample_n`` matches x the player stretch (shots / SOT), the spread the
sample's own variance scaled to the centre (engine.sheet_predictive_sd). The
share model (arm B, bet.sofa.player_share) prices him off his side:

    centre = share x T
    share  = (his count over his starts + m x prior_pos)
             / (the side's count in the same matches + m)
    T      = the side's own team centre today (SHEET's team row of the
             market's team metric: the sample shrunk to the league, the
             rating blend, game state - live_centre, the replay's hook)

and for shots on target ``x accuracy``, accuracy = (his SOT + m_acc x
acc_pos) / (his shots + m_acc) (literature: volume repeats, accuracy does
not). The spread rule is arm A's, scaled to the new centre.

``collect`` replays every finished football match with a cached squad list
kicking off in [--from, --to) on a DB (a COPY or the refit replay DB, opened
read-only) and writes one feature line per priced player sample; ``analyse``
fits (m, m_acc, position priors) on kickoffs before --split and judges arm B
against arm A after it: binary log-loss at Superbet-like lines, match
bootstrap, calibration at p >= 0.70 (raw, and through the installed curve).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_share.py \\
        collect --db-path data/refit_2026-10-17/sofa_replay.db \\
        --from 2025-07-01 --to 2026-10-13 --out <features.jsonl.gz>
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_share.py \\
        analyse --features <features.jsonl.gz> --split 2026-04-01
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import math
import random
import sqlite3
import statistics
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import player_share as psh  # noqa: E402
from bet.sofa.confidence import Calibration  # noqa: E402
from bet.sofa.engine import (  # noqa: E402
    sheet_count_p_raw,
    sheet_predictive_sd,
    winning_boundary,
)
from bet.sofa.game_state import load_table as load_game_state_table  # noqa: E402
from bet.sofa.listing_index import entity_indexed_events  # noqa: E402
from bet.sofa.metrics import extract_flat_statistics, extract_metric  # noqa: E402
from bet.sofa.per_market_k import k_for_market  # noqa: E402
from bet.sofa.player_stretch import (  # noqa: E402
    load_table as load_player_stretch_table,
)
from bet.sofa.players import (  # noqa: E402
    extract_player_metric,
    match_player,
    squad_statistics,
    started,
)
from bet.sofa.rating_weight import load_table as load_rating_weight_table  # noqa: E402
from bet.sofa.samples import _competition_id, finish_history  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402

# the lines Superbet quotes footballers at (settled 10-12..10-19: shots 0.5 ..
# 2.5 hold 70% of the offered rows, SOT 0.5 / 1.5 80%)
LINES: dict[str, tuple[float, ...]] = {
    "player_shots_for": (0.5, 1.5, 2.5, 3.5),
    "player_shots_on_target_for": (0.5, 1.5, 2.5),
    "player_fouls_for": (0.5, 1.5, 2.5),
    "player_tackles_for": (0.5, 1.5, 2.5),
}
GRID_M = (0.0, 2.0, 5.0, 10.0, 20.0, 40.0, 80.0)
GRID_M_ACC = (0.0, 5.0, 10.0, 20.0, 40.0, 80.0)


def _position(lineups: dict[str, Any] | None, is_home: bool) -> dict[str, str]:
    """normalised name -> lineup position letter, one side of one match."""
    from bet.sofa.names import normalize_name

    out: dict[str, str] = {}
    side = (lineups or {}).get("home" if is_home else "away") or {}
    for entry in side.get("players") or []:
        player = (entry or {}).get("player") or {}
        name = player.get("name")
        pos = entry.get("position") or player.get("position")
        if isinstance(name, str) and isinstance(pos, str) and pos:
            out[normalize_name(name)] = pos[:1].upper()
    return out


def collect(db_path: Path, from_ts: int, to_ts: int, out: Path,
            sample_n: int, min_sample: int) -> collections.Counter[str]:
    counts: collections.Counter[str] = collections.Counter()
    rules = cfc.CentreRules(
        football_rating=True, rated_scope=True, venue_prior=True,
        game_state=load_game_state_table(None),
        rating_weights=load_rating_weight_table(None),
    )
    football = cfc.FootballRatingReplay.from_db(db_path, rules)
    stretch = load_player_stretch_table(None)
    baselines = cfc.load_baselines()
    constants = cfc._load_engine_constants()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    targets = [e for e in cfc.player_targets(conn, counts)
               if from_ts <= int(e["startTimestamp"]) < to_ts]
    print(f"{len(targets)} targets", file=sys.stderr, flush=True)
    cache: collections.OrderedDict[int, tuple[Any, Any]] = collections.OrderedDict()

    def payload(event_id: int) -> tuple[Any, Any]:
        if event_id in cache:
            cache.move_to_end(event_id)
            return cache[event_id]
        row = conn.execute(
            "SELECT statistics_json, lineups_json FROM sofa_event_stats "
            "WHERE sofascore_event_id = ?", (event_id,)).fetchone()
        stats = json.loads(row[0]) if row and row[0] else None
        lineups = json.loads(row[1]) if row and row[1] else None
        cache[event_id] = (stats, lineups)
        if len(cache) > 30_000:
            cache.popitem(last=False)
        return stats, lineups

    with gzip.open(out, "wt") as fh:
        for i, event in enumerate(targets):
            if i % 2000 == 0:
                print(f"  {i}/{len(targets)} {dict(counts.most_common(6))}",
                      file=sys.stderr, flush=True)
            kickoff = int(event["startTimestamp"])
            competition = _competition_id(event)
            home = int(((event.get("homeTeam") or {}).get("id")) or 0)
            away = int(((event.get("awayTeam") or {}).get("id")) or 0)
            if competition is None or not home or not away:
                counts["no_competition_or_team"] += 1
                continue
            forecast = football.forecast_fixture(competition, home, away, kickoff)
            stats_t, lineups_t = payload(int(event["id"]))
            for is_home, entity in ((True, home), (False, away)):
                side = "side_a" if is_home else "side_b"
                target = squad_statistics(lineups_t, is_home=is_home,
                                          statistics=stats_t)
                if not target:
                    counts["target_side_without_squad"] += 1
                    continue
                admitted = [
                    past for past in entity_indexed_events(
                        conn, entity, "last", kickoff, cfc.PLAYER_HISTORY_LISTED)
                    if cfc.admitted_football_event(past, entity, kickoff)
                    and not cfc.is_same_match(past, event)
                ]
                recent = finish_history(admitted, entity, "football",
                                        competition, kickoff, sample_n)
                hist: list[tuple[dict[str, Any], dict[str, float], str,
                                 dict[str, str]]] = []
                for past in recent:
                    own_home = (past.get("homeTeam") or {}).get("id") == entity
                    stats_p, lineups_p = payload(int(past["id"]))
                    squad = squad_statistics(lineups_p, is_home=own_home,
                                             statistics=stats_p)
                    if not squad:
                        continue
                    flat = extract_flat_statistics(stats_p)
                    totals: dict[str, float] = {}
                    for tm in psh.TEAM_METRIC_KEYS:
                        tv_ = extract_metric(tm, "football", flat, None, past,
                                             own_home)
                        if isinstance(tv_, float | int):
                            totals[tm] = float(tv_)
                    hist.append((squad, totals, "home" if own_home else "away",
                                 _position(lineups_p, own_home)))
                if not hist:
                    counts["no_history_squads"] += 1
                    continue
                team_centres: dict[str, float | None] = {}
                for team_metric in psh.TEAM_METRIC_KEYS:
                    team_vals = [t[team_metric] for _s, t, _v, _p in hist
                                 if team_metric in t]
                    if len(team_vals) < min_sample:
                        team_centres[team_metric] = None
                        continue
                    mean = statistics.mean(team_vals)
                    prior = cfc.prior_for(baselines, team_metric, competition)
                    centre = mean
                    if prior is not None:
                        k = k_for_market(constants, "football", team_metric,
                                         cfc.k_centre_for("football", constants))
                        w = len(team_vals) / (len(team_vals) + k)
                        centre = w * mean + (1 - w) * prior
                    played = cfc.Played(int(event["id"]), kickoff, home, away,
                                        "football", competition, {})
                    team_centres[team_metric] = cfc.live_centre(
                        played, team_metric, side, centre, forecast,
                        [v for _s, _t, v, _p in hist], rules)
                sup = forecast.supremacy(side)
                positions = _position(lineups_t, is_home)
                for name, stats in sorted(target.items()):
                    if stats.get("minutesPlayed") is None or started(stats) is False:
                        continue
                    keys = [(sq, tot, pos, match_player(name, sq))
                            for sq, tot, _v, pos in hist]
                    for metric, lines in LINES.items():
                        team_metric = psh.TEAM_METRIC[metric]
                        tkey = team_metric
                        actual = extract_player_metric(metric, stats)
                        if not isinstance(actual, float | int):
                            continue
                        vals: list[float] = []
                        his_vol: list[float] = []
                        team_vol: list[float] = []
                        his_cnt: list[float] = []
                        pos_seen: str | None = None
                        for sq, tot, pos, key in keys:
                            if key is None or started(sq[key]) is False:
                                continue
                            v = extract_player_metric(metric, sq[key])
                            if not isinstance(v, float | int):
                                continue
                            vals.append(float(v))
                            if pos_seen is None:
                                pos_seen = pos.get(key)
                            vol_metric = psh.VOLUME_METRIC[metric]
                            hv = extract_player_metric(vol_metric, sq[key])
                            if tkey in tot and isinstance(hv, float | int):
                                his_vol.append(float(hv))
                                team_vol.append(tot[tkey])
                                his_cnt.append(float(v))
                        n = len(vals)
                        if n < min_sample or all(v == 0.0 for v in vals):
                            continue
                        mean = statistics.mean(vals)
                        var = statistics.variance(vals) if n > 1 else 0.0
                        mult = stretch.multiplier(metric, sup)
                        centre_a = mean * mult if mult is not None else mean
                        rec = {
                            "ts": kickoff, "ev": int(event["id"]), "c": competition,
                            "m": metric, "n": n, "mean": round(mean, 4),
                            "var": round(var, 4), "ca": round(centre_a, 4),
                            "y": float(actual),
                            "pos": positions.get(name) or pos_seen,
                            "hv": sum(his_vol), "tv": sum(team_vol),
                            "k": len(his_vol),
                            "sv": (sum(his_cnt) if metric in psh.ACCURACY_MARKETS
                                   else None),
                            "T": (None if team_centres.get(team_metric) is None
                                  else round(float(team_centres[team_metric]
                                                   or 0.0), 4)),
                        }
                        fh.write(json.dumps(rec) + "\n")
                        counts[f"samples:{metric}"] += 1
    conn.close()
    return counts


def _ll(y: int, p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def p_over(metric: str, rec: dict[str, Any], centre: float, line: float) -> float:
    sd = sheet_predictive_sd(metric, "football", rec["mean"], rec["var"],
                             rec["n"], centre)
    return sheet_count_p_raw(metric, centre, sd, winning_boundary(line, "OVER"),
                             "OVER")


def load(path: Path, metric: str) -> list[dict[str, Any]]:
    out = []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            r = json.loads(line)
            # live, 96% of a footballer's starts carry his side's statistics
            # (03_samples 10-12..10-19); the replay DB's older squads often
            # do not (placeholder zeros beside NO_STATISTICS), so a sample
            # is read only where every start has them, as live
            if (r["m"] == metric and r.get("T") and r["k"] >= psh.MIN_SHARE_MATCHES
                    and r["k"] == r["n"] and r["tv"] > 0):
                out.append(r)
    return out


def priors(rows: Iterable[dict[str, Any]], metric: str) -> dict[str, dict[str, float]]:
    """Pooled share (and accuracy) per position over ``rows``."""
    hv: dict[str, float] = collections.defaultdict(float)
    tv: dict[str, float] = collections.defaultdict(float)
    sv: dict[str, float] = collections.defaultdict(float)
    for r in rows:
        for pos in (r.get("pos") or "?", "*"):
            hv[pos] += r["hv"]
            tv[pos] += r["tv"]
            if r.get("sv") is not None:
                sv[pos] += r["sv"]
    share = {p: hv[p] / tv[p] for p in tv if tv[p] > 0}
    acc = {p: sv[p] / hv[p] for p in hv if hv[p] > 0 and p in sv}
    return {"share": share, "accuracy": acc}


def centre_b(rec: dict[str, Any], pri: dict[str, dict[str, float]], m: float,
             m_acc: float | None) -> float:
    pos = rec.get("pos") or "?"
    return psh.share_centre(
        his_volume=rec["hv"], team_volume=rec["tv"], team_centre=rec["T"],
        prior_share=pri["share"].get(pos, pri["share"]["*"]), m=m,
        his_count=rec.get("sv") if m_acc is not None else None,
        prior_accuracy=(pri["accuracy"].get(pos, pri["accuracy"].get("*", 0.0))
                        if m_acc is not None else None),
        m_accuracy=m_acc)


def mean_ll(rows: Sequence[dict[str, Any]], metric: str, fn: Any) -> float:
    tot = 0.0
    c = 0
    for r in rows:
        centre = fn(r)
        for line in LINES[metric]:
            tot += _ll(int(r["y"] > line), p_over(metric, r, centre, line))
            c += 1
    return tot / max(c, 1)


def bootstrap(per_event: dict[int, list[float]],
              b: int = 1000) -> tuple[float, float, float]:
    keys = list(per_event)
    total = (sum(sum(v) for v in per_event.values())
             / sum(len(v) for v in per_event.values()))
    rnd = random.Random(20261021)
    vals = []
    sums = [(sum(per_event[k]), len(per_event[k])) for k in keys]
    for _ in range(b):
        s = 0.0
        c = 0
        for _k in range(len(keys)):
            a, n = sums[rnd.randrange(len(keys))]
            s += a
            c += n
        vals.append(s / c)
    vals.sort()
    return total, vals[int(0.025 * b)], vals[int(0.975 * b)]


def analyse(path: Path, split_ts: int, metric: str,
            cal: Calibration) -> dict[str, Any] | None:
    rows = load(path, metric)
    train = [r for r in rows if r["ts"] < split_ts]
    test = [r for r in rows if r["ts"] >= split_ts]
    print(f"\n=== {metric}: train {len(train)} samples, test {len(test)} "
          f"({len({r['ev'] for r in test})} matches)")
    if not train or not test:
        return None
    pri = priors(train, metric)
    print("  position priors share:",
          {k: round(v, 4) for k, v in sorted(pri["share"].items())})
    acc_grid: Sequence[float | None] = (
        GRID_M_ACC if metric == "player_shots_on_target_for" else (None,))
    sub = train[:: max(1, len(train) // 60000)]
    base = mean_ll(sub, metric, lambda r: r["ca"])
    best = None
    for m in GRID_M:
        for ma in acc_grid:
            v = mean_ll(sub, metric, lambda r, m=m, ma=ma: centre_b(r, pri, m, ma))
            print(f"  train m={m:5.1f} m_acc={ma}: LL B-A {v - base:+.5f}")
            if best is None or v < best[0]:
                best = (v, m, ma)
    assert best is not None
    _, m, ma = best
    print(f"  chosen on train: m={m} m_acc={ma}")
    for line in LINES[metric]:
        per_ev: dict[int, list[float]] = collections.defaultdict(list)
        cal_a: list[tuple[float, int]] = []
        cal_b: list[tuple[float, int]] = []
        cur_a: list[tuple[float, int]] = []
        cur_b: list[tuple[float, int]] = []
        for r in test:
            y = int(r["y"] > line)
            pa = p_over(metric, r, r["ca"], line)
            pb = p_over(metric, r, centre_b(r, pri, m, ma), line)
            per_ev[r["ev"]].append(_ll(y, pb) - _ll(y, pa))
            if pa >= 0.70:
                cal_a.append((pa, y))
            if pb >= 0.70:
                cal_b.append((pb, y))
            for p, bucket in ((pa, cur_a), (pb, cur_b)):
                hit = cal.realised(metric, p, sport="football", direction="OVER")
                if hit is not None and hit[0] >= 0.70:
                    bucket.append((hit[0], y))
        d = bootstrap(per_ev)

        def gap(xs: list[tuple[float, int]]) -> str:
            if not xs:
                return "n 0"
            return (f"n {len(xs)} p {sum(p for p, _ in xs) / len(xs):.3f} "
                    f"hit {sum(y for _, y in xs) / len(xs):.3f}")
        print(f"  test line {line}: dLL B-A {d[0]:+.5f} [{d[1]:+.5f}, {d[2]:+.5f}]"
              f" | raw>=.70 A {gap(cal_a)} | B {gap(cal_b)}"
              f" | curve>=.70 A {gap(cur_a)} | B {gap(cur_b)}")
    cell: dict[str, Any] = {
        "m": m, "prior_share": {k: round(v, 5) for k, v in sorted(pri["share"].items())
                                if k != "?"},
        "n_train_samples": len(train), "n_test_samples": len(test),
    }
    if ma is not None:
        cell["m_accuracy"] = ma
        cell["prior_accuracy"] = {k: round(v, 5) for k, v in
                                  sorted(pri["accuracy"].items()) if k != "?"}
    return cell


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--db-path", required=True)
    c.add_argument("--from", dest="from_day", required=True)
    c.add_argument("--to", dest="to_day", required=True)
    c.add_argument("--out", required=True)
    a = sub.add_parser("analyse")
    a.add_argument("--features", required=True)
    a.add_argument("--split", required=True)
    a.add_argument("--markets", nargs="+", default=list(LINES))
    a.add_argument("--write-config", metavar="FILE",
                   help="write the train fit of --config-markets (a staged "
                   "config/sofa_player_share.json)")
    a.add_argument("--config-markets", nargs="+",
                   default=["player_shots_for", "player_shots_on_target_for"])
    args = ap.parse_args()
    if args.cmd == "collect":
        from_ts = cfc.day_ts(args.from_day)
        to_ts = cfc.day_ts(args.to_day)
        assert from_ts is not None and to_ts is not None
        counts = collect(Path(args.db_path), from_ts, to_ts, Path(args.out),
                         sample_n=10, min_sample=5)
        print(json.dumps(dict(counts.most_common(30)), indent=1))
        return 0
    split = cfc.day_ts(args.split)
    assert split is not None
    cal = Calibration.load()
    cells: dict[str, Any] = {}
    for metric in args.markets:
        cell = analyse(Path(args.features), split, metric, cal)
        if cell is not None and metric in args.config_markets:
            cells[metric] = cell
    if args.write_config:
        doc = {
            "_doc": ("Footballer share model (epochs.FOOTBALL_PLAYER_SHARE, "
                     "bet.sofa.player_share): m / m_accuracy and the position "
                     "priors fitted on the replayed history before the split. "
                     "Read only while epochs.FOOTBALL_PLAYER_SHARE_FROM_UTC is "
                     "set. Written by scripts/sofa/measure_player_share.py."),
            "fitted_from": {"features": args.features, "split": args.split,
                            "fit": "grid on binary log-loss at LINES, train only"},
            "markets": cells,
        }
        psh.parse_table(doc)  # what is written must be readable
        Path(args.write_config).parent.mkdir(parents=True, exist_ok=True)
        Path(args.write_config).write_text(json.dumps(doc, indent=2) + "\n",
                                           encoding="utf-8")
        print(f"wrote {args.write_config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
