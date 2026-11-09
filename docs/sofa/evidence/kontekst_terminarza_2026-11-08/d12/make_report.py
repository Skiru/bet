"""D12: d12_main.json + d12_sim_delta.json -> d12_report.md / d12_report.json."""
import json
from pathlib import Path
D = Path(__file__).parent
V = {v: json.loads((D / f"d12_{v}.json").read_text()) for v in ("main", "sim_delta")}
feat_log = (D / "features.log").read_text().strip()
p_log = [ln for ln in (D / "check_p.log").read_text().splitlines() if "n=" in ln]
c_log = next(ln for ln in (D / "check_conf.log").read_text().splitlines() if ln.startswith("TOTAL"))
de_log = (D / "delta_error.log").read_text().strip()
L = []
w = L.append


def hr(h):
    return f"{h['n']} (won {h['won']} / lost {h['lost']} / other {h['other']}; hit {h['hit_rate']})"


w("# D12 - downstream gates, schedule term `football_result` (path ii), settled days 2026-10-13..2026-11-07\n")
w("Pre-registered: `docs/sofa/evidence/kontekst_terminarza_2026-11-08/r3_final_review.md` 248-262. Read-only measurement; "
  "scripts and outputs in `data/refit_2026-11-08_schedule/d12/` (`extract.py`, `features.py`, `pricing.py`, `conf.py`, "
  "`d12.py`, `make_report.py`). Every number below is printed by those scripts (`d12_main.json`, `d12_sim_delta.json`, logs).\n")
w("Variants: **base** = the artifacts as built (08_confidence legs, 11_coupon singles, 08_refusals rows). **corrected** = "
  "the term exp(t) on the noted pure-rating goals centres of path (ii) rows (frozen `fr_frozen.json` coef), the four "
  "simulator floor keys untouched. Two runs: **main** (simulator keys NOT recomputed - base p not reproducible within 1e-6) "
  "and **sim_delta** (sensitivity: simulator keys also corrected by the delta method below).\n")
w("## 1. Method and reproduction\n")
w("- Features: " + feat_log.replace("\n", "; ") + ". Calendar = `sofa_listed_event` (as `football_features.py`) plus the "
  "2068 day fixtures absent from it, taken from their cached `/event` payload (`sofa_event_detail`); the 16 'differ from pkl' "
  "are events whose history gained those fixtures.")
w("- Base p from the noted centres (centres printed to 3 dp) vs `p_central`, all in-scope sheet rows of the 26 days:\n")
w("```")
L.extend(p_log)
w("```")
w("  The base is therefore NOT reproduced exactly (rounding of the noted centres). Corrected p = p_central + "
  "[price(centres x exp(t)) - price(centres)]; " + de_log + " (non-sim). For the simulator (max diff 0.0013, 7024 of 25104 rows "
  "> 1e-6) the main run does not recompute; sim_delta applies the same delta with the event-seeded simulator (common random numbers).")
w("- Confidence: the day's CONFIDENCE chain (`Calibration.realised` with the day's staged calibration and overlays -> "
  "`LineEvidence.read` -> `leg_floor` / catch-all / x >= 0.90 / prints_as_single), called on today's config files. "
  "The line evidence of each past day is not kept on disk (refitted every morning, overwritten), so the chain at the base p "
  "differs from the recorded confidence on most legs: " + c_log + " (all in-scope + floor-sim 08 legs; `src_same` = same curve). "
  "Therefore corrected confidence = recorded confidence + [chain(p_corr) - chain(p_base)] where the chain does not reproduce "
  "the leg exactly, and chain(p_corr) where it does. Per run: " +
  "; ".join(f"{v}: {s['reproduction_chain_vs_recorded']}" for v, s in V.items()) + ".")
