#!/usr/bin/env python3
# ruff: noqa: E501  - report keys and paths read better unwrapped.
"""Read-only E2E of epochs.FOOTBALL_STAT_VARIANTS on stored days.

Evidence, not a stage (a ``measure_*`` script): it reads a day's artifacts
from ``--runs-dir`` and the database ``mode=ro``, and writes only under
``--scratch`` (a copy of each day it runs CONFIDENCE on). Never point
``--scratch`` at runs/sofa.

Per day:
  OFFER     the day's recorded unmapped odds (unmapped_prices/, the latest
            OFFER run that saw each fixture) replayed through the real
            OfferFetcher with Superbet's own listing names (01_board.json):
            the switch off must read nothing new; on, the stat-variant rungs
            are merged into the stored 04_offer.json.
  SAMPLES   a side metric the stored 03_samples.json lacks (SAMPLES asks only
            what the day's rungs needed) is rebuilt from the cached
            /statistics of the same past matches as the fixture's corners_for
            sample - checked against the side metrics the day did sample.
  SHEET     bet.sofa.derived.price_derived_rungs with SHEET's own arguments
            (constants, reliability, side correlations, in-play strip, stats
            only), checked to reproduce the stored derived rows; off = the
            stored offer, on = with the new rungs: every old row must be
            byte-identical.
  CONFIDENCE scripts/sofa/run_confidence.py on a scratch copy of the day,
            stored sheet vs stored sheet + new rows, the clock frozen just
            after the day's newest price: legs lost / changed / added.
  SETTLE    the new rows of finished matches graded with run_settle's own
            _settle_derived on the cached statistics.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_stat_variants_e2e.py \\
        --runs-dir runs/sofa --db data/sofa.db --scratch <scratch dir> \\
        --days 2026-10-18 2026-10-19 2026-10-20 [--grade-days 2026-10-14 ...] \\
        [--json-out f]

Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from pydantic import RootModel

from bet.sofa import offer as offer_mod
from bet.sofa import unmapped_prices
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    GapReason,
    MetricSample,
    Observation,
    PricedRung,
    SheetRow,
)
from bet.sofa.derived import load_side_correlations, price_derived_rungs
from bet.sofa.engine import MAX_LADDER_SIGMA
from bet.sofa.epochs import STATS_ONLY
from bet.sofa.market_mapper import (
    STAT_VARIANT_MARKETS,
    derived_base,
    derived_side_metric,
    is_derived,
)
from bet.sofa.metrics import extract_flat_statistics, extract_metric
from bet.sofa.offer import OfferFetcher
from scripts.sofa.run_settle import _settle_derived
from scripts.sofa.run_sheet import (
    UNFITTED_K_PRICE,
    get_calibration_correction,
    load_engine_constants,
    load_reliability,
    read_constant,
    sheet_row_json,
    strip_in_play_prices,
)

TEMPLATE_METRIC = "corners_for"
FLOOR = 0.70


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


# --- OFFER ------------------------------------------------------------------


class _Recorded:
    """A Superbet client answering from one OFFER run's recorded odds."""

    def __init__(self, payloads: Mapping[str, dict[str, Any]]) -> None:
        self.payloads = payloads

    def event_odds(self, event_id: str) -> dict[str, Any]:
        return self.payloads.get(str(event_id), {"odds": []})


def _latest_records(run: Path) -> dict[int, tuple[datetime, list[dict[str, Any]]]]:
    """Per fixture, the records of the latest OFFER run that saw it."""
    folder = run / unmapped_prices.DIRNAME
    out: dict[int, tuple[datetime, list[dict[str, Any]]]] = {}
    for path in sorted(folder.glob("*.jsonl.gz")):
        per: dict[int, list[dict[str, Any]]] = defaultdict(list)
        stamp: dict[int, datetime] = {}
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                eid = int(r["sofascore_event_id"])
                per[eid].append(r)
                at = _ts(str(r["fetched_at_utc"]))
                stamp[eid] = max(stamp.get(eid, at), at)
        for eid, records in per.items():
            out[eid] = (stamp[eid], records)
    return out


