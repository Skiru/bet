"""Review 2026-10-27 R1: a football joint's side Superbet quoted no ladder for.

Under epochs.DERIVED_SHEET_MARGINS that side's centre came from
run_sheet.sample_centre alone (prior, K_CENTRE, rating), while its marginal
row - and the cache replay that fitted the joint curves - also carries the
opponent correction, the venue prior, GAME_STATE, the stretches, the referee
and the season phase (10-26 event 16310990 both_over_cards_points 0.5: the
quoted side 1.81 -> 1.93, the filled side flat at 1.67). Under
epochs.JOINT_FILLED_SIDE_CHAIN the filled side goes through the same chain
(bet.sofa.centre_chain) on the same corrected sample, and its rows carry
JOINT_SIDE_CHAIN. Off: byte-identical. Offline and fast.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from bet.sofa import epochs
from bet.sofa import referees as rf
from bet.sofa.centre_chain import JOINT_SIDE_CHAIN_NOTE, CentreTerms
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import FixtureSamples, Observation, PricedRung, SheetRow
from bet.sofa.football_rating import LINKED, FootballForecast
from bet.sofa.game_state import GameStateTable
from bet.sofa.opponent_correction import SampleCorrector
from scripts.sofa.run_sheet import process_fixture, sample_centre, sheet_derived_margins
from tests.sofa.test_sheet import FETCHED, make_fixture, make_offer
from tests.sofa.test_sheet_day_priors import _obs, _samples

M = "cards_points_for"
HOME = [20.0, 10.0, 30.0, 20.0, 40.0, 10.0, 20.0, 30.0, 20.0, 10.0]
AWAY = [30.0, 20.0, 40.0, 30.0, 20.0, 50.0, 30.0, 20.0, 40.0, 30.0]
BASELINES = {M: {"global": {"mean": 22.0, "n": 50000}}}
GAME_STATE = GameStateTable(betas={M: -0.10})
REFEREE = rf.parse_effect_table({"markets": {
    M: {"family": "cards_points", "beta": 0.4, "K": 5.0}}})
STRICT = rf.RefereeRead(77, 12, 18.0, 4.0)  # 12 matches at 1.5x the league
READS = {"cards_points": STRICT}
FACTOR = {42: 1.10, 38: 0.90}  # home / away team ids of make_fixture


class _Forecast:
    """A FootballForecast stand-in: no rating centre, a goal supremacy."""

    def centre(self, market: str, side: str | None) -> tuple[float, str] | None:
        return None

    def supremacy(self, side: str) -> float | None:
        return {"side_a": 0.6, "side_b": -0.6}.get(side)

    def venue_multiplier(self, market: str, side: str,
                         venues: object) -> float | None:
        return None

    def link_status(self, market: str) -> str | None:
        return LINKED

    def fixture_link(self) -> str:
        return LINKED

    def no_league_rate(self, market: str) -> bool:
        return False


class _Corrector:
    """A SampleCorrector stand-in: each team's sample x its own factor."""

    def correct(self, observations: Sequence[Observation], market: str,
                team: int, today_opponent: int | None,
                split: object = None,
                today_competition: int | None = None) -> list[Observation]:
        f = FACTOR[team]
        return [o.model_copy(update={"value": o.value * f}) for o in observations]


FOOTBALL = cast("FootballForecast", _Forecast())
CORRECTOR = cast("SampleCorrector", _Corrector())


def _samples_for() -> FixtureSamples:
    a = [o.model_copy(update={"value": v})
         for o, v in zip(_obs(range(100, 110), 0.0), HOME, strict=True)]
    b = [o.model_copy(update={"value": v})
         for o, v in zip(_obs(range(110, 120), 0.0), AWAY, strict=True)]
    return _samples(1, M, a, b)


def _rung(market: str, subject: str, line: float, over: float,
          under: float | None) -> PricedRung:
    return PricedRung(market=market, subject=subject, line=line, over_odds=over,
                      under_odds=under, fetched_at_utc=FETCHED)


def _offer(quote_away_ladder: bool) -> Any:
    rungs = [
        _rung(M, "Arsenal", 15.5, 1.70, 2.10),
        _rung("handicap_cards_points", "Arsenal", -5.5, 1.90, None),
        _rung("most_cards_points", "Arsenal", 0.0, 1.50, None),
        _rung("both_over_cards_points", "", 10.5, 1.60, 2.20),
    ]
    if quote_away_ladder:
        rungs.insert(1, _rung(M, "Chelsea", 25.5, 1.80, 2.00))
    return make_offer(rungs)


def _rows(quote_away_ladder: bool, *, chain: bool | None,
          terms: bool = True) -> list[SheetRow]:
    """`chain` None: the argument left out (the default)."""
    extra: dict[str, Any] = {} if chain is None else {"joint_side_chain_on": chain}
    rows, _ = process_fixture(
        make_fixture(), _samples_for(), _offer(quote_away_ladder),
        baselines=BASELINES, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), stats_only=True, marginal_centres_on=True,
        sheet_margins_on=True, football=FOOTBALL,
        game_state=GAME_STATE if terms else None,
        referee_effect=REFEREE if terms else None,
        referee_reads=READS if terms else None,
        sample_corrector=CORRECTOR if terms else None,
        **extra)
    return rows


def _derived(rows: list[SheetRow]) -> dict[tuple[str, str, float, str], SheetRow]:
    return {(r.market, r.subject or "", r.line, r.direction): r for r in rows
            if r.market.startswith(("handicap_", "most_", "both_over_"))}


def _quoted_away_centre() -> float:
    rows = [r for r in _rows(True, chain=True)
            if r.market == M and r.subject == "Chelsea"]
    assert rows and rows[0].centre is not None
    return rows[0].centre


