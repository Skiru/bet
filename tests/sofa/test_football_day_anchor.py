"""K8 (identity plan): RESOLVE's football day anchor -
resolve.football_day_anchor_event, epochs.FOOTBALL_DAY_ANCHOR_FROM_UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from bet.sofa import epochs
from bet.sofa.resolve import football_day_anchor_event

KICK = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def _ev(
    eid: int,
    home: int,
    away: int,
    start: datetime = KICK,
    status: str = "notstarted",
    gender: str = "M",
) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": int(start.timestamp()),
        "status": {"type": status},
        "tournament": {"name": "Qatar League 2"},
        "homeTeam": {"id": home, "name": f"t{home}", "gender": gender},
        "awayTeam": {"id": away, "name": f"t{away}", "gender": gender},
    }


def _pick(
    events: list[dict[str, Any]],
    anchor: int = 1,
    other: int | None = None,
    side_a: bool = True,
    a: str = "Al Mesaimeer",
    b: str = "Etihad AL Gharafa",
) -> dict[str, Any] | None:
    return football_day_anchor_event(events, anchor, other, KICK, side_a, a, b)


def test_the_anchors_only_game_of_the_hour_in_superbets_order() -> None:
    # 10-14: Al Mesaimeer - Etihad AL Gharafa = Al Mesaimeer SC - Al-Gharafa II
    e = _ev(10, 1, 2)
    assert _pick([e, _ev(11, 1, 3, KICK + timedelta(days=4))]) == e
    # the anchor as Superbet's side_b must be away
    assert _pick([_ev(10, 2, 1)], side_a=False) is not None
    assert _pick([_ev(10, 2, 1)], side_a=True) is None  # reversed: the F25 gate


def test_refusals() -> None:
    assert _pick([_ev(10, 1, 2), _ev(11, 3, 1, KICK + timedelta(minutes=50))]) is None
    assert _pick([_ev(10, 1, 2, KICK + timedelta(minutes=61))]) is None
    # 10-07 Pacific - Forge: the postponed twin is no candidate
    played = _ev(10, 1, 2)
    assert _pick([played, _ev(11, 1, 2, status="postponed")]) == played
    assert _pick([_ev(10, 1, 2)], other=99) is None  # the opponent's own id
    assert _pick([_ev(10, 1, 2)], other=2) is not None
    assert _pick([_ev(10, 1, 2, gender="F")]) is None  # men's board
    assert (
        _pick([_ev(10, 1, 2, gender="F")], a="Barcelona (K)", b="Levante (K)")
        is not None
    )


def test_the_switch_is_the_operators_moment() -> None:
    assert epochs.FOOTBALL_DAY_ANCHOR_FROM_UTC == datetime(
        2026, 10, 14, 11, 30, tzinfo=UTC
    )
    assert epochs.football_day_anchor(
        "2026-10-14", datetime(2026, 10, 14, 11, 31, tzinfo=UTC)
    )
    assert not epochs.football_day_anchor(
        "2026-10-14", datetime(2026, 10, 14, 11, 29, tzinfo=UTC)
    )
    assert not epochs.football_day_anchor(
        "2026-10-13", datetime(2026, 10, 14, 12, tzinfo=UTC)
    )
