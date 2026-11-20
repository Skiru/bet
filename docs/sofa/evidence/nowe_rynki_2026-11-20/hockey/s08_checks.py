"""Adversarial checks.
(1) Grade every offered side a second way: shadow.build_result on the cached Sofascore /event detail
    (sofa_event_detail, allow_final_only=True as SHADOW_SETTLE) + shadow.actual_value / grade with the four
    markets registered IN-PROCESS as scope "full" specs (617 total, 621/653 team totals, 613 handicap) -
    compared with s06's y. Also shadow.line_probability on a one-game replay is not possible offline, so
    p is re-derived on 5 games by re-building the joint from line_probability over synthetic GameResults.
(2) NHL tie rate re-derived from raw payloads (status AET/AP vs Ended level) in the walk's window.
(3) Probe (not a proposal): tie cells of the joint scaled by k fitted on 2024-25, tested 2025-26..2026-27."""
import pickle, sys, json, sqlite3, collections, math, re
import numpy as np
from bet.sofa import shadow
from bet.sofa.shadow import SPORTS, ShadowLine, MarketSpec, GameResult
S = sys.argv[1]
A = pickle.load(open(f'{S}/analysis.pkl', 'rb'))
R = pickle.load(open(f'{S}/results.pkl', 'rb'))
W = pickle.load(open(f'{S}/walk.pkl', 'rb'))
sp = SPORTS['hockey']
shadow.MARKETS['hockey'].update({
    617: MarketSpec('total_incl', 'total', 'full'),
    621: MarketSpec('team_total_incl', 'team_total', 'full', team='T1'),
    653: MarketSpec('team_total_incl', 'team_total', 'full', team='T2'),
    613: MarketSpec('handicap_incl', 'handicap', 'full')})
con = sqlite3.connect('file:data/sofa.db?mode=ro', uri=True)
results = {}
for eid, r in R.items():
    if r['state'] != 'SETTLED': continue
    det = json.loads(con.execute('select detail_json from sofa_event_detail where sofascore_event_id=?', (r['sofascore_event_id'],)).fetchone()[0])
    det = det.get('event', det)
    results[eid] = shadow.build_result(det, sp, bool(r['home_is_team1']), allow_final_only=True)
agree = collections.Counter()
for l in A['legs']:
    res = results[l['eid']]
    if l['m'] == 613:
        side = 'T1' if l['name'].rsplit(' (', 1)[0] == R[l['eid']]['team1'] else 'T2'
        ln = ShadowLine(l['eid'], 613, 'handicap_incl', 0, '', l['L'], side, l['odds'])
    else:
        subj = {617: '', 621: 'T1', 653: 'T2'}[l['m']]
        ln = ShadowLine(l['eid'], l['m'], 'x', 0, subj, l['L'], l['side'], l['odds'])
    act = shadow.actual_value(ln, res, sp)
    out = shadow.grade(ln, act)
    agree[(l['m'], (out == 'WIN') == bool(l['y']))] += 1
print('(1) grading via shadow.build_result/actual_value vs s06 y:', dict(agree))
# p re-derived: line_probability over GameResults rebuilt from the stored joint (5 games)
nhl = {w['event_id']: w for w in W if w['nhl'] and not w.get('no_p')}
maxdiff = 0.0
checked = 0
for l in A['legs'][:400:20]:
    w = nhl[R[l['eid']]['sofascore_event_id']]
    if not R[l['eid']]['home_is_team1']: continue
    games = []
    for (a, b, o), c in w['joint'].items():
        g = GameResult((a, 0, 0), (b, 0, 0), a + (o == 1), b + (o == 2), None if o == 0 and a == b else ('T1' if (o == 1 or a > b) else 'T2'), o > 0)
        games += [g] * c
    if l['m'] == 613:
        side = 'T1' if l['name'].rsplit(' (', 1)[0] == R[l['eid']]['team1'] else 'T2'
        ln = ShadowLine('', 613, 'h', 0, '', l['L'], side, 1.0)
    else:
        ln = ShadowLine('', l['m'], 'x', 0, {617: '', 621: 'T1', 653: 'T2'}[l['m']], l['L'], l['side'], 1.0)
    p2 = shadow.__dict__.get('line_probability')
    from bet.sofa.score_model import line_probability
    p2 = line_probability(ln, games, sp)
    maxdiff = max(maxdiff, abs(p2 - l['p'])); checked += 1
