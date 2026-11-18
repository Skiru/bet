"""Counts only: stakes states per side as of kick-off, per period, with which
statistics are present. No outcome (score of the match itself, residual,
hit rate) is computed by state. Scores are read only for matches BEFORE each
kick-off to rebuild the table."""
from __future__ import annotations

import itertools
import pickle
import sys
from collections import Counter, defaultdict

import pandas as pd

S = sys.argv[1]
sys.path.insert(0, S)
from stakes_state import H2H, final_state  # noqa: E402

d = pd.read_pickle(f"{S}/listed.pkl")
stats = pickle.load(open(f"{S}/stats_presence.pkl", "rb"))

# national competitions in scope: ut -> (boundaries rule, h2h first?)
NATIONAL = {
    10783: ("unl", True),      # UEFA Nations League
    27: ("top12", True),       # EURO qualification
    11: ("top12", False),      # WCQ UEFA
    13: ("top12", False),      # WCQ CAF
    1848: ("top2", False),     # AFCON qualification
    14100: ("first_last", False),  # CONCACAF Nations League
    295: ("conmebol", False),  # WCQ CONMEBOL
}


def national_bounds(rule: str, n: int, tname: str) -> list[int]:
    if rule == "unl":
        return [1] if "League D" in str(tname) else list(range(1, n))
    if rule == "top12":
        return [1, 2]
    if rule == "top2":
        return [2]
    if rule == "first_last":
        return sorted({1, n - 1})
    if rule == "conmebol":
        return [6, 7]
    raise ValueError(rule)


P = [("pre", "2022-07-01", "2024-07-01"), ("dev", "2024-07-01", "2025-07-01"),
     ("val", "2025-07-01", "2026-01-01"), ("exam", "2026-01-01", "2026-11-18")]
P = [(n, pd.Timestamp(a).timestamp(), pd.Timestamp(b).timestamp()) for n, a, b in P]


def period(ts: float) -> str | None:
    for n, a, b in P:
        if a <= ts < b:
            return n
    return None


d = d[d.st.isin(["finished", "notstarted"]) & (~d.friendly) & d.hid.notna() & d.aid.notna() & d.ut.notna()]
d = d[~((d.st == "finished") & (d.hg.isna() | d.ag.isna()))]
d = d[d.start_ts >= P[0][1] - 400 * 86400]
league_round = d.cup_rt.isna() & d.rnd_name.isna()
ko_utseason = set(map(tuple, d.loc[~league_round, ["ut", "season"]].dropna().values.tolist()))
d = d[league_round]
NOW = pd.Timestamp("2026-11-18").timestamp()
teamsets = defaultdict(list)
for (ut, season, tid), g in d.groupby(["ut", "season", "tid"], dropna=True):
    teamsets[(ut, season)].append((tid, set(g.hid.astype(int)) | set(g.aid.astype(int))))

rows = []
groups_seen = Counter()
group_meta = []
for (ut, season, tid), g in d.groupby(["ut", "season", "tid"], dropna=True):
    key_ut = ut
    ut = int(ut)
    nat = ut in NATIONAL
    if not nat and (g.hnat == 1).any():
        continue  # national competitions outside the scope
    teams = sorted(set(g.hid.astype(int)) | set(g.aid.astype(int)))
    n = len(teams)
    if n < 3:
        continue
    kind = "nat" if nat else "club"
    if not nat and n < 12:
        groups_seen["club_small"] += 1
        continue
    if not nat and any(t2 != tid and len(ts2 & set(teams)) >= 3 for t2, ts2 in teamsets[(key_ut, season)]):
        groups_seen["club_split_stage"] += 1
        continue
    pc = Counter(frozenset((int(r.hid), int(r.aid))) for r in g.itertuples())
    m = max(pc.values())
    allp = [frozenset(p) for p in itertools.combinations(teams, 2)]
    missing = sum(m - pc[p] for p in allp)
    in_progress = (g.st == "notstarted").any() or g.start_ts.max() >= NOW - 30 * 86400
    if m > 4 or (missing and not in_progress) or (missing > 0.25 * m * len(allp)):
        groups_seen[kind + "_incomplete"] += 1
        continue
    groups_seen[kind + "_ok"] += 1
    group_meta.append(dict(ut=ut, season=season, tid=tid, n=n, m=m, nat=nat, ko=(key_ut, season) in ko_utseason,
                           missing=missing, last=g.start_ts.max()))
    inferred = []
    for p in allp:
        x, y = tuple(p)
        inferred += [(x, y)] * (m - pc[p])
    if nat:
        rule, h2h_first = NATIONAL[ut]
        bounds = national_bounds(rule, n, g.tname.iloc[0])
    else:
        zone = 3 if n <= 16 else 4
        bounds, h2h_first = [1, n - zone], False
    g = g.sort_values("start_ts")
    ev = list(g.itertuples())
    total_rounds = m * (n - 1)
    for r in ev:
        if r.st != "finished":
            continue
        per = period(r.start_ts)
        if per is None:
            continue
        before = [x for x in ev if x.st == "finished" and x.start_ts < r.start_ts]
        pts = {t: 0 for t in teams}
        played_n = Counter()
        for x in before:
            h, a, hg, ag = int(x.hid), int(x.aid), int(x.hg), int(x.ag)
            pts[h] += 3 if hg > ag else 1 if hg == ag else 0
            pts[a] += 3 if ag > hg else 1 if hg == ag else 0
            played_n[h] += 1
            played_n[a] += 1
        others = [(int(x.hid), int(x.aid)) for x in ev
                  if not (x.st == "finished" and x.start_ts < r.start_ts) and x.event_id != r.event_id] + inferred
        h2h = H2H([(int(x.hid), int(x.aid), int(x.hg), int(x.ag)) for x in before], m) if h2h_first else None
        mt = (int(r.hid), int(r.aid))
        st = {}
        tb = {}
        for side, sid in (("home", mt[0]), ("away", mt[1])):
            st[side], tb[side] = final_state(pts, others, mt, sid, bounds, h2h)
        left = {s: total_rounds - played_n[t] for s, t in (("home", mt[0]), ("away", mt[1]))}
        sp = stats.get(int(r.event_id))
        rows.append(dict(
            event_id=int(r.event_id), ko=(key_ut, season) in ko_utseason, m=m, ts=r.start_ts, period=per, nat=nat, ut=ut, ut_name=r.ut_name,
            tname=r.tname, women=(r.gender == "F"), n=n, exact=len(others) <= 8,
            home=st["home"], away=st["away"], tb_home=tb["home"], tb_away=tb["away"],
            left_home=left["home"], left_away=left["away"],
            progress=sum(played_n.values()) / (n * total_rounds),
            has_stats=bool(sp and sp[0]), corners=bool(sp and sp[1]), shots=bool(sp and sp[2]),
            cards=bool(sp and sp[3]), fouls=bool(sp and sp[4])))
out = pd.DataFrame(rows)
out.to_pickle(f"{S}/states.pkl")
pd.DataFrame(group_meta).to_pickle(f"{S}/groups.pkl")
print(groups_seen)
print(len(out))