def replay_offer(run: Path, fixtures: Sequence[Fixture], on: bool
                 ) -> tuple[dict[int, list[PricedRung]], dict[int, set[str]]]:
    """The rungs (and the names it now reads) OFFER would add per fixture."""
    board = {str(b["superbet_event_id"]): b for b in _read(run / "01_board.json")}
    latest = _latest_records(run)
    added: dict[int, list[PricedRung]] = {}
    read_names: dict[int, set[str]] = {}
    saved = getattr(offer_mod, "now")  # noqa: B009 - the module's own clock
    try:
        for fx in fixtures:
            if fx.sport != "football" or fx.sofascore_event_id not in latest:
                continue
            at, records = latest[fx.sofascore_event_id]
            payloads: dict[str, dict[str, Any]] = {}
            for su_id in fx.superbet_event_ids:
                b = board.get(str(su_id))
                if b is None:
                    continue
                items = [{k: r[k] for k in unmapped_prices.FIELDS if k in r}
                         for r in records if str(r["superbet_event_id"]) == str(su_id)]
                payloads[str(su_id)] = {
                    "matchName": f"{b['side_a']}·{b['side_b']}", "odds": items}
            # the rungs carry the recorded fetch time, as OFFER stamped them
            setattr(offer_mod, "now", _clock(at))  # noqa: B010
            fetcher = OfferFetcher(_Recorded(payloads), football_stat_variants=on)
            [entry] = fetcher.fetch_offers([fx])
            if entry.rungs:
                added[fx.sofascore_event_id] = list(entry.rungs)
                read_names[fx.sofascore_event_id] = {
                    str(r["marketName"]) for r in records} - set(entry.unmapped_markets)
    finally:
        setattr(offer_mod, "now", saved)  # noqa: B010
    return added, read_names


def _clock(at: datetime) -> Callable[[], datetime]:
    def frozen() -> datetime:
        return at

    return frozen


# --- SAMPLES ------------------------------------------------------------------


class Stats:
    def __init__(self, db: str) -> None:
        self.conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        self.cache: dict[int, dict[str, Any] | None] = {}
        self.detail: dict[int, dict[str, Any] | None] = {}

    def flat(self, eid: int) -> dict[str, Any] | None:
        if eid not in self.cache:
            row = self.conn.execute(
                "SELECT statistics_json FROM sofa_event_stats WHERE sofascore_event_id = ?",
                (eid,)).fetchone()
            data = json.loads(row[0]) if row and row[0] else None
            flat = extract_flat_statistics(data) if data else None
            self.cache[eid] = flat if isinstance(flat, dict) else None
        return self.cache[eid]

    def event(self, eid: int) -> dict[str, Any] | None:
        if eid not in self.detail:
            row = self.conn.execute(
                "SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id = ?",
                (eid,)).fetchone()
            data = json.loads(row[0]) if row and row[0] else None
            self.detail[eid] = (data or {}).get("event") if data else None
        return self.detail[eid]


def _rebuild_side(stats: Stats, metric: str, template: Sequence[Observation]
                  ) -> list[Observation]:
    out: list[Observation] = []
    for o in template:
        flat = stats.flat(o.sofascore_event_id)
        if not flat or o.venue not in ("home", "away"):
            continue
        home = o.venue == "home"
        value = extract_metric(metric, "football", flat, None, {}, home)
        against = extract_metric(metric, "football", flat, None, {}, not home)
        if isinstance(value, GapReason):
            continue
        out.append(o.model_copy(update={
            "value": value,
            "against": None if isinstance(against, GapReason) else against}))
    return out


def rebuild_samples(stats: Stats, samples: FixtureSamples, wanted: set[str],
                    check: Counter[str]) -> tuple[FixtureSamples, set[str]]:
    """The fixture's samples with every wanted side metric present; a metric
    the day sampled is also rebuilt to check the rebuild (check counts)."""
    template = samples.metrics.get(TEMPLATE_METRIC)
    metrics = dict(samples.metrics)
    rebuilt: set[str] = set()
    if template is None:
        return samples, rebuilt
    for metric in sorted(wanted):
        a = _rebuild_side(stats, metric, template.side_a)
        b = _rebuild_side(stats, metric, template.side_b)
        held = samples.metrics.get(metric)
        if held is not None:
            for mine, theirs in ((a, held.side_a), (b, held.side_b)):
                got = {o.sofascore_event_id: o.value for o in mine}
                want = {o.sofascore_event_id: o.value for o in theirs}
                for eid in set(got) & set(want):
                    check["values_compared"] += 1
                    check["values_equal"] += got[eid] == want[eid]
            continue
        if a and b:
            metrics[metric] = MetricSample(metric=metric, side_a=a, side_b=b, h2h=[])
            rebuilt.add(metric)
    return samples.model_copy(update={"metrics": metrics}), rebuilt


