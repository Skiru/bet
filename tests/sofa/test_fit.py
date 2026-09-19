"""T33–T35 — E11 constant fitting."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.db import get_connection, migrate
from scripts.sofa.fit_constants import (
    K_GRID,
    _pick_plateau_k,
    bucket_p,
    fit_baselines,
    fit_k_centre,
    fit_k_price,
    fit_max_ladder_sigma,
    fit_reliability,
)
from scripts.sofa.run_sheet import (
    get_calibration_correction,
    process_fixture,
    read_constant,
)


def seed_rows(db_path: str, rows: list[dict[str, Any]]) -> None:
    with get_connection(db_path) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO sofa_settled_row (
                    run_date, sofascore_event_id, sport, competition_id,
                    market, subject, line, direction, sample_size, sample_mean,
                    sample_sd, p_central, p_bar, market_p, actual_value,
                    outcome, settled_at, ladder_sigma
                ) VALUES (
                    :run_date, :sofascore_event_id, :sport, :competition_id,
                    :market, :subject, :line, :direction, :sample_size,
                    :sample_mean, :sample_sd, :p_central, :p_bar, :market_p,
                    :actual_value, :outcome, :settled_at, :ladder_sigma
                )
                """,
                row,
            )
        conn.commit()


def base_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "run_date": "2026-09-01",
        "sofascore_event_id": 1,
        "sport": "football",
        "competition_id": 17,
        "market": "goals_total",
        "subject": "",
        "line": 2.5,
        "direction": "OVER",
        "sample_size": 10,
        "sample_mean": 2.6,
        "sample_sd": 1.2,
        "p_central": 0.55,
        "p_bar": 0.55,
        "market_p": None,
        "actual_value": 3.0,
        "outcome": "WIN",
        "settled_at": "2026-09-02T00:00:00+00:00",
        "ladder_sigma": None,
    }
    row.update(overrides)
    return row


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "sofa.db")
    migrate(path)
    return path


# --------------------------------------------------------------------------
# T33 — the fit is deterministic.
# --------------------------------------------------------------------------


def test_fit_is_deterministic(db: str) -> None:
    rows = [
        base_row(
            sofascore_event_id=i,
            competition_id=17 if i % 2 else 8,
            actual_value=float(i % 6),
            p_central=0.3 + (i % 7) / 10.0,
            outcome="WIN" if i % 3 else "LOSS",
            market_p=0.5,
        )
        for i in range(200)
    ]
    seed_rows(db, rows)

    with get_connection(db) as conn:
        first = (
            json.dumps(fit_baselines(conn), sort_keys=True),
            json.dumps(fit_reliability(conn), sort_keys=True),
            fit_k_centre(conn, fit_baselines(conn)),
            fit_k_price(conn),
        )
        second = (
            json.dumps(fit_baselines(conn), sort_keys=True),
            json.dumps(fit_reliability(conn), sort_keys=True),
            fit_k_centre(conn, fit_baselines(conn)),
            fit_k_price(conn),
        )
    assert first == second


# --------------------------------------------------------------------------
# The baseline must not be biased by aggregation or by dropping pushes (C5).
# --------------------------------------------------------------------------


def test_baseline_does_not_take_the_larger_side_of_a_for_market(db: str) -> None:
    """A `_for` market has two subjects per event with two different values.

    Aggregating over the event picks the larger one every time and walks the
    prior upward — silently, and in the direction that makes OVER look better.
    """
    rows = []
    for event_id in range(40):
        rows.append(
            base_row(
                sofascore_event_id=event_id,
                market="corners_for",
                subject="Home",
                actual_value=8.0,
            )
        )
        rows.append(
            base_row(
                sofascore_event_id=event_id,
                market="corners_for",
                subject="Away",
                actual_value=2.0,
            )
        )
    seed_rows(db, rows)

    with get_connection(db) as conn:
        baselines = fit_baselines(conn)

    # The true mean of {8, 2} repeated is 5.0. Taking the max per event gives 8.
    assert baselines["corners_for"]["17"]["mean"] == pytest.approx(5.0)
    assert baselines["corners_for"]["17"]["n"] == 80


