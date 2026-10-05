"""National-team sample composition, measured on the cache (scratch, read-only).

Reuses scripts/sofa/measure_sample_composition.py (Past, Target, before,
poisson_logloss, poisson_over, _statistics, paired_interval, LINES).
"""
from __future__ import annotations
import json, sqlite3, sys, re, pickle
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, "/Users/mkoziol/projects/bet")
from scripts.sofa.measure_sample_composition import (
    Past, Target, before, poisson_logloss, poisson_over, _statistics,
    paired_interval, LINES, split_metric)
from bet.sofa.comparability import MatchKind, competition_id, match_kind
from bet.sofa.metrics import is_extra_time_event, regulation_score

OUT = Path(__file__).parent
DAY = 86400
LINES = dict(LINES)
LINES.update({"yellow_cards_total": (2.5, 3.5, 4.5), "yellow_cards_for": (0.5, 1.5, 2.5),
              "corners_total": (7.5, 8.5, 9.5, 10.5), "corners_for": (2.5, 3.5, 4.5, 5.5),
              "shots_total": (19.5, 21.5, 23.5), "shots_for": (8.5, 10.5, 12.5)})

def load():
    cache = OUT / "nations_cache.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    con = sqlite3.connect("file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro", uri=True)
    events = []
    for (js,) in con.execute(
        "SELECT event_json FROM sofa_listed_event WHERE sport='football' AND "
        "(json_extract(event_json,'$.homeTeam.national')=1 OR json_extract(event_json,'$.awayTeam.national')=1)"):
        e = json.loads(js)
        if (e.get("status") or {}).get("type") != "finished":
            continue
        events.append(e)
    ids = [e["id"] for e in events]
    stats = {}
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        q = "SELECT sofascore_event_id, statistics_json FROM sofa_event_stats WHERE status_type='finished' AND sofascore_event_id IN (%s)" % ",".join("?" * len(chunk))
        for eid, js in con.execute(q, chunk):
            v = _statistics(js)
            if v:
                stats[int(eid)] = v
    history = defaultdict(list); targets = []; meta = {}
    seen = set()
    for e in events:
        eid, ts = e.get("id"), e.get("startTimestamp")
        comp = competition_id(e)
        if not isinstance(eid, int) or not isinstance(ts, int) or eid in seen:
            continue
        seen.add(eid)
        if comp is None:
            comp = -1
        try:
            home, away = int(e["homeTeam"]["id"]), int(e["awayTeam"]["id"])
        except Exception:
            continue
        reg = regulation_score(e)
        if reg is None:
            continue
        season = (e.get("season") or {}).get("id")
        values = {} if is_extra_time_event(e) else dict(stats.get(eid, {}))
        values["goals"] = reg
        kind = match_kind(e, "football")
        sw = {k: (v[1], v[0]) for k, v in values.items()}
        history[home].append(Past(ts, eid, comp, season, kind, values))
        history[away].append(Past(ts, eid, comp, season, kind, sw))
        both_nat = bool(e["homeTeam"].get("national")) and bool(e["awayTeam"].get("national"))
        if kind is not MatchKind.FRIENDLY and both_nat:
            targets.append(Target(ts, eid, comp, season, home, away, values, kind))
            name = " ".join(str(x) for x in (e["homeTeam"].get("name"), e["awayTeam"].get("name"),
                         (e["tournament"].get("uniqueTournament") or {}).get("name") or e["tournament"].get("name")))
            youth = bool(re.search(r"\bU-?\d\d\b", name))
            women = (e["homeTeam"].get("gender") == "F") or bool(re.search(r"wom[ae]n", name, re.I))
            meta[eid] = {"senior_men": not youth and not women, "youth": youth, "women": women,
                         "comp": comp, "name": name}
    for s in history.values():
        s.sort(key=lambda p: (p.ts, p.event_id))
    data = (dict(history), targets, meta)
    cache.write_bytes(pickle.dumps(data))
    return data

