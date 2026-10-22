#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""Which per-leg chance should the chat-slip knapsack maximise - read-only
evidence, walk-forward, no look-ahead in any objective.

Follows measure_slip_chance.py (POMIAR_SZANSA_NOGI_KUPON_CZAT_2026-10-20.md):
b (slip_builder.measured_chance) is better calibrated than confidence a, but
a ranks legs better inside an odds band. Question: does an objective ranked
by a but at an honest level pick better slips than b?

Pre-registered objectives (fixed before any test result was read; nothing
added afterwards except what is labelled exploratory):

  B   b = slip_builder.measured_chance, walk-forward (day d reads only
      runs/sofa/<d>/family_record.json - the 14 days strictly before d).
  A   raw confidence a (the printed one, 13_results.json).
  H1  a_cal: confidence recalibrated walk-forward. For test day d an
      isotonic regression (pool-adjacent-violators on (a, hit), ties pooled,
      then linear interpolation between the blocks' mean a - flat beyond
      the ends - so the map stays strictly increasing and keeps a's order
      inside a sport) is fitted on every settled official printed single of
      2026-10-05 .. d-1 (days before 10-13 graded by
      record_results.graded_confidence, the ledger's own grader; days from
      10-13 from 13_results.json), per sport where the sport has >= 300
      training rows, else on all sports pooled. No odds covariate. Clipped
      to [0.01, 0.99].
  H2  min(a_cal, b): the honest level, the builder's cap kept.

Leg level (test days 2026-10-13 .. 2026-10-19, WIN / LOSS printed singles
with b defined): Brier, log-loss, match bootstrap, paired H1-B, H2-B, A-B,
H1-A; ranking inside odds bands as in the previous report.

Slip level: for each test day and window of kickoff (local Europe/Warsaw):
sliding 3-hour windows starting 10:00 .. 23:00 every hour, the non-
overlapping 3-hour windows 10/13/16/19/22, and the whole day, at targets 2,
4 and 8, slip_builder.best_slip (the exact knapsack, max 5 legs, one per
match, odds 1.10-2.00) runs with each objective as the leg chance, mimicking
slip_builder.build(..., allow_rest=True, slips=1): the supported tiers
first, the whole pool when they reach no slip. Reads, vetoes and the
start-time-vs-now filter are ignored (they are as-of-build). The pool is the
WIN / LOSS legs only: a refunded / void / unsettled leg is dropped from the
pool before the search (for every objective alike - a refund would remove
the leg from a real slip anyway). Per slip: all legs won, mean and sum of
(hit - 1/odds), the objective's predicted slip chance (and b's).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_slip_objective.py \\
        [--from 2026-10-13 --to 2026-10-19] [--reps 2000] [--md-out f] [--json-out f]
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import coupon_results as cr  # noqa: E402
from bet.sofa import family_record as fr  # noqa: E402
from bet.sofa import slip_builder as sb  # noqa: E402
from scripts.sofa.measure_slip_chance import (  # noqa: E402
    BANDS,
    EPS,
    Boot,
    arr,
    auc,
    brier,
    days,
    fmt,
    logloss,
    record_for,
)

HISTORY_FROM = "2026-10-05"  # the first stats-only coupon (11_coupon.json)
MIN_SPORT_ROWS = 300
OBJ = ("B", "A", "H1", "H2")
NAMES = {"B": "b = measured_chance (obecny)", "A": "a = pewność", "H1": "a_cal (izotoniczna walk-forward)",
         "H2": "min(a_cal, b)", "c": "1/kurs"}
TARGETS = (2.0, 4.0, 8.0)
SLIDE_STARTS = tuple(range(10, 24))
BLOCK_STARTS = (10, 13, 16, 19, 22)
CAL_BINS = (0.0, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01)


# ---------------------------------------------------------------- history

