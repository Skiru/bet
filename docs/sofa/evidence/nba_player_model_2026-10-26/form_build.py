"""Stage 1: replay basketball player-games (fit_player_model machinery), dump per
(player-game, family) rows: eid, ts, pid, fam, act, exp, sd, p_over_cal, y_over, line, raw5_mean, nown, tournament."""
import sys, sqlite3, json, pickle, statistics, math
sys.path.insert(0, "/Users/mkoziol/projects/bet/scripts/sofa")
import fit_player_model as fp
import bet.sofa.player_model as pm
from bet.sofa.shadow import SPORTS
DB, OUT = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
hist = fp.History.from_db(conn, "basketball", team_from_side=True, any_team=False)
specs = fp.family_specs("basketball")
print("families", [s.family for s in specs], flush=True)
# tournament per event
tour = {}
for eid, text in conn.execute("SELECT event_id, event_json FROM sofa_listed_event WHERE sport=?", (SPORTS["basketball"].sofascore_slug,)):
    try:
        ev = json.loads(text); t = (ev.get("tournament") or {}).get("uniqueTournament") or {}
        tour[int(eid)] = (t.get("id"), t.get("name"))
    except Exception: pass
recs = fp.build_records_parallel(hist, specs, 7)
print("records", len(recs), flush=True)
prm = pm.load_params()["basketball"]
printed = fp.printed_lines("/Users/mkoziol/projects/bet/runs/sofa", "basketball")
KEEP = {"player_points","player_rebounds","player_assists","player_threes","player_pts_reb_ast"}
import multiprocessing
def chunk(idx):
    out = []
    for i in idx:
        r = recs[i]
        for f, spec in enumerate(specs):
            if spec.family not in KEEP: continue
            y = r.act[f]
            if y is None: continue
            got = fp.record_distribution(r, f, spec.family, prm)
            if got is None: continue
            pmf, _ = got
            mean = sum(k*m for k, m in pmf.items()); var = sum(m*(k-mean)**2 for k, m in pmf.items())
            own20 = [v for _, v in fp.family_sample(r, f, fp.LINE_SAMPLE)]
            line = fp.nearest_line(own20, printed.get(spec.family, []))
            s = fp.score_pmf(pmf, y, line)
            p = pm.calibrate_side(s.p_over, prm.calibration_b)
            own = fp.family_sample(r, f, 70)
            raw5 = statistics.fmean([v for _, v in own[:5]]) if len(own) >= 5 else None
            out.append((r.eid, r.ts, r.pid, spec.family, float(y), mean, math.sqrt(var), p, s.y_over, line, raw5, len(own), tour.get(r.eid, (None, None))[0]))
    return out
n = len(recs); chunks = [list(range(j, n, 64)) for j in range(64)]
with multiprocessing.get_context("fork").Pool(7) as pool:
    rows = [x for part in pool.map(chunk, chunks) for x in part]
pickle.dump(rows, open(OUT, "wb"))
print("rows", len(rows))
