"""Offered 'Liczba dogrywek' events: walk-forward model p (no OT) vs Superbet de-vigged price; gates; ROI."""
import json, math, random
ev = {e["sofa"]: e for e in json.load(open("cs2_ot_events.json")) if e.get("sofa") and e.get("graded")}
R = {r["eid"]: r for r in map(json.loads, open("cs2_ot_wf_rows.jsonl"))}
OFFSET = -0.0164  # cs2 sport_printable realised_minus_confidence, config/sofa_superbet_line_evidence.json (before 2026-11-20)
rows = []
for eid, e in ev.items():
    r = R.get(eid)
    if not r: continue
    fu = (1/e["under"]) / (1/e["under"] + 1/e["over"])
    y = 1 - int(e["ot_maps"] > 0)
    assert y == r["y_noot"], (eid, y, r["y_noot"])
    rows.append(dict(eid=eid, p=r["p_race"], pb=r["p_base"], fair=fu, y=y, odds=e["under"], over=e["over"], bo=r["bo"], margin=1/e["under"]+1/e["over"]-1))
def boot(v, reps=4000):
    rng = random.Random(2); n = len(v); s = sorted(sum(v[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return sum(v)/n, s[int(.025*reps)], s[int(.975*reps)-1]
def ll(p, y): return -math.log(p if y else 1-p)
n = len(rows); print("events", n, "bo", {b: sum(r['bo']==b for r in rows) for b in (3,5)})
print("realised Under %.3f, mean model %.3f, mean fair %.3f, mean 1/odds %.3f" % (sum(r['y'] for r in rows)/n, sum(r['p'] for r in rows)/n, sum(r['fair'] for r in rows)/n, sum(1/r['odds'] for r in rows)/n))
print("Brier model - fair %+.4f [%+.4f, %+.4f]" % boot([(r['p']-r['y'])**2-(r['fair']-r['y'])**2 for r in rows]))
print("logloss model - fair %+.4f [%+.4f, %+.4f]" % boot([ll(r['p'],r['y'])-ll(r['fair'],r['y']) for r in rows]))
print("Brier base - fair %+.4f [%+.4f, %+.4f]" % boot([(r['pb']-r['y'])**2-(r['fair']-r['y'])**2 for r in rows]))
print("realised - model %+.3f [%+.3f, %+.3f]" % boot([r['y']-r['p'] for r in rows]))
print("realised - fair %+.3f [%+.3f, %+.3f]" % boot([r['y']-r['fair'] for r in rows]))
# gates with a confidence = p_race + offset (curve ~ identity assumed; see report)
for label, adj in (("conf=p+offset", OFFSET), ("conf=p", 0.0)):
    P = [r for r in rows if r['p']+adj >= 0.70 and (r['p']+adj)*r['odds'] >= 0.90 and r['margin'] <= 0.15]
    if P:
        roi = [r['odds']*r['y']-1 for r in P]
        print(f"{label}: printable {len(P)}/{n}, hit {sum(r['y'] for r in P)/len(P):.3f}, mean 1/odds {sum(1/r['odds'] for r in P)/len(P):.3f}, ROI %+.3f [%+.3f, %+.3f]" % boot(roi),
              " after 12%% tax %+.3f" % (sum(0.88*r['odds']*r['y'] for r in P)/len(P)-1))
# spread of model p vs fair: correlation
import statistics
print("sd model p %.4f, sd fair %.4f, corr %.3f" % (statistics.pstdev([r['p'] for r in rows]), statistics.pstdev([r['fair'] for r in rows]), statistics.correlation([r['p'] for r in rows],[r['fair'] for r in rows])))
