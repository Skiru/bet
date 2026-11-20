import pickle, collections
from bet.sofa import sport_confidence as scf
A=pickle.load(open('/private/tmp/claude-501/-Users-mkoziol-projects-bet/04c6201e-4497-4273-b02c-92e4cd7d7f51/scratchpad/hockey/analysis.pkl','rb'))
R=pickle.load(open('/private/tmp/claude-501/-Users-mkoziol-projects-bet/04c6201e-4497-4273-b02c-92e4cd7d7f51/scratchpad/hockey/results.pkl','rb'))
cur=A['curves']
def conf(c,p):
    e=scf._find(c,p) if c else None
    return None if e is None else float(e['realised_lo95'])
pr=[]
for l in A['legs']:
    k=f"{l['mk']}|{l['side']}" if l['mk']!='handicap' else 'handicap|TEAM'
    c=conf(cur.get(k),l['p'])
    if c is not None and c>=.7 and c*l['odds']>=.9 and l['ovr']<=.15: pr.append({**l,'c':c})
print('printed',len(pr), collections.Counter(l['m'] for l in pr))
states=[(a,b,o) for a in range(13) for b in range(13) for o in ((1,2) if a==b else (0,))]
def win(l,s):
    a,b,o=s; fa=a+(o==1); fb=b+(o==2)
    if l['m']==617: v=fa+fb; return v>l['L'] if l['side']=='OVER' else v<l['L']
    if l['m'] in (621,653):
        v=fa if l['m']==621 else fb; return v>l['L'] if l['side']=='OVER' else v<l['L']
    side='T1' if l['name'].rsplit(' (',1)[0]==R[l['eid']]['team1'] else 'T2'
    # sbv L = handicap of team1 per report; name carries the team's own handicap
    h=float(l['name'].rsplit('(',1)[1].rstrip(')').replace(',','.'))
    m=(fa-fb) if side=='T1' else (fb-fa)
    return m+h>0
byg=collections.defaultdict(list)
for l in pr: byg[l['eid']].append(l)
dups=0; ex=[]
for g,ls in byg.items():
    sig=collections.defaultdict(list)
    for l in ls: sig[tuple(win(l,s) for s in states)].append(l)
    for k,v in sig.items():
        if len(v)>1: dups+=len(v)-1; ex.append([(x['m'],x['name'],x['L']) for x in v])
print('identical-event duplicates among printed',dups, ex[:5])
# also check: whole-offer identity of 613 |h|>=1.5 with reg, 617 odd
