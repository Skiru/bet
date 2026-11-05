#!/usr/bin/env python3
"""Are Sofascore's fan votes ("who wins", /event/{id}/votes) a signal beside
Superbet's de-vigged price? (operator 2026-11-05, "Sprawdzić!")

Read-only evidence: writes nothing the pipeline reads. Three steps:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_fan_votes.py population
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_fan_votes.py fetch --max 2000
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_fan_votes.py report

* population - every settled football event whose 1 / X / 2 Superbet priced
  before the start (04_offer `result_1x2` 1 and 2, the draw = `double_chance`
  12's other side) and every tennis match winner (`match_won_for`), outcome
  from 07_settled. One row per event in `<out>/population.jsonl`.
* fetch - `/event/{id}/votes` through the bridge (SofascoreClient: token bucket,
  breaker; MIN_INTERVAL_MS untouched), resumable, at most --max requests a run,
  stops on an open breaker or 3 refusals (403 / 429) in a row. **A past
  event's votes are Sofascore's FINAL tally** (the answer carries no
  timestamp and votes may be cast after the start): every row is stamped
  `asked_after_kickoff` and the report labels the result an UPPER BOUND.
* report - the two frozen rules (FROZEN_RULES below, written before the
  results were looked at), dev / hold-out split by date, match bootstrap,
  Benjamini-Hochberg over the betting cells.

The forward design (votes asked before the start) is in the report, not here.
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import os
import random
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.engine import devig_many  # noqa: E402

OUT = _REPO / "data" / "fan_votes_2026-11-05"
RUNS = _REPO / "runs" / "sofa"

# ---------------------------------------------------------------- frozen rules
# Written down before any vote was fetched (2026-11-05); the report repeats them.
SPLIT_DATE = "2026-10-20"      # dev: event day < SPLIT_DATE; hold-out: >= it
MIN_VOTES = 20                 # an event with fewer total votes is out
THRESHOLDS = (0.05, 0.10, 0.15, 0.20)
DEFAULT_T = 0.10               # used when no dev threshold reaches MIN_DEV_BETS
MIN_DEV_BETS = 50
TAX = 0.88                     # Polish 12% stake tax: return = 0.88 x odds
BOOT = 2000
SEED = 20261105
BH_Q = 0.05
WORKERS = 3                    # parallel asks (the bridge serves ~11 req/s)
TARGET_RPS = 4                 # a share of the bridge, so a live rebuild keeps its pace
FROZEN_RULES = """\
R1 (logistic, per sport x selection: football 1 / X / 2, tennis home):
   M0: y ~ a + b*logit(fair p);  M1: y ~ a + b*logit(fair p) + c*logit(vote share)
   fitted on dev, scored once on hold-out: delta Brier and delta log-loss
   (M1 - M0, summed over an event's selections), match bootstrap 95% CI.
   Signal = M1 better with the CI below 0.
R2 (betting, cells = football 1X2 / DNB / DC, tennis winner x two directions):
   d = fair p - vote share of the selection (DNB on the two-way renormalised
   shares, DC on the summed shares).
   ANTI_CROWD: back every selection with d > t (the crowd under-votes it);
   PRO_CROWD:  back every selection with -d > t (the crowd over-votes it).
   t chosen on dev from {0.05, 0.10, 0.15, 0.20} by ROI after tax among
   thresholds with >= 50 dev bets (else 0.10); hold-out read once with that t.
   Per cell: n, realised - fair p, ROI before and after tax (0.88 x odds - 1;
   a DNB refund = 0), match bootstrap 95% CI, one-sided p (ROI after tax <= 0),
   Benjamini-Hochberg q = 0.05 over the 8 cells.
   Edge verdict only if the hold-out lower bound of ROI after tax is > 0 and
   the cell survives BH.
Events with fewer than 20 total votes are out. Vote share = (votes + 1) /
(total + k), k = 3 (football) / 2 (tennis).
"""


# ------------------------------------------------------------------ population
def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _norm(name: object) -> str:
    return " ".join(str(name or "").casefold().replace("-", " ").split())


def _side_of(subject: str, home: str, away: str) -> str | None:
    s, h, a = _norm(subject), _norm(home), _norm(away)
    if not s:
        return None
    hit_h = s == h or set(s.split()) <= set(h.split())
    hit_a = s == a or set(s.split()) <= set(a.split())
    if hit_h and not hit_a:
        return "H"
    if hit_a and not hit_h:
        return "A"
    return None


def _before(rung: Mapping[str, Any], kickoff: str | None) -> bool:
    at = rung.get("fetched_at_utc")
    if not at or not kickoff:
        return False
    return str(at) < str(kickoff)


def _odds(x: object) -> float | None:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if v > 1.0 else None


def football_event(rungs: Sequence[Mapping[str, Any]], kickoff: str | None
                   ) -> dict[str, float] | None:
    """Pre-start prices of one football event: 1 / X / 2, DNB, DC."""
    pick: dict[tuple[str, str], Mapping[str, Any]] = {}
    for r in rungs:
        if r.get("market") in ("result_1x2", "draw_no_bet", "double_chance") \
                and _before(r, kickoff):
            pick[(str(r["market"]), str(r.get("subject")))] = r
    r1 = pick.get(("result_1x2", "1"))
    r2 = pick.get(("result_1x2", "2"))
    r12 = pick.get(("double_chance", "12"))
    if not (r1 and r2 and r12):
        return None
    o1, o2, ox = _odds(r1.get("over_odds")), _odds(r2.get("over_odds")), \
        _odds(r12.get("under_odds"))
    if not (o1 and o2 and ox):
        return None
    fair = devig_many([1 / o1, 1 / ox, 1 / o2])
    if not fair:
        return None
    out = {"o_H": o1, "o_D": ox, "o_A": o2,
           "p_H": fair[0], "p_D": fair[1], "p_A": fair[2]}
    dnb = pick.get(("draw_no_bet", "1"))
    if dnb and _odds(dnb.get("over_odds")) and _odds(dnb.get("under_odds")):
        out["o_dnb_H"] = float(dnb["over_odds"])
        out["o_dnb_A"] = float(dnb["under_odds"])
    for sub in ("1X", "X2", "12"):
        dc = pick.get(("double_chance", sub))
        if dc and _odds(dc.get("over_odds")):
            out[f"o_dc_{sub}"] = float(dc["over_odds"])
    return out


def tennis_event(rungs: Sequence[Mapping[str, Any]], kickoff: str | None,
                 home: str, away: str) -> tuple[dict[str, float], str] | None:
    """(prices, the side of the rung's subject) of one tennis winner market."""
    for r in rungs:
        if r.get("market") != "match_won_for" or not _before(r, kickoff):
            continue
        side = _side_of(str(r.get("subject") or ""), home, away)
        o_yes, o_no = _odds(r.get("over_odds")), _odds(r.get("under_odds"))
        if side is None or not (o_yes and o_no):
            continue
        fair = devig_many([1 / o_yes, 1 / o_no])
        if not fair:
            continue
        if side == "H":
            return {"o_H": o_yes, "o_A": o_no, "p_H": fair[0], "p_A": fair[1]}, side
        return {"o_H": o_no, "o_A": o_yes, "p_H": fair[1], "p_A": fair[0]}, side
    return None


def outcomes(settled: Iterable[Mapping[str, Any]]) -> dict[tuple[str, int], Any]:
    """{(sport, event id): football 'H' / 'D' / 'A', tennis {subject: won}}."""
    fb: dict[int, dict[str, str]] = defaultdict(dict)
    tn: dict[int, dict[str, bool]] = defaultdict(dict)
    for r in settled:
        if r.get("direction") != "OVER" or r.get("outcome") not in ("WIN", "LOSS"):
            continue
        eid = int(r["sofascore_event_id"])
        if r.get("market") == "result_1x2":
            fb[eid][str(r.get("subject"))] = str(r["outcome"])
        elif r.get("market") == "match_won_for":
            tn[eid][str(r.get("subject"))] = r["outcome"] == "WIN"
    out: dict[tuple[str, int], Any] = {}
    for eid, sub in fb.items():
        if sub.get("1") == "WIN" and sub.get("2") != "WIN":
            out[("football", eid)] = "H"
        elif sub.get("2") == "WIN" and sub.get("1") != "WIN":
            out[("football", eid)] = "A"
        elif sub.get("1") == "LOSS" and sub.get("2") == "LOSS":
            out[("football", eid)] = "D"
    for eid, subs in tn.items():
        out[("tennis", eid)] = subs
    return out


def build_population(runs: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day_dir in sorted(glob.glob(str(runs / "2026-*"))):
        day = os.path.basename(day_dir)
        paths = [os.path.join(day_dir, f) for f in
                 ("04_offer.json", "07_settled.json", "02_fixtures.json")]
        if not all(os.path.exists(p) for p in paths):
            continue
        try:
            offer, settled, fixtures = (_load(p) for p in paths)
        except (OSError, ValueError):
            continue
        res = outcomes(settled)
        fx = {str(f.get("sofascore_event_id")): f for f in fixtures}
        for entry in offer:
            eid_s = str(entry.get("sofascore_event_id"))
            f = fx.get(eid_s)
            if not f or f.get("sport") not in ("football", "tennis"):
                continue
            eid, sport = int(eid_s), str(f["sport"])
            kickoff = entry.get("superbet_kickoff_seen_utc") or f.get("kickoff_utc")
            rungs = entry.get("rungs") or []
            base = {"date": day, "event_id": eid, "sport": sport,
                    "kickoff_utc": kickoff, "home": f.get("home_name"),
                    "away": f.get("away_name")}
            if sport == "football":
                won = res.get(("football", eid))
                prices = football_event(rungs, kickoff)
                if won is None or prices is None:
                    continue
                rows.append({**base, **prices, "outcome": won})
            else:
                subs = res.get(("tennis", eid))
                got = tennis_event(rungs, kickoff, str(f.get("home_name")),
                                   str(f.get("away_name")))
                if not subs or got is None:
                    continue
                prices, _ = got
                side_won = None
                for subject, won_b in subs.items():
                    s = _side_of(subject, str(f.get("home_name")),
                                 str(f.get("away_name")))
                    if s:
                        side_won = s if won_b else ("A" if s == "H" else "H")
                        break
                if side_won is None:
                    continue
                rows.append({**base, **prices, "outcome": side_won})
    return rows


# ------------------------------------------------------------------ fetch
def parse_votes(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"status": "NOT_FOUND"}
    v = payload.get("vote")
    if not isinstance(v, Mapping):
        return {"status": "NO_VOTE"}
    def n(k: str) -> int | None:
        x = v.get(k)
        return int(x) if isinstance(x, int | float) else None
    return {"status": "OK", "vote1": n("vote1"), "voteX": n("voteX"),
            "vote2": n("vote2")}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def fetch(out: Path, max_requests: int) -> int:
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig
    from bet.sofa.errors import CircuitOpenError, SofaError
    from bet.sofa.timeutil import now

    pop = _read_jsonl(out / "population.jsonl")
    votes_path = out / "votes.jsonl"
    done = {int(r["event_id"]) for r in _read_jsonl(votes_path)
            if r.get("status") in ("OK", "NOT_FOUND", "NO_VOTE")}
    todo = [r for r in pop if int(r["event_id"]) not in done]
    # newest days first: the hold-out is filled before the dev window
    todo.sort(key=lambda r: (r["date"], r["event_id"]), reverse=True)
    config = SofaConfig.from_env()
    config = dataclasses.replace(
        config, run_id="measure-fan-votes-" + now().strftime("%Y%m%dT%H%M%SZ"),
        target_rps=min(config.target_rps, TARGET_RPS))
    client = SofascoreClient(config)

    def ask(r: Mapping[str, Any]) -> dict[str, Any]:
        at = now()
        url = f"https://api.sofascore.com/api/v1/event/{r['event_id']}/votes"
        try:
            rec = parse_votes(client._execute(url, stage="MEASURE_FAN_VOTES"))
        except CircuitOpenError:
            rec = {"status": "BREAKER_OPEN"}
        except SofaError as exc:
            rec = {"status": f"FAILED {exc}"}
        stamp = at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        rec.update({"event_id": r["event_id"], "asked_at_utc": stamp,
                    "asked_after_kickoff": bool(r.get("kickoff_utc")
                                                and stamp > str(r["kickoff_utc"]))})
        return rec

    asked = 0
    left_before = len(todo)
    todo = todo[:max_requests]
    with votes_path.open("a", encoding="utf-8") as fh, \
            ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for start in range(0, len(todo), WORKERS):
            recs = list(pool.map(ask, todo[start:start + WORKERS]))
            stop = False
            for rec in recs:
                if rec["status"] == "BREAKER_OPEN":
                    stop = True
                    continue
                asked += 1
                fh.write(json.dumps(rec) + "\n")
            fh.flush()
            refused = sum(1 for rec in recs if rec["status"].startswith("FAILED")
                          and ("403" in rec["status"] or "429" in rec["status"]))
            if stop or refused >= 2:
                print("breaker open / refusals - stop", file=sys.stderr)
                break
            if asked and asked % 300 < WORKERS:
                print(f"{asked} asked", file=sys.stderr)
    print(f"asked {asked}, left {max(0, left_before - asked)}")
    return asked


# ------------------------------------------------------------------ analysis
def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.asarray(np.log(p / (1 - p)))


def fit_logistic(x: np.ndarray, y: np.ndarray, ridge: float = 1e-6,
                 iters: int = 50) -> np.ndarray:
    """Newton-Raphson; x without the intercept column."""
    xx = np.column_stack([np.ones(len(y)), x])
    w = np.zeros(xx.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(xx @ w)))
        g = xx.T @ (y - p) - ridge * w
        h = (xx * (p * (1 - p))[:, None]).T @ xx + ridge * np.eye(len(w))
        step = np.linalg.solve(h, g)
        w = w + step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    return w


def predict(w: np.ndarray, x: np.ndarray) -> np.ndarray:
    xx = np.column_stack([np.ones(len(x)), x])
    return np.asarray(1 / (1 + np.exp(-(xx @ w))))


SELECTIONS = {"football": ("H", "D", "A"), "tennis": ("H",)}


def vote_shares(ev: Mapping[str, Any]) -> dict[str, float] | None:
    v1, v2 = ev.get("vote1") or 0, ev.get("vote2") or 0
    vx = ev.get("voteX") or 0
    if ev["sport"] == "football":
        tot = v1 + vx + v2
        if tot < MIN_VOTES:
            return None
        return {"H": (v1 + 1) / (tot + 3), "D": (vx + 1) / (tot + 3),
                "A": (v2 + 1) / (tot + 3)}
    tot = v1 + v2
    if tot < MIN_VOTES:
        return None
    return {"H": (v1 + 1) / (tot + 2), "A": (v2 + 1) / (tot + 2)}


def joined(pop: Sequence[Mapping[str, Any]], votes: Sequence[Mapping[str, Any]]
           ) -> list[dict[str, Any]]:
    by = {int(v["event_id"]): v for v in votes if v.get("status") == "OK"}
    out = []
    seen: set[int] = set()
    for r in sorted(pop, key=lambda r: (r["date"], r["event_id"])):
        if int(r["event_id"]) in seen:
            continue  # an event on two days' offers counts once, on its first
        seen.add(int(r["event_id"]))
        v = by.get(int(r["event_id"]))
        if not v:
            continue
        ev = {**r, **{k: v.get(k) for k in ("vote1", "voteX", "vote2",
                                             "asked_after_kickoff")}}
        sh = vote_shares(ev)
        if sh is None:
            continue
        ev["share"] = sh
        out.append(ev)
    return out


def r1_scores(dev: Sequence[Mapping[str, Any]], hold: Sequence[Mapping[str, Any]],
              sport: str) -> dict[str, Any]:
    """Per hold-out event: (brier M0, brier M1, logloss M0, logloss M1, brier price)."""
    per_event = np.zeros((len(hold), 5))
    coefs = {}
    for sel in SELECTIONS[sport]:
        def arrays(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, ...]:
            p = np.array([r[f"p_{sel}"] for r in rows])
            s = np.array([r["share"][sel] for r in rows])
            y = np.array([1.0 if r["outcome"] == sel else 0.0 for r in rows])
            return p, s, y
        pd_, sd_, yd = arrays(dev)
        ph, sh, yh = arrays(hold)
        w0 = fit_logistic(logit(pd_)[:, None], yd)
        w1 = fit_logistic(np.column_stack([logit(pd_), logit(sd_)]), yd)
        coefs[sel] = {"M0": [round(float(c), 3) for c in w0],
                      "M1": [round(float(c), 3) for c in w1]}
        q0 = np.clip(predict(w0, logit(ph)[:, None]), 1e-6, 1 - 1e-6)
        q1 = np.clip(predict(w1, np.column_stack([logit(ph), logit(sh)])),
                     1e-6, 1 - 1e-6)
        per_event[:, 0] += (q0 - yh) ** 2
        per_event[:, 1] += (q1 - yh) ** 2
        per_event[:, 2] += -(yh * np.log(q0) + (1 - yh) * np.log(1 - q0))
        per_event[:, 3] += -(yh * np.log(q1) + (1 - yh) * np.log(1 - q1))
        per_event[:, 4] += (ph - yh) ** 2
    rng = np.random.default_rng(SEED)
    n = len(hold)
    db = per_event[:, 1] - per_event[:, 0]
    dl = per_event[:, 3] - per_event[:, 2]
    idx = rng.integers(0, n, size=(BOOT, n))
    bb, bl = db[idx].mean(axis=1), dl[idx].mean(axis=1)
    return {"n_dev": len(dev), "n_hold": n, "coefs": coefs,
            "brier_m0": float(per_event[:, 0].mean()),
            "brier_price": float(per_event[:, 4].mean()),
            "d_brier": float(db.mean()),
            "d_brier_ci": _q95(bb),
            "d_logloss": float(dl.mean()),
            "d_logloss_ci": _q95(bl)}


Bet = tuple[float, float, float, float]


def _q95(xs: np.ndarray) -> list[float]:
    return [float(np.quantile(xs, 0.025)), float(np.quantile(xs, 0.975))]


def candidate_bets(ev: Mapping[str, Any], market: str) -> list[Bet]:
    """(d = fair p - vote share, odds, fair p, result) per priced selection;
    result 1 won / 0 lost / -1 refund."""
    sh, out = ev["share"], ev["outcome"]
    bets: list[tuple[float, float, float, float]] = []
    if market in ("1x2", "winner"):
        for sel in SELECTIONS["football"] if ev["sport"] == "football" else ("H", "A"):
            o = ev.get(f"o_{sel}")
            if o:
                bets.append((ev[f"p_{sel}"] - sh[sel], o, ev[f"p_{sel}"],
                             1.0 if out == sel else 0.0))
    elif market == "dnb":
        for sel in ("H", "A"):
            o = ev.get(f"o_dnb_{sel}")
            if not o:
                continue
            p = ev[f"p_{sel}"] / (ev["p_H"] + ev["p_A"])
            s = sh[sel] / (sh["H"] + sh["A"])
            res = -1.0 if out == "D" else (1.0 if out == sel else 0.0)
            bets.append((p - s, o, p, res))
    elif market == "dc":
        for sub, pair in (("1X", ("H", "D")), ("X2", ("D", "A")), ("12", ("H", "A"))):
            o = ev.get(f"o_dc_{sub}")
            if not o:
                continue
            p = sum(ev[f"p_{k}"] for k in pair)
            s = sum(sh[k] for k in pair)
            bets.append((p - s, o, p, 1.0 if out in pair else 0.0))
    return bets


def _bets(rows: Sequence[Mapping[str, Any]], market: str, direction: str, t: float
          ) -> list[tuple[int, float, float, float]]:
    out = []
    for i, ev in enumerate(rows):
        for d, o, p, res in candidate_bets(ev, market):
            sig = d if direction == "ANTI_CROWD" else -d
            if sig > t:
                out.append((i, o, p, res))
    return out


def _money(bets: Sequence[tuple[int, float, float, float]]) -> dict[str, float]:
    n = len(bets)
    if not n:
        return {"n": 0}
    pre = [(o - 1 if r == 1 else (0.0 if r < 0 else -1.0)) for _, o, _, r in bets]
    post = [(TAX * o - 1 if r == 1 else (0.0 if r < 0 else -1.0))
            for _, o, _, r in bets]
    graded = [(p, r) for _, _, p, r in bets if r >= 0]
    gap = (sum(r for _, r in graded) - sum(p for p, _ in graded)) / len(graded) \
        if graded else 0.0
    return {"n": n, "roi_pre": sum(pre) / n, "roi_post": sum(post) / n,
            "realised_minus_fair": gap}


def r2_cell(dev: Sequence[Mapping[str, Any]], hold: Sequence[Mapping[str, Any]],
            market: str, direction: str) -> dict[str, Any]:
    best_t, best = DEFAULT_T, None
    dev_by_t = {}
    for t in THRESHOLDS:
        m = _money(_bets(dev, market, direction, t))
        dev_by_t[str(t)] = m
        if m["n"] >= MIN_DEV_BETS and (best is None or m["roi_post"] > best):
            best, best_t = m["roi_post"], t
    bets = _bets(hold, market, direction, best_t)
    res: dict[str, Any] = {"market": market, "direction": direction, "t": best_t,
                           "dev": dev_by_t[str(best_t)], "hold": _money(bets)}
    if not bets:
        res["p_one_sided"] = 1.0
        return res
    by_ev: dict[int, list[tuple[int, float, float, float]]] = defaultdict(list)
    for b in bets:
        by_ev[b[0]].append(b)
    keys = list(by_ev)
    rnd = random.Random(SEED)
    roi_post, roi_pre, gaps = [], [], []
    for _ in range(BOOT):
        sample = [b for k in rnd.choices(keys, k=len(keys)) for b in by_ev[k]]
        m = _money(sample)
        roi_post.append(m["roi_post"])
        roi_pre.append(m["roi_pre"])
        gaps.append(m["realised_minus_fair"])
    def ci(xs: list[float]) -> list[float]:
        xs = sorted(xs)
        return [xs[int(0.025 * BOOT)], xs[int(0.975 * BOOT) - 1]]
    res["roi_post_ci"] = ci(roi_post)
    res["roi_pre_ci"] = ci(roi_pre)
    res["gap_ci"] = ci(gaps)
    res["p_one_sided"] = (sum(1 for x in roi_post if x <= 0) + 1) / (BOOT + 1)
    return res


def bh(pvals: Sequence[float], q: float = BH_Q) -> list[bool]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    passed = [False] * m
    k_max = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            k_max = rank
    for rank, i in enumerate(order, start=1):
        passed[i] = rank <= k_max
    return passed


def descriptive(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    tot = [(r.get("vote1") or 0) + (r.get("voteX") or 0) + (r.get("vote2") or 0)
           for r in rows]
    corr = []
    for r in rows:
        corr.append((r["p_H"], r["share"]["H"]))
    a = np.array(corr) if corr else np.zeros((0, 2))
    return {"n": len(rows),
            "votes_median": float(np.median(tot)) if tot else 0.0,
            "votes_p10": float(np.quantile(tot, 0.1)) if tot else 0.0,
            "corr_pH_shareH": (float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
                               if len(a) > 2 else 0.0),
            "mean_share_minus_p_H": (float((a[:, 1] - a[:, 0]).mean())
                                     if len(a) else 0.0)}


def report(out: Path) -> dict[str, Any]:
    pop = _read_jsonl(out / "population.jsonl")
    votes = _read_jsonl(out / "votes.jsonl")
    rows = joined(pop, votes)
    status: dict[str, int] = defaultdict(int)
    for v in votes:
        status[str(v.get("status")).split(" ")[0]] += 1
    result: dict[str, Any] = {
        "population": {s: sum(1 for r in pop if r["sport"] == s) for s in SELECTIONS},
        "asked": len(votes), "status": dict(status),
        "asked_after_kickoff": sum(1 for v in votes if v.get("asked_after_kickoff")),
        "split_date": SPLIT_DATE, "r1": {}, "r2": [], "descriptive": {}}
    for sport in SELECTIONS:
        sr = [r for r in rows if r["sport"] == sport]
        dev = [r for r in sr if r["date"] < SPLIT_DATE]
        hold = [r for r in sr if r["date"] >= SPLIT_DATE]
        result["descriptive"][sport] = {"dev": descriptive(dev),
                                        "hold": descriptive(hold)}
        if len(dev) >= 100 and len(hold) >= 100:
            result["r1"][sport] = r1_scores(dev, hold, sport)
        markets = ("1x2", "dnb", "dc") if sport == "football" else ("winner",)
        for market in markets:
            for direction in ("ANTI_CROWD", "PRO_CROWD"):
                cell = r2_cell(dev, hold, market, direction)
                cell["sport"] = sport
                result["r2"].append(cell)
    passed = bh([c["p_one_sided"] for c in result["r2"]])
    for c, ok in zip(result["r2"], passed, strict=True):
        c["bh_pass"] = ok
        c["edge"] = bool(ok and c.get("roi_post_ci", [-1.0])[0] > 0)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else "")
    ap.add_argument("step", choices=("population", "fetch", "report"))
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--max", type=int, default=2000)
    ap.add_argument("--partial", action="store_true")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.step == "population":
        rows = build_population(args.runs)
        with (args.out / "population.jsonl").open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        by: dict[tuple[str, str], int] = defaultdict(int)
        for r in rows:
            by[(r["sport"], "dev" if r["date"] < SPLIT_DATE else "hold")] += 1
        print(json.dumps({f"{k[0]}:{k[1]}": v for k, v in sorted(by.items())}))
        return 0
    if args.step == "fetch":
        from bet.sofa.timeutil import frozen_clock_refusal
        refusal = frozen_clock_refusal(RUNS)
        if refusal:
            print(refusal, file=sys.stderr)
            return 2
        fetch(args.out, min(args.max, 2000))
        return 0
    asked = {int(v["event_id"]) for v in _read_jsonl(args.out / "votes.jsonl")}
    missing = sum(1 for r in _read_jsonl(args.out / "population.jsonl")
                  if int(r["event_id"]) not in asked)
    if missing and not args.partial:
        # the hold-out is read once: never on a half-fetched population
        print(f"{missing} events not asked yet - fetch first (--partial overrides)",
              file=sys.stderr)
        return 1
    res = report(args.out)
    (args.out / "report.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
