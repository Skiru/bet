"""Audit 2026-10-13 B15 with A5: a football sample corrected for its opponents
and today's domain (bet.sofa.opponent_correction) behind
epochs.SAMPLE_OPPONENT_CORRECTION_FROM_UTC, and CONFIDENCE's gates reading
the corrected values. Off (None) = the raw sample, byte for byte. Offline."""

from __future__ import annotations

import json
import math
from collections import deque
from datetime import UTC, datetime, timedelta

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.football_rating import (
    CROSS_RATIO_POWER,
    RatingBook,
    _Strength,
    _Team,
)
from bet.sofa.opponent_correction import (
    SampleCorrector,
    correct_total,
    gate_values,
    mode_values,
    split_index,
)
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_player_markets import _fixture

M = "corners_for"
TS = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp())
A, B, O_LEAGUE, O_WEAK = 1, 2, 10, 11


def _book() -> RatingBook:
    """A (home) and O_LEAGUE play league 100; B plays league 200 (stronger by
    0.5 in log on corners); O_WEAK is A's league rival rated on few matches."""
    book = RatingBook(shared_league_link=True)
    book.last_ts = TS
    for team, comp in ((A, 100), (O_LEAGUE, 100), (B, 200), (O_WEAK, 100)):
        book.team_comps[team] = deque([(TS - 86400 * i, comp) for i in range(5)])
    book.teams[(O_LEAGUE, M)] = _Team(attack=1.25, defence=0.5, n=20)
    book.teams[(O_WEAK, M)] = _Team(attack=1.0, defence=0.25, n=3)
    book.teams[(B, M)] = _Team(attack=1.0, defence=1.0, n=20)
    book.strength[(100, M)] = _Strength(sigma=-0.25, n=30)
    book.strength[(200, M)] = _Strength(sigma=0.25, n=30)
    return book


def _obs(eid: int, value: float, opponent: int | None,
         against: float | None = None) -> Observation:
    return Observation(
        sofascore_event_id=eid, match_date_utc=datetime(2026, 9, 1, tzinfo=UTC)
        + timedelta(days=eid % 28), opponent=f"T{opponent}", value=value,
        competition_id=100, season_id=1, venue=None, opponent_id=opponent,
        against=against)


def test_a_league_match_is_rescaled_by_the_opponents_defence_and_the_domain() -> None:
    corrector = SampleCorrector(_book())
    # A vs O_LEAGUE is LINKED (power 1, no gap in that match); today A meets
    # B from a league 0.5 stronger in log: A's rate falls by exp(-0.5)
    out = corrector.correct([_obs(1, 6.0, O_LEAGUE)], M, A, B)
    assert out[0].value == pytest.approx(6.0 / 0.5 * math.exp(-0.5))
    # against a league rival today the domain term is 0: opponent only
    same = corrector.correct([_obs(1, 6.0, O_LEAGUE)], M, A, O_LEAGUE)
    assert same[0].value == pytest.approx(12.0)


def test_a_cross_league_sample_match_reads_the_ratio_at_the_cross_power() -> None:
    book = _book()
    book.teams[(B, M)] = _Team(attack=2.0, defence=0.8, n=20)
    corrector = SampleCorrector(book)
    # the sample match itself was A vs B (cross-league): gap cancels today
    out = corrector.correct([_obs(1, 4.0, B)], M, A, B)
    assert out[0].value == pytest.approx(4.0 / 0.8 ** CROSS_RATIO_POWER)


def test_unknown_or_thinly_rated_opponents_and_player_markets_stay_raw() -> None:
    corrector = SampleCorrector(_book())
    raw = [_obs(1, 5.0, None), _obs(2, 5.0, O_WEAK), _obs(3, 5.0, 999)]
    assert [o.value for o in corrector.correct(raw, M, A, B)] == [5.0, 5.0, 5.0]
    # no rating metric for the market: untouched
    assert corrector.correct([_obs(4, 5.0, O_LEAGUE)], "throw_ins_for", A, B)[
        0].value == 5.0
    assert corrector.correct([_obs(5, 1.0, O_LEAGUE)], "player_shots", A, B)[
        0].value == 1.0