# --- SHEET --------------------------------------------------------------------


def sheet_pricer() -> Callable[[Fixture, FixtureSamples, FixtureOffer], list[SheetRow]]:
    config = SofaConfig.from_env()
    constants = load_engine_constants(config)
    reliability = load_reliability(config)
    correlations = load_side_correlations()
    k_price, k_fit = read_constant(constants, "K_PRICE", UNFITTED_K_PRICE)
    sigma, s_fit = read_constant(constants, "MAX_LADDER_SIGMA", MAX_LADDER_SIGMA)

    def price(fixture: Fixture, samples: FixtureSamples, offer: FixtureOffer
              ) -> list[SheetRow]:
        k_centre_fit = read_constant(constants, "K_CENTRE", 10.0, fixture.sport)[1]
        unfitted = [n for n, f in (("K_CENTRE", k_centre_fit), ("K_PRICE", k_fit),
                                   ("MAX_LADDER_SIGMA", s_fit)) if not f]
        stripped, _ = strip_in_play_prices(offer, fixture)

        def correction(market: str, p: float, direction: str = "") -> float:
            return get_calibration_correction(reliability, market, p, direction)

        rows, _ = price_derived_rungs(
            fixture=fixture, samples=samples, offer=stripped,
            correlations=correlations, vetoes=[], min_sample=config.min_sample,
            max_ladder_sigma=sigma, k_price=k_price, unfitted=unfitted,
            correction_for=correction, stats_only=True)
        return [r.model_copy(update={"epoch": STATS_ONLY}) for r in rows]

    return price


_COMPARED = ("p_central", "p_bar", "sample_size", "sample_mean", "sample_sd",
             "market_p", "verdict", "calibration_correction")
_MODEL_FIELDS = ("p_central", "sample_size", "sample_mean", "sample_sd",
                 "calibration_correction")


def _derived_key(r: Mapping[str, Any]) -> tuple[Any, ...]:
    return (r["sofascore_event_id"], r["market"], r.get("subject") or "", r["line"],
            r["direction"])


# --- CONFIDENCE -----------------------------------------------------------------


def run_confidence(scratch: Path, date: str, clock: datetime) -> dict[str, Any]:
    env = {**os.environ, "SOFA_NOW": clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "SOFA_RUNS_DIR": str(scratch), "PYTHONPATH": "src:."}
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/run_confidence.py", "--date", date,
         "--runs-dir", str(scratch)], env=env, capture_output=True, text=True,
        check=False)
    summary: dict[str, Any] = {"rc": proc.returncode}
    for line in proc.stdout.splitlines():
        if line.startswith("{") and '"CONFIDENCE"' in line:
            summary.update(json.loads(line))
    if proc.returncode not in (0, 1):
        summary["stderr"] = proc.stderr[-2000:]
    doc = _read(scratch / date / "08_confidence.json")
    summary["legs_doc"] = doc.get("legs") or []
    return summary


def _leg_key(leg: Mapping[str, Any]) -> tuple[Any, ...]:
    return (leg["sofascore_event_id"], leg["market"], leg.get("subject") or "",
            leg["line"], leg["direction"])