def test_baseline_includes_events_that_landed_on_the_line(db: str) -> None:
    """Excluding PUSH removes exactly the integer-valued events — a biased slice."""
    rows = [
        base_row(sofascore_event_id=i, actual_value=2.0, line=2.0, outcome="PUSH")
        for i in range(30)
    ] + [
        base_row(sofascore_event_id=100 + i, actual_value=4.0, outcome="WIN")
        for i in range(30)
    ]
    seed_rows(db, rows)

    with get_connection(db) as conn:
        baselines = fit_baselines(conn)

    assert baselines["goals_total"]["17"]["n"] == 60
    assert baselines["goals_total"]["17"]["mean"] == pytest.approx(3.0)


def test_thin_league_falls_back_to_the_global_pool(db: str) -> None:
    rows = [
        base_row(sofascore_event_id=i, competition_id=17, actual_value=3.0)
        for i in range(40)
    ] + [
        base_row(sofascore_event_id=100 + i, competition_id=999, actual_value=1.0)
        for i in range(5)
    ]
    seed_rows(db, rows)

    with get_connection(db) as conn:
        baselines = fit_baselines(conn)

    assert "17" in baselines["goals_total"]
    assert "999" not in baselines["goals_total"], "5 observations is not a prior"
    assert "global" in baselines["goals_total"]


# --------------------------------------------------------------------------
# The calibration correction only ever raises the bar.
# --------------------------------------------------------------------------


def test_reliability_emits_no_correction_when_the_interval_straddles_zero(
    db: str,
) -> None:
    """A correction that fires in both directions fits noise it has not measured.

    Seeds MIN_BUCKET_ROWS worth of rows on purpose: the rule under test is the
    straddling interval, and a bucket thinner than the row floor never reaches
    it. At 100 this asserted the floor instead, which is a different test that
    already exists.
    """
    rows = [
        base_row(
            sofascore_event_id=i,
            p_central=0.55,
            outcome="WIN" if i % 2 else "LOSS",
        )
        for i in range(200)
    ]
    seed_rows(db, rows)

    with get_connection(db) as conn:
        reliability = fit_reliability(conn)

    bucket = reliability["goals_total"][bucket_p(0.55)]
    assert bucket["correction"] == 0.0
    assert bucket["ci_lower"] <= 0


def test_reliability_corrects_measured_overconfidence(db: str) -> None:
    """Declared 0.85, realised 0.50 over 200 rows: a gap the interval clears."""
    rows = [
        base_row(
            sofascore_event_id=i, p_central=0.85, outcome="WIN" if i % 2 else "LOSS"
        )
        for i in range(200)
    ]
    seed_rows(db, rows)

    with get_connection(db) as conn:
        reliability = fit_reliability(conn)

    bucket = reliability["goals_total"][bucket_p(0.85)]
    assert bucket["realised"] == pytest.approx(0.5)
    assert bucket["correction"] == pytest.approx(0.35, abs=0.01)
    assert bucket["ci_lower"] > 0


def test_a_five_point_gap_at_n200_does_not_justify_a_correction(db: str) -> None:
    """The interval, not the point estimate, decides.

    Declared 0.85 against a realised 0.80 is a 5pp gap — real-looking, and not
    separable from zero at this sample size. Correcting on it would be fitting
    noise, and the correction would then be applied to every row of the market.
    """
    rows = [
        base_row(
            sofascore_event_id=i, p_central=0.85, outcome="WIN" if i % 5 else "LOSS"
        )
        for i in range(200)
    ]
    seed_rows(db, rows)

    with get_connection(db) as conn:
        reliability = fit_reliability(conn)

    bucket = reliability["goals_total"][bucket_p(0.85)]
    assert bucket["realised"] == pytest.approx(0.8)
    assert bucket["correction"] == 0.0
    assert bucket["ci_lower"] <= 0


