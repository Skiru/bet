"""Audit 2026-10-13 stage 4: C1 (season phase of the goals centre) and B14
(the football rating's weight per market). Offline and fast. Evidence:
docs/sofa/evidence/season_phase_2026-10-13.md,
docs/sofa/evidence/rating_weight_2026-10-13.md."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from bet.sofa import rating_weight as rw
from bet.sofa import season_phase as sp
from tests.sofa.test_audit_2026_10_13_b1b2 import _book, _over, _rows

DAY = 86400


# --- switches -------------------------------------------------------------


@pytest.mark.parametrize("name,pred", [
    ("SEASON_PHASE_FROM_UTC", epochs.season_phase_enabled),
    ("FOOTBALL_RATING_WEIGHT_FROM_UTC", epochs.football_rating_weight),
])
def test_stage4_switches_are_off_and_read_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch, name: str, pred: object) -> None:
    assert getattr(epochs, name) is None
    check = pred  # type: ignore[assignment]
    late = datetime(2027, 1, 1, tzinfo=UTC)
    assert not check("2027-01-01", late)  # type: ignore[operator]
    monkeypatch.setattr(epochs, name, datetime(2026, 10, 14, tzinfo=UTC))
    assert check("2026-10-14", datetime(2026, 10, 14, 1, tzinfo=UTC))  # type: ignore[operator]
    assert not check("2026-10-13", late)  # type: ignore[operator]
    assert not check("2026-10-14", datetime(2026, 10, 13, 23, tzinfo=UTC))  # type: ignore[operator]


# --- C1: season phase -----------------------------------------------------


def test_phase_label_cuts() -> None:
    assert sp.phase_label(1, 38) == sp.PHASE_EARLY
    assert sp.phase_label(3, 38) == sp.PHASE_EARLY
    assert sp.phase_label(3.5, 38) == sp.PHASE_MID
    assert sp.phase_label(30.5, 38) == sp.PHASE_LATE
    assert sp.phase_label(29, 38) == sp.PHASE_MID
    assert sp.phase_label(37, 38) == sp.PHASE_FINAL
    assert sp.phase_label(38, 38) == sp.PHASE_FINAL
    assert sp.phase_label(39, 38) is None  # a changed format
    assert sp.phase_label(2, 6) is None  # a cup / group stage


def _season(comp: int, season: int, start: int, teams: int, rounds: int,
            first_id: int) -> list[fr.FootballResult]:
    """A round robin: each round every team plays once, a week apart."""
    out = []
    eid = first_id
    for rnd in range(rounds):
        for k in range(teams // 2):
            home, away = 1 + (k + rnd) % teams, 1 + (teams - 1 - k + rnd) % teams
            out.append(fr.FootballResult(
                eid, start + rnd * 7 * DAY + k, comp, home, away,
                {"goals_for": (1.0, 1.0)}, season_id=season))
            eid += 1
    return out


def test_the_index_reads_the_previous_season_and_never_the_future() -> None:
    prev = _season(1, 10, 0, 20, 38, 1)
    cur = _season(1, 11, 400 * DAY, 20, 38, 10_000)
    history = sorted(prev + cur, key=lambda r: r.ts)
    phases = sp.phases_by_event(history)
    # the first season has no previous one: no phase at all
    assert all(phases[r.event_id] is None for r in prev)
    by_round = {}
    for r in cur:
        rnd = (r.ts - 400 * DAY) // (7 * DAY) + 1
        by_round.setdefault(rnd, set()).add(phases[r.event_id])
    assert by_round[1] == {sp.PHASE_EARLY} and by_round[3] == {sp.PHASE_EARLY}
    assert by_round[4] == {sp.PHASE_MID} and by_round[30] == {sp.PHASE_MID}
    assert by_round[31] == {sp.PHASE_LATE}
    assert by_round[37] == {sp.PHASE_FINAL} and by_round[38] == {sp.PHASE_FINAL}
    # as of: the index cut before round 37 says round 37 even though the
    # season's matches after it exist in the history
    cut = 400 * DAY + 36 * 7 * DAY
    idx = sp.index_from_history(history, cut)
    r37 = next(r for r in cur if r.ts >= cut)
    assert idx.match_round(1, 11, r37.home_id, r37.away_id) == 37
    assert idx.phase(1, 11, r37.ts, r37.home_id, r37.away_id) == sp.PHASE_FINAL
    # a season id of None has no phase
    assert idx.phase(1, None, r37.ts, 1, 2) is None


def test_fit_coefficients_recovers_a_relative_phase_effect() -> None:
    centres, ys, labels = [], [], []
    truth = {sp.PHASE_EARLY: -0.03, sp.PHASE_LATE: 0.05, sp.PHASE_FINAL: 0.11}
    for i in range(4000):
        p = sp.PHASES[i % 4]
        c = 1.0 + (i % 5) * 0.3
        centres.append(c)
        # mid has a level bias of +10%: it must not leak into the phases
        ys.append(c * 1.1 * math.exp(truth.get(p, 0.0)))
        labels.append(p)
    coefs = sp.fit_coefficients(centres, ys, labels)
    assert coefs.keys() == truth.keys()
    for p, c in truth.items():
        assert coefs[p] == pytest.approx(c, abs=1e-9)
    # thin cells give nothing
    assert sp.fit_coefficients(centres[:100], ys[:100], labels[:100]) == {}


def test_the_table_parses_and_refuses() -> None:
    t = sp.parse_table({"markets": {"goals_for": {"coefficients": {"final": 0.1}}}})
    assert t.multiplier("goals_for", sp.PHASE_FINAL) == pytest.approx(math.exp(0.1))
    assert t.multiplier("goals_for", sp.PHASE_MID) is None
    assert t.multiplier("goals_for", None) is None
    assert t.multiplier("corners_for", sp.PHASE_FINAL) is None
    assert sp.apply(2.0, "goals_for", sp.PHASE_FINAL, None) == (2.0, None)
    for bad in ({}, {"markets": {"corners_for": {"coefficients": {}}}},
                {"markets": {"goals_for": {"coefficients": {"mid": 0.1}}}},
                {"markets": {"goals_for": {"coefficients": {"late": 2.0}}}}):
        with pytest.raises(ValueError):
            sp.parse_table(bad)


def test_season_phase_off_is_byte_for_byte_and_on_moves_the_goals_centre() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    plain = _rows("goals_for", fc)
    assert json.dumps(plain) == json.dumps(
        _rows("goals_for", fc, season_phase=None, season_phase_label="final"))
    table = sp.SeasonPhaseTable({"goals_for": {"final": 0.1}})
    moved = _over(_rows("goals_for", fc, season_phase=table,
                        season_phase_label=sp.PHASE_FINAL))
    base = _over(plain)
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * math.exp(0.1), abs=1e-3)  # type: ignore[arg-type]
    assert any(n.startswith("SEASON_PHASE") for n in moved["notes"])  # type: ignore[attr-defined]
    assert any("SEASON_PHASE_LATE_SHARE" in n for n in moved["notes"]  # type: ignore[attr-defined]
               if n.startswith("UNFITTED_CONSTANTS"))
    # mid season / no phase / another market: untouched
    for label in (sp.PHASE_MID, None):
        assert _rows("goals_for", fc, season_phase=table,
                     season_phase_label=label) == plain
    assert _rows("corners_for", fc, season_phase=table,
                 season_phase_label=sp.PHASE_FINAL) == _rows("corners_for", fc)


# --- B14: rating weight per market ----------------------------------------


def test_blend_off_is_the_half_blend() -> None:
    assert rw.blend(3.0, 1.0, "goals_for", None) == (
        fr.W_FOOTBALL_RATING * 3.0 + (1 - fr.W_FOOTBALL_RATING) * 1.0)
    t = rw.RatingWeightTable({"goals_for": 0.8})
    assert rw.blend(3.0, 1.0, "goals_for", t) == pytest.approx(0.8 * 3 + 0.2 * 1)
    assert rw.weight_for("shots_for", t) == fr.W_FOOTBALL_RATING
    for bad in ({}, {"markets": {"goals_for": {"w": 1.5}}},
                {"markets": {"goals_for": {"w": True}}}):
        with pytest.raises(ValueError):
            rw.parse_table(bad)


def test_fit_weight_finds_the_rating_when_the_rating_is_the_truth() -> None:
    rated = [1.0 + (i % 7) * 0.4 for i in range(600)]
    sample = [2.0] * 600
    y = [float(round(r)) for r in rated]
    w, loss = rw.fit_weight(rated, sample, y, [0.05] * 600)
    assert w >= 0.8 and math.isfinite(loss)
    # the sample is the truth: W at 0
    w0, _ = rw.fit_weight(rated, [float(v) for v in y], y, [0.05] * 600)
    assert w0 <= 0.2
    assert rw.fit_weight([], [], [], []) == (fr.W_FOOTBALL_RATING, pytest.approx(
        float("nan"), nan_ok=True))


def test_rating_weight_off_is_byte_for_byte_and_on_moves_the_centre() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    plain = _rows("goals_for", fc)
    assert json.dumps(plain) == json.dumps(
        _rows("goals_for", fc, rating_weights=None))
    # a table without the market: the same centre as W_FOOTBALL_RATING
    same = _over(_rows("goals_for", fc, rating_weights=rw.RatingWeightTable({})))
    assert same["centre"] == _over(plain)["centre"]
    moved = _over(_rows("goals_for", fc,
                        rating_weights=rw.RatingWeightTable({"goals_for": 0.6})))
    rated = fc.centre("goals_for", "side_a")
    assert rated is not None
    sample_centre = 2 * float(same["centre"]) - rated[0]  # type: ignore[arg-type]
    assert moved["centre"] == pytest.approx(
        0.6 * rated[0] + 0.4 * sample_centre, abs=2e-3)
    assert moved["centre"] != same["centre"]
    assert any("market's own" in n for n in moved["notes"])  # type: ignore[attr-defined]


def test_the_shipped_tables_read_and_hold_only_the_markets_that_passed() -> None:
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    phase = sp.load_table(repo / "config" / sp.CONFIG_FILE)
    assert set(phase.coefficients) == set(sp.SEASON_PHASE_MARKETS)
    # the end of a season scores more than its middle, the start less
    for coefs in phase.coefficients.values():
        assert coefs["final"] > 0 and coefs["late"] > 0 and coefs["early"] < 0
    weights = rw.load_table(repo / "config" / rw.CONFIG_FILE)
    # the full-match totals did not pass: they keep W_FOOTBALL_RATING
    assert not {"goals_total", "shots_total", "fouls_total",
                "cards_points_total"} & set(weights.weights)
    assert weights.weights["goals_for"] > fr.W_FOOTBALL_RATING
    assert not set(weights.weights) & fr.UNRATED_MARKETS
