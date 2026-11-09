import json, collections, sys, re
sys.path[:0]=["/Users/mkoziol/projects/bet/src"]
from bet.sofa import epochs, confidence as C
from pathlib import Path
on=json.load(open("runs/sofa/2026-11-08/08_confidence.json"))
ct=json.load(open("runs_ctrl/sofa/2026-11-08/08_confidence.json"))
def key(l): return (l.get("sofascore_event_id"),l["market"],str(l.get("subject")),l.get("line"),l.get("direction"))
scope=epochs.SCHEDULE_TERM_MARKETS
legs=on["legs"]
fb=[l for l in legs if l.get("sport")=="football"]
ins=[l for l in fb if l["market"] in scope]
print("on legs",len(legs),"football",len(fb),"in-scope",len(ins))
print("in-scope with schedule_term",sum("schedule_term" in l for l in ins),"with shadow",sum("p_central_no_schedule_term" in l for l in ins))
print("out-of-scope legs w/ fields",sum(("schedule_term" in l or "p_central_no_schedule_term" in l) for l in legs if l["market"] not in scope and l["market"] not in epochs.SCHEDULE_TERM_FLOOR_EXCLUDED))
print("leg schedule_term keys",collections.Counter(tuple(sorted(l["schedule_term"])) for l in legs if "schedule_term" in l))
print("statuses",collections.Counter((l["market"] in scope, l["schedule_term"]["status"]) for l in legs if "schedule_term" in l))
# floor legs
fl=[l for l in legs if l.get("floor_rule")]
print("floor_rule legs on",len(fl),collections.Counter((l["market"],l["direction"]) for l in fl))
flc=[l for l in ct["legs"] if l.get("floor_rule")]
print("floor_rule legs ctrl",len(flc))
cm={key(l):l for l in ct["legs"]}
same=sum(1 for l in fl if key(l) in cm and cm[key(l)]["confidence"]==l["confidence"] and cm[key(l)]["model_p"]==l["model_p"])
print("floor legs identical (p, conf) to ctrl",same,"of",len(fl), "floor confidences <0.70:",sum(l["confidence"]<0.70 for l in fl))
print("floor legs carrying schedule_term", collections.Counter(l.get("schedule_term",{}).get("status") for l in fl))
# curve source check: legs whose model_p equal to ctrl, in keys changed between staged files
a=json.load(open("/Users/mkoziol/projects/bet/config/sofa_confidence_calibration.next.2026-11-07.json"));b=json.load(open("/Users/mkoziol/projects/bet/config/sofa_confidence_calibration.next.2026-11-10.json"))
chg=[k for k in b["by_market_direction"] if a["by_market_direction"].get(k)!=b["by_market_direction"][k]]
chgm={k.split("@")[0].split("|")[0] for k in chg}
eqp=[(l,cm[key(l)]) for l in fb if key(l) in cm and l["model_p"]==cm[key(l)]["model_p"]]
moved=[(l,c) for l,c in eqp if l["confidence"]!=c["confidence"]]
print("legs with equal model_p on/ctrl:",len(eqp),"of which confidence differs:",len(moved))
print(" differing by market",collections.Counter(l["market"] for l,_ in moved).most_common(12))
print(" differing in markets changed between staged files:",sum(l["market"] in chgm for l,_ in moved),"/",len(moved))
outside=[(l,c) for l,c in moved if l["market"] not in chgm and l["market"] not in epochs.FOOTBALL_SIM_MARKETS]
print(" differing outside changed curve markets:",len(outside),[ (l["market"],l["calibrated_on"],c["calibrated_on"],l["confidence"],c["confidence"]) for l,c in outside[:4]])
for l,c in moved[:3]: print("  ex",l["market"],l["subject"],l["line"],l["direction"],"p",l["model_p"],"conf on",l["confidence"],l["calibrated_on"],"ctrl",c["confidence"],c["calibrated_on"])
# replay calibration directly
calB=C.Calibration.load(Path("/Users/mkoziol/projects/bet/config/sofa_confidence_calibration.next.2026-11-10.json"))
calA=C.Calibration.load(Path("/Users/mkoziol/projects/bet/config/sofa_confidence_calibration.next.2026-11-07.json"))
