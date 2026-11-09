"""D12 phase 1: per-day compact extraction of the artifacts (read-only)."""
from __future__ import annotations
import json, pickle, sys
from pathlib import Path
REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from scripts.sofa.build_coupon import board_sides  # noqa: E402
from bet.sofa.epochs import FOOTBALL_SIM_MARKETS  # noqa: E402

OUT = REPO / "data/refit_2026-11-08_schedule/d12/days"
NONSIM = {"result_1x2", "draw_no_bet", "double_chance", "btts_or_over", "dc_and_over",
          "dc_and_under", "result_handicap", "result_or_btts", "result_or_clean_sheet",
          "result_or_over", "result_or_under", "first_goal"}
SCOPE_ALL = NONSIM | set(FOOTBALL_SIM_MARKETS)
VIEW = {"goals_total", "goals_for"}
RMG_MKT = {"result_1x2", "double_chance", "goals_for", "goals_total"}

def key(r):
    return (int(r["sofascore_event_id"]), r["market"], r.get("subject") or "", float(r["line"]), r["direction"])

def football(x):
    return x.get("sport", "football") == "football"

def main(day: str) -> None:
    run = REPO / "runs/sofa" / day
    out = {"day": day}
    sheet = json.loads((run / "05_sheet.json").read_text())
    rows, view_rows = [], []
    for r in sheet:
        if r.get("sport") != "football":
            continue
        m = r.get("market")
        if m in SCOPE_ALL:
            rows.append({k: v for k, v in r.items() if k not in ("unfitted_constants",)})
        elif m in VIEW:
            view_rows.append({"sofascore_event_id": r["sofascore_event_id"], "sport": "football",
                              "market": m, "subject": r.get("subject"), "notes": r.get("notes")})
    del sheet
    out["sheet_scope"] = rows
    out["sheet_view"] = view_rows
    conf = json.loads((run / "08_confidence.json").read_text())
    out["conf_created"] = conf.get("created_at_utc")
    out["conf_legs"] = [x for x in conf.get("legs") or [] if football(x)]
    out["conf_removed"] = [x for x in conf.get("removed_by_reads") or [] if football(x)]
    del conf
    cp = json.loads((run / "11_coupon.json").read_text())
    out["coupon_singles"] = [x for x in cp.get("singles") or [] if football(x)]
    out["coupon_removed"] = [x for x in cp.get("removed_by_reads") or [] if football(x)]
    out["coupon_same_event"] = [x for x in cp.get("removed_as_same_event") or [] if football(x)]
    out["coupon_meta"] = {k: cp.get(k) for k in ("created_at_utc", "same_event_dedup", "rating_market_gap")}
    del cp
    offer = json.loads((run / "04_offer.json").read_text())
    out["offer"] = {int(e["sofascore_event_id"]): e.get("rungs") or [] for e in offer
                    if e.get("sofascore_event_id") is not None}
    del offer
    st = json.loads((run / "07_settled.json").read_text())
    out["settled"] = {key(r): r.get("outcome") for r in st if r.get("sport") == "football"}
    del st
    res = run / "13_results.json"
    out["results"] = json.loads(res.read_text()).get("legs") if res.exists() else None
    ref = run / "08_refusals.json"
    if ref.exists():
        d = json.loads(ref.read_text())
        cols = d["columns"]
        evs = d["events"]
        keep = []
        for r in d["rows"]:
            rec = dict(zip(cols, r, strict=True))
            if rec["market"] in SCOPE_ALL:
                ev = evs[rec["event"]]
                if ev.get("sport") == "football":
                    rec["sofascore_event_id"] = ev["sofascore_event_id"]
                    keep.append(rec)
        out["refusals"] = keep
    else:
        out["refusals"] = None
    fx = json.loads((run / "02_fixtures.json").read_text())
    out["fixtures"] = {int(f["sofascore_event_id"]): {k: f.get(k) for k in (
        "home_name", "away_name", "competition_name", "competition_id", "season_id",
        "national_teams", "superbet_event_ids", "kickoff_utc", "category_name",
        "home_entity_id", "away_entity_id")} for f in fx if f.get("sport") == "football"}
    out["boards"] = board_sides(run)
    (OUT / f"{day}.pkl").write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    print(day, "scope rows", len(rows), "legs", len(out["conf_legs"]), "singles", len(out["coupon_singles"]),
          "refusals", None if out["refusals"] is None else len(out["refusals"]), flush=True)

if __name__ == "__main__":
    for d in sys.argv[1:]:
        main(d)