w("- Simulator keys in scope (htft, result_1h, result_2h, higher_scoring_half, first_goal_1h): 0 legs in 08_confidence and 0 "
  "printed singles on all 26 days; of their 12,315 sheet rows the 08_refusals rows (10-21..11-07) were 10,468 BELOW_CONFIDENCE_FLOOR, "
  "1,799 KICKED_OFF, 33 CROSS_LEAGUE_UNLINKED, 12 NO_LINE_EVIDENCE, 2 NO_FETCHED_AT, 1 ODDS_TOO_LOW; sim_delta produced no simulator entrant, "
  "so the two runs are identical. 21 in-scope legs had no sheet row (not recomputed); 752 legs are the four floor keys (excluded, uncorrected).")
w("- Printability = confidence >= the leg's floor, x >= 0.90, not catch-all, prints_as_single (margin <= 15% or the "
  "one-sided rule). Gates that do not read p (start, fresh price, reads, settleability, unlinked...) are taken as built.\n")
for v, s in V.items():
    t = s["totals"]
    h = s["hit"]
    ts = s["t"]
    w(f"## 2. Run `{v}`\n")
    w("### t distribution (in-scope 08 legs recomputed)\n")
    w(f"- leg status: {ts['legs_status']}; printed legs: {ts['printed_status']}")
    w(f"- sides with coverage: {ts['sides_ok']}; share of those sides with t != 0: {ts['share_sides_t_nonzero']}; "
      f"mean |t| per side {ts['mean_abs_t_side']}; max |t| {ts['max_abs_t_side']}\n")
    w("### Printed / printable legs (in scope)\n")
    w("| quantity | base | corrected |")
    w("|---|---|---|")
    w(f"| in-scope 08 legs (passed every gate) | {t.get('legs_in_scope', 0)} | - |")
    w(f"| ... sim legs not recomputed | {t.get('legs_not_recomputed_sim', 0)} | |")
    w(f"| ... legs whose p changed / confidence changed | | {t.get('legs_p_changed', 0)} / {t.get('legs_conf_changed', 0)} |")
    w(f"| printed in-scope singles (11_coupon) | {hr(h['printed_in_scope_outcome'])} | {hr(h['corr_printed_in_scope_outcome'])} |")
    w(f"| printed -> not printable (flip out) | - | {hr(h['flip_out_outcome'])} |")
    w(f"| refused at a p gate -> printable (entrants; 08_refusals days 10-21..11-07 only) | - | {hr(h['entrant_outcome'])} |")
    w(f"| refused rows the base chain (today's config) already calls printable (skipped) | {t.get('refused_rows_base_chain_printable', 0)} | |")
    w(f"| football singles printed, all markets | {t.get('printed_football_base', 0)} | {t.get('printed_football_corr', 0)} |\n")
    w("### MODEL_ABOVE_OWN_SAMPLE\n")
    w(f"- removed legs (11_coupon removed_by_reads, refusal MODEL_ABOVE_OWN_SAMPLE): in scope {hr(h['maos_in_scope_outcome'])}; "
      f"out of scope {hr(h['maos_out_of_scope_outcome'])} - identical in both variants (the term moves no row with a sample; "
      f"path (ii) rows carry sample_size 0, `model_above_own_sample` needs >= 5 values). "
      f"In-scope 08_refusals rows with that reason (10-21..11-07): {t.get('maos_refusal_rows_in_scope', 0)}.\n")
    w("### price_gap (confidence - 1/odds > 0.03), printed in-scope legs\n")
    w(f"- base (recomputed on the leg): {hr(h['price_gap_base_outcome'])}; recorded `price_gap` field: {t.get('price_gap_recorded_field', 0)}")
    w(f"- corrected: {hr(h['price_gap_corr_outcome'])}\n")
    w("### rating_market_gap (D >= 1.0), printed football singles (all markets; live only from 11-04)\n")
    srcs = {k.replace('rmg_view_source_', ''): n for k, n in t.items() if k.startswith('rmg_view_source_')}
    w(f"- rating view sources: {srcs}")
    w(f"- matches with D >= 1: base {t.get('rmg_matches_d_ge1_base', 0)}, corrected {t.get('rmg_matches_d_ge1_corr', 0)}")
    w(f"- flagged legs: base {hr(h['rmg_base_outcome'])} (in scope {t.get('rmg_base_in_scope', 0)}, out {t.get('rmg_base_out_of_scope', 0)}); "
      f"corrected, D on the corrected rating whatever its source {hr(h['rmg_corr_outcome'])} (in {t.get('rmg_corr_in_scope', 0)}, out {t.get('rmg_corr_out_of_scope', 0)}); "
      f"corrected as wired today (only a SOURCE_PURE view moves) {hr(h['rmg_corr_as_wired_outcome'])}")
    pdx = s["per_day"]
    agree = {d: (pdx[d].get('rmg_recorded_field', 0), pdx[d].get('rmg_recorded_vs_base_recompute_agree', 0), pdx[d].get('printed_football_base', 0))
             for d in sorted(pdx) if d >= "2026-11-04"}
    w(f"- base recompute vs the recorded field, 11-04..11-07 (recorded flags, singles agreeing, singles): {agree}\n")
    w("### SAME_EVENT_DEDUP twins (hypothetical: the rule is live from 11-08; groups with >= 2 printed legs of one event, one in scope)\n")
    w(f"- twin groups: {t.get('twin_groups_with_in_scope', 0)}; with a confidence or membership change: "
      f"{t.get('twin_groups_conf_or_membership_changed', 0)}; chosen leg changed: {t.get('twin_groups_choice_changed', 0)}")
    w(f"- legs dedup would remove: base {t.get('dedup_removed_base', 0)}, corrected {t.get('dedup_removed_corr', 0)}\n")
    w("### Per day (printed in scope / flip out / entrants / conf changed)\n")
    w("| day | printed in scope | flip out | entrants | legs conf changed |")
    w("|---|---|---|---|---|")
    for d in sorted(pdx):
        x = pdx[d]
        w(f"| {d} | {x.get('printed_in_scope', 0)} | {x.get('flip_out', 0)} | "
          f"{x.get('entrants', 0) if x.get('refusals_file') else 'n/a'} | {x.get('legs_conf_changed', 0)} |")
    w("")
