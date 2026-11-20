import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path
from bet.sofa.market_coverage import template_of
from bet.sofa import leg_identity as li, football_sim_markets as sim
# 4: draw both halves "tak" vs htft X/X
dbh = tuple((s[0] == s[1] and s[2] == s[3]) for s in li._STATES)
print("DBH tak == htft X/X:", dbh == li._football_vector("htft", "X/X", None, 0.5))
for day in sys.argv[1:]:
    rd = Path("runs/sofa") / day
    fx = {int(f["sofascore_event_id"]): f for f in json.load(open(rd / "02_fixtures.json")) if f.get("sport") == "football"}
    board = {str(e["superbet_event_id"]): (e.get("side_a") or "", e.get("side_b") or "") for e in json.load(open(rd / "01_board.json"))}
    latest = {}
    for fp in sorted((rd / "unmapped_prices").glob("2026*.jsonl.gz")):
        for line in gzip.open(fp, "rt", encoding="utf-8"):
            d = json.loads(line); eid = d.get("sofascore_event_id")
            if not isinstance(eid, int) or eid not in fx or d.get("status") != "active": continue
            if (d.get("fetched_at_utc") or "") >= fx[eid]["kickoff_utc"]: continue
            k = (eid, d.get("marketName"), d.get("name"), d.get("specialBetValue"))
            if k not in latest or latest[k][0] <= d["fetched_at_utc"]:
                latest[k] = (d["fetched_at_utc"], d.get("price"), str(d.get("superbet_event_id")))
    zone = Counter(); ev = defaultdict(set)
    for (eid, mn, name, sbv), (ts, price, sb) in latest.items():
        if price and 1.09 <= price <= 1.43:
            f = fx[eid]; b = board.get(sb, ("", ""))
            t = template_of(mn or "", [b[0], b[1], f["home_name"], f["away_name"]])
            zone[t] += 1; ev[t].add(eid)
    print(day, "football events", len(fx), "unmapped selections", len(latest))
    for t, n in zone.most_common(30): print(f"   {n:6d} sel {len(ev[t]):5d} ev  {t}")
