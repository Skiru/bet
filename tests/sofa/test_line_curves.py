"""History curves per line (bet.sofa.line_curves, epochs.LINE_CURVES_FROM_UTC):
a men's football leg of a listed key reads its direction's curve at its own
line; everything else reads exactly as before."""

from __future__ import annotations

import ast
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import line_curves as lc
from bet.sofa.confidence import Calibration
from scripts.sofa import fit_line_evidence as fle
from scripts.sofa import install_line_curves as ilc
from scripts.sofa.fit_confidence import MIN_MARKET_BUCKET, line_curve_section

REPO = Path(__file__).resolve().parents[2]


def _bucket(lo95: float, n: int = 1000) -> dict[str, Any]:
    return {"n": n, "realised": lo95 + 0.01, "realised_lo95": lo95}


def _cal() -> Calibration:
    pooled = {"0.750-0.800": _bucket(0.77)}
    return Calibration(
        pooled={}, by_market={"goals_for": pooled},
        by_market_direction={"goals_for|UNDER": pooled},
        by_market_direction_line={"goals_for|UNDER": {
            "1.5": {"0.750-0.800": _bucket(0.72)}}},
        by_class={"women": {"by_market": {"goals_for": pooled},
                            "by_market_direction": {"goals_for|UNDER": pooled}}},
    )


def test_line_label_is_the_lines_shortest_form() -> None:
    assert lc.line_label(1.5) == "1.5"
    assert lc.line_label(10.0) == "10"
    assert lc.line_label(2) == "2"


def test_the_listed_keys_are_read_from_the_config_file(tmp_path: Path) -> None:
    path = tmp_path / lc.FILE
    assert lc.load_keys(path) == frozenset()  # absent: nothing per line
    path.write_text(json.dumps({"keys": ["goals_for|UNDER"]}))
    assert lc.load_keys(path) == frozenset({"goals_for|UNDER"})
    shipped = lc.load_keys()
    assert "goals_for|UNDER" in shipped and len(shipped) == 33


def test_a_leg_reads_its_line_curve_first_and_the_pooled_one_otherwise() -> None:
    cal = _cal()
    assert cal.realised("goals_for", 0.78, "football", "UNDER", line=1.5) == (
        0.72, "line:goals_for|UNDER@1.5", 1000)
    # another line, no line given, or a bucket the line lacks: as before
    assert cal.realised("goals_for", 0.78, "football", "UNDER", line=2.5) == (
        0.77, "market:goals_for|UNDER", 1000)
    assert cal.realised("goals_for", 0.78, "football", "UNDER") == (
        0.77, "market:goals_for|UNDER", 1000)
    assert cal.realised("goals_for", 0.70, "football", "UNDER", line=1.5) is None
    # a class leg never reads a line curve
    assert cal.realised("goals_for", 0.78, "football", "UNDER", "women", line=1.5) \
        == (0.77, "women:market:goals_for|UNDER", 1000)


def test_a_file_without_the_section_reads_as_before(tmp_path: Path) -> None:
    doc = {"pooled": {}, "by_market": {}, "by_market_direction": {
        "goals_for|UNDER": {"0.750-0.800": _bucket(0.77)}}}
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(doc))
    cal = Calibration.load(path)
    assert cal.by_market_direction_line == {}
    assert cal.realised("goals_for", 0.78, "football", "UNDER", line=1.5) == (
        0.77, "market:goals_for|UNDER", 1000)


def test_the_switch_is_judged_on_the_day_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "LINE_CURVES_FROM_UTC", at)
    assert epochs.line_curves("2026-10-19", at)
    assert not epochs.line_curves("2026-10-18", at)  # a day built before
    before = datetime(2026, 10, 18, 23, 59, tzinfo=UTC)
    assert not epochs.line_curves("2026-10-19", before)
    monkeypatch.setattr(epochs, "LINE_CURVES_FROM_UTC", None)
    assert not epochs.line_curves("2026-10-19", at)
    assert epochs.LINE_CURVES_FROM_UTC is None


def test_the_shipped_switch_is_the_next_days_midnight() -> None:
    assert epochs.LINE_CURVES_FROM_UTC == datetime(2026, 10, 19, 0, 0, tzinfo=UTC)


def test_the_section_keeps_only_buckets_with_enough_rows() -> None:
    counts = {"goals_for|UNDER": {"1.5": {3: [300, MIN_MARKET_BUCKET]},
                                  "2.5": {3: [10, MIN_MARKET_BUCKET - 1]}}}
    section = line_curve_section(counts)  # type: ignore[arg-type]
    assert list(section) == ["goals_for|UNDER"]
    assert list(section["goals_for|UNDER"]) == ["1.5"]
    entry = section["goals_for|UNDER"]["1.5"]["0.750-0.800"]
    assert entry["n"] == MIN_MARKET_BUCKET
    assert entry["realised"] == round(300 / MIN_MARKET_BUCKET, 4)
    assert 0 < entry["realised_lo95"] < entry["realised"]
    assert line_curve_section({}) == {}