def history_rows(runs: Path, first: str, last: str, db: str, cache: Path | None) -> list[dict[str, Any]]:
    """Settled official printed singles of first..last graded by the ledger's grader."""
    if cache is not None and cache.exists():
        doc = json.loads(cache.read_text(encoding="utf-8"))
        if doc.get("span") == [first, last]:
            return list(doc["rows"])
    from scripts.sofa.record_results import graded_confidence
    out: list[dict[str, Any]] = []
    for d in days(first, last):
        for g in graded_confidence(str(runs), d, db):
            if g["variant"] != fr.VARIANT:
                continue
            for s in g["singles"]:
                if s.get("outcome") not in ("WIN", "LOSS"):
                    continue
                src = s["source"]
                if src.get("confidence") is None:
                    continue
                out.append({"day": d, "sport": str(src.get("sport") or "football"),
                            "a": float(src["confidence"]), "y": 1.0 if s["outcome"] == "WIN" else 0.0})
    if cache is not None:
        cache.write_text(json.dumps({"span": [first, last], "rows": out}), encoding="utf-8")
    return out


# ---------------------------------------------------------------- test rows

def test_rows(runs: Path, day: str, db: str, notes: list[str]) -> list[dict[str, Any]]:
    res = cr.load(runs / day)
    if res is None:
        notes.append(f"{day}: brak 13_results.json - pominięty")
        return []
    coupon = json.loads((runs / day / "11_coupon.json").read_text(encoding="utf-8"))
    by_key: dict[str, dict[str, Any]] = {}
    for leg in (coupon.get("singles") or []) + (coupon.get("legs") or []):
        by_key.setdefault(cr.key_of(leg), leg)
    record, how = record_for(runs, day, db)
    fam, sport = sb.shortfalls(record)
    plus = frozenset(k for k, e in (record.get("families") or {}).items() if fr.on_plus(e))
    out: list[dict[str, Any]] = []
    cnt: Counter[str] = Counter()
    for key, e in (res.get("legs") or {}).items():
        cnt[str(e.get("outcome"))] += 1
        if e.get("outcome") not in ("WIN", "LOSS"):
            continue
        leg = by_key.get(key)
        if leg is None:
            cnt["no_coupon_leg"] += 1
            continue
        odds = e.get("odds") or leg.get("offered_odds") or leg.get("odds")
        conf = e.get("confidence") if e.get("confidence") is not None else leg.get("confidence")
        if not odds or conf is None:
            cnt["no_price_or_conf"] += 1
            continue
        odds, conf = float(odds), float(conf)
        src = dict(leg)
        src["confidence"] = conf
        src["offered_odds"] = odds
        t = sb.tier(src, plus)
        mc = sb.measured_chance(src, odds, fam, sport, t)
        if mc is None:
            cnt["no_measured_chance"] += 1
            continue
        mk = str(leg.get("group_key") or leg.get("sofascore_event_id"))
        out.append({
            "day": day, "match": f"{day}|{mk}", "match_key": mk, "key": key,
            "sport": str(leg.get("sport") or "football"), "odds": odds,
            "y": 1.0 if e["outcome"] == "WIN" else 0.0, "tier": t,
            "kickoff_utc": leg.get("kickoff_utc"), "family": fr.family_key(src),
            "A": conf, "B": mc[0], "c": 1.0 / odds,
        })
    notes.append(f"{day}: rekord rodzin {how} (dni {fr.span(record)}); wyniki {dict(cnt)}")
    return out


# ---------------------------------------------------------------- isotonic

class Iso:
    """PAV isotonic fit, interpolated between block means (strictly increasing)."""

    def __init__(self, x: np.ndarray, y: np.ndarray) -> None:
        ux, inv = np.unique(x, return_inverse=True)
        w = np.bincount(inv).astype(float)
        sy = np.bincount(inv, weights=y)
        sx = ux * w
        blocks: list[list[float]] = []  # [sum_w, sum_y, sum_x]
        for i in range(len(ux)):
            blocks.append([w[i], sy[i], sx[i]])
            while len(blocks) > 1 and blocks[-2][1] / blocks[-2][0] >= blocks[-1][1] / blocks[-1][0]:
                b2 = blocks.pop()
                b1 = blocks[-1]
                b1[0] += b2[0]
                b1[1] += b2[1]
                b1[2] += b2[2]
        self.xs = np.array([b[2] / b[0] for b in blocks])
        self.ys = np.array([b[1] / b[0] for b in blocks])
        self.n = int(len(x))
        self.blocks = len(blocks)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        y: np.ndarray
        if len(self.xs) == 1:
            y = np.clip(np.full_like(x, self.ys[0]), 0.01, 0.99)
        else:
            y = np.clip(np.interp(x, self.xs, self.ys), 0.01, 0.99)
        return y


