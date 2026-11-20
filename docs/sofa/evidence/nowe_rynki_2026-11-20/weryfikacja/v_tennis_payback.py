import pickle,collections,json,sqlite3,sys,re,resource
sys.path.insert(0,'src'); sys.path.insert(0,'scripts/sofa')
from bet.sofa.settle import is_completed_event, settle_completed
V=sys.argv[1]
c=pickle.load(open(f'{V}/collect.pkl','rb'))
fx=c['fx']
db=sqlite3.connect('file:data/sofa.db?mode=ro',uri=True)
st={}
def state(ev):
    if ev in st: return st[ev]
    row=db.execute('select detail_json from sofa_event_detail where sofascore_event_id=?',(ev,)).fetchone()
    s=db.execute('select statistics_json,status_type from sofa_event_stats where sofascore_event_id=?',(ev,)).fetchone()
    e=json.loads(row[0]).get('event',{}) if row else {}
    desc=(e.get('status') or {}).get('description'); typ=(e.get('status') or {}).get('type')
    ok = bool(e) and is_completed_event(e) and settle_completed(e)
    tot=None; sets={}
    if s and s[0]:
        for p in json.loads(s[0]).get('statistics',[]):
            d={}
            for g in p['groups']:
                for i in g['statisticsItems']:
                    if i['key'] in ('aces','doubleFaults'):
                        d[i['key']]=(i.get('homeValue') or 0, i.get('awayValue') or 0)
            sets[p['period']]=d
    st[ev]=dict(ok=ok,desc=desc,typ=typ,stype=s[1] if s else None,sets=sets,
                bo=e.get('defaultPeriodCount'), h1=(e.get('homeScore') or {}).get('period3'))
    return st[ev]
def run(src, label, use_ok=True):
    agg=collections.defaultdict(lambda:[0,0,0.0,0.0,set()])
    skip=collections.Counter()
    for (ev,mn,name,sbv),r in src.items():
        if mn not in ('Asy','Podwójne błędy'): continue
        day=fx[ev]['day']
        if not ('2026-10-21'<=day<='2026-11-19'): continue
        if r.get('status')!='active' or float(r['price'])<=1.0: skip['inactive']+=1; continue
        s=state(ev)
        if use_ok and not s['ok']: skip['not_ok:'+str(s['desc'])]+=1; continue
        if not use_ok and s['stype']!='finished': skip['notfinished']+=1; continue
        key='aces' if mn=='Asy' else 'doubleFaults'
        a=s['sets'].get('ALL',{}).get(key)
        if a is None: skip['nostat']+=1; continue
        v=a[0]+a[1]; N=int(name[:-1]); pr=float(r['price']); w=v>=N
        x=agg[mn]; x[0]+=1; x[1]+=w; x[2]+=1/pr; x[3]+=w*pr; x[4].add(ev)
    print(label, dict(skip))
    for k,(n,w,i,p,evs) in agg.items():
        print(f'  {k}: n {n} matches {len(evs)} hit {w/n:.3f} implied {i/n:.3f} payback {p/n:.3f}')
run(c['pre'],'PRE-START, settle_completed')
run(c['any'],'LAST-ANY (verify_tennis style), status finished', use_ok=False)
# sanity: ALL vs sum of sets, retired descriptions among 'finished'
mism=0;n=0;desc=collections.Counter()
for ev,s in st.items():
    desc[(s['stype'],s['desc'],s['ok'])]+=1
    if s['ok'] and 'ALL' in s['sets'] and '1ST' in s['sets'] and '2ND' in s['sets']:
        per=[p for p in s['sets'] if p!='ALL']
        for k in ('aces','doubleFaults'):
            if k in s['sets']['ALL']:
                n+=1
                tot=sum(sum(s['sets'][p].get(k,(0,0))) for p in per)
                if tot!=sum(s['sets']['ALL'][k]): mism+=1
print('ALL vs sum of sets mismatches',mism,'of',n)
print(desc.most_common(12))
print('bo values',collections.Counter(s['bo'] for s in st.values()))
print('maxrss GB',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9)
