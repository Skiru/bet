"""Step 1a: landscape of unmapped football markets 11-06..11-19 that touch halves / handicap / btts combos.
Writes templates.json (template -> events, selections) and cand_prices.jsonl.gz (latest pre-kickoff price
per (eid, marketName, name, sbv) of the candidate templates)."""
import gzip, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path[:0] = ["src", "."]
from bet.sofa.market_coverage import template_of
from bet.sofa.market_mapper import fold

OUT = Path(sys.argv[1])
RUNS = Path("runs/sofa")
DAYS = [f"2026-11-{d:02d}" for d in range(6, 20)]
KEEP = re.compile(r"(handicap|obu polow|zaklad bez remisu|obie druzyny strzela gola &|wygra obie|polow|podwojna szansa)")
CAND = re.compile(r"^(\{[ab]\} wygra obie polowy|remis w obu polowach|obie druzyny strzela gola & (powyzej|ponizej) # gola|handicap|handicap .*|[12]\.\s?polowa - handicap|[12]\.\s?polowa - zaklad bez remisu|[12]\.\s?polowa - podwojna szansa|\{[ab]\} wygra przynajmniej jedna polowe|remis w jednej z polow|\{[ab]\} wygra jedna z polow)$")
tmpl_ev = defaultdict(set); tmpl_sel = defaultdict(Counter)
latest = {}
for day in DAYS:
    rd = RUNS / day
    fx = {int(f["sofascore_event_id"]): f for f in json.load(open(rd / "02_fixtures.json")) if f.get("sport") == "football"}
    board = {str(e["superbet_event_id"]): (e.get("side_a") or "", e.get("side_b") or "") for e in json.load(open(rd / "01_board.json"))}
    for fp in sorted((rd / "unmapped_prices").glob("2026*.jsonl.gz")):
        with gzip.open(fp, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                eid = d.get("sofascore_event_id")
                f = fx.get(eid) if isinstance(eid, int) else None
                if f is None:
                    continue
                b = board.get(str(d.get("superbet_event_id")), ("", ""))
                sides = [b[0], b[1], f.get("home_name") or "", f.get("away_name") or ""]
                mn = d.get("marketName") or ""
                fm = fold(mn)
                if not KEEP.search(fm):
                    continue
                t = template_of(mn, sides)
                tmpl_ev[t].add(eid)
                st = template_of(d.get("name") or "", sides)
                tmpl_sel[t][st] += 1
                if CAND.match(t):
                    fetched = d.get("fetched_at_utc") or ""
                    if fetched >= (f.get("kickoff_utc") or ""):
                        continue
                    key = (eid, mn, d.get("name"), d.get("specialBetValue"))
                    old = latest.get(key)
                    if old is None or old["fetched_at_utc"] <= fetched:
                        latest[key] = {"day": day, "eid": eid, "sb": d.get("superbet_event_id"), "template": t,
                                       "marketName": mn, "name": d.get("name"), "sel_template": st,
                                       "sbv": d.get("specialBetValue"), "price": d.get("price"), "status": d.get("status"),
                                       "fetched_at_utc": fetched, "kickoff_utc": f.get("kickoff_utc"),
                                       "side_a": b[0], "side_b": b[1], "home": f.get("home_name"), "away": f.get("away_name"),
                                       "competition_id": f.get("competition_id"), "competition_name": f.get("competition_name")}
    print(day, len(latest), file=sys.stderr, flush=True)
summ = sorted(((t, len(e), tmpl_sel[t].most_common(12)) for t, e in tmpl_ev.items()), key=lambda x: -x[1])
json.dump([{"template": t, "events": n, "selections": s} for t, n, s in summ], open(OUT / "templates.json", "w"), ensure_ascii=False, indent=1)
with gzip.open(OUT / "cand_prices.jsonl.gz", "wt", encoding="utf-8") as fh:
    for r in latest.values():
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print("templates", len(summ), "cand selections", len(latest))
