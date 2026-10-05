import sys, numpy as np, math
sys.path.insert(0, '/private/tmp/claude-501/-Users-mkoziol-projects-bet/326c21e7-29e6-43a0-88f5-09a4e6cdf26e/scratchpad/nations')
import measure_nations as M
from scripts.sofa.measure_sample_composition import before, poisson_over, poisson_logloss, split_metric, paired_interval
from bet.sofa.comparability import MatchKind
from datetime import datetime, UTC
h, targets, meta = M.load()
DAY=86400; start=int(datetime(2015,1,1,tzinfo=UTC).timestamp())
rng=np.random.default_rng(7)
for metric in sys.argv[1:]:
    stat, scope = split_metric(metric); lines = M.LINES[metric]
    recs=[]  # (eid, oldest, newest, lam, y, senior)
    for t in targets:
        if t.ts<start or stat not in t.values: continue
        pair=t.values[stat]
        ab=[p for p in before(h.get(t.home,[]),t.ts,metric) if p.kind is not MatchKind.FRIENDLY][:10]
        bb=[p for p in before(h.get(t.away,[]),t.ts,metric) if p.kind is not MatchKind.FRIENDLY][:10]
        if scope=='total':
            if len(ab)<10 or len(bb)<10: continue
            pool=ab+bb; lam=np.mean([p.value(metric) for p in pool]); y=pair[0]+pair[1]
            recs.append((t.event_id,(t.ts-min(p.ts for p in pool))/DAY,(t.ts-max(min(p.ts for p in ab), 0)*0 - max(max(p.ts for p in ab)*0,0))/DAY if False else max(t.ts-max(p.ts for p in ab), t.ts-max(p.ts for p in bb))/DAY, lam, y, meta[t.event_id]['senior_men']))
        else:
            for side,y in ((ab,pair[0]),(bb,pair[1])):
                if len(side)<10: continue
                lam=np.mean([p.value(metric) for p in side])
                recs.append((t.event_id,(t.ts-min(p.ts for p in side))/DAY,(t.ts-max(p.ts for p in side))/DAY,lam,y,meta[t.event_id]['senior_men']))
    ids=np.array([r[0] for r in recs]); old=np.array([r[1] for r in recs]); new=np.array([r[2] for r in recs])
    lam=np.array([r[3] for r in recs]); y=np.array([r[4] for r in recs]); sen=np.array([r[5] for r in recs])
    const=y.mean()
    ll=np.array([poisson_logloss(l,v) for l,v in zip(lam,y)]); llc=np.array([poisson_logloss(const,v) for v in y])
    print(f"\n## {metric}: {len(y)} cases; newest>60d share {np.mean(new>60):.1%}; senior_men newest>60d {np.mean(new[sen]>60):.1%}")
    print("| bucket | cases | skill vs constant (ll_const - ll_R0) [95%] | mean lam - y [95%] | P(over) pred - realised per line |")
    for lab,arr,bks in (("oldest",old,((0,180),(180,400),(400,730),(730,1e9))),("newest",new,((0,60),(60,120),(120,1e9)))):
        for lo,hi in bks:
            s=(arr>lo)&(arr<=hi)
            if s.sum()<30: print(f"| {lab} {lo}-{hi:.0f} | {s.sum()} | too few |"); continue
            d=llc[s]-ll[s]; a,b=paired_interval(d,ids[s],rng,500)
            e=lam[s]-y[s]; c,dd=paired_interval(e,ids[s],rng,500)
            cal=" ".join(f"{L}:{np.mean([poisson_over(l,L) for l in lam[s]])-np.mean(y[s]>L):+.3f}" for L in lines)
            print(f"| {lab} {lo}-{hi:.0f} | {s.sum()} | {d.mean():+.4f} [{a:+.4f}; {b:+.4f}] | {e.mean():+.3f} [{c:+.3f}; {dd:+.3f}] | {cal} |")
