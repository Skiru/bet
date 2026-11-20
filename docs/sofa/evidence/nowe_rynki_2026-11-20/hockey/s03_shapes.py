"""Step 1 tables: per market events, days, tournaments, lines, 2-way pairing, overround, printable zone."""
import pickle, sys, collections, re, statistics as st
D = pickle.load(open(sys.argv[1], 'rb'))
events, settled, last = D['events'], D['settled'], D['last']
groups = collections.defaultdict(dict)   # (eid, m, mname, sbv) -> {name: price}
for (eid, m, mname, sbv, name), (ts, price) in last.items():
    groups[(eid, m, mname, sbv)][name] = price
by_m = collections.defaultdict(list)
for k, g in groups.items():
    by_m[k[1]].append((k, g))
for m in sorted(by_m):
    gs = by_m[m]
    evs = {k[0] for k, _ in gs}
    tours = collections.Counter(events[e]['tournament'] for e in evs)
    days = collections.Counter(events[e]['kickoff_utc'][:10] for e in evs)
    sizes = collections.Counter(len(g) for _, g in gs)
    ovr = [sum(1/p for p in g.values()) - 1 for _, g in gs if len(g) >= 2]
    sbvs = collections.Counter(k[3] for k, _ in gs)
    zone = 0
    for _, g in gs:
        if len(g) < 2: continue
        s = sum(1/p for p in g.values())
        for p in g.values():
            if 1.09 <= p <= 1.43 and (1/p)/s >= 0.70: zone += 1
    print(f"== {m} {gs[0][0][2][:60]}: events {len(evs)}, groups {len(gs)}, group sizes {dict(sizes)}")
    print("   tournaments", dict(tours.most_common(6)))
    print("   kickoff days", dict(sorted(days.items())))
    print("   sbv", dict(sbvs.most_common(12)))
    if ovr: print(f"   overround median {st.median(ovr):.3f} p10 {sorted(ovr)[len(ovr)//10]:.3f} p90 {sorted(ovr)[9*len(ovr)//10]:.3f}; zone selections {zone}")
    # settled coverage
    st_ = collections.Counter((settled.get(e) or {}).get('state', 'NO_RECORD') for e in evs)
    print("   SHADOW state", dict(st_))
