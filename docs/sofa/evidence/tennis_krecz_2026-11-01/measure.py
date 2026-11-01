"""READ-ONLY: tennis RECENT_RETIREMENT and MODEL_ABOVE_OWN_SAMPLE on settled legs.

Population P1 (primary): tennis legs of runs/sofa/<d>/08_confidence.json
(confidence >= 0.70, Superbet price, final CONFIDENCE run of the day - mostly
the printed / locked legs), deduped by key, graded by sofa_settled_row (live
run_date rows). Population P2 (secondary, A only): every live sofa_settled_row
tennis row with offered_odds (the whole priced SHEET, no confidence).
"""
from __future__ import annotations

import collections
import glob
import json
import random
import sqlite3
import sys
from datetime import datetime, timezone

DB = "file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro"
RUNS = "/Users/mkoziol/projects/bet/runs/sofa"
DAYS = [f"2026-10-{d:02d}" for d in range(5, 32)]
DEV_END = "2026-10-24"
HO_START, HO_END = "2026-10-25", "2026-10-31"
WINDOW_S = 14 * 86400
B = 2000

SIDE_MARKETS_SUBJECT = {"games_won_for", "games_won_set1_for", "games_won_set2_for",
                        "match_won_for", "set1_won_for", "set2_won_for",
                        "aces_for", "double_faults_for"}
TOTALS = {"games_set1_total", "games_set2_total", "games_total", "sets_total",
          "tiebreaks_total"}