def add_calibrated(test: list[dict[str, Any]], hist: list[dict[str, Any]], notes: list[str]) -> None:
    """a_cal per test day from settled rows strictly before it."""
    test_days = sorted({r["day"] for r in test})
    for d in test_days:
        train = [h for h in hist if h["day"] < d] + [
            {"day": r["day"], "sport": r["sport"], "a": r["A"], "y": r["y"]} for r in test if r["day"] < d]
        pooled = Iso(np.array([t["a"] for t in train]), np.array([t["y"] for t in train]))
        per: dict[str, Iso] = {}
        n_sport = Counter(t["sport"] for t in train)
        for s, n in n_sport.items():
            if n >= MIN_SPORT_ROWS:
                rs = [t for t in train if t["sport"] == s]
                per[s] = Iso(np.array([t["a"] for t in rs]), np.array([t["y"] for t in rs]))
        rows = [r for r in test if r["day"] == d]
        for s in {r["sport"] for r in rows}:
            f = per.get(s, pooled)
            sel = [r for r in rows if r["sport"] == s]
            vals = f(np.array([r["A"] for r in sel]))
            for r, v in zip(sel, vals, strict=True):
                r["H1"] = float(v)
                r["H2"] = float(min(v, r["B"]))
        span = f"{min(t['day'] for t in train)}..{max(t['day'] for t in train)}"
        own = ", ".join(f"{s} {n_sport[s]}" for s in sorted(per))
        pool_s = sorted({r["sport"] for r in rows} - set(per))
        notes.append(f"{d}: trening {span}, {len(train)} nóg; własna krzywa: {own}; pula (wszystkie sporty, {len(train)}): {', '.join(pool_s) or '-'}")


# ---------------------------------------------------------------- leg level

def leg_scores(rows: list[dict[str, Any]], reps: int, seed: int, lines: list[str], out: dict[str, Any], title: str) -> None:
    y = arr(rows, "y")
    boot = Boot([r["match"] for r in rows], reps, seed)
    one = np.ones(len(rows))
    lines.append(f"\n**{title}** - {len(rows)} nóg, {len({r['match'] for r in rows})} meczów, trafienie {y.mean():.3f}\n")
    lines.append("| cel | średnia p | Brier [95%] | log-loss [95%] |")
    lines.append("|---|---|---|---|")
    res: dict[str, Any] = {}
    for k in (*OBJ, "c"):
        p = arr(rows, k)
        b, ll = boot.ratio(brier(p, y), one), boot.ratio(logloss(p, y), one)
        res[k] = {"brier": b, "logloss": ll, "mean_p": float(p.mean())}
        lines.append(f"| {k}: {NAMES[k]} | {p.mean():.3f} | {fmt(b)} | {fmt(ll)} |")
    lines.append("\n| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] |")
    lines.append("|---|---|---|")
    for u, v in (("H1", "B"), ("H2", "B"), ("A", "B"), ("H1", "A"), ("H2", "H1")):
        pu, pv = arr(rows, u), arr(rows, v)
        db_ = boot.ratio(brier(pu, y) - brier(pv, y), one)
        dl = boot.ratio(logloss(pu, y) - logloss(pv, y), one)
        res[f"{u}-{v}"] = {"brier": db_, "logloss": dl}
        lines.append(f"| {u} − {v} | {fmt(db_, 2, 1000)} | {fmt(dl, 2, 1000)} |")
    out[title] = res


