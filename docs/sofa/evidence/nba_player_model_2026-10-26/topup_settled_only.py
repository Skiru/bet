"""Top-up rule for THIN basketball players: own sample (the playing teams' listed games) < MIN_APPEARANCES
-> add the SAME player id's appearances from any other listed non-friendly basketball game before the cutoff (newest first, <=FOREIGN_CAP, each game once).
Foreign appearances enter only that player's own sample (replay_game's foreign path), never the pool. Read-only on data/sofa.db (mode=ro)."""
import sys, json, math, pickle, sqlite3, random, statistics, multiprocessing, glob
from dataclasses import replace
from datetime import datetime, UTC
sys.path.insert(0, "/Users/mkoziol/projects/bet/scripts/sofa")
import fit_player_model as fp
import bet.sofa.player_model as pm
from bet.sofa.shadow import SPORTS
S = "/private/tmp/claude-501/-Users-mkoziol-projects-bet/701c2cc6-a874-47d8-924e-5ecfaf45df41/scratchpad"
FAMS = ["player_points","player_rebounds","player_assists","player_threes","player_pts_reb_ast"]
FOREIGN_CAP = 20
LOG = []
class TopUp(fp.History):
    def foreign_before(self, teams, before_ts, exclude, players):
        own = {}
        for a in self.appearances_before(teams, before_ts, exclude):
            own.setdefault(a.player_id, set()).add(a.event_id)
        out = {}
        for pid in players:
            have = own.get(pid, set()); n_own = len(have); fts = []
            if n_own < pm.MIN_APPEARANCES:
                cand = []
                for e, team in self.player_index.get(pid, ()):
                    ev = self.events.get(e)
                    if ev is None or e == exclude or e in have or ev[0] >= before_ts or e not in self.lineups: continue
                    cand.append((ev[0], e, team))
                cand = sorted(set(cand), reverse=True)[:FOREIGN_CAP]
                for ts, e, team in cand:
                    for a in self.appearances_in(e, team):
                        if a.player_id == pid:
                            out.setdefault(pid, []).append(replace(a, ts=ts, foreign=True)); fts.append(ts)
            LOG.append((exclude, pid, n_own, tuple(fts)))
        return out
if __name__ == "__main__":
    DB = "/Users/mkoziol/projects/bet/data/sofa.db"
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=120)
    hist = fp.History.from_db(conn, "basketball", team_from_side=True, any_team=True); hist.__class__ = TopUp
    base = replace(hist, any_team=False, player_index={}, _cache={}); base.__class__ = fp.History
    tour = {}
    for eid, text in conn.execute("SELECT event_id, event_json FROM sofa_listed_event WHERE sport=?", (SPORTS["basketball"].sofascore_slug,)):
        try: t = (json.loads(text).get("tournament") or {}).get("uniqueTournament") or {}; tour[int(eid)] = t.get("id")
        except Exception: pass
    specs = fp.family_specs("basketball"); fidx = {s.family: i for i, s in enumerate(specs)}; prm = pm.load_params()["basketball"]
    printed = fp.printed_lines("/Users/mkoziol/projects/bet/runs/sofa", "basketball")
    eids = sorted(e for e in hist.lineups if e in hist.events)
    # ---- settled THIN_SAMPLE lines 10-03..10-25
    L = {}
    for fpath in sorted(glob.glob("/Users/mkoziol/projects/bet/runs/sofa/shadow/basketball/*/settled.json")):
        d = json.load(open(fpath))
        if not ("2026-10-03" <= d["date"] <= "2026-10-25"): continue
        for seid, ev in d["events"].items():
            sid = ev.get("sofascore_event_id")
            for g in ev.get("graded", []):
                if g.get("family") in FAMS and g.get("model_p") is None and g.get("model_reason") == "THIN_SAMPLE" and g.get("outcome") in ("WIN","LOSS") and g.get("model_player_id") and sid:
                    L[(seid, g["market_id"], g["subject"], g["line"], g["side"])] = dict(sid=int(sid), day=d["date"], fam=g["family"], pid=int(g["model_player_id"]), line=float(g["line"]), side=g["side"], odds=float(g["odds"]), win=1 if g["outcome"]=="WIN" else 0, nba=(ev.get("sofascore_tournament")=="NBA"), tour=ev.get("sofascore_tournament"))
    print("settled THIN lines (with player id)", len(L), flush=True)
    recs = {}
    for sid in sorted({v["sid"] for v in L.values()}):
        LOG.clear()
        for r in fp.replay_game(hist, sid, specs): recs[(sid, r.pid)] = r
    out = []; nrec = 0
    for k, v in L.items():
        r = recs.get((v["sid"], v["pid"]))
        if r is None: out.append(dict(v, p=None)); continue
        f = fidx[v["fam"]]; got = fp.record_distribution(r, f, v["fam"], prm)
        if got is None: out.append(dict(v, p=None)); continue
        pmf, _ = got; po = min(max(sum(m for kk, m in pmf.items() if kk > v["line"]), 1e-6), 1-1e-6); po = pm.calibrate_side(po, prm.calibration_b)
        out.append(dict(v, p=po if v["side"] == "OVER" else 1-po))
    pickle.dump(out, open(f"{S}/topup_settled.pkl", "wb")); print("settled priced", sum(1 for o in out if o["p"] is not None), "of", len(out))
