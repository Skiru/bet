#!/usr/bin/env python3
"""Fit the confidence calibration: what the model says -> what actually happens.

This is a DIFFERENT question from K_PRICE, and the distinction is the whole
point of the confidence view. K_PRICE asks "does the model beat the price"; the
answer measured on 6,187 priced rows is no (Brier 0.2067 against the price's
0.1845). Calibration asks "when the model says 0.88, how often does it happen",
and the answer over 1,868,474 settled rows is: to within 0.3 pp, exactly 0.88 —
right up to about 0.90, above which the model runs out of resolution and tops
out near 0.92 whatever it claims.

An operator who accepts a shaded price is not asking the first question. He is
asking the second, and it needs its own fitted table rather than a reuse of the
reliability curve, which is bucketed on `p_central` for a different purpose and
only ever emits a correction where a 95% interval clears zero.

Usage:
    python -m scripts.sofa.fit_confidence --db-path data/sofa.db
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import line_curves as lc  # noqa: E402
from bet.sofa import live_only_curves as loc  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    CLASS_WOMEN,
    direction_key,
    match_class,
)
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.engine import has_calibratable_model  # noqa: E402
from bet.sofa.fit_meta import (  # noqa: E402
    carry_operator_keys,
    carry_separately_fitted_curves,
    fit_stamp,
    friendly_exclusion_sql,
)
from bet.sofa.listing_index import listed_events_by_id  # noqa: E402
from bet.sofa.market_mapper import is_derived  # noqa: E402
from bet.sofa.resolve import sofascore_gender  # noqa: E402
from bet.sofa.shot_detail import METRICS as SHOT_DETAIL_METRICS  # noqa: E402
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS  # noqa: E402

# Buckets are narrow at the top because that is where the operator lives and
# where the model stops being linear. Below 0.60 the confidence view does not
# look, so the grid does not waste resolution there.
EDGES = [0.0, 0.60, 0.70, 0.75, 0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 1.01]

# A per-market bucket below this is noise; it falls back to the pooled curve.
MIN_MARKET_BUCKET = 400
MIN_POOLED_BUCKET = 200
# ...but not to the pool alone. A market|direction bucket with at least this
# many rows of its own, and fewer than MIN_MARKET_BUCKET, is written to
# `thin_by_market_direction`, and CONFIDENCE reads the pool there capped at
# the bucket's own Wilson lower bound (Calibration.realised). Measured
# 2026-10-03 night: goals_1h_total had no cache-replay rows, its UNDER buckets
# 0.70-0.875 were 232-393 rows each and read pooled:football (0.8149 /
# 0.8408); six such legs printed on the 10-03 coupon. Leave-one-day-out over
# the live days 09-17..10-02 (data/night_2026-10-03/g1h/loo_thin_buckets.py)
# no rule for these buckets moved the coupon's ROI outside noise (standard
# -3.70% pooled vs -3.74% capped, wariant -4.64% vs -4.69%); the cap is the
# one that never claims more for a market than its own rows bound - for the
# WARIANT's goals_1h_total UNDER legs in the hole the pool claimed 0.828 and
# they realised 0.800 (n=80); capped, 0.822 claimed against 0.824 (n=51).
MIN_THIN_BUCKET = 100


def bucket_of(p: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def wilson_lo(k: int, n: int, z: float = 1.959964) -> float:
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def line_curve_section(
    counts: dict[str, dict[str, dict[int, list[int]]]],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """bet.sofa.line_curves' section: {"<market>|<DIR>": {"<line>": curve}},
    each line's buckets of >= MIN_MARKET_BUCKET rows, labelled and bounded as
    every other curve here (a thinner bucket is left out: CONFIDENCE reads
    the pooled direction curve there)."""
    out: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for key in sorted(counts):
        lines: dict[str, dict[str, dict[str, Any]]] = {}
        for line in sorted(counts[key], key=float):
            c = {f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}": {
                     "n": n, "realised": round(k / n, 4),
                     "realised_lo95": round(wilson_lo(k, n), 4)}
                 for b, (k, n) in sorted(counts[key][line].items())
                 if n >= MIN_MARKET_BUCKET}
            if c:
                lines[line] = c
        if lines:
            out[key] = lines
    return out


def event_class(event: dict[str, Any]) -> str | None:
    """The match class of one cached event, as run_confidence reads it."""
    tournament = event.get("tournament") or {}
    sport = ((tournament.get("category") or {}).get("sport") or {}).get("slug")
    if sport == "football":
        return CLASS_WOMEN if sofascore_gender(event) == "W" else None
    if sport == "tennis":
        # The category name only - what run_confidence reads. The players'
        # gender field would put Juniors girls (485 cached events) in
        # tennis_women here while the run cannot tell them from boys.
        category = str((tournament.get("category") or {}).get("name") or "")
        return match_class("tennis", category)
    return None


def load_event_classes(db_path: str) -> dict[int, str]:
    """sofascore_event_id -> match class, for the football events in the cache.

    Only CLASS_WOMEN today. Read with resolve.sofascore_gender - the teams'
    own gender field first, the competition name only as a fallback - over
    every cached listing, which is where both the replayed and the live rows'
    events live.
    """
    out: dict[int, str] = {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        has_listings = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'sofa_entity_events'"
        ).fetchone()
        if has_listings is None:
            return out  # no cache: no class is known, every row is unclassed
        # Pages and the listed-event index (listing_index.py): calibrate_from_cache
        # replays index-only matches too, and a women's one read as unclassed
        # would go into the men's curves. First classed page copy, as before;
        # a newer indexed copy wins.
        out = listed_events_by_id(con, event_class, kinds=("last",))
    finally:
        con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--out", default="config/sofa_confidence_calibration.json")
    ap.add_argument(
        "--classes-only", action="store_true",
        help="refit only the by_class section of --out and keep every other "
        "curve byte-for-byte (a class curve can be added between two builds "
        "of one day without moving any leg that is not in the class)",
    )
    ap.add_argument(
        "--line-curves-only", action="store_true",
        help="refit only the per-line curves (by_market_direction_line, "
        "bet.sofa.line_curves) of --out and keep every other curve "
        "byte-for-byte",
    )
    args = ap.parse_args()
    if args.classes_only and args.line_curves_only:
        print("REFUSED: --classes-only and --line-curves-only are two fits",
              file=sys.stderr)
        return 2
    if args.line_curves_only and Path(args.out).resolve() in {
            (_REPO / "config" / "sofa_confidence_calibration.json").resolve(),
            config_path("sofa_confidence_calibration.json").resolve()}:
        # the installed file changes only through install_line_curves.py
        # (backup, tests, restore): fit a staged copy
        print("REFUSED: --line-curves-only writes a staged copy, never the "
              "installed calibration (then install_line_curves.py)", file=sys.stderr)
        return 2
    classes = load_event_classes(args.db_path)
    # bet.sofa.line_curves: the keys whose curve is also fitted per line
    line_keys = lc.load_keys()
    per_line: dict[str, dict[str, dict[int, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))

    # Read-only: the fit only reads, and may run beside a day that writes.
    con = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    # A settled table without the event id (hand-built test fixtures) scores
    # exactly as before and classes nothing.
    columns = {r[1] for r in con.execute("PRAGMA table_info(sofa_settled_row)")}
    event_col = "sofascore_event_id" if "sofascore_event_id" in columns else "NULL"
    outcome_col = "outcome" if "outcome" in columns else "NULL"
    run_col = "run_date" if "run_date" in columns else "NULL"
    # A table without run_date (hand-built fixtures; the real one has it NOT
    # NULL, bet.sofa.db) cannot tell a replayed row from a live one: every
    # row counts as history there, as it did before the live-only rule.
    provenance_known = "run_date" in columns
    # Friendlies are out of SAMPLES and the rating, so they are out of the
    # curves too (2026-10-02). A table without competition_id cannot say.
    friendly_term = (
        friendly_exclusion_sql() if "competition_id" in columns else "1"
    )
    stamp = fit_stamp(con)
    rows = con.execute(
        f"""select market, line, direction, sample_size, sample_mean, sample_sd,
                  actual_value, p_central, sport, {event_col}, {outcome_col},
                  {run_col}
           from sofa_settled_row
           where sample_mean is not null and sample_sd is not null
             and sample_size > 0 and actual_value is not null
             and {friendly_term}"""
    )

    per_market: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    # Per market AND direction. OVER and UNDER of one rung are complements, so
    # a curve that pools them describes neither: measured 2026-09-25 in the
    # 0.70-0.75 bucket, goals_for OVER realised 0.646 (n=20,396) against UNDER
    # 0.817, and the pooled 0.7177 put "Pasto to score O0.5 @1.44" on the PDF
    # at x=1.03 when its own direction said x~0.93. The coupon is mostly
    # UNDER, so the pooled curve is an UNDER curve that OVER legs borrow.
    per_market_direction: dict[str, dict[int, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    pooled: dict[int, list[int]] = defaultdict(list)
    # Pooled per sport. A global pool is 95% football counting markets, so a
    # tennis metric borrowing it borrows football's shape — which is how
    # `sets_total` read 0.856 off 64,790 rows that were almost all goals and
    # corners. Silence about tennis is not the same as knowledge about it.
    pooled_by_sport: dict[str, dict[int, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # Per match class (CLASS_WOMEN): the same three curves over the class's
    # rows only. Measured 2026-09-30 on the cache replay, football goals at
    # p 0.80-0.85: men realised 0.806 (n=655,622), women 0.792 (n=67,531);
    # corners at 0.90-0.925 0.903 against 0.874. A women's leg read the
    # men-dominated curve and was printed 1.5-3.5 pp too confident.
    by_class_market: dict[str, dict[str, dict[int, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    by_class_direction: dict[str, dict[str, dict[int, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    by_class_sport: dict[str, dict[str, dict[int, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    # bet.sofa.live_only_curves: the curve keys a REPLAYED row reached (run_date
    # loc.REPLAY_RUN_DATE). Our settled days are an audit of a curve, never
    # its source (CLAUDE.md): a key reached by live SETTLE rows alone gets no
    # curve and is listed under loc.REFUSED_FIELD (found 2026-10-22: tennis
    # service points, per-set aces / double faults, tiebreaks had curves from
    # live rows only, docs/sofa/history/KRZYWE_TYLKO_Z_NASZYCH_DNI_2026-10-23.md).
    # A live row still counts in a key the replay reached - only the key's
    # provenance is judged here.
    hist_market: set[str] = set()
    hist_direction: set[str] = set()
    hist_sport: set[str] = set()
    hist_pooled: set[str] = set()
    hist_line: set[tuple[str, str]] = set()
    hist_class_market: dict[str, set[str]] = defaultdict(set)
    hist_class_direction: dict[str, set[str]] = defaultdict(set)
    hist_class_sport: dict[str, set[str]] = defaultdict(set)
    scored = 0
    for (market, line, direction, n, mean, sd, actual, stored_p, sport,
         event_id, outcome, run_date) in rows:
        if market in SHOT_DETAIL_METRICS:
            # SHEET prices the footballer shot-detail markets with their own
            # estimator (shot_detail.forecast), curved by fit_shot_detail and
            # the new-market gate (new_market_curves_fitted_from); the replay
            # prices them from a plain sample, so its rows describe another p.
            # Fitted here they replaced the installed left / right foot curves
            # with a 0-0.60 bucket (refit 2026-10-17: 793 / 1,053 rows) - the
            # carry fills only a key the fit lacks.
            continue
        if is_derived(market) and run_date == "cache-calibration":
            # A replayed joint (calibrate_from_cache: the tennis rating's
            # handicap_games / most_games, `--derived` football joints). Its
            # stored outcome is the grade - the actual is a margin or a min,
            # and "actual > line" is not it - so it is scored by the
            # outcome, into its own market's curves only: no pool, no class
            # (the reasons of the live rows below). Inert until something
            # reads a derived key's curve (a later epoch, after its measurement).
            if (outcome in ("WIN", "LOSS") and stored_p is not None
                    and not args.classes_only):
                hit = 1 if outcome == "WIN" else 0
                b = bucket_of(min(max(float(stored_p), 0.0), 1.0))
                per_market[market][b].append(hit)
                per_market_direction[direction_key(market, direction)][b].append(hit)
                hist_market.add(market)
                hist_direction.add(direction_key(market, direction))
                scored += 1
            continue
        if is_derived(market):
            # A joint / comparative market (both_over_, handicap_, most_) is
            # not a count against its line: its actual_value is a margin or
            # a min(a, b), and SETTLE grades it by side (run_settle.
            # _settle_derived - a handicap wins when margin > -line, most_ by
            # side or draw). Scored below as "actual > line" on a p rebuilt
            # from sample_mean/sd it disagreed with the stored outcome on
            # 351/1243 handicap and 197/431 most rows of 2026-09-30, and every
            # one of them fed pooled_by_sport and the class curves too.
            # run_confidence refuses derived legs anyway (no curve measured
            # for a joint), so they belong in no curve family.
            continue
        if not has_calibratable_model(market):
            # Neither a count, an empirical frequency, nor a modelled
            # non-count (the xG pair): no model at all.
            continue
        if stored_p is None:
            continue
        # Every row is keyed on its STORED p_central, because that is the
        # number run_confidence looks a leg up at (cal.realised(market,
        # row["p_central"], ...)). For a live row it is SHEET's p after the
        # prior shrink, the variance scale, the NB and the ratings; for a
        # cache-replay row it is calibrate_from_cache's, which since
        # 2026-10-02 calls SHEET's own estimator.
        #
        # Until 2026-10-02 only the empirical-frequency markets were keyed on
        # the stored p (they have no distribution to recompute from); every
        # other row was re-priced here from the RAW sample_mean / sample_sd -
        # no shrink, no scale - so a bucket held rows whose SHEET p was
        # elsewhere. The replay's stored p is compressed toward the prior by
        # K_CENTRE, and on the 10-02 refit candidate the throw_ins_total /
        # fouls_total 0.80-0.95 buckets were filled with rows SHEET would
        # have priced lower: +3-6 pp overstatement on the live legs.
        p = float(stored_p)
        p = min(max(p, 0.0), 1.0)
        hit = 1 if ((actual > line) if direction == "OVER" else (actual < line)) else 0
        b = bucket_of(p)
        # A player prop gets its own market and direction curves and enters
        # no pool: a pooled number must say what it pooled across, and since
        # 2026-10-03 a player leg reads its direction's curve or nothing
        # (confidence.PLAYER_PROP_MARKETS), so a pool never serves one either.
        # The cache replay adds ~1.2M player rows; they moved the football
        # pool by <=0.01 pp, but a team leg must not read player rows at all.
        # D2: a rating-only market (the tennis match winner) is a win
        # probability, not a count - it enters no pool either
        # (confidence.OWN_CURVE_ONLY never reads one for it).
        pools_it = (not market.startswith("player_")
                    and market not in RATING_ONLY_MARKETS)
        replayed = run_date == loc.REPLAY_RUN_DATE or not provenance_known
        dkey = direction_key(market, direction)
        klass = classes.get(event_id)
        if klass is not None:
            by_class_market[klass][market][b].append(hit)
            by_class_direction[klass][dkey][b].append(hit)
            if pools_it:
                by_class_sport[klass][sport][b].append(hit)
            if replayed:
                hist_class_market[klass].add(market)
                hist_class_direction[klass].add(dkey)
                if pools_it:
                    hist_class_sport[klass].add(sport)
        if args.classes_only:
            scored += 1
            continue
        # bet.sofa.line_curves: men's football rows of a listed key, per line
        # (a class row reads its class's curves, never a line curve)
        if klass is None and sport == lc.SPORT and line_keys:
            if dkey in line_keys:
                label = lc.line_label(line)
                cell = per_line[dkey][label][b]
                cell[0] += hit
                cell[1] += 1
                if replayed:
                    hist_line.add((dkey, label))
        if args.line_curves_only:
            scored += 1
            continue
        per_market[market][b].append(hit)
        per_market_direction[dkey][b].append(hit)
        if pools_it:
            pooled[b].append(hit)
            if sport:
                pooled_by_sport[sport][b].append(hit)
        if replayed:
            hist_market.add(market)
            hist_direction.add(dkey)
            if pools_it:
                hist_pooled.add(loc.POOLED_ALL)
                if sport:
                    hist_sport.add(sport)
        scored += 1

    def curve(
        counts: dict[int, list[int]], floor: int, below: int | None = None
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for b, hits in sorted(counts.items()):
            if len(hits) < floor or (below is not None and len(hits) >= below):
                continue
            k, n = sum(hits), len(hits)
            out[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"] = {
                "n": n,
                "realised": round(k / n, 4),
                # The operator is told the LOWER bound, not the point estimate.
                # A confidence view that quotes its own best case is the same
                # mistake as a coupon that ranks by surplus.
                "realised_lo95": round(wilson_lo(k, n), 4),
            }
        return out

    line_refused: list[str] = []
    line_section = loc.refuse_lines(line_curve_section(per_line), hist_line,
                                    line_refused)
    line_fitted_from = {"db_path": args.db_path, "keys": sorted(line_keys),
                        "min_market_bucket": MIN_MARKET_BUCKET,
                        loc.REFUSED_FIELD: line_refused, **stamp}
    if args.line_curves_only:
        prior_doc: dict[str, Any] = json.loads(
            Path(args.out).read_text(encoding="utf-8"))
        prior_doc[lc.SECTION] = line_section
        prior_doc[lc.FITTED_FROM] = line_fitted_from
        write_atomic(Path(args.out), json.dumps(prior_doc, indent=1) + "\n")
        print(json.dumps({
            "stage": "FIT_CONFIDENCE", "verdict": "OK", "mode": "line-curves-only",
            "metrics": {"scored_rows": scored, "keys": len(line_section),
                        "lines": sum(len(v) for v in line_section.values()),
                        "live_only_refused": len(line_refused)},
            loc.REFUSED_FIELD: line_refused,
            "output_path": args.out,
        }))
        return 0
    refused: list[str] = []
    by_direction = loc.refuse({
        m: c
        for m, counts in per_market_direction.items()
        if (c := curve(counts, MIN_MARKET_BUCKET))
    }, hist_direction, "by_market_direction", refused)
    # The buckets by_direction leaves out for thinness, where the market's
    # own rows still bound what a pool may claim for it (MIN_THIN_BUCKET).
    # Player props read no pool, so they have no use for one.
    thin_by_direction = loc.refuse({
        m: c
        for m, counts in per_market_direction.items()
        if not m.startswith("player_")
        and (c := curve(counts, MIN_THIN_BUCKET, below=MIN_MARKET_BUCKET))
    }, hist_direction, "thin_by_market_direction", refused)
    class_refused: list[str] = []
    by_class = {
        klass: {
            "by_market": loc.refuse({
                m: c for m, counts in by_class_market[klass].items()
                if (c := curve(counts, MIN_MARKET_BUCKET))
            }, hist_class_market[klass], "by_market", class_refused, klass),
            "by_market_direction": loc.refuse({
                m: c for m, counts in by_class_direction[klass].items()
                if (c := curve(counts, MIN_MARKET_BUCKET))
            }, hist_class_direction[klass], "by_market_direction",
                class_refused, klass),
            "thin_by_market_direction": loc.refuse({
                m: c for m, counts in by_class_direction[klass].items()
                if not m.startswith("player_")
                and (c := curve(counts, MIN_THIN_BUCKET, below=MIN_MARKET_BUCKET))
            }, hist_class_direction[klass], "thin_by_market_direction",
                class_refused, klass),
            "pooled_by_sport": loc.refuse({
                sp: c for sp, counts in by_class_sport[klass].items()
                if (c := curve(counts, MIN_POOLED_BUCKET))
            }, hist_class_sport[klass], "pooled_by_sport", class_refused, klass),
        }
        for klass in sorted(by_class_sport)
    }
    if args.classes_only:
        prior: dict[str, Any] = json.loads(Path(args.out).read_text(encoding="utf-8"))
        prior["by_class"] = by_class
        prior["by_class_fitted_from"] = {
            "db_path": args.db_path, "scored_rows": scored,
            "classes": {k: len(v["by_market"]) for k, v in by_class.items()},
            loc.REFUSED_FIELD: class_refused,
            **stamp,
        }
        write_atomic(Path(args.out), json.dumps(prior, indent=1) + "\n")
        print(json.dumps({
            "stage": "FIT_CONFIDENCE", "verdict": "OK", "mode": "classes-only",
            "metrics": prior["by_class_fitted_from"], "output_path": args.out,
        }))
        return 0
    doc: dict[str, Any] = {
        "_doc": (
            "What the model's probability turns into in practice. Fitted by "
            "scripts/sofa/fit_confidence.py. A market with too few rows in a "
            "bucket falls back to its SPORT's pooled curve, then the global "
            "one; a bucket absent from all three means the confidence view "
            "refuses the row rather than guessing. A market is never served "
            "from a pool ABOVE the top of its own measured range - see "
            "Calibration.realised. by_market_direction is the same curve "
            "split by OVER/UNDER and is read first; the two directions of one "
            "rung are complements, so the pooled curve describes neither. "
            "thin_by_market_direction holds the direction buckets with "
            "min_thin_bucket..min_market_bucket rows: where the lookup falls "
            "to a pool, the pool is capped at that bucket's realised_lo95; "
            "from the 2026-10-05 stats-only epoch so is the by_market curve "
            "(both directions pooled) - see Calibration.cap_market_by_thin."
        ),
        "fitted_from": {"db_path": args.db_path, "scored_rows": scored, **stamp},
        "min_market_bucket": MIN_MARKET_BUCKET,
        "pooled": loc.refuse(
            {loc.POOLED_ALL: c} if (c := curve(pooled, MIN_POOLED_BUCKET)) else {},
            hist_pooled, "pooled", refused).get(loc.POOLED_ALL, {}),
        "pooled_by_sport": loc.refuse({
            sp: c
            for sp, counts in pooled_by_sport.items()
            if (c := curve(counts, MIN_POOLED_BUCKET))
        }, hist_sport, "pooled_by_sport", refused),
        "by_market": loc.refuse({
            m: c
            for m, counts in per_market.items()
            if (c := curve(counts, MIN_MARKET_BUCKET))
        }, hist_market, "by_market", refused),
        "by_market_direction": by_direction,
        lc.SECTION: line_section,
        lc.FITTED_FROM: line_fitted_from,
        "min_thin_bucket": MIN_THIN_BUCKET,
        "thin_by_market_direction": thin_by_direction,
        "by_class": by_class,
        "by_class_fitted_from": {
            "db_path": args.db_path, "scored_rows": scored,
            "classes": {k: len(v["by_market"]) for k, v in by_class.items()},
            **stamp,
        },
    }
    # The full fit rebuilds the file from the DB; an operator-owned key
    # (admitted_player_markets) is not in the DB and must survive it.
    out_path = Path(args.out)
    carried: list[str] = []
    if out_path.exists():
        prior = json.loads(out_path.read_text(encoding="utf-8"))
        carry_operator_keys(doc, prior)
        # the separately fitted curves (new markets, the tennis winner):
        # not in the DB either, so a refit must not drop them
        carried = carry_separately_fitted_curves(doc, prior)
    # A separately fitted curve (fit_meta.SEPARATE_FIT_META: its own history
    # fit) may fill a key this fit refused: it is no longer without a curve.
    live_only = sorted(e for e in (*refused, *line_refused, *class_refused)
                       if not loc.present(doc, e))
    doc[loc.REFUSED_FIELD] = live_only
    write_atomic(out_path, json.dumps(doc, indent=1) + "\n")
    print(
        json.dumps(
            {
                "stage": "FIT_CONFIDENCE",
                "verdict": "OK",
                "metrics": {
                    "scored_rows": scored,
                    "markets": len(doc["by_market"]),
                    "market_directions": len(by_direction),
                    "thin_market_directions": len(thin_by_direction),
                    "pooled_buckets": len(doc["pooled"]),
                    "pooled_by_sport": {
                        sp: len(c) for sp, c in doc["pooled_by_sport"].items()
                    },
                    "carried_separate_curves": len(carried),
                    "live_only_refused": len(live_only),
                },
                loc.REFUSED_FIELD: live_only,
                "output_path": args.out,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