def calibration(rows: list[dict[str, Any]], k: str, lines: list[str]) -> None:
    lines.append(f"\n**{k}: {NAMES[k]}**\n")
    lines.append("| przedział p | N | średnia p | trafienie | trafienie − p |")
    lines.append("|---|---|---|---|---|")
    for lo, hi in zip(CAL_BINS, CAL_BINS[1:], strict=False):
        sel = [r for r in rows if lo <= r[k] < hi]
        if not sel:
            continue
        mp = float(np.mean([r[k] for r in sel]))
        hr = float(np.mean([r["y"] for r in sel]))
        lab = f"{lo:.2f}-{hi:.2f}" if hi <= 1 else f"{lo:.2f}+"
        lines.append(f"| {lab} | {len(sel)} | {mp:.3f} | {hr:.3f} | {hr - mp:+.3f} |")


def ranking(rows: list[dict[str, Any]], reps: int, seed: int, lines: list[str], out: dict[str, Any]) -> None:
    lines.append("| pasmo kursu | N | cel | górna − dolna połowa (trafienie − 1/k) [95%] | AUC |")
    lines.append("|---|---|---|---|---|")
    for lo, hi in BANDS:
        band = [r for r in rows if lo <= r["odds"] < hi or (hi == 2.00 and r["odds"] == 2.00)]
        if len(band) < 40:
            lines.append(f"| {lo:.2f}-{hi:.2f} | {len(band)} | - | za mało nóg | |")
            continue
        boot = Boot([r["match"] for r in band], reps, seed)
        y, c = arr(band, "y"), arr(band, "c")
        for k in OBJ:
            g = arr(band, k) - c
            med = float(np.median(g))
            top = g > med
            if top.sum() == 0 or (~top).sum() == 0:
                top = g >= med
            bot = ~top
            ex = y - c
            st, sbm = boot.sums(ex * top), boot.sums(ex * bot)
            nt, nb = boot.sums(top.astype(float)), boot.sums(bot.astype(float))
            point = st.sum() / nt.sum() - sbm.sum() / nb.sum()
            bs = (boot.w @ st) / np.maximum(boot.w @ nt, EPS) - (boot.w @ sbm) / np.maximum(boot.w @ nb, EPS)
            diff = (point, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))
            au = auc(arr(band, k), y)
            out[f"{lo:.2f}-{hi:.2f}|{k}"] = {"n": len(band), "diff": diff, "auc": au}
            lines.append(f"| {lo:.2f}-{hi:.2f} | {len(band)} | {k} | {fmt(diff, 1, 100)} pp | {au:.3f} |")


