"""Collect tennis serve N+ ladders, tiebreak-in-set and old-format offer keys. Read-only."""
import collections
import glob
import gzip
import json
import os
import pickle
import re
from datetime import date, timedelta

OUT = os.path.dirname(os.path.abspath(__file__))
fx = {}  # ev -> dict
days = []
d = date(2026, 10, 1)
while d <= date(2026, 11, 20):
    days.append(d.isoformat())
    d += timedelta(days=1)

for day in days:
    p = f"runs/sofa/{day}/02_fixtures.json"
    if not os.path.exists(p):
        continue
    for f in json.load(open(p)):
        if f.get("sport") != "tennis":
            continue
        ks = [k for k in (f.get("kickoff_utc"), f.get("superbet_kickoff_utc")) if k]
        fx.setdefault(f["sofascore_event_id"], dict(day=day, ko=min(ks) if ks else None,
                       home=f.get("home_name"), away=f.get("away_name"),
                       comp=f.get("competition_name"), cat=f.get("category_name")))

SERVE = re.compile(r"^(?:([12])\. set - )?(?:(.+?) )?(asy \+ podwójne błędy|asy|podwójne błędy)$", re.I)
NPLUS = re.compile(r"^(\d+)\+$")

# offer: old-format serve keys and games_setX_total 12.5 per day
offer = {}
for day in days:
    p = f"runs/sofa/{day}/04_offer.json"
    if not os.path.exists(p):
        continue
    old, um_new, set12 = set(), set(), collections.defaultdict(set)
    for e in json.load(open(p)):
        ev = e["sofascore_event_id"]
        if ev not in fx:
            continue
        for r in e.get("rungs") or []:
            m = r["market"]
            if m.startswith(("aces", "double_faults", "serve_points")):
                old.add(ev)
            if m in ("games_set1_total", "games_set2_total", "games_set3_total"):
                set12[ev].add((m, r["line"]))
        for u in e.get("unmapped_markets") or []:
            if isinstance(u, str) and SERVE.match(u) and "podwójne błędy" != u.lower():
                um_new.add(ev)
    offer[day] = dict(old=old, um_new=um_new, set12=dict(set12))

serve_last_pre, serve_last_any, tb = {}, {}, {}
post_start_recs = collections.Counter()
mn_counter = collections.Counter()
new_by_day = collections.defaultdict(set)
for day in days:
    for f in sorted(glob.glob(f"runs/sofa/{day}/unmapped_prices/2026*.jsonl.gz")):
        for line in gzip.open(f, "rt"):
            r = json.loads(line)
            ev = r.get("sofascore_event_id")
            if ev not in fx:
                continue
            mn = r["marketName"]
            ko = fx[ev]["ko"]
            pre = ko is None or r["fetched_at_utc"] < ko.replace("Z", "")[:19] + "Z" or r["fetched_at_utc"][:19] < ko[:19]
            pre = r["fetched_at_utc"][:19] < ko[:19] if ko else True
            m = SERVE.match(mn)
            if m and NPLUS.match(r["name"]):
                k = (ev, mn, r["name"], r.get("specialBetValue"))
                if not pre:
                    post_start_recs[r.get("status")] += 1
                if pre:
                    new_by_day[day].add(ev)
                    o = serve_last_pre.get(k)
                    if o is None or r["fetched_at_utc"] > o["fetched_at_utc"]:
                        serve_last_pre[k] = r
                o = serve_last_any.get(k)
                if o is None or r["fetched_at_utc"] > o["fetched_at_utc"]:
                    serve_last_any[k] = r
            elif mn.startswith("Tiebreak w X. secie") and pre:
                k = (ev, mn, r["name"], r.get("specialBetValue"))
                o = tb.get(k)
                if o is None or r["fetched_at_utc"] > o["fetched_at_utc"]:
                    tb[k] = r
pickle.dump(dict(fx=fx, offer=offer, pre=serve_last_pre, any=serve_last_any, tb=tb,
                 post=post_start_recs, new_by_day={k: v for k, v in new_by_day.items()}),
            open(os.path.join(OUT, "collect.pkl"), "wb"))
print("tennis fixtures", len(fx), "serve keys pre", len(serve_last_pre), "any", len(serve_last_any),
      "tb", len(tb), "post-start serve records by status", dict(post_start_recs))