def _fit_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("""create table sofa_settled_row (market text, line real,
        direction text, sample_size int, sample_mean real, sample_sd real,
        actual_value real, p_central real, sport text, sofascore_event_id int)""")
    con.execute("create table sofa_entity_events (kind text, events_json text)")
    rows = []
    # goals_for UNDER (a listed key): line 1.5 realises 0.70, line 4.5 0.95
    for i in range(1000):
        rows.append(("goals_for", 1.5, "UNDER", 10, 1.0, 1.0,
                     1.0 if i % 10 < 7 else 3.0, 0.78, "football", i))
        rows.append(("goals_for", 4.5, "UNDER", 10, 1.0, 1.0,
                     1.0 if i % 20 else 6.0, 0.78, "football", 5000 + i))
        # corners_total UNDER is not listed: never per line
        rows.append(("corners_total", 10.5, "UNDER", 10, 9.0, 2.0, 8.0, 0.78,
                     "football", 9000 + i))
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def _run_fit(db: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/sofa/fit_confidence.py", "--db-path", str(db),
         "--out", str(out), *extra],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"})


def test_fit_confidence_writes_the_listed_keys_per_line(tmp_path: Path) -> None:
    db, out = tmp_path / "sofa.db", tmp_path / "cal.json"
    _fit_db(db)
    proc = _run_fit(db, out)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text())
    section = doc[lc.SECTION]
    assert set(section) == {"goals_for|UNDER"}
    assert section["goals_for|UNDER"]["1.5"]["0.750-0.800"]["realised"] == 0.7
    assert section["goals_for|UNDER"]["4.5"]["0.750-0.800"]["realised"] == 0.95
    # the pooled direction curve is unchanged: both lines together
    assert doc["by_market_direction"]["goals_for|UNDER"]["0.750-0.800"]["realised"] \
        == 0.825
    assert doc[lc.FITTED_FROM]["keys"] == sorted(lc.load_keys())


def test_line_curves_only_keeps_every_other_curve_byte_for_byte(
    tmp_path: Path,
) -> None:
    db, out = tmp_path / "sofa.db", tmp_path / "cal.json"
    _fit_db(db)
    prior = {"by_market_direction": {"x|OVER": {"0.700-0.750": _bucket(0.7)}},
             "admitted_player_markets": ["player_shots_for"], lc.SECTION: {"old": {}}}
    out.write_text(json.dumps(prior))
    proc = _run_fit(db, out, "--line-curves-only")
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text())
    assert {k: v for k, v in doc.items() if k not in ilc.TAKEN} == {
        k: v for k, v in prior.items() if k not in ilc.TAKEN}
    assert set(doc[lc.SECTION]) == {"goals_for|UNDER"}
    refused = _run_fit(db, out, "--line-curves-only", "--classes-only")
    assert refused.returncode == 2


def test_run_confidence_passes_the_line_only_under_the_switch() -> None:
    source = (REPO / "scripts/sofa/run_confidence.py").read_text()
    assert "per_line = line_curves(args.date, now)" in source
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "realised"
             and any(k.arg == "line" for k in n.keywords)]
    assert len(calls) == 1
    line_kw = next(k for k in calls[0].keywords if k.arg == "line")
    # football only, None off the switch or without a line: lc.leg_line
    assert ast.unparse(line_kw.value) == "leg_line(row, per_line)"


def _evidence_day(run: Path) -> None:
    run.mkdir(parents=True)
    (run / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "superbet_event_ids": [],
         "competition_name": "Liga"}]))
    (run / "07_settled.json").write_text(json.dumps([
        {"sport": "football", "outcome": "WIN", "p_central": 0.78,
         "offered_odds": 1.3, "direction": "UNDER", "market": "goals_for",
         "line": 1.5, "sofascore_event_id": 1}]))


def test_the_evidence_base_reads_the_line_curve_when_the_day_does(
    tmp_path: Path,
) -> None:
    _evidence_day(tmp_path / "2026-10-18")
    cal = _cal()
    pooled = list(fle.sheet_rows(tmp_path, ["2026-10-18"], cal))
    per_line = list(fle.sheet_rows(tmp_path, ["2026-10-18"], cal, per_line=True))
    assert pooled[0]["base"] == 0.77 and per_line[0]["base"] == 0.72
    assert pooled[0]["key"] == per_line[0]["key"] == "goals_for|UNDER"


