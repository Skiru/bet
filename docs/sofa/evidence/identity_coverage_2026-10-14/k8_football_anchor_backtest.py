import json,glob,sqlite3,collections,sys
from datetime import datetime,UTC
sys.path[:0]=['src','.']
from bet.sofa.names import normalize_name
from scripts.sofa import measure_day_anchor as mda
from scripts.sofa import measure_team_identity as m
SPORT=sys.argv[1]; FIRST,LAST=sys.argv[2],sys.argv[3]
c=sqlite3.connect("file:data/sofa.db?mode=ro",uri=True)
def vid(name):
    r=c.execute("select sofascore_id from sofa_entity where sport=? and query_key=? and status='verified'",(SPORT,normalize_name(name))).fetchone()
    return r[0] if r else None
board={}
for p in sorted(glob.glob('runs/sofa/*/01_board.json')):
    for e in json.load(open(p)):
        if e['sport']==SPORT: board[str(e['superbet_event_id'])]=e
fix={}
for p in sorted(glob.glob('runs/sofa/*/02_fixtures.json')):
    for f in json.load(open(p)):
        if f['sport']!=SPORT: continue
        for sb in f['superbet_event_ids']: fix[str(sb)]=f
items=[]
for sb,e in board.items():
    d=str(e['kickoff_utc'])[:10]
    if d<FIRST or d>LAST: continue
    a,b=m.board_sides(e)
    items.append((sb,e,a,b,vid(a),vid(b),fix.get(sb)))
from bet.sofa.player_model import team_name_index
import time
IDX=team_name_index(c, SPORT, int(time.time()), window_s=400*86400)
def idx_id(name):
    v=IDX.get(normalize_name(name)) or set()
    return next(iter(v)) if len(v)==1 else None
items=[(sb,e,a,b,ia,ib,f,idx_id(a),idx_id(b)) for sb,e,a,b,ia,ib,f in items]
ids={x for it in items for x in (it[4],it[5]) if x}
since=int(datetime.fromisoformat(FIRST).replace(tzinfo=UTC).timestamp())-86400
games=mda.load_games(c,[SPORT],since,ids)
res=collections.Counter(); wrong=[]; picks=[]
for sb,e,a,b,ia,ib,f,xa,xb in items:
    rec={'kickoff_utc':e['kickoff_utc'],'team1':a,'team2':b,'team1_id':ia,'team2_id':ib}
    st,g=mda.predict(rec,games,3600)
    if st=='PICK':
        # orientation as Superbet orders the sides (RESOLVE's F25 gate)
        straight=(ia is not None and ia==g.home_id) or (ib is not None and ib==g.away_id)
        if not straight: st='REVERSED'
        # the other name known exactly (listing index) as another team: refuse
        for own,x in ((ia,xb),(ib,xa)):
            pass
        oa = ib if ia is None else None
        other_known = xb if ia is not None and ib is None else (xa if ib is not None and ia is None else None)
        if st=='PICK' and other_known is not None and other_known not in (g.home_id,g.away_id): st='OTHER_KNOWN'
    if f is not None:
        if st=='PICK':
            ok=g.event_id==f['sofascore_event_id']; res['fixture:'+('correct' if ok else 'WRONG')]+=1
            if not ok: wrong.append((e['match_name'],e['kickoff_utc'],f['sofascore_event_id'],g.event_id))
        else: res['fixture:'+st]+=1
    else:
        res['gap:'+st]+=1
        if st=='PICK': picks.append((e['match_name'],e['kickoff_utc'],g.event_id))
print(res); print('WRONG',wrong[:20]); print('PICKS',len(picks))
for p in picks[:200]: print('  ',p)
