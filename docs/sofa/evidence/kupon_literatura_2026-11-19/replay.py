"""Read-only replay of slip_builder.build over settled days: OLD vs literature arms.

arms:
  OLD      current: chance = min(conf, 1/odds); max chance at price product >= target
  FAIR     chance = min(conf, fair p): market_p (power de-vig, Clarke 2017 / Strumbelj 2014)
           for a two-sided leg, (1/odds) x ONE_SIDED for a one-sided leg (no margin known)
  FAIR_EV  FAIR, and the search maximises expected return sum log(chance x odds)
           (Kelly / EV objective) instead of chance
usage: replay.py <dev|hold> <out.jsonl>
"""
import datetime as dt, json, math, sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).parent))
from legs import RUNS, DEV_TO, days
from bet.sofa import slip_builder as sb, veto
from bet.sofa.coupon_results import key_of

LOCAL = ZoneInfo("Europe/Warsaw")
ONE_SIDED = 0.9465  # dev 10-13..11-04: one-sided legs 1.10-2.00 realised / price (dev_legs.out)
REQUESTS = [(1.5, 2), (2.0, 2), (3.0, 3), (4.4, 7)]
_orig_chance, _orig_score = sb.measured_chance, sb._search_score


def fair_chance(leg, odds):
    conf = float(leg["confidence"])
    mp, base = leg.get("market_p"), leg.get("offered_odds")
    if mp is not None and base:
        fair = (1.0 / odds) * float(mp) * float(base)
    else:
        fair = ONE_SIDED / odds
    if conf <= fair:
        return max(min(conf, 0.999), 1e-6), "pewność"
    return max(min(fair, 0.999), 1e-6), "cena bez marży"


def ev_score(x):
    return _orig_score(x) + math.log(x.odds)


def set_arm(arm):
    sb.measured_chance = _orig_chance if arm == "OLD" else fair_chance
    sb._search_score = ev_score if arm == "FAIR_EV" else _orig_score


split, out = sys.argv[1], Path(sys.argv[2])
ONLY = sys.argv[3] if len(sys.argv) > 3 else None
if len(sys.argv) > 4:
    REQUESTS = [tuple(float(v) if i == 0 else int(v) for i, v in enumerate(q.split(":"))) for q in sys.argv[4].split(",")]
rows = []
for D in days():
    if (split == "dev") != (D <= DEV_TO):
        continue
    if ONLY and D != ONLY:
        continue
    run = RUNS / D
    coupon = json.loads((run / "11_coupon.json").read_text())
    res = json.loads((run / "13_results.json").read_text())["legs"]
    singles = coupon.get("singles") or []
    reads = veto.load_reads(run / "reads.json") if (run / "reads.json").exists() else []
    vetoes = veto.load_vetoes(run / "vetoes.json") if (run / "vetoes.json").exists() else []
    day = dt.date.fromisoformat(D)
    for arm in ("OLD", "FAIR", "FAIR_EV"):
        set_arm(arm)
        for target, max_legs in REQUESTS:
            for h in range(10, 23, 2):
                lo = dt.datetime.combine(day, dt.time(h), LOCAL)
                hi = lo + dt.timedelta(hours=4)
                now = (lo - dt.timedelta(minutes=60)).astimezone(dt.timezone.utc)
                r = sb.build(singles, now, target, slips=3, max_legs=max_legs,
                             window=(lo.astimezone(dt.timezone.utc), hi.astimezone(dt.timezone.utc)),
                             reads=reads, vetoes=vetoes, built_at=coupon.get("created_at_utc"),
                             fresh_prices=None)
                for i, s in enumerate(r.slips):
                    legs = []
                    for x in s.legs:
                        g = res.get(key_of(x.leg)) or {}
                        legs.append({"key": key_of(x.leg), "odds": x.odds, "chance": x.chance,
                                     "mp": x.leg.get("market_p"), "ov": x.leg.get("overround"),
                                     "status": str(g.get("status") or "unknown")})
                    rows.append({"day": D, "arm": arm, "target": target, "max_legs": max_legs,
                                 "win": h, "rank": i, "reached": s.reached, "legs": legs,
                                 "prod": s.price_product, "chance": s.chance})
    print(D, len(rows), flush=True)
set_arm("OLD")
out.write_text("\n".join(json.dumps(r) for r in rows))
