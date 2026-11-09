"""D12 (r3_final_review.md 248-262): downstream gates on the settled days
2026-10-13..2026-11-07, base vs the football_result schedule term on path (ii).

Base = what the artifacts hold (08_confidence legs, 11_coupon singles,
08_refusals rows). Corrected p = p_central + [price(noted centres x exp(t)) -
price(noted centres)] (the noted centres are rounded to 3 dp, so the base
cannot be re-priced exactly; the delta carries the term). Corrected
confidence: the day's CONFIDENCE chain (conf.Day) at the corrected p; where
that chain at the base p does not give the recorded confidence (today's line
evidence differs from the day's), recorded + [chain(p_corr) - chain(p_base)].
Simulator keys: main = not recomputed (base p not reproducible within 1e-6);
sensitivity "sim_delta" = the same delta method with the seeded simulator.
"""
from __future__ import annotations
import collections, json, math, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import pricing as P  # noqa: E402
import conf as C  # noqa: E402
from bet.sofa import leg_identity as li  # noqa: E402
from bet.sofa import price_gap as pg  # noqa: E402
from bet.sofa import rating_market_gap as rmg  # noqa: E402
from bet.sofa.confidence import MIN_ODDS_FOR_CEILING, overround  # noqa: E402

D12 = P.D12
P_DEP = {"BELOW_CONFIDENCE_FLOOR", "NEGATIVE_LEG_EV", "CATCH_ALL_BUCKET",
         "NO_LINE_EVIDENCE", "NOT_CALIBRATED", "MARGIN_TOO_HIGH", "ONE_SIDED_NOT_ADMITTED", None}


def K(r):
    return (int(r["sofascore_event_id"]), r["market"], r.get("subject") or "", float(r["line"]), r["direction"])


def hits(keys, outcome):
    w = l = u = 0
    for k in keys:
        o = outcome(k)
        if o == "WIN":
            w += 1
        elif o == "LOSS":
            l += 1
        else:
            u += 1
    return {"n": len(keys), "won": w, "lost": l, "ungraded": u,
            "hit_rate": round(w / (w + l), 4) if w + l else None}


