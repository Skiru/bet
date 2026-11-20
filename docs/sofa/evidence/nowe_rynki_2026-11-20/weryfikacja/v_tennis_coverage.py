import pickle,collections,sys
V=sys.argv[1]
c=pickle.load(open(f'{V}/collect.pkl','rb')); fx=c['fx']; off=c['offer']; nb=c['new_by_day']
def cat(e): return fx[e]['cat'] or '?'
per=collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
for e,f in fx.items():
    per[f['day']]['fx'][cat(e)]+=1
for d,o in off.items():
    for e in o['old']: per[d]['old'][cat(e)]+=1
for d,s in nb.items():
    for e in s: per[d]['new'][cat(e)]+=1
for d in sorted(per):
    if d<'2026-10-28': continue
    p=per[d]
    print(d,'fixtures ATP',p['fx']['ATP'],'WTA',p['fx']['WTA'],'| old',dict(p['old']),'| new',dict(p['new']))
# old-format share of ATP/WTA fixtures before/after 11-13
for lo,hi in (('2026-10-01','2026-10-16'),('2026-10-17','2026-11-12'),('2026-11-13','2026-11-19')):
    F=O=0
    for d in per:
        if lo<=d<=hi:
            F+=per[d]['fx']['ATP']+per[d]['fx']['WTA']; O+=per[d]['old']['ATP']+per[d]['old']['WTA']
    n=sum(1 for d in per if lo<=d<=hi)
    print(lo,hi,'days',n,'ATP+WTA fixtures',F,'old-format ATP+WTA',O,'per day old (all cats)',round(sum(sum(per[d]['old'].values()) for d in per if lo<=d<=hi)/n,1))
