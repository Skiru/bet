import json, sys, collections, re
d=json.load(open(sys.argv[1]))
fam=collections.defaultdict(lambda: collections.Counter())
cnt=collections.Counter()
for r in d:
    if r.get('sport') not in ('football','tennis'): continue
    k=(r['sport'], r['market'])
    cnt[k]+=1
    # classify estimator by notes prefixes
    pre=set()
    for n in r.get('notes') or []:
        m=re.match(r'([A-Z][A-Z0-9_]+)[: ]', n)
        if m: pre.add(m.group(1))
    fam[k].update(pre)
    fam[k]['bar:'+str(r.get('bar_reason'))]+=1
    fam[k]['src:'+str(r.get('forecast_source'))]+=1
    fam[k]['ss>0' if (r.get('sample_size') or 0)>0 else 'ss=0']+=1
for k in sorted(cnt):
    top=[x for x,_ in fam[k].most_common(14)]
    print(k[0], k[1], cnt[k], '|', ' '.join(top))