def run(variant: str):
    """variant: 'main' (sim keys not recomputed) or 'sim_delta'."""
    recompute = set(P.NONSIM) | (set(P.SIM_SCOPE) if variant == "sim_delta" else set())
    agg = collections.defaultdict(collections.Counter)
    lists = collections.defaultdict(list)
    tstat = {"legs": collections.Counter(), "abs_t_sides": [], "printed": collections.Counter()}
    repro = collections.Counter()
    days_out = {}
    import os
    only = set(filter(None, os.environ.get("D12_DAYS", "").split(",")))
    for pth in sorted((D12 / "days").glob("*.pkl")):
        if only and pth.stem not in only:
            continue
        d = pickle.loads(pth.read_bytes())
        day = d["day"]
        rows = {K(r): r for r in d["sheet_scope"]}
        res = d["results"] or {}

        def outcome(k, res=res, d=d):
            jk = json.dumps([k[0], k[1], k[2], k[3], k[4]], ensure_ascii=False)
            r = res.get(jk)
            if r is not None:
                return {"won": "WIN", "lost": "LOSS"}.get(r["status"], "OTHER")
            return d["settled"].get(k, "OTHER")

        offer_rung = {}
        for eid, rungs in d["offer"].items():
            for rg in rungs:
                offer_rung[(eid, rg["market"], rg.get("subject") or "", float(rg["line"]))] = rg
        conf_created = C.parse(d["conf_created"])

        def corr_p(row, base_p):
            """(p_corr, t_home, t_away, tstatus) or None when not recomputed."""
            if row["market"] not in recompute:
                return None
            eid = int(row["sofascore_event_id"])
            th, ta, st = P.terms(eid)
            c = P.centres(row)
            if c is None:
                return ("unparsed",)
            lh, la, r, cards, _ = c
            if th == 0.0 and ta == 0.0:
                return base_p, th, ta, st
            pb = P.price(row, lh, la, r, cards)
            pc = P.price(row, lh * math.exp(th), la * math.exp(ta), r, cards)
            if pb is None or pc is None:
                return ("unpriced",)
            return min(max(base_p + (pc - pb), 0.0), 1.0), th, ta, st

        def chain(row, p, odds, now, ovr, one_sided):
            dd = C.Day(day, now)
            fx = d["fixtures"].get(int(row["sofascore_event_id"]))
            kl = dd.klass(row, fx, d["boards"].get(int(row["sofascore_event_id"])))
            return dd.gate(row, p, odds, kl, ovr, one_sided)

        # ---- A. legs universe (passed every gate in the actual build)
        printed_keys = {K(x) for x in d["coupon_singles"]}
        legs = [x for x in d["conf_legs"] if x["market"] in P.SCOPE | P.FLOOR_SIM]
        leg_corr = {}
        for leg in legs:
            k = K(leg)
            row = rows.get(k)
            in_scope = leg["market"] in P.SCOPE
            agg[day]["legs_in_scope" if in_scope else "legs_floor_sim"] += 1
            if not in_scope or row is None:
                if in_scope and row is None:
                    agg[day]["legs_no_sheet_row"] += 1
                continue
            cp = corr_p(row, leg["model_p"])
            if cp is None:
                agg[day]["legs_not_recomputed_sim"] += 1
                continue
            if len(cp) == 1:
                agg[day]["legs_" + cp[0]] += 1
                continue
            p_c, th, ta, st = cp
            tstat["legs"][st] += 1
            if st == "ok":
                tstat["abs_t_sides"] += [abs(th), abs(ta)]
                if th != 0.0 or ta != 0.0:
                    tstat["legs"]["t_nonzero"] += 1
            if k in printed_keys:
                tstat["printed"][st] += 1
                if st == "ok" and (th != 0.0 or ta != 0.0):
                    tstat["printed"]["t_nonzero"] += 1
            now = C.parse(leg.get("printed_at_utc") or d["conf_created"])
            rg = offer_rung.get(k[:4])
            ovr = leg.get("overround")
            one_sided = bool(leg.get("one_sided_market"))
            gb = chain(row, leg["model_p"], leg["offered_odds"], now, ovr, one_sided)
            gc = chain(row, p_c, leg["offered_odds"], now, ovr, one_sided)
            exact = gb["conf"] is not None and abs(gb["conf"] - leg["confidence"]) < 1e-9
            repro["exact" if exact else ("none" if gb["conf"] is None else "differs")] += 1
            if gc["conf"] is None:
                c_conf, status = None, gc["status"]
            elif exact:
                c_conf, status = gc["conf"], gc["status"]
            else:
                # anchored: recorded + chain delta, re-gated
                base_c = gb["conf"] if gb["conf"] is not None else leg["confidence"]
                c_conf = round(leg["confidence"] + (gc["conf"] - base_c), 4)
                fl = gc.get("floor", 0.70)
                status = ("BELOW_CONFIDENCE_FLOOR" if c_conf < fl else
                          "NEGATIVE_LEG_EV" if c_conf * leg["offered_odds"] < 0.90 - 1e-12 else
                          gc["status"] if gc["status"] in ("PRINTABLE", "MARGIN_TOO_HIGH", "ONE_SIDED_NOT_ADMITTED", "CATCH_ALL_BUCKET") else "PRINTABLE")
            leg_corr[k] = {"p_base": leg["model_p"], "p_corr": round(p_c, 4), "conf_base": leg["confidence"],
                           "conf_corr": c_conf, "status_corr": status, "t": (th, ta),
                           "odds": leg["offered_odds"]}
            if abs(p_c - leg["model_p"]) > 1e-12:
                agg[day]["legs_p_changed"] += 1
            if c_conf is not None and abs(c_conf - leg["confidence"]) > 1e-9:
                agg[day]["legs_conf_changed"] += 1
        # printed in-scope singles and flips out
        sc_printed = [x for x in d["coupon_singles"] if x["market"] in P.SCOPE]
        out_keys = [K(x) for x in sc_printed if K(x) in leg_corr and leg_corr[K(x)]["status_corr"] != "PRINTABLE"]
        lists["printed_in_scope"] += [(day, K(x)) for x in sc_printed]
        lists["flip_out"] += [(day, k) for k in out_keys]
        for x in sc_printed:
            lists["printed_in_scope_outcome"].append(outcome(K(x)))
        for k in out_keys:
            lists["flip_out_outcome"].append(outcome(k))
            lists["flip_out_detail"].append({"day": day, "key": list(k), **leg_corr[k]})
        # ---- B. entrants from 08_refusals (rows refused at a p-dependent gate)
        entrants = []
        if d["refusals"] is not None:
            agg[day]["refusals_file"] = 1
            for rr in d["refusals"]:
                if rr["market"] not in P.SCOPE or rr["reason"] not in P_DEP or rr["reason"] is None:
                    continue
                if rr["reason"] in ("MARGIN_TOO_HIGH", "ONE_SIDED_NOT_ADMITTED"):
                    continue  # p-independent once past the confidence gates
                k = K(rr)
                row = rows.get(k)
                if row is None or rr.get("odds") is None or rr["odds"] < MIN_ODDS_FOR_CEILING:
                    continue
                cp = corr_p(row, row["p_central"])
                if cp is None or len(cp) == 1:
                    continue
                p_c = cp[0]
                if abs(p_c - row["p_central"]) < 1e-12:
                    continue
                rg = offer_rung.get(k[:4]) or {}
                ovr = overround(rg.get("over_odds"), rg.get("under_odds"))
                one_sided = k[4] == "OVER" and rg.get("under_odds") is None
                gb = chain(row, row["p_central"], rr["odds"], conf_created, ovr, one_sided)
                gc = chain(row, p_c, rr["odds"], conf_created, ovr, one_sided)
                if gb["status"] == "PRINTABLE":
                    agg[day]["refused_rows_base_chain_printable"] += 1  # today's config disagrees
                    continue
                if gc["status"] == "PRINTABLE":
                    entrants.append({"sofascore_event_id": k[0], "sport": "football", "market": k[1],
                                     "subject": k[2], "line": k[3], "direction": k[4],
                                     "offered_odds": rr["odds"], "confidence": gc["conf"],
                                     "match": d["coupon_singles"][0]["match"] if False else None,
                                     "_reason_base": rr["reason"], "_p": (row["p_central"], p_c)})
        fxn = d["fixtures"]
        for e in entrants:
            f = fxn.get(e["sofascore_event_id"]) or {}
            e["match"] = f"{f.get('home_name')} - {f.get('away_name')}"
            lists["entrant_outcome"].append(outcome(K(e)))
            lists["entrant_detail"].append({"day": day, "key": list(K(e)), "conf": e["confidence"],
                                            "odds": e["offered_odds"], "p": e["_p"], "base_reason": e["_reason_base"]})
        agg[day]["entrants"] += len(entrants)
        agg[day]["flip_out"] += len(out_keys)
        agg[day]["printed_in_scope"] += len(sc_printed)
        # ---- corrected printed set (football, all markets)
        base_set = [dict(x) for x in d["coupon_singles"]]
        corr_set = []
        for x in base_set:
            k = K(x)
            if k in leg_corr:
                lc = leg_corr[k]
                if lc["status_corr"] != "PRINTABLE":
                    continue
                corr_set.append(dict(x, confidence=lc["conf_corr"]))
            else:
                corr_set.append(dict(x))
        corr_set += [{k2: v for k2, v in e.items() if not k2.startswith("_")} for e in entrants]
        # ---- C. price_gap (confidence - 1/odds > GAP), in scope
        for name, s in (("base", base_set), ("corr", corr_set)):
            for x in s:
                if x["market"] in P.SCOPE and pg.annotate(x) is not None:
                    agg[day][f"price_gap_{name}"] += 1
                    lists[f"price_gap_{name}_outcome"].append(outcome(K(x)))
            agg[day][f"printed_football_{name}"] += len(s)
        agg[day]["price_gap_recorded_field"] += sum(1 for x in base_set if x["market"] in P.SCOPE and x.get("price_gap"))
        # ---- D. MODEL_ABOVE_OWN_SAMPLE
        for x in d["coupon_removed"]:
            if x.get("refusal") == "MODEL_ABOVE_OWN_SAMPLE":
                tag = "in_scope" if x["market"] in P.SCOPE else "out_of_scope"
                agg[day][f"maos_removed_{tag}"] += 1
                lists[f"maos_{tag}_outcome"].append(outcome(K(x)))
        if d["refusals"] is not None:
            agg[day]["maos_refusal_rows_in_scope"] += sum(1 for rr in d["refusals"] if rr["reason"] == "MODEL_ABOVE_OWN_SAMPLE")
        # ---- E. rating_market_gap
        ev_ids = {int(x["sofascore_event_id"]) for x in base_set + corr_set}
        names = {e: (f.get("home_name"), f.get("away_name")) for e, f in fxn.items()}
        sheet_rows = d["sheet_view"] + d["sheet_scope"]
        offers = [{"sofascore_event_id": e, "rungs": r} for e, r in d["offer"].items()]
        views = rmg.views_by_event(sheet_rows, offers, ev_ids, names)
        views_c, views_w = {}, {}
        for e, v in views.items():
            th, ta, st = P.terms(e)
            rv = v.rating
            rc = rmg.RatingView(rv.home * math.exp(th), rv.away * math.exp(ta), rv.source)
            views_c[e] = rmg.EventView(v.market_home, v.market_away, v.observations, v.rmse, rc, v.sides, v.home_name, v.away_name)
            rw = rc if rv.source == rmg.SOURCE_PURE else rv
            views_w[e] = rmg.EventView(v.market_home, v.market_away, v.observations, v.rmse, rw, v.sides, v.home_name, v.away_name)
            agg[day][f"rmg_view_source_{rv.source}"] += 1
            if round(v.d, 9) >= 1.0:
                agg[day]["rmg_matches_d_ge1_base"] += 1
            if round(views_c[e].d, 9) >= 1.0:
                agg[day]["rmg_matches_d_ge1_corr"] += 1
        for name, s, vw in (("base", base_set, views), ("corr", corr_set, views_c), ("corr_as_wired", corr_set, views_w)):
            for x in s:
                e = rmg.annotate(x, vw.get(int(x["sofascore_event_id"])))
                if e is not None:
                    tag = "in_scope" if x["market"] in P.SCOPE else "out_of_scope"
                    agg[day][f"rmg_{name}_{tag}"] += 1
                    lists[f"rmg_{name}_outcome"].append(outcome(K(x)))
        rec = [x for x in base_set if x.get("rating_market_gap")]
        agg[day]["rmg_recorded_field"] += len(rec)
        agg[day]["rmg_recorded_vs_base_recompute_agree"] += sum(
            1 for x in base_set if bool(x.get("rating_market_gap")) == (rmg.annotate(x, views.get(int(x["sofascore_event_id"]))) is not None))
        # ---- F. SAME_EVENT_DEDUP twins (hypothetical on these days; active from 11-08)
        boards = d["boards"]
        refused = [x for x in d["coupon_removed"]]

        def strip(s):
            return [{k2: v for k2, v in x.items() if k2 != "group_key"} for x in s]
        kb, rb = li.dedupe([], strip(base_set), boards, refused=strip(refused))
        kc, rc_ = li.dedupe([], strip(corr_set), boards, refused=strip(refused))

        def groups(s):
            g = collections.defaultdict(list)
            for x in s:
                ek = li.event_key(x, boards.get(int(x["sofascore_event_id"])))
                if ek is not None:
                    g[(int(x["sofascore_event_id"]), ek)].append(x)
            return g
        gb_, gc_ = groups(strip(base_set)), groups(strip(corr_set))
        kept_b = {K(x) for x in kb}
        kept_c = {K(x) for x in kc}
        for gk in set(gb_) | set(gc_):
            mb, mc = gb_.get(gk, []), gc_.get(gk, [])
            if max(len(mb), len(mc)) < 2:
                continue
            if not any(x["market"] in P.SCOPE for x in mb + mc):
                continue
            agg[day]["twin_groups_with_in_scope"] += 1
            conf_b = {K(x): x["confidence"] for x in mb}
            conf_c = {K(x): x["confidence"] for x in mc}
            changed = any(k in conf_c and abs(conf_c[k] - v) > 1e-9 for k, v in conf_b.items()) or set(conf_b) != set(conf_c)
            if changed:
                agg[day]["twin_groups_conf_or_membership_changed"] += 1
            wb = sorted(k for k in conf_b if k in kept_b)
            wc = sorted(k for k in conf_c if k in kept_c)
            if wb != wc:
                agg[day]["twin_groups_choice_changed"] += 1
                lists["twin_choice_changed"].append({"day": day, "base_kept": [list(k) for k in wb],
                                                     "corr_kept": [list(k) for k in wc],
                                                     "base_members": [[*K(x), x["confidence"], li.price(x)] for x in mb],
                                                     "corr_members": [[*K(x), x["confidence"], li.price(x)] for x in mc]})
        agg[day]["dedup_removed_base"] = len(rb)
        agg[day]["dedup_removed_corr"] = len(rc_)
        # corrected printed hit rate
        lists["corr_printed_in_scope_outcome"] += [outcome(K(x)) for x in corr_set if x["market"] in P.SCOPE]
        days_out[day] = dict(agg[day])
        print(variant, day, dict(agg[day]), flush=True)
    tot = collections.Counter()
    for v in agg.values():
        tot.update(v)
    abs_t = tstat["abs_t_sides"]

    def hr(name):
        o = lists.get(name, [])
        w, l = o.count("WIN"), o.count("LOSS")
        return {"n": len(o), "won": w, "lost": l, "other": len(o) - w - l,
                "hit_rate": round(w / (w + l), 4) if w + l else None}
    summary = {
        "variant": variant, "totals": dict(tot), "reproduction_chain_vs_recorded": dict(repro),
        "t": {"legs_status": dict(tstat["legs"]), "printed_status": dict(tstat["printed"]),
              "sides_ok": len(abs_t), "mean_abs_t_side": round(sum(abs_t) / len(abs_t), 5) if abs_t else None,
              "max_abs_t_side": round(max(abs_t), 5) if abs_t else None,
              "share_sides_t_nonzero": round(sum(1 for a in abs_t if a > 0) / len(abs_t), 4) if abs_t else None},
        "hit": {n: hr(n) for n in ("printed_in_scope_outcome", "corr_printed_in_scope_outcome", "flip_out_outcome",
                                   "entrant_outcome", "price_gap_base_outcome", "price_gap_corr_outcome",
                                   "maos_in_scope_outcome", "maos_out_of_scope_outcome",
                                   "rmg_base_outcome", "rmg_corr_outcome", "rmg_corr_as_wired_outcome")},
        "per_day": days_out,
        "flip_out_detail": lists["flip_out_detail"], "entrant_detail": lists["entrant_detail"],
        "twin_choice_changed": lists["twin_choice_changed"],
    }
    return summary


if __name__ == "__main__":
    out = {v: run(v) for v in sys.argv[1:]}
    for v, s in out.items():
        (D12 / f"d12_{v}.json").write_text(json.dumps(s, indent=1, default=str))
