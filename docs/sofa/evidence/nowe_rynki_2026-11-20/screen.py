import gzip, json, glob, os, sys, collections, statistics, re
sys.path[:0] = ["src", "."]
from bet.sofa.market_coverage import template_of, fixture_sides, classify_market_name
D0, D1 = "2026-11-06", "2026-11-19"
days = [d for d in sorted(os.listdir("runs/sofa")) if D0 <= d <= D1]
# last snapshot per (event, market, sbv, name)
stats = collections.defaultdict(lambda: {"ev": set(), "days": set(), "sel": 0, "zone": 0, "zone_ev": set(), "ovr": [], "onesided": 0, "ex": "", "fam": ""})
for d in days:
    rd = f"runs/sofa/{d}"
    try:
        fx = {int(f["sofascore_event_id"]): f for f in json.load(open(f"{rd}/02_fixtures.json"))}
        board = {str(b["superbet_event_id"]): b for b in json.load(open(f"{rd}/01_board.json"))}
    except Exception:
        fx, board = {}, {}
    last = {}
    for f in sorted(glob.glob(f"{rd}/unmapped_prices/*.jsonl.gz")):
        b = os.path.basename(f)
        sport = b.split("_")[0] if b[0].isalpha() else None
        for line in gzip.open(f, "rt"):
            r = json.loads(line)
            sp = sport
            if sp is None:
                fxe = fx.get(r.get("sofascore_event_id"))
                if not fxe: continue
                sp = fxe["sport"]
            key = (sp, r["superbet_event_id"], r.get("marketName"), r.get("name"), r.get("specialBetValue"))
            if key not in last or r["fetched_at_utc"] >= last[key][0]:
                last[key] = (r["fetched_at_utc"], r, sp)
    groups = collections.defaultdict(list)
    for (sp, ev, mn, nm, sbv), (_, r, _) in last.items():
        groups[(sp, ev, mn, sbv)].append(r)
    tcache = {}
    for (sp, ev, mn, sbv), rows in groups.items():
        if sp in ("football", "tennis"):
            fxe = fx.get(rows[0].get("sofascore_event_id"))
            ck = (mn, rows[0].get("sofascore_event_id"))
            if ck not in tcache:
                sides = fixture_sides(fxe, board) if fxe else []
                t = template_of(mn, sides); fam = classify_market_name(mn, sp, sides).family if fxe else ""
                tcache[ck] = (t, fam)
            t, fam = tcache[ck]
        else:
            t, fam = f"mid:{rows[0].get('marketId')}", ""
        prices = [float(r["price"]) for r in rows if r.get("price")]
        if not prices: continue
        s = sum(1 / p for p in prices)
        part = len(prices) >= 2 and 1.0 <= s <= 1.4
        st = stats[(sp, t)]
        st["ev"].add(ev); st["days"].add(d); st["ex"] = st["ex"] or mn; st["fam"] = st["fam"] or fam
        if part: st["ovr"].append(s)
        for p in prices:
            st["sel"] += 1
            fair = (1 / p) / s if part else 1 / p
            if not part: st["onesided"] += 1
            if 1.09 <= p <= 1.43 and fair >= 0.70:
                st["zone"] += 1; st["zone_ev"].add(ev)
out = []
for (sp, t), st in stats.items():
    out.append({"sport": sp, "template": t, "family": st["fam"], "example": st["ex"], "events": len(st["ev"]), "days": len(st["days"]),
                "sel": st["sel"], "zone": st["zone"], "zone_events": len(st["zone_ev"]), "onesided_share": round(st["onesided"] / max(1, st["sel"]), 2),
                "ovr_med": round(statistics.median(st["ovr"]), 3) if st["ovr"] else None})
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
print(len(out))
