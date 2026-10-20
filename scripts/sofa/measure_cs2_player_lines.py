#!/usr/bin/env python3
"""CS2 player lines (kills / deaths / assists / headshots) on history, at
Superbet-like lines, with the CURRENT estimator. Read-only measurement: the
database is opened mode=ro, no config / curve / model is touched.

Walk-forward over cs2_map / cs2_player_map, series by series: every map of a
series is priced from the state before the series (map Elo + player Elo with
its logistic calibration refitted every sport_confidence.REFIT_DAYS_CS2 days
on earlier predictions only, as cs2_walk_forward_rows does; ExposureBook and
each player's last MAX_SAMPLE maps updated after the series). The estimator is
cs2_engine.model_probability's player branch as it runs today
(epochs.CS2_COUNT_EXPOSURE on, CS2_MAP_IDENTITY off):

- kills / deaths / assists: cs2_engine.exposure_* (round race (W, L) x per-round
  rates x the player's shrunk share, NB / normal with the player phi); where
  the exposure has no number, cs2_engine.count_p on the player's last 20 maps;
- headshots: count_p (outside EXPOSURE_FAMILIES);
- no number when the player has < MIN_SAMPLE maps, or is not on his team's
  last MAX_SAMPLE maps (live, cs2_engine.player_id finds him by nickname
  there), or a namesake on that team makes the nickname ambiguous.

The exposure mixture is evaluated vectorised (numpy) with the engine's own
formulas and checked against cs2_engine.exposure_p on a sample of rows (the
script stops when they differ by more than 1e-6).

Lines: Superbet posts one line per player and map (maps 1, 2, rarely 3, "z
dogrywka" = overtime counts), its fair OVER p at 0.45-0.54. The rule that
reproduces Superbet's line best on the settled days (runs/sofa/cs2/*/
settled.json joined to the same maps) is chosen among nearest-half-integer
rules of the sample mean / median, the model mean / median and the line
whose model P(OVER) is closest to 0.5, and used on history. The report also
evaluates the replayed model at Superbet's actual settled lines.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_player_lines.py \\
        --out <dir> [--dataset <dir>] [--db-path data/sofa.db] [--from 2025-11-15]
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import gzip
import json
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2_engine as ce  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.cs2 import NICK_PREFIX_MIN, esports_name  # noqa: E402

STATS = ("kills", "deaths", "assists", "headshots")
FAMILY = {s: f"player_{s}" for s in STATS}
KMAX = 70
EPS = 1e-12
POOL_N = 30


# --- data --------------------------------------------------------------------------


def connect(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def drop_bad_headshots(maps: list[ce.MapRow]) -> tuple[list[ce.MapRow], int]:
    """A variant (--drop-bad-headshots): a player row's headshots above its
    kills is impossible (239 rows, all 2025-10-27, values like 410 / 2030)
    and is dropped from that row, as a missing stat."""
    out, n = [], 0
    for m in maps:
        rows = []
        for t, pid, nick, st in m.players:
            d = dict(st)
            if (
                isinstance(d.get("headshots"), int)
                and isinstance(d.get("kills"), int)
                and d["headshots"] > d["kills"]
            ):
                n += 1
                st = tuple((k, v) for k, v in st if k != "headshots")
            rows.append((t, pid, nick, st))
        out.append(dataclasses.replace(m, players=tuple(rows)))
    return out, n


def load_maps(conn: sqlite3.Connection, before_ts: int) -> list[ce.MapRow]:
    # every stored map: the live loader keeps LOOKBACK_DAYS (365) before the
    # day; the history here starts 2025-10-01, so 400 days takes all of it
    # (in-process only, the engine file is untouched)
    ce.LOOKBACK_DAYS = 400
    maps: list[ce.MapRow] = ce.load_history(conn, before_ts, None)
    return maps


def load_extra(
    conn: sqlite3.Connection,
) -> tuple[
    dict[tuple[int, int], dict[str, Any]],
    dict[tuple[int, int], dict[str, Any]],
    dict[int, dict[str, Any]],
]:
    """(event, order) -> map extras; (game key, player) -> extra player stats;
    event -> series extras."""
    maps: dict[tuple[int, int], dict[str, Any]] = {}
    gid_key: dict[int, tuple[int, int]] = {}
    for gid, eid, order, hot, aot, hp1, ap1 in conn.execute(
        "SELECT game_id, sofascore_event_id, map_order, home_overtime, "
        "away_overtime, home_period1, away_period1 FROM cs2_map"
    ):
        maps[(eid, order)] = {"game_id": gid, "ot": (hot or 0) + (aot or 0)}
        gid_key[gid] = (eid, order)
    players: dict[tuple[int, int], dict[str, Any]] = {}
    for gid, pid, fk, adr, kast in conn.execute(
        "SELECT game_id, player_id, first_kills_diff, adr, kast FROM cs2_player_map"
    ):
        k = gid_key.get(gid)
        if k is not None:
            players[(gid, pid)] = {"fk": fk, "adr": adr, "kast": kast}
    series: dict[int, dict[str, Any]] = {}
    for eid, tour, utid in conn.execute(
        "SELECT sofascore_event_id, tournament, unique_tournament_id FROM cs2_series"
    ):
        series[eid] = {"tournament": tour, "utid": utid}
    return maps, players, series


# --- the exposure mixture, vectorised --------------------------------------------


_RACE: dict[float, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}


def race_arrays(p_team: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    key = round(min(max(p_team, 0.05), 0.95), 3)
    got = _RACE.get(key)
    if got is None:
        cells = ce.race_cells(p_team, 0)
        got = (
            np.array([c[0] for c in cells]),
            np.array([c[1] for c in cells], float),
            np.array([c[2] for c in cells], float),
        )
        _RACE[key] = got
    return got


def mixture_cdf(q: np.ndarray, mu: np.ndarray, phi: float) -> np.ndarray:
    """P(X <= k), k = 0..KMAX, of the (q, mu) mixture exactly as
    cs2_engine.exposure_sides prices a half line: NB variance phi x mu when
    phi > 1, else the continuity-corrected normal; mu <= 0 all mass at 0."""
    out = np.zeros(KMAX + 1)
    pos = mu > 0
    out += q[~pos].sum()
    if not pos.any():
        return out
    qq, mm = q[pos], mu[pos]
    if phi > 1.0:
        r = mm / (phi - 1.0)
        qnb = 1.0 - 1.0 / phi
        pmf = np.exp(r * math.log(1.0 / phi))
        acc = pmf.copy()
        out[0] += (qq * acc).sum()
        for k in range(KMAX):
            pmf = pmf * (k + r) / (k + 1) * qnb
            acc = np.minimum(acc + pmf, 1.0)
            out[k + 1] += (qq * acc).sum()
    else:
        sd = np.sqrt(max(phi, ce.MIN_VAR_RATIO) * mm)
        ks = np.arange(KMAX + 1)
        z = (ks[None, :] + 0.5 - mm[:, None]) / sd[:, None]
        cdf = 0.5 * (1.0 + _erf(z / math.sqrt(2.0)))
        out += (qq[:, None] * cdf).sum(axis=0)
    # side_given_no_push normalises by the mass kept (cells under RACE_MIN_Q
    # are dropped), so the cdf is of the kept mixture
    return np.asarray(out / q.sum())


_ERF = np.frompyfunc(math.erf, 1, 1)


def _erf(x: np.ndarray) -> np.ndarray:
    return np.asarray(_ERF(x), dtype=float)


# --- the walk ------------------------------------------------------------------------


def walk(
    maps: list[ce.MapRow],
    score_from: int,
    mextra: dict[tuple[int, int], Any],
    pextra: dict[tuple[int, int], Any],
    sextra: dict[int, Any],
) -> tuple[list[dict[str, Any]], np.ndarray, list[list[int]]]:
    """Rows (one per player-map-stat scored), their exposure cdf (NaN row when
    the exposure has no number) and the player's sample (last MAX_SAMPLE values,
    newest first) for count_p."""
    book = ce.EloBook()
    players = ce.PlayerEloBook()
    points: list[tuple[float, float]] = []
    ppoints: list[tuple[float, float]] = []
    model = ce.RatingModel(book)
    next_refit = 0
    expo = ce.ExposureBook()
    pvals: dict[tuple[int, str], deque[int]] = defaultdict(
        lambda: deque(maxlen=ce.MAX_SAMPLE)
    )
    pall: dict[int, int] = Counter()  # maps a player has, any team
    pteam: dict[tuple[int, int], int] = Counter()  # maps a player has for a team
    plast: dict[int, int] = {}
    prole: dict[int, deque[tuple[Any, ...]]] = defaultdict(
        lambda: deque(maxlen=ce.MAX_SAMPLE)
    )
    team_recent: dict[int, deque[ce.MapRow]] = defaultdict(
        lambda: deque(maxlen=ce.MAX_SAMPLE)
    )
    team_pool: dict[int, deque[str]] = defaultdict(lambda: deque(maxlen=POOL_N))
    rows: list[dict[str, Any]] = []
    cdfs: list[np.ndarray] = []
    samples: list[list[int]] = []
    by_series: dict[int, list[ce.MapRow]] = {}
    for m in maps:
        by_series.setdefault(m.event_id, []).append(m)
    checks = 0
    nan_row = np.full(KMAX + 1, np.nan)
    for eid, smaps in by_series.items():
        start = smaps[0].start_ts
        if start >= next_refit:
            model = scf._cs2_refit(book, players, points, ppoints)
            next_refit = start + scf.REFIT_DAYS_CS2 * 86400
        home, away = smaps[0].home_id, smaps[0].away_id
        score = start >= score_from
        p_home = model.p_map(home, away, True) if score else None
        if p_home is not None:
            # the nickname on each team's last maps, as cs2_engine.player_id
            names: dict[int, dict[str, set[int]]] = {}
            for t in (home, away):
                nm: dict[str, set[int]] = defaultdict(set)
                for tm in team_recent[t]:
                    for tt, pid, nick, _ in tm.players:
                        if tt == t:
                            nm[nick].add(pid)
                names[t] = nm
            elo_h = book.rating(home)
            elo_a = book.rating(away)
            sx = sextra.get(eid, {})
            for m in smaps:
                if m.home_rounds is None or m.away_rounds is None:
                    continue
                mx = mextra.get((eid, m.order), {})
                for team, opp, w, lost, totals, prow in ce.map_sides(m):
                    p_team = p_home if team == home else 1.0 - p_home
                    q, wa, la = race_arrays(p_team)
                    nicks = {pid: nick for t, pid, nick, _ in m.players if t == team}
                    own_pool = sum(1 for x in team_pool[team] if x == m.map_name)
                    opp_pool = sum(1 for x in team_pool[opp] if x == m.map_name)
                    for pid, own in prow:
                        nick = nicks.get(pid, "")
                        ids = names[team].get(nick, set())
                        found = ids == {pid}
                        role = list(prole[pid])
                        k_sum = sum(r[0] for r in role if r[0] is not None)
                        hs_sum = sum(r[3] for r in role if r[3] is not None)
                        fk = [r[4] for r in role if r[4] is not None]
                        adr = [r[5] for r in role if r[5] is not None]
                        base = {
                            "event_id": eid,
                            "game_id": mx.get("game_id"),
                            "date": time.strftime("%Y-%m-%d", time.gmtime(start)),
                            "ts": start,
                            "map_order": m.order,
                            "best_of": m.best_of,
                            "map_name": m.map_name,
                            "tournament": sx.get("tournament"),
                            "utid": sx.get("utid"),
                            "team": team,
                            "opp": opp,
                            "is_home": int(team == home),
                            "player_id": pid,
                            "nick": nick,
                            "p_team": round(p_team, 4),
                            "elo_team": round(elo_h if team == home else elo_a, 1),
                            "elo_opp": round(elo_a if team == home else elo_h, 1),
                            "player_maps_all": pall[pid],
                            "player_maps_team": pteam[(pid, team)],
                            "found_by_nick": int(found),
                            "namesake_on_team": int(len(ids) > 1),
                            "days_since_last": (
                                round((start - plast[pid]) / 86400, 2)
                                if pid in plast
                                else None
                            ),
                            "hs_pct_prior": (
                                round(hs_sum / k_sum, 4) if k_sum > 0 else None
                            ),
                            "fk_diff_prior": (
                                round(sum(fk) / len(fk), 3) if fk else None
                            ),
                            "adr_prior": (
                                round(sum(adr) / len(adr), 2) if adr else None
                            ),
                            "kill_share_prior": (
                                round(s, 4)
                                if (s := expo.share(pid, "kills")) is not None
                                else None
                            ),
                            "own_pool": own_pool,
                            "opp_pool": opp_pool,
                            "W": w,
                            "L": lost,
                            "rounds": w + lost,
                            "ot": int(w + lost > 24),
                        }
                        for stat in STATS:
                            v = own.get(stat)
                            if not isinstance(v, int):
                                continue
                            sample = list(reversed(pvals[(pid, stat)]))
                            if len(sample) < ce.MIN_SAMPLE:
                                continue
                            row = dict(base)
                            row["family"] = FAMILY[stat]
                            row["actual"] = v
                            row["n_sample"] = len(sample)
                            row["sample_mean"] = round(sum(sample) / len(sample), 3)
                            cdf = nan_row
                            row["exp_ok"] = 0
                            if True:  # every stat: share and rates gate it
                                cells_r = expo.rates(team, opp, stat)
                                sh = expo.share(pid, stat)
                                phi = expo.phi("player", stat)
                                if (
                                    cells_r is not None
                                    and sh is not None
                                    and phi is not None
                                ):
                                    mu = sh * (cells_r[0] * wa + cells_r[1] * la)
                                    cdf = mixture_cdf(q, mu, phi)
                                    row["exp_ok"] = 1
                                    row["exp_mean"] = round(
                                        float((q * mu).sum() / q.sum()), 3
                                    )
                                    row["phi"] = round(phi, 4)
                                    row["share"] = round(sh, 4)
                                    if checks < 300 and stat != "headshots":
                                        checks += 1
                                        _check(expo, p_team, team, opp, stat, pid, cdf)
                            rows.append(row)
                            cdfs.append(cdf.astype(np.float32))
                            samples.append(sample)
        # --- state update, as cs2_walk_forward_rows / measure_cs2_count_exposure
        if book.rated(home, away):
            d = ce.logit_diff(book, home, away)
            points.extend((d, 1.0 if m.home_won else 0.0) for m in smaps)
            gap = players.gap(home, away)
            if gap is not None:
                ppoints.extend((gap, 1.0 if m.home_won else 0.0) for m in smaps)
        for m in smaps:
            winner, loser = (
                (m.home_id, m.away_id) if m.home_won else (m.away_id, m.home_id)
            )
            book.update(winner, loser)
            players.update(m)
            expo.update(m)
            team_recent[m.home_id].append(m)
            team_recent[m.away_id].append(m)
            if m.map_name:
                team_pool[m.home_id].append(m.map_name)
                team_pool[m.away_id].append(m.map_name)
            gid = mextra.get((eid, m.order), {}).get("game_id")
            for t, pid, _, st in m.players:
                sd = dict(st)
                for stat in STATS:
                    if isinstance(sd.get(stat), int):
                        pvals[(pid, stat)].append(sd[stat])
                pall[pid] += 1
                pteam[(pid, t)] += 1
                plast[pid] = m.start_ts
                px = pextra.get((gid, pid), {}) if gid is not None else {}
                prole[pid].append(
                    (
                        sd.get("kills"),
                        sd.get("deaths"),
                        sd.get("assists"),
                        sd.get("headshots"),
                        px.get("fk"),
                        px.get("adr"),
                    )
                )
    return rows, np.vstack(cdfs) if cdfs else np.zeros((0, KMAX + 1)), samples


def _check(
    expo: ce.ExposureBook,
    p_team: float,
    team: int,
    opp: int,
    stat: str,
    pid: int,
    cdf: np.ndarray,
) -> None:
    for line in (5.5, 10.5, 14.5, 18.5):
        mp = ce.exposure_p(expo, p_team, team, opp, stat, pid, line, True)
        if mp is None:
            continue
        mine = ce.clamp(1.0 - float(cdf[int(line)]))
        if abs(mine - mp.p) > 1e-6:
            raise SystemExit(
                f"vectorised exposure differs: {mine} vs {mp.p} ({stat}, line {line})"
            )


# --- lines and p ----------------------------------------------------------------------


def p_over_exp(cdf: np.ndarray, line: float) -> float | None:
    k = math.floor(line)
    if k > KMAX or math.isnan(float(cdf[0])):
        return None
    return float(ce.clamp(1.0 - float(cdf[k])))


def model_median_line(cdf: np.ndarray) -> float | None:
    """The half line whose P(OVER) is closest to 0.5."""
    if math.isnan(float(cdf[0])):
        return None
    po = 1.0 - cdf
    k = int(np.argmin(np.abs(po - 0.5)))
    return k + 0.5


def half(x: float) -> float:
    return math.floor(x) + 0.5


def p_model(
    row: dict[str, Any], cdf: np.ndarray, sample: list[int], line: float
) -> tuple[float | None, str | None]:
    """OVER p of the current estimator at `line` and its source."""
    if not row["found_by_nick"]:
        return None, None
    if row["family"] != "player_headshots" and row["exp_ok"]:
        p = p_over_exp(cdf, line)
        if p is not None:
            return p, "round_exposure"
    mp = ce.count_p(sample, line, True)
    return (None, None) if mp is None else (mp.p, mp.model)


# --- the settled Superbet lines ---


def settled_lines(runs_dir: str) -> list[dict[str, Any]]:
    out = []
    for f in sorted(glob.glob(f"{runs_dir}/cs2/*/settled.json")):
        date = Path(f).parent.name
        try:
            doc = json.loads(Path(f).read_text(encoding="utf-8"))
        except ValueError:
            continue
        for sb, e in (doc.get("events") or {}).items():
            eid = e.get("sofascore_event_id")
            if eid is None:
                continue
            for g in e.get("graded") or []:
                if g.get("family") not in FAMILY.values():
                    continue
                if g.get("outcome") not in ("WIN", "LOSS") or g.get("side") != "OVER":
                    continue
                out.append(
                    {
                        "date": date,
                        "sb": sb,
                        "event_id": int(eid),
                        "map_nr": int(g.get("map_nr") or 0),
                        "subject": str(g.get("subject") or ""),
                        "family": g["family"],
                        "line": float(g["line"]),
                        "y": 1 if g["outcome"] == "WIN" else 0,
                        "fair_p": g.get("fair_p"),
                        "odds": g.get("odds"),
                        "model_p": g.get("model_p"),
                        "model": g.get("model"),
                    }
                )
    return out


def match_subject(subject: str, nicks: dict[str, int]) -> int | None:
    """cs2.MapResult.player's rule on the map's players (both rosters)."""
    wanted = esports_name(subject)
    hits = [pid for n, pid in nicks.items() if n == wanted]
    if not hits and len(wanted) >= NICK_PREFIX_MIN:
        hits = [
            pid
            for n, pid in nicks.items()
            if len(n) >= NICK_PREFIX_MIN
            and (wanted.startswith(n) or n.startswith(wanted))
        ]
    return hits[0] if len(hits) == 1 else None


# --- statistics ---


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def logistic(
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    init: tuple[float, float] = (0.0, 1.0),
    iters: int = 25,
) -> tuple[float, float]:
    a, b = init
    for _ in range(iters):
        z = a + b * x
        p = 1 / (1 + np.exp(-z))
        g0 = (w * (y - p)).sum()
        g1 = (w * (y - p) * x).sum()
        v = w * p * (1 - p)
        h00, h01, h11 = v.sum(), (v * x).sum(), (v * x * x).sum()
        det = h00 * h11 - h01 * h01
        if det <= 0:
            break
        da = (h11 * g0 - h01 * g1) / det
        db = (h00 * g1 - h01 * g0) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-9:
            break
    return a, b


def metrics(
    p: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    base: float,
    init: tuple[float, float] | None = None,
) -> dict[str, float]:
    pc = np.clip(p, EPS, 1 - EPS)
    ll = -(y * np.log(pc) + (1 - y) * np.log(1 - pc))
    bc = min(max(base, EPS), 1 - EPS)
    ll0 = -(y * math.log(bc) + (1 - y) * math.log(1 - bc))
    sw = w.sum()
    x = np.log(pc / (1 - pc))
    _, slope = logistic(x, y, w) if init is None else logistic(x, y, w, init, iters=4)
    return {
        "logloss": float((w * ll).sum() / sw),
        "gain_vs_base": float((w * (ll0 - ll)).sum() / sw),
        "slope": float(slope),
        "citl": float((w * (y - p)).sum() / sw),
        "mean_p": float((w * p).sum() / sw),
    }


def boot_metrics(
    p: np.ndarray, y: np.ndarray, g: np.ndarray, base: float, reps: int, seed: int = 0
) -> dict[str, Any]:
    """Point estimates and a match (series) bootstrap 95% interval, by Poisson
    weights per series."""
    if len(p) == 0:
        return {}
    uniq, inv = np.unique(g, return_inverse=True)
    point = metrics(p, y, np.ones(len(p)), base)
    pc = np.clip(p, EPS, 1 - EPS)
    x = np.log(pc / (1 - pc))
    init = logistic(x, y, np.ones(len(p)))
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = defaultdict(list)
    for _ in range(reps):
        wg = rng.poisson(1.0, len(uniq)).astype(float)
        w = wg[inv]
        if w.sum() == 0:
            continue
        for k, v in metrics(p, y, w, base, init).items():
            draws[k].append(v)
    out: dict[str, Any] = {"n": int(len(p)), "matches": int(len(uniq))}
    for k, v in point.items():
        arr = np.sort(np.array(draws[k]))
        out[k] = [
            round(v, 5),
            round(float(arr[int(0.025 * len(arr))]), 5),
            round(float(arr[int(0.975 * len(arr)) - 1]), 5),
        ]
    return out


def calib_table(
    p: np.ndarray, y: np.ndarray, edges: list[float]
) -> list[dict[str, Any]]:
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        sel = (p >= lo) & (p < hi)
        n = int(sel.sum())
        if n == 0:
            continue
        k = float(y[sel].sum())
        lo95, hi95 = wilson(k, n)
        out.append(
            {
                "bucket": f"{lo:.3f}-{hi:.3f}",
                "n": n,
                "mean_p": round(float(p[sel].mean()), 4),
                "realised": round(k / n, 4),
                "wilson95": [round(lo95, 4), round(hi95, 4)],
            }
        )
    return out


# --- main ---


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--out", required=True, help="directory for the report JSON")
    ap.add_argument("--dataset", help="directory for rows.jsonl.gz (default --out)")
    ap.add_argument(
        "--from",
        dest="start",
        default="2025-11-15",
        help="first scored series day (warm-up before it)",
    )
    ap.add_argument("--before", default="2026-10-20")
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument(
        "--drop-bad-headshots",
        action="store_true",
        help="variant: drop headshots > kills (a data defect)",
    )
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ds_dir = Path(args.dataset or args.out)
    ds_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    conn = connect(args.db_path)
    try:
        maps = load_maps(conn, scf.day_ts(args.before))
        mextra, pextra, sextra = load_extra(conn)
    finally:
        conn.close()
    if args.drop_bad_headshots:
        maps, n_bad = drop_bad_headshots(maps)
        print(f"dropped {n_bad} headshots > kills", flush=True)
    print(
        f"maps {len(maps)} series {len({m.event_id for m in maps})} "
        f"({time.time() - t_start:.0f}s)",
        flush=True,
    )
    rows, cdfs, samples = walk(maps, scf.day_ts(args.start), mextra, pextra, sextra)
    print(f"rows {len(rows)} ({time.time() - t_start:.0f}s)", flush=True)

    # --- Superbet's settled lines joined to the replay -------------------------------
    idx: dict[tuple[int, int, str], dict[int, int]] = defaultdict(dict)
    for i, r in enumerate(rows):
        idx[(r["event_id"], r["map_order"], r["family"])][r["player_id"]] = i
    nick_of: dict[tuple[int, int], dict[str, int]] = defaultdict(dict)
    for m in maps:
        for _, pid, nick, _ in m.players:
            nick_of[(m.event_id, m.order)][nick] = pid
    sb = settled_lines(args.runs_dir)
    joined = []
    miss: Counter[str] = Counter()
    for s in sb:
        nicks = nick_of.get((s["event_id"], s["map_nr"]))
        if not nicks:
            miss["map_not_in_history"] += 1
            continue
        spid = match_subject(s["subject"], nicks)
        if spid is None:
            miss["subject_not_matched"] += 1
            continue
        si = idx.get((s["event_id"], s["map_nr"], s["family"]), {}).get(spid)
        if si is None:
            miss["no_replay_row(sample<8 or before window)"] += 1
            continue
        joined.append((s, si))
    print(
        f"superbet lines {len(sb)} joined {len(joined)} miss {dict(miss)}", flush=True
    )

    # line rule: exact agreement with Superbet's line
    rules: dict[str, Callable[[int], float]] = {
        "half(sample_mean)": lambda i: half(rows[i]["sample_mean"]),
        "half(sample_median)": lambda i: half(float(np.median(samples[i]))),
        "half(exp_mean)": lambda i: (
            half(rows[i]["exp_mean"])
            if rows[i]["exp_ok"]
            else half(rows[i]["sample_mean"])
        ),
        "model_median_line": lambda i: (
            model_median_line(cdfs[i]) or half(rows[i]["sample_mean"])
        ),
        "half(sample_mean-0.5)": lambda i: half(rows[i]["sample_mean"] - 0.5),
        "half(exp_mean-0.5)": lambda i: (
            half(rows[i]["exp_mean"] - 0.5)
            if rows[i]["exp_ok"]
            else half(rows[i]["sample_mean"] - 0.5)
        ),
    }
    rule_fit: dict[str, dict[str, Any]] = {}
    for name, fn in rules.items():
        per: dict[str, list[float]] = defaultdict(list)
        for s, i in joined:
            per[s["family"]].append(fn(i) - s["line"])
        rule_fit[name] = {
            f: {
                "n": len(v),
                "exact": round(sum(1 for d in v if d == 0) / len(v), 4),
                "within1": round(sum(1 for d in v if abs(d) <= 1) / len(v), 4),
                "mean_diff": round(sum(v) / len(v), 3),
            }
            for f, v in sorted(per.items())
        }
    best_rule = {
        f: max(rules, key=lambda r: rule_fit[r][f]["exact"])
        for f in FAMILY.values()
        if f in rule_fit["half(sample_mean)"]
    }
    print(
        "rule exact:",
        {r: {f: v["exact"] for f, v in d.items()} for r, d in rule_fit.items()},
        flush=True,
    )
    print("best rule per family:", best_rule, flush=True)

    # --- the replayed model at Superbet's actual lines ----------------------------
    at_sb: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for s, i in joined:
        pv, src = p_model(rows[i], cdfs[i], samples[i], s["line"])
        if pv is None:
            continue
        a = at_sb[s["family"]]
        a["p"].append(pv)
        a["y"].append(s["y"])
        a["g"].append(s["event_id"])
        a["fair"].append(s["fair_p"] if s["fair_p"] is not None else np.nan)
        a["stored"].append(s["model_p"] if s["model_p"] is not None else np.nan)
        a["stored_model"].append(s["model"] or "")
        a["date"].append(s["date"])

    # --- the dataset at the chosen line ---------------------------------------------
    ds_path = ds_dir / "rows.jsonl.gz"
    fam_arr: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    with gzip.open(ds_path, "wt", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            rule = best_rule.get(r["family"], "half(sample_mean)")
            line = rules[rule](i)
            if line < 0.5:
                line = 0.5
            pv, src = p_model(r, cdfs[i], samples[i], line)
            pe = p_over_exp(cdfs[i], line) if r["exp_ok"] else None
            mc = ce.count_p(samples[i], line, True)
            r2 = dict(r)
            r2.update(
                {
                    "line_rule": rule,
                    "line": line,
                    "p_over": None if pv is None else round(pv, 5),
                    "model_src": src,
                    "p_over_exposure": None if pe is None else round(pe, 5),
                    "p_over_count": None if mc is None else round(mc.p, 5),
                    "y_over": int(r["actual"] > line),
                    "p_over_lines": {
                        f"{ln:.1f}": round(float(1 - cdfs[i][int(ln)]), 5)
                        for ln in (line - 2, line - 1, line + 1, line + 2)
                        if 0.5 <= ln <= KMAX and r["exp_ok"]
                    },
                }
            )
            fh.write(json.dumps(r2, separators=(",", ":")) + "\n")
            if pv is None:
                continue
            fa = fam_arr[r["family"]]
            fa["p"].append(pv)
            fa["y"].append(r2["y_over"])
            fa["g"].append(r["event_id"])
            fa["i"].append(i)
            fa["src"].append(src)
            fa["line"].append(line)
    print(f"dataset {ds_path} ({time.time() - t_start:.0f}s)", flush=True)

    # --- report -----------------------------------------------------------------------
    hist_edges = [round(0.05 * k, 2) for k in range(21)]
    hist_edges[-1] = 1.01
    rep: dict[str, Any] = {
        "window": {"scored_from": args.start, "before": args.before},
        "rows": len(rows),
        "line_rule_fit": rule_fit,
        "best_rule": best_rule,
        "superbet_join_miss": dict(miss),
        "families": {},
        "at_superbet_lines": {},
    }
    for fam, a in sorted(at_sb.items()):
        p = np.array(a["p"])
        y = np.array(a["y"], float)
        g = np.array(a["g"])
        both_p = np.concatenate([p, 1 - p])
        both_y = np.concatenate([y, 1 - y])
        fair = np.array(a["fair"], float)
        stored = np.array(a["stored"], float)
        sm = np.array(a["stored_model"])
        ok = ~np.isnan(stored) & (sm == "round_exposure")
        rep["at_superbet_lines"][fam] = {
            "lines": int(len(p)),
            "matches": int(len(set(a["g"]))),
            "days": int(len(set(a["date"]))),
            "over_realised": round(float(y.mean()), 4),
            "fair_p_over_mean": round(float(np.nanmean(fair)), 4),
            "p_hist_both_sides": calib_table(both_p, both_y, hist_edges),
            "calib_both_sides_edges": calib_table(both_p, both_y, scf.EDGES),
            "metrics_over": boot_metrics(p, y, g, float(y.mean()), args.reps),
            "fair_metrics_over": boot_metrics(
                np.nan_to_num(fair, nan=0.5), y, g, float(y.mean()), args.reps
            ),
            "replay_vs_stored_exposure": {
                "n": int(ok.sum()),
                "mean_abs_diff": (
                    round(float(np.abs(p[ok] - stored[ok]).mean()), 4)
                    if ok.any()
                    else None
                ),
                "corr": (
                    round(float(np.corrcoef(p[ok], stored[ok])[0, 1]), 4)
                    if ok.sum() > 2
                    else None
                ),
            },
            "corr_model_fair": round(
                float(np.corrcoef(p[~np.isnan(fair)], fair[~np.isnan(fair)])[0, 1]), 4
            ),
        }
    for fam, fa in sorted(fam_arr.items()):
        p = np.array(fa["p"])
        y = np.array(fa["y"], float)
        g = np.array(fa["g"])
        both_p = np.concatenate([p, 1 - p])
        both_y = np.concatenate([y, 1 - y])
        hi = both_p >= scf.PRINTABLE_FROM
        rep["families"][fam] = {
            "lines": int(len(p)),
            "matches": int(len(set(fa["g"]))),
            "days": int(len({rows[i]["date"] for i in fa["i"]})),
            "src": dict(Counter(fa["src"])),
            "over_realised": round(float(y.mean()), 4),
            "p_hist_both_sides": calib_table(both_p, both_y, hist_edges),
            "calib_both_sides_edges": calib_table(both_p, both_y, scf.EDGES),
            "sides_ge_070": int(hi.sum()),
            "metrics_over": boot_metrics(p, y, g, float(y.mean()), args.reps),
        }
    # --- Q3 slices (every family) -------------------------------------------------
    slices: dict[str, dict[str, Any]] = {}
    for fam, fa in sorted(fam_arr.items()):
        idxs = fa["i"]
        p = np.array(fa["p"])
        y = np.array(fa["y"], float)
        g = np.array(fa["g"])
        base = float(y.mean())
        feats = [rows[i] for i in idxs]

        def sl(
            name: str,
            keyf: Any,
            feats: list[dict[str, Any]] = feats,
            p: np.ndarray = p,
            y: np.ndarray = y,
            g: np.ndarray = g,
            base: float = base,
            fam: str = fam,
        ) -> None:
            keys = np.array([keyf(r) for r in feats], dtype=object)
            res = {}
            for k in sorted({k for k in keys if k is not None}, key=str):
                sel = keys == k
                if sel.sum() < 200:
                    continue
                res[str(k)] = boot_metrics(p[sel], y[sel], g[sel], base, args.reps)
            slices.setdefault(fam, {})[name] = res

        def tert(v: float | None, cuts: tuple[float, float]) -> str | None:
            if v is None:
                return None
            return "low" if v < cuts[0] else "mid" if v < cuts[1] else "high"

        def q3(vals: list[float | None]) -> tuple[float, float]:
            arr = np.array([v for v in vals if v is not None], float)
            return (float(np.quantile(arr, 1 / 3)), float(np.quantile(arr, 2 / 3)))

        hs_c = q3([r["hs_pct_prior"] for r in feats])
        fk_c = q3([r["fk_diff_prior"] for r in feats])
        adr_c = q3([r["adr_prior"] for r in feats])
        ks_c = q3([r["kill_share_prior"] for r in feats])
        elo_c = q3([(r["elo_team"] + r["elo_opp"]) / 2 for r in feats])
        sl("all", lambda r: "all")
        sl("model_src", lambda r, fa=fa, feats=feats: None)  # filled below
        srcs = np.array(fa["src"], dtype=object)
        res = {}
        for k in sorted(set(fa["src"])):
            sel = srcs == k
            if sel.sum() >= 200:
                res[k] = boot_metrics(p[sel], y[sel], g[sel], base, args.reps)
        slices[fam]["model_src"] = res
        sl(
            "strength_gap",
            lambda r: (
                "even<0.1"
                if abs(r["p_team"] - 0.5) < 0.1
                else "mid0.1-0.2"
                if abs(r["p_team"] - 0.5) < 0.2
                else "big>=0.2"
            ),
        )
        sl("team_fav", lambda r: "fav" if r["p_team"] >= 0.5 else "dog")
        sl("overtime_realised(diagnostic)", lambda r: "ot" if r["ot"] else "reg")
        sl(
            "rounds_realised(diagnostic)",
            lambda r: (
                "<=19"
                if r["rounds"] <= 19
                else "20-22"
                if r["rounds"] <= 22
                else "23-24"
                if r["rounds"] <= 24
                else ">24"
            ),
        )
        sl("map_order", lambda r: str(min(r["map_order"], 3)))
        sl("best_of", lambda r: f"bo{r['best_of']}" if r["best_of"] else "unknown")
        sl(
            "bo_map",
            lambda r: (
                f"bo{r['best_of']}m{min(r['map_order'], 3)}" if r["best_of"] else None
            ),
        )
        sl("map_name", lambda r: r["map_name"] or "unknown")
        sl(
            "pick_proxy(pool)",
            lambda r: (
                "own>opp"
                if r["own_pool"] > r["opp_pool"] + 1
                else "opp>own"
                if r["opp_pool"] > r["own_pool"] + 1
                else "even"
            ),
        )
        sl("role_hs_pct(proxy)", lambda r: tert(r["hs_pct_prior"], hs_c))
        sl("role_fk_diff(proxy)", lambda r: tert(r["fk_diff_prior"], fk_c))
        sl("role_adr(proxy)", lambda r: tert(r["adr_prior"], adr_c))
        sl("kill_share(proxy)", lambda r: tert(r["kill_share_prior"], ks_c))
        sl(
            "player_maps_all",
            lambda r: (
                "<20"
                if r["player_maps_all"] < 20
                else "20-49"
                if r["player_maps_all"] < 50
                else "50-99"
                if r["player_maps_all"] < 100
                else ">=100"
            ),
        )
        sl(
            "player_maps_team(standin)",
            lambda r: (
                "<8"
                if r["player_maps_team"] < 8
                else "8-19"
                if r["player_maps_team"] < 20
                else ">=20"
            ),
        )
        sl(
            "days_since_last",
            lambda r: (
                None
                if r["days_since_last"] is None
                else "<=2"
                if r["days_since_last"] <= 2
                else "2-7"
                if r["days_since_last"] <= 7
                else "7-21"
                if r["days_since_last"] <= 21
                else ">21"
            ),
        )
        sl(
            "tier_proxy(mean_elo)",
            lambda r: tert((r["elo_team"] + r["elo_opp"]) / 2, elo_c),
        )
        sl("line_vs_sample", lambda r, fam=fam: None)
        lv = np.array([rows[i]["sample_mean"] for i in idxs]) - np.array(fa["line"])
        res = {}
        for name, sel in (
            ("line_above_mean", lv < -0.25),
            ("line_near_mean", np.abs(lv) <= 0.25),
            ("line_below_mean", lv > 0.25),
        ):
            if sel.sum() >= 200:
                res[name] = boot_metrics(p[sel], y[sel], g[sel], base, args.reps)
        slices[fam]["line_vs_sample"] = res
        sl("period", lambda r: r["date"][:7])
    rep["slices"] = slices
    rep["elapsed_s"] = round(time.time() - t_start)
    (out_dir / "report.json").write_text(
        json.dumps(rep, indent=1) + "\n", encoding="utf-8"
    )
    print(f"report {out_dir / 'report.json'} ({rep['elapsed_s']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