def test_a_total_is_split_into_its_two_counts_and_each_is_corrected() -> None:
    corrector = SampleCorrector(_book())
    split_sample = MetricSample(metric=M, side_a=[_obs(1, 6.0, O_LEAGUE, 4.0)],
                               side_b=[], h2h=[])
    total = MetricSample(metric="corners_total",
                         side_a=[_obs(1, 10.0, O_LEAGUE)], side_b=[], h2h=[])
    pools = correct_total(corrector, {"corners_total": total, M: split_sample},
                          "corners_total", A, B)
    g = -0.5
    expected = 6.0 / 0.5 * math.exp(g) + 4.0 / 1.25 * math.exp(-g)
    assert pools[0][0].value == pytest.approx(expected)
    # a split that does not add up to the total, or none at all: raw
    bad = MetricSample(metric=M, side_a=[_obs(1, 6.0, O_LEAGUE, 3.0)],
                       side_b=[], h2h=[])
    assert correct_total(corrector, {"corners_total": total, M: bad},
                         "corners_total", A, B)[0][0].value == 10.0
    assert correct_total(corrector, {"corners_total": total},
                         "corners_total", A, B)[0][0].value == 10.0
    assert split_index(None) == {}


def test_an_h2h_match_is_read_from_the_side_it_was_recorded_for() -> None:
    corrector = SampleCorrector(_book())
    h2h = _obs(7, 9.0, A)  # recorded for B: its opponent is A
    total = MetricSample(metric="corners_total", side_a=[], side_b=[],
                         h2h=[h2h])
    split_sample = MetricSample(metric=M, side_a=[], side_b=[
        _obs(7, 5.0, A, 4.0)], h2h=[])
    book = corrector.book
    book.teams[(A, M)] = _Team(attack=2.0, defence=0.5, n=20)
    pools = correct_total(corrector, {"corners_total": total, M: split_sample},
                          "corners_total", A, B)
    # B's own 5 against A's defence, A's 4 against... B is A's opponent here,
    # and today's opponent too: the gap of the sample match is today's (0)
    p = CROSS_RATIO_POWER
    assert pools[2][0].value == pytest.approx(5.0 / 0.5 ** p + 4.0 / 2.0 ** p)


# --- SHEET -----------------------------------------------------------------


def _samples() -> FixtureSamples:
    side_a = [_obs(100 + i, v, O_LEAGUE, 3.0) for i, v in enumerate(
        [5, 6, 4, 7, 5, 6, 5, 4, 6, 5])]
    side_b = [_obs(200 + i, v, None, 3.0) for i, v in enumerate(
        [4, 5, 4, 6, 5, 4, 5, 3, 4, 5])]
    return FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={M: MetricSample(metric=M, side_a=side_a, side_b=side_b, h2h=[])},
    )


def _offer() -> FixtureOffer:
    return FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market=M, subject="Criciúma", line=5.5,
                          over_odds=1.9, under_odds=1.9,
                          fetched_at_utc=datetime(2026, 9, 22, tzinfo=UTC))],
    )


def _rows(corrector: SampleCorrector | None) -> list[dict[str, object]]:
    rows, _ = process_fixture(
        _fixture(), _samples(), _offer(), baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(),
        stats_only=True, sample_corrector=corrector)
    return [sheet_row_json(r) for r in rows]


def test_off_the_sheet_row_is_the_raw_sample_byte_for_byte() -> None:
    rows = _rows(None)
    assert rows
    for row in rows:
        assert "corrected_sample" not in row and "opponent_rule" not in row
        assert row["sample_mean"] == pytest.approx(5.3)
        assert not any("SAMPLE_OPPONENT_CORRECTED" in n for n in row["notes"])


def test_on_the_side_sample_is_rescaled_and_the_row_carries_what_it_priced() -> None:
    book = _book()
    book.team_comps[2] = deque([(TS, 100)] * 5)  # today's away in A's league
    book.teams[(O_LEAGUE, M)] = _Team(attack=1.25, defence=0.8, n=20)
    plain = _rows(None)
    rows = _rows(SampleCorrector(book))
    assert len(rows) == len(plain) == 2
    for row, raw in zip(rows, plain, strict=True):
        assert row["sample_mean"] == pytest.approx(5.3 / 0.8)
        assert row["corrected_sample"] == [
            round(v / 0.8, 4) for v in [5, 6, 4, 7, 5, 6, 5, 4, 6, 5]]
        assert row["p_central"] != raw["p_central"]
        assert any("SAMPLE_OPPONENT_CORRECTED: 10 of 10" in n for n in row["notes"])


