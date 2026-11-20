"""Analyse cs2_ot_wf_rows.jsonl: calibration of P(no OT in series), race vs base, per-map OT by favourite band."""
import json, math, random, sys
from collections import defaultdict
from datetime import datetime, timezone
FROM = sys.argv[1] if len(sys.argv) > 1 else "2026-02-01"
t0 = datetime.fromisoformat(FROM).replace(tzinfo=timezone.utc).timestamp()
R = [json.loads(l) for l in open("cs2_ot_wf_rows.jsonl")]
R = [r for r in R if r["ts"] >= t0]
def ll(p, y): p = min(max(p, 1e-6), 1 - 1e-6); return -math.log(p if y else 1 - p)
def boot_mean(vals, reps=2000):
    rng = random.Random(0); n = len(vals); s = []
    for _ in range(reps): s.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    s.sort(); return sum(vals) / n, s[int(.025 * reps)], s[int(.975 * reps) - 1]
print("series", len(R), "from", FROM)
for bo in (1, 3, 5, None):
    S = [r for r in R if bo is None or r["bo"] == bo]
    if not S: continue
    y = sum(r["y_noot"] for r in S) / len(S)
    print(f"bo={bo} n={len(S)} realised noOT {y:.4f} mean p_race {sum(r['p_race'] for r in S)/len(S):.4f} p_base {sum(r['p_base'] for r in S)/len(S):.4f}")
    d = [ll(r["p_race"], r["y_noot"]) - ll(r["p_base"], r["y_noot"]) for r in S]
    db = [(r["p_race"] - r["y_noot"]) ** 2 - (r["p_base"] - r["y_noot"]) ** 2 for r in S]
    print("   logloss race-base %+.5f [%+.5f, %+.5f]" % boot_mean(d), " brier race-base %+.5f [%+.5f, %+.5f]" % boot_mean(db))
    for k in ("p_race", "p_base"):
        g = [r["y_noot"] - r[k] for r in S]
        print(f"   {k} realised-claimed %+.4f [%+.4f, %+.4f]" % boot_mean(g))
print("calibration bands (all formats), p_race:")
for k in ("p_race", "p_base"):
    bands = defaultdict(list)
    for r in R:
        b = math.floor(r[k] * 20) / 20; bands[b].append(r)
    for b in sorted(bands):
        S = bands[b]
        if len(S) < 30: continue
        m = boot_mean([r["y_noot"] - r[k] for r in S])
        print(f"  {k} [{b:.2f},{b+.05:.2f}) n={len(S):5d} claimed {sum(r[k] for r in S)/len(S):.3f} realised {sum(r['y_noot'] for r in S)/len(S):.3f} gap %+.3f [%+.3f, %+.3f]" % m)
# per-map OT calibration by favourite band (race vs base)
print("per-map OT share by favourite map p:")
mb = defaultdict(lambda: [0, 0, 0.0, 0.0])
for r in R:
    fav = max(r["p_map"], 1 - r["p_map"]); b = min(math.floor(fav * 10) / 10, 0.9)
    for (h, a, w) in r["maps"]:
        x = mb[b]; x[0] += 1; x[1] += int(h + a >= 25); x[2] += r["race_map_ot"]; x[3] += r["base_map"]
for b in sorted(mb):
    n, o, pr, pb = mb[b]; print(f"  fav [{b:.1f},{b+.1:.1f}) maps {n:5d} OT realised {o/n:.4f} race {pr/n:.4f} base {pb/n:.4f}")
# >= 0.70 claimed bucket
for k in ("p_race", "p_base"):
    S = [r for r in R if r[k] >= 0.70 and r["bo"] == 3]
    if S:
        m = boot_mean([r["y_noot"] - r[k] for r in S])
        print(f"bo3 {k}>=0.70 n={len(S)} claimed {sum(r[k] for r in S)/len(S):.3f} realised {sum(r['y_noot'] for r in S)/len(S):.3f} gap %+.4f [%+.4f, %+.4f]" % m)
