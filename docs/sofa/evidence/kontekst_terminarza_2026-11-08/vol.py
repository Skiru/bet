import json,collections,glob,os
days=sorted(glob.glob('runs/sofa/2026-10-2*')+glob.glob('runs/sofa/2026-11-0*'))
agg=collections.defaultdict(lambda: collections.Counter())
reasons=collections.Counter()
nd=0; events=0
for dd in days:
    f=dd+'/08_refusals.json'
    if not os.path.exists(f): continue
    nd+=1
    d=json.load(open(f))
    ev=d['events']
    tset={i for i,e in enumerate(ev) if e.get('sport')=='tennis'}
    events+=len(tset)
    for r in d['rows']:
        if r[0] not in tset: continue
        m,dirn,conf,reason,p=r[1],r[6],r[9],r[10],r[8]
        k=(m,dirn); a=agg[k]
        a['rows']+=1
        if p is not None: a['p']+=1
        if conf is not None:
            a['conf']+=1
            if conf>=0.70: a['c70']+=1
            if conf>=0.60: a['c60']+=1
        if reason is None: a['pass']+=1
        else: reasons[(m,reason.split(':')[0].split('(')[0])]+=1
print('days',nd,'tennis events',events)
fam=collections.defaultdict(collections.Counter)
for (m,dr),a in agg.items():
    fam[m].update(a)
print('| market | dir | rows | p | confidence | conf>=0.70 | conf>=0.60 | passed all gates |')
for (m,dr),a in sorted(agg.items(), key=lambda x:-x[1]['rows']):
    print(f"| {m} | {dr} | {a['rows']} | {a['p']} | {a['conf']} | {a['c70']} | {a['c60']} | {a['pass']} |")
print()
print('FAMILY')
for m,a in sorted(fam.items(), key=lambda x:-x[1]['rows']):
    print(f"| {m} | {a['rows']} | {a['p']} | {a['conf']} | {a['c70']} | {a['c60']} | {a['pass']} |")
print()
top=collections.defaultdict(list)
for (m,r),n in reasons.items(): top[m].append((n,r))
for m in sorted(top): print(m, sorted(top[m],reverse=True)[:4])