def test_a_sample_nothing_could_correct_carries_no_corrected_sample() -> None:
    rows = _rows(SampleCorrector(RatingBook()))
    assert rows and all("corrected_sample" not in r for r in rows)
    assert [r["p_central"] for r in rows] == [r["p_central"] for r in _rows(None)]


# --- CONFIDENCE (A5) -------------------------------------------------------


def test_the_gates_read_the_corrected_sample_only_when_the_row_has_one() -> None:
    raw = [5.0, 6.0, 4.0]
    assert gate_values({}, raw) == raw
    assert gate_values({"corrected_sample": None}, raw) == raw
    assert gate_values({"corrected_sample": [10.0, 12.0, 8.0]}, raw) == [
        10.0, 12.0, 8.0]
    # a sample of another length is not this row's: the raw one
    assert gate_values({"corrected_sample": [1.0]}, raw) == raw


def test_mode_loses_reads_a_corrected_sample_rounded_to_counts() -> None:
    # every corrected value is distinct: unrounded, statistics.mode would be
    # the first value; rounded, it is the count the sample sits on
    corrected = [4.4, 3.6, 4.2, 6.9, 3.8]
    assert mode_values({"corrected_sample": corrected}, corrected) == [
        4.0, 4.0, 4.0, 7.0, 4.0]
    assert mode_values({}, [4.4, 3.6]) == [4.4, 3.6]


def test_goals_stay_raw_they_were_not_measured() -> None:
    book = _book()
    book.teams[(O_LEAGUE, "goals_for")] = _Team(attack=1.0, defence=0.5, n=20)
    out = SampleCorrector(book).correct([_obs(1, 2.0, O_LEAGUE)], "goals_for", A, B)
    assert out[0].value == 2.0


def test_confidence_calls_the_gates_through_gate_values() -> None:
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "scripts" / "sofa"
           / "run_confidence.py").read_text(encoding="utf-8")
    at = src.index("values = gate_values(row, values)")
    assert at < src.index("if line_is_beyond_sample(")
    assert at < src.index("own_gap = model_above_own_sample(")
    assert "mode_values(row, values)" in src[src.index("mode_loses(row["):][:200]


# --- switch ----------------------------------------------------------------


def test_the_switch_is_off_and_reads_the_day_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert epochs.SAMPLE_OPPONENT_CORRECTION_FROM_UTC is None
    assert not epochs.sample_opponent_correction(
        "2027-01-01", datetime(2027, 1, 1, tzinfo=UTC))
    start = datetime(2026, 10, 20, tzinfo=UTC)
    monkeypatch.setattr(epochs, "SAMPLE_OPPONENT_CORRECTION_FROM_UTC", start)
    assert epochs.sample_opponent_correction("2026-10-20", start)
    assert not epochs.sample_opponent_correction(
        "2026-10-19", start + timedelta(days=1))
    assert not epochs.sample_opponent_correction(
        "2026-10-20", start - timedelta(seconds=1))


def test_rebuild_reruns_sheet_on_a_raw_sample_sheet_once_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = epochs.SAMPLE_OPPONENT_CORRECTION
    assert epochs.sheet_sample_opponent_correction([{"opponent_rule": rule}])
    assert not epochs.sheet_sample_opponent_correction([{"opponent_rule": rule}, {}])
    assert epochs.sheet_sample_opponent_correction([])
    at = datetime(2026, 10, 20, 7, tzinfo=UTC)
    limit = timedelta(minutes=45)
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-20", at, limit, sheet_opponent=False)).names()
    monkeypatch.setattr(epochs, "SAMPLE_OPPONENT_CORRECTION_FROM_UTC",
                        datetime(2026, 10, 20, tzinfo=UTC))
    stale = rp.build_plan(rp.DayState("2026-10-20", at, limit, sheet_opponent=False))
    step = next(s for s in stale.steps if s.name == "SHEET")
    assert "opponents" in step.reason
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-20", at, limit, sheet_opponent=True)).names()


def test_the_markers_do_not_leak_into_a_default_row() -> None:
    rows = _rows(None)
    assert json.dumps(rows).count("opponent_rule") == 0
