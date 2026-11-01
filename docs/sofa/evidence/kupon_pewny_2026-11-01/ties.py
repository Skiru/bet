import datetime as dt, json
from pathlib import Path
from zoneinfo import ZoneInfo
from bet.sofa import slip_builder as sb, veto
LOCAL=ZoneInfo("Europe/Warsaw"); RUNS=Path("/Users/mkoziol/projects/bet/runs/sofa")
tie_req=0; req=0; tie_sizes=[]
for d in range(13,32):
    D=f"2026-10-{d:02d}"; run=RUNS/D; c=json.loads((run/"11_coupon.json").read_text())
    reads=veto.load_reads(run/"reads.json"); vet=veto.load_vetoes(run/"vetoes.json"); day=dt.date.fromisoformat(D)
    for h in range(10,23,2):
        lo=dt.datetime.combine(day,dt.time(h),LOCAL); hi=lo+dt.timedelta(hours=2); now=(lo-dt.timedelta(minutes=60)).astimezone(dt.timezone.utc)
        pool,_=sb.candidates(c["singles"],now,window=(lo.astimezone(dt.timezone.utc),hi.astimezone(dt.timezone.utc)),reads=reads,vetoes=vet,built_at=c["created_at_utc"])
        ok=[x for x in pool if x.odds>=sb.SAFE_TARGET]
        if not ok: continue
        req+=1; best=max(sb._search_score(x) for x in ok)
        top={x.match_key for x in ok if abs(sb._search_score(x)-best)<1e-12}
        if len(top)>1: tie_req+=1; tie_sizes.append(len(top))
print("requests with a single>=1.14:",req,"top-1 tied across matches:",tie_req,"median tie size",sorted(tie_sizes)[len(tie_sizes)//2] if tie_sizes else None)
