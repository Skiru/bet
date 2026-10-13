#!/usr/bin/env python3
"""B6 (audit 2026-10-13) - the serve index as a second neighbour coordinate.
Read-only evidence for a pre-registered test (operator O4).

Nothing here writes a config, a curve, a run artifact or a database. The
question (docs/sofa/evidence/tennis_serve_neighbours_2026-10-13.md, registered
before this ran): the rating's neighbour table picks the 600 historical
matches with the nearest win probability p. Does picking the 600 nearest in
(p / sd_p, D / sd_D) - D the match's serve-dominance index (s_A - r_B) +
(s_B - r_A) from online serve / return point ratings - read the score markets
better? The distribution stays the empirical one (``MatchForecast.read`` on the
chosen rows): no point model, no mixture - unlike the serve / return model
declined on 2026-10-08, which REPLACED or MIXED the distribution.

Walk forward exactly as measure_tennis_set_markets (two windows, coefficients
and ``tier_start`` refitted before each window, ``AsOfRating`` at the match's
UTC day, the scoped tier x gender table). The serve ratings and every table
row's D are as of the matches before it (``ServeRatings``, parameters of
2026-10-08: m0 = 8, floor 0.06 - not re-tuned).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_serve_neighbours.py \\
        [--db data/sofa.db] [--out-dir data/audit_2026-10-13/b6] [--boot 2000]

Writes ``rows.npz``, ``results.json`` and ``report.md``. Exit 0 OK, 2 failure.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import tennis_rating as tr  # noqa: E402
from bet.sofa.confidence import line_is_beyond_sample, mode_loses  # noqa: E402
from scripts.sofa.measure_tennis_calibration import (  # noqa: E402
    BucketCurve,
    parse_serve_points,
)
from scripts.sofa.measure_tennis_outcome_model import (  # noqa: E402
    clean_config,
    is_team_cup,
    load,
)
from scripts.sofa.measure_tennis_set_markets import (  # noqa: E402
    MIN_SAMPLE,
    WINDOWS,
    PlayerLog,
    _ci,
    _day_ts,
    boot_mean_diff,
    flip,
    is_bo3_complete,
    sample_for,
)

FloatArr = npt.NDArray[np.float64]
IntArr = npt.NDArray[np.int64]

DEFAULT_OUT = "data/audit_2026-10-13/b6"
M0 = 8.0  # measure_tennis_calibration.tune_serve's pick on 2026-10-08
ETA_FLOOR = 0.06
MIN_SERVE_MATCHES = 6
MU0 = -0.35  # logit(0.587), the start of the serve-point level
FAMILY_LINES: dict[str, tuple[float, ...]] = {
    "games_won_for": (9.5, 10.5, 11.5, 12.5, 13.5, 14.5),
    "games_total": tuple(17.5 + i for i in range(9)),
    "handicap_games": tuple(-6.5 + i for i in range(14)),
    "tiebreaks_total": (0.5, 1.5),
    "sets_total": (2.5,),
    "games_set1_total": (6.5, 7.5, 8.5, 9.5, 10.5, 12.5),
    "games_set2_total": (6.5, 7.5, 8.5, 9.5, 10.5, 12.5),
    "games_won_set1_for": (2.5, 3.5, 4.5, 5.5, 6.5),
}
FAMILIES: tuple[str, ...] = tuple(FAMILY_LINES)
SUBJECT = frozenset({"games_won_for", "games_won_set1_for", "handicap_games"})
NO_SAMPLE = frozenset({"handicap_games"})
PRINT = 0.70


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _lg(p: float) -> float:
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


class ServeRatings:
    """Online serve / return point ratings (measure_tennis_calibration
    build_panel's update, verbatim): P(point won on serve) = sigma(mu + s_i -
    r_j), mu per gender x surface drifting with the points played."""

    def __init__(self, m0: float = M0, floor: float = ETA_FLOOR) -> None:
        self.m0, self.floor = m0, floor
        self.sv: dict[int, float] = {}
        self.rv: dict[int, float] = {}
        self.ms: dict[int, int] = {}
        self.mu: dict[tuple[int, int], float] = {}

    def index(self, home: int, away: int) -> float | None:
        """D = (s_h - r_a) + (s_a - r_h), or None while either player has
        fewer than MIN_SERVE_MATCHES rated matches."""
        if (self.ms.get(home, 0) < MIN_SERVE_MATCHES
                or self.ms.get(away, 0) < MIN_SERVE_MATCHES):
            return None
        sv, rv = self.sv, self.rv
        return (sv.get(home, 0.0) - rv.get(away, 0.0)) + (
            sv.get(away, 0.0) - rv.get(home, 0.0))

    def update(self, r: tr.TennisResult, st: tuple[int, int, int, int]) -> None:
        g = 1 if r.female else 0
        s3 = {"clay": 2, "grass": 3}.get(r.surface, 0)
        mu = self.mu.get((g, s3), MU0)
        hw, hn, aw, an = st
        h, a = r.home_id, r.away_id
        sv, rv, ms = self.sv, self.rv, self.ms
        for srv, ret, won_pts, n_pts in ((h, a, hw, hn), (a, h, aw, an)):
            pi = _sig(mu + sv.get(srv, 0.0) - rv.get(ret, 0.0))
            delta = max(-2.0, min(2.0, (won_pts / n_pts - pi)
                                  / max(pi * (1 - pi), 0.05)))
            sv[srv] = sv.get(srv, 0.0) + max(
                self.floor, 1.0 / (ms.get(srv, 0) + self.m0)) * delta
            rv[ret] = rv.get(ret, 0.0) - max(
                self.floor, 1.0 / (ms.get(ret, 0) + self.m0)) * delta
        ms[h] = ms.get(h, 0) + 1
        ms[a] = ms.get(a, 0) + 1
        tot = (hw + aw) / (hn + an)
        self.mu[(g, s3)] = mu + 0.002 * (_lg(tot) - mu)


class _Cell2D:
    """One scoped table cell's rows with a known D, as numpy arrays sorted by
    p, rebuilt when the cell has grown since the last query."""

    def __init__(self) -> None:
        self.p: list[float] = []
        self.d: list[float] = []
        self.rows: list[tr.Outcome] = []
        self._built = -1
        self.ps: FloatArr = np.empty(0)
        self.ds: FloatArr = np.empty(0)
        self.order: IntArr = np.empty(0, dtype=np.int64)
        self.sd_p = 1.0
        self.sd_d = 1.0

    def add(self, o: tr.Outcome, d: float) -> None:
        self.p.append(o.p)
        self.d.append(d)
        self.rows.append(o)

    def build(self) -> None:
        if self._built == len(self.p):
            return
        p = np.asarray(self.p)
        d = np.asarray(self.d)
        self.order = np.argsort(p, kind="stable")
        self.ps, self.ds = p[self.order], d[self.order]
        self.sd_p = float(p.std()) or 1.0
        self.sd_d = float(d.std()) or 1.0
        self._built = len(self.p)

    def nearest(self, p: float, d: float, k: int = tr.NEIGHBOURS) -> tuple[
            tr.Outcome, ...] | None:
        """The k rows nearest in (dp/sd_p)^2 + (dD/sd_D)^2, exactly: a band of
        rows nearest by p, widened until the k-th distance is inside it."""
        if len(self.p) < k:
            return None
        self.build()
        n = self.ps.size
        i = int(np.searchsorted(self.ps, p))
        band = 4 * k
        while True:
            lo, hi = max(0, i - band), min(n, i + band)
            dp = (self.ps[lo:hi] - p) / self.sd_p
            dd = (self.ds[lo:hi] - d) / self.sd_d
            dist = dp * dp + dd * dd
            if hi - lo < k:
                band *= 2
                continue
            pick = np.argpartition(dist, k - 1)[:k]
            r2 = float(dist[pick].max())
            edge = math.inf
            if lo > 0:
                edge = min(edge, (p - self.ps[lo - 1]) / self.sd_p)
            if hi < n:
                edge = min(edge, (self.ps[hi] - p) / self.sd_p)
            if edge * edge > r2 or (lo == 0 and hi == n):
                break
            band *= 2
        return tuple(self.rows[int(self.order[lo + j])] for j in sorted(pick))


class ServeAsOf(tr.AsOfRating):
    """AsOfRating that also files each table row under its cells with the D
    the match had before it was played, and runs the serve ratings in the same
    time order (so a test match's D sees only earlier matches)."""

    def __init__(self, history: Sequence[tr.TennisResult],
                 coefficients: Mapping[str, Sequence[float]],
                 names: Sequence[str], tier_start: Mapping[str, float] | None,
                 stats: Mapping[int, tuple[int, int, int, int]]) -> None:
        super().__init__(history, coefficients, names, True, tier_start)
        self.serve = ServeRatings()
        self.stats = stats
        self.cells: dict[tuple[str, bool | None], _Cell2D] = defaultdict(_Cell2D)

    def _add(self, r: tr.TennisResult) -> None:
        book = self.book
        d = self.serve.index(r.home_id, r.away_id)
        if (r.completed and book.rated(r.home_id) >= tr.MIN_RATED
                and book.rated(r.away_id) >= tr.MIN_RATED):
            c = self._coefficients.get(r.tier)
            if c is not None:
                feats = book.features(r.home_id, r.away_id, r.surface, r.ts)
                for o in tr._outcomes(r, tr.calibrated_p(c, feats, self._names)):
                    self.model.insert(o)
                    if d is not None and not (o.match_tiebreak and o.tier != "ITF"):
                        for key in ((o.tier, o.female), (o.tier, None)):
                            self.cells[key].add(o, d)
        st = self.stats.get(r.event_id)
        if st is not None and r.completed:
            self.serve.update(r, st)
        book.update(r)


def load_serve_stats(db: str) -> dict[int, tuple[int, int, int, int]]:
    out: dict[int, tuple[int, int, int, int]] = {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        for eid, sj in con.execute(
            "select sofascore_event_id, statistics_json from sofa_event_stats "
            "where statistics_json like '%First serve return points%'"
        ):
            parsed = parse_serve_points(sj)
            if parsed:
                out[int(eid)] = parsed
    finally:
        con.close()
    return out


def b6_values(sets: Sequence[tuple[int, int]]) -> dict[str, float]:
    s1, s2 = sets[0], sets[1]
    gf = sum(a for a, _ in sets)
    ga = sum(b for _, b in sets)
    return {
        "games_won_for": float(gf),
        "games_total": float(gf + ga),
        "handicap_games": float(gf - ga),
        "tiebreaks_total": float(sum(1 for a, b in sets if (a, b) in ((7, 6), (6, 7)))),
        "sets_total": float(len(sets)),
        "games_set1_total": float(s1[0] + s1[1]),
        "games_set2_total": float(s2[0] + s2[1]),
        "games_won_set1_for": float(s1[0]),
    }


def wins(family: str, value: float, line: float, direction: str) -> int:
    if family == "handicap_games":
        return int(value > -line)
    return int(value > line) if direction == "OVER" else int(value < line)


ROW_FIELDS = ("event", "window", "family", "line", "dir", "tier", "y",
              "p_base", "p_serve", "beyond", "mode")


def walk(
    history: Sequence[tr.TennisResult], meta: Mapping[int, tuple[str, str]],
    stats: Mapping[int, tuple[int, int, int, int]], window: str,
    test_from: int, test_to: int,
) -> tuple[dict[str, list[Any]], dict[str, Any]]:
    coefficients, tier_start = clean_config(history, test_from)
    rating = ServeAsOf(history, coefficients, tr.V5_FEATURES, tier_start, stats)
    logs: dict[int, PlayerLog] = defaultdict(PlayerLog)
    out: dict[str, list[Any]] = {f: [] for f in ROW_FIELDS}
    info: dict[str, Any] = {"skips": defaultdict(int),
                            "by_tier": defaultdict(lambda: [0, 0])}
    win_code = {"W1": 1, "W2": 2}[window]
    j = 0
    for r in history:
        if r.ts >= test_to:
            break
        while j < len(history) and history[j].ts < r.ts:
            h = history[j]
            j += 1
            if is_bo3_complete(h):
                logs[h.home_id].rows.append(
                    (h.ts, h.event_id, h.surface, b6_values(h.sets)))
                logs[h.away_id].rows.append(
                    (h.ts, h.event_id, h.surface, b6_values(flip(h.sets))))
        if r.ts < test_from:
            continue
        cat, text = meta.get(r.event_id, ("", ""))
        if is_team_cup(text) or not is_bo3_complete(r):
            info["skips"]["not_in_population"] += 1
            continue
        day = r.ts - r.ts % 86400
        model = rating.model_at(day)
        fc = model.forecast(r.home_id, r.away_id, cat, r.surface,
                            datetime.fromtimestamp(r.ts, UTC))
        if fc is None or not fc.neighbours_home:
            info["skips"]["unrated"] += 1
            continue
        d = rating.serve.index(r.home_id, r.away_id)
        info["by_tier"][r.tier][0] += 1
        if d is None or fc.table_scope == "pooled":
            info["skips"]["no_serve_index" if d is None else "pooled_table"] += 1
            continue
        key = ((r.tier, rating.book.female.get(r.home_id, False))
               if fc.table_scope == "tier_gender" else (r.tier, None))
        cell = rating.cells.get(key)
        home = cell.nearest(fc.p_home, d) if cell is not None else None
        away = cell.nearest(1.0 - fc.p_home, d) if cell is not None else None
        if home is None or away is None:
            info["skips"]["thin_cell"] += 1
            continue
        info["by_tier"][r.tier][1] += 1
        alt = tr.MatchForecast(fc.p_home, home, away, fc.rated_home, fc.rated_away,
                               fc.table_scope)
        actual = {"side_a": b6_values(r.sets), "side_b": b6_values(flip(r.sets))}
        tier_c = tr.TIERS.index(r.tier) if r.tier in tr.TIERS else -1
        for fi, family in enumerate(FAMILIES):
            sides = ("side_a", "side_b") if family in SUBJECT else (None,)
            directions = ("OVER",) if family == "handicap_games" else ("OVER", "UNDER")
            for side in sides:
                player = r.away_id if side == "side_b" else r.home_id
                value = actual[side or "side_a"][family]
                values: list[float] | None = None
                if family not in NO_SAMPLE:
                    if side is None:
                        sa = sample_for(logs[r.home_id], r.surface, r.ts, family)
                        sb = sample_for(logs[r.away_id], r.surface, r.ts, family)
                        if len(sa) >= MIN_SAMPLE and len(sb) >= MIN_SAMPLE:
                            values = list({e: v for e, v in (*sa, *sb)}.values())
                    else:
                        own = sample_for(logs[player], r.surface, r.ts, family)
                        if len(own) >= MIN_SAMPLE:
                            values = [v for _, v in own]
                for line in FAMILY_LINES[family]:
                    for direction in directions:
                        pb = fc.read(family, side, line, direction)
                        ps = alt.read(family, side, line, direction)
                        if pb is None or ps is None:
                            continue
                        out["event"].append(r.event_id)
                        out["window"].append(win_code)
                        out["family"].append(fi)
                        out["line"].append(line)
                        out["dir"].append(0 if direction == "OVER" else 1)
                        out["tier"].append(tier_c)
                        out["y"].append(wins(family, value, line, direction))
                        out["p_base"].append(pb)
                        out["p_serve"].append(ps)
                        out["beyond"].append(
                            -1 if values is None
                            else int(line_is_beyond_sample(line, direction, values)))
                        out["mode"].append(
                            -1 if values is None
                            else int(mode_loses(line, direction, values)))
    info["skips"] = dict(info["skips"])
    info["by_tier"] = {k: {"forecast": v[0], "with_serve_index": v[1]}
                       for k, v in info["by_tier"].items()}
    return out, info


def ll(p: FloatArr, y: FloatArr) -> FloatArr:
    q = np.clip(p, 0.01, 0.99)
    res: FloatArr = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    return res


def recalibrated(p_fit: FloatArr, y_fit: FloatArr, p: FloatArr) -> FloatArr:
    """The shipped bucket curve fitted on (p_fit, y_fit), applied to p; a
    bucket below its row floor keeps the raw p."""
    curve = BucketCurve().fit(p_fit, y_fit)
    got = curve.predict(p)
    out: FloatArr = np.where(np.isnan(got), p, got)
    return out


def score(rows: Mapping[str, Any], boot: int) -> dict[str, Any]:
    res: dict[str, Any] = {}
    y = rows["y"].astype(np.float64)
    pb, ps = rows["p_base"], rows["p_serve"]
    for fi, family in enumerate(FAMILIES):
        fam = rows["family"] == fi
        e: dict[str, Any] = {"rows": int(fam.sum()),
                             "matches": int(np.unique(rows["event"][fam]).size)}
        if not fam.any():
            res[family] = e
            continue
        d = ll(ps[fam], y[fam]) - ll(pb[fam], y[fam])
        e["ll_base"] = float(ll(pb[fam], y[fam]).mean())
        e["diff"] = boot_mean_diff(rows["event"][fam], d, boot)
        for w in (1, 2):
            sel = fam & (rows["window"] == w)
            if sel.any():
                dw = ll(ps[sel], y[sel]) - ll(pb[sel], y[sel])
                e[f"diff_W{w}"] = boot_mean_diff(rows["event"][sel], dw, boot)
                e[f"matches_W{w}"] = int(np.unique(rows["event"][sel]).size)
        if family == "games_won_for":
            sel = fam & (rows["line"] >= 12.5) & (rows["line"] <= 14.5)
            dz = ll(ps[sel], y[sel]) - ll(pb[sel], y[sel])
            e["diff_12_5_to_14_5"] = boot_mean_diff(rows["event"][sel], dz, boot)
        # recalibration: a bucket curve per direction fitted on W1, scored on W2
        w2 = fam & (rows["window"] == 2)
        cal_b = np.full(pb.shape, np.nan)
        cal_s = np.full(ps.shape, np.nan)
        for di in (0, 1):
            fit = fam & (rows["window"] == 1) & (rows["dir"] == di)
            tgt = w2 & (rows["dir"] == di)
            if fit.any() and tgt.any():
                cal_b[tgt] = recalibrated(pb[fit], y[fit], pb[tgt])
                cal_s[tgt] = recalibrated(ps[fit], y[fit], ps[tgt])
        ok = w2 & ~np.isnan(cal_b) & ~np.isnan(cal_s)
        if ok.any():
            dc = ll(cal_s[ok], y[ok]) - ll(cal_b[ok], y[ok])
            e["diff_W2_recalibrated"] = boot_mean_diff(rows["event"][ok], dc, boot)
        for name, p in (("base", pb), ("serve", ps)):
            z = fam & (p >= PRINT)
            if z.any():
                anyg = z & ((rows["beyond"] == 1) | (rows["mode"] == 1))
                e[f"print_{name}"] = {
                    "rows": int(z.sum()),
                    "mean_p": float(p[z].mean()), "realised": float(y[z].mean()),
                    "LINE_BEYOND_SAMPLE": int((z & (rows["beyond"] == 1)).sum()),
                    "MODE_LOSES": int((z & (rows["mode"] == 1)).sum()),
                    "either": int(anyg.sum()),
                    "no_sample": int((z & (rows["beyond"] == -1)).sum()),
                }
        e["threshold_met"] = bool(
            e.get("diff_W1", (0, 0, 1))[2] < 0 and e.get("diff_W2", (0, 0, 1))[2] < 0
            and e.get("diff_W2_recalibrated", (0, 0, 1))[2] < 0)
        res[family] = e
    return res


def render(results: Mapping[str, Any]) -> str:
    lines = ["# B6 - wynik (log-loss, sąsiedzi 2D - 1D, 1e-4 nat)", "",
             "| rodzina | wiersze | mecze | W1+W2 [95%] | W1 | W2 | W2 po rekalibracji "
             "| próg |", "|---|---|---|---|---|---|---|---|"]
    for f, e in results["families"].items():
        lines.append(
            f"| {f} | {e['rows']} | {e['matches']} | {_ci(e.get('diff'))} "
            f"| {_ci(e.get('diff_W1'))} | {_ci(e.get('diff_W2'))} "
            f"| {_ci(e.get('diff_W2_recalibrated'))} "
            f"| {'tak' if e.get('threshold_met') else 'nie'} |")
    g = results["families"].get("games_won_for", {})
    if "diff_12_5_to_14_5" in g:
        lines.append("")
        lines.append(f"games_won_for 12,5-14,5: {_ci(g['diff_12_5_to_14_5'])}")
    lines.append("")
    for f, e in results["families"].items():
        for name in ("base", "serve"):
            pz = e.get(f"print_{name}")
            if pz:
                lines.append(
                    f"- {f} {name}: p>=0,70 {pz['rows']} wierszy, p {pz['mean_p']:.3f}"
                    f" zreal. {pz['realised']:.3f}; LINE_BEYOND_SAMPLE "
                    f"{pz['LINE_BEYOND_SAMPLE']}, MODE_LOSES {pz['MODE_LOSES']}, "
                    f"razem {pz['either']}, bez próbki {pz['no_sample']}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=None, help="default: SOFA_DB_PATH / data/sofa.db")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--rows", default=None, help="score saved rows.npz only")
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if args.rows:
        loaded = np.load(args.rows)
        rows = {k: loaded[k] for k in loaded.files}
        info: dict[str, Any] = json.loads((out / "walk.json").read_text())
    else:
        from bet.sofa.config import SofaConfig

        db = str(args.db or SofaConfig.from_env().db_path)
        history, meta = load(db)
        stats = load_serve_stats(db)
        print(f"history {len(history)}, serve stats {len(stats)} "
              f"({time.time() - t0:.0f}s)", flush=True)
        parts = []
        info = {"db": db, "serve_stats": len(stats), "m0": M0,
                "eta_floor": ETA_FLOOR, "windows": {}}
        for name, a, b in WINDOWS:
            part, winfo = walk(history, meta, stats, name, _day_ts(a), _day_ts(b))
            parts.append(part)
            info["windows"][name] = winfo
            print(f"{name}: {len(part['event'])} rows, {winfo} "
                  f"({time.time() - t0:.0f}s)", flush=True)
        rows = {
            f: np.asarray([v for p in parts for v in p[f]],
                          dtype=np.float64 if f in ("line", "p_base", "p_serve")
                          else np.int64)
            for f in ROW_FIELDS
        }
        np.savez_compressed(out / "rows.npz", **rows)
        (out / "walk.json").write_text(json.dumps(info, indent=1))
    results = {**info, "boot": args.boot, "families": score(rows, args.boot)}
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "report.md").write_text(render(results))
    print(render(results))
    print(f"wrote {out} ({time.time() - t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise SystemExit(2) from exc
