"""D12: CONFIDENCE's p -> confidence chain for one football row, as
run_confidence.py main() computes it (cal.realised -> line evidence read ->
floor), with today's config files (the line evidence of each day is not kept
on disk - see the report)."""
from __future__ import annotations
import dataclasses, sys
from datetime import datetime
from pathlib import Path
REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa import epochs, football_sim_curves, live_only_curves  # noqa: E402
from bet.sofa.confidence import (COUPON_PROFILE, Calibration, calibration_path_for,  # noqa: E402
                                 curve_market, direction_key, is_derived, match_class,
                                 reads_catch_all_bucket, one_sided_single, overround)
from bet.sofa.epochs import (derived_curves, leg_floor, line_curves, line_evidence,  # noqa: E402
                             line_evidence_v2, pool_neighbour_cap, one_sided_singles)
from bet.sofa.epochs import stats_only as stats_only_epoch  # noqa: E402
from bet.sofa.football_1x2_dnb import leg_class as r1x2_class  # noqa: E402
from bet.sofa.football_score_markets import leg_class as score_class  # noqa: E402
from bet.sofa.line_curves import leg_line  # noqa: E402
from bet.sofa.line_evidence import LineEvidence, evidence_key  # noqa: E402

_cal: dict = {}
_ev: dict = {}


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class Day:
    def __init__(self, date: str, now: datetime):
        self.date, self.now = date, now
        path = calibration_path_for(date, now)
        so = stats_only_epoch(date, now)
        k = (str(path), epochs.live_only_curve_refused(date, now), epochs.football_sim(date, now),
             so, pool_neighbour_cap(date, now))
        if k not in _cal:
            cal = Calibration.load(path)
            cal = live_only_curves.for_day(cal, date, now)
            cal = football_sim_curves.for_day(cal, date, now)
            if so:
                cal = dataclasses.replace(cal, gap_shrink_k=0.0, cap_market_by_thin=True)
            if pool_neighbour_cap(date, now):
                cal = dataclasses.replace(cal, cap_pool_by_neighbour=True)
            _cal[k] = cal
        self.cal = _cal[k]
        self.calibration_path = str(path)
        if line_evidence(date, now):
            ek = (line_evidence_v2(date, now), epochs.bucket_design_effect(date, now),
                  tuple(sorted(epochs.price_gap_offset_sports(date, now))))
            if ek not in _ev:
                _ev[ek] = LineEvidence.load(v2=ek[0], bucket_deff=ek[1], price_gap_sports=frozenset(ek[2]))
            self.ev = _ev[ek]
        else:
            self.ev = None
        self.per_line = line_curves(date, now)
        self.derived = derived_curves(date, now)
        self.one_sided_ok = one_sided_singles(date, now)

    def klass(self, row, fx, board):
        k = match_class("football", (fx or {}).get("competition_name"), board,
                        (fx or {}).get("competition_id"))
        k = r1x2_class(row, k)
        return score_class(row, k)

    def confidence(self, row, p: float, odds: float, klass):
        """(confidence, source, n, line_offset, band_cap) or (None, reason)."""
        r = dict(row, p_central=p)
        hit = None if (self.ev is not None and is_derived(r["market"]) and not self.derived) \
            else self.cal.realised(curve_market(r), p, "football", r["direction"], klass,
                                   line=leg_line(r, self.per_line))
        off, cap = 0.0, None
        if self.ev is not None:
            rd = self.ev.read("football", evidence_key(direction_key(r["market"], r["direction"]), klass),
                              float(p), hit, float(odds))
            if rd is None:
                return None, "NO_LINE_EVIDENCE"
            hit = (rd.value, rd.source, rd.n)
            off, cap = rd.offset, rd.band_cap
        if hit is None:
            return None, "NOT_CALIBRATED"
        return (hit[0], hit[1], hit[2], off, cap), None

    def gate(self, row, p: float, odds: float, klass, rung_overround, one_sided_market: bool):
        """Every p-dependent gate of CONFIDENCE plus prints_as_single.
        -> dict(conf, source, n, status) status in PRINTABLE / reason."""
        c, why = self.confidence(row, p, odds, klass)
        if c is None:
            return {"conf": None, "status": why}
        conf, src, n, off, cap = c
        out = {"conf": conf, "source": src, "n": n}
        fl = leg_floor(row, self.date, COUPON_PROFILE.floor, self.now)
        out["floor"] = fl
        if conf < fl:
            out["status"] = "BELOW_CONFIDENCE_FLOOR"
        elif reads_catch_all_bucket(p):
            out["status"] = "CATCH_ALL_BUCKET"
        elif not COUPON_PROFILE.clears_price(conf, odds):
            out["status"] = "NEGATIVE_LEG_EV"
        else:
            leg = {"overround": rung_overround, "one_sided_market": one_sided_market,
                   "calibrated_on": src, "calibration_n": n}
            single = COUPON_PROFILE.single_is_fairly_priced(rung_overround) or (
                self.one_sided_ok and one_sided_single(leg))
            out["status"] = "PRINTABLE" if single else (
                "ONE_SIDED_NOT_ADMITTED" if rung_overround is None else "MARGIN_TOO_HIGH")
        return out
