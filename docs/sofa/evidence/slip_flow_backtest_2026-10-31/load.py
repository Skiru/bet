"""Build a flat leg table from printed snapshots (append-only), 13_results grades, closing.jsonl.
Decision time = the day's FIRST printed snapshot (morning). Read-only on the repo."""
import json, os, sys, sqlite3, pickle
from datetime import datetime
import pandas as pd
ROOT='/Users/mkoziol/projects/bet/runs/sofa'
OUT=os.path.dirname(os.path.abspath(__file__))
DAYS=[f'2026-10-{d:02d}' for d in range(13,31)]
def ts(s):
    if s is None: return None
    s=s.replace('Z','+00:00'); return datetime.fromisoformat(s).timestamp()
def rkey(l):
    eid=l['sofascore_event_id']
    if 'family' in l and 'market_id' in l:
        return json.dumps([eid,l['family'],l.get('period',0),l.get('subject',''),l.get('line'),l.get('side',l.get('direction')),l.get('market_id') or 0,l.get('map_nr',0) or 0])
    return json.dumps([eid,l['market'],l['subject'],l['line'],l['direction']])
def ckey(l):
    ln=l['line']
    return f"{l['sofascore_event_id']}|{l['market']}|{l['subject']}|{ln}|{l['direction']}"
def verdicts(l):
    return ','.join(sorted({r.get('verdict','?') for r in (l.get('reads') or [])}))
db=sqlite3.connect('file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro',uri=True)
rows=[]
for d in DAYS:
    res=json.load(open(f'{ROOT}/{d}/13_results.json'))['legs']
    snaps=sorted(os.listdir(f'{ROOT}/{d}/printed'))
    clos={}
    if os.path.exists(f'{ROOT}/{d}/closing.jsonl'):
        for line in open(f'{ROOT}/{d}/closing.jsonl'):
            r=json.loads(line)
            if r.get('variant')!='official': continue
            k=r['leg_key']; 
            if r.get('odds_close') and (k not in clos or r['fetched_at_utc']>clos[k]['fetched_at_utc']): clos[k]=r
    first={}; track={}
    for i,f in enumerate(snaps):
        q=json.load(open(f'{ROOT}/{d}/printed/{f}'))
        t=ts(q['pdf_rendered_at_utc']) if q.get('pdf_rendered_at_utc') else ts(q['created_at_utc'])
        for src,L in (('legs',q['legs']),('removed',q.get('removed_by_reads',[]))):
            for l in L:
                k=rkey(l); ko=ts(l['kickoff_utc'])
                if ko is not None and ko<=t: continue  # started: not actionable
                tr=track.setdefault(k,{'first_t':t,'first_snap':i,'first_src':src,'leg':l})
                tr['last_t']=t; tr['last_odds']=l.get('offered_odds',l.get('odds')); tr['last_src']=src
                tr['last_verdicts']=verdicts(l); tr['last_conf']=l['confidence']
                if src=='removed': tr['ever_removed']=1
    t0=None
    for k,tr in track.items():
        l=tr['leg']
        g=res.get(k)
        status=g['status'] if g else None; gsrc='13_results' if g else None
        if g is None and 'family' not in l:
            r=db.execute('select outcome from sofa_settled_row where sofascore_event_id=? and market=? and subject=? and line=? and direction=?',(l['sofascore_event_id'],l['market'],l['subject'],l['line'] if l['line'] is not None else 0.0,l['direction'])).fetchone()
            if r: status={'WIN':'won','LOSS':'lost'}.get(r[0],r[0].lower()); gsrc='db'
        odds=l.get('offered_odds',l.get('odds'))
        c=clos.get(ckey(l)) if 'family' not in l else None
        pg=l.get('price_gap') or {}
        rows.append(dict(day=d,key=k,eid=l['sofascore_event_id'],sport=l['sport'],match=l['match'],competition=l.get('competition'),
            market=l['market'],subject=l.get('subject'),line=l.get('line'),direction=l['direction'],kickoff=ts(l['kickoff_utc']),
            first_t=tr['first_t'],first_snap=tr['first_snap'],first_src=tr['first_src'],last_t=tr['last_t'],last_odds=tr['last_odds'],
            last_src=tr['last_src'],last_verdicts=tr['last_verdicts'],ever_removed=tr.get('ever_removed',0),
            odds=odds,conf=l['confidence'],model_p=l.get('model_p'),forecast_p=l.get('forecast_p'),forecast_source=l.get('forecast_source'),
            implied_p=l.get('implied_p'),market_p=l.get('market_p'),overround=l.get('overround'),line_offset=l.get('line_offset'),
            price_band_cap=l.get('price_band_cap'),calibrated_on=l.get('calibrated_on'),calibration_n=l.get('calibration_n'),
            sample_size=l.get('sample_size'),sample_hit_rate=l.get('sample_hit_rate'),price_gap=1 if pg else 0,
            one_sided=1 if l.get('one_sided_market') else 0,verd0=verdicts(l),peer_pref=1 if (l.get('peer') or {}).get('preferred') else 0,
            has_peer=1 if l.get('peer') else 0,ladder_no=l.get('ladder_no'),context_flags=','.join(l.get('context_flags') or []),
            sb_market=l.get('superbet_market'),locked=l.get('locked'),
            status=status,gsrc=gsrc,res_odds=g.get('odds') if g else None,
            clv_taken=c.get('odds_taken') if c else None,clv_close=c.get('odds_close') if c else None,clv_min=c.get('minutes_before') if c else None))
    print(d,len(snaps),len(track),sum(1 for r in rows if r['day']==d and r['status'] is None),file=sys.stderr)
df=pd.DataFrame(rows)
df.to_pickle(f'{OUT}/legs.pkl')
print(df.shape)
