"""epochs.SCHEDULE_TERM past SHEET (plan steps 17 / 20): a SHEET row's
`schedule_term` (cut to status / t_home / t_away) and
`p_central_no_schedule_term` ride onto CONFIDENCE's legs and SETTLE's
07_settled.json rows (T-SCHEDULE-TERM-FORWARD reads them there), never into
sofa_settled_row (no column, no migration); a leg whose p the term moved
shows "kontekst terminarza w modelu" on the PDF, the HTML, the dossier and
the read set. Absent fields stay absent; nothing gates on them."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import schedule_term, schedule_term_view
from bet.sofa.dossier import leg_rows
from scripts.sofa.build_coupon_pdf import schedule_term_label

FEATURES = {"rest_bucket": "short", "indicators": ["own_rest_short"],
            "coverage": True}
TERM = {"status": "APPLIED", "t_home": -0.031234, "t_away": 0.012,
        "home": FEATURES, "away": FEATURES}
EXTRA = {"schedule_term": TERM, "p_central_no_schedule_term": 0.7012}


def test_applied_is_the_terms_own_status() -> None:
    assert schedule_term_view.APPLIED == schedule_term.APPLIED


def test_leg_fields_cut_the_features_and_keep_absent_absent() -> None:
    got = schedule_term_view.leg_fields(EXTRA)
    assert got == {"schedule_term": {"status": "APPLIED", "t_home": -0.031234,
                                     "t_away": 0.012},
                   "p_central_no_schedule_term": 0.7012}
    assert schedule_term_view.leg_fields({"p_central": 0.7}) == {}
    assert schedule_term_view.leg_fields(
        {"schedule_term": None, "p_central_no_schedule_term": None}) == {}
    # a floor key: the term rides, no shadow p (it kept the uncorrected p)
    floor = {"schedule_term": {**TERM, "status": "EXCLUDED_FLOOR"}}
    assert schedule_term_view.leg_fields(floor) == {
        "schedule_term": {"status": "EXCLUDED_FLOOR", "t_home": -0.031234,
                          "t_away": 0.012}}


@pytest.mark.parametrize("term", [
    None,
    {"status": "EXCLUDED_FLOOR", "t_home": -0.03, "t_away": 0.01},
    {"status": "NATIONAL", "t_home": 0.0, "t_away": 0.0},
    {"status": "NO_COVERAGE", "t_home": 0.0, "t_away": 0.0},
    {"status": "APPLIED", "t_home": 0.0, "t_away": 0.0},
])
def test_no_note_when_the_term_did_not_move_the_p(term: Any) -> None:
    leg = {"market": "result_1x2", "schedule_term": term}
    assert schedule_term_view.label(leg) == ""
    assert schedule_term_label(leg) == ""
    assert "schedule_term_note" not in leg_rows([leg])[0]


def test_the_note_on_pdf_html_dossier() -> None:
    leg = {"market": "result_1x2", **schedule_term_view.leg_fields(EXTRA)}
    text = "kontekst terminarza w modelu (t = -0.031 gosp. / +0.012 gości)"
    assert schedule_term_view.label(leg) == text
    assert text in schedule_term_label(leg)
    assert leg_rows([leg])[0]["schedule_term_note"] == text
    html = (Path(__file__).resolve().parents[2] / "src/bet/sofa/templates/"
            "coupon_view.html").read_text(encoding="utf-8")
    assert "r.schedule_term" in html


def test_the_html_row_carries_the_note() -> None:
    from bet.sofa import coupon_html as ch
    from tests.sofa.test_coupon_html import _doc

    doc = _doc()
    doc["singles"][0].update(schedule_term_view.leg_fields(EXTRA))
    rows = ch.build_view(doc, "2026-10-08", None)["rows"]
    assert rows[0]["schedule_term"] == (
        "kontekst terminarza w modelu (t = -0.031 gosp. / +0.012 gości)")
    assert all(r["schedule_term"] == "" for r in rows[1:])
    assert "kontekst terminarza w modelu" in ch.render_html(
        "2026-10-08", ch.build_view(doc, "2026-10-08", None))


# -- CONFIDENCE: the leg carries the fields, gates unchanged ----------------

def _confidence_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                    extra: dict[str, Any]) -> dict[str, Any]:
    from tests.sofa import test_stats_only_confidence as so

    tmp_path.mkdir(parents=True, exist_ok=True)
    p = 0.75
    odds = round(0.95 / so._conf(p), 2)
    row = so._row(1, p, odds, 0.60, **extra)
    runs = so._day(tmp_path, [row], {1: so.KO[1]}, {1: (odds, so._under(odds))})
    assert so._run(runs, monkeypatch) == 0
    return so._doc(runs)


def test_confidence_carries_the_term_onto_the_leg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    on = _confidence_doc(tmp_path / "on", monkeypatch, EXTRA)
    off = _confidence_doc(tmp_path / "off", monkeypatch, {})
    leg_on, leg_off = on["singles"][0], off["singles"][0]
    assert leg_on["schedule_term"] == {"status": "APPLIED", "t_home": -0.031234,
                                       "t_away": 0.012}
    assert leg_on["p_central_no_schedule_term"] == 0.7012
    assert "schedule_term" not in leg_off
    assert "p_central_no_schedule_term" not in leg_off
    # nothing else moves
    strip = ("schedule_term", "p_central_no_schedule_term")
    assert {k: v for k, v in leg_on.items() if k not in strip} == leg_off
    assert [s["sofascore_event_id"] for s in on["singles"]] == [1]


# -- SETTLE: 07_settled.json carries them, the DB row does not --------------

def test_settle_writes_the_term_to_07_settled_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.sofa import test_settle_resettle_merges as rs

    sheet = [rs._row(1) | EXTRA, rs._row(2)]
    run_dir = rs._day(tmp_path, monkeypatch, sheet)
    monkeypatch.setattr(rs.run_settle, "_event_payload", rs._payload())
    assert rs._run(monkeypatch) == 0
    rows, _ = rs._files(run_dir)
    by_ev = {r["sofascore_event_id"]: r for r in rows}
    assert by_ev[1]["schedule_term"] == {"status": "APPLIED", "t_home": -0.031234,
                                         "t_away": 0.012}
    assert by_ev[1]["p_central_no_schedule_term"] == 0.7012
    assert by_ev[1]["p_central"] == 0.55 and by_ev[1]["outcome"] == "WIN"
    assert "schedule_term" not in by_ev[2]
    assert "p_central_no_schedule_term" not in by_ev[2]
    with sqlite3.connect(tmp_path / "sofa.db") as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sofa_settled_row)")}
        n = conn.execute("SELECT COUNT(*) FROM sofa_settled_row").fetchone()[0]
    assert n == 2
    assert not {"schedule_term", "p_central_no_schedule_term"} & cols


def test_read_set_lists_the_term_and_the_note() -> None:
    from scripts.sofa import read_set

    assert "schedule_term" in read_set.FIELDS
    src = Path(read_set.__file__).read_text(encoding="utf-8")
    assert 'compact["schedule_term_note"] = note' in src
    assert json.dumps(schedule_term_view.leg_fields(EXTRA))  # serialisable


def test_a_side_t_that_rounds_to_zero_shows_no_sign() -> None:
    leg = {"schedule_term": {"status": "APPLIED", "t_home": 0.0251,
                             "t_away": -0.0002}}
    assert schedule_term_view.label(leg) == (
        "kontekst terminarza w modelu (t = +0.025 gosp. / 0.000 gości)")