print(f'    p via score_model.line_probability on {checked} sides: max |diff| {maxdiff:.2e}')
# (2) tie rate from raw payloads
ev = pickle.load(open(f'{S}/hockey_events.pkl', 'rb'))
ids = {w['event_id'] for w in W if w['nhl']}
c = collections.Counter()
for i in ids:
    e = ev[i]; d = e['status']['description']
    H, Aw = e['homeScore'], e['awayScore']
    c[d in ('AET', 'AP')] += 1
    c['nt_level'] += int(H.get('normaltime') == Aw.get('normaltime'))
print(f"(2) raw payloads, the {len(ids)} NHL games of the walk: AET/AP {c[True]} = {c[True]/len(ids):.4f}; normaltime level {c['nt_level']/len(ids):.4f}")
del ev
# (3) tie inflation probe
rows = [w for w in W if w['nhl'] and not w.get('no_p')]
import time
def season(ts):
    y, m = time.gmtime(ts).tm_year, time.gmtime(ts).tm_mon
    return y if m >= 8 else y - 1
def scaled(w, k):
    j = {key: c * (k if key[0] == key[1] else 1.0) for key, c in w['joint'].items()}
    t = sum(j.values()); return {key: c / t for key, c in j.items()}
dev = [w for w in rows if season(w['ts']) == 2024]; test = [w for w in rows if season(w['ts']) >= 2025]
pt_dev = np.mean([sum(c for k_, c in w['joint'].items() if k_[0] == k_[1]) / w['n'] for w in dev]); rt_dev = np.mean([w['reg'][0] == w['reg'][1] for w in dev])
# k such that mean scaled tie = realised on dev (solve by bisection)
lo, hi = 1.0, 2.0
for _ in range(40):
    k = (lo + hi) / 2
    m = np.mean([sum(c for key, c in scaled(w, k).items() if key[0] == key[1]) for w in dev])
    lo, hi = (k, hi) if m < rt_dev else (lo, k)
print(f"(3) dev 2024-25: model tie {pt_dev:.4f}, realised {rt_dev:.4f}, k {k:.3f}")
def ll_lines(w, j):
    out = []
    ff, rr = w['full'], w['reg']
    for L in (4.5, 5.5, 6.5, 7.5):
        p = sum(c for (a, b, o), c in j.items() if a + b + (o > 0) > L)
        out.append(('total_incl', p, int(sum(ff) > L)))
    for L in (1.5, 2.5, 3.5):
        for t in (0, 1):
            p = sum(c for (a, b, o), c in j.items() if ((a + (o == 1)) if t == 0 else (b + (o == 2))) > L)
            out.append(('team_incl', p, int(ff[t] > L)))
    p = sum(c for (a, b, o), c in j.items() if a == b)
    out.append(('tie', p, int(rr[0] == rr[1])))
    return out
rng = np.random.default_rng(3)
for fam in ('total_incl', 'team_incl', 'tie'):
    diffs = []
    for w in test:
        base = {key: c / w['n'] for key, c in w['joint'].items()}
        a = [x for x in ll_lines(w, base) if x[0] == fam]; b = [x for x in ll_lines(w, scaled(w, k)) if x[0] == fam]
        f = lambda p, y: -math.log(max(p if y else 1 - p, 1e-6))
        diffs.append(np.mean([f(pb, y) - f(pa, y) for (_, pa, y), (_, pb, _) in zip(a, b)]))
    diffs = np.array(diffs)
    bs = [diffs[rng.integers(0, len(diffs), len(diffs))].mean() for _ in range(2000)]
    print(f"    test 2025-27 {fam}: logloss scaled - base {diffs.mean():+.5f} [{np.percentile(bs,2.5):+.5f}, {np.percentile(bs,97.5):+.5f}] (n games {len(diffs)})")
