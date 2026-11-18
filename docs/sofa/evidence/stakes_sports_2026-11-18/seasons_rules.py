import re
POST = re.compile(r"play.?off|play.?in|knockout|final|quarter|semi|champion|wild.?card|pre.?play|stanley cup", re.I)
OTHER = re.compile(r"releg|play.?out|placement|promotion|qualif|classification|friendl|pre.?season|playdown|consolation|cup|5th|7th|9th|lower|upper|masters", re.I)
NCAA = "conference / at-large selection, no single table"
CONF = "conferences / divisions inside one table, map not coded"
EXCLUDED_STRUCTURE = {
 **{("ice-hockey",u):NCAA for u in (14285,14317)},
 **{("ice-hockey",u):CONF for u in (268,844,17188,1159,1141,9475,1454,14191)},  # KHL AHL ECHL MHL VHL WHL OHL QMJHL
 **{("basketball",u):NCAA for u in (33651,648,33652,33653,33655,13434,33654,18640)},
 **{("basketball",u):CONF for u in (1502,21307,1472,23100)},  # B.League B1 districts, Liga Argentina, LNBP; 23100 virtual
 **{("volleyball",u):NCAA for u in (23428,)},
}
NHL_EAST=("Boston","Buffalo","Detroit","Florida","Montr","Ottawa","Tampa","Toronto","Carolina","Columbus","New Jersey","New York","Philadelphia","Pittsburgh","Washington")
NBA_EAST=("Atlanta","Boston","Brooklyn","Charlotte","Chicago","Cleveland","Detroit","Indiana","Miami","Milwaukee","New York","Orlando","Philadelphia","Toronto","Washington")
def conference_of(sport,ut,names):
    if (sport,ut)==("ice-hockey",234): east=NHL_EAST
    elif (sport,ut)==("basketball",132): east=NBA_EAST
    else: return None
    return {t:("E" if any(n.startswith(e) for e in east) else "W") for t,n in names.items()}
TWO_POINT_HOCKEY={234,1442}  # NHL, EIHL: W 2 / OTL 1
def _award_hockey3(r,sport):
    ot=r["sdesc"] in ("AET","AP"); w=r["win"]
    if w==1: return (2,1) if ot else (3,0)
    if w==2: return (1,2) if ot else (0,3)
    return (0,0)
def _award_hockey2(r,sport):
    ot=r["sdesc"] in ("AET","AP"); w=r["win"]
    if w==1: return (2,1 if ot else 0)
    if w==2: return (1 if ot else 0,2)
    return (0,0)
def _award_bb(r,sport):
    w=r["win"]; return (1,0) if w==1 else (0,1) if w==2 else (0,0)
def _award_vb(r,sport):
    hs,as_=r["hs"],r["as"]
    if not isinstance(hs,int) or not isinstance(as_,int): return (0,0)
    if hs==3 and as_<=1: return (3,0)
    if as_==3 and hs<=1: return (0,3)
    if hs==3 and as_==2: return (2,1)
    if as_==3 and hs==2: return (1,2)
    return (0,0)
def points_rule(sport,ut,n_post,conf,n_teams):
    if sport=="ice-hockey":
        if ut==234: return dict(k=8,maxpg=2,award=_award_hockey2)
        two = ut in TWO_POINT_HOCKEY
        return dict(k=n_post,maxpg=2 if two else 3,award=_award_hockey2 if two else _award_hockey3)
    if sport=="basketball":
        if ut==132: return dict(k=10,maxpg=1,award=_award_bb)
        return dict(k=n_post,maxpg=1,award=_award_bb)
    if sport=="volleyball": return dict(k=n_post,maxpg=3,award=_award_vb)

import collections as _c, datetime as _dt
def start_year(ts):
    d=_dt.datetime.fromtimestamp(ts,_dt.UTC); return d.year-(1 if d.month<7 else 0)
def season_groups(rows):
    """(sport, ut, primary season id) -> every row of that league-season (all phases).
    Grouped by Sofascore season.id (fix 2026-11-18: summer leagues such as the WNBA no longer
    glue two seasons that share a start year); a satellite season of the same league whose
    games lie inside another season's time span (NBA Cup group games) is merged into it."""
    by=_c.defaultdict(list)
    for r in rows:
        if r["ut_id"] is None or r["season_id"] is None or not r["t_name"]: continue
        by[(r["sport"],r["ut_id"],r["season_id"])].append(r)
    span={k:(min(r["ts"] for r in v),max(r["ts"] for r in v),len(v)) for k,v in by.items()}
    out={}
    perut=_c.defaultdict(list)
    for k in by: perut[k[:2]].append(k)
    for ut,keys in perut.items():
        keys.sort(key=lambda k:-span[k][2])
        primary=[]
        for k in keys:
            host=next((p for p in primary if span[p][0]<=span[k][0] and span[k][1]<=span[p][1]),None)
            if host is None: primary.append(k); out[k]=list(by[k])
            else: out[host]+=by[k]
    return out