def test_install_takes_only_the_section_and_restores_on_a_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "sofa_confidence_calibration.json"
    installed = {"by_market_direction": {"a|OVER": {}}, "fitted_from": {"x": 1}}
    target.write_text(json.dumps(installed))
    staged = tmp_path / "staged.json"
    section = {"goals_for|UNDER": {"1.5": {"0.750-0.800": _bucket(0.72)}}}
    staged.write_text(json.dumps({**installed, lc.SECTION: section,
                                  lc.FITTED_FROM: {"db_path": "replay"}}))
    base = ["--staged", str(staged), "--target", str(target)]
    assert ilc.main([*base, "--dry-run"]) == 0
    assert json.loads(target.read_text()) == installed
    # a failing test run restores the file
    assert ilc.main([*base, "--confirm", "--backup-dir", str(tmp_path / "b1"),
                     "--tests", "false"]) == 2
    assert json.loads(target.read_text()) == installed
    assert ilc.main([*base, "--confirm", "--backup-dir", str(tmp_path / "b2"),
                     "--tests", "true"]) == 0
    assert json.loads(target.read_text())[lc.SECTION] == section
    assert json.loads((tmp_path / "b2" / target.name).read_text()) == installed
    # an existing backup, or a staged file fitted from another installed one
    assert ilc.main([*base, "--confirm", "--backup-dir", str(tmp_path / "b2"),
                     "--tests", "true"]) == 2
    staged.write_text(json.dumps({**installed, "fitted_from": {"x": 2},
                                  lc.SECTION: section}))
    assert ilc.main([*base, "--dry-run"]) == 2
    staged.write_text(json.dumps(installed))
    assert ilc.main([*base, "--dry-run"]) == 2  # no section


def test_a_one_sided_single_may_read_its_markets_line_curve() -> None:
    from bet.sofa.confidence import one_sided_single
    leg = {"one_sided_market": True, "overround": None, "calibration_n": 3012,
           "calibrated_on": "line:player_shots_for|OVER@1.5"}
    assert one_sided_single(leg)
    assert one_sided_single({**leg, "calibrated_on": "market:player_shots_for|OVER"})
    assert one_sided_single({**leg, "calibrated_on":
                             "line:player_shots_for|OVER@1.5-0.0100sb"})
    # still not a pool, a line-evidence bound or a thin curve
    for source in ("pooled:football", "sb:football:player_shots_for|OVER"):
        assert not one_sided_single({**leg, "calibrated_on": source})
    assert not one_sided_single({**leg, "calibration_n": 299})


def test_leg_line_and_the_days_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"sport": "football", "line": 1.5}
    assert lc.leg_line(row, True) == 1.5
    assert lc.leg_line(row, False) is None
    assert lc.leg_line({**row, "sport": "tennis"}, True) is None
    assert lc.leg_line({**row, "line": None}, True) is None  # never a crash
    assert lc.leg_line({"sport": "football"}, True) is None
    monkeypatch.setattr(epochs, "LINE_CURVES_FROM_UTC",
                        datetime(2026, 10, 19, 0, 0, tzinfo=UTC))
    assert lc.day_reads_per_line("2026-10-19")
    assert not lc.day_reads_per_line("2026-10-18")


def test_the_pdf_names_a_line_curve_without_its_prefix() -> None:
    from scripts.sofa.build_coupon_pdf import source_label
    assert source_label("line:goals_for|UNDER@1.5-0.0068sb") == \
        "goals_for|UNDER@1.5-0.0068sb"
    assert source_label("market:goals_for|UNDER") == "goals_for|UNDER"
    assert source_label("women:market:goals_for|UNDER") == "women:goals_for|UNDER"
    assert source_label("sb:football:x|OVER") == "sb:football:x|OVER"


def test_install_keeps_the_installed_files_indentation(tmp_path: Path) -> None:
    target = tmp_path / "sofa_confidence_calibration.json"
    installed = {"by_market_direction": {"a|OVER": {"0.700-0.750": _bucket(0.7)}}}
    target.write_text(json.dumps(installed, indent=2) + "\n")
    staged = tmp_path / "staged.json"
    staged.write_text(json.dumps({**installed, lc.SECTION: {"goals_for|UNDER": {
        "1.5": {"0.750-0.800": _bucket(0.72)}}}}, indent=1))
    assert ilc.main(["--staged", str(staged), "--target", str(target), "--confirm",
                     "--backup-dir", str(tmp_path / "b"), "--tests", "true"]) == 0
    text = target.read_text()
    assert text.splitlines()[1].startswith('  "')  # still two spaces
    assert ilc.indent_of(text) == 2 and ilc.indent_of('{\n "a": 1\n}') == 1


def test_line_curves_only_never_writes_the_installed_file(tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    _fit_db(db)
    proc = _run_fit(db, REPO / "config" / "sofa_confidence_calibration.json",
                    "--line-curves-only")
    assert proc.returncode == 2 and "staged copy" in proc.stderr
