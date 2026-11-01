"""READ-ONLY: does a tier gap between the two tennis players mislead confidence?

PRE-REGISTERED (written before any outcome was read):
  Tier (ordinal) per tournament, from category name + tournament name:
    4 = category "ATP" or "WTA" (tour, Slams included)
    3 = "Challenger" or "WTA 125"
    2 = ITF Men M25 (and any M>=25), ITF Women W35/W50/W75/W100 (W>=35)
    1 = ITF Men M15 (M<25), ITF Women W15 (W<35)
    unmapped = UTR, Juniors, Davis Cup, BJK Cup, United Cup, Exhibition,
               country / other categories, ITF without a prize token
    Qualifying of a tier counts as that tier.
  Player tier as of kickoff (PRIMARY) = median of the mapped tiers of his last
    10 finished singles matches (from his 'last' listing) started before
    kickoff - 10 min; >= 5 mapped matches required, else unknown.
    SENSITIVITY: modal tier (ties -> the tier of the most recent tied match).
  gap = tier(favoured) - tier(opponent).
    S1 STEP_DOWN_FAVOURED: gap >= 1   (favoured usually plays a level higher)
    S2 STEP_UP_FAVOURED:   gap <= -1
    S0 control:            gap == 0
    (0 < |gap| < 1, median half-steps: reported apart as 'half')
  Secondary: match tier vs favoured tier: DOWN (match <= fav - 1),
    UP (match >= fav + 1), LEVEL (|diff| < 1).
  Favoured side: as tennis_measure/measure.py (side markets OVER = subject,
    UNDER = opponent; set_score / set_score_not likewise; aces / DF and totals
    skipped). Totals: no favoured side, reported only for |gap| >= 1 vs 0.
  Stats: n legs, n matches, mean conf, mean 1/odds, hit, hit-conf, hit-1/odds,
    flat ROI, 95% match bootstrap (2000); dev kickoff <= 10-24, hold-out
    10-25..10-31; flag - control difference bootstrapped (matches resampled
    within each group) on hold-out and dev.
  Verdict rule: hold-out CI vs price or vs confidence excludes 0 AND dev point
    estimate same sign -> candidate; else noise.
"""
from __future__ import annotations

import collections
import json
import random
import re
import sqlite3
import statistics
import sys
from datetime import datetime

DB = "file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro"
RUNS = "/Users/mkoziol/projects/bet/runs/sofa"
DAYS = [f"2026-10-{d:02d}" for d in range(5, 32)]
DEV_END = "2026-10-24"
HO_START, HO_END = "2026-10-25", "2026-10-31"
B = 2000
MODE = "modal" if "--modal" in sys.argv else "median"

SIDE_MARKETS_SUBJECT = {"games_won_for", "games_won_set1_for", "games_won_set2_for",
                        "match_won_for", "set1_won_for", "set2_won_for",
                        "aces_for", "double_faults_for"}
TOTALS = {"games_set1_total", "games_set2_total", "games_total", "sets_total",
          "tiebreaks_total"}
PRIZE = re.compile(r"\b([MW])(\d{2,3})\b")


def tier_of(cat: str | None, name: str | None) -> int | None:
    cat = (cat or "").strip()
    if cat in ("ATP", "WTA"):
        return 4
    if cat in ("Challenger", "WTA 125"):
        return 3
    if cat in ("ITF Men", "ITF Women"):
        m = PRIZE.search(name or "")
        if not m:
            return None
        g, v = m.group(1), int(m.group(2))
        if g == "M":
            return 2 if v >= 25 else 1
        return 2 if v >= 35 else 1
    return None