def per_sport(rows: list[dict[str, Any]], reps: int, seed: int, lines: list[str], out: dict[str, Any]) -> None:
    lines.append("| sport | N | mecze | Brier B | Brier A | Brier H1 | Brier H2 | Δ H1−B ×1000 [95%] | Δ H2−B ×1000 [95%] |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for s in sorted({r["sport"] for r in rows}):
        rs = [r for r in rows if r["sport"] == s]
        y = arr(rs, "y")
        one = np.ones(len(rs))
        boot = Boot([r["match"] for r in rs], reps, seed)
        br = {k: float(np.mean(brier(arr(rs, k), y))) for k in OBJ}
        d1 = boot.ratio(brier(arr(rs, "H1"), y) - brier(arr(rs, "B"), y), one)
        d2 = boot.ratio(brier(arr(rs, "H2"), y) - brier(arr(rs, "B"), y), one)
        out[s] = {"n": len(rs), "brier": br, "H1-B": d1, "H2-B": d2}
        lines.append(f"| {s} | {len(rs)} | {len({r['match'] for r in rs})} | {br['B']:.4f} | {br['A']:.4f} | {br['H1']:.4f} | {br['H2']:.4f} | {fmt(d1, 2, 1000)} | {fmt(d2, 2, 1000)} |")


def lodo_leg(rows: list[dict[str, Any]], lines: list[str]) -> None:
    ds = sorted({r["day"] for r in rows})
    lines.append("\n| para | Δ Brier ×1000 ogółem | per dzień | bez dnia: min..max | znak stały |")
    lines.append("|---|---|---|---|---|")
    for u, v in (("H1", "B"), ("H2", "B"), ("A", "B")):
        def d(rs: list[dict[str, Any]], u: str = u, v: str = v) -> float:
            y = arr(rs, "y")
            return float(np.mean(brier(arr(rs, u), y) - brier(arr(rs, v), y))) * 1000
        tot = d(rows)
        per = [d([r for r in rows if r["day"] == x]) for x in ds]
        wo = [d([r for r in rows if r["day"] != x]) for x in ds]
        same = all(np.sign(w) == np.sign(tot) for w in wo)
        lines.append(f"| {u} − {v} | {tot:+.2f} | {' / '.join(f'{x:+.1f}' for x in per)} | {min(wo):+.2f}..{max(wo):+.2f} | {'tak' if same else 'NIE'} |")


# ---------------------------------------------------------------- slip level

def local_start(r: dict[str, Any]) -> datetime.datetime | None:
    k = r.get("kickoff_utc")
    if not k:
        return None
    return datetime.datetime.fromisoformat(str(k).replace("Z", "+00:00")).astimezone(sb.LOCAL)


def windows_of(day: str) -> list[tuple[str, str, datetime.datetime | None, datetime.datetime | None]]:
    """(kind, label, lo, hi) local; kind slide / block / day."""
    base = datetime.datetime.fromisoformat(day).replace(tzinfo=sb.LOCAL)
    out: list[tuple[str, str, datetime.datetime | None, datetime.datetime | None]] = []
    for h in SLIDE_STARTS:
        lo = base + datetime.timedelta(hours=h)
        out.append(("slide", f"{h:02d}-{(h + 3) % 24:02d}", lo, lo + datetime.timedelta(hours=3)))
    for h in BLOCK_STARTS:
        lo = base + datetime.timedelta(hours=h)
        out.append(("block", f"{h:02d}-{(h + 3) % 24:02d}", lo, lo + datetime.timedelta(hours=3)))
    out.append(("day", "cały dzień", None, None))
    return out


def run_knapsack(pool: list[dict[str, Any]], obj: str, target: float) -> list[dict[str, Any]] | None:
    legs = [sb.Leg({"group_key": r["match_key"], "kickoff_utc": r["kickoff_utc"], "_row": r},
                   r["odds"], max(min(float(r[obj]), 0.999), 1e-6), obj, int(r["tier"]))
            for r in pool]
    sup = [x for x in legs if x.tier < sb.TIER_REST]
    s = sb.best_slip(sup, target, sb.MAX_LEGS) if sup else None
    supported = s is not None
    if s is None:
        s = sb.best_slip(legs, target, sb.MAX_LEGS)
    if s is None:
        return None
    rows = [x.leg["_row"] for x in s.legs]
    for r in rows:
        r["_supported"] = supported
    return rows


def slips(rows: list[dict[str, Any]], notes: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if sb.MIN_LEG_ODDS <= r["odds"] <= sb.MAX_LEG_ODDS:
            by_day[r["day"]].append(r)
    for day in sorted(by_day):
        pool_all = by_day[day]
        no_ko = sum(1 for r in pool_all if local_start(r) is None)
        t0 = time.time()
        for kind, label, lo, hi in windows_of(day):
            pool = pool_all if lo is None else [r for r in pool_all if (st := local_start(r)) is not None and lo <= st < hi]  # type: ignore[operator]
            for target in TARGETS:
                for obj in OBJ:
                    chosen = run_knapsack(pool, obj, target) if pool else None
                    if chosen is None:
                        continue
                    ex = [r["y"] - r["c"] for r in chosen]
                    out.append({
                        "day": day, "kind": kind, "window": label, "target": target, "obj": obj,
                        "n_pool": len(pool), "legs": sorted(r["key"] for r in chosen),
                        "n_legs": len(chosen), "won": float(all(r["y"] == 1.0 for r in chosen)),
                        "ex_mean": float(np.mean(ex)), "ex_sum": float(np.sum(ex)),
                        "pred": float(math.prod(r[obj] for r in chosen)),
                        "pred_B": float(math.prod(r["B"] for r in chosen)),
                        "pred_H1": float(math.prod(r["H1"] for r in chosen)),
                        "supported": bool(chosen[0]["_supported"]),
                        "sports": [r["sport"] for r in chosen],
                        "ex_legs": ex,
                    })
        notes.append(f"{day}: pula 1,10-2,00 {len(pool_all)} nóg (bez godziny startu {no_ko}); knapsack {time.time() - t0:.0f} s")
    return out


def paired(sl: list[dict[str, Any]], kind: str, u: str, v: str) -> list[tuple[str, str, float, dict[str, Any], dict[str, Any]]]:
    idx = {(s["day"], s["window"], s["target"], s["obj"]): s for s in sl if s["kind"] == kind}
    out = []
    for (d, w, t, o), s in idx.items():
        if o != u:
            continue
        other = idx.get((d, w, t, v))
        if other is not None:
            out.append((d, w, t, s, other))
    return out


def boot_units(units: list[str], vals: np.ndarray, reps: int, seed: int) -> tuple[float, float, float]:
    """Mean of vals with a cluster bootstrap over units."""
    ids = sorted(set(units))
    ix = {u: i for i, u in enumerate(ids)}
    g = np.array([ix[u] for u in units])
    s = np.bincount(g, weights=vals, minlength=len(ids))
    n = np.bincount(g, minlength=len(ids)).astype(float)
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(reps):
        w = np.bincount(rng.integers(0, len(ids), len(ids)), minlength=len(ids))
        bs.append((w @ s) / max(w @ n, EPS))
    return float(s.sum() / n.sum()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def slip_tables(sl: list[dict[str, Any]], reps: int, seed: int, lines: list[str], out: dict[str, Any]) -> None:
    kinds = (("block", "okna 3 h rozłączne (10/13/16/19/22) - bootstrap jednostek (dzień, okno); okna nie dzielą meczów", "unit"),
             ("slide", "okna 3 h przesuwne co godzinę 10:00-23:00 - bootstrap DNI (okna się nakładają)", "day"),
             ("day", "cały dzień - bootstrap dni", "day"))
    for kind, title, cl in kinds:
        ks = [s for s in sl if s["kind"] == kind]
        if not ks:
            continue
        lines.append(f"\n### {title}\n")
        lines.append("Kalibracja liczby kuponu: przewidywana szansa celu vs zrealizowana (wszystkie nogi wygrane).\n")
        lines.append("| cel | kurs | kuponów | śr. nóg | przewidywana | zrealizowana [95%] | zreal. − przew. [95%] | śr. (trafienie − 1/k) na nogę [95%] | przewidywana wg b |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        res: dict[str, Any] = {}
        for t in TARGETS:
            for o in OBJ:
                ss = [s for s in ks if s["obj"] == o and s["target"] == t]
                if not ss:
                    continue
                units = [s["day"] if cl == "day" else f"{s['day']}|{s['window']}" for s in ss]
                won = np.array([s["won"] for s in ss])
                pred = np.array([s["pred"] for s in ss])
                exm = np.array([s["ex_mean"] for s in ss])
                w = boot_units(units, won, reps, seed)
                gap = boot_units(units, won - pred, reps, seed)
                e = boot_units(units, exm, reps, seed)
                res[f"{t:g}|{o}"] = {"n": len(ss), "won": w, "pred": float(pred.mean()), "gap": gap, "ex": e}
                lines.append(f"| {o} | {t:g} | {len(ss)} | {np.mean([s['n_legs'] for s in ss]):.2f} | {pred.mean():.3f} | {fmt(w, 3)} | {fmt(gap, 3)} | {fmt(e, 1, 100)} pp | {np.mean([s['pred_B'] for s in ss]):.3f} |")
        lines.append("\nRóżnice sparowane (ten sam dzień, okno, cel). „inne” = odsetek par, w których cel wybrał inny zestaw nóg niż B.\n")
        lines.append("| para | cel | par | inne | Δ zrealizowana (wygrany kupon) [95%] | Δ śr. (trafienie − 1/k) na nogę [95%] | Δ przewidywana wg b |")
        lines.append("|---|---|---|---|---|---|---|")
        for u in ("H1", "H2", "A"):
            for tgt in (*TARGETS, None):
                pr = [p for p in paired(ks, kind, u, "B") if tgt is None or p[2] == tgt]
                if not pr:
                    continue
                units = [d if cl == "day" else f"{d}|{w}" for d, w, _, _, _ in pr]
                dw = np.array([a["won"] - b["won"] for *_, a, b in pr])
                de = np.array([a["ex_mean"] - b["ex_mean"] for *_, a, b in pr])
                dpb = np.array([a["pred_B"] - b["pred_B"] for *_, a, b in pr])
                diff = float(np.mean([a["legs"] != b["legs"] for *_, a, b in pr]))
                bw = boot_units(units, dw, reps, seed)
                be = boot_units(units, de, reps, seed)
                res[f"{u}-B|{tgt}"] = {"n": len(pr), "differ": diff, "won": bw, "ex": be, "sd_won": float(dw.std(ddof=1)) if len(dw) > 1 else None,
                                     "sd_ex": float(de.std(ddof=1)) if len(de) > 1 else None}
                lab = "wszystkie" if tgt is None else f"{tgt:g}"
                lines.append(f"| {u} − B | {lab} | {len(pr)} | {diff:.0%} | {fmt(bw, 3)} | {fmt(be, 1, 100)} pp | {dpb.mean():+.4f} |")
        out[kind] = res


def _delta_won(a: dict[str, Any], b: dict[str, Any]) -> float:
    return float(a["won"] - b["won"])


def _delta_ex_pp(a: dict[str, Any], b: dict[str, Any]) -> float:
    return float(100 * (a["ex_mean"] - b["ex_mean"]))


def slip_lodo(sl: list[dict[str, Any]], lines: list[str], out: dict[str, Any]) -> None:
    lines.append("\n| para | okna | miara | ogółem | per dzień | bez dnia: min..max | znak stały |")
    lines.append("|---|---|---|---|---|---|---|")
    ds = sorted({s["day"] for s in sl})
    for kind in ("block", "slide"):
        for u in ("H1", "H2", "A"):
            pr = paired(sl, kind, u, "B")
            for name, f in (("Δ wygrany", _delta_won), ("Δ (trafienie − 1/k) pp", _delta_ex_pp)):
                vals = [(d, f(a, b)) for d, _, _, a, b in pr]
                tot = float(np.mean([v for _, v in vals]))
                per = [float(np.mean([v for d, v in vals if d == x])) if any(d == x for d, _ in vals) else float("nan") for x in ds]
                wo = [float(np.mean([v for d, v in vals if d != x])) for x in ds]
                same = all(np.sign(w) == np.sign(tot) for w in wo) and tot != 0
                out[f"{kind}|{u}|{name}"] = {"tot": tot, "per": per, "wo": wo}
                lines.append(f"| {u} − B | {kind} | {name} | {tot:+.3f} | {' / '.join(f'{x:+.2f}' for x in per)} | {min(wo):+.3f}..{max(wo):+.3f} | {'tak' if same else 'NIE'} |")
    lines.append(f"\nDni w kolejności: {', '.join(ds)}.")


def slip_sports(sl: list[dict[str, Any]], lines: list[str]) -> None:
    lines.append("| cel | okna | nogi kuponów per sport (n, śr. trafienie − 1/k pp) |")
    lines.append("|---|---|---|")
    for kind in ("block", "slide"):
        for o in OBJ:
            acc: dict[str, list[float]] = defaultdict(list)
            for s in sl:
                if s["kind"] == kind and s["obj"] == o:
                    for sp, e in zip(s["sports"], s["ex_legs"], strict=True):
                        acc[sp].append(e)
            lines.append(f"| {o} | {kind} | " + "; ".join(f"{sp} {len(v)}, {100 * np.mean(v):+.1f}" for sp, v in sorted(acc.items())) + " |")


def needed_n(out: dict[str, Any], lines: list[str]) -> None:
    lines.append("| para | miara | Δ zaobserwowana | SD na jednostkę (dzień, okno, cel) | jednostek, by 95% przedział wykluczył 0 przy tej Δ | ≈ dni (15 jednostek / dzień) | jednostek dla Δ = 2 pp (trafienie − 1/k) / 5 pp (wygrany) |")
    lines.append("|---|---|---|---|---|---|---|")
    blk = out.get("slips", {}).get("block", {})
    for u in ("H1", "H2", "A"):
        e = blk.get(f"{u}-B|None")
        if not e:
            continue
        for name, key, sdk, ref in (("wygrany kupon", "won", "sd_won", 0.05), ("trafienie − 1/k na nogę", "ex", "sd_ex", 0.02)):
            d, sd = e[key][0], e[sdk]
            if sd is None or sd == 0:
                continue
            n_obs = math.inf if d == 0 else (1.96 * sd / abs(d)) ** 2
            n_ref = (1.96 * sd / ref) ** 2
            days_ = n_obs / 15 if math.isfinite(n_obs) else math.inf
            lines.append(f"| {u} − B | {name} | {d:+.4f} | {sd:.3f} | {n_obs:,.0f} | {days_:,.0f} | {n_ref:,.0f} |")


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="first", default="2026-10-13")
    ap.add_argument("--to", dest="last", default="2026-10-19")
    ap.add_argument("--runs", default=str(_ROOT / "runs" / "sofa"))
    ap.add_argument("--db-path", default=str(_ROOT / "data" / "sofa.db"))
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261020)
    ap.add_argument("--history-cache", default=None, help="JSON cache of the graded history (scratch)")
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    runs = Path(args.runs)
    notes: list[str] = []
    prev = (datetime.date.fromisoformat(args.first) - datetime.timedelta(days=1)).isoformat()
    hist = history_rows(runs, HISTORY_FROM, prev, args.db_path, Path(args.history_cache) if args.history_cache else None)
    notes.append(f"historia {HISTORY_FROM}..{prev}: {len(hist)} nóg WIN/LOSS; per sport {dict(Counter(h['sport'] for h in hist))}; per dzień {dict(sorted(Counter(h['day'] for h in hist).items()))}")
    rows: list[dict[str, Any]] = []
    for d in days(args.first, args.last):
        rows += test_rows(runs, d, args.db_path, notes)
    add_calibrated(rows, hist, notes)
    lines: list[str] = ["## Dane i okna treningowe\n"]
    lines += [f"- {n}" for n in notes]
    out: dict[str, Any] = {}
    lines.append("\n## Poziom nogi\n")
    leg_scores(rows, args.reps, args.seed, lines, out, "Wszystkie nogi z b")
    pool = [r for r in rows if sb.MIN_LEG_ODDS <= r["odds"] <= sb.MAX_LEG_ODDS]
    leg_scores(pool, args.reps, args.seed, lines, out, "Nogi kursu 1,10-2,00 (pula buildera)")
    lines.append("\n### Bez jednego dnia (pula buildera)")
    lodo_leg(pool, lines)
    lines.append("\n### Per sport (pula buildera)\n")
    per_sport(pool, args.reps, args.seed, lines, out.setdefault("sport", {}))
    lines.append("\n### Kalibracja (pula buildera)")
    for k in OBJ:
        calibration(pool, k, lines)
    lines.append("\n### Ranking w paśmie ceny (pula buildera)\n")
    ranking(pool, args.reps, args.seed, lines, out.setdefault("ranking", {}))
    lines.append("\n## Poziom kuponu\n")
    sl = slips(rows, notes)
    lines.append("Notatki z budowy: " + "; ".join(n for n in notes if "knapsack" in n))
    sup = Counter((s["obj"], s["supported"]) for s in sl)
    lines.append(f"\nKupony z warstw na plusie (supported) vs z całej puli: {dict(sup)}")
    slip_tables(sl, args.reps, args.seed, lines, out.setdefault("slips", {}))
    lines.append("\n### Bez jednego dnia (kupony)")
    slip_lodo(sl, lines, out.setdefault("slip_lodo", {}))
    lines.append("\n### Nogi wybranych kuponów per sport\n")
    slip_sports(sl, lines)
    lines.append("\n### Ile jednostek trzeba (okna rozłączne, wszystkie cele)\n")
    needed_n(out, lines)
    text = "\n".join(lines) + "\n"
    if args.md_out:
        Path(args.md_out).write_text(text, encoding="utf-8")
    else:
        print(text)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"out": out, "slips": sl}, default=str, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
