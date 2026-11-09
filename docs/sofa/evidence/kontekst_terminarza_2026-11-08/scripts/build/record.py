"""Recording replay (r3 D4) of calibrate_from_cache on the DB copy, live code
untouched (monkeypatched module globals, run_window.py pattern).

Per _settle_centred call one record: event, ts, competition, market, subject,
book (0 none / 1 plain / 2 form table), n, mean, variance, shrunk centre,
hooked (final) centre, season-phase multiplier, dispersion (alpha, family),
empirical flag, tennis rating flag; actual in a separate column store.
Per football forecast (every event, both books): the rating centres of
BASE_METRICS home / away and the home supremacy. Per tennis forecast: p_home.

Records stream to OUT/<tier>/<YYYY-MM>.pkl.gz chunks (tier dev / exam);
exam outcomes (actual) go to OUT/exam_y/ only (G2), never beside exam X.

--smoke: additionally recompute every returned row's p_central from the
record with the pure engine functions and count |diff| > 1e-9 (D4).

usage: record.py OUT --from YYYY-MM-DD [--to YYYY-MM-DD] [--smoke]
"""
from __future__ import annotations

import argparse
import gzip
import math
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO), str(REPO / "scripts/sofa")]
import calibrate_from_cache as cfc  # noqa: E402
from bet.sofa import engine  # noqa: E402
from bet.sofa.football_rating import BASE_METRICS  # noqa: E402

EXAM_FROM = 1767225600  # 2026-01-01 00:00Z
COPY = REPO / "data/refit_2026-11-08_schedule/sofa_copy.db"

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--from", dest="emit_from", required=True)
ap.add_argument("--to", dest="emit_to", default=None)
ap.add_argument("--smoke", action="store_true")
ap.add_argument("--players", default="skip")
args = ap.parse_args()
OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)


def month(ts: int) -> str:
    return time.strftime("%Y-%m", time.gmtime(ts))


class Sink:
    """Buffers per (tier, month) and flushes a chunk file every LIMIT records."""

    LIMIT = 400_000

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.buf: dict[tuple[str, str], list[Any]] = defaultdict(list)
        self.parts: dict[tuple[str, str], int] = defaultdict(int)
        self.count = 0

    def add(self, tier: str, ts: int, rec: Any) -> None:
        key = (tier, month(ts))
        self.buf[key].append(rec)
        self.count += 1
        if len(self.buf[key]) >= self.LIMIT:
            self.flush(key)

    def flush(self, key: tuple[str, str]) -> None:
        recs = self.buf.pop(key, None)
        if not recs:
            return
        tier, mon = key
        d = OUT / tier / self.kind
        d.mkdir(parents=True, exist_ok=True)
        i = self.parts[key]
        self.parts[key] += 1
        with gzip.open(d / f"{mon}_{i:03d}.pkl.gz", "wb", compresslevel=3) as f:
            pickle.dump(recs, f, protocol=pickle.HIGHEST_PROTOCOL)

    def close(self) -> None:
        for key in list(self.buf):
            self.flush(key)


ROWS = Sink("rows")        # X: predictors (no actual for exam)
YS = Sink("y")             # outcomes; tier "exam_y" for exam rows
FC = Sink("forecasts")
STATE: dict[str, Any] = {"book": 0, "phase_mult": 1.0, "seen_fc": set()}
SMOKE = {"rows": 0, "bad": 0, "max": 0.0, "checked_records": 0}


def tier_of(ts: int) -> str:
    return "exam" if ts >= EXAM_FROM else "dev"


# --- book tag -------------------------------------------------------------
orig_match_rows = cfc._match_rows


def match_rows(match, history, baselines, engine_constants, correlations,
               rating, joint_bases, football):  # type: ignore[no-untyped-def]
    STATE["book"] = 0 if football is None else (2 if football.rules.form_table else 1)
    yield from orig_match_rows(match, history, baselines, engine_constants,
                               correlations, rating, joint_bases, football)


cfc._match_rows = match_rows

# --- season-phase multiplier ------------------------------------------------
orig_phase = cfc.apply_season_phase


def phase(centre, market, ph, table):  # type: ignore[no-untyped-def]
    out = orig_phase(centre, market, ph, table)
    STATE["phase_mult"] = (out[0] / centre) if centre else 1.0
    return out


cfc.apply_season_phase = phase

# --- football forecasts ------------------------------------------------------
orig_ffc = cfc.FootballRatingReplay.forecast


def ffc(self, match):  # type: ignore[no-untyped-def]
    fc = orig_ffc(self, match)
    if fc is None:
        return fc
    book = 2 if self.rules.form_table else 1
    key = (match.event_id, book)
    if key not in STATE["seen_fc"]:
        STATE["seen_fc"].add(key)
        cents = {}
        for m in BASE_METRICS:
            for side in ("side_a", "side_b"):
                c = fc.centre(m, side)
                cents[(m, side)] = None if c is None else float(c[0])
        rec = (match.event_id, match.timestamp, match.competition_id,
               match.home_id, match.away_id, book, cents, fc.supremacy("side_a"))
        FC.add(tier_of(match.timestamp), match.timestamp, rec)
    return fc


