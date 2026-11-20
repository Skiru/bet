"""Step 1/2 inventory of the N+ selections (graded.jsonl from s3)."""
import json, sys, collections, re
D = sys.argv[1]
g = [json.loads(l) for l in open(f'{D}/graded.jsonl')]
def scope(t): return 'set1' if t.startswith('1. set') else 'set2' if t.startswith('2. set') else 'match'
def subj(t): return 'player' if '{a}' in t or '{b}' in t else 'total'
def stat(t): return 'aces+df' if '+ podwojne' in t else 'df' if 'podwojne' in t else 'aces'
# sbv consistency: set prefix and N
bad = 0
for r in g:
    sbv = str(r['sbv']); sc = scope(r['template'])
    exp = str(r['n']) if sc == 'match' else f"{1 if sc=='set1' else 2}-{r['n']}"
    if sbv != exp: bad += 1
print('sbv inconsistent with name/template:', bad, 'of', len(g))
ev = collections.defaultdict(set); sel = collections.Counter()
for r in g:
    ev[r['day']].add(r['sid']); sel[r['day']] += 1
print('day events selections')
for d in sorted(ev): print(d, len(ev[d]), sel[d])
print('total events', len({r['sid'] for r in g}), 'selections', len(g), 'days', len(ev))
c = collections.Counter((scope(r['template']), subj(r['template']), stat(r['template'])) for r in g)
for k, v in sorted(c.items()): print(k, v)
st = collections.Counter(r['last_status'] for r in g); print('last pre-start status', st)
noact = sum(1 for r in g if r['active_price'] is None); print('never active pre-start', noact)
pr = [r['active_price'] for r in g if r['active_price'] is not None]
bands = collections.Counter()
for p in pr:
    b = '1.00' if p <= 1.0 else '1.01-1.086' if p < 1.087 else '1.087-1.30' if p < 1.30 else '1.30-1.60' if p < 1.6 else '1.60-2.20' if p < 2.2 else '2.20-5' if p < 5 else '>=5'
    bands[b] += 1
print('price bands (last active pre-start):', sorted(bands.items()))
# rungs per ladder
lad = collections.Counter((r['sid'], r['template']) for r in g)
print('ladders', len(lad), 'mean rungs', round(sum(lad.values()) / len(lad), 2))
# where 1+ priced 1.00
print('1+ rungs', sum(1 for r in g if r['n'] == 1), '1+ @1.00', sum(1 for r in g if r['n'] == 1 and (r['active_price'] or 0) <= 1.0))
