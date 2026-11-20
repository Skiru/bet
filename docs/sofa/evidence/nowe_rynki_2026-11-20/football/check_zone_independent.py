"""Adversarial re-derivation of step 1's zone count for "<team> wygra obie połowy" straight from the raw
unmapped files (no template_of, no cands.parse): latest pre-kickoff active price per (eid, market, selection),
tak / nie from one snapshot, fair = (1/price)/overround."""
import gzip, json, unicodedata
from collections import defaultdict
from pathlib import Path
def low(s):
    return unicodedata.normalize("NFKD", (s or "").replace("ł", "l").replace("Ł", "L")).encode("ascii", "ignore").decode().lower().strip()
latest = {}
for d in range(6, 20):
    day = Path(f"runs/sofa/2026-11-{d:02d}")
    ko = {int(f["sofascore_event_id"]): f["kickoff_utc"] for f in json.load(open(day / "02_fixtures.json")) if f.get("sport") == "football"}
    for fp in sorted((day / "unmapped_prices").glob("2026*.jsonl.gz")):
        for line in gzip.open(fp, "rt"):
            if "obie po" not in line:
                continue
            r = json.loads(line)
            mn = low(r["marketName"])
            if not mn.endswith(" wygra obie polowy") or r["sofascore_event_id"] not in ko:
                continue
            if r["fetched_at_utc"] >= ko[r["sofascore_event_id"]] or r.get("status") not in (None, "active"):
                continue
            k = (r["sofascore_event_id"], mn, low(r["name"]))
            if k not in latest or latest[k][0] <= r["fetched_at_utc"]:
                latest[k] = (r["fetched_at_utc"], r["price"])
zone = pairs = 0
ovs = []
for (e, mn, sel), (t, p) in latest.items():
    if sel != "nie":
        continue
    o = latest.get((e, mn, "tak"))
    if o is None or o[0] != t:
        continue
    pairs += 1
    over = 1 / p + 1 / o[1]
    ovs.append(over)
    if 1.09 <= p <= 1.43 and (1 / p) / over >= 0.70:
        zone += 1
ovs.sort()
print("pairs", pairs, "zone 'nie'", zone, "median overround", round(ovs[len(ovs) // 2], 4))
