"""A one-sided market's leg may print as a single (epochs.ONE_SIDED_SINGLES_FROM_UTC,
from 2026-10-12 00:00Z, operator).

Superbet quotes a footballer's props on the OVER side only, so the ladder has
no overround and `single_is_fairly_priced` (overround <= MAX_OVERROUND)
refused every football player leg as a single, with no reason on the row:
the five player legs of 2026-10-09..10-10 that passed every confidence gate
never printed. "No margin can be measured" is not "the margin is dear"; the
switch admits such a leg when its confidence is its own market's history
curve with >= ONE_SIDED_MIN_CURVE_N rows. Before the switch, nothing changes.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.confidence import one_sided_single
from bet.sofa.coupon_html import build_view
from tests.sofa.confidence_day import (
    DAY,
    ODDS_A,
    P_A,
    UNDER_A,
    UNDER_B,
    _fixture,
    _offer,
    _run,
    _samples,
    _sheet_row,
)

ADMITTED: dict[str, Any] = {
    "one_sided_market": True,
    "overround": None,
    "calibrated_on": "market:player_shots_for|OVER",
    "calibration_n": 1240,
}


def test_an_admitted_leg() -> None:
    assert one_sided_single(ADMITTED)
    # The line-evidence suffix is still the market's own curve.
    tackles = "market:player_tackles_for|OVER-0.0028sb"
    assert one_sided_single({**ADMITTED, "calibrated_on": tackles})


@pytest.mark.parametrize(
    "change",
    [
        {"one_sided_market": None},            # a two-sided ladder that lost a side
        {"overround": 0.08},                   # a margin: the margin rule judges it
        {"calibrated_on": "market_thin:player_shots_for|OVER"},
        {"calibrated_on": "pooled:football"},
        {"calibrated_on": "sb:football:player_shots_for|OVER"},
        {"calibration_n": 299},
        {"calibration_n": None},
    ],
)
def test_everything_else_is_refused(change: dict[str, Any]) -> None:
    assert not one_sided_single({**ADMITTED, **change})


def test_the_switch_starts_the_next_day_and_never_mid_day() -> None:
    start = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
    assert epochs.ONE_SIDED_SINGLES_FROM_UTC == start
    assert epochs.one_sided_singles("2026-10-12", start)
    assert not epochs.one_sided_singles("2026-10-11", start)
    assert not epochs.one_sided_singles(
        "2026-10-12", datetime(2026, 10, 11, 23, 59, tzinfo=UTC))
    assert epochs.ONE_SIDED_MIN_CURVE_N == 300


def test_the_switch_judges_the_day_and_the_build_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "ONE_SIDED_SINGLES_FROM_UTC", at)
    assert epochs.one_sided_singles("2026-10-13", at)
    assert not epochs.one_sided_singles("2026-10-12", at)
    assert not epochs.one_sided_singles(
        "2026-10-13", datetime(2026, 10, 12, 23, 0, tzinfo=UTC))


# --- end to end through CONFIDENCE ------------------------------------------


def _day(tmp_path: Path) -> Path:
    """Leg 1 one-sided (no UNDER quoted), leg 2 an ordinary two-sided one."""
    run = tmp_path / DAY
    run.mkdir()
    one_sided = _offer(1, ODDS_A, UNDER_A)
    one_sided["rungs"][0]["under_odds"] = None
    (run / "02_fixtures.json").write_text(json.dumps([_fixture(1), _fixture(2)]))
    (run / "03_samples.json").write_text(json.dumps([_samples(1), _samples(2)]))
    (run / "04_offer.json").write_text(
        json.dumps([one_sided, _offer(2, 1.30, UNDER_B)]))
    (run / "05_sheet.json").write_text(json.dumps([
        _sheet_row(1, P_A, ODDS_A, P_A - 0.03),
        _sheet_row(2, P_A, 1.30, P_A - 0.03),
    ]))
    (run / "vetoes.json").write_text("[]")
    return tmp_path


def _confidence(
    runs: Path, monkeypatch: pytest.MonkeyPatch, switch: datetime | None
) -> dict[str, Any]:
    import scripts.sofa.run_confidence as rc

    monkeypatch.setattr(epochs, "ONE_SIDED_SINGLES_FROM_UTC", switch)
    monkeypatch.setattr(sys, "argv", ["run_confidence.py", "--date", DAY,
                                      "--runs-dir", str(runs)])
    assert rc.main() == 0
    return dict(json.loads((runs / DAY / "08_confidence.json").read_text()))


def _ids(legs: list[dict[str, Any]]) -> set[int]:
    return {int(leg["sofascore_event_id"]) for leg in legs}


def test_off_the_one_sided_leg_is_a_leg_but_not_a_single(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = _confidence(_day(tmp_path), monkeypatch, None)
    assert _ids(doc["legs"]) == {1, 2}
    assert _ids(doc["singles"]) == {2}
    leg = next(x for x in doc["legs"] if x["sofascore_event_id"] == 1)
    assert leg["one_sided_market"] is True and leg["overround"] is None
    two_sided = next(x for x in doc["legs"] if x["sofascore_event_id"] == 2)
    assert "one_sided_market" not in two_sided


def test_on_the_one_sided_leg_prints_and_the_page_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = _day(tmp_path)
    doc = _confidence(runs, monkeypatch, datetime(2025, 12, 1, tzinfo=UTC))
    assert _ids(doc["singles"]) == {1, 2}
    leg = next(x for x in doc["singles"] if x["sofascore_event_id"] == 1)
    assert one_sided_single(leg)
    md = (runs / DAY / "08_confidence.md").read_text()
    assert "| — |" in md  # its margin column, rendered instead of crashing

    # The PDF renders the leg (its margin cell used to format None and crash)
    # and the HTML view names why it has no margin.
    pdf = _run("build_coupon_pdf.py", runs, "--runs-dir", str(runs))
    assert pdf.returncode == 0, pdf.stderr
    assert (runs / DAY / f"KUPON_{DAY}.pdf").exists()
    view = build_view(doc, DAY)
    margins = {r["match"]: r["margin_txt"] for r in view["rows"]}
    assert margins["Home 1 - Away 1"] == "jednostr."
    assert margins["Home 2 - Away 2"].endswith("%")


def test_on_the_audit_accepts_the_admitted_leg_and_only_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.sofa.audit_variants as av

    runs = _day(tmp_path)
    switch = datetime(2025, 12, 1, tzinfo=UTC)
    doc = _confidence(runs, monkeypatch, switch)
    single = next(x for x in doc["singles"] if x["sofascore_event_id"] == 1)
    assert not [f for f in av.audit_confidence(str(runs), DAY) if "margin" in f]
    # The same leg without its curve size is not admitted, and C2 says so.
    single["calibration_n"] = 10
    (runs / DAY / "08_confidence.json").write_text(json.dumps(doc))
    findings = av.audit_confidence(str(runs), DAY)
    assert [f for f in findings if "not an admitted one-sided leg" in f]
    # With the switch off again the same artifact is a margin finding.
    monkeypatch.setattr(epochs, "ONE_SIDED_SINGLES_FROM_UTC", None)
    assert [f for f in av.audit_confidence(str(runs), DAY) if "margin None" in f]


@pytest.mark.parametrize(("switch", "printed", "removed"), [
    (None, [2], []),
    (datetime(2026, 10, 1, tzinfo=UTC), [2, 3], [1]),
])
def test_on_a_stats_only_day_a_read_removes_it_only_when_it_would_print(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    switch: datetime | None, printed: list[int], removed: list[int],
) -> None:
    """removed_by_reads is graded apart as "the legs a read took off the
    coupon": a one-sided leg is one of them only when the switch prints it.
    Leg 1 one-sided and watched, leg 2 two-sided, leg 3 one-sided."""
    from tests.sofa import test_stats_only_confidence as so

    p = 0.75
    odds = round(0.95 / so._conf(p), 2)
    ko = {1: "2026-10-07T18:00:00Z", 2: "2026-10-07T15:00:00Z",
          3: "2026-10-07T16:00:00Z"}
    runs = so._day(tmp_path, [so._row(e, p, odds, 0.70) for e in (1, 2, 3)], ko,
                   {1: (odds, None), 2: (odds, so._under(odds)), 3: (odds, None)})
    (runs / so.DAY / "reads.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "market": "goals_total", "subject": None,
        "line": None, "direction": None, "verdict": "WATCH",
        "author": "analyst", "reason": "test"}]))
    monkeypatch.setattr(epochs, "ONE_SIDED_SINGLES_FROM_UTC", switch)
    assert so._run(runs, monkeypatch) == 0
    doc = so._doc(runs)
    assert sorted(s["sofascore_event_id"] for s in doc["singles"]) == printed
    assert [r["sofascore_event_id"] for r in doc["removed_by_reads"]] == removed
