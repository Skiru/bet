"""tennis_games_sets X rows (outcome-free), both arms (doprecyzowanie 6).

usage: tg_build.py validate|exam
Neighbour tables per arm: every rated match before the scored day enters with
its arm p (coefficients: validate - fitted on explore; exam - tw_frozen.json);
scoped cells as AsOfRating / TennisRatingModel (tier_gender, tier, pooled).
Output tennis/tg_<tier>_X.pkl: rows (eid, ts, home, away, tour, market, subject,
side, line, p_base, p_treat). No outcome of a scored row is read.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO), str(REPO / "scripts/sofa"),
                str(REPO / "data/refit_2026-11-08_schedule")]
import tw_analysis as twa  # noqa: E402
from bet.sofa import tennis_rating as tr  # noqa: E402
from bet.sofa.engine import outside_model_resolution  # noqa: E402

D = REPO / "data/refit_2026-11-08_schedule"
T = D / "tennis"
COPY = D / "sofa_copy.db"
MARKETS = {"games_won_for", "games_won_set1_for", "games_won_set2_for",
           "games_won_set3_for"}
tier_name = sys.argv[1]
VAL_FROM = twa.EXPLORE_END
VAL_TO = int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp())
EXAM_TO = int(dt.datetime(2026, 11, 1, tzinfo=dt.UTC).timestamp())
# dev: whole dev window with the FROZEN arms - the rows the P3 dev curves are fitted on
lo, hi = {"validate": (VAL_FROM, VAL_TO), "exam": (VAL_TO, EXAM_TO),
          "dev": (1719792000, VAL_TO)}[tier_name]


def lines_for(centre: float) -> list[float]:
    import calibrate_from_cache as cfc
    return cfc.lines_for(centre)


# arm coefficients
if tier_name == "validate":
    dev = twa.load_dev()
    arms = twa.fit_arms([r for r in dev if r["ts"] < twa.EXPLORE_END])
else:
    fz = json.loads((T / "tw_frozen.json").read_text())
    arms = {a: {t: np.array(v) for t, v in fz[a].items()} for a in ("base", "treat")}

rows_all = (pickle.loads((T / "tw_all_dev.pkl").read_bytes())
            + pickle.loads((T / "tw_all_exam_X.pkl").read_bytes()))
rows_all = [r for r in rows_all if r["tier"] in arms["base"]]
pb, pt = twa.arm_p(arms, rows_all)
p_of = {r["event_id"]: (float(b), float(t), r) for r, b, t in zip(rows_all, pb, pt, strict=True)}
history = tr.load_history(str(COPY), score_winner=True)
print("history", len(history), "rated", len(p_of), flush=True)

# recorded tennis rating rows of the window (X only: no y store is opened)
want: dict[int, list] = defaultdict(list)
tierdir = "exam" if tier_name == "exam" else "dev"
for p in sorted((D / "full" / tierdir / "rows").glob("*.pkl.gz")):
    for rec in pickle.load(gzip.open(p)):
        (eid, ts, comp, sport, market, subject, book, n, mean, var, shrunk, final,
         phase, disp, emp, rp, sample, home, away, nrows) = rec
        if sport == "tennis" and market in MARKETS and rp and lo <= ts < hi:
            want[eid].append((market, subject, final, home, away, ts))
print("scored matches", len(want), flush=True)

models = {a: tr.TennisRatingModel(tr.RatingBook(), {}, [], tr.FEATURES, True)
          for a in ("base", "treat")}
by_day = defaultdict(list)
for eid in want:
    if eid in p_of:
        by_day[want[eid][0][5] // 86400].append(eid)
out = []
hist_i = 0
for day in sorted(by_day):
    cut = day * 86400
    while hist_i < len(history) and history[hist_i].ts < cut:
        r = history[hist_i]
        hist_i += 1
        got = p_of.get(r.event_id)
        if got is None:
            continue
        for a, p in (("base", got[0]), ("treat", got[1])):
            for o in tr._outcomes(r, p):
                models[a].insert(o)
    for eid in by_day[day]:
        b, t, row = p_of[eid]
        fcs = {}
        for a, p in (("base", b), ("treat", t)):
            m = models[a]
            found = m._scoped_cell(row["tier"], bool(row.get("female_flag", row["female"])))
            if found is not None:
                _, cell = found
                fcs[a] = tr.MatchForecast(
                    p_home=p, neighbours_home=tr._window(cell.rows, cell.keys, p),
                    neighbours_away=tr._window(cell.rows, cell.keys, 1 - p),
                    rated_home=0, rated_away=0)
            else:
                full = row["tier"] != "ITF"
                fcs[a] = tr.MatchForecast(
                    p_home=p, neighbours_home=m._neighbours(p, full),
                    neighbours_away=m._neighbours(1 - p, full), rated_home=0, rated_away=0)
        for market, subject, final, home, away, ts in want[eid]:
            side = "side_a" if int(subject) == home else "side_b"
            for line in lines_for(final):
                p0 = fcs["base"].read(market, side, line, "OVER")
                if p0 is None or outside_model_resolution(p0):
                    continue
                p1 = fcs["treat"].read(market, side, line, "OVER")
                out.append((eid, ts, home, away, row["tournament_id"], market, subject,
                            side, line, p0, p0 if p1 is None else p1))
(T / f"tg_{tier_name}_X.pkl").write_bytes(pickle.dumps(out))
print("rows", len(out), flush=True)
