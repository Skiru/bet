"""Step 6: secondary markets on history, same walk-forward as s04. For games of the competitions
where Superbet posts 633 'Wszystkie tercje powyżej 0.5 gola' (Liiga 134, SHL 261, NLA 128, CHL 494,
Extraliga 237, DEL 225) and 643/666 extra (AHL 844): P(every period >= 1 goal) from the sims;
P1 first-goal probabilities from the model's P1 means (two Poisson processes: P(no goal) = exp(-m),
P(team1 first) = m1/m (1 - exp(-m))); real period scores."""
import pickle, sys, time, math, resource
from bet.sofa import sport_confidence as scf
from bet.sofa.shadow import SPORTS
from bet.sofa.score_model import build_model, SimParams, late_goal_in_mean_params, _rated_values
EV, OUT, START, END = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
COMPS = {134, 261, 128, 494, 237, 225, 844}
sp = SPORTS['hockey']
history = scf.parse_history(pickle.load(open(EV, 'rb')), sp)
start_ts, end_ts = scf.day_ts(START), scf.day_ts(END)
ratings = [g.rating for g in history]
window = [g for g in history if start_ts <= g.rating.ts < end_ts]
params = late_goal_in_mean_params(SimParams(), 'hockey', False)
model, next_rebuild, out, i = None, start_ts, [], 0
while i < len(window):
    ts = window[i].rating.ts
    j = i
    while j < len(window) and window[j].rating.ts == ts:
        j += 1
    batch = window[i:j]
    if model is None or ts >= next_rebuild:
        model = build_model(ratings, sp, ts, params, shared_league_link=True, strict_league_rate=True)
        next_rebuild = ts + scf.REBUILD_DAYS * 86400
    for g in batch:
        r = g.rating
        if g.result is None or r.competition_id not in COMPS:
            continue
        exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
        if exp is None:
            continue
        sims = model.simulate(exp[0], exp[1], seed=r.event_id, n=1000)
        allp = sum(1 for s in sims if all(a + b >= 1 for a, b in zip(s.t1_periods, s.t2_periods))) / len(sims)
        m1, m2 = exp[0][0], exp[1][0]
        m = m1 + m2
        res = g.result
        out.append({'event_id': r.event_id, 'ts': r.ts, 'comp': r.competition_id,
                    'p_all_periods': allp, 'p1_none': math.exp(-m), 'p1_t1_first': m1 / m * (1 - math.exp(-m)),
                    'p1_t2_first': m2 / m * (1 - math.exp(-m)),
                    'periods': (res.t1_periods, res.t2_periods)})
    for g in batch:
        model.book.update(_rated_values(g.rating, sp))
        model.note_game(g.rating)
        if model.last_played is not None:
            model.last_played[g.rating.home_id] = g.rating.ts
            model.last_played[g.rating.away_id] = g.rating.ts
    i = j
pickle.dump(out, open(OUT, 'wb'))
print('rows', len(out), 'maxrss GB', round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 2))
