"""bet.sofa.line_evidence and its epoch (operator, 2026-10-07): no market is
refused by name; every key is read through its own settled Superbet lines."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import confidence, epochs, sport_confidence
from bet.sofa import line_evidence as le

REPO = Path(__file__).resolve().parents[2]


def _ev(printable: dict | None = None,
        buckets: dict | None = None) -> le.LineEvidence:
    entry: dict = {"n": 500, "games": 120, "buckets": buckets or {}}
    if printable is not None:
        entry["printable"] = printable
    return le.LineEvidence({"keys": {"tennis": {"games_won_for|OVER": entry}}})


def test_the_grid_is_the_curves_grid() -> None:
    assert le.EDGES == sport_confidence.EDGES
    assert le.PRINTABLE_FROM == confidence.COUPON_PROFILE.floor


def test_a_significant_overstatement_lowers_the_curve() -> None:
    ev = _ev({"n": 278, "games": 89,
              "realised_minus_confidence": [-0.1177, -0.1992, -0.0369]})
    read = ev.read("tennis", "games_won_for|OVER", 0.8, (0.80, "market:x", 900))
    assert read is not None
    assert read.value == 0.6823 and read.offset == -0.1177 and read.n == 900
    assert read.source.endswith("sb")


def test_an_offset_never_raises_and_a_measured_point_lowers() -> None:
    up = _ev({"n": 300, "games": 90,
              "realised_minus_confidence": [0.07, 0.01, 0.13]})
    assert up.offset("tennis", "games_won_for|OVER") == 0.0
    # 2026-10-07 13:00Z: the point offset, significant or not (out of sample
    # the significance test let tennis print 0.778 against 0.698 realised)
    noise = _ev({"n": 570, "games": 169,
                 "realised_minus_confidence": [-0.04, -0.12, 0.03]})
    read = noise.read("tennis", "games_won_for|OVER", 0.8,
                      (0.80, "market:x", 900))
    assert read is not None and read.value == 0.76 and read.offset == -0.04


def test_a_thin_key_reads_its_sports_pooled_offset() -> None:
    doc = {"keys": {"tennis": {"games_won_for|OVER": {
        "printable": {"n": 20, "games": 9,
                      "realised_minus_confidence": [-0.3, -0.5, -0.1]}}}},
        "sport_printable": {"tennis": {
            "n": 400, "games": 120,
            "realised_minus_confidence": [-0.058, -0.1, -0.02]}}}
    ev = le.LineEvidence(doc)
    assert ev.offset("tennis", "games_won_for|OVER") == -0.058
    assert ev.offset("tennis", "unknown|OVER") == -0.058
    assert ev.offset("hockey", "total|OVER") == 0.0
    thin_sport = le.LineEvidence({"sport_printable": {"cs2": {
        "n": 40, "games": 12, "realised_minus_confidence": [-0.2, -0.4, 0.0]}}})
    assert thin_sport.offset("cs2", "map_winner|TEAM") == 0.0
    # a sport pools every key: 20 games suffice (CS2, 10-07: 61 lines, 27 series)
    cs2 = le.LineEvidence({"sport_printable": {"cs2": {
        "n": 61, "games": 27, "realised_minus_confidence": [-0.204, -0.32, -0.07]}}})
    assert cs2.offset("cs2", "map_team_rounds|OVER") == -0.204


def test_a_handful_of_lines_is_not_an_offset() -> None:
    # 2026-10-07 first fit: one game's lost lines read a "significant" -0.7
    one_game = _ev({"n": 2, "games": 1,
                    "realised_minus_confidence": [-0.7, -0.7, -0.7]})
    assert one_game.offset("tennis", "games_won_for|OVER") == 0.0
    few_games = _ev({"n": 80, "games": 12,
                     "realised_minus_confidence": [-0.2, -0.3, -0.1]})
    assert few_games.offset("tennis", "games_won_for|OVER") == 0.0


def test_no_curve_reads_the_wilson_bound_of_its_own_lines() -> None:
    ev = _ev(buckets={"0.800-0.825": {"n": 120, "k": 108}})
    read = ev.read("tennis", "games_won_for|OVER", 0.81, None)
    assert read is not None
    assert read.value == round(le.wilson_lo(108, 120), 4)
    assert read.source == "sb:tennis:games_won_for|OVER"
    thin = _ev(buckets={"0.800-0.825": {"n": 49, "k": 49}})
    assert thin.read("tennis", "games_won_for|OVER", 0.81, None) is None
    assert ev.read("tennis", "games_won_for|OVER", 0.71, None) is None


def test_a_class_leg_keeps_its_own_evidence() -> None:
    assert le.evidence_key("goals_total|UNDER", "women") == "women:goals_total|UNDER"
    assert le.evidence_key("goals_total|UNDER", None) == "goals_total|UNDER"


def test_an_absent_file_reads_as_unfitted(tmp_path: Path) -> None:
    ev = le.LineEvidence.load(tmp_path / "none.json")
    assert not ev.fitted
    assert ev.read("tennis", "x|OVER", 0.8, (0.8, "s", 1)) == le.Read(
        0.8, "s", 1)
    assert ev.read("tennis", "x|OVER", 0.8, None) is None


def test_fit_buckets_and_the_printable_gap() -> None:
    rows = [{"sport": "hockey", "key": "total|OVER", "p": 0.81, "y": i % 2,
             "game": f"g{i}", "base": 0.80} for i in range(60)]
    rows += [{"sport": "hockey", "key": "total|OVER", "p": 0.55, "y": 1,
              "game": "g0", "base": None}]
    out = le.fit(rows)["keys"]
    entry = out["hockey"]["total|OVER"]
    assert entry["buckets"]["0.800-0.825"] == {"n": 60, "k": 30}
    assert entry["buckets"]["0.000-0.600"] == {"n": 1, "k": 1}
    assert entry["printable"]["n"] == 60 and entry["printable"]["games"] == 60
    point, lo, hi = entry["printable"]["realised_minus_confidence"]
    assert point == -0.3 and lo <= point <= hi < 0


def test_the_epoch_starts_at_a_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "LINE_EVIDENCE_FROM_UTC", None)
    assert not epochs.line_evidence("2026-10-09", datetime(2026, 10, 9, tzinfo=UTC))
    monkeypatch.setattr(epochs, "LINE_EVIDENCE_DATE", "2026-10-08")
    monkeypatch.setattr(epochs, "LINE_EVIDENCE_FROM_UTC",
                        datetime(2026, 10, 8, tzinfo=UTC))
    on = datetime(2026, 10, 8, 0, 0, tzinfo=UTC)
    assert epochs.line_evidence("2026-10-08", on)
    assert not epochs.line_evidence("2026-10-07", on)
    assert not epochs.line_evidence(
        "2026-10-08", datetime(2026, 10, 7, 23, 59, tzinfo=UTC))


def test_a_sport_with_curves_is_read_without_admission() -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "run_sport_confidence", REPO / "scripts/sofa/run_sport_confidence.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_sport_confidence"] = mod
    spec.loader.exec_module(mod)
    cal = sport_confidence.SportCalibration({"sports": {"basketball": {
        "admitted": [], "curves": {"handicap|TEAM": {
            "0.800-0.825": {"n": 300, "realised": 0.82, "realised_lo95": 0.80}}}}}})
    fixtures = {"sports_run": ["basketball"]}
    assert mod.sport_status("basketball", fixtures, cal) == mod.NOT_CALIBRATED
    assert mod.sport_status("basketball", fixtures, cal, le.LineEvidence({})) == mod.OK
    assert cal.lookup("basketball", "handicap", "T1", 0.81) is None
    hit = cal.lookup("basketball", "handicap", "T1", 0.81, require_admitted=False)
    assert hit is not None and hit.value == 0.80


def test_confidence_drops_the_by_name_gates_only_under_the_evidence() -> None:
    source = (REPO / "scripts/sofa/run_confidence.py").read_text()
    for gate in ("is_derived(row[\"market\"])",
                 "cal.player_prop_not_admitted(row[\"market\"])",
                 "cal.tennis_set_market_not_admitted(row[\"market\"])",
                 "cal.refused_by_operator("):
        assert f"if evidence is None and {gate}" in source, gate
    assert "refused[NO_LINE_EVIDENCE] += 1" in source


def _banded(cells: dict, star: dict | None = None) -> le.LineEvidence:
    bands = {"handicap|TEAM": {"1.60-2.20": cells}}
    if star is not None:
        bands[le.SPORT_SCOPE] = {"1.60-2.20": star}
    return le.LineEvidence({"keys": {}, "bands": {"basketball": bands}})


def test_the_price_bands() -> None:
    assert le.band_label(1.20) == "1.00-1.30"
    assert le.band_label(1.30) == "1.30-1.60"
    assert le.band_label(1.78) == "1.60-2.20"
    assert le.band_label(5.0) == "2.20-1000.00"


def test_a_band_measured_below_the_curve_caps_it_at_its_realised_rate() -> None:
    # 2026-10-07: basketball handicap p >= 0.925 at 1.60-2.20 - 21 lines,
    # 16 won - where the curve printed 0.934 (Bochnia -36.5 @ 1.78)
    ev = _banded({"0.925-0.950": {"n": 14, "k": 11}, "0.950-1.010": {"n": 7, "k": 5}})
    read = ev.read("basketball", "handicap|TEAM", 0.94, (0.9338, "c", 4000), 1.78)
    assert read is not None
    assert read.value == round(16 / 21, 4) == read.band_cap
    assert "cap:handicap|TEAM@1.60-2.20:>=0.925" in read.source


def test_a_band_within_its_interval_leaves_the_curve() -> None:
    # 63 lines at 0.81 against a 0.80 curve: no evidence of overstatement
    ev = _banded({"0.800-0.825": {"n": 63, "k": 51}})
    read = ev.read("basketball", "handicap|TEAM", 0.81, (0.80, "c", 4000), 1.70)
    assert read is not None and read.value == 0.80 and read.band_cap is None
    # another band, no cell: no cap
    assert ev.read("basketball", "handicap|TEAM", 0.81, (0.80, "c", 1), 1.20) \
        == le.Read(0.80, "c", 1)
    # no price, no cap
    assert ev.read("basketball", "handicap|TEAM", 0.81, (0.80, "c", 1)) \
        == le.Read(0.80, "c", 1)


def test_a_thin_key_falls_to_the_sports_lines_in_the_band() -> None:
    ev = _banded({"0.800-0.825": {"n": 5, "k": 2}},
                 star={"0.800-0.825": {"n": 85, "k": 49}})
    cell = ev.band_cell("basketball", "handicap|TEAM", 0.81, 1.9)
    assert cell == (85, 49, "*@1.60-2.20:0.800-0.825")
    read = ev.read("basketball", "handicap|TEAM", 0.81, (0.80, "c", 1), 1.9)
    assert read is not None and read.value == round(49 / 85, 4)
    assert ev.band_cell("basketball", "handicap|TEAM", 0.81, 1.9) is not None
    tiny = _banded({"0.800-0.825": {"n": 19, "k": 0}})
    assert tiny.band_cell("basketball", "handicap|TEAM", 0.81, 1.9) is None


def test_the_cap_only_lowers() -> None:
    ev = _banded({"0.800-0.825": {"n": 400, "k": 380}})
    read = ev.read("basketball", "handicap|TEAM", 0.81, (0.80, "c", 1), 1.9)
    assert read is not None and read.value == 0.80


def test_fit_writes_the_bands_of_priced_rows() -> None:
    rows = [{"sport": "hockey", "key": "total|OVER", "p": 0.81, "y": 1,
             "game": "g", "base": 0.8, "odds": 1.45},
            {"sport": "hockey", "key": "total|OVER", "p": 0.81, "y": 0,
             "game": "g", "base": 0.8, "odds": None}]
    out = le.fit(rows)
    assert out["keys"]["hockey"]["total|OVER"]["n"] == 2
    assert out["sport_printable"]["hockey"]["n"] == 2
    assert out["bands"]["hockey"]["total|OVER"] == {
        "1.30-1.60": {"0.800-0.825": {"n": 1, "k": 1}}}
    assert out["bands"]["hockey"][le.SPORT_SCOPE] == {
        "1.30-1.60": {"0.800-0.825": {"n": 1, "k": 1}}}


def test_a_staged_sport_calibration_is_read_from_its_day(tmp_path: Path) -> None:
    import json

    main = tmp_path / sport_confidence.CALIBRATION_FILE
    nxt = tmp_path / sport_confidence.NEXT_CALIBRATION_FILE
    main.write_text("{}")
    assert sport_confidence.calibration_path_for("2026-10-08", tmp_path) == main
    nxt.write_text(json.dumps({"effective_from": "2026-10-08"}))
    assert sport_confidence.calibration_path_for("2026-10-07", tmp_path) == main
    assert sport_confidence.calibration_path_for("2026-10-08", tmp_path) == nxt
    assert sport_confidence.calibration_path_for("2026-10-09", tmp_path) == nxt


def test_stage_and_audit_read_one_confidence() -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "run_sport_confidence", REPO / "scripts/sofa/run_sport_confidence.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_sport_confidence"] = mod
    spec.loader.exec_module(mod)
    cal = sport_confidence.SportCalibration({"sports": {"basketball": {
        "admitted": [], "curves": {"quarter_total|OVER": {
            "0.800-0.825": {"n": 300, "realised": 0.82, "realised_lo95": 0.80}}}}}})
    assert mod.read_confidence(cal, None, "basketball", "quarter_total", "OVER",
                               0.81, 1.5)[3] == mod.NOT_CALIBRATED
    ev = le.LineEvidence({"keys": {}, "bands": {"basketball": {
        "quarter_total|OVER": {"1.30-1.60": {"0.800-0.825": {"n": 60, "k": 36}}}}}})
    conf, offset, cap, why = mod.read_confidence(
        cal, ev, "basketball", "quarter_total", "OVER", 0.81, 1.5)
    assert why is None and offset == 0.0
    assert conf is not None and conf.value == cap == 0.6
    source = (REPO / "scripts/sofa/audit_variants.py").read_text()
    assert "rsc.read_confidence(" in source
    assert "scf.calibration_path_for(date)" in source


def test_the_operator_moved_the_epoch_into_2026_10_07() -> None:
    # "dzisiejszy kupon przebudowany z nowymi zasadami" - 10-07 10:55Z
    at = datetime(2026, 10, 7, 10, 55, tzinfo=UTC)
    assert epochs.line_evidence("2026-10-07", at)
    early = datetime(2026, 10, 7, 7, 31, tzinfo=UTC)
    assert not epochs.line_evidence("2026-10-07", early)
    assert not epochs.line_evidence("2026-10-06", at)


def test_without_a_band_cell_the_keys_own_lines_bound_it() -> None:
    # verifier 2026-10-07: Mannheim - Tychy handicap -4.5 T2 printed 0.9448
    # at p 0.951 - no band cell; the key's lines at p >= 0.85 won 35/51
    ev = le.LineEvidence({"keys": {"hockey": {"handicap|TEAM": {"buckets": {
        "0.850-0.875": {"n": 25, "k": 17}, "0.875-0.900": {"n": 16, "k": 13},
        "0.900-0.925": {"n": 8, "k": 5}, "0.925-0.950": {"n": 2, "k": 0}}}}},
        "bands": {"hockey": {}}})
    cell = ev.band_cell("hockey", "handicap|TEAM", 0.951, 1.38)
    # widened down from 0.95 until 20 lines: p >= 0.875 holds 26 (18 won)
    assert cell == (26, 18, "handicap|TEAM@all:>=0.875")
    read = ev.read("hockey", "handicap|TEAM", 0.951, (0.9448, "c", 1), 1.38)
    assert read is not None and read.value == round(18 / 26, 4)
    # never widened below the printable floor
    low = le.LineEvidence({"keys": {"hockey": {"x|OVER": {"buckets": {
        "0.600-0.700": {"n": 500, "k": 300}}}}}, "bands": {}})
    assert low.band_cell("hockey", "x|OVER", 0.95, 1.38) is None
