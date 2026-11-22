"""audit_settlement 7c: the day's singles result line (review 2026-11-22)."""

from __future__ import annotations


def test_suma_kuponu_is_written_without_measured_sports() -> None:
    """2026-11-22 review: the 7c „Suma kuponu” row came only with measured
    sport singles; the settler is told to quote it every day."""
    import inspect

    from scripts.sofa import audit_settlement
    assert audit_settlement.suma_kuponu(-398.07) == (
        "**Suma kuponu (pojedyncze, wszystkie sporty): -398.07 j.**")
    src = inspect.getsource(audit_settlement)
    assert src.count("suma_kuponu(") >= 3  # def + both branches
