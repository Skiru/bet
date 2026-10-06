"""The four changes from the 2026-09-25 settlement review (2026-09-26).

1. CONFIDENCE reads a per-direction curve. OVER and UNDER of one rung are
   complements; the pooled market curve overstated football team OVER legs by
   3.0 pp on the live settled rows (1.9 pp per direction).
2. Singles of one match are shown as one match. Boyaca Chico - Pasto carried
   three printed singles on 2026-09-25 and nothing said so. Counted, not
   capped: a cap back-tested worse.
3./4. audit_settlement 7g measures MAX_OVERROUND and the market classes over
   every settled day - observation, never a gate.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import (
    Calibration,
    direction_key,
    fixture_leg_counts,
)
from scripts.sofa import audit_trend

# ---------------------------------------------------------------------------
# 1. the per-direction curve
# ---------------------------------------------------------------------------

MARKET_CURVE = {
    "0.700-0.750": {"n": 5000, "realised": 0.74, "realised_lo95": 0.7177},
    "0.750-0.800": {"n": 5000, "realised": 0.79, "realised_lo95": 0.7720},
}
OVER_CURVE = {
    "0.700-0.750": {"n": 2000, "realised": 0.70, "realised_lo95": 0.6800},
}


def _cal(**kw: Any) -> Calibration:
    return Calibration(pooled={}, by_market={"goals_for": MARKET_CURVE}, **kw)


def test_the_direction_key() -> None:
    assert direction_key("goals_for", "over") == "goals_for|OVER"


def test_a_direction_curve_is_read_first() -> None:
    cal = _cal(by_market_direction={"goals_for|OVER": OVER_CURVE})
    assert cal.realised("goals_for", 0.72, "football", "OVER") == (
        0.68, "market:goals_for|OVER", 2000)


def test_the_other_direction_without_its_own_curve_keeps_the_market_curve() -> None:
    cal = _cal(by_market_direction={"goals_for|OVER": OVER_CURVE})
    assert cal.realised("goals_for", 0.72, "football", "UNDER") == (
        0.7177, "market:goals_for", 5000)


def test_a_thin_direction_bucket_falls_back_to_the_market_curve() -> None:
    """Missing because the split is thin, not because it was measured to fail.

    The first version refused here, and back-tested it refused goals_2h_total
    and tiebreaks_total legs on every day 22-25.09 on no evidence.
    """
    cal = _cal(by_market_direction={"goals_for|OVER": OVER_CURVE})
    assert cal.realised("goals_for", 0.77, "football", "OVER") == (
        0.7720, "market:goals_for", 5000)


def test_a_file_without_direction_curves_reads_as_before() -> None:
    cal = _cal()
    assert cal.realised("goals_for", 0.72, "football", "OVER") == cal.realised(
        "goals_for", 0.72, "football")


def test_load_reads_the_direction_section(tmp_path: Path) -> None:
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({
        "pooled": {}, "by_market": {"goals_for": MARKET_CURVE},
        "by_market_direction": {"goals_for|OVER": OVER_CURVE},
    }))
    got = Calibration.load(path).realised("goals_for", 0.72, None, "OVER")
    assert got is not None and got[1] == "market:goals_for|OVER"


def test_the_fit_writes_a_curve_per_direction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa import fit_confidence

    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute(
        "create table sofa_settled_row (market text, line real, direction text,"
        " sample_size int, sample_mean real, sample_sd real, actual_value real,"
        " p_central real, sport text)"
    )
    # games_won_for is an empirical frequency: p is the stored p_central, so
    # the bucket is known exactly. OVER hits 1 in 2, UNDER 3 in 4.
    rows = (
        [("games_won_for", 9.5, "OVER", 10, 10.0, 2.0, 12.0, 0.72, "tennis")] * 250
        + [("games_won_for", 9.5, "OVER", 10, 10.0, 2.0, 7.0, 0.72, "tennis")] * 250
        + [("games_won_for", 9.5, "UNDER", 10, 9.0, 2.0, 7.0, 0.72, "tennis")] * 375
        + [("games_won_for", 9.5, "UNDER", 10, 9.0, 2.0, 12.0, 0.72, "tennis")] * 125
    )
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    out = tmp_path / "cal.json"
    monkeypatch.setattr(sys, "argv", ["fit", "--db-path", str(db), "--out", str(out)])
    assert fit_confidence.main() == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    bucket = "0.700-0.750"
    assert doc["by_market"]["games_won_for"][bucket]["realised"] == 0.625
    assert doc["by_market_direction"]["games_won_for|OVER"][bucket]["realised"] == 0.5
    assert doc["by_market_direction"]["games_won_for|UNDER"][bucket]["realised"] == 0.75


def test_the_stage_looks_up_the_legs_own_direction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: run_confidence must pass the direction, or the split is dead."""
    from scripts.sofa import run_confidence
    from tests.sofa import confidence_day as harness

    run = tmp_path / harness.DAY
    run.mkdir()
    p, odds, under = 0.72, 1.40, 2.80
    (run / "02_fixtures.json").write_text(json.dumps([harness._fixture(1)]))
    (run / "03_samples.json").write_text(json.dumps([harness._samples(1)]))
    (run / "04_offer.json").write_text(json.dumps([harness._offer(1, odds, under)]))
    (run / "05_sheet.json").write_text(
        json.dumps([harness._sheet_row(1, p, odds, p - 0.03)]))
    (run / "vetoes.json").write_text("[]")

    # A value no fitted curve would produce, so it can only come from here.
    marker = {"0.700-0.750": {"n": 4321, "realised": 0.8, "realised_lo95": 0.7777}}
    fake = Calibration(
        pooled={}, by_market={"goals_total": MARKET_CURVE},
        by_market_direction={"goals_total|OVER": marker},
    )
    monkeypatch.setattr(
        run_confidence.Calibration, "load", staticmethod(lambda *a: fake))
    monkeypatch.setattr(sys, "argv", [
        "run_confidence", "--date", harness.DAY, "--runs-dir", str(tmp_path)])
    run_confidence.main()
    doc = json.loads((run / "08_confidence.json").read_text())
    (leg,) = doc["legs"]
    assert leg["confidence"] == 0.7777
    assert leg["calibrated_on"] == "market:goals_total|OVER"


