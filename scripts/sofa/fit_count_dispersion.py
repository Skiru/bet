#!/usr/bin/env python3
"""Fit the football count dispersion (config/sofa_count_dispersion.json).

Track A2 -> W2 (2026-10-08). SHEET prices a football count's spread from the
sample variance of 8-10 matches; a dispersion fitted on the history beat it on
52 of 52 markets out of sample (docs/sofa/evidence/count_families_2026-10-08.md).
This fits what the switch `epochs.COUNT_DISPERSION_FROM_UTC` reads:

    variance = mu + alpha * mu^2     around SHEET's own centre mu

with alpha per market and per competition (`nb_lg`: the competition's moment
estimate pooled toward the market's maximum-likelihood alpha with `kc` cases'
worth of weight, `kc` chosen on the validation slice by the ladder log-loss the
measurement used), the negative binomial as the family and the floored normal
for `shots_total` (`norm_lg`). The estimation code is the measurement's own
(`count_dispersion_estimation`, `measure_count_families`); the cases are the
cache replay's (`measure_count_families collect`: calibrate_from_cache.iter_rows
with its `_settle_sample` swapped for a collector), so the history, the
same-competition goal samples, the K_CENTRE shrink and the friendly exclusion
are SHEET's.

Read-only on the database (`mode=ro`); writes only --out (default
config/sofa_count_dispersion.json) and only with --write (without it the run
is a dry run that prints the target); the file is INERT while the switch is None.
Installing the switch and refitting the curves on it is the operator's call.

    # the cases once (~10 min, ~4.4 GB), then the fit (~5 min)
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_count_dispersion.py \\
        --before 2026-10-08 --cases data/refit_2026-10-08/count_cases [--write]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.count_dispersion import (  # noqa: E402
    CONFIG_FILE,
    FAMILY_NB,
    FAMILY_NORMAL,
    MIN_COMPETITION_CASES,
    NORMAL_MARKETS,
    pooled_alpha,
)
from bet.sofa.engine import NEGATIVE_BINOMIAL_METRICS  # noqa: E402
from scripts.sofa import measure_count_families as mcf  # noqa: E402
from scripts.sofa.count_dispersion_estimation import (  # noqa: E402
    mle_alpha,
    moment_stats,
)

EVIDENCE = "docs/sofa/evidence/count_families_2026-10-08.md"
EVIDENCE_JSON = "docs/sofa/evidence/count_families_2026-10-08.json"
METHOD = (
    "nb_lg (A2): variance = mu + alpha mu^2; alpha(market, competition) = the "
    "competition's moment estimate pooled toward the market's MLE alpha with kc "
    "cases' worth of weight (kc by validation ladder log-loss); family nb, "
    "normal (floored, as engine.sheet_count_p_raw) for shots_total"
)
KC_GRID = (10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0)
VAL_MONTHS = 6
MIN_TRAIN_CASES = 2000  # the measurement's TOO_THIN bar (train_fit)
MLE_CASES = 60000
VAL_CASES = 40000


def _durable(path: Path | str | None) -> str | None:
    """A path as provenance: relative to the repository when inside it, else
    only its last component (a scratch / temp directory is not durable)."""
    if path is None:
        return None
    p = Path(path)
    try:
        return str(p.resolve().relative_to(_REPO))
    except ValueError:
        return p.name


def cases_fingerprint(cases_dir: Path) -> str | None:
    """sha256 of the case set's identity: meta.json and the name and size of
    every cases_*.npz (the files themselves are GBs)."""
    meta = cases_dir / "meta.json"
    if not meta.exists():
        return None
    h = hashlib.sha256(meta.read_bytes())
    for f in sorted(cases_dir.glob("cases_*.npz")):
        h.update(f"{f.name}:{f.stat().st_size}".encode())
    return h.hexdigest()


def _day_ts(day: str) -> float:
    return datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp()


def val_start_for(before: str, months: int = VAL_MONTHS) -> str:
    d = datetime.fromisoformat(before).replace(tzinfo=UTC)
    return (d - timedelta(days=round(30.4375 * months))).date().isoformat()


def fit_market(
    market: str, cases: mcf.Cases, before_ts: float, val_ts: float
) -> dict[str, Any]:
    """One market's cell, or {"status": "TOO_THIN", ...}. Never sees a case
    at or after `before_ts`; `kc` is chosen on [val_ts, before_ts) from an
    alpha fitted before val_ts, the final alpha on everything before."""
    train_all = cases.take(cases.ts < before_ts)
    train_fit = cases.take(cases.ts < val_ts)
    val = cases.take((cases.ts >= val_ts) & (cases.ts < before_ts))
    family = FAMILY_NORMAL if market in NORMAL_MARKETS else FAMILY_NB
    cell: dict[str, Any] = {
        "family": family, "n_cases": len(train_all), "n_val_cases": len(val),
    }
    if len(train_fit) < MIN_TRAIN_CASES or len(train_all) < MIN_TRAIN_CASES:
        cell["status"] = "TOO_THIN"
        return cell

    nb_listed = market in NEGATIVE_BINOMIAL_METRICS
    fam_name = "norm_lg" if family == FAMILY_NORMAL else "nb_lg"
    kc = 100.0  # the measurement's own default, kept when there is no validation
    if len(val):
        sub = mcf._sub(val, VAL_CASES, seed=1)
        fit1 = _market_fit(train_fit)
        kc = min(
            KC_GRID,
            key=lambda k: mcf.total_ll(mcf.score_families(
                (fam_name,), market, nb_listed, sub, fit1, mcf.Hyper(kc=k)
            )[fam_name]),
        )
    fit = _market_fit(train_all)
    comps, counts = np.unique(train_all.comp, return_counts=True)
    by_comp: dict[str, float] = {}
    for comp, cnt in zip(comps.tolist(), counts.tolist(), strict=True):
        if comp == 0 or cnt < MIN_COMPETITION_CASES:
            continue
        a, b = fit.comp_ab.get(int(comp), (0.0, 0.0))
        by_comp[str(int(comp))] = round(pooled_alpha(
            a, b, mom=fit.alpha_mom, mle=fit.alpha, bmean=fit.bmean, kc=kc), 5)
    cell.update({
        "status": "OK", "alpha": round(fit.alpha, 5), "alpha_moment": round(
            fit.alpha_mom, 5), "kc": kc, "n_competitions": len(by_comp),
        "by_competition": by_comp,
    })
    return cell


def _market_fit(train: mcf.Cases) -> mcf.Fit:
    """The part of mcf.Fit the nb_lg / norm_lg families read."""
    fit = mcf.Fit()
    fit.alpha_mom, fit.bmean, fit.comp_ab = moment_stats(
        train.comp, train.centre, train.y)
    s = mcf._sub(train, MLE_CASES)
    fit.alpha = mle_alpha(s.y, s.centre)
    return fit


def evidence_gate(
    evidence: dict[str, Any] | None, market: str
) -> tuple[bool, list[float] | None]:
    """(admitted, d log-loss x1000 [point, lo, hi] against the sample variance)
    from the measurement's JSON: the family this fit uses (nb_lg; norm_lg for
    shots_total) must have a log-loss interval below zero and both halves of
    the test window below zero. A market the measurement did not score
    (TOO_THIN, absent) is not admitted. No evidence file = no gate (None)."""
    if evidence is None:
        return True, None
    entry = evidence.get(market)
    if entry is None or entry.get("status") != "OK":
        return False, None
    fam = "norm_lg" if market in NORMAL_MARKETS else "nb_lg"
    f = (entry.get("families") or {}).get(fam)
    if f is None:
        return False, None
    d = [round(x * 1e3, 3) for x in f["d_ll"]]
    ok = d[2] < 0.0 and all(h < 0.0 for h in f.get("half_d_ll", [0.0]))
    return ok, d


def load_evidence(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    out: dict[str, Any] = json.loads(path.read_text())["main"]["markets"]
    return out


def build_config(
    cells: dict[str, dict[str, Any]], *, before: str, val_start: str,
    cases_dir: Path, max_case_ts: float, db_path: str | None,
    evidence: dict[str, Any] | None = None,
    fingerprint: str | None = None, min_case_ts: float | None = None,
) -> dict[str, Any]:
    markets: dict[str, dict[str, Any]] = {}
    not_admitted: list[str] = []
    for m, c in sorted(cells.items()):
        if c.get("status") != "OK":
            continue
        ok, d = evidence_gate(evidence, m)
        if not ok:
            not_admitted.append(m)
            continue
        cell = {k: v for k, v in c.items() if k not in ("status", "n_val_cases")}
        if d is not None:
            cell["evidence_d_logloss_x1000"] = d
        markets[m] = cell
    return {
        "_doc": (
            "Football count dispersion: variance = mu + alpha mu^2 around "
            "SHEET's centre, alpha per market and competition (bet.sofa."
            "count_dispersion). INERT while epochs.COUNT_DISPERSION_FROM_UTC "
            "is None (nothing reads it); written by "
            "scripts/sofa/fit_count_dispersion.py. A competition absent from "
            "a market's by_competition reads the market's alpha; a market "
            "absent from this file keeps the sample variance."
        ),
        "inert_until": "epochs.COUNT_DISPERSION_FROM_UTC is set by the operator",
        "fitted_from": {
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "before": before,
            "validation_start": val_start,
            "max_case_date": datetime.fromtimestamp(
                max_case_ts, UTC).date().isoformat(),
            "min_case_date": (
                datetime.fromtimestamp(min_case_ts, UTC).date().isoformat()
                if min_case_ts is not None else None),
            "cases_fingerprint_sha256": fingerprint,
            "method": METHOD,
            "evidence": EVIDENCE,
            "evidence_json": EVIDENCE_JSON,
            "cases_dir": _durable(cases_dir),
            "db_path": _durable(db_path),
            "db_access": "read-only (mode=ro); no live row touched",
            "markets_fitted": len(markets),
            "markets_too_thin": sorted(
                m for m, c in cells.items() if c.get("status") != "OK"),
            "markets_not_admitted_by_evidence": not_admitted,
            "admission_rule": (
                "the measurement's d log-loss [95%] of the family used and both "
                "halves of its test window below zero (evidence_gate)"
                if evidence is not None else "none (no evidence file)"),
        },
        "unfitted_constants": [
            "KC_GRID", "VAL_MONTHS", "MIN_COMPETITION_CASES", "MIN_TRAIN_CASES",
        ],
        "markets": markets,
    }


LIVE_DB = _REPO / "data" / "sofa.db"


def collection_db_refusal(db: str | None) -> str | None:
    """Fits run on a copy of the database, never the live one: collecting the
    cases needs an explicit --db that is not data/sofa.db."""
    if not db:
        return ("--db is required to collect the cases: pass the refit's COPY "
                "of the database (e.g. data/refit_<date>/sofa.db), or --cases "
                "with a collected meta.json")
    if Path(db).resolve() == LIVE_DB.resolve():
        return f"--db {db} is the live database; a fit runs on a copy (rule 4)"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--before", required=True, help="fit on cases before this day")
    ap.add_argument("--cases", default=None, help=(
        "directory of cases_<market>.npz (measure_count_families collect); "
        "collected from --db (read-only) when meta.json is absent"))
    ap.add_argument("--db", default=None, help=(
        "the refit's COPY of the database (VACUUM INTO; CLAUDE.md 'Changing "
        "the pipeline' 4). Required when the cases are collected; the live "
        "data/sofa.db is refused. Not read when --cases already holds meta.json"))
    ap.add_argument("--out", default=None, help=f"default config/{CONFIG_FILE}")
    ap.add_argument("--evidence-json", default=str(_REPO / EVIDENCE_JSON), help=(
        "the measurement's results (admits a market only where the family "
        "used beat the sample variance out of sample); absent file = no gate"))
    ap.add_argument("--markets", default="", help="comma list (a test run)")
    ap.add_argument("--write", action="store_true", help=(
        "write --out (default the live config path); without it: a dry run "
        "that fits, prints the target and writes nothing"))
    ap.add_argument("--dry-run", action="store_true", help=(
        "kept for old command lines: the default now (see --write)"))
    args = ap.parse_args()

    cases_dir = Path(
        args.cases or _REPO / "data" / f"refit_{args.before}" / "count_cases")
    if not (cases_dir / "meta.json").exists():
        refusal = collection_db_refusal(args.db)
        if refusal:
            print(f"REFUSED: {refusal}", file=sys.stderr, flush=True)
            return 2
        print(f"collecting cases into {cases_dir} (db read-only)", flush=True)
        ns = argparse.Namespace(out=str(cases_dir), db=args.db, refresh=False)
        if mcf.cmd_collect(ns) != 0:
            return 2
    before_ts = _day_ts(args.before)
    val_start = val_start_for(args.before)
    val_ts = _day_ts(val_start)
    only = {m for m in args.markets.split(",") if m}
    cells: dict[str, dict[str, Any]] = {}
    max_ts = 0.0
    min_ts = float("inf")
    t0 = time.time()
    for path in sorted(cases_dir.glob("cases_*.npz")):
        market = path.stem[len("cases_"):]
        if only and market not in only:
            continue
        cases = mcf.load_cases(path)
        seen = cases.ts[cases.ts < before_ts]
        max_ts = max(max_ts, float(seen.max()) if len(seen) else 0.0)
        if len(seen):
            min_ts = min(min_ts, float(seen.min()))
        cells[market] = fit_market(market, cases, before_ts, val_ts)
        c = cells[market]
        print(f"{market:28s} {c['status']:8s} n={c['n_cases']:>9,} "
              f"alpha={c.get('alpha', '-')} kc={c.get('kc', '-')} "
              f"comps={c.get('n_competitions', '-')} ({time.time() - t0:.0f}s)",
              flush=True)
    cfg = build_config(
        cells, before=args.before, val_start=val_start, cases_dir=cases_dir,
        max_case_ts=max_ts, db_path=args.db,
        evidence=load_evidence(Path(args.evidence_json)),
        fingerprint=cases_fingerprint(cases_dir),
        min_case_ts=min_ts if min_ts != float("inf") else None)
    out = Path(args.out) if args.out else config_path(CONFIG_FILE)
    if args.dry_run or not args.write:
        print(f"dry run: {len(cfg['markets'])} markets, nothing written "
              f"(target {out}; --write to write it)")
        return 0
    write_atomic(out, json.dumps(cfg, indent=1, ensure_ascii=False) + "\n")
    print(f"written {out} ({len(cfg['markets'])} markets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
