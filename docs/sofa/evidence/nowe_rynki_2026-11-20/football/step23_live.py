"""Steps 2-3 on 11-06..11-19: grade every candidate selection from SETTLE's 90-minute / period1 reading and
price it from the simulator's joint score path (walk-forward pure rating centres, see live_centres.py)."""
import gzip, json, pickle, sqlite3, sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
sys.path[:0] = ["src", ".", str(Path(__file__).parent)]
from cands import parse
from bet.sofa import football_sim_markets as fsm
from bet.sofa.metrics import regulation_score
from bet.sofa.settle import is_completed_event, settle_completed

_FC = None
def _init(path):
    global _FC
    _FC = pickle.load(open(path, "rb"))
def job(e):
    from simcore import joint
    return e, joint(e, _FC.get(e))

def main():
    S = Path(sys.argv[1])
    rows = [json.loads(l) for l in gzip.open(S / "cand_rows.jsonl.gz", "rt")]
    fc = pickle.load(open(S / "centres_live_1106_1119.pkl", "rb"))
    eids = sorted({r["eid"] for r in rows})
    # --- grading: SETTLE's sim reader decides gradeability; ht / ft as it reads them
    con = sqlite3.connect("file:data/sofa.db?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    grade = {}
    if (S / "live_grades.json").exists():
        grade = {int(k): v for k, v in json.load(open(S / "live_grades.json")).items()}
    for i in ([] if grade else range(0, len(eids), 400)):
        ch = eids[i:i + 400]
        q = ",".join("?" * len(ch))
        det = dict(con.execute(f"SELECT sofascore_event_id, detail_json FROM sofa_event_detail WHERE sofascore_event_id IN ({q})", ch))
        inc = dict(con.execute(f"SELECT sofascore_event_id, incidents_json FROM sofa_event_stats WHERE sofascore_event_id IN ({q})", ch))
        for e in ch:
            d = det.get(e)
            ev = (json.loads(d) or {}).get("event") if d else None
            if not ev:
                grade[e] = "NO_EVENT"; continue
            st = (ev.get("status") or {}).get("type")
            if not is_completed_event(ev):
                grade[e] = f"NOT_COMPLETED:{st}:{(ev.get('status') or {}).get('code')}"; continue
            if not settle_completed(ev):
                grade[e] = "AWARDED"; continue
            i_js = inc.get(e)
            incidents = json.loads(i_js) if i_js else None
            v = fsm.sim_value(fsm.HTFT, "1/1", ev, incidents if isinstance(incidents, dict) else None)
            if isinstance(v, str):
                grade[e] = v; continue
            sc = regulation_score(ev)
            ht = (int(ev["homeScore"]["period1"]), int(ev["awayScore"]["period1"]))
            ft = (int(sc[0]), int(sc[1]))
            et = (ev.get("status") or {}).get("code") in (110, 120)
            grade[e] = {"ht": ht, "ft": ft, "et": bool(et)}
    con.close()
    json.dump({str(k): v for k, v in grade.items()}, open(S / "live_grades.json", "w"))
    # --- price
    from simcore import joint, p_of
    with Pool(4, initializer=_init, initargs=(str(S / "centres_live_1106_1119.pkl"),)) as pool:
        J = dict(pool.map(job, eids, chunksize=16))
    recs_by = {}
    for line in gzip.open(S / "cand_prices.jsonl.gz", "rt"):
        r = json.loads(line)
        recs_by[(r["eid"], r["marketName"], r["name"], r["sbv"])] = r
    out = []
    cov = defaultdict(Counter)
    for r in rows:
        rec = recs_by[(r["eid"], r["marketName"], r["name"], r["sbv"])]
        cand, gk, label, held = parse(rec)
        g = grade.get(r["eid"])
        j = J.get(r["eid"])
        p = p_of(j, held) if j is not None else None
        y = None
        if isinstance(g, dict):
            h1, a1 = g["ht"]; h2, a2 = g["ft"][0] - h1, g["ft"][1] - a1
            v = held(h1, a1, h2, a2)
            y = "REFUND" if v is None else int(v)
            cov[cand]["graded" if v is not None else "refund"] += 1
        else:
            cov[cand][f"ungraded:{g}"] += 1
        if p is None:
            cov[cand]["no_centres"] += 1
        out.append({**r, "p_sim": None if p is None else round(p, 5), "y": y, "et": g.get("et") if isinstance(g, dict) else None})
    with gzip.open(S / "live_eval.jsonl.gz", "wt") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(cov, open(S / "step2_coverage.json", "w"), indent=1)
    for c, v in sorted(cov.items()):
        tot = sum(x for k, x in v.items() if k != "no_centres")
        print(c, f"graded {v['graded'] / tot:.3f}", dict(v.most_common(8)))
    print("event grade reasons", Counter(g if isinstance(g, str) else ("ET" if g["et"] else "OK") for g in grade.values()).most_common(12))

if __name__ == '__main__':
    main()
