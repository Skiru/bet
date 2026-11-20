"""Step 6: 633 'Wszystkie tercje powyżej 0.5 gola' and 643 / 666 first goal, from periods.pkl (s07)."""
import pickle, sys, collections, math
import numpy as np
S = sys.argv[1]
Pp = pickle.load(open(f'{S}/periods.pkl', 'rb'))
D = pickle.load(open(f'{S}/offers.pkl', 'rb'))
ev, st, last = D['events'], D['settled'], D['last']
rng = np.random.default_rng(5)
def boot(v, B=2000):
    v = np.array(v); m = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(B)]
    return v.mean(), np.percentile(m, 2.5), np.percentile(m, 97.5)
six = [r for r in Pp if r['comp'] != 844]
y = [int(all(a + b >= 1 for a, b in zip(*r['periods']))) for r in six]
p = [r['p_all_periods'] for r in six]
print(f"633 history (6 leagues, 2025-09..2026-11): games {len(six)}, model mean {np.mean(p):.4f}, realised {np.mean(y):.4f}, real-model {boot(np.array(y)-np.array(p))}")
print("   model p quantiles 5/50/95/max:", np.percentile(p, [5, 50, 95, 100]).round(3), "| share p>=0.70:", np.mean(np.array(p) >= .70).round(4))
for lo, hi in ((0, .55), (.55, .62), (.62, .68), (.68, 1)):
    ii = [i for i, x in enumerate(p) if lo <= x < hi]
    if ii: print(f"   band {lo}-{hi}: n {len(ii)} model {np.mean([p[i] for i in ii]):.3f} real {np.mean([y[i] for i in ii]):.3f}")
# P1 first goal: gradable from the period-1 score only when P1 is 0-0 or one-sided
P1 = [r for r in Pp]
g = collections.Counter()
for r in P1:
    a, b = r['periods'][0][0], r['periods'][1][0]
    g['0-0' if a + b == 0 else ('one-sided' if a == 0 or b == 0 else 'both scored (order unknown)')] += 1
print("643 P1 first goal, gradability from period scores:", dict(g), f"-> gradable {(g['0-0']+g['one-sided'])/len(P1):.3f}")
pn = np.array([r['p1_none'] for r in P1]); yn = np.array([r['periods'][0][0] + r['periods'][1][0] == 0 for r in P1], float)
print(f"   P1 no goal: model {pn.mean():.4f} realised {yn.mean():.4f}")
pf = np.array([max(r['p1_t1_first'], r['p1_t2_first']) for r in P1])
print(f"   favourite first in P1: model p quantiles 50/95/max {np.percentile(pf,[50,95,100]).round(3)}; share >= 0.70: {np.mean(pf>=.70):.4f}")
# match first goal (666): from the full scores, gradable only when one side scored nothing in regulation (or 0-0)
g2 = collections.Counter()
for r in P1:
    a, b = sum(r['periods'][0]), sum(r['periods'][1])
    g2['gradable' if a == 0 or b == 0 else 'order unknown'] += 1
print("666 match first goal, gradable from regulation scores:", dict(g2), f"-> {g2['gradable']/len(P1):.3f}")
# offered 633 / 643 / 666 prices: what does the market say, and is any side priced in the zone
for M in (633, 643, 666):
    groups = collections.defaultdict(dict)
    for (eid, m, mn, sbv, name), (ts, price) in last.items():
        if m == M: groups[eid][name] = price
    fav = []
    for eid, g_ in groups.items():
        s = sum(1 / x for x in g_.values())
        for name, x in g_.items():
            fav.append(((1 / x) / s, x, name))
    fav.sort(reverse=True)
    print(f"{M}: groups {len(groups)}, top de-vigged sides:", [(round(a, 3), b, c) for a, b, c in fav[:4]],
          "| sides fair>=0.70:", sum(1 for a, _, _ in fav if a >= .70))