# ---------------------------------------------------------------------------
# 2. singles of one match
# ---------------------------------------------------------------------------


def test_singles_are_counted_per_fixture() -> None:
    singles = [{"sofascore_event_id": e} for e in (7, 7, 7, 8)]
    assert fixture_leg_counts(singles) == {7: 3, 8: 1}


# ---------------------------------------------------------------------------
# 3./4. the multi-day trend
# ---------------------------------------------------------------------------


def test_margin_bands_split_at_the_two_limits_in_use() -> None:
    assert audit_trend.margin_band(0.105) == audit_trend.MARGIN_BANDS[0][0]
    assert audit_trend.margin_band(0.1051) == audit_trend.MARGIN_BANDS[1][0]
    assert audit_trend.margin_band(0.15) == audit_trend.MARGIN_BANDS[1][0]
    assert audit_trend.margin_band(0.2) == audit_trend.MARGIN_BANDS[2][0]
    assert audit_trend.margin_band(None) == audit_trend.NO_MARGIN


def _tally(units: float, bets: int = 10) -> audit_trend.Tally:
    return audit_trend.Tally(bets=bets, won=5, units=units)


def test_a_class_is_named_only_when_every_day_agrees_and_there_is_evidence() -> None:
    lost = {"a": _tally(-1), "b": _tally(-2), "c": _tally(-0.5)}
    assert audit_trend.consistent_sign(lost) == "ujemne"
    mixed = {**lost, "c": _tally(+0.5)}
    assert audit_trend.consistent_sign(mixed) is None
    two_days = {"a": _tally(-1, 20), "b": _tally(-1, 20)}
    assert audit_trend.consistent_sign(two_days) is None  # too few days
    thin = {d: _tally(-1, 3) for d in "abc"}
    assert audit_trend.consistent_sign(thin) is None  # too few bets