def _copy_day(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for p in src.iterdir():
        if p.is_file() and p.suffix in (".json", ".jsonl"):
            shutil.copy2(p, dst / p.name)
        elif p.is_dir() and p.name == "printed":
            shutil.copytree(p, dst / p.name)


# --- the day ----------------------------------------------------------------------


def run_day(runs: Path, scratch: Path, stats: Stats, date: str, with_confidence: bool
            ) -> dict[str, Any]:
    run = runs / date
    fixtures = RootModel[list[Fixture]].model_validate_json(
        (run / "02_fixtures.json").read_text()).root
    by_id = {f.sofascore_event_id: f for f in fixtures}
    samples = {s.sofascore_event_id: s for s in RootModel[list[FixtureSamples]]
               .model_validate_json((run / "03_samples.json").read_text()).root}
    offers = {o.sofascore_event_id: o for o in RootModel[list[FixtureOffer]]
              .model_validate_json((run / "04_offer.json").read_text()).root}
    sheet_doc: list[dict[str, Any]] = _read(run / "05_sheet.json")
    out: dict[str, Any] = {"date": date}

    off_added, _ = replay_offer(run, fixtures, on=False)
    out["offer_off_new_rungs"] = sum(len(v) for v in off_added.values())
    added, _names = replay_offer(run, fixtures, on=True)
    added = {e: [r for r in rs if r.market in STAT_VARIANT_MARKETS]
             for e, rs in added.items() if e in offers}
    out["offer_on_new_rungs"] = Counter(r.market for rs in added.values() for r in rs)
    out["offer_on_fixtures"] = len([e for e, rs in added.items() if rs])

    price = sheet_pricer()
    check: Counter[str] = Counter()
    repro: Counter[str] = Counter()
    stored = {_derived_key(r): r for r in sheet_doc
              if is_derived(str(r["market"]))
              and by_id.get(r["sofascore_event_id"]) is not None
              and by_id[r["sofascore_event_id"]].sport == "football"}
    new_rows: list[dict[str, Any]] = []
    skipped_reason: Counter[str] = Counter()
    rebuilt_n: Counter[str] = Counter()
    old_moved = 0
    sha = next((r.get("config_sha") for r in sheet_doc if r.get("config_sha")), None)
    for eid, rungs in sorted(added.items()):
        if not rungs or eid not in samples:
            skipped_reason["no samples entry"] += len(rungs)
            continue
        fx = by_id[eid]
        offer_off = offers[eid]
        offer_on = offer_off.model_copy(update={"rungs": [*offer_off.rungs, *rungs]})
        wanted = {derived_side_metric(cast(str, derived_base(r.market))) for r in rungs}
        smp, rebuilt = rebuild_samples(stats, samples[eid], wanted, check)
        for m in rebuilt:
            rebuilt_n[m] += 1
        rows_off = price(fx, smp, offer_off)
        rows_on = price(fx, smp, offer_on)
        # the replay reproduces SHEET's stored derived rows (bases that do not
        # read the marginal rows' centres)
        for r in rows_off:
            js = sheet_row_json(r)
            if derived_side_metric(cast(str, derived_base(r.market))) in (
                    "goals_for", "corners_for", "shots_on_target_for", "cards_points_for"):
                continue
            held = stored.get(_derived_key(js))
            if held is None:
                repro["absent_in_stored"] += 1
                continue
            differ = [k for k in _COMPARED if js.get(k) != held.get(k)]
            repro["equal" if not differ else "differ"] += 1
            for k in differ:
                repro[f"differ:{k}"] += 1
            # a price that moved after SHEET ran (an OFFER refresh re-reads the
            # prices, never SHEET) moves market_p / p_bar / verdict only
            if not [k for k in differ if k in _MODEL_FIELDS]:
                repro["model_equal"] += 1
        old_off = [sheet_row_json(r) for r in rows_off]
        old_on = [sheet_row_json(r) for r in rows_on if r.market not in STAT_VARIANT_MARKETS]
        if old_off != old_on:
            old_moved += 1
        priced_keys = {(r.market, r.subject, r.line) for r in rows_on
                       if r.market in STAT_VARIANT_MARKETS}
        for rung in rungs:
            if (rung.market, rung.subject, rung.line) not in priced_keys:
                side = derived_side_metric(cast(str, derived_base(rung.market)))
                skipped_reason["no side sample" if side not in smp.metrics
                               else "other (thin sample / side not resolved)"] += 1
        for r in rows_on:
            if r.market in STAT_VARIANT_MARKETS:
                js = sheet_row_json(r)
                if sha is not None:
                    js["config_sha"] = sha
                new_rows.append(js)
    out["samples_rebuilt_fixtures"] = dict(rebuilt_n)
    out["samples_rebuild_check"] = dict(check)
    out["sheet_reproduces_stored_derived_rows"] = dict(repro)
    out["sheet_old_rows_moved_fixtures"] = old_moved
    out["sheet_new_rows"] = Counter(r["market"] for r in new_rows)
    out["sheet_new_rows_by_verdict"] = Counter(r["verdict"] for r in new_rows)
    out["sheet_new_rungs_without_row"] = dict(skipped_reason)
    priced = [r for r in new_rows if r.get("offered_odds")]
    out["sheet_new_priced_rows_p_ge_floor"] = sum(
        (r.get("p_central") or 0) >= FLOOR for r in priced)
    out["sheet_new_priced_rows_p_ge_floor_x_ge_0_90"] = sum(
        (r.get("p_central") or 0) >= FLOOR
        and (r.get("p_central") or 0) * float(r["offered_odds"]) >= 0.90 for r in priced)

    if with_confidence:
        newest = max(r.fetched_at_utc for o in offers.values() for r in o.rungs)
        clock = newest + timedelta(minutes=5)
        arms: dict[str, dict[str, Any]] = {}
        for arm, extra in (("off", []), ("on", new_rows)):
            dst = scratch / arm
            _copy_day(run, dst / date)
            (dst / date / "05_sheet.json").write_text(
                json.dumps([*sheet_doc, *extra], ensure_ascii=False, indent=2),
                encoding="utf-8")
            if arm == "on":
                # OFFER with the switch on: the stored offer plus the new rungs
                offer_doc: list[dict[str, Any]] = _read(run / "04_offer.json")
                for entry in offer_doc:
                    for rung in added.get(int(entry["sofascore_event_id"]), []):
                        entry.setdefault("rungs", []).append(rung.model_dump(mode="json"))
                (dst / date / "04_offer.json").write_text(
                    json.dumps(offer_doc, ensure_ascii=False, indent=2), encoding="utf-8")
            arms[arm] = run_confidence(dst, date, clock)
        off_legs = {_leg_key(leg): leg for leg in arms["off"].pop("legs_doc")}
        on_legs = {_leg_key(leg): leg for leg in arms["on"].pop("legs_doc")}
        changed = sum(1 for k, leg in off_legs.items()
                      if k in on_legs and json.dumps(leg, sort_keys=True)
                      != json.dumps(on_legs[k], sort_keys=True))
        out["confidence"] = {
            "clock": clock.isoformat(),
            "rc": {a: arms[a].get("rc") for a in arms},
            "legs_off": len(off_legs), "legs_on": len(on_legs),
            "lost": len(set(off_legs) - set(on_legs)), "changed": changed,
            "new_legs": len(set(on_legs) - set(off_legs)),
            "new_legs_markets": Counter(k[1] for k in set(on_legs) - set(off_legs)),
            "refused_delta": {
                k: v - (arms["off"].get("metrics", {}).get("refused", {}).get(k, 0))
                for k, v in (arms["on"].get("metrics", {}).get("refused", {})).items()
                if v != arms["off"].get("metrics", {}).get("refused", {}).get(k, 0)},
            "stderr": {a: arms[a].get("stderr") for a in arms if arms[a].get("stderr")},
        }
    out["_new_rows"] = new_rows
    return out


def grade(stats: Stats, rows: Sequence[Mapping[str, Any]],
          fixtures: Mapping[int, Mapping[str, Any]]) -> Iterator[dict[str, Any]]:
    """Each row graded as SETTLE grades it (the fixture passed, so a
    handicap's side falls back to the side SHEET priced)."""
    for r in rows:
        eid = int(r["sofascore_event_id"])
        event = stats.event(eid)
        flat = stats.flat(eid)
        if event is None or flat is None:
            yield {**r, "outcome": "NO_DATA"}
            continue
        if (event.get("status") or {}).get("type") != "finished":
            yield {**r, "outcome": "NOT_FINISHED"}
            continue
        graded = _settle_derived(dict(r), "football", flat, None, event,
                                 dict(fixtures.get(eid) or {}) or None)
        yield {**r, "outcome": graded if isinstance(graded, str) else graded[1],
               "actual": None if isinstance(graded, str) else graded[0]}


def bootstrap_gap(rows: Sequence[Mapping[str, Any]], draws: int = 2000,
                  seed: int = 20261021) -> tuple[float, float, float] | None:
    """realised - mean p over decided rows, a 95% interval resampling
    matches (the rungs of one match are not independent)."""
    import random

    by_match: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        if r["outcome"] in ("WIN", "LOSS"):
            by_match[(str(r["day"]), int(r["sofascore_event_id"]))].append(
                (float(r["outcome"] == "WIN"), float(r["p_central"])))
    keys = list(by_match)
    if not keys:
        return None

    def gap(sample: Sequence[tuple[str, int]]) -> float:
        pairs = [x for k in sample for x in by_match[k]]
        return sum(w - p for w, p in pairs) / len(pairs)

    rng = random.Random(seed)
    stats_ = sorted(gap([rng.choice(keys) for _ in keys]) for _ in range(draws))
    return gap(keys), stats_[int(0.025 * draws)], stats_[int(0.975 * draws) - 1]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0] if __doc__ else None)
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--db", required=True)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--days", nargs="*", default=[])
    ap.add_argument("--grade-days", nargs="*", default=[])
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--rows-out", default=None, help="the graded rows, as JSON")
    args = ap.parse_args(argv)
    runs, scratch = Path(args.runs_dir), Path(args.scratch)
    if scratch.resolve() == runs.resolve() or scratch.resolve() == Path("runs/sofa").resolve():
        print("REFUSED: --scratch must not be the runs dir", file=sys.stderr)
        return 2
    stats = Stats(args.db)
    report: dict[str, Any] = {"days": {}, "graded": {}}
    graded_rows: list[dict[str, Any]] = []
    try:
        for d in sorted(set(args.days) | set(args.grade_days)):
            day = run_day(runs, scratch / d, stats, d, with_confidence=d in args.days)
            rows = day.pop("_new_rows")
            report["days"][d] = day
            if d in args.grade_days:
                # the quoted side only: an unquoted complement (UNDER of a
                # "tak"-only ladder) is a NO_PRICE row, never a bet
                fixtures = {int(f["sofascore_event_id"]): f
                            for f in _read(runs / d / "02_fixtures.json")}
                graded_rows.extend({**r, "day": d} for r in grade(
                    stats, [r for r in rows if r.get("offered_odds")], fixtures))
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    fam: dict[str, dict[str, Any]] = {}
    for r in graded_rows:
        f = fam.setdefault(r["market"], {"rows": 0, "outcomes": Counter(), "won": 0,
                                         "decided": 0, "p_sum": 0.0, "at_floor": 0,
                                         "at_floor_won": 0, "at_floor_p": 0.0})
        f["rows"] += 1
        f["outcomes"][r["outcome"]] += 1
        if r["outcome"] in ("WIN", "LOSS"):
            f["decided"] += 1
            f["won"] += r["outcome"] == "WIN"
            f["p_sum"] += float(r["p_central"])
            if float(r["p_central"]) >= FLOOR:
                f["at_floor"] += 1
                f["at_floor_won"] += r["outcome"] == "WIN"
                f["at_floor_p"] += float(r["p_central"])
    for f in fam.values():
        f["realised"] = round(f["won"] / f["decided"], 4) if f["decided"] else None
        f["mean_p"] = round(f["p_sum"] / f["decided"], 4) if f["decided"] else None
        f["at_floor_realised"] = (round(f["at_floor_won"] / f["at_floor"], 4)
                                  if f["at_floor"] else None)
        f["at_floor_mean_p"] = (round(f["at_floor_p"] / f["at_floor"], 4)
                                if f["at_floor"] else None)
        f.pop("p_sum")
        f.pop("at_floor_p")
    report["graded"] = fam
    report["graded_events"] = len({(r["day"], r["sofascore_event_id"]) for r in graded_rows
                                   if r["outcome"] in ("WIN", "LOSS")})
    # realised - p with a match bootstrap: every priced row, and at p >= 0.70
    gaps: dict[str, Any] = {}
    for label, floor in (("all", 0.0), ("p_ge_floor", FLOOR)):
        for market in [*sorted(fam), "_pooled"]:
            chosen = [r for r in graded_rows if float(r["p_central"]) >= floor
                      and (market == "_pooled" or r["market"] == market)]
            got = bootstrap_gap(chosen)
            if got is not None:
                gaps[f"{label}:{market}"] = {
                    "n": sum(r["outcome"] in ("WIN", "LOSS") for r in chosen),
                    "gap": round(got[0], 4), "lo95": round(got[1], 4),
                    "hi95": round(got[2], 4)}
    report["realised_minus_p"] = gaps
    if args.rows_out:
        Path(args.rows_out).write_text(
            json.dumps(graded_rows, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8")
    text = json.dumps(report, indent=1, ensure_ascii=False, default=str)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
