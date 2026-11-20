"""Step 4/5: walk-forward replay of the installed hockey score model (score_model.build_model /
ScoreModel.expected / ScoreModel.simulate, today's hockey params: SimParams() defaults, strict league
rate, shared-league link, no shots / empty-net fit / late-goal-in-mean - epochs as of 2026-11-20),
mirroring sport_confidence.walk_forward_rows (rebuild every REBUILD_DAYS, the book updated game by
game, games sharing a start forecast before any is learnt).

For every NHL game (uniqueTournament 234) in [START, END) and a 1-in-THIN sample of other leagues it
stores the simulated joint distribution {(reg1, reg2, ot_winner): count} (home = team1) and the real
result, so every line (regulation or incl. OT/SO) is priced offline from the same sims."""
import pickle, sys, time, collections, dataclasses, resource
from bet.sofa import sport_confidence as scf
from bet.sofa.shadow import SPORTS
from bet.sofa.score_model import (build_model, SimParams, late_goal_in_mean_params, _rated_values)

EV, OUT, START, END = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
THIN = 10
sp = SPORTS['hockey']
events = pickle.load(open(EV, 'rb'))
t0 = time.time()
history = scf.parse_history(events, sp)
del events
print('history', len(history), round(time.time() - t0, 1), 's', flush=True)
start_ts, end_ts = scf.day_ts(START), scf.day_ts(END)
ratings = [g.rating for g in history]
window = [g for g in history if start_ts <= g.rating.ts < end_ts]
params = late_goal_in_mean_params(SimParams(), 'hockey', False)
model = None
next_rebuild = start_ts
out = []
i = 0
nonnhl = 0
while i < len(window):
    ts = window[i].rating.ts
    j = i
    while j < len(window) and window[j].rating.ts == ts:
        j += 1
    batch = window[i:j]
    if model is None or ts >= next_rebuild:
        t1 = time.time()
        model = build_model(ratings, sp, ts, params, shared_league_link=True, strict_league_rate=True,
                            season_restart=False)
        next_rebuild = ts + scf.REBUILD_DAYS * 86400
        print('rebuild', time.strftime('%Y-%m-%d', time.gmtime(ts)), round(time.time() - t1, 1), 's; rows', len(out),
              'rss GB', round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 2), flush=True)
    for g in batch:
        r = g.rating
        if g.result is None:
            continue
        nhl = r.competition_id == 234
        if not nhl:
            nonnhl += 1
            if nonnhl % THIN:
                continue
        exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
        if exp is None:
            out.append({'event_id': r.event_id, 'ts': r.ts, 'comp': r.competition_id, 'nhl': nhl, 'no_p': True})
            continue
        n = 4000 if (nhl and r.ts >= scf.day_ts('2026-10-01')) else (2000 if nhl else 1000)
        sims = model.simulate(exp[0], exp[1], seed=r.event_id, n=n)
        joint = collections.Counter()
        for s in sims:
            r1, r2 = sum(s.t1_periods), sum(s.t2_periods)
            otw = 0 if r1 != r2 else (1 if s.winner == 'T1' else 2)
            # sanity: the simulator's full score is regulation + the OT/SO winner's one goal
            assert (s.t1_full, s.t2_full) == (r1 + (otw == 1), r2 + (otw == 2))
            joint[(r1, r2, otw)] += 1
        res = g.result
        reg = (sum(res.t1_periods), sum(res.t2_periods))
        out.append({'event_id': r.event_id, 'ts': r.ts, 'comp': r.competition_id, 'nhl': nhl,
                    'home': r.home_id, 'away': r.away_id, 'mu': (sum(exp[0]), sum(exp[1])),
                    'joint': dict(joint), 'n': n, 'reg': reg, 'full': (res.t1_full, res.t2_full),
                    'winner': res.winner, 'overtime': res.overtime,
                    'status': (g.event.get('status') or {}).get('description')})
    for g in batch:
        model.book.update(_rated_values(g.rating, sp))
        model.note_game(g.rating)
        if model.last_played is not None:
            model.last_played[g.rating.home_id] = g.rating.ts
            model.last_played[g.rating.away_id] = g.rating.ts
    i = j
pickle.dump(out, open(OUT, 'wb'))
print('done rows', len(out), 'nhl', sum(1 for o in out if o['nhl']), round(time.time() - t0), 's', flush=True)