# --------------------------------------------------------------------------
# T34 — every gate is scale-free.
# --------------------------------------------------------------------------


def _sheet_rows_at_scale(scale: float) -> list[Any]:
    """Price the same shape of market with every quantity multiplied by `scale`."""
    fixture = Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["sb1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 18, 0, tzinfo=UTC),
        home_name="Arsenal",
        away_name="Chelsea",
        home_entity_id=42,
        away_entity_id=38,
        competition_name="PL",
        competition_id=17,
        season_id=1,
        category_name="England",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )
    raw_values = [2.0, 3.0, 4.0, 2.0, 5.0, 3.0]

    def obs(values: list[float], start: int) -> list[Observation]:
        return [
            Observation(
                sofascore_event_id=start + i,
                match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
                opponent=f"Opp{i}",
                value=v * scale,
                competition_id=17,
                season_id=1,
                venue="home",
            )
            for i, v in enumerate(values)
        ]

    samples = FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        metrics={
            "goals_total": MetricSample(
                metric="goals_total",
                side_a=obs(raw_values, 1000),
                side_b=obs(raw_values, 2000),
                h2h=[],
            )
        },
        gaps=[],
    )
    offer = FixtureOffer(
        sofascore_event_id=1,
        status="PRICED",
        rungs=[
            PricedRung(
                market="goals_total",
                subject="",
                line=line * scale,
                over_odds=over,
                under_odds=under,
                fetched_at_utc=datetime(2026, 9, 17, 10, 0, tzinfo=UTC),
            )
            for line, over, under in [(2.5, 1.60, 2.30), (3.5, 2.60, 1.48)]
        ],
        unmapped_markets=[],
    )
    rows, _ = process_fixture(fixture, samples, offer, {}, {}, {}, [], SofaConfig())
    return rows


def test_ladder_sigma_is_scale_free() -> None:
    """L15: the gate must fire on the error, not on the size of the numbers.

    Corners live around 10 and goals around 2.7. A band on a raw difference or
    a raw ratio fires on whichever market happens to have bigger numbers, and
    looks exactly like it is detecting a problem.
    """
    base = _sheet_rows_at_scale(1.0)
    scaled = _sheet_rows_at_scale(4.0)

    assert base and scaled
    assert len(base) == len(scaled)

    base_sigmas = [r.ladder_sigma for r in base]
    scaled_sigmas = [r.ladder_sigma for r in scaled]
    assert any(s is not None for s in base_sigmas), "need a measured sigma to compare"

    for a, b in zip(base_sigmas, scaled_sigmas, strict=True):
        if a is None or b is None:
            assert a is None and b is None
            continue
        assert a == pytest.approx(b, abs=1e-3), (
            f"ladder_sigma moved from {a} to {b} when every quantity was "
            "multiplied by 4; the gate is reading magnitude, not error"
        )


def test_verdicts_are_scale_free() -> None:
    """Multiplying every quantity by a constant must not change any verdict."""
    base = _sheet_rows_at_scale(1.0)
    scaled = _sheet_rows_at_scale(4.0)
    assert [r.verdict for r in base] == [r.verdict for r in scaled]


def test_max_ladder_sigma_band_edges_come_from_the_data(db: str) -> None:
    """The fitted threshold is a quantile of the observed spread, not a constant."""
    rows = [
        base_row(
            sofascore_event_id=i,
            ladder_sigma=(i % 50) / 10.0,
            p_central=0.8,
            outcome="LOSS" if (i % 50) / 10.0 > 3.0 else "WIN",
        )
        for i in range(600)
    ]
    seed_rows(db, rows)

    with get_connection(db) as conn:
        threshold, report = fit_max_ladder_sigma(conn)

    assert report["status"] in {"FITTED", "NO_DIVERGENCE"}
    assert report["rows_available"] == 600
    if threshold is not None:
        observed = [r["ladder_sigma"] for r in rows]
        assert min(observed) <= threshold <= max(observed)


