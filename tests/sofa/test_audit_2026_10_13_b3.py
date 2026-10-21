"""Audit 2026-10-13 B3: a football joint's side without a quoted ladder.

A joint (both_over_* / most_* / handicap_*) read its margins from the marginal
rows only when Superbet quoted BOTH sides' ladders; with one missing it fell
back to both raw samples (Kyoto - Ratchaburi 2026-10-13: handicap_corners
Kyoto -2.5 p 0.060 against a market 0.504). epochs.DERIVED_SHEET_MARGINS
prices the missing side with the SHEET formula (run_sheet.sample_centre) and
refuses an UNLINKED fixture's joints as its marginal rows are refused.
Evidence: docs/sofa/evidence/derived_margins_2026-10-13.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from bet.sofa import epochs
from bet.sofa.confidence import has_cross_league_unlinked_note
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import FixtureSamples, PricedRung, SheetRow
from bet.sofa.football_rating import LINKED, UNLINKED, FootballForecast
from scripts.sofa.run_sheet import process_fixture
from tests.sofa.test_sheet import FETCHED, make_fixture, make_offer
from tests.sofa.test_sheet_day_priors import _obs, _samples

HOME = [6.0, 4.0, 7.0, 5.0, 8.0, 3.0, 6.0, 5.0, 7.0, 4.0]
AWAY = [9.0, 8.0, 10.0, 7.0, 9.0, 11.0, 8.0, 9.0, 10.0, 8.0]
BASELINES = {"corners_for": {"global": {"mean": 5.0, "n": 50000}}}


def _samples_for() -> FixtureSamples:
    a = _obs(range(100, 110), 0.0)
    b = _obs(range(110, 120), 0.0)
    a = [o.model_copy(update={"value": v}) for o, v in zip(a, HOME, strict=True)]
    b = [o.model_copy(update={"value": v}) for o, v in zip(b, AWAY, strict=True)]
    return _samples(1, "corners_for", a, b)


def _rung(market: str, subject: str, line: float, over: float,
          under: float | None) -> PricedRung:
    return PricedRung(market=market, subject=subject, line=line, over_odds=over,
                      under_odds=under, fetched_at_utc=FETCHED)


def _offer(quote_away_ladder: bool) -> Any:
    rungs = [
        _rung("corners_for", "Arsenal", 4.5, 1.70, 2.10),
        _rung("handicap_corners", "Arsenal", -1.5, 1.90, None),
        _rung("handicap_corners", "Chelsea", 1.5, 1.90, None),
        _rung("most_corners", "Arsenal", 0.0, 1.50, None),
        _rung("both_over_corners", "", 3.5, 1.60, 2.20),
    ]
    if quote_away_ladder:
        rungs.insert(1, _rung("corners_for", "Chelsea", 4.5, 1.80, 2.00))
    return make_offer(rungs)


class _Forecast:
    """A FootballForecast stand-in: a fixed rating centre per side."""

    def __init__(self, status: str = LINKED) -> None:
        self.status = status

    def centre(self, market: str, side: str | None) -> tuple[float, str] | None:
        if market != "corners_for" or side not in ("side_a", "side_b"):
            return None
        return (6.5, "stub") if side == "side_a" else (4.0, "stub")

    def link_status(self, market: str) -> str | None:
        return self.status if market.endswith("_for") else None

    def fixture_link(self) -> str:
        return self.status

    def no_league_rate(self, market: str) -> bool:
        return False


def _rows(quote_away_ladder: bool, on: bool,
          football: _Forecast | None = None) -> list[SheetRow]:
    rows, _ = process_fixture(
        make_fixture(), _samples_for(), _offer(quote_away_ladder),
        baselines=BASELINES, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), stats_only=True, marginal_centres_on=True,
        football=cast("FootballForecast | None", football),
        sheet_margins_on=on)
    return rows


def _derived(rows: list[SheetRow]) -> dict[tuple[str, str, float, str], SheetRow]:
    return {(r.market, r.subject or "", r.line, r.direction): r for r in rows
            if r.market.startswith(("handicap_", "most_", "both_over_"))}


def test_off_the_missing_ladder_keeps_the_raw_joint() -> None:
    off = _derived(_rows(False, on=False))
    assert off
    for row in off.values():
        assert not any(str(n).startswith("SHEET_MARGIN") for n in row.notes)


def test_on_the_missing_side_gets_the_centre_its_marginal_row_would_have() -> None:
    """One formula: the joint with Chelsea's ladder missing equals the joint
    with it quoted (the marginal row's centre is rounded to 4 places)."""
    quoted = _derived(_rows(True, on=True))
    filled = _derived(_rows(False, on=True))
    raw = _derived(_rows(False, on=False))
    assert quoted.keys() == filled.keys()
    moved = 0
    for key, row in filled.items():
        assert row.p_central == pytest.approx(quoted[key].p_central, abs=2e-3)
        moved += row.p_central != raw[key].p_central
        assert any(str(n).startswith("SHEET_MARGIN: side_b corners_for")
                   for n in row.notes)
    assert moved > 0


def test_on_with_both_ladders_quoted_nothing_changes() -> None:
    off = [r.model_dump(mode="json") for r in _rows(True, on=False)]
    on = [r.model_dump(mode="json") for r in _rows(True, on=True)]
    assert on == off


def test_the_rating_enters_the_filled_side_and_its_constants_are_named() -> None:
    football = _Forecast()
    filled = _derived(_rows(False, on=True, football=football))
    quoted = _derived(_rows(True, on=True, football=football))
    for key, row in filled.items():
        assert row.p_central == pytest.approx(quoted[key].p_central, abs=2e-3)
        unfitted = [n for n in row.notes if str(n).startswith("UNFITTED_CONSTANTS")]
        assert unfitted and "W_FOOTBALL_RATING" in unfitted[0]
        assert any("rating at W_FOOTBALL_RATING" in str(n) for n in row.notes)


def test_an_unlinked_fixture_refuses_its_joints_like_its_marginal_rows() -> None:
    football = _Forecast(UNLINKED)
    on = _rows(False, on=True, football=football)
    off = _rows(False, on=False, football=football)
    marginals = [r for r in on if r.market == "corners_for"]
    assert marginals and all(has_cross_league_unlinked_note(r.notes)
                             for r in marginals)
    assert all(has_cross_league_unlinked_note(r.notes)
               for r in _derived(on).values())
    assert not any(has_cross_league_unlinked_note(r.notes)
                   for r in _derived(off).values())


def test_a_thin_side_is_not_filled() -> None:
    samples = _samples_for()
    thin = samples.metrics["corners_for"].model_copy(
        update={"side_b": samples.metrics["corners_for"].side_b[:3]})
    samples = samples.model_copy(update={"metrics": {"corners_for": thin}})
    rows, _ = process_fixture(
        make_fixture(), samples, _offer(False), baselines=BASELINES,
        reliability={}, engine_constants={}, vetoes=[], config=SofaConfig(),
        stats_only=True, marginal_centres_on=True, sheet_margins_on=True)
    assert not any(str(n).startswith("SHEET_MARGIN")
                   for r in rows for n in r.notes)


def test_the_switch_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # operator 2026-10-21: on with DERIVED_CURVES / CARDS_CORRELATION
    assert epochs.DERIVED_SHEET_MARGINS_FROM_UTC == datetime(2026, 10, 21, tzinfo=UTC)
    assert epochs.derived_sheet_margins(
        "2026-12-01", datetime(2026, 12, 1, tzinfo=UTC))
    assert not epochs.derived_sheet_margins(
        "2026-10-20", datetime(2026, 12, 1, tzinfo=UTC))
    at = datetime(2026, 10, 15, tzinfo=UTC)
    monkeypatch.setattr(epochs, "DERIVED_SHEET_MARGINS_FROM_UTC", at)
    assert epochs.derived_sheet_margins("2026-10-15", at)
    assert not epochs.derived_sheet_margins(
        "2026-10-15", datetime(2026, 10, 14, 23, 59, tzinfo=UTC))
    # a rebuild of an earlier day keeps the rule it printed under
    assert not epochs.derived_sheet_margins(
        "2026-10-14", datetime(2026, 10, 16, tzinfo=UTC))
