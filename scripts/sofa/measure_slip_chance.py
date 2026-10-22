#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""Which per-leg probability best predicts a printed leg's result - the
question behind the chat-slip builder's objective (read-only evidence).

`bet.sofa.slip_builder.best_slip` maximises the product of the legs'
`measured_chance`; the optimiser is exact, so the slip is the best only if
that per-leg number is the best estimate. On every settled printed single
(`13_results.json` WIN / LOSS joined to `11_coupon.json` singles and
locked_singles by `coupon_results.key_of`) this compares

  a  confidence (the printed one, 13_results),
  b  slip_builder.measured_chance walk-forward: day d reads only
     runs/sofa/<d>/family_record.json (the 14 days strictly before d) or,
     when missing, the same record recomputed from those days,
  b0 the same without the tier constant (TIER_SHORTFALL, measured on
     10-12..10-19 - in sample for these days): the family / sport shortfall,
  c  1/odds,
  d  1/odds devigged proportionally: (1/odds) / (1 + overround) where the
     leg's group overround is on the leg (one-sided legs have none),

by Brier and log-loss with a match-level bootstrap, calibration bins and
ranking within odds bands. Nothing is written but the --json-out file.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_slip_chance.py \\
        --from 2026-10-13 --to 2026-10-19 [--reps 2000] [--json-out f]
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
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

EST = ("a", "b", "b0", "c", "d")
NAMES = {"a": "pewność (confidence)", "b": "szansa zmierzona (measured_chance)",
         "b0": "szansa zmierzona bez stałej warstwy", "c": "1/kurs",
         "d": "1/kurs bez marży (proporcjonalnie)"}
BANDS = ((1.10, 1.20), (1.20, 1.30), (1.30, 1.45), (1.45, 1.70), (1.70, 2.00))
BINS = (0.0, 0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01)
EPS = 1e-6


def days(a: str, b: str) -> list[str]:
    d, e = datetime.date.fromisoformat(a), datetime.date.fromisoformat(b)
    out = []
    while d <= e:
        out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def record_for(runs: Path, day: str, db: str) -> tuple[dict[str, Any], str]:
    doc = fr.load(runs / day, day)
    if doc is not None:
        return doc, "plik"
    from scripts.sofa.build_family_record import compute
    return compute(str(runs), day, db), "przeliczony"


def rows_of_day(runs: Path, day: str, db: str, notes: list[str]) -> list[dict[str, Any]]:
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
        mc0 = sb.measured_chance(src, odds, fam, sport, sb.TIER_REST)
        ov = leg.get("overround")
        out.append({
            "day": day, "match": f"{day}|{leg.get('group_key') or leg.get('sofascore_event_id')}",
            "sport": str(leg.get("sport") or "football"), "odds": odds,
            "y": 1.0 if e["outcome"] == "WIN" else 0.0, "tier": t,
            "a": conf, "b": None if mc is None else mc[0],
            "b_src": None if mc is None else mc[1],
            "b0": None if mc0 is None else mc0[0], "c": 1.0 / odds,
            "d": None if ov is None else (1.0 / odds) / (1.0 + float(ov)),
        })
    notes.append(f"{day}: rekord rodzin {how} (dni {fr.span(record)}); wyniki {dict(cnt)}")
    return out


class Boot:
    """Match-level bootstrap: per-match sums, resampled matches."""

    def __init__(self, matches: list[str], reps: int, seed: int) -> None:
        self.ids = {m: i for i, m in enumerate(sorted(set(matches)))}
        self.idx = np.array([self.ids[m] for m in matches])
        rng = np.random.default_rng(seed)
        k = len(self.ids)
        self.w = np.stack([np.bincount(rng.integers(0, k, k), minlength=k)
                           for _ in range(reps)]).astype(float)  # reps x matches

    def sums(self, v: np.ndarray) -> np.ndarray:
        return np.bincount(self.idx, weights=v, minlength=len(self.ids))

    def ratio(self, num: np.ndarray, den: np.ndarray) -> tuple[float, float, float]:
        sn, sd = self.sums(num), self.sums(den)
        point = sn.sum() / sd.sum()
        bs = (self.w @ sn) / np.maximum(self.w @ sd, EPS)
        return float(point), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    out: np.ndarray = (p - y) ** 2
    return out


def logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    q = np.clip(p, EPS, 1 - EPS)
    out: np.ndarray = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    return out


