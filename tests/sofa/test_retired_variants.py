"""K5 (plan 2026-10-05): the WARIANT and WARIANT WSZYSTKIE are not built for
a stats-only day; the separate sport coupons stop only when the sports print
on the one coupon (F7) - never earlier, or those days have no record."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest

from bet.sofa import epochs
from bet.sofa.confidence import PROFILES, profile_retired


def test_the_wariant_is_retired_only_for_stats_only_builds():
    at = epochs.STATS_ONLY_FROM_UTC
    wariant = PROFILES["wariant"]
    assert profile_retired(wariant, "2026-10-05", at)
    assert not profile_retired(wariant, "2026-10-05", at - timedelta(seconds=1))
    assert not profile_retired(wariant, "2026-10-04", at + timedelta(days=1))
    assert not profile_retired(PROFILES["standard"], "2026-10-06", at)


def test_wszystkie_is_refused_on_a_stats_only_day(tmp_path, monkeypatch, capsys):
    from scripts.sofa import run_multi_coupon

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_NOW", "2026-10-07T09:00:00Z")
    monkeypatch.setattr(sys, "argv", ["run_multi_coupon.py", "--date", "2026-10-07"])
    assert run_multi_coupon.main() == 2
    assert "retired" in capsys.readouterr().out


def test_the_sport_coupons_run_until_the_sports_are_on_the_coupon(monkeypatch):
    assert epochs.SPORTS_ON_COUPON_FROM_UTC is None or epochs.sports_on_coupon(
        "2026-10-05", epochs.SPORTS_ON_COUPON_FROM_UTC)
    monkeypatch.setattr(epochs, "SPORTS_ON_COUPON_FROM_UTC", None)
    assert not epochs.sports_on_coupon("2026-10-09", datetime(2026, 10, 9, tzinfo=UTC))
    cut = datetime(2026, 10, 6, 12, tzinfo=UTC)
    monkeypatch.setattr(epochs, "SPORTS_ON_COUPON_FROM_UTC", cut)
    assert epochs.sports_on_coupon("2026-10-06", cut)
    assert not epochs.sports_on_coupon("2026-10-06", cut - timedelta(minutes=1))


@pytest.mark.parametrize("script", ["run_multi_coupon.py", "run_sport_coupon.py"])
def test_the_retirement_is_read_from_the_epoch_module(script):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts" / "sofa" / script).read_text()
    assert "from bet.sofa.epochs import" in text
