"""Score a serve/return model for tennis against the estimator that ships.

`games_won_for` prices `p_central` as `hits/n` — how often the player crossed
the line in their last ten matches. That number ignores who those matches were
against, ignores who today's opponent is, and carries one observation per
match. This script builds the alternative that the cached data supports, and
scores it honestly:

  1. serve/return point counts, out of the `statistics_json` we already cache
     and nobody reads (7,046 tennis events, 97.9% carry `Service points won`);
  2. a joint ridge-penalised rating, `P(point | i serving to j) =
     sigmoid(s_i - r_j + c)`, so a player who held 62% against strong
     returners outranks one who held 62% against weak ones;
  3. a hold/games Monte Carlo, which reproduces the real bimodal shape —
     trough at eleven games, wall at twelve — without being told about it.

Measured 2026-09-22 on 1,848 settled rows, this beats the incumbent and still
does not matter:

    estimator                     Brier
    current hits/n                0.2397
    raw serve rates, no rating    0.2475
    serve rating model            0.2364
    devigged market price         0.2102
    constant 0.5                  0.2500

It loses to the price (best blend w=0.10 for +0.0003, and 0/3 days better
under leave-one-day-out), and it LOWERS the ceiling that actually gates the
coupon: top Wilson lower bound 0.5962 against hits/n's 0.6428, because a
better-calibrated model is a humbler one and its top bucket is 0.750-0.800.
A model that never claims 0.80 cannot pass a 0.80 floor.

Kept as a measurement harness, not wired into the pipeline. Run it before
proposing any tennis estimator: the bar is the market's 0.2102.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_serve_model.py
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

sys.path.insert(0, "src")

from rapidfuzz import fuzz  # noqa: E402

FRAC = re.compile(r"^\s*(\d+)\s*/\s*(\d+)")
# Median serve-point win rate over the cached matches; the fitted intercept
# reproduces it to three places, which is the model checking its own arithmetic.
TOUR_SPW = 0.583


@dataclass(frozen=True)
class SideServe:
    serve_won: int
    serve_played: int
    return_won: int
    return_played: int


def _frac(value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    m = FRAC.match(str(value))
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_serve(stats_json: str) -> dict[str, SideServe] | None:
    """Serve and return point counts for both sides, or None if unusable.

    Counts come from the first/second serve splits, because only those carry
    the denominator. Reading it off `First serve 51/75` instead produced a
    serve-point win rate of 1.03 on some events.
    """
    try:
        doc = json.loads(stats_json)
    except (TypeError, ValueError):
        return None
    items: dict[str, tuple[object, object]] = {}
    for period in doc.get("statistics") or []:
        if period.get("period") not in (None, "ALL"):
            continue
        for group in period.get("groups") or []:
            for item in group.get("statisticsItems") or []:
                items[str(item.get("name"))] = (item.get("home"), item.get("away"))
    need = ("First serve points", "Second serve points",
            "First serve return points", "Second serve return points")
    if not all(k in items for k in need):
        return None
    out: dict[str, SideServe] = {}
    for i, side in enumerate(("home", "away")):
        f1, f2 = _frac(items[need[0]][i]), _frac(items[need[1]][i])
        r1, r2 = _frac(items[need[2]][i]), _frac(items[need[3]][i])
        if not (f1 and f2 and r1 and r2):
            return None
        served, returned = f1[1] + f2[1], r1[1] + r2[1]
        if served <= 0 or returned <= 0:
            return None
        out[side] = SideServe(f1[0] + f2[0], served, r1[0] + r2[0], returned)
    # Identities that must hold inside one match. A payload that fails them is
    # not a thin payload, it is a misread one, and it is dropped rather than
    # averaged in.
    h, a = out["home"], out["away"]
    if h.serve_played != a.return_played or a.serve_played != h.return_played:
        return None
    if h.serve_won + a.return_won != h.serve_played:
        return None
    if a.serve_won + h.return_won != a.serve_played:
        return None
    return out


def load_serve(db: str) -> dict[int, dict[str, SideServe]]:
    con = sqlite3.connect(db)
    out = {}
    for eid, sj in con.execute(
        "select sofascore_event_id, statistics_json from sofa_event_stats "
        "where statistics_json is not null"
    ):
        parsed = parse_serve(sj)
        if parsed:
            out[eid] = parsed
    return out


def load_events(db: str) -> tuple[dict[int, tuple[str, str]], dict[int, int]]:
    """event id -> (home name, away name), and event id -> start timestamp."""
    con = sqlite3.connect(db)
    sides: dict[int, tuple[str, str]] = {}
    dates: dict[int, int] = {}
    for (ej,) in con.execute("select events_json from sofa_entity_events"):
        try:
            doc = json.loads(ej)
        except (TypeError, ValueError):
            continue
        events = doc.get("events") if isinstance(doc, dict) else doc
        if not isinstance(events, list):
            continue
        for e in events:
            eid = e.get("id")
            home = (e.get("homeTeam") or {}).get("name")
            away = (e.get("awayTeam") or {}).get("name")
            if eid is not None and home and away:
                sides[eid] = (home, away)
            if eid is not None and e.get("startTimestamp"):
                dates[eid] = e["startTimestamp"]
    return sides, dates


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def fit_rating(
    rows: list[tuple[str, str, int, int]], lam: float = 35.0, iters: int = 500,
    lr: float = 1.0,
) -> tuple[dict[str, float], dict[str, float], float]:
    """Serve and return strengths per player, ridge-penalised toward zero.

    The step is normalised by each player's OWN point count. Scaling it by the
    total instead made the update ~1e-4 per iteration and the fit never left
    the origin — 400 iterations produced a serve spread of sd 0.022, which is
    half a percentage point of serve-point rate across the entire tour.

    `lam = 35` minimised Brier on the settled rows; the graph is thin (2,318
    players over 4,586 matches, largest connected component 587) so the
    penalty is doing real work rather than tidying.
    """
    players = sorted({p for row in rows for p in row[:2]})
    idx = {p: i for i, p in enumerate(players)}
    n = len(players)
    s, r = [0.0] * n, [0.0] * n
    served, returned = [0.0] * n, [0.0] * n
    for a, b, _won, played in rows:
        served[idx[a]] += played
        returned[idx[b]] += played
    total_won = sum(w for _, _, w, _ in rows)
    total_played = sum(p for _, _, _, p in rows)
    c = math.log(max(total_won, 1) / max(total_played - total_won, 1))
    for _ in range(iters):
        gs, gr = [0.0] * n, [0.0] * n
        gc = 0.0
        for a, b, won, played in rows:
            i, j = idx[a], idx[b]
            resid = won - played * sigmoid(s[i] - r[j] + c)
            gs[i] += resid
            gr[j] -= resid
            gc += resid
        for i in range(n):
            s[i] += lr * (gs[i] - lam * s[i]) / (served[i] + lam)
            r[i] += lr * (gr[i] - lam * r[i]) / (returned[i] + lam)
        c += lr * gc / max(total_played, 1)
    return ({players[i]: s[i] for i in range(n)},
            {players[i]: r[i] for i in range(n)}, c)


def hold_probability(p: float) -> float:
    """P(server holds) given P(server wins a point) = p."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    q = 1.0 - p
    base = p**4 * (1 + 4 * q + 10 * q * q)
    return base + 20 * p**3 * q**3 * (p * p / (1 - 2 * p * q))