cfc.FootballRatingReplay.forecast = ffc

orig_tfc = cfc.RatingReplay.forecast


def tfc(self, match):  # type: ignore[no-untyped-def]
    fc = orig_tfc(self, match)
    key = (match.event_id, 0)
    if fc is not None and key not in STATE["seen_fc"]:
        STATE["seen_fc"].add(key)
        rec = (match.event_id, match.timestamp, None, match.home_id,
               match.away_id, 0, {"p_home": float(fc.p_home)}, None)
        FC.add(tier_of(match.timestamp), match.timestamp, rec)
    return fc


cfc.RatingReplay.forecast = tfc

# --- settle records ------------------------------------------------------------
orig_settle = cfc._settle_centred


def settle(match, market, subject, actual, sample, baselines, engine_constants,
           rating_p=None, centre_hook=None):  # type: ignore[no-untyped-def]
    got: dict[str, float] = {}

    def hook(c: float) -> float:
        STATE["phase_mult"] = 1.0
        got["shrunk"] = c
        out = centre_hook(c) if centre_hook is not None else c
        got["final"] = out
        got["phase"] = STATE["phase_mult"]
        return out

    rows = orig_settle(match, market, subject, actual, sample, baselines,
                       engine_constants, rating_p, hook)
    n = len(sample)
    if n < cfc.MIN_SAMPLE or "final" not in got:
        return rows
    disp = (cfc.COUNT_DISPERSION.read(match.sport, market, match.competition_id)
            if cfc.COUNT_DISPERSION is not None else None)
    mean = sum(sample) / n
    var = (sum((v - mean) ** 2 for v in sample) / (n - 1)) if n > 1 else 0.0
    emp = engine.uses_empirical_frequency(market)
    ts = match.timestamp
    rec = (match.event_id, ts, match.competition_id, match.sport, market, subject,
           STATE["book"], n, mean, var, got["shrunk"], got["final"], got["phase"],
           None if disp is None else (disp.alpha, disp.family),
           emp, rating_p is not None, tuple(sample) if emp else None,
           match.home_id, match.away_id, len(rows))
    tier = tier_of(ts)
    ROWS.add(tier, ts, rec)
    YS.add("exam_y" if tier == "exam" else "dev", ts,
           (match.event_id, market, subject, STATE["book"], float(actual)))
    if args.smoke and rows:
        SMOKE["checked_records"] += 1
        centre = got["final"]
        spread = engine.sheet_predictive_sd(market, match.sport, mean, var, n,
                                            centre, disp)
        for r in rows:
            if rating_p is not None:
                continue
            boundary = cfc.winning_boundary(r.line, r.direction)
            if emp:
                p = engine.p_empirical_centred_raw(list(sample), boundary,
                                                   r.direction, centre - mean)
            else:
                p = engine.sheet_count_p_raw(market, centre, spread, boundary,
                                             r.direction, disp)
            # the stored p_central is round(p_raw, 6) (calibrate_from_cache)
            d = abs(round(p, 6) - r.p_central)
            SMOKE["rows"] += 1
            SMOKE["max"] = max(SMOKE["max"], d)
            if not d <= 1e-9 or math.isnan(d):
                SMOKE["bad"] += 1
    return rows


cfc._settle_centred = settle

FLAGS = [
    "--halves", "include", "--player-starts-only",
    "--derived", "cards_points,goals,corners,shots_on_target",
    "--count-dispersion", "--cards-correlation", "--per-market-k",
    "--tennis-scoped-table", "--tennis-rating", "include",
    "--football-rating", "--rated-scope", "--venue-prior", "--game-state",
    "--rating-weight", "--season-phase", "--opponent-correction",
    "--tennis-set-ratings", "--cup-strength", "--sample-cup-strength",
    "--tennis-sample-scope", "--goals-stretch", "--count-stretch",
    "--player-stretch", "--closeness-stretch", "--player-coverage",
    "--awarded-excluded", "--referee", "--player-share",
    "--tennis-score-winner", "--sample-conflict-cut", "--form-table-per-family",
]
sys.argv = ["calibrate_from_cache.py", "--db-path", str(COPY),
            "--runs-dir", str(REPO / "runs/sofa"), *FLAGS,
            "--players", args.players, "--from", args.emit_from, "--no-write"]
if args.emit_to:
    sys.argv += ["--to", args.emit_to]
if args.players == "skip":
    # --player-share only feeds player rows (team centres untouched in live_centre)
    sys.argv.remove("--player-share")
print("argv", " ".join(sys.argv[1:]), flush=True)
t = time.time()
rc = None
try:
    rc = cfc.main()
finally:
    for s in (ROWS, YS, FC):
        s.close()
    summary = {"rc": rc, "records": ROWS.count, "forecasts": FC.count,
               "secs": round(time.time() - t), "smoke": SMOKE, "argv": sys.argv}
    (OUT / "summary.pkl").write_bytes(pickle.dumps(summary))
    print("SUMMARY", summary, flush=True)
