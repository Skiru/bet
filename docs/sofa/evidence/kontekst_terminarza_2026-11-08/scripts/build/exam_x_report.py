"""r3 step 8 - outcome-free exam X report (no y store is opened).

 1. Football exam rows (2026-01..10; non-national, coverage both sides):
    group `goals` (full/exam/rows, goals_for / goals_1h_for / goals_2h_for at
    fb.book_for) and `football_result` (full/exam/forecasts, rating book
    fb.book_for("result_1x2"), goals_for side_a / side_b centres -> 2 rows a
    match): per column of fb.COLS the share of rows with the own column = 1,
    per month; exposed row counts per group x column.
    Tennis exam X (tennis/tw_exam_X.pkl, best_of 3): shares of
    max_games78 >= 3, max_layoff21 >= 1, max_ret14 >= 1, coverage, per tier.
 2. Live vs replay exposure: live = football fixtures of runs/sofa/<d>/03_samples.json
    (sport from 02_fixtures.json), d = 2026-10-02..2026-10-31; replay = football_features
    events of the same UTC days with a goals_for row (book fb.book_for) in full/exam/rows.
    Per side shares of the rest buckets and flags, |live - replay| > 3 pp flagged.
    Missing-feature reasons from 02_fixtures + the DB copy (only status.type /
    national / presence are extracted in SQL - no score leaves the DB).

Outputs desc/exam_x_report.md + .json.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pickle
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

D = Path("/Users/mkoziol/projects/bet/data/refit_2026-11-08_schedule")
REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(D)]
import fb_analysis as fb  # noqa: E402
from bet.sofa.comparability import FRIENDLY_COMPETITION_IDS  # noqa: E402

OUT = D / "desc"
EXAM_FROM = int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp())
EXAM_TO = int(dt.datetime(2026, 11, 1, tzinfo=dt.UTC).timestamp())
LIVE_DAYS = [dt.date(2026, 10, 2) + dt.timedelta(days=i) for i in range(30)]
TOL = 0.03
BUCKETS = ["R1", "R2", "R3", "R4_intl", "R4_other", "R5_season_start", "R5_winter",
           "R5_other", "cont_prev4", "cont_prev4_x_R1", "et_prev", "dense14", "cont_next4"]


def month(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m")


def day(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%d")


def side_cols(sf) -> dict[str, int]:  # type: ignore[no-untyped-def]
    ind = sf.indicators()
    out = {b: ind[b] for b in BUCKETS if b in ind}
    out["R3"] = int(sf.coverage and sf.rest_bucket == "R3")
    return out


def part1(feats: dict) -> tuple[dict, set[int]]:
    goals = set(fb.GROUPS["goals"])
    tally: dict = {"goals": defaultdict(lambda: defaultdict(int)),
                   "football_result": defaultdict(lambda: defaultdict(int))}
    per_metric = defaultdict(lambda: defaultdict(int))
    drops = Counter()
    replay_goals_for: set[int] = set()
    for r in fb.read_chunks("exam", "rows"):
        (eid, ts, comp, sport, market, subject, book, n, mean, var, shrunk, final,
         phase, disp, emp, rp, sample, home, away, nr) = r
        if sport != "football" or market not in goals or book != fb.book_for(market):
            continue
        if not (EXAM_FROM <= ts < EXAM_TO):
            drops["goals:outside exam"] += 1
            continue
        f = feats.get(eid)
        if f is None:
            drops["goals:no features"] += 1
            continue
        if f["national"]:
            drops["goals:national"] += 1
            continue
        side = "home" if int(subject) == home else "away" if int(subject) == away else None
        if side is None:
            drops["goals:no side"] += 1
            continue
        if not (f["home"].coverage and f["away"].coverage):
            drops["goals:no coverage"] += 1
            continue
        if market == "goals_for":
            replay_goals_for.add(eid)
        cols = side_cols(f[side])
        for key in (month(ts), "all"):
            t = tally["goals"][key]
            t["rows"] += 1
            for c, v in cols.items():
                t[c] += v
        pm = per_metric[market]
        pm["rows"] += 1
        for c, v in cols.items():
            pm[c] += v
    book = fb.book_for("result_1x2")
    for p in sorted((D / "full/exam/forecasts").glob("*.pkl.gz")):
        import gzip
        for rec in pickle.load(gzip.open(p)):
            eid, ts, comp, home, away, bk, cents, sup = rec
            if bk != book or not cents:
                continue
            lh, la = cents.get(("goals_for", "side_a")), cents.get(("goals_for", "side_b"))
            if lh is None or la is None or not (EXAM_FROM <= ts < EXAM_TO):
                continue
            f = feats.get(eid)
            if f is None:
                drops["result:no features"] += 1
                continue
            if f["national"]:
                drops["result:national"] += 1
                continue
            if not (f["home"].coverage and f["away"].coverage):
                drops["result:no coverage"] += 1
                continue
            for side in ("home", "away"):
                cols = side_cols(f[side])
                for key in (month(ts), "all"):
                    t = tally["football_result"][key]
                    t["rows"] += 1
                    for c, v in cols.items():
                        t[c] += v
    res = {"book_result": book, "drops": dict(drops),
           "groups": {g: {k: dict(v) for k, v in sorted(t.items())} for g, t in tally.items()},
           "goals_per_metric": {m: dict(v) for m, v in per_metric.items()}}
    return res, replay_goals_for


def tennis() -> dict:
    x = pickle.loads((D / "tennis/tw_exam_X.pkl").read_bytes())
    by = defaultdict(lambda: Counter())
    for r in x:
        if r["best_of"] != 3:
            continue
        s = r["sched"]
        for t in (r["tier"], "all"):
            c = by[t]
            c["matches"] += 1
            cov = s["coverage"] == 1.0
            c["coverage"] += cov
            c["games78>=3"] += s["max_games78"] >= 3.0
            c["layoff21"] += s["max_layoff21"] >= 1.0
            c["ret14"] += s["max_ret14"] >= 1.0
            if cov:
                c["cov:games78>=3"] += s["max_games78"] >= 3.0
                c["cov:layoff21"] += s["max_layoff21"] >= 1.0
                c["cov:ret14"] += s["max_ret14"] >= 1.0
    return {t: dict(c) for t, c in sorted(by.items())}


def part2(feats: dict, replay_eids: set[int]) -> dict:
    live: dict[int, dict] = {}
    missing_days = []
    for d in LIVE_DAYS:
        ds = d.isoformat()
        ps, pf = REPO / f"runs/sofa/{ds}/03_samples.json", REPO / f"runs/sofa/{ds}/02_fixtures.json"
        if not ps.exists() or not pf.exists():
            missing_days.append(ds)
            continue
        fx = {f["sofascore_event_id"]: f for f in json.loads(pf.read_text())}
        for s in json.loads(ps.read_text()):
            eid = s["sofascore_event_id"]
            f = fx.get(eid)
            if f is None or f.get("sport") != "football":
                continue
            live.setdefault(eid, {**{k: f.get(k) for k in (
                "kickoff_utc", "competition_id", "national_teams", "sofascore_status")},
                "day": ds, "readiness": s.get("readiness")})
    # missing-feature reasons (SQL extracts status / national / presence only)
    miss = [e for e in live if e not in feats]
    conn = sqlite3.connect(f"file:{D / 'sofa_copy.db'}?mode=ro", uri=True)
    db = {}
    for i in range(0, len(miss), 500):
        chunk = miss[i:i + 500]
        q = ("SELECT event_id, json_extract(event_json, '$.status.type'), "
             "json_extract(event_json, '$.homeTeam.national'), "
             "json_extract(event_json, '$.awayTeam.national') FROM sofa_listed_event "
             f"WHERE sport = 'football' AND event_id IN ({','.join('?' * len(chunk))})")
        for eid, st, hn, an in conn.execute(q, chunk):
            db[eid] = (st, bool(hn) or bool(an))
    reasons = Counter()
    for e in miss:
        lv = live[e]
        r = []
        if lv["national_teams"]:
            r.append("national (02_fixtures)")
        if lv["competition_id"] in FRIENDLY_COMPETITION_IDS:
            r.append("friendly competition")
        if e not in db:
            r.append("not in sofa_listed_event (DB copy)")
        else:
            st, nat = db[e]
            if st != "finished":
                r.append(f"status {st} in DB copy")
            if nat and not lv["national_teams"]:
                r.append("national (DB copy)")
        reasons[" + ".join(r) if r else "unexplained"] += 1
    # populations: sides of matches with features, non-national, both covered
    def tally(eids):  # type: ignore[no-untyped-def]
        c = Counter()
        nm = 0
        for e in eids:
            f = feats[e]
            if f["national"] or not (f["home"].coverage and f["away"].coverage):
                continue
            nm += 1
            for s in ("home", "away"):
                for k, v in side_cols(f[s]).items():
                    c[k] += v
        return nm, c
    live_feat = [e for e in live if e in feats]
    live_nat = sum(1 for e in live_feat if feats[e]["national"])
    live_friendly = sum(1 for e in live_feat if feats[e]["friendly"])
    live_nocov = sum(1 for e in live_feat if not feats[e]["national"]
                     and not (feats[e]["home"].coverage and feats[e]["away"].coverage))
    days = {d.isoformat() for d in LIVE_DAYS} - set(missing_days)
    replay = [e for e, f in feats.items() if day(f["ts"]) in days and e in replay_eids]
    nl, cl = tally(live_feat)
    nr, cr = tally(replay)
    rows = {}
    flags = []
    for b in BUCKETS:
        sl, sr = cl[b] / (2 * nl) if nl else math.nan, cr[b] / (2 * nr) if nr else math.nan
        se = math.sqrt(sl * (1 - sl) / (2 * nl)) if nl else math.nan
        rows[b] = {"live_sides": cl[b], "live_share": sl, "replay_sides": cr[b],
                   "replay_share": sr, "diff_pp": 100 * (sl - sr), "live_se_pp_naive": 100 * se}
        if abs(sl - sr) > TOL:
            flags.append(b)
    overlap = len(set(live_feat) & set(replay))
    return {"missing_days": missing_days, "live_fixtures": len(live),
            "live_ready": sum(1 for v in live.values() if v["readiness"] == "READY"),
            "live_with_features": len(live_feat), "live_no_features": len(miss),
            "no_feature_reasons": dict(reasons), "live_features_national": live_nat,
            "live_features_friendly": live_friendly, "live_features_no_coverage": live_nocov,
            "live_matches_compared": nl, "replay_matches_compared": nr,
            "live_in_replay": overlap, "buckets": rows, "over_3pp": flags}


def md(p1: dict, tn: dict, p2: dict) -> str:
    L = ["# Exam X report (outcome-free) - r3 step 8", "",
         f"Generated {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%MZ} by `desc/exam_x_report.py`. "
         "No outcome store opened.", "",
         "## 1. Football exam rows (2026-01..10, non-national, coverage both sides)", "",
         f"`goals`: full/exam/rows goals_for / goals_1h_for / goals_2h_for at `fb.book_for`; "
         f"`football_result`: full/exam/forecasts rating book {p1['book_result']}, 2 rows a match "
         "(goals_for centre of each side). Share = rows with the OWN column = 1.", "",
         f"Dropped rows: {p1['drops']}", ""]
    for g, t in p1["groups"].items():
        months = [k for k in t if k != "all"] + ["all"]
        L += [f"### {g}", "", "| col | " + " | ".join(months) + " |",
              "|---|" + "---|" * len(months)]
        L.append("| rows | " + " | ".join(str(t[m]["rows"]) for m in months) + " |")
        for c in BUCKETS:
            L.append(f"| {c} | " + " | ".join(f"{100 * t[m].get(c, 0) / t[m]['rows']:.2f}%"
                                               for m in months) + " |")
        L += ["", f"Exposed rows (own col = 1), {g}, all months: "
              + ", ".join(f"{c} {t['all'].get(c, 0)}" for c in BUCKETS), ""]
    L += ["Per goals metric (rows / exposed own): "]
    for m, v in p1["goals_per_metric"].items():
        L.append(f"- {m}: rows {v['rows']}; " + ", ".join(f"{c} {v.get(c, 0)}" for c in BUCKETS))
    L += ["", "### Tennis exam X (tw_exam_X.pkl, best of three; max over the two players)", "",
          "| tier | matches | coverage | games78>=3 | layoff21 | ret14 | among covered: games78>=3 | layoff21 | ret14 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for t, c in tn.items():
        m, cv = c["matches"], max(c["coverage"], 1)
        L.append(f"| {t} | {m} | {100 * c['coverage'] / m:.2f}% | {100 * c['games78>=3'] / m:.2f}% | "
                 f"{100 * c['layoff21'] / m:.2f}% | {100 * c['ret14'] / m:.2f}% | "
                 f"{100 * c.get('cov:games78>=3', 0) / cv:.2f}% | {100 * c.get('cov:layoff21', 0) / cv:.2f}% | "
                 f"{100 * c.get('cov:ret14', 0) / cv:.2f}% |")
    L += ["", "## 2. Live vs replay exposure (2026-10-02..2026-10-31)", "",
          f"Missing days: {p2['missing_days'] or 'none'}. Live football fixtures in 03_samples: "
          f"{p2['live_fixtures']} (READY {p2['live_ready']}); with features {p2['live_with_features']}; "
          f"without {p2['live_no_features']}.", "",
          f"No-feature reasons: {p2['no_feature_reasons']}", "",
          f"Of those with features: national {p2['live_features_national']}, friendly "
          f"{p2['live_features_friendly']}, non-national without coverage of both sides "
          f"{p2['live_features_no_coverage']}.", "",
          f"Compared (non-national, both covered): live {p2['live_matches_compared']} matches, replay "
          f"{p2['replay_matches_compared']} matches (exam goals_for rows, same UTC days); live matches also in "
          f"the replay set: {p2['live_in_replay']}. Shares are per side (2 per match).", "",
          "| bucket | live sides | live | replay sides | replay | diff pp | live SE pp (naive) | > 3 pp |",
          "|---|---|---|---|---|---|---|---|"]
    for b, v in p2["buckets"].items():
        L.append(f"| {b} | {v['live_sides']} | {100 * v['live_share']:.2f}% | {v['replay_sides']} | "
                 f"{100 * v['replay_share']:.2f}% | {v['diff_pp']:+.2f} | {v['live_se_pp_naive']:.2f} | "
                 f"{'**YES**' if b in p2['over_3pp'] else ''} |")
    L += ["", f"Buckets over the 3 pp tolerance: {p2['over_3pp'] or 'none'}. The naive SE ignores "
          "clustering of the two sides of one match.", ""]
    return "\n".join(L)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    p1, replay_eids = part1(feats)
    tn = tennis()
    p2 = part2(feats, replay_eids)
    (OUT / "exam_x_report.json").write_text(json.dumps(
        {"football": p1, "tennis": tn, "live_vs_replay": p2}, indent=1, default=str))
    text = md(p1, tn, p2)
    (OUT / "exam_x_report.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