def adm(p): return p.kind is not MatchKind.FRIENDLY

def make_rules():
    def r_all(b, t, n, m):  # (a) newest ten competitive (SAMPLES today for non-goal metrics)
        return [p for p in b if adm(p)][:n]
    def r_same(b, t, n, m):  # (b) same competition REGULAR, >=5 else (a)  (SAMPLES today for goals)
        ch = [p for p in b if p.kind is MatchKind.REGULAR and p.competition == t.competition][:n]
        return ch if len(ch) >= m else r_all(b, t, n, m)
    def win(N):
        def r(b, t, n, m):  # (c) newest ten competitive within N days, >=5 else (a)
            ch = [p for p in b if adm(p) and t.ts - p.ts <= N * DAY][:n]
            return ch if len(ch) >= m else r_all(b, t, n, m)
        return r
    def newest5(b, t, n, m):
        return [p for p in b if adm(p)][:5]
    def incl_friendly(b, t, n, m):
        return list(b)[:n]
    rules = {"a_all10": r_all, "b_same_comp": r_same}
    for N in (180, 365, 540, 730):
        rules[f"c_win{N}"] = win(N)
    rules["n5_newest5"] = newest5
    rules["f_incl_friendly10"] = incl_friendly
    return rules

def hard_window(b, t, n, X):
    return [p for p in b if adm(p) and t.ts - p.ts <= X * DAY][:n]

def evaluate(history, targets, metric, n=10, m=5, start_ts=0):
    stat, scope = split_metric(metric)
    lines = LINES.get(metric, ())
    rules = make_rules(); names = list(rules)
    rows, ids, ages, hard = [], [], [], []
    def score(lam, y):
        return [poisson_logloss(lam, y), (lam - y) ** 2] + [(poisson_over(lam, L) - (y > L)) ** 2 for L in lines]
    for t in targets:
        if t.ts < start_ts: continue
        pair = t.values.get(stat)
        if pair is None: continue
        ab = before(history.get(t.home, []), t.ts, metric)
        bb = before(history.get(t.away, []), t.ts, metric)
        base_a = rules["a_all10"](ab, t, n, m); base_b = rules["a_all10"](bb, t, n, m)
        def hw(sideb, X):
            return hard_window(sideb, t, n, X)
        if scope == "total":
            if len(base_a) < n or len(base_b) < n: continue
            y = pair[0] + pair[1]
            per = []
            for nm in names:
                pool = rules[nm](ab, t, n, m) + rules[nm](bb, t, n, m)
                vals = [p.value(metric) or 0.0 for p in pool]
                per.append(score(sum(vals) / len(vals), y))
            hrow = {}
            for X in (180, 365, 540, 730):
                ha, hb = hw(ab, X), hw(bb, X)
                if len(ha) >= m and len(hb) >= m:
                    vals = [p.value(metric) or 0.0 for p in ha + hb]
                    hrow[X] = score(sum(vals) / len(vals), y)
            rows.append(per); ids.append(t.event_id); hard.append(hrow)
            ages.append((t.ts - min(p.ts for p in base_a + base_b)) / DAY)
            continue
        for sideb, base, y in ((ab, base_a, pair[0]), (bb, base_b, pair[1])):
            if len(base) < n: continue
            per = []
            for nm in names:
                own = rules[nm](sideb, t, n, m)
                vals = [p.value(metric) or 0.0 for p in own]
                per.append(score(sum(vals) / len(vals), y))
            hrow = {}
            for X in (180, 365, 540, 730):
                h = hw(sideb, X)
                if len(h) >= m:
                    vals = [p.value(metric) or 0.0 for p in h]
                    hrow[X] = score(sum(vals) / len(vals), y)
            rows.append(per); ids.append(t.event_id); hard.append(hrow)
            ages.append((t.ts - min(p.ts for p in base)) / DAY)
    return names, np.asarray(rows), np.asarray(ids), np.asarray(ages), hard
