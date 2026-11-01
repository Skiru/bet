"""Read-only replay of build_slip --safest vs default on 11_coupon.json, 10-13..10-31."""
import datetime as dt, json, math, sys
from pathlib import Path
from zoneinfo import ZoneInfo
from bet.sofa import slip_builder as sb, veto
from bet.sofa.coupon_results import key_of

LOCAL = ZoneInfo("Europe/Warsaw")
RUNS = Path("/Users/mkoziol/projects/bet/runs/sofa")
OUT = Path(sys.argv[1])
ARMS = {"A_def_t2": (2.0, False), "B_def_t125": (1.25, False),
        "C_safe_114": (sb.SAFE_TARGET, True), "D_safe_t13": (1.30, True)}
rows = []
for d in range(13, 32):
    D = f"2026-10-{d:02d}"; run = RUNS / D
    coupon = json.loads((run / "11_coupon.json").read_text())
    res = json.loads((run / "13_results.json").read_text())["legs"]
    singles = coupon.get("singles") or []
    reads = veto.load_reads(run / "reads.json"); vetoes = veto.load_vetoes(run / "vetoes.json")
    day = dt.date.fromisoformat(D)
    for arm, (target, safe) in ARMS.items():
        seen = {}
        for h in range(10, 23, 2):
            lo = dt.datetime.combine(day, dt.time(h), LOCAL)
            hi = lo + dt.timedelta(hours=2)
            now = (lo - dt.timedelta(minutes=60)).astimezone(dt.timezone.utc)
            r = sb.build(singles, now, target, slips=3,
                         window=(lo.astimezone(dt.timezone.utc), hi.astimezone(dt.timezone.utc)),
                         reads=reads, vetoes=vetoes, built_at=coupon["created_at_utc"],
                         safe=safe, fresh_prices=None)
            rows.append({"kind": "request", "day": D, "arm": arm, "win": h, "found": len(r.slips),
                         "cands": r.candidates, "not_reached": sum(not s.reached for s in r.slips)})
            for i, s in enumerate(r.slips):
                legs = []
                for x in s.legs:
                    k = key_of(x.leg); g = res.get(k) or {}
                    legs.append({"key": k, "match": x.match_key, "odds": x.odds, "chance": x.chance,
                                 "conf": float(x.leg["confidence"]), "src": x.chance_source,
                                 "status": str(g.get("status") or "unknown"),
                                 "sport": x.leg.get("sport") or "football",
                                 "market": x.leg.get("market"), "dir": x.leg.get("direction"),
                                 "kickoff": x.leg.get("kickoff_utc")})
                ident = tuple(sorted(l["key"] for l in legs))
                if ident in seen:
                    continue
                seen[ident] = 1
                rows.append({"kind": "slip", "day": D, "arm": arm, "win": h, "rank": i,
                             "reached": s.reached, "needs": s.needs_legs, "legs": legs,
                             "chance": s.chance, "prod": s.price_product,
                             "dup_match": len({l["match"] for l in legs}) != len(legs)})
OUT.write_text("\n".join(json.dumps(r) for r in rows))
print(len(rows))