def test_max_ladder_sigma_is_null_without_ladder_rows(db: str) -> None:
    """A9: the backfill cannot fit this. Say NOT_FITTED, do not write 1.25."""
    seed_rows(db, [base_row(sofascore_event_id=i) for i in range(500)])
    with get_connection(db) as conn:
        threshold, report = fit_max_ladder_sigma(conn)
    assert threshold is None
    assert report["status"] == "NOT_FITTED"
    assert "Superbet ladder" in report["reason"]


# --------------------------------------------------------------------------
# The plateau rule: smallest K on the plateau, not the point minimum.
# --------------------------------------------------------------------------


def test_plateau_pick_prefers_the_larger_k_on_a_flat_curve() -> None:
    """Among values the data cannot tell apart, shrink more, not less.

    This asserted ``== 2.0`` until F42. The rule's own docstring argued that
    trusting the sample too much is the error that has already cost money and
    that a smaller K trusts the sample more, and then returned the smallest K
    on the plateau — the most sample-trusting value available. The test
    encoded the behaviour rather than the reasoning, so it held the
    contradiction in place.
    """
    curve = {0.0: 0.4100, 2.0: 0.3500, 5.0: 0.3495, 10.0: 0.3490, 25.0: 0.3489}
    # The point minimum is 25.0; everything from 2.0 up is within tolerance,
    # and 0.0 is measurably worse, so the band is not the whole grid.
    assert min(curve, key=lambda k: curve[k]) == 25.0
    assert _pick_plateau_k(curve) == 25.0


def test_plateau_pick_respects_a_genuine_minimum() -> None:
    curve = {0.0: 0.50, 2.0: 0.45, 5.0: 0.30, 10.0: 0.42}
    assert _pick_plateau_k(curve) == 5.0


def test_k_grid_matches_the_plan() -> None:
    assert K_GRID == [0.0, 2.0, 5.0, 8.0, 10.0, 15.0, 25.0, 1000.0]


# --------------------------------------------------------------------------
# T35 — a missing config degrades to documented behaviour, never to a crash
# and never to a number from nowhere.
# --------------------------------------------------------------------------


def test_missing_reliability_means_no_correction() -> None:
    assert get_calibration_correction({}, "goals_total", 0.55) == 0.0
    assert get_calibration_correction({"other_market": {}}, "goals_total", 0.55) == 0.0


def test_a_null_constant_is_not_fitted() -> None:
    value, fitted = read_constant({"K_CENTRE": {"value": None}}, "K_CENTRE", 10.0)
    assert value == 10.0
    assert fitted is False


def test_a_missing_constant_is_not_fitted() -> None:
    value, fitted = read_constant({}, "K_PRICE", 10.0)
    assert value == 10.0
    assert fitted is False


def test_a_fitted_constant_is_used_and_marked() -> None:
    value, fitted = read_constant({"K_PRICE": {"value": 5.0}}, "K_PRICE", 10.0)
    assert value == 5.0
    assert fitted is True


def test_unfitted_constants_are_recorded_on_every_row() -> None:
    """An engine running on placeholders must not look like a calibrated one."""
    rows = _sheet_rows_at_scale(1.0)
    assert rows
    for row in rows:
        assert any(note.startswith("UNFITTED_CONSTANTS") for note in row.notes)


def test_shipped_constants_file_does_not_claim_to_be_fitted() -> None:
    """The repo's config must not assert a value it never measured (§6.0)."""
    path = Path("config/sofa_engine_constants.json")
    if not path.exists():
        pytest.skip("no constants file shipped")
    constants = json.loads(path.read_text(encoding="utf-8"))
    for name in ("K_CENTRE", "K_PRICE", "MAX_LADDER_SIGMA"):
        entry = constants[name]
        if entry.get("value") is not None:
            assert entry.get("status") == "FITTED", (
                f"{name} has a value but is not marked FITTED"
            )
            assert constants["fitted_from"]["settled_rows"] > 0
