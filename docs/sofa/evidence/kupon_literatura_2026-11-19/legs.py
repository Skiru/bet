"""Load every coupon single of the settled days with its grade (read-only)."""
import json
from pathlib import Path
from bet.sofa.coupon_results import key_of

RUNS = Path("/Users/mkoziol/projects/bet/runs/sofa")
DEV_TO = "2026-11-04"  # dev 10-13..11-04, hold-out 11-05..11-18


def days():
    out = []
    for d in sorted(RUNS.glob("2026-1*")):
        if (d / "11_coupon.json").exists() and (d / "13_results.json").exists():
            if "2026-10-13" <= d.name <= "2026-11-18":
                out.append(d.name)
    return out


def load(split):
    rows = []
    for D in days():
        if (split == "dev") != (D <= DEV_TO):
            continue
        c = json.loads((RUNS / D / "11_coupon.json").read_text())
        res = json.loads((RUNS / D / "13_results.json").read_text())["legs"]
        for leg in c.get("singles") or []:
            g = res.get(key_of(leg)) or {}
            st = g.get("status")
            if st not in ("won", "lost"):
                continue
            o = leg.get("offered_odds")
            if not o:
                continue
            rows.append({"day": D, "odds": float(o), "conf": float(leg["confidence"]),
                         "mp": leg.get("market_p"), "ov": leg.get("overround"),
                         "won": st == "won", "sport": leg.get("sport") or "football",
                         "match": str(leg.get("group_key") or leg.get("sofascore_event_id")),
                         "sample": leg.get("sample_size")})
    return rows
