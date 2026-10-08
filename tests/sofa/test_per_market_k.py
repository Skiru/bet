"""epochs.PER_MARKET_K: the football centre shrunk with the K of its own market
(K_CENTRE.by_market). Off (None) = the sport's K, byte for byte."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa.contracts import SheetRow
from bet.sofa.per_market_k import k_for_market
from scripts.sofa import calibrate_from_cache as cc
from scripts.sofa import fit_constants as fc
from scripts.sofa.calibrate_from_cache import Played
from scripts.sofa.run_sheet import sheet_row_json

CONFIG = Path(__file__).resolve().parents[2] / "config" / "sofa_engine_constants.json"
BASE = {"K_CENTRE": {"value": 10.0, "by_sport": {"football": 15.0, "tennis": 5.0}}}
WITH = {"K_CENTRE": {**BASE["K_CENTRE"],
                     "by_market": {"football": {"shots_for": 8, "fouls_total": 2.0}}}}


WITH_TOTAL = {"K_CENTRE": {**BASE["K_CENTRE"],
                           "by_market": {"football": {"shots_total": 5.0}}}}


def test_the_switch_starts_with_the_2026_10_09_epoch() -> None:
    start = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    assert epochs.PER_MARKET_K_FROM_UTC == start
    assert not epochs.per_market_k_enabled("2026-10-08", start)
    assert not epochs.per_market_k_enabled(
        "2026-10-09", start - timedelta(minutes=1))
    assert epochs.per_market_k_enabled("2026-10-09", start)


def test_the_shipped_file_keeps_its_old_keys() -> None:
    k = json.loads(CONFIG.read_text())["K_CENTRE"]
    assert k["by_sport"]["football"] == 15.0
    assert k["value"] == 10.0
    assert "curve" in k and k["status"] == "FITTED"
    assert k["by_market"]["football"]["shots_for"] == 8.0  # live from the switch


def test_k_for_market_reads_only_football_and_only_listed_markets() -> None:
    assert k_for_market(WITH, "football", "shots_for", 15.0) == 8.0
    assert k_for_market(WITH, "football", "fouls_total", 15.0) == 2.0
    assert k_for_market(WITH, "football", "goals_for", 15.0) == 15.0
    assert k_for_market(WITH, "tennis", "shots_for", 5.0) == 5.0
    assert k_for_market(BASE, "football", "shots_for", 15.0) == 15.0
    assert k_for_market({}, "football", "shots_for", 15.0) == 15.0
    assert k_for_market({"K_CENTRE": {"by_market": {"football": {"x": True}}}},
                        "football", "x", 15.0) == 15.0
    assert k_for_market({"K_CENTRE": {"by_market": {"football": {"x": -1}}}},
                        "football", "x", 15.0) == 15.0


def _match() -> Played:
    return Played(event_id=1, timestamp=0, home_id=1, away_id=2, sport="football",
                  competition_id=17, values={})


def test_replay_centre_is_unchanged_when_off_and_moves_when_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = [6.0, 7.0, 5.0, 8.0, 6.0, 7.0, 9.0, 6.0]
    baselines = {"shots_for": {"17": {"mean": 4.0, "n": 500}},
                 "goals_for": {"17": {"mean": 1.2, "n": 500}}}
    match = _match()
    off_with = cc.shrunk_centre(match, "shots_for", sample, baselines, WITH)
    off_base = cc.shrunk_centre(match, "shots_for", sample, baselines, BASE)
    assert off_with == off_base  # the file's table is inert with the flag off
    n, mean = len(sample), sum(sample) / len(sample)
    assert off_base == pytest.approx((n * mean + 15 * 4.0) / (n + 15))
    monkeypatch.setattr(cc, "PER_MARKET_K", True)
    on = cc.shrunk_centre(match, "shots_for", sample, baselines, WITH)
    assert on == pytest.approx((n * mean + 8 * 4.0) / (n + 8))
    assert on > off_base  # less shrinkage toward the lower prior
    # a market with no entry keeps the sport's K even with the flag on
    g = [1.0, 2.0, 0.0, 3.0, 1.0, 1.0, 2.0, 0.0]
    assert cc.shrunk_centre(match, "goals_for", g, baselines, WITH) == \
        cc.shrunk_centre(match, "goals_for", g, baselines, BASE)


def test_rebuild_reruns_sheet_on_a_sheet_of_the_other_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
    limit = timedelta(minutes=45)
    assert epochs.sheet_per_market_k([{"k_rule": epochs.PER_MARKET_K}])
    assert not epochs.sheet_per_market_k([{"k_rule": epochs.PER_MARKET_K}, {}])
    assert epochs.sheet_per_market_k([])
    monkeypatch.setattr(epochs, "PER_MARKET_K_FROM_UTC", None)
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-09", at, limit, sheet_k=False)).names()
    monkeypatch.setattr(epochs, "PER_MARKET_K_FROM_UTC",
                        datetime(2026, 10, 9, tzinfo=UTC))
    stale = rp.build_plan(rp.DayState("2026-10-09", at, limit, sheet_k=False))
    step = next(s for s in stale.steps if s.name == "SHEET")
    assert "K_CENTRE" in step.reason
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-09", at, limit, sheet_k=True)).names()
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-08", at, limit, sheet_k=False)).names()


def test_a_sheet_row_carries_the_rule_only_when_priced_under_it() -> None:
    assert "k_rule" in SheetRow.model_fields

    class _R:
        def __init__(self, rule: str | None) -> None:
            self.rule = rule

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {"epoch": "x", "link_rule": None, "k_rule": self.rule}

    assert "k_rule" not in sheet_row_json(_R(None))  # type: ignore[arg-type]
    assert sheet_row_json(_R(epochs.PER_MARKET_K))[  # type: ignore[arg-type]
        "k_rule"] == epochs.PER_MARKET_K


def test_a_constants_refit_carries_by_market_over(tmp_path: Path) -> None:
    path = tmp_path / "sofa_engine_constants.json"
    assert fc.carried_by_market(path) is None
    path.write_text(json.dumps(WITH))
    assert fc.carried_by_market(path) == {"football": {"shots_for": 8,
                                                       "fouls_total": 2.0}}
    path.write_text(json.dumps(BASE))
    assert fc.carried_by_market(path) is None
    path.write_text("not json")
    assert fc.carried_by_market(path) is None


# --- SHEET: the switch is the gate -----------------------------------------


def _price(engine_constants: dict[str, Any], on: bool, metric: str) -> list[Any]:
    from bet.sofa.config import SofaConfig
    from scripts.sofa.run_sheet import process_fixture
    from tests.sofa.test_sheet import make_fixture, make_offer, rung
    from tests.sofa.test_sheet_day_priors import _obs, _samples

    fixture = make_fixture(sofascore_event_id=1, competition_id=18643)
    own = _samples(1, metric, _obs(range(100, 110), 26.0), _obs(range(110, 120), 24.0))
    offer = make_offer([rung(23.5, 1.40, 2.80, metric), rung(25.5, 2.10, 1.70, metric),
                        rung(27.5, 3.60, 1.28, metric)])
    rows, _ = process_fixture(
        fixture, own, offer,
        baselines={metric: {"global": {"mean": 20.0, "n": 50000}}},
        reliability={}, engine_constants=engine_constants, vetoes=[],
        config=SofaConfig(), per_market_k_on=on)
    return rows


def test_sheet_off_ignores_the_table_and_on_reads_it() -> None:
    metric = "shots_total"
    plain = _price(BASE, False, metric)
    with_table_off = _price(WITH_TOTAL, False, metric)
    assert plain and [r.model_dump() for r in plain] == \
        [r.model_dump() for r in with_table_off]
    # on, but the market is not listed: the sport's K, the same rows
    assert [r.model_dump() for r in _price(WITH, True, "corners_total")] == \
        [r.model_dump() for r in _price(BASE, False, "corners_total")]
    # on and listed (K = 5 against 15): less shrinkage toward the prior 20
    # of a sample whose mean is 25
    listed = _price(WITH_TOTAL, True, metric)
    assert listed
    assert listed[0].centre > plain[0].centre
    # pooled sample: n = 20, mean 25.0, prior 20.0
    assert plain[0].centre == pytest.approx((20 * 25.0 + 15 * 20.0) / 35, abs=0.01)
    assert listed[0].centre == pytest.approx((20 * 25.0 + 5 * 20.0) / 25, abs=0.01)


def test_the_cards_and_k_markers_do_not_leak_into_a_default_row() -> None:
    rows = _price(BASE, False, "shots_total")
    assert all(r.k_rule is None and r.cards_rule is None for r in rows)