def _leg(eid: int, overround: float, odds: float = 1.5) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "market": "goals_total", "subject": "",
            "line": 2.5, "direction": "UNDER", "sport": "football",
            "offered_odds": odds, "overround": overround, "confidence": 0.75}


def test_the_trend_reads_every_settled_day_up_to_the_report_date(
    tmp_path: Path,
) -> None:
    for day, outcome in (("2026-01-01", "WIN"), ("2026-01-02", "LOSS"),
                         ("2026-01-03", "WIN")):
        d = tmp_path / day
        d.mkdir()
        legs = [_leg(1, 0.09), _leg(2, 0.12)]
        (d / "08_confidence.json").write_text(json.dumps(
            {"legs": legs, "singles": legs[:1], "pdf_max_singles": 30}))
        (d / "07_settled.json").write_text(json.dumps([
            {"sofascore_event_id": e, "market": "goals_total", "subject": "",
             "line": 2.5, "direction": "UNDER", "outcome": outcome}
            for e in (1, 2)]))

    def load(day: str) -> list[dict[str, Any]]:
        path = tmp_path / day / "07_settled.json"
        return json.loads(path.read_text()) if path.exists() else []

    trend = audit_trend.build_trend(tmp_path, "2026-01-02", load)
    assert trend.days == ["2026-01-01", "2026-01-02"]  # the 3rd is after the date
    bands = trend.margin["standard"]
    low = audit_trend.MARGIN_BANDS[0][0]
    mid = audit_trend.MARGIN_BANDS[1][0]
    assert set(bands) == {low, mid}
    assert bands[low]["2026-01-01"].units == pytest.approx(0.5)
    assert bands[low]["2026-01-02"].units == pytest.approx(-1.0)
    # Only the PRINTED single is a class entry; the 12% leg never printed.
    assert trend.classes["standard"][("football", "goals_total", "UNDER")][
        "2026-01-01"].bets == 1
    text = "\n".join(audit_trend.render(trend, "## 7g"))
    assert "niczego nie zmienia" in text


def test_the_pdf_says_when_singles_share_a_match(tmp_path: Path) -> None:
    """Two printed singles on one fixture are marked; a lone one is not."""
    import pypdf

    from tests.sofa import confidence_day as harness

    run = tmp_path / harness.DAY
    run.mkdir()
    rows = [harness._sheet_row(1, 0.72, 1.40, 0.69),
            harness._sheet_row(2, 0.72, 1.40, 0.69)]
    (run / "02_fixtures.json").write_text(
        json.dumps([harness._fixture(1), harness._fixture(2)]))
    (run / "05_sheet.json").write_text(json.dumps(rows))
    (run / "03_samples.json").write_text(
        json.dumps([harness._samples(1), harness._samples(2)]))
    leg = {"sofascore_event_id": 1, "match": "Home 1 - Away 1",
           "competition": "Test League", "sport": "football",
           "kickoff_utc": harness.KICKOFF, "market": "goals_total", "subject": "",
           "line": 1.5, "direction": "OVER", "confidence": 0.75,
           "offered_odds": 1.40, "leg_ev": 0.05, "overround": 0.08,
           "sample_size": 20, "unfitted_constants": []}
    singles = [leg, {**leg, "line": 2.5},
               {**leg, "sofascore_event_id": 2, "match": "Home 2 - Away 2"}]
    (run / "08_confidence.json").write_text(json.dumps({
        "created_at_utc": "2026-01-01T00:00:00Z", "profile": "standard",
        "confidence_floor": 0.7, "min_ev": None, "max_overround": 0.105,
        "pdf_max_singles": 30, "vetoes_applied": 0, "vetoes_unmatched": 0,
        "unfitted_constants": [], "legs": singles, "singles": singles,
        "builders": []}))
    got = harness._run("build_coupon_pdf.py", tmp_path, "--runs-dir", str(tmp_path))
    assert got.returncode == 0, got.stderr
    text = " ".join(
        page.extract_text() for page in
        pypdf.PdfReader(run / f"KUPON_{harness.DAY}.pdf").pages)
    assert text.count("ten sam mecz: 2 nóg") == 2
    assert "1 mecz(e/ów) ma na tej liście" in text
