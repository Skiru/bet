import pickle, collections
rows=pickle.load(open('nhl_rows.pkl','rb'))
C=collections.Counter(); ex=[]
def g(d,k): return d.get(k)
tie_odd=collections.Counter(); ident=collections.Counter()
for eid,ts,desc,H,A,wc in rows:
    p=[(H.get(f'period{i}'),A.get(f'period{i}')) for i in (1,2,3)]
    if any(a is None or b is None for a,b in p): C[(desc,'missing period')]+=1; continue
    rh=sum(a for a,_ in p); ra=sum(b for _,b in p)
    ch,ca=H.get('current'),A.get('current')
    nt=(H.get('normaltime'),A.get('normaltime'))
    tie = rh==ra
    if desc=='Ended':
        ok = (ch,ca)==(rh,ra) and not tie
        C[(desc,'cur==reg' if (ch,ca)==(rh,ra) else 'cur!=reg', 'tie' if tie else 'no tie')]+=1
        if not ok: ex.append((eid,desc,H,A))
    else:
        d=(ch-rh,ca-ra)
        winner = 'H' if d==(1,0) else 'A' if d==(0,1) else '?'
        w2 = {1:'H',2:'A'}.get(wc)
        # who won OT/SO by overtime/penalties fields
        if desc=='AET': wf='H' if (H.get('overtime') or 0)>(A.get('overtime') or 0) else 'A'
        else: wf='H' if (H.get('penalties') or 0)>(A.get('penalties') or 0) else 'A'
        C[(desc,'tie' if tie else 'NOT TIE','delta',d,'winnerCode_agrees' if winner==w2 else 'winnerCode_DIS','field_agrees' if winner==wf else 'field_DIS','nt==reg' if nt==(rh,ra) else 'nt!=reg')]+=1
        if d not in ((1,0),(0,1)) or winner!=w2 or winner!=wf or not tie: ex.append((eid,desc,H,A,wc))
        if desc=='AP': C[('AP overtime', (H.get('overtime'),A.get('overtime')), 'pens', 'present' if H.get('penalties') is not None else 'absent')]+=1
    # identity check, final score per rule
    fh,fa = (ch,ca)
    T=fh+fa; RT=rh+ra
    for k in range(1,12):
        L=k+0.5
        same=(T>L)==(RT>L); ident[('total',k%2,same)]+=1
    for h in (-4.5,-3.5,-2.5,-1.5,-0.5,0.5,1.5,2.5,3.5,4.5):
        same=((fh-fa)+h>0)==((rh-ra)+h>0); ident[('hcp',abs(h)>=1.5,same)]+=1
    for L in (0.5,1.5,2.5,3.5,4.5):
        same=(fh>L)==(rh>L); ident[('team1',L,same)]+=1
for k,v in sorted(C.items(),key=str): print(v,k)
print('exceptions',len(ex)); [print(x) for x in ex[:8]]
for k,v in sorted(ident.items(),key=str): print(k,v)
