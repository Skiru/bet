"""Every switch of the 2026-10-08 change set off = the commit it started from,
byte for byte, through the entries SHEET uses (`process_fixture`,
`price_derived_rungs`, `load_side_correlations`).

The golden file was produced by running `off_scenarios.py` against an archive
of that commit (`git archive`), not against the working tree - see
golden/make_off_goldens.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from tests.sofa.off_scenarios import GOLDEN_DIR, all_scenarios

GOLDEN = GOLDEN_DIR / "off_identical_head.json"


def test_the_switches_are_where_the_install_put_them() -> None:
    start = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    for name in ("COUNT_DISPERSION", "TENNIS_SCOPED_TABLE", "PER_MARKET_K"):
        assert getattr(epochs, f"{name}_FROM_UTC") == start, name
    # CARDS_CORRELATION on from 10-21 with the derived joints' curves
    # (operator 2026-10-21), never on a day before it
    assert epochs.CARDS_CORRELATION_FROM_UTC == datetime(2026, 10, 21, tzinfo=UTC)
    assert epochs.CARDS_CORRELATION_DATE == "2026-10-21"


def test_off_is_identical_to_the_commit_the_change_set_started_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "Off" is the clock before the switches: the scenarios read
    # timeutil.now(), and from 2026-10-09 00:00Z the switches are on, so a
    # live clock made this test fail from that day on (2026-10-10).
    monkeypatch.setenv("SOFA_NOW", "2026-10-08T12:00:00Z")
    golden = json.loads(GOLDEN.read_text())
    got = all_scenarios()
    assert got.keys() == golden.keys()
    for key in golden:
        assert got[key] == golden[key], key
    # the golden is not vacuous
    assert golden["process_fixture_football"]["shots_total/stats_only=True"]
    assert golden["price_derived_rungs"]["centres"]["rows"]
    assert golden["load_side_correlations"]["file"]["cards_points"] is None
