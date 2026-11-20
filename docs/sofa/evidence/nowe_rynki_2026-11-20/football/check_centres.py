"""Adversarial check 1: my walk-forward centres vs the live SHEET's own sim notes (05_sheet.json that survived)."""
import json, pickle, re, sys
import numpy as np
S = sys.argv[1]
fc = pickle.load(open(f"{S}/centres_live_1106_1119.pkl", "rb"))
NOTE = re.compile(r"goals centres home ([\d.]+) / away ([\d.]+)")
for day in ("2026-11-09", "2026-11-16", "2026-11-18", "2026-11-19"):
    d = json.load(open(f"runs/sofa/{day}/05_sheet.json"))
    rows = d["rows"] if isinstance(d, dict) else d
    live = {}
    for r in rows:
        if r.get("market") != "team_scores_both_halves":
            continue
        txt = " ".join(str(n) for n in (r.get("notes") or []))
        m = NOTE.search(txt)
        if m:
            live[int(r["sofascore_event_id"])] = (float(m.group(1)), float(m.group(2)))
    del d, rows
    diffs = []
    miss = 0
    for eid, (h, a) in live.items():
        v = fc.get(eid, {}).get("goals_for")
        if v is None:
            miss += 1
            continue
        diffs.append((v[0] - h, v[1] - a, v[0] / h - 1, v[1] / a - 1))
    D = np.array(diffs)
    if len(D):
        rel = np.abs(D[:, 2:]).ravel()
        print(day, "live sim events", len(live), "mine missing", miss, "compared", len(D),
              "median |rel diff|", round(float(np.median(rel)), 4), "p90", round(float(np.percentile(rel, 90)), 4),
              "share within 1%", round(float(np.mean(rel < 0.01)), 3), "within 5%", round(float(np.mean(rel < 0.05)), 3),
              "mean signed rel", round(float(np.mean(D[:, 2:])), 4))
