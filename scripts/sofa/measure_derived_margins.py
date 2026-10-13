"""Measure B3 of the 2026-10-13 audit (epochs.DERIVED_SHEET_MARGINS).

Pre-registered in docs/sofa/evidence/derived_margins_2026-10-13.md.

Test H: one step ahead on the cached football history. For every match of
the window whose two sides each have a sample, the football joint
(both_over / handicap / most of goals, corners, shots on target, cards) is
built twice with the shipped `joint.build_joint` and side correlation:

  OLD  both sides from the raw sample (what SHEET does today when Superbet
       quotes one side's ladder only),
  NEW  both sides from SHEET's formula: the league prior with K_CENTRE (per
       market), then W_FOOTBALL_RATING x the as-of rating's centre; the
       variance from marginal_centred_stats with the fitted dispersion.

A match whose metric the rating cannot link (UNLINKED) is refused by NEW and
left out of the comparison (reported apart). Scored on the same events
(both models inside [0.05, 0.95]): log-loss and Brier, NEW - OLD, 95% from
resampling matches (2000, seed 0).

Live: how many derived football rows of the days lacked one side's ladder.

Read-only: the history pickle is read, never rewritten; nothing the pipeline
reads is written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_derived_margins.py \\
        [--history data/cache/football_history.pkl] [--from 2026-01-01] \\
        [--to 2026-10-12] [--max-matches 15000] [--live-days 2026-10-09 ...] \\
        [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa.comparability import (  # noqa: E402
    SAME_COMPETITION_METRICS,
    pick_same_competition,
)
from bet.sofa.count_dispersion import load_table  # noqa: E402
from bet.sofa.derived import (  # noqa: E402
    SideStats,
    load_side_correlations,
    marginal_centred_stats,
)
from bet.sofa.epochs import DERIVED_MARGINAL_CENTRES_METRICS  # noqa: E402
from bet.sofa.joint import build_joint  # noqa: E402
from bet.sofa.per_market_k import k_for_market  # noqa: E402
from bet.sofa.samples import (  # noqa: E402
    FRIENDLY_COMPETITION_IDS,
    INDEXED_HISTORY_LIMIT,
)
from scripts.sofa.calibrate_from_cache import (  # noqa: E402
    _load_engine_constants,
    k_centre_for,
    load_baselines,
    prior_for,
)
from scripts.sofa.measure_dependence_goals import event_probs  # noqa: E402

F64 = NDArray[np.float64]
N_BOOT = 2000
MIN_SAMPLE = 8
SAMPLE_N = 10
REACH = 3
RES_LO, RES_HI = 0.05, 0.95
FLOOR = 0.70
CLASSES = ("both_over", "handicap", "most")


def note(msg: str) -> None:
    print(f"[{datetime.now(UTC):%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


def ts_of(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


@dataclass
class Case:
    event_id: int
    base: str
    comp: int
    raw: tuple[SideStats, SideStats]
    new: tuple[SideStats, SideStats] | None  # None = UNLINKED (NEW refuses)
    rated: int  # sides with a rating centre
    x: float
    y: float


def _raw(values: list[float]) -> SideStats:
    n = len(values)
    var = statistics.variance(values) if n > 1 else 0.0
    return SideStats(n=n, mean=statistics.mean(values), variance=var,
                     sd=math.sqrt(var))


def collect(history: Sequence[fr.FootballResult], t0: int, t1: int
            ) -> list[Case]:
    """One case per (match, base) of [t0, t1) with both samples, the book
    and the samples taken strictly before the match."""
    baselines = load_baselines()
    constants = _load_engine_constants()
    k_sport = k_centre_for("football", constants)
    dispersion = load_table()
    keys = sorted(DERIVED_MARGINAL_CENTRES_METRICS)
    hist: dict[tuple[int, str], list[tuple[float, int]]] = defaultdict(list)
    book = fr.RatingBook()
    cases: list[Case] = []
    started = time.time()
    for i, r in enumerate(history):
        if r.ts >= t1:
            break
        if i and i % 100000 == 0:
            note(f"  replayed {i} matches ({time.time() - started:.0f}s), "
                 f"{len(cases)} cases")
        if r.ts >= t0 and r.competition_id not in FRIENDLY_COMPETITION_IDS:
            fc = fr.FootballForecast(book, r.competition_id, r.home_id, r.away_id)
            for key in keys:
                if key not in r.values:
                    continue
                samples = []
                for team in (r.home_id, r.away_id):
                    past = hist[(team, key)]
                    picked = None
                    if key in SAME_COMPETITION_METRICS:
                        picked = pick_same_competition(
                            past[: -INDEXED_HISTORY_LIMIT - 1: -1], r.competition_id,
                            SAMPLE_N, lambda p: p[1], lambda p: True)
                    vals = ([p[0] for p in reversed(picked)] if picked is not None
                            else [p[0] for p in past[-SAMPLE_N:]])
                    samples.append(vals)
                if (len(samples[0]) < MIN_SAMPLE or len(samples[1]) < MIN_SAMPLE
                        or not any(samples[0]) or not any(samples[1])):
                    continue
                raw = (_raw(samples[0]), _raw(samples[1]))
                status = book.link(r.home_id, r.away_id, key)[0]
                new: tuple[SideStats, SideStats] | None = None
                rated = 0
                if status != fr.UNLINKED:
                    prior = prior_for(baselines, key, r.competition_id)
                    k = k_for_market(constants, "football", key, k_sport)
                    disp = dispersion.read("football", key, r.competition_id)
                    sides = []
                    for side, st in zip(("side_a", "side_b"), raw, strict=True):
                        w = st.n / (st.n + k)
                        centre = (st.mean if prior is None
                                  else w * st.mean + (1 - w) * prior)
                        got = fc.centre(key, side)
                        if got is not None:
                            rated += 1
                            centre = (fr.W_FOOTBALL_RATING * got[0]
                                      + (1 - fr.W_FOOTBALL_RATING) * centre)
                        sides.append(marginal_centred_stats(st, key, centre, disp))
                    new = (sides[0], sides[1])
                vh, va = r.values[key]
                cases.append(Case(r.event_id, key[: -len("_for")], r.competition_id,
                                  raw, new, rated, float(vh), float(va)))
        if r.competition_id not in FRIENDLY_COMPETITION_IDS:
            for key, (vh, va) in r.values.items():
                if key not in DERIVED_MARGINAL_CENTRES_METRICS:
                    continue
                for team, v in ((r.home_id, vh), (r.away_id, va)):
                    lst = hist[(team, key)]
                    lst.append((float(v), r.competition_id))
                    if len(lst) > 2 * INDEXED_HISTORY_LIMIT:
                        del lst[:INDEXED_HISTORY_LIMIT]
        book.update(r)
    return cases


def _pmf(st: tuple[SideStats, SideStats], rho: float) -> F64:
    j = build_joint(st[0].mean, st[0].variance, st[1].mean, st[1].variance, rho)
    return np.asarray(j.pmf, dtype=np.float64)


def _events(c: Case) -> tuple[list[float], list[float]]:
    assert c.new is not None
    ma = (c.raw[0].mean + c.new[0].mean) / 2
    mb = (c.raw[1].mean + c.new[1].mean) / 2
    low = max(0, math.floor(min(ma, mb)) - REACH)
    lines = [low + 0.5 + k for k in range(2 * REACH + 1)]
    first = math.floor(-(ma - mb)) - REACH
    hl = [first + 0.5 + k for k in range(2 * REACH + 1)]
    return lines, hl


def _outcomes(c: Case, lines: list[float], hl: list[float]) -> dict[str, F64]:
    both = min(c.x, c.y)
    d = c.x - c.y
    return {
        "both_over": np.array([float(both >= math.floor(L) + 1) for L in lines]),
        "handicap_home": np.array([float(d > -L) for L in hl]),
        "handicap_away": np.array([float(-d > -L) for L in hl]),
        "most": np.array([float(d > 0), float(d < 0), float(d == 0)]),
    }


PARTS = (("both_over", "both_over"), ("handicap_home", "handicap"),
         ("handicap_away", "handicap"), ("most", "most"))


def ratio_ci(num: F64, den: F64, seed: int = 0) -> list[float]:
    """(sum num / sum den, 2.5%, 97.5%) resampling matches."""
    tot = float(den.sum())
    if tot <= 0:
        return [float("nan")] * 3
    rng = np.random.default_rng(seed)
    n = len(num)
    stats = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = rng.integers(0, n, n)
        d = den[idx].sum()
        stats[b] = num[idx].sum() / d if d > 0 else np.nan
    lo, hi = np.nanpercentile(stats, [2.5, 97.5])
    return [float(num.sum() / tot), float(lo), float(hi)]


def score(cases: list[Case], rho_by_base: dict[str, float]) -> dict[str, Any]:
    """Per-match sums, paired on the same events."""
    n = len(cases)
    groups = [*(f"{b}/{c}" for b in sorted({c.base for c in cases}) for c in CLASSES),
              *CLASSES, "all"]
    acc = {g: {k: np.zeros(n) for k in ("ll", "br", "cnt")} for g in groups}
    # the printable region: p >= FLOOR for either model
    region: dict[str, dict[str, F64]] = {
        m: {k: np.zeros(n) for k in ("p", "o", "cnt")} for m in ("old", "new")}
    started = time.time()
    for i, c in enumerate(cases):
        if i and i % 2000 == 0:
            note(f"  scored {i}/{n} ({time.time() - started:.0f}s)")
        assert c.new is not None
        rho = rho_by_base.get(c.base, 0.0)
        lines, hl = _events(c)
        ev_old = event_probs(_pmf(c.raw, rho), lines, hl)
        ev_new = event_probs(_pmf(c.new, rho), lines, hl)
        out = _outcomes(c, lines, hl)
        for part, cls in PARTS:
            po, pn, o = ev_old[part], ev_new[part], out[part]
            keep = (po >= RES_LO) & (po <= RES_HI) & (pn >= RES_LO) & (pn <= RES_HI)
            if not keep.any():
                continue
            po, pn, o = po[keep], pn[keep], o[keep]
            ll = (-(o * np.log(pn) + (1 - o) * np.log(1 - pn))
                  + (o * np.log(po) + (1 - o) * np.log(1 - po)))
            br = (pn - o) ** 2 - (po - o) ** 2
            for g in (f"{c.base}/{cls}", cls, "all"):
                acc[g]["ll"][i] += float(ll.sum())
                acc[g]["br"][i] += float(br.sum())
                acc[g]["cnt"][i] += float(keep.sum())
            for m, p in (("old", po), ("new", pn)):
                sel = p >= FLOOR
                region[m]["p"][i] += float(p[sel].sum())
                region[m]["o"][i] += float(o[sel].sum())
                region[m]["cnt"][i] += float(sel.sum())
    res: dict[str, Any] = {"matches": n}
    for g in groups:
        a = acc[g]
        res[g] = {
            "events": int(a["cnt"].sum()),
            "matches": int((a["cnt"] > 0).sum()),
            "logloss_new_minus_old": ratio_ci(a["ll"], a["cnt"]),
            "brier_new_minus_old": ratio_ci(a["br"], a["cnt"]),
        }
    for m in ("old", "new"):
        r = region[m]
        res[f"printable_{m}"] = {
            "events": int(r["cnt"].sum()),
            "realised_minus_p": ratio_ci(r["o"] - r["p"], r["cnt"]),
        }
    return res


def unlinked_calibration(cases: list[Case], rho_by_base: dict[str, float]
                         ) -> dict[str, Any]:
    """OLD's printable region (p >= FLOOR) in the matches NEW refuses."""
    n = len(cases)
    p_sum, o_sum, cnt = np.zeros(n), np.zeros(n), np.zeros(n)
    for i, c in enumerate(cases):
        ma, mb = c.raw[0].mean, c.raw[1].mean
        low = max(0, math.floor(min(ma, mb)) - REACH)
        lines = [low + 0.5 + k for k in range(2 * REACH + 1)]
        first = math.floor(-(ma - mb)) - REACH
        hl = [first + 0.5 + k for k in range(2 * REACH + 1)]
        ev = event_probs(_pmf(c.raw, rho_by_base.get(c.base, 0.0)), lines, hl)
        out = _outcomes(c, lines, hl)
        for part, _cls in PARTS:
            p, o = ev[part], out[part]
            sel = (p >= FLOOR) & (p <= RES_HI)
            p_sum[i] += float(p[sel].sum())
            o_sum[i] += float(o[sel].sum())
            cnt[i] += float(sel.sum())
    return {"matches": n, "events": int(cnt.sum()),
            "realised_minus_p": ratio_ci(o_sum - p_sum, cnt)}


