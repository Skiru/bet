"""Extra checks on measured_rows.json: implied vs realised by rung position and
category; gate variants (curve without line evidence, model p only)."""
import json, collections, numpy as np
rows = json.load(open('measured_rows.json'))
H = [r for r in rows if '2026-10-21' <= r['day'] <= '2026-11-19' and r.get('odds') and r.get('p') is not None]
lad = collections.defaultdict(list)
for r in H: lad[(r['sid'], r['template'])].append(r)
pos = collections.defaultdict(list)
for v in lad.values():
    v.sort(key=lambda r: r['n'])
    for i, r in enumerate(v): pos[min(i, 5)].append(r)
print('rung position (0 = lowest active rung): n, mean 1/odds, mean model p, realised')
for i in sorted(pos):
    S = pos[i]; print(i, len(S), round(np.mean([1/r['odds'] for r in S]), 3), round(np.mean([r['p'] for r in S]), 3), round(np.mean([r['y'] for r in S]), 3))
print('by category: n, 1/odds, p, realised')
for c in sorted({r['cat'] for r in H}):
    S = [r for r in H if r['cat'] == c]; print(c, len(S), len({r['sid'] for r in S}), round(np.mean([1/r['odds'] for r in S]), 3), round(np.mean([r['p'] for r in S]), 3), round(np.mean([r['y'] for r in S]), 3))
# model-side: ladder's implied median vs model median position: where is Superbet's 50% point?
# variant gates
def show(name, S):
    if not S: print(name, 0); return
    y = np.array([r['y'] for r in S]); o = np.array([r['odds'] for r in S])
    print(f"{name}: legs {len(S)} matches {len({r['sid'] for r in S})} realised {y.mean():.3f} 1/odds {np.mean(1/o):.3f} ROI {np.mean(y*o-1)*100:+.1f}% after tax {np.mean(y*o*0.88-1)*100:+.1f}%")
show('A model p>=0.70 & p*odds>=0.90 & odds>=1.087', [r for r in H if r['p'] >= 0.7 and r['p']*r['odds'] >= 0.9 and r['odds'] >= 1.087])
show('B curve (no line evidence) >=0.70 & x>=0.90', [r for r in H if r.get('curve') and r['curve'] >= 0.7 and r['curve']*r['odds'] >= 0.9 and r['odds'] >= 1.087])
show('C full chain (as CONFIDENCE)', [r for r in H if r.get('refusal') is None])
show('D model p >= 1/odds (any p)', [r for r in H if r['p'] >= 1/r['odds']])
off = [r['offset'] for r in H if r.get('conf') is not None and r.get('curve') and r['curve'] >= 0.7]
print('line-evidence offset on curve>=0.70 rows: mean', round(float(np.mean(off)), 4), 'share <0', round(float(np.mean(np.array(off) < 0)), 3))
# lowered only by band cap?
print('sources of conf>=0.70 rows:', collections.Counter(('cap' if '|cap:' in r['source'] else 'sbd' if 'sbd' in r['source'] else 'curve') for r in H if r.get('conf') and r['conf'] >= 0.7))
# per-day gate count distribution (hold-out, days with the format)
days = sorted({r['day'] for r in H}); c = collections.Counter(r['day'] for r in H if r.get('refusal') is None)
print('gate legs per day', [c.get(d, 0) for d in days])
