"""K7 (plan 2026-10-05): the ledger keeps the rule epochs apart."""

from __future__ import annotations

from typing import Any

from scripts.sofa import audit_ledger, record_results


def _row(
    date: str, variant: str, units: float, epoch: str | None = None
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": date, "variant": variant,
        "total": {"positions": 1, "settled": 1, "won": int(units > 0),
                  "lost": int(units < 0), "units": units},
    }
    if epoch:
        row["epoch"] = epoch
    return row


def test_the_three_epochs_are_never_added():
    rows = [
        _row("2026-10-04", "official", 0.3),
        _row("2026-10-05", "official:pre_stats_only", -1.0, "old"),
        _row("2026-10-05", "official", 0.2, "stats_only"),
        _row("2026-10-06", "official", -1.0, "stats_only"),
    ]
    text = "\n".join(audit_ledger.render(rows, None))
    assert "| official [do 10-04] | 1 | 1 | 1 | 1 | 0 | +0.30 |" in text
    assert "| official [stats_only] | 2 | 2 | 2 | 1 | 1 | -0.80 |" in text
    assert "| official:pre_stats_only [10-05 rano] | 1 |" in text
    assert audit_ledger.epoch_group({"date": "2026-10-05"}) == "10-05 rano"


def test_a_locked_leg_keeps_the_epoch_of_the_build_that_printed_it():
    assert record_results.position_epoch({"locked": True}, "stats_only") == "old"
    assert record_results.position_epoch(
        {"locked": True, "printed_under": {"epoch": "stats_only"}}, "stats_only"
    ) == "stats_only"
    assert record_results.position_epoch({}, "stats_only") == "stats_only"