w("## 3. Limitations\n")
w("- The base p is not re-priced exactly (centres noted to 3 dp); the term enters as a delta (error bound above). "
  "Simulator keys: not recomputed in `main`; `sim_delta` is a sensitivity only.")
w("- Confidence on today's config files: the per-day line-evidence fit is not on disk; the corrected confidence is anchored "
  "on the recorded one plus the chain's delta. Curves are step functions in p buckets, so most small p moves change no confidence.")
w("- Features as of the DB copy (2026-11-08): `cont_next4` sees fixtures listed later than the build; 2068 fixtures were "
  "added from `/event` payloads. Not a live replay of the build-time calendar.")
w("- Entrants only from `08_refusals.json` (10-21..11-07), the LAST build of each day: rows refused KICKED_OFF there were "
  "judged by earlier builds whose refusals are not kept -> entrants are a lower bound; days 10-13..10-20 have none counted.")
w("- 08 legs are the last build's (locked legs keep their print-time confidence and odds). Twins / dedup and "
  "rating_market_gap were not live on most of these days: their numbers are what the rule would have done.")
w("- No curve refit with the term (r3 steps 22-27): the corrected p is read through today's curves.")
(D / "d12_report.md").write_text("\n".join(L) + "\n")
(D / "d12_report.json").write_text(json.dumps({v: {k: s[k] for k in ("totals", "reproduction_chain_vs_recorded", "t", "hit", "per_day")}
                                               | {"flip_out_detail": s["flip_out_detail"], "entrant_detail": s["entrant_detail"],
                                                  "twin_choice_changed": s["twin_choice_changed"]}
                                               for v, s in V.items()} | {"base_p_check": p_log, "delta_error": de_log,
                                                                           "confidence_chain_check": c_log, "features": feat_log}, indent=1))
print("\n".join(L))
