"""Scenarios for the "switches off = HEAD byte for byte" golden file.

Imports only what exists both before and after the 2026-10-08 change set
(no switch argument), so `tests/sofa/golden/make_off_goldens.py` can run it
against an archive of the commit the change set started from and write
`golden/off_identical_head.json`; the test runs it against the working tree
and compares.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).parent / "golden"
CORRELATIONS_INPUT = GOLDEN_DIR / "side_correlations_input.json"


# row fields the change set ADDED (None = priced under the old rule): absent
# from the commit it started from, so they are dropped while None
_NEW_MARKERS = ("dispersion_rule", "tennis_table_rule", "k_rule", "cards_rule")


def _row(r: Any) -> dict[str, Any]:
    out: dict[str, Any] = r.model_dump(mode="json")
    for key in _NEW_MARKERS:
        if out.get(key) is None:
            out.pop(key, None)
    return out


def _dump(rows: list[Any]) -> list[dict[str, Any]]:
    return [_row(r) for r in rows]


def football_process_fixture() -> dict[str, Any]:
    from bet.sofa.config import SofaConfig
    from scripts.sofa.run_sheet import process_fixture
    from tests.sofa.test_sheet import make_fixture, make_offer, rung
    from tests.sofa.test_sheet_day_priors import _obs, _samples

    out: dict[str, Any] = {}
    for metric, lines, va, vb in (
            ("shots_total", (23.5, 25.5, 27.5), 26.0, 24.0),
            ("corners_total", (8.5, 10.5, 12.5), 11.0, 10.0),
            ("goals_total", (2.5, 3.5, 4.5), 3.0, 4.0)):
        for stats_only in (False, True):
            fixture = make_fixture(sofascore_event_id=1, competition_id=18643)
            own = _samples(1, metric, _obs(range(100, 110), va),
                           _obs(range(110, 120), vb))
            offer = make_offer([rung(lines[0], 1.40, 2.80, metric),
                                rung(lines[1], 2.10, 1.70, metric),
                                rung(lines[2], 3.60, 1.28, metric)])
            rows, _ = process_fixture(
                fixture, own, offer,
                baselines={metric: {"global": {"mean": 20.0, "n": 50000}}},
                reliability={}, engine_constants={}, vetoes=[],
                config=SofaConfig(), stats_only=stats_only)
            out[f"{metric}/stats_only={stats_only}"] = _dump(rows)
    return out


def tennis_process_fixture() -> dict[str, Any]:
    from tests.sofa.test_stats_only_sheet import _tennis

    out: dict[str, Any] = {}
    for stats_only in (False, True):
        rows = _tennis(1.40, 3.00, stats_only=stats_only)
        out[f"stats_only={stats_only}"] = {
            f"{m}/{d}": _row(r) for (m, d), r in rows.items()}
    return out


def derived_rungs() -> dict[str, Any]:
    from bet.sofa.contracts import FixtureOffer, PricedRung
    from bet.sofa.derived import price_derived_rungs
    from bet.sofa.timeutil import now
    from tests.sofa.test_derived_markets import make_fixture, make_samples

    a = [2, 0, 1, 3, 1, 0, 2, 1, 1, 2]
    b = [0, 1, 1, 0, 2, 1, 0, 0, 1, 1]
    rungs = [
        PricedRung(market=m, subject=s, line=ln, over_odds=1.8, under_odds=1.95,
                   fetched_at_utc=now())
        for m, s, ln in (("both_over_goals", "", 0.5), ("both_over_goals", "", 1.5),
                         ("handicap_goals", "1", -0.5), ("most_goals", "1", 0.5))
    ]
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED", rungs=rungs,
                         unmapped_markets=[])
    out: dict[str, Any] = {}
    for label, centres, stats_only in (
            ("raw", None, False), ("stats_only", None, True),
            ("centres", {("goals_for", "side_a"): 1.4,
                         ("goals_for", "side_b"): 0.8}, True)):
        rows, skipped = price_derived_rungs(
            fixture=make_fixture(), samples=make_samples("goals_for", a, b),
            offer=offer, correlations={"goals": 0.1}, vetoes=[], min_sample=5,
            max_ladder_sigma=9.0, k_price=10.0, unfitted=[],
            stats_only=stats_only, marginal_centres=centres)
        out[label] = {
            "rows": [{k: v for k, v in _row(r).items()
                      if "fetched" not in k and "_at" not in k} for r in rows],
            "skipped": [[x[1].value, x[2]] for x in skipped]}
    return out


def side_correlations() -> dict[str, Any]:
    from bet.sofa.derived import load_side_correlations

    return {
        "file": load_side_correlations(CORRELATIONS_INPUT),
        "missing": load_side_correlations(GOLDEN_DIR / "nope.json"),
        "live_file_keys": sorted(load_side_correlations()),
    }


def all_scenarios() -> dict[str, Any]:
    return json.loads(json.dumps({
        "process_fixture_football": football_process_fixture(),
        "process_fixture_tennis": tennis_process_fixture(),
        "price_derived_rungs": derived_rungs(),
        "load_side_correlations": side_correlations(),
    }, sort_keys=True, default=str))