def _filled_away_centre(terms: CentreTerms | None,
                        corrector: SampleCorrector | None) -> tuple[float, list[str]]:
    centres: dict[tuple[str, str], float] = {}
    notes, _ = sheet_derived_margins(
        make_fixture(), _samples_for(), _offer(False), centres,
        baselines=BASELINES, day_obs=None, football=FOOTBALL,
        engine_constants={}, k_centre=10.0, per_market_k_on=False, min_sample=5,
        centre_terms=terms, sample_corrector=corrector)
    return centres[(M, "side_b")], notes.get(M, [])


TERMS = CentreTerms(football=FOOTBALL, game_state=GAME_STATE,
                    referee_effect=REFEREE, referee_reads=READS)


def test_the_switch_is_on_from_10_28_and_reads_the_day_and_the_clock() -> None:
    assert epochs.JOINT_FILLED_SIDE_CHAIN_FROM_UTC == datetime(
        2026, 10, 28, tzinfo=UTC)
    at = datetime(2026, 10, 28, 6, tzinfo=UTC)
    assert epochs.joint_filled_side_chain("2026-10-28", at)
    assert not epochs.joint_filled_side_chain("2026-10-27", at)
    assert not epochs.joint_filled_side_chain(
        "2026-10-28", datetime(2026, 10, 27, 23, tzinfo=UTC))


def test_on_the_filled_side_gets_exactly_its_marginal_rows_centre() -> None:
    quoted = _quoted_away_centre()
    filled, notes = _filled_away_centre(TERMS, CORRECTOR)
    # the marginal row's centre is rounded to 4 places
    assert filled == pytest.approx(quoted, abs=1e-4)
    assert any(n.startswith(f"{JOINT_SIDE_CHAIN_NOTE}: side_b {M}")
               and "GAME_STATE" in n and "REFEREE" in n
               and "observations rescaled" in n for n in notes)


def test_on_the_joint_with_the_ladder_missing_equals_the_joint_with_it_quoted() -> None:
    quoted = _derived(_rows(True, chain=True))
    filled = _derived(_rows(False, chain=True))
    old = _derived(_rows(False, chain=False))
    assert quoted.keys() == filled.keys() and filled
    moved = 0
    for key, row in filled.items():
        assert row.p_central == pytest.approx(quoted[key].p_central, abs=1e-3)
        moved += abs((row.p_central or 0.0) - (old[key].p_central or 0.0)) > 1e-3
        assert any(str(n).startswith(f"{JOINT_SIDE_CHAIN_NOTE}: side_b")
                   for n in row.notes)
        unfitted = [n for n in row.notes if str(n).startswith("UNFITTED_CONSTANTS")]
        assert unfitted and any(c in unfitted[0] for c in rf.REFEREE_UNFITTED)
    assert moved > 0


def test_off_the_filled_side_is_sample_centre_alone_as_before() -> None:
    filled, notes = _filled_away_centre(None, None)
    raw = [o.value for o in _samples_for().metrics[M].side_b]
    expected, *_ = sample_centre(
        fixture=make_fixture(), market=M, subject="", n=len(raw),
        mean=statistics.mean(raw), own_sides=[_samples_for().metrics[M].side_b],
        own_events=set(), own_teams=[38], baselines=BASELINES, day_obs=None,
        football=FOOTBALL, tennis_tiers=None, engine_constants={},
        k_centre=10.0, per_market_k_on=False, side="side_b")
    assert filled == expected
    assert filled != pytest.approx(_quoted_away_centre(), abs=1e-2)
    assert not any(JOINT_SIDE_CHAIN_NOTE in n for n in notes)
    # a corrector handed in without the chain changes nothing either
    assert _filled_away_centre(None, CORRECTOR)[0] == expected


def test_off_is_byte_identical_to_the_default() -> None:
    off = [r.model_dump(mode="json") for r in _rows(False, chain=False)]
    default = [r.model_dump(mode="json") for r in _rows(False, chain=None)]
    assert off == default
    assert not any(JOINT_SIDE_CHAIN_NOTE in str(n) for r in off for n in r["notes"])


def test_the_marginal_rows_never_move_and_both_ladders_quoted_changes_nothing() -> None:
    on = [r.model_dump(mode="json") for r in _rows(True, chain=True)]
    off = [r.model_dump(mode="json") for r in _rows(True, chain=False)]
    assert on == off
    def marginal(chain: bool) -> list[dict[str, Any]]:
        return [r.model_dump(mode="json") for r in _rows(False, chain=chain)
                if r.market == M]

    assert marginal(True) == marginal(False)


def test_with_every_term_off_the_chain_only_adds_its_marker() -> None:
    on = _derived(_rows(False, chain=True, terms=False))
    off = _derived(_rows(False, chain=False, terms=False))
    for key, row in on.items():
        assert row.p_central == off[key].p_central
        assert [n for n in row.notes if JOINT_SIDE_CHAIN_NOTE not in str(n)] \
            == list(off[key].notes)
        assert any("(none applied)" in str(n) for n in row.notes)


def test_the_ledger_opens_od_10_28_for_the_review() -> None:
    import importlib
    audit_ledger = importlib.import_module("scripts.sofa.audit_ledger")
    assert audit_ledger.epoch_group(
        {"date": "2026-10-28", "epoch": "stats_only"}) == "od 10-28"
    assert audit_ledger.epoch_group(
        {"date": "2026-10-27", "epoch": "stats_only"}) == "od 10-27"
    assert "od 10-28" in audit_ledger.EPOCH_GROUPS
