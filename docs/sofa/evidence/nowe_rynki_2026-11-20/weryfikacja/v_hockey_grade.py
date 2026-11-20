import json, sqlite3, collections, resource, pickle
c=sqlite3.connect('file:data/sofa.db?mode=ro',uri=True)
ids=[r[0] for r in c.execute("SELECT event_id FROM sofa_listed_event WHERE sport=?",('ice-hockey',))]
ids=sorted(set(ids))
ut=collections.Counter(); st=collections.Counter(); bad=[]; rows=[]
seen=set()
for i in range(0,len(ids),500):
    ch=ids[i:i+500]
    for (js,) in c.execute("SELECT event_json FROM sofa_listed_event WHERE event_id IN (%s)"%",".join("?"*len(ch)),ch):
        e=json.loads(js)
        if not isinstance(e.get('id'),int) or e['id'] in seen: continue
        u=((e.get('tournament') or {}).get('uniqueTournament') or {})
        if u.get('name')!='NHL': continue
        if (e.get('status') or {}).get('type')!='finished': continue
        seen.add(e['id'])
        H,A=e.get('homeScore') or {},e.get('awayScore') or {}
        desc=(e.get('status') or {}).get('description')
        st[desc]+=1
        rows.append((e['id'],e.get('startTimestamp'),desc,{k:H.get(k) for k in ('current','display','normaltime','period1','period2','period3','overtime','penalties')},{k:A.get(k) for k in ('current','display','normaltime','period1','period2','period3','overtime','penalties')},e.get('winnerCode')))
print('NHL finished',len(rows),dict(st),'rss MB',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6)
pickle.dump(rows,open('/private/tmp/claude-501/-Users-mkoziol-projects-bet/04c6201e-4497-4273-b02c-92e4cd7d7f51/scratchpad/verify/hockey/nhl_rows.pkl','wb'))