def ts(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def norm(s: str) -> str:
    return " ".join(s.lower().split())


con = sqlite3.connect(DB, uri=True)

fix: dict[int, dict] = {}
for d in DAYS:
    try:
        for f in json.load(open(f"{RUNS}/{d}/02_fixtures.json")):
            if f.get("sport") == "tennis" and f.get("home_entity_id") and f.get("away_entity_id"):
                fix.setdefault(f["sofascore_event_id"], f)
    except FileNotFoundError:
        pass


def subject_side(ev: int, subject: str) -> str | None:
    h = fix.get(ev)
    if h is None:
        return None
    s = norm(subject)
    for suf in (" 0:2", " 2:0", " 2:1", " 1:2", " 0:1", " 1:0"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    if s == norm(h["home_name"]):
        return "home"
    if s == norm(h["away_name"]):
        return "away"
    return None


def favoured(ev: int, market: str, subject: str, direction: str) -> str | None:
    side = subject_side(ev, subject)
    if side is None:
        return None
    other = "away" if side == "home" else "home"
    if market in SIDE_MARKETS_SUBJECT:
        if market in ("aces_for", "double_faults_for"):
            return None
        return side if direction == "OVER" else other
    if market in ("set_score_not", "set_score"):
        return side if direction == "OVER" else other
    return None


_hist: dict[int, list[tuple[int, int | None]]] = {}
COVER = collections.Counter()


def history(pid: int) -> list[tuple[int, int | None]]:
    """(start_ts, tier or None) of his finished singles matches, time order."""
    if pid in _hist:
        return _hist[pid]
    out = []
    for eid, st, j in con.execute(
            "select l.event_id, l.start_ts, e.event_json from sofa_listing_event l "
            "join sofa_listed_event e on e.event_id = l.event_id "
            "where l.entity_id = ? and l.kind = 'last'", (pid,)):
        ev = json.loads(j)
        hid = (ev.get("homeTeam") or {}).get("id")
        aid = (ev.get("awayTeam") or {}).get("id")
        if pid not in (hid, aid):
            continue
        if (ev.get("status") or {}).get("type") != "finished":
            continue
        t = ev.get("tournament") or {}
        tier = tier_of((t.get("category") or {}).get("name"),
                       t.get("name", "") + " " + (t.get("uniqueTournament") or {}).get("name", ""))
        COVER[tier is not None] += 1
        out.append((ev.get("startTimestamp") or st, tier))
    out.sort(key=lambda x: x[0])
    _hist[pid] = out
    return out


def player_tier(pid: int, kickoff: int, mode: str = MODE) -> float | None:
    past = [(st, t) for st, t in history(pid) if st < kickoff - 600][-10:]
    tiers = [t for _, t in past if t is not None]
    if len(tiers) < 5:
        return None
    if mode == "median":
        return float(statistics.median(tiers))
    c = collections.Counter(tiers)
    top = max(c.values())
    tied = {t for t, n in c.items() if n == top}
    for _, t in reversed(past):
        if t in tied:
            return float(t)
    return None


legs: dict[tuple, dict] = {}
for d in DAYS:
    try:
        doc = json.load(open(f"{RUNS}/{d}/08_confidence.json"))
    except FileNotFoundError:
        continue
    for leg in doc["legs"]:
        if leg.get("sport") != "tennis" or not leg.get("offered_odds"):
            continue
        k = (leg["sofascore_event_id"], leg["market"], leg["subject"], float(leg["line"]),
             leg["direction"])
        if k not in legs:
            leg["_day"] = d
            legs[k] = leg

events = sorted({k[0] for k in legs})
graded: dict[tuple, str] = {}
for i in range(0, len(events), 500):
    chunk = events[i:i + 500]
    q = ",".join("?" * len(chunk))
    for ev, m, s, ln, dr, out in con.execute(
            f"select sofascore_event_id, market, subject, line, direction, outcome "
            f"from sofa_settled_row where sport='tennis' and run_date != 'cache-calibration' "
            f"and sofascore_event_id in ({q})", chunk):
        graded[(ev, m, s, float(ln), dr)] = out

rows = []
for k, leg in legs.items():
    out = graded.get(k)
    if out not in ("WIN", "LOSS"):
        continue
    ev = k[0]
    f = fix.get(ev)
    ko = ts(leg["kickoff_utc"])
    r = dict(ev=ev, day=leg["kickoff_utc"][:10], market=leg["market"], conf=leg["confidence"],
             odds=leg["offered_odds"], win=1 if out == "WIN" else 0,
             total=leg["market"] in TOTALS, gap=None, mdiff=None, fav=None,
             subj=leg["subject"], dirn=leg["direction"], line=leg["line"])
    if f is not None:
        th = player_tier(f["home_entity_id"], ko)
        ta = player_tier(f["away_entity_id"], ko)
        mt = tier_of(f.get("category_name"), f.get("competition_name"))
        fav = favoured(ev, leg["market"], leg["subject"], leg["direction"])
        r["fav"] = fav
        r["mt"] = mt
        r["th"], r["ta"] = th, ta
        if fav is not None and th is not None and ta is not None:
            tf, to = (th, ta) if fav == "home" else (ta, th)
            r["gap"] = tf - to
            if mt is not None:
                r["mdiff"] = mt - tf
        if r["total"] and th is not None and ta is not None:
            r["gap"] = abs(th - ta)
    rows.append(r)


def boot_groups(sub, key, seed=7):
    by = collections.defaultdict(list)
    for r in sub:
        by[r["ev"]].append(key(r))
    return list(by.values())


def resample(groups, rng):
    s = n = 0.0
    for _ in range(len(groups)):
        g = groups[rng.randrange(len(groups))]
        s += sum(g)
        n += len(g)
    return s / n


def boot(sub, key):
    groups = boot_groups(sub, key)
    tot = sum(sum(g) for g in groups) / sum(len(g) for g in groups)
    rng = random.Random(7)
    vals = sorted(resample(groups, rng) for _ in range(B))
    return tot, vals[int(0.025 * B)], vals[int(0.975 * B) - 1]


def boot_diff(a, b, key):
    ga, gb = boot_groups(a, key), boot_groups(b, key)
    if not ga or not gb:
        return None
    pt = (sum(sum(g) for g in ga) / sum(len(g) for g in ga)
          - sum(sum(g) for g in gb) / sum(len(g) for g in gb))
    rng = random.Random(11)
    vals = sorted(resample(ga, rng) - resample(gb, rng) for _ in range(B))
    return pt, vals[int(0.025 * B)], vals[int(0.975 * B) - 1]


def pp(t):
    return f"{t[0]*100:+.1f} [{t[1]*100:+.1f},{t[2]*100:+.1f}]"


def summarize(sub, label):
    if not sub:
        return f"{label:30s} n 0"
    n = len(sub)
    m = len({r["ev"] for r in sub})
    mc = sum(r["conf"] for r in sub) / n
    mi = sum(1 / r["odds"] for r in sub) / n
    hit = sum(r["win"] for r in sub) / n
    return (f"{label:30s} n {n:5d} m {m:4d} conf {mc:.3f} 1/o {mi:.3f} hit {hit:.3f} | "
            f"h-c {pp(boot(sub, lambda r: r['win'] - r['conf']))} | "
            f"h-1/o {pp(boot(sub, lambda r: r['win'] - 1 / r['odds']))} | "
            f"ROI {pp(boot(sub, lambda r: r['win'] * r['odds'] - 1))}")


def diff(a, b, label):
    dc = boot_diff(a, b, lambda r: r["win"] - r["conf"])
    dp = boot_diff(a, b, lambda r: r["win"] - 1 / r["odds"])
    if dc is None:
        return f"{label:30s} diff: empty"
    return f"{label:30s} flag-control: h-c {pp(dc)} | h-1/o {pp(dp)}"


def split(rs):
    return [("dev", [r for r in rs if r["day"] <= DEV_END]),
            ("hold", [r for r in rs if HO_START <= r["day"] <= HO_END])]


side = [r for r in rows if not r["total"] and r["fav"] is not None]
print(f"MODE {MODE}; graded legs {len(rows)}; side legs with favoured {len(side)}; "
      f"with gap {sum(r['gap'] is not None for r in side)}; totals {sum(r['total'] for r in rows)} "
      f"with both tiers {sum(r['total'] and r['gap'] is not None for r in rows)}")
print(f"listing matches mapped/unmapped: {COVER[True]}/{COVER[False]} "
      f"({COVER[False]/(COVER[True]+COVER[False])*100:.1f}% unmapped)")
print("fixture (match) tier of side legs:", collections.Counter(r.get("mt") for r in side))
print("gap distribution side legs:", sorted(collections.Counter(r["gap"] for r in side).items(),
                                            key=lambda x: (x[0] is None, x[0] or 0)))

groups = {"S1 STEP_DOWN_FAV gap>=1": lambda r: r["gap"] is not None and r["gap"] >= 1,
          "S2 STEP_UP_FAV gap<=-1": lambda r: r["gap"] is not None and r["gap"] <= -1,
          "S0 same tier gap==0": lambda r: r["gap"] == 0,
          "half 0<|gap|<1": lambda r: r["gap"] is not None and 0 < abs(r["gap"]) < 1}
print("\n=== PRIMARY: favoured vs opponent tier ===")
for per, rs in split(side):
    ctrl = [r for r in rs if groups["S0 same tier gap==0"](r)]
    for name, fn in groups.items():
        sub = [r for r in rs if fn(r)]
        print(summarize(sub, f"{per} {name}"))
    for name in ("S1 STEP_DOWN_FAV gap>=1", "S2 STEP_UP_FAV gap<=-1"):
        print(diff([r for r in rs if groups[name](r)], ctrl, f"{per} {name[:2]} vs S0"))
    print()

print("=== SECONDARY: match tier vs favoured player's tier ===")
sec = {"DOWN match<=fav-1": lambda r: r["mdiff"] is not None and r["mdiff"] <= -1,
       "UP match>=fav+1": lambda r: r["mdiff"] is not None and r["mdiff"] >= 1,
       "LEVEL": lambda r: r["mdiff"] is not None and abs(r["mdiff"]) < 1}
for per, rs in split(side):
    ctrl = [r for r in rs if sec["LEVEL"](r)]
    for name, fn in sec.items():
        print(summarize([r for r in rs if fn(r)], f"{per} {name}"))
    for name in ("DOWN match<=fav-1", "UP match>=fav+1"):
        print(diff([r for r in rs if sec[name](r)], ctrl, f"{per} {name[:4]} vs LEVEL"))
    print()

print("=== TOTALS: |tier gap| >= 1 vs 0 ===")
tot = [r for r in rows if r["total"] and r["gap"] is not None]
for per, rs in split(tot):
    a = [r for r in rs if r["gap"] >= 1]
    b = [r for r in rs if r["gap"] == 0]
    print(summarize(a, f"{per} totals |gap|>=1"))
    print(summarize(b, f"{per} totals gap==0"))
    print(diff(a, b, f"{per} totals"))

print("\n=== firing per day (side legs / matches) ===")
for name in ("S1 STEP_DOWN_FAV gap>=1", "S2 STEP_UP_FAV gap<=-1"):
    fl = collections.defaultdict(list)
    for r in side:
        if groups[name](r):
            fl[r["day"]].append(r["ev"])
    nd = len({r["day"] for r in side})
    tl = sum(len(v) for v in fl.values())
    tm = sum(len(set(v)) for v in fl.values())
    print(f"{name}: {tl} legs / {tm} match-days over {nd} days = {tl/nd:.1f} legs, "
          f"{tm/nd:.1f} matches a day")
s1 = [r for r in side if groups["S1 STEP_DOWN_FAV gap>=1"](r)]
print("S1 markets:", collections.Counter(r["market"] for r in s1).most_common(8))

print("\n=== Pereira check ===")
for r in rows:
    if "Pereira" in r["subj"] and r["market"].startswith("games_won_set1"):
        print(r["day"], r["subj"], r["dirn"], r["line"], r["conf"], r["odds"], r["win"],
              "th", r.get("th"), "ta", r.get("ta"), "mt", r.get("mt"), "gap", r["gap"])
