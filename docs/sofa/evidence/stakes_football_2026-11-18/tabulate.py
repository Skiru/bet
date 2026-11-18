import sys
import pandas as pd
S=sys.argv[1]
x=pd.read_pickle(f"{S}/states.pkl")
x["kind"]=x.nat.map({True:"nat",False:"club"})
x.loc[x.women,"kind"]=x.loc[x.women,"kind"]+"_W"
print("groups (league-seasons/groups) with >=1 match in period:")
print(x.groupby(["kind","period"]).apply(lambda g: g[["ut","tname"]].drop_duplicates().shape[0]).unstack())
print("matches:"); print(x.groupby(["kind","period"]).size().unstack())
s=pd.concat([x.assign(state=x.home,tb=x.tb_home,left=x.left_home),x.assign(state=x.away,tb=x.tb_away,left=x.left_away)])
order=["MUST_WIN","ALIVE","SECURED","DEAD","AMBIGUOUS"]
for k in ["club","nat","club_W","nat_W"]:
    t=s[s.kind==k]
    if t.empty: continue
    print(f"\n== {k}: side-matches by state x period (all / with stats / corners / shots / cards / fouls)")
    for col in ["event_id","has_stats","corners","shots","cards","fouls"]:
        if col=="event_id": tab=t.groupby(["state","period"]).size().unstack().reindex(order)
        else: tab=t[t[col]].groupby(["state","period"]).size().unstack().reindex(order)
        print(col); print(tab.fillna(0).astype(int).to_string())
    print("tb-dependent share by state:"); print(t.groupby("state").tb.mean().reindex(order).round(3))
    print("AMBIGUOUS share:", round((t.state=="AMBIGUOUS").mean(),4), " among non-ALIVE-early(progress>=.67):", round((t[t.progress>=0.67].state=="AMBIGUOUS").mean(),4))
x.to_pickle(f"{S}/states2.pkl")
# matches where at least one side non-ALIVE (excl ambiguous)
x["exposed"]=(~x.home.isin(["ALIVE","AMBIGUOUS"]))|(~x.away.isin(["ALIVE","AMBIGUOUS"]))
x["anyamb"]=(x.home=="AMBIGUOUS")|(x.away=="AMBIGUOUS")
print("\nmatches with >=1 exposed side (no ambiguous side):")
print(x[x.exposed&~x.anyamb].groupby(["kind","period"]).size().unstack())
print("with stats:"); print(x[x.exposed&~x.anyamb&x.has_stats].groupby(["kind","period"]).size().unstack())
print("matches with >=1 ambiguous side:"); print(x[x.anyamb].groupby(["kind","period"]).size().unstack())
# club exact vs bounds
c=x[~x.nat]
print("\nclub exact enumeration share (all / progress>=.9):", round(c.exact.mean(),3), round(c[c.progress>=.9].exact.mean(),3))
print("club in ut-season with knockout rounds share:", round(c.ko.mean(),3))
# national last two rounds
n=x[x.nat&~x.women]
n["last2"]=(n.left_home<=2)|(n.left_away<=2)
print("\nnational: matches in the last two rounds (either side <=2 left incl. this):")
print(n[n.last2].groupby(["ut_name","period"]).size().unstack().fillna(0).astype(int))
print("all national group matches:"); print(n.groupby(["ut_name","period"]).size().unstack().fillna(0).astype(int))
print("national with stats:"); print(n[n.has_stats].groupby(["period"]).size(), n[n.corners].groupby(["period"]).size())