def arr(rows: list[dict[str, Any]], k: str) -> np.ndarray:
    return np.array([float(r[k]) for r in rows])


def fmt(t: tuple[float, float, float], nd: int = 4, scale: float = 1.0) -> str:
    return f"{t[0] * scale:.{nd}f} [{t[1] * scale:.{nd}f}; {t[2] * scale:.{nd}f}]"


def auc(score: np.ndarray, y: np.ndarray) -> float:
    pos = y == 1
    n1, n0 = int(pos.sum()), int((~pos).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    _, inv, counts = np.unique(score, return_inverse=True, return_counts=True)
    upper = np.cumsum(counts)
    avg = upper - (counts - 1) / 2.0  # average rank of each distinct value
    ranks = avg[inv]
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def auc_boot(rows: list[dict[str, Any]], k: str, reps: int, seed: int) -> tuple[float, float, float]:
    score, y = arr(rows, k), arr(rows, "y")
    point = auc(score, y)
    matches = sorted({r["match"] for r in rows})
    pos = defaultdict(list)
    for i, r in enumerate(rows):
        pos[r["match"]].append(i)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(reps):
        pick = rng.integers(0, len(matches), len(matches))
        ix = np.concatenate([pos[matches[j]] for j in pick])
        vals.append(auc(score[ix], y[ix]))
    v = np.array(vals)
    v = v[~np.isnan(v)]
    return point, float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def scores_block(rows: list[dict[str, Any]], ests: tuple[str, ...], reps: int, seed: int,
                 lines: list[str], title: str, out: dict[str, Any]) -> None:
    y = arr(rows, "y")
    boot = Boot([r["match"] for r in rows], reps, seed)
    one = np.ones(len(rows))
    n_m = len({r["match"] for r in rows})
    lines.append(f"\n**{title}** - {len(rows)} nóg, {n_m} meczów, trafienie {y.mean():.3f}\n")
    lines.append("| estymator | średnia p | Brier [95%] | log-loss [95%] |")
    lines.append("|---|---|---|---|")
    res: dict[str, Any] = {}
    for k in ests:
        p = arr(rows, k)
        b, ll = boot.ratio(brier(p, y), one), boot.ratio(logloss(p, y), one)
        res[k] = {"brier": b, "logloss": ll, "mean_p": float(p.mean())}
        lines.append(f"| {k}: {NAMES[k]} | {p.mean():.3f} | {fmt(b)} | {fmt(ll)} |")
    lines.append("\nRóżnice sparowane (ujemna = pierwszy lepszy), te same losowania meczów:\n")
    lines.append("| para | Δ Brier ×1000 [95%] | Δ log-loss ×1000 [95%] |")
    lines.append("|---|---|---|")
    pairs = [(u, v) for u, v in (("b", "a"), ("b", "c"), ("a", "c"), ("b0", "a"), ("b", "b0"), ("d", "c"), ("a", "d"), ("b", "d")) if u in ests and v in ests]
    for u, v in pairs:
        pu, pv = arr(rows, u), arr(rows, v)
        db_ = boot.ratio(brier(pu, y) - brier(pv, y), one)
        dl = boot.ratio(logloss(pu, y) - logloss(pv, y), one)
        res[f"{u}-{v}"] = {"brier": db_, "logloss": dl}
        lines.append(f"| {u} − {v} | {fmt(db_, 2, 1000)} | {fmt(dl, 2, 1000)} |")
    out[title] = res


def lodo(rows: list[dict[str, Any]], pairs: list[tuple[str, str]], lines: list[str]) -> None:
    ds = sorted({r["day"] for r in rows})
    lines.append("\n| para | Δ Brier ×1000 ogółem | per dzień (Δ Brier ×1000) | bez dnia: min..max | znak stały bez każdego dnia |")
    lines.append("|---|---|---|---|---|")
    for u, v in pairs:
        def d(rs: list[dict[str, Any]]) -> float:
            y = arr(rs, "y")
            return float(np.mean(brier(arr(rs, u), y) - brier(arr(rs, v), y))) * 1000
        tot = d(rows)
        per = [d([r for r in rows if r["day"] == x]) for x in ds]
        wo = [d([r for r in rows if r["day"] != x]) for x in ds]
        same = all(np.sign(w) == np.sign(tot) for w in wo)
        lines.append(f"| {u} − {v} | {tot:+.2f} | {' / '.join(f'{x:+.1f}' for x in per)} | {min(wo):+.2f}..{max(wo):+.2f} | {'tak' if same else 'NIE'} |")
    lines.append(f"\nDni w kolejności: {', '.join(ds)}.")


def calibration(rows: list[dict[str, Any]], k: str, lines: list[str]) -> None:
    lines.append(f"\n**{k}: {NAMES[k]}**\n")
    lines.append("| przedział p | N | średnia p | trafienie | trafienie − p |")
    lines.append("|---|---|---|---|---|")
    for lo, hi in zip(BINS, BINS[1:], strict=False):
        sel = [r for r in rows if lo <= r[k] < hi]
        if not sel:
            continue
        mp = float(np.mean([r[k] for r in sel]))
        hr = float(np.mean([r["y"] for r in sel]))
        lab = f"{lo:.2f}-{hi:.2f}" if hi <= 1 else f"{lo:.2f}+"
        lines.append(f"| {lab} | {len(sel)} | {mp:.3f} | {hr:.3f} | {hr - mp:+.3f} |")


def ranking(rows: list[dict[str, Any]], reps: int, seed: int, lines: list[str], out: dict[str, Any]) -> None:
    lines.append("| pasmo kursu | N | mecze | est. | mediana p−1/k | górna połowa: trafienie − 1/k | dolna połowa: trafienie − 1/k | górna − dolna (trafienie − 1/k) [95%] | AUC est. [95%] | AUC 1/k |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for lo, hi in BANDS:
        band = [r for r in rows if lo <= r["odds"] < hi or (hi == 2.00 and r["odds"] == 2.00)]
        if len(band) < 40:
            lines.append(f"| {lo:.2f}-{hi:.2f} | {len(band)} | - | - | za mało nóg (< 40) | | | | | |")
            continue
        nm = len({r["match"] for r in band})
        boot = Boot([r["match"] for r in band], reps, seed)
        y, c = arr(band, "y"), arr(band, "c")
        auc_c = auc(c, y)
        for k in ("a", "b"):
            g = arr(band, k) - c
            med = float(np.median(g))
            top = g > med
            if top.sum() == 0 or (~top).sum() == 0:
                top = g >= med
            bot = ~top
            # top minus bottom hit rate on the same draws
            ex = y - c  # hit minus 1/odds: the price inside the band held out
            st, sbm = boot.sums(ex * top), boot.sums(ex * bot)
            nt, nb = boot.sums(top.astype(float)), boot.sums(bot.astype(float))
            point = st.sum() / nt.sum() - sbm.sum() / nb.sum()
            bs = (boot.w @ st) / np.maximum(boot.w @ nt, EPS) - (boot.w @ sbm) / np.maximum(boot.w @ nb, EPS)
            diff = (point, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))
            e_t = float(y[top].mean() - c[top].mean())
            e_b = float(y[bot].mean() - c[bot].mean())
            au = auc_boot(band, k, min(reps, 1000), seed)
            out[f"{lo:.2f}-{hi:.2f}|{k}"] = {"n": len(band), "diff": diff, "auc": au, "auc_c": auc_c,
                                             "top_n": int(top.sum()), "bot_n": int(bot.sum())}
            lines.append(f"| {lo:.2f}-{hi:.2f} | {len(band)} | {nm} | {k} | {med:+.3f} | {e_t:+.3f} (n {int(top.sum())}) | {e_b:+.3f} (n {int(bot.sum())}) | {fmt(diff, 1, 100)} pp | {fmt(au, 3)} | {auc_c:.3f} |")


def per_sport(rows: list[dict[str, Any]], reps: int, seed: int, lines: list[str], out: dict[str, Any]) -> None:
    lines.append("| sport | N | mecze | trafienie | Brier a | Brier b | Brier c | Δ b−a ×1000 [95%] | Δ b−c ×1000 [95%] | Δ a−c ×1000 [95%] | log-loss a | log-loss b | log-loss c |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in sorted({r["sport"] for r in rows}):
        rs = [r for r in rows if r["sport"] == s]
        y = arr(rs, "y")
        one = np.ones(len(rs))
        boot = Boot([r["match"] for r in rs], reps, seed)
        p = {k: arr(rs, k) for k in ("a", "b", "c")}
        br = {k: float(np.mean(brier(p[k], y))) for k in p}
        ll = {k: float(np.mean(logloss(p[k], y))) for k in p}
        dd = {f"{u}-{v}": boot.ratio(brier(p[u], y) - brier(p[v], y), one) for u, v in (("b", "a"), ("b", "c"), ("a", "c"))}
        out[s] = {"n": len(rs), "brier": br, "logloss": ll, "diff": dd}
        lines.append(f"| {s} | {len(rs)} | {len({r['match'] for r in rs})} | {y.mean():.3f} | {br['a']:.4f} | {br['b']:.4f} | {br['c']:.4f} | {fmt(dd['b-a'], 2, 1000)} | {fmt(dd['b-c'], 2, 1000)} | {fmt(dd['a-c'], 2, 1000)} | {ll['a']:.4f} | {ll['b']:.4f} | {ll['c']:.4f} |")


def section(rows: list[dict[str, Any]], title: str, reps: int, seed: int, lines: list[str], out: dict[str, Any]) -> None:
    lines.append(f"\n## {title}\n")
    by_sport = Counter(r["sport"] for r in rows)
    m_sport = {s: len({r['match'] for r in rows if r['sport'] == s}) for s in by_sport}
    lines.append("Nogi / mecze per sport: " + ", ".join(f"{s} {by_sport[s]} / {m_sport[s]}" for s in sorted(by_sport)))
    lines.append("Nogi per dzień: " + ", ".join(f"{d} {n}" for d, n in sorted(Counter(r['day'] for r in rows).items())))
    lines.append("\n### Brier i log-loss, wszystkie nogi (a, b, b0, c)")
    scores_block(rows, ("a", "b", "b0", "c"), reps, seed, lines, f"{title}: a/b/b0/c", out)
    dr = [r for r in rows if r["d"] is not None]
    lines.append(f"\n### Z ceną bez marży (d) - tylko nogi z marżą grupy ({len(dr)} z {len(rows)})")
    scores_block(dr, EST, reps, seed, lines, f"{title}: z d", out)
    lines.append("\n### Per sport (a, b, c)\n")
    per_sport(rows, reps, seed, lines, out.setdefault(f"{title}: sport", {}))
    lines.append("\n### Bez jednego dnia (znak różnicy Brier)")
    lodo(rows, [("b", "a"), ("b", "c"), ("a", "c"), ("b", "b0")], lines)
    lines.append("\n### Kalibracja")
    for k in ("a", "b"):
        calibration(rows, k, lines)
    lines.append("\n### Ranking w paśmie ceny\n")
    lines.append("Pasmo dzielone na medianie (p − 1/kurs); 'trafienie − 1/k' to trafienie minus średnie 1/kurs w połowie (cena kontrolowana); różnica górna − dolna w punktach procentowych (trafienie − 1/kurs), bootstrap meczów; AUC estymatora w paśmie vs AUC samego 1/kurs.\n")
    ranking(rows, reps, seed, lines, out.setdefault(f"{title}: ranking", {}))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="first", default="2026-10-13")
    ap.add_argument("--to", dest="last", default="2026-10-19")
    ap.add_argument("--runs", default=str(_ROOT / "runs" / "sofa"))
    ap.add_argument("--db-path", default=str(_ROOT / "data" / "sofa.db"))
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261020)
    ap.add_argument("--md-out")
    ap.add_argument("--json-out")
    a = ap.parse_args()
    runs = Path(a.runs)
    notes: list[str] = []
    rows: list[dict[str, Any]] = []
    for d in days(a.first, a.last):
        rows += rows_of_day(runs, d, a.db_path, notes)
    missing_b = sum(r["b"] is None for r in rows)
    srcs = Counter(r["b_src"] for r in rows)
    tiers = Counter(r["tier"] for r in rows)
    full = [r for r in rows if r["b"] is not None and r["b0"] is not None]
    lines = ["# measure_slip_chance", "", *[f"- {n}" for n in notes],
             f"- nogi WIN/LOSS: {len(rows)}; bez szansy zmierzonej (brak rodziny i sportu w rekordzie): {missing_b} - pominięte",
             f"- źródło b: {dict(srcs)}; warstwy: {dict(tiers)}"]
    out: dict[str, Any] = {}
    section(full, "Wszystkie nogi", a.reps, a.seed, lines, out)
    sub = [r for r in full if sb.MIN_LEG_ODDS <= r["odds"] <= sb.MAX_LEG_ODDS]
    section(sub, "Nogi, które builder może wziąć (kurs 1.10-2.00)", a.reps, a.seed, lines, out)
    text = "\n".join(lines) + "\n"
    if a.md_out:
        Path(a.md_out).write_text(text, encoding="utf-8")
    else:
        print(text)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