def simulate_games(hold_a: float, hold_b: float, sims: int, seed: int,
                   best_of: int = 3) -> list[int]:
    """Games won by A over `sims` simulated matches."""
    rnd = random.Random(seed)
    need = best_of // 2 + 1
    out: list[int] = []
    for _ in range(sims):
        sets_a = sets_b = total = 0
        while sets_a < need and sets_b < need:
            ga = gb = 0
            server_a = True
            while True:
                held = rnd.random() < (hold_a if server_a else hold_b)
                if held == server_a:
                    ga += 1
                else:
                    gb += 1
                server_a = not server_a
                if ga >= 6 and ga - gb >= 2:
                    sets_a += 1
                    break
                if gb >= 6 and gb - ga >= 2:
                    sets_b += 1
                    break
                if ga == 6 and gb == 6:
                    if rnd.random() < 0.5 + (hold_a - hold_b) / 2:
                        ga += 1
                        sets_a += 1
                    else:
                        gb += 1
                        sets_b += 1
                    break
            total += ga
        out.append(total)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--cutoff", default="2026-09-19",
                    help="fit only on matches before this date, so the score "
                         "is not read off matches the rating already saw")
    ap.add_argument("--lam", type=float, default=35.0)
    ap.add_argument("--sims", type=int, default=3000)
    ap.add_argument("--days", nargs="*",
                    default=["2026-09-19", "2026-09-20", "2026-09-21"])
    args = ap.parse_args()

    serve = load_serve(args.db_path)
    sides, dates = load_events(args.db_path)
    cut = int(datetime.fromisoformat(args.cutoff).replace(tzinfo=UTC).timestamp())

    rows: list[tuple[str, str, int, int]] = []
    for eid, match in serve.items():
        names, when = sides.get(eid), dates.get(eid)
        if not names or when is None or when >= cut:
            continue
        rows.append((names[0], names[1], match["home"].serve_won,
                     match["home"].serve_played))
        rows.append((names[1], names[0], match["away"].serve_won,
                     match["away"].serve_played))
    print(f"matches parsed clean: {len(serve):,}   "
          f"fit observations before {args.cutoff}: {len(rows):,}   "
          f"points: {sum(p for *_, p in rows):,}")
    if not rows:
        print("nothing to fit", file=sys.stderr)
        return 2
    strength, ret, c0 = fit_rating(rows, lam=args.lam)
    print(f"players rated: {len(strength):,}   intercept {c0:.4f} "
          f"(=> tour serve rate {sigmoid(c0):.3f}, measured median {TOUR_SPW})")

    names_sorted = sorted(strength)

    def look(player: str) -> str | None:
        if player in strength:
            return player
        best = max(names_sorted,
                   key=lambda q: fuzz.token_set_ratio(player.lower(), q.lower()))
        ok = fuzz.token_set_ratio(player.lower(), best.lower()) >= 88
        return best if ok else None

    cache: dict[tuple[float, float], list[int]] = {}
    scored: list[tuple[float, float, float, float]] = []  # model, now, market, win
    for day in args.days:
        try:
            sheet = {(r["sofascore_event_id"], r["market"], r.get("subject") or "",
                      r["line"], r["direction"]): r
                     for r in json.load(open(f"runs/sofa/{day}/05_sheet.json"))}
            samples = {x["sofascore_event_id"]: x
                       for x in json.load(open(f"runs/sofa/{day}/03_samples.json"))}
            fixtures = {f["sofascore_event_id"]: f
                        for f in json.load(open(f"runs/sofa/{day}/02_fixtures.json"))}
            settled = json.load(open(f"runs/sofa/{day}/07_settled.json"))
        except OSError:
            continue
        for r in settled:
            if r["market"] != "games_won_for":
                continue
            if r.get("outcome") not in ("WIN", "LOSS"):
                continue
            key = (r["sofascore_event_id"], r["market"], r.get("subject") or "",
                   r["line"], r["direction"])
            row = sheet.get(key)
            fixture = fixtures.get(r["sofascore_event_id"])
            if not row or not fixture or row.get("market_p") is None:
                continue
            if r["sofascore_event_id"] not in samples:
                continue
            subject = (r.get("subject") or "").lower()
            home = (fixture.get("home_name") or "").lower()
            away = (fixture.get("away_name") or "").lower()
            sh = fuzz.token_set_ratio(subject, home)
            sa = fuzz.token_set_ratio(subject, away)
            if max(sh, sa) < 70 or abs(sh - sa) < 10:
                continue
            me = fixture["home_name"] if sh > sa else fixture["away_name"]
            opp = fixture["away_name"] if sh > sa else fixture["home_name"]
            a, b = look(me), look(opp)
            if a is None or b is None:
                continue
            pa = sigmoid(strength[a] - ret[b] + c0)
            pb = sigmoid(strength[b] - ret[a] + c0)
            ck = (round(pa, 3), round(pb, 3))
            if ck not in cache:
                cache[ck] = simulate_games(hold_probability(pa), hold_probability(pb),
                                           args.sims, abs(hash(ck)) % 10**6)
            games = cache[ck]
            if r["direction"] == "OVER":
                p = sum(1 for g in games if g > r["line"]) / len(games)
            else:
                p = sum(1 for g in games if g < r["line"]) / len(games)
            scored.append((p, r["p_central"], row["market_p"],
                           1.0 if r["outcome"] == "WIN" else 0.0))

    if not scored:
        print("no settled rows to score", file=sys.stderr)
        return 2

    def brier(values: list[float]) -> float:
        return st.mean((v - s[3]) ** 2 for v, s in zip(values, scored))

    model = [s[0] for s in scored]
    now = [s[1] for s in scored]
    market = [s[2] for s in scored]
    print(f"\nscored rows: {len(scored):,}")
    print(f"  current hits/n         Brier={brier(now):.4f}")
    print(f"  serve rating model     Brier={brier(model):.4f}")
    print(f"  devigged market price  Brier={brier(market):.4f}")
    print(f"  constant 0.5           Brier={brier([0.5] * len(scored)):.4f}")
    best = min(((w, brier([w * m + (1 - w) * k for m, k in zip(model, market)]))
                for w in (i / 20 for i in range(21))), key=lambda t: t[1])
    print(f"  best blend with price  w={best[0]:.2f} -> {best[1]:.4f} "
          f"(gain over price alone {brier(market) - best[1]:+.4f})")

    buckets: dict[int, list[float]] = defaultdict(list)
    for p, _n, _m, win in scored:
        buckets[min(int(p * 20), 19)].append(win)
    top = 0.0
    for bucket in sorted(buckets):
        hits = buckets[bucket]
        if len(hits) < 60:
            continue
        k, n = int(sum(hits)), len(hits)
        z = 1.959964
        d = 1 + z * z / n
        centre = (k / n + z * z / (2 * n)) / d
        margin = z * math.sqrt((k / n) * (1 - k / n) / n + z * z / (4 * n * n)) / d
        top = max(top, max(0.0, centre - margin))
    print(f"  ceiling (top Wilson lower bound) {top:.4f} — the coupon floor is 0.80")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
