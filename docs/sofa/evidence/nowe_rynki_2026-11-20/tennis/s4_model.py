"""Step 4: price every N+ selection with the point model exactly as SHEET
does (run_sheet.load_point_pricer: load_point_history -> fixture_match ->
forecast_fixtures -> PointPricer, 4,000 sims seeded by event id), as of each
fixture's start. p(N+) = P(count > N - 0.5) = PointPricer.p(..., 'OVER')."""
import json, sys, time, pickle, resource
from datetime import datetime
sys.path.insert(0, 'src')
from bet.sofa import tennis_point_sheet as tps
from bet.sofa.tennis_point_model import load_point_history

D = sys.argv[1]
meta = json.load(open(f'{D}/events_meta.json'))
chk = json.load(open(f'{D}/check_old.json'))
meta_all = dict(meta); meta_all.update(chk['fixtures'])
t0 = time.time()
history = load_point_history('data/sofa.db')
pickle.dump(history, open(f'{D}/history.pkl', 'wb'))
print('history', len(history), round(time.time() - t0), 's', 'maxrss GB',
      resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, flush=True)
female_of = tps.female_by_player(history)
matches = []
notrated = {}
for sid, e in meta_all.items():
    ko = datetime.fromisoformat(e['kickoff'].replace('Z', '+00:00'))
    m = tps.fixture_match(int(sid), ko, e['home_id'], e['away_id'], e['cat'], e['ground'],
                          e['comp_id'], e['bo'], female_of)
    if m is None:
        notrated[sid] = 'NOT_RATED'
    else:
        matches.append(m)
fc = tps.forecast_fixtures(history, matches)
print('forecasts', len(fc), 'not rated', len(notrated), round(time.time() - t0), 's', flush=True)
pickle.dump(fc, open(f'{D}/forecasts.pkl', 'wb'))
del history
pricer = tps.PointPricer(fc)
out = open(f'{D}/priced.jsonl', 'w')
for line in open(f'{D}/graded.jsonl'):
    r = json.loads(line)
    side = None if r['side'] is None else (0 if r['side'] else 1)
    p = pricer.p(int(r['sid']), r['metric'], side, r['n'] - 0.5, 'OVER')
    r['p'] = p
    c = pricer.centre(int(r['sid']), r['metric'], side)
    r['model_mean'] = None if c is None else round(c[0], 3)
    f = fc.get(int(r['sid']))
    r['female'] = None if f is None else None
    out.write(json.dumps(r) + '\n')
out.close()
# check: reproduce SHEET's p_central of old-format rows (11-12..11-19)
diffs = []
for rd, sid, m, subj, line, d, pc in chk['rows']:
    e = chk['fixtures'].get(str(sid))
    if e is None: continue
    side = None
    if m.endswith('_for'):
        from bet.sofa.market_mapper import fold
        side = 0 if fold(subj) == fold(e['home']) else 1 if fold(subj) == fold(e['away']) else None
        if side is None: continue
    p = pricer.p(int(sid), m, side, line, d)
    if p is not None: diffs.append(abs(p - pc))
import numpy as np
print('check vs SHEET p_central: n', len(diffs), 'mean |diff|', float(np.mean(diffs)) if diffs else None,
      'max', max(diffs) if diffs else None, 'share <0.005', float(np.mean(np.array(diffs) < 0.005)) if diffs else None)
print('done', round(time.time() - t0), 's', 'maxrss GB', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9)
