"""T30–T32 — E10 settlement and backfill."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa.db import get_connection, migrate
from bet.sofa.settle import (
    SettledRow,
    historical_sample,
    insert_settled_rows,
    is_completed_event,
    line_grid,
    settle,
    settle_metric,
)

# --------------------------------------------------------------------------
# T30 — settlement is pure, and an integer line pushes.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "line", "direction", "expected"),
    [
        # Half lines: never a push, one side always wins.
        (3.0, 2.5, "OVER", "WIN"),
        (2.0, 2.5, "OVER", "LOSS"),
        (2.0, 2.5, "UNDER", "WIN"),
        (3.0, 2.5, "UNDER", "LOSS"),
        # Integer lines: an exact hit is a PUSH for BOTH directions.
        (2.0, 2.0, "OVER", "PUSH"),
        (2.0, 2.0, "UNDER", "PUSH"),
        (3.0, 2.0, "OVER", "WIN"),
        (1.0, 2.0, "OVER", "LOSS"),
        (1.0, 2.0, "UNDER", "WIN"),
        (3.0, 2.0, "UNDER", "LOSS"),
        # Zero is a real value, not a missing one.
        (0.0, 0.5, "UNDER", "WIN"),
        (0.0, 0.0, "OVER", "PUSH"),
        # Non-integer realised values (xG).
        (1.73, 1.5, "OVER", "WIN"),
        (1.5, 1.5, "OVER", "PUSH"),
    ],
)
def test_settle_table(
    actual: float, line: float, direction: str, expected: str
) -> None:
    assert settle(actual, line, direction) == expected  # type: ignore[arg-type]


def test_push_mass_is_never_given_to_a_side() -> None:
    """On an integer line neither OVER nor UNDER may claim an exact hit."""
    for line in (1.0, 2.0, 3.0, 10.0):
        assert settle(line, line, "OVER") == "PUSH"
        assert settle(line, line, "UNDER") == "PUSH"


def test_settle_is_pure() -> None:
    """Same inputs, same answer — no hidden state anywhere in settlement."""
    first = [settle(float(v), 2.5, "OVER") for v in range(6)]
    second = [settle(float(v), 2.5, "OVER") for v in range(6)]
    assert first == second


# --------------------------------------------------------------------------
# T31 — no future leak on the backfill path.
# --------------------------------------------------------------------------


def _event(
    event_id: int,
    ts: datetime,
    *,
    home_id: int = 1,
    away_id: int = 2,
    home_goals: int = 1,
    away_goals: int = 1,
    status_type: str = "finished",
    status_code: int = 100,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "startTimestamp": int(ts.timestamp()),
        "status": {"type": status_type, "code": status_code},
        "homeTeam": {"id": home_id, "name": f"T{home_id}"},
        "awayTeam": {"id": away_id, "name": f"T{away_id}"},
        "homeScore": {
            "current": home_goals,
            "period1": home_goals,
            "period2": 0,
            "normaltime": home_goals,
        },
        "awayScore": {
            "current": away_goals,
            "period1": away_goals,
            "period2": 0,
            "normaltime": away_goals,
        },
        "tournament": {"uniqueTournament": {"id": 17}},
        "season": {"id": 1},
    }


def test_backfill_sample_excludes_the_match_day_and_everything_after() -> None:
    """T31: a sample for a match on day D holds nothing from day >= D."""
    kickoff = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)
    events = [
        _event(1, datetime(2026, 5, 1, 18, 0, tzinfo=UTC)),
        _event(2, datetime(2026, 5, 5, 18, 0, tzinfo=UTC)),
        # Exactly at kickoff — the boundary case that leaks most quietly.
        _event(3, kickoff),
        # After kickoff — the future.
        _event(4, datetime(2026, 5, 20, 18, 0, tzinfo=UTC)),
    ]

    sampled = historical_sample(
        events,
        before_utc=kickoff,
        entity_id=1,
        sport="football",
        metric="goals_total",
        metrics_by_event={},
        incidents_by_event={},
        sample_n=10,
    )

    assert [event_id for event_id, _ in sampled] == [2, 1]


def test_backfill_sample_requires_aware_datetime() -> None:
    """A naive boundary is a boundary in the wrong timezone (L21)."""
    with pytest.raises(ValueError, match="timezone-aware"):
        historical_sample(
            [],
            before_utc=datetime(2026, 5, 10, 18, 0),  # noqa: DTZ001 - the point of the test
            entity_id=1,
            sport="football",
            metric="goals_total",
            metrics_by_event={},
            incidents_by_event={},
            sample_n=10,
        )


def test_backfill_sample_excludes_friendlies() -> None:
    kickoff = datetime(2026, 5, 10, tzinfo=UTC)
    league = _event(1, datetime(2026, 5, 1, tzinfo=UTC))
    friendly = _event(2, datetime(2026, 5, 2, tzinfo=UTC))
    friendly["tournament"]["uniqueTournament"]["id"] = 853

    sampled = historical_sample(
        [league, friendly],
        before_utc=kickoff,
        entity_id=1,
        sport="football",
        metric="goals_total",
        metrics_by_event={},
        incidents_by_event={},
        sample_n=10,
        excluded_competition_ids=frozenset({853}),
    )
    assert [event_id for event_id, _ in sampled] == [1]


def test_backfill_sample_dedupes_one_match_to_one_observation() -> None:
    """L13: the same historical match twice in the listing is one observation."""
    kickoff = datetime(2026, 5, 10, tzinfo=UTC)
    duplicated = _event(7, datetime(2026, 5, 1, tzinfo=UTC))
    sampled = historical_sample(
        [duplicated, dict(duplicated)],
        before_utc=kickoff,
        entity_id=1,
        sport="football",
        metric="goals_total",
        metrics_by_event={},
        incidents_by_event={},
        sample_n=10,
    )
    assert len(sampled) == 1


# --------------------------------------------------------------------------
# T32 — "ret" in a surname is not a retirement.
# --------------------------------------------------------------------------


def test_berrettini_is_not_a_retirement() -> None:
    """L31: status comes from status fields, never from a name."""
    event = _event(1, datetime(2026, 5, 1, tzinfo=UTC))
    event["homeTeam"]["name"] = "Matteo Berrettini"
    event["awayTeam"]["name"] = "Stefanos Tsitsipas"
    assert is_completed_event(event) is True


@pytest.mark.parametrize(
    "name",
    [
        "Matteo Berrettini",
        "Lorenzo Sonego",  # contains no marker but is a control
        "Retief Retirement",  # adversarial: the word itself, in a name
        "Jiri Vesely (ret)",  # adversarial: the marker, in a name
    ],
)
def test_names_never_decide_completion(name: str) -> None:
    event = _event(1, datetime(2026, 5, 1, tzinfo=UTC))
    event["homeTeam"]["name"] = name
    assert is_completed_event(event) is True


def test_retirement_is_read_from_the_status_code() -> None:
    event = _event(1, datetime(2026, 5, 1, tzinfo=UTC), status_code=91)
    assert is_completed_event(event) is False


@pytest.mark.parametrize(
    "status_type", ["canceled", "postponed", "notstarted", "inprogress"]
)
def test_unfinished_events_are_not_settleable(status_type: str) -> None:
    event = _event(1, datetime(2026, 5, 1, tzinfo=UTC), status_type=status_type)
    assert is_completed_event(event) is False


def test_retired_match_never_reaches_the_sample() -> None:
    kickoff = datetime(2026, 5, 10, tzinfo=UTC)
    played = _event(1, datetime(2026, 5, 1, tzinfo=UTC))
    retired = _event(2, datetime(2026, 5, 2, tzinfo=UTC), status_code=91)
    retired["homeTeam"]["name"] = "Matteo Berrettini"

    sampled = historical_sample(
        [played, retired],
        before_utc=kickoff,
        entity_id=1,
        sport="football",
        metric="goals_total",
        metrics_by_event={},
        incidents_by_event={},
        sample_n=10,
    )
    assert [event_id for event_id, _ in sampled] == [1]


# --------------------------------------------------------------------------
# settle_metric and persistence
# --------------------------------------------------------------------------


def test_line_grid_is_always_half_integer_and_positive() -> None:
    for centre in (0.4, 2.6, 9.3, 25.0):
        for sd in (0.0, 1.5, 6.0):
            grid = line_grid(centre, sd)
            assert grid, (centre, sd)
            assert all(g > 0 for g in grid)
            assert all(abs(g * 2 - round(g * 2)) < 1e-9 for g in grid)


def test_settle_metric_refuses_a_sample_below_min() -> None:
    event = _event(1, datetime(2026, 5, 1, tzinfo=UTC))
    rows = settle_metric(
        run_date="2026-05-01",
        event=event,
        sport="football",
        metric="goals_total",
        actual_value=3.0,
        sample_values=[1.0, 2.0],
        min_sample=5,
        k_centre=10.0,
        k_price=10.0,
        prior=None,
    )
    assert rows == []


def test_settle_metric_leaves_market_p_null_backwards() -> None:
    """A9: no historical Superbet price exists, so none may be invented."""
    event = _event(1, datetime(2026, 5, 1, tzinfo=UTC))
    rows = settle_metric(
        run_date="2026-05-01",
        event=event,
        sport="football",
        metric="goals_total",
        actual_value=3.0,
        sample_values=[1.0, 2.0, 3.0, 2.0, 4.0, 1.0],
        min_sample=5,
        k_centre=10.0,
        k_price=10.0,
        prior=None,
    )
    assert rows
    assert all(row.market_p is None for row in rows)
    assert {row.outcome for row in rows} <= {"WIN", "LOSS", "PUSH"}


def test_settle_metric_outcome_matches_the_pure_function() -> None:
    """The stored outcome is the one settle() gives — one settlement, not two."""
    event = _event(1, datetime(2026, 5, 1, tzinfo=UTC))
    rows = settle_metric(
        run_date="2026-05-01",
        event=event,
        sport="football",
        metric="goals_total",
        actual_value=2.0,
        sample_values=[1.0, 2.0, 3.0, 2.0, 4.0, 1.0],
        min_sample=5,
        k_centre=10.0,
        k_price=10.0,
        prior=None,
    )
    for row in rows:
        assert row.outcome == settle(row.actual_value, row.line, row.direction)


def test_insert_settled_rows_is_idempotent(tmp_path: Any) -> None:
    db_path = str(tmp_path / "sofa.db")
    migrate(db_path)
    row = SettledRow(
        run_date="2026-05-01",
        sofascore_event_id=1,
        sport="football",
        competition_id=17,
        market="goals_total",
        subject="",
        line=2.5,
        direction="OVER",
        sample_size=8,
        sample_mean=2.4,
        sample_sd=1.1,
        p_central=0.48,
        p_bar=0.48,
        market_p=None,
        actual_value=3.0,
        outcome="WIN",
        settled_at="2026-05-02T00:00:00+00:00",
    )
    with get_connection(db_path) as conn:
        assert insert_settled_rows(conn, [row]) == 1
        assert insert_settled_rows(conn, [row]) == 0
        count = conn.execute("SELECT COUNT(*) AS c FROM sofa_settled_row").fetchone()[
            "c"
        ]
    assert count == 1