def ts(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def norm(s: str) -> str:
    return " ".join(s.lower().split())


con = sqlite3.connect(DB, uri=True)

# ---- fixtures: event -> (home id, away id, home name, away name)
fix: dict[int, tuple[int, int, str, str]] = {}
for d in DAYS:
    try:
        for f in json.load(open(f"{RUNS}/{d}/02_fixtures.json")):
            if f.get("sport") == "tennis" and f.get("home_entity_id") and f.get("away_entity_id"):
                fix.setdefault(f["sofascore_event_id"], (f["home_entity_id"], f["away_entity_id"],
                                                         f["home_name"], f["away_name"]))
    except FileNotFoundError:
        pass


def subject_side(ev: int, subject: str) -> str | None:
    """'home' / 'away' for a subject naming a player of the fixture."""
    h = fix.get(ev)
    if h is None:
        return None
    s = norm(subject)
    for suf in (" 0:2", " 2:0", " 2:1", " 1:2", " 0:1", " 1:0"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    if s == norm(h[2]):
        return "home"
    if s == norm(h[3]):
        return "away"
    return None


def favoured(ev: int, market: str, subject: str, direction: str) -> str | None:
    """Side whose success the leg needs (mapping stated in the report)."""
    side = subject_side(ev, subject)
    if side is None:
        return None
    other = "away" if side == "home" else "home"
    if market in SIDE_MARKETS_SUBJECT:
        if market in ("aces_for", "double_faults_for"):
            return None  # serve counts: not a strength claim; skipped
        return side if direction == "OVER" else other
    if market == "set_score_not":   # "<X> 0:2" OVER = X wins a set
        return side if direction == "OVER" else other
    if market == "set_score":       # "<X> 2:0" OVER = X wins 2:0
        return side if direction == "OVER" else other
    return None


# ---- player listings: abnormal finishes
_hist: dict[int, list[tuple[int, int, int, int | None, bool]]] = {}


def history(pid: int) -> list[tuple[int, int, int, int | None, bool]]:
    """(start_ts, event_id, status_code, winnerCode, pid_is_home) singles only."""
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
        status = ev.get("status") or {}
        if status.get("type") != "finished":
            continue
        out.append((ev.get("startTimestamp") or st, eid, status.get("code"),
                    ev.get("winnerCode"), pid == hid))
    out.sort()
    _hist[pid] = out
    return out


ABN_CODES: collections.Counter = collections.Counter()


def recent_retirement(pid: int, kickoff: int, strict: bool = False) -> bool:
    """He lost a match by retirement / walkover / default in [kickoff-14d,
    kickoff); strict: no normally completed match of his since then."""
    last_abn = None
    for st, eid, code, wc, is_home in history(pid):
        if st >= kickoff - 600 or st < kickoff - WINDOW_S:
            continue
        if code != 100 and wc in (1, 2):
            lost = (wc == 2) if is_home else (wc == 1)
            if lost:
                last_abn = st
                ABN_CODES[code] += 1
    if last_abn is None:
        return False
    if not strict:
        return True
    return not any(last_abn < st < kickoff - 600 and code == 100
                   for st, eid, code, wc, _ in history(pid))


# ---- P1 legs
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
ungraded = collections.Counter()
for k, leg in legs.items():
    out = graded.get(k)
    if out not in ("WIN", "LOSS"):
        ungraded[leg["_day"] <= DEV_END] += 1
        continue
    ko = ts(leg["kickoff_utc"])
    ev = k[0]
    fav = favoured(ev, leg["market"], leg["subject"], leg["direction"])
    f = fix.get(ev)
    retA = retA_strict = None
    either = None
    if f is not None:
        pids = {"home": f[0], "away": f[1]}
        if fav is not None:
            retA = recent_retirement(pids[fav], ko)
            retA_strict = recent_retirement(pids[fav], ko, strict=True)
        either = recent_retirement(f[0], ko) or recent_retirement(f[1], ko)
    hr = leg.get("sample_hit_rate")
    gap = (leg["model_p"] - hr) if (hr is not None and leg.get("model_p") is not None
                                     and (leg.get("sample_size") or 0) >= 5) else None
    rows.append(dict(ev=ev, day=leg["kickoff_utc"][:10], market=leg["market"],
                     conf=leg["confidence"], odds=leg["offered_odds"],
                     win=1 if out == "WIN" else 0, fav=fav, retA=retA, retA_s=retA_strict,
                     either=either, gap=gap, total=leg["market"] in TOTALS))


def boot(sub: list[dict], key) -> tuple[float, float, float]:
    by = collections.defaultdict(list)
    for r in sub:
        by[r["ev"]].append(key(r))
    groups = list(by.values())
    tot = sum(sum(g) for g in groups) / sum(len(g) for g in groups)
    rng = random.Random(7)
    vals = []
    for _ in range(B):
        s = n = 0.0
        for _ in range(len(groups)):
            g = groups[rng.randrange(len(groups))]
            s += sum(g)
            n += len(g)
        vals.append(s / n)
    vals.sort()
    return tot, vals[int(0.025 * B)], vals[int(0.975 * B) - 1]


def summarize(sub: list[dict], label: str) -> str:
    if not sub:
        return f"{label:34s} n 0"
    n = len(sub)
    m = len({r["ev"] for r in sub})
    mc = sum(r["conf"] for r in sub) / n
    mi = sum(1 / r["odds"] for r in sub) / n
    hit = sum(r["win"] for r in sub) / n
    dc = boot(sub, lambda r: r["win"] - r["conf"])
    dp = boot(sub, lambda r: r["win"] - 1 / r["odds"])
    roi = boot(sub, lambda r: r["win"] * r["odds"] - 1)
    return (f"{label:34s} n {n:5d} m {m:4d} conf {mc:.3f} 1/odds {mi:.3f} hit {hit:.3f} | "
            f"hit-conf {dc[0]*100:+.1f} [{dc[1]*100:+.1f},{dc[2]*100:+.1f}] | "
            f"hit-1/o {dp[0]*100:+.1f} [{dp[1]*100:+.1f},{dp[2]*100:+.1f}] | "
            f"ROI {roi[0]*100:+.1f}% [{roi[1]*100:+.1f},{roi[2]*100:+.1f}]")


def split(rs):
    return [("dev <=10-24", [r for r in rs if r["day"] <= DEV_END]),
            ("hold 10-25..31", [r for r in rs if HO_START <= r["day"] <= HO_END])]


print(f"P1 legs deduped {len(legs)}, graded {len(rows)}, ungraded (refund/void/pending) "
      f"dev {ungraded[True]} hold {ungraded[False]}")
print(f"fixtures with entity ids {len(fix)}; legs with favoured side "
      f"{sum(r['fav'] is not None for r in rows)}; totals {sum(r['total'] for r in rows)}")

print("\n=== A RECENT_RETIREMENT (favoured player lost by ret/wo/default in 14 d) ===")
for per, rs in split(rows):
    side = [r for r in rs if r["retA"] is not None]
    print(summarize([r for r in side if r["retA"]], f"{per} FLAG"))
    print(summarize([r for r in side if not r["retA"]], f"{per} control"))
    print(summarize([r for r in side if r["retA_s"]], f"{per} FLAG strict(no win since)"))
print("--- A on totals / all legs: either player")
for per, rs in split(rows):
    tot = [r for r in rs if r["total"] and r["either"] is not None]
    print(summarize([r for r in tot if r["either"]], f"{per} totals FLAG"))
    print(summarize([r for r in tot if not r["either"]], f"{per} totals control"))
print("abnormal codes counted in flags:", dict(ABN_CODES))
fl = collections.Counter(r["day"] for r in rows if r["retA"])
fm = collections.defaultdict(set)
for r in rows:
    if r["retA"]:
        fm[r["day"]].add(r["ev"])
print("A flagged legs per day (legs/matches):",
      {d: f"{fl[d]}/{len(fm[d])}" for d in sorted(fl)})
print("A favoured-side markets:", collections.Counter(r["market"] for r in rows if r["retA"]))

print("\n=== B MODEL_ABOVE_OWN_SAMPLE (model_p - sample_hit_rate, sample >= 5) ===")
for thr in (0.15, 0.10, 0.20):
    for per, rs in split(rows):
        g = [r for r in rs if r["gap"] is not None]
        print(summarize([r for r in g if r["gap"] > thr], f"{per} gap>{thr:.2f} FLAG"))
        print(summarize([r for r in g if r["gap"] <= thr], f"{per} gap>{thr:.2f} control"))
    print()
print("B flagged by market (0.15):",
      collections.Counter(r["market"] for r in rows if r["gap"] is not None and r["gap"] > 0.15))

# ---- P2: whole priced sheet, A only
if "--p2" in sys.argv:
    print("\n=== P2 (secondary): all live settled tennis SHEET rows with a price, A only ===")
    p2 = []
    q = ("select r.sofascore_event_id, r.market, r.subject, r.direction, r.offered_odds, "
         "r.outcome, r.run_date, r.p_central from sofa_settled_row r where r.sport='tennis' "
         "and r.run_date between '2026-10-05' and '2026-10-31' and r.offered_odds > 1.0")
    kick: dict[int, int] = {}
    for d in DAYS:
        try:
            for f in json.load(open(f"{RUNS}/{d}/02_fixtures.json")):
                if f.get("sport") == "tennis":
                    kick.setdefault(f["sofascore_event_id"], ts(f["kickoff_utc"]))
        except FileNotFoundError:
            pass
    for ev, m, s, dr, odds, out, rd, pc in con.execute(q):
        if out not in ("WIN", "LOSS") or ev not in fix or ev not in kick:
            continue
        fav = favoured(ev, m, s, dr)
        if fav is None:
            continue
        f = fix[ev]
        pid = f[0] if fav == "home" else f[1]
        day = datetime.fromtimestamp(kick[ev], timezone.utc).strftime("%Y-%m-%d")
        p2.append(dict(ev=ev, day=day, market=m, conf=pc, odds=odds,
                       win=1 if out == "WIN" else 0, retA=recent_retirement(pid, kick[ev])))
    for per, rs in split(p2):
        print(summarize([r for r in rs if r["retA"]], f"{per} FLAG (conf=p_central)"))
        print(summarize([r for r in rs if not r["retA"]], f"{per} control"))
        hi = [r for r in rs if r["conf"] >= 0.70]
        print(summarize([r for r in hi if r["retA"]], f"{per} p>=.70 FLAG"))
        print(summarize([r for r in hi if not r["retA"]], f"{per} p>=.70 control"))
