import gzip,json,glob,sqlite3,collections,os,re
# independent check: match-total aces ladder "asy" and double faults "podwójne błędy" (match totals only)
last={}
for d in sorted(os.listdir('runs/sofa')):
    if not ('2026-10-21'<=d<='2026-11-19'): continue
    for f in glob.glob(f'runs/sofa/{d}/unmapped_prices/2026*.jsonl.gz'):
        for l in gzip.open(f,'rt'):
            r=json.loads(l); mn=r['marketName']
            if mn in ('asy','Asy','podwójne błędy','Podwójne błędy'):
                k=(r['sofascore_event_id'],mn.lower(),r['name'])
                if k not in last or r['fetched_at_utc']>last[k]['fetched_at_utc']: last[k]=r
db=sqlite3.connect('file:data/sofa.db?mode=ro',uri=True)
cache={}
def stat(ev,key):
    if ev not in cache:
        row=db.execute("select statistics_json,status_type from sofa_event_stats where sofascore_event_id=?",(ev,)).fetchone()
        cache[ev]=None
        if row and row[0] and row[1]=='finished':
            for p in json.loads(row[0]).get('statistics',[]):
                if p['period']=='ALL':
                    cache[ev]={i['key']:(i.get('homeValue',0) or 0)+(i.get('awayValue',0) or 0) for g in p['groups'] for i in g['statisticsItems']}
    s=cache[ev]; return None if s is None else s.get(key)
agg=collections.defaultdict(lambda:[0,0,0.0,0.0])  # n, wins, sum implied, sum payout
for (ev,mn,name),r in last.items():
    m=re.match(r'(\d+)\+$',name)
    if not m or r.get('status')!='active' or float(r['price'])<=1.0: continue
    # skip if fetched after start? approximate: keep last snapshot
    v=stat(ev,'aces' if mn=='asy' else 'doubleFaults')
    if v is None: continue
    N=int(m.group(1)); pr=float(r['price']); win=v>=N
    # rung rank within ladder
    a=agg[(mn,"all")]; a[0]+=1; a[1]+=win; a[2]+=1/pr; a[3]+=win*pr
    if 1.09<=pr<=1.29:
        b=agg[(mn,"odds 1.09-1.29")]; b[0]+=1; b[1]+=win; b[2]+=1/pr; b[3]+=win*pr
for k,(n,w,imp,pay) in agg.items(): print(k,'n',n,'hit',round(w/n,3),'implied',round(imp/n,3),'payback',round(pay/n,3))
print('events',len({k[0] for k in last}), 'with stats', sum(1 for v in cache.values() if v))
