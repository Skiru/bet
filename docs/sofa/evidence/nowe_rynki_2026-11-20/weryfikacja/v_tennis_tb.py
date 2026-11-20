import pickle,collections,json,sys
V=sys.argv[1]
c=pickle.load(open(f'{V}/collect.pkl','rb'))
fx=c['fx']; off=c['offer']
tbev=collections.defaultdict(set)
for (ev,mn,name,sbv),r in c['tb'].items():
    tbev[fx[ev]['day']].add((ev,sbv))
tot=collections.Counter()
for d in ['2026-11-15','2026-11-16','2026-11-17','2026-11-18','2026-11-19']:
    s12=off[d]['set12']
    evs={e for e,_ in tbev[d]}
    has=sum(1 for e in evs if any(l==12.5 for m,l in s12.get(e,())))
    both=sum(1 for e,sb in tbev[d] if (f'games_set{sb}_total',12.5) in s12.get(e,()))
    print(d,'tb events',len(evs),'with any games_setX_total 12.5',has,'(event,set) pairs',len(tbev[d]),'pair has own-set 12.5',both,
          'any set3 key', sum(1 for e in evs if any(m=='games_set3_total' for m,l in s12.get(e,()))))
    tot['ev']+=len(evs); tot['has']+=has; tot['pairs']+=len(tbev[d]); tot['both']+=both
print(dict(tot))
# all lines of games_set1_total available on these events: is 12.5 the top rung?
lines=collections.Counter()
for d in ['2026-11-17']:
    for e,ks in off[d]['set12'].items():
        for m,l in ks: lines[(m,l)]+=1
print(sorted(lines.items()))