def live_counts(days: Sequence[str], runs_dir: Path) -> dict[str, Any]:
    """Derived football rows of a metric in DERIVED_MARGINAL_CENTRES_METRICS
    whose fixture has no marginal row for one side (no quoted ladder), and
    how many of them sit in an UNLINKED fixture."""
    from bet.sofa.contracts import Fixture
    from bet.sofa.market_mapper import derived_base, derived_side_metric, is_derived
    from scripts.sofa.run_sheet import determine_side

    out: dict[str, Any] = {}
    for day in days:
        d = runs_dir / day
        try:
            sheet = json.loads((d / "05_sheet.json").read_text())
            fixtures = {
                f["sofascore_event_id"]: Fixture.model_validate_json(json.dumps(f))
                for f in json.loads((d / "02_fixtures.json").read_text())}
        except (OSError, ValueError) as exc:
            out[day] = {"error": str(exc)}
            continue
        sides: dict[tuple[int, str], set[str]] = defaultdict(set)
        unlinked: set[int] = set()
        for r in sheet:
            if r.get("sport") != "football":
                continue
            if any(str(n).startswith("CROSS_LEAGUE_UNLINKED")
                   for n in r.get("notes") or []):
                unlinked.add(r["sofascore_event_id"])
            fx = fixtures.get(r["sofascore_event_id"])
            if (r["market"] in DERIVED_MARGINAL_CENTRES_METRICS and r.get("subject")
                    and fx is not None):
                s = determine_side(r["subject"], fx)
                if s is not None:
                    sides[(r["sofascore_event_id"], r["market"])].add(s)
        rows = rows_missing = 0
        matches: set[int] = set()
        matches_missing: set[int] = set()
        missing_unlinked: set[int] = set()
        rows_missing_unlinked = 0
        # every football derived row of an UNLINKED fixture (the switch
        # refuses them all, whatever the metric)
        all_unlinked = [r for r in sheet if r.get("sport") == "football"
                        and is_derived(r["market"])
                        and r["sofascore_event_id"] in unlinked]
        for r in sheet:
            if r.get("sport") != "football" or not is_derived(r["market"]):
                continue
            base = derived_base(r["market"])
            if base is None:
                continue
            metric = derived_side_metric(base)
            if metric not in DERIVED_MARGINAL_CENTRES_METRICS:
                continue
            eid = r["sofascore_event_id"]
            rows += 1
            matches.add(eid)
            if len(sides.get((eid, metric), set())) < 2:
                rows_missing += 1
                matches_missing.add(eid)
                if eid in unlinked:
                    rows_missing_unlinked += 1
                    missing_unlinked.add(eid)
        out[day] = {"derived_rows": rows, "derived_matches": len(matches),
                    "rows_one_side_unquoted": rows_missing,
                    "matches_one_side_unquoted": len(matches_missing),
                    "rows_one_side_unquoted_unlinked": rows_missing_unlinked,
                    "matches_one_side_unquoted_unlinked": len(missing_unlinked),
                    "all_derived_rows_unlinked": len(all_unlinked),
                    "all_derived_matches_unlinked": len(
                        {r["sofascore_event_id"] for r in all_unlinked})}
        note(f"live {day}: {out[day]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="data/cache/football_history.pkl")
    ap.add_argument("--from", dest="start", default="2026-01-01")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--max-matches", type=int, default=15000)
    ap.add_argument("--max-unlinked", type=int, default=5000)
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--live-days", nargs="*", default=[])
    ap.add_argument("--skip-history", action="store_true")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    result: dict[str, Any] = {
        "registered": "docs/sofa/evidence/derived_margins_2026-10-13.md"}
    if args.live_days:
        result["live"] = live_counts(args.live_days, Path(args.runs_dir))
    if not args.skip_history:
        _fp, history = pickle.loads(Path(args.history).read_bytes())
        note(f"history {len(history)} matches")
        end = datetime.fromisoformat(args.end) + timedelta(days=1)
        t1 = ts_of(end.date().isoformat())
        cases = collect(history, ts_of(args.start), t1)
        del history
        corr = load_side_correlations()
        rho_by_base = {b: float(corr.get(b) or 0.0)
                       for b in {c.base for c in cases}}
        rng = np.random.default_rng(0)
        linked = [c for c in cases if c.new is not None]
        refused = [c for c in cases if c.new is None]
        picked: list[Case] = []
        avail: dict[str, Any] = {}
        for base in sorted({c.base for c in linked}):
            pool = [c for c in linked if c.base == base]
            avail[base] = {
                "eligible_matches": len(pool),
                "unlinked_matches": sum(1 for c in refused if c.base == base),
                "rated_both_sides": sum(1 for c in pool if c.rated == 2)}
            if len(pool) > args.max_matches:
                keep = np.sort(rng.choice(len(pool), args.max_matches, replace=False))
                pool = [pool[i] for i in keep]
            avail[base]["scored_matches"] = len(pool)
            picked.extend(pool)
        note(f"cases {len(cases)}: scored {len(picked)}, unlinked {len(refused)}")
        result["window"] = [args.start, args.end]
        result["rho"] = rho_by_base
        result["population"] = avail
        result["score"] = score(picked, rho_by_base)
        if refused:
            if len(refused) > args.max_unlinked:
                keep = np.sort(
                    rng.choice(len(refused), args.max_unlinked, replace=False))
                refused = [refused[i] for i in keep]
            result["unlinked_old"] = unlinked_calibration(refused, rho_by_base)
    text = json.dumps(result, indent=1, default=float)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
