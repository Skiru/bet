"""bet.sofa.family_record and scripts/sofa/build_family_record.py: the record
of every market family on the coupon's printed legs of the days before, the
HTML view's selection aid (never a gate)."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import coupon_html as ch
from bet.sofa import family_record as fr
from scripts.sofa import build_family_record as bfr

NOW = datetime.datetime(2026, 10, 18, 6, 0, tzinfo=datetime.UTC)


def _leg(eid: int, market: str = "corners_total", direction: str = "OVER",
         sport: str = "football") -> dict[str, Any]:
    return {"sofascore_event_id": eid, "group_key": f"sofa:{eid}",
            "sport": sport, "market": market, "direction": direction}


def test_window_is_the_days_before_never_the_day_never_before_the_rules() -> None:
    assert fr.window("2026-10-18") == [f"2026-10-{d:02d}" for d in range(9, 18)]
    w = fr.window("2026-11-01")
    assert len(w) == fr.WINDOW_DAYS and w[0] == "2026-10-18" and w[-1] == "2026-10-31"
    assert fr.window("2026-10-09") == []


def test_summarize_counts_win_and_loss_at_the_printed_price_only() -> None:
    rows: list[fr.Graded] = [
        (_leg(1), "WIN", 1.5), (_leg(1), "LOSS", 1.2), (_leg(2), "WIN", 1.25),
        (_leg(3), "REFUND", 1.4), (_leg(4), "PENDING", 1.4), (_leg(5), "WIN", None),
        (_leg(6, direction="UNDER"), "LOSS", 1.3),
        (_leg(7, sport="hockey", market="total"), "WIN", 1.8),
    ]
    out = fr.summarize(rows)
    over = out["football|corners_total|OVER"]
    assert over["legs"] == 3 and over["matches"] == 2 and over["won"] == 2
    assert over["units"] == pytest.approx(0.5 - 1 + 0.25)
    assert over["roi"] == pytest.approx(-0.25 / 3, abs=1e-4)
    assert over["implied"] == pytest.approx(
        (1 / 1.5 + 1 / 1.2 + 1 / 1.25) / 3, abs=1e-4)
    assert out["football|corners_total|UNDER"]["units"] == -1.0
    assert out["hockey|total|OVER"]["units"] == pytest.approx(0.8)


def test_on_plus_needs_the_legs_and_a_profit() -> None:
    assert fr.on_plus({"legs": 50, "units": 0.01})
    assert not fr.on_plus({"legs": 49, "units": 5.0})
    assert not fr.on_plus({"legs": 500, "units": 0.0})
    assert not fr.on_plus(None)
    assert fr.on_plus({"legs": 10, "units": 1.0}, min_legs=10)


def test_load_refuses_another_days_record_and_garbage(tmp_path: Path) -> None:
    doc = fr.build("2026-10-18", {"2026-10-17": [(_leg(1), "WIN", 1.5)]}, NOW)
    (tmp_path / fr.FILE).write_text(json.dumps(doc))
    assert fr.load(tmp_path, "2026-10-18") == doc
    assert fr.load(tmp_path, "2026-10-19") is None  # a copied run lends nothing
    for key, other in (("min_legs", 10), ("window_days", 7)):
        (tmp_path / fr.FILE).write_text(json.dumps({**doc, key: other}))
        assert fr.load(tmp_path, "2026-10-18") is None  # other parameters
    (tmp_path / fr.FILE).write_text("{not json")
    assert fr.load(tmp_path, "2026-10-18") is None
    assert fr.load(tmp_path / "missing", "2026-10-18") is None


def test_ensure_recomputes_only_when_the_ledger_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def graded(runs_dir: str, day: str, db: str) -> list[fr.Graded]:
        calls.append(day)
        return [(_leg(int(day[-2:])), "WIN", 1.3)] * 60

    monkeypatch.setattr(bfr, "graded_day", graded)
    runs = tmp_path / "runs"
    (runs / "2026-10-18").mkdir(parents=True)
    ledger = bfr.ledger_path(str(runs))
    ledger.parent.mkdir(parents=True)
    ledger.write_text("")
    os.utime(ledger, (1, 1))
    path = bfr.ensure(str(runs), "2026-10-18", "unused.db")
    doc = json.loads(path.read_text())
    assert doc["before"] == "2026-10-18" and doc["days"][0] == "2026-10-09"
    assert len(calls) == 9
    assert fr.on_plus(doc["families"]["football|corners_total|OVER"])
    bfr.ensure(str(runs), "2026-10-18", "unused.db")
    assert len(calls) == 9  # fresh: not recomputed
    os.utime(ledger, None)
    os.utime(path, (2, 2))  # the ledger was written after the record
    bfr.ensure(str(runs), "2026-10-18", "unused.db")
    assert len(calls) == 18


def test_ensure_quietly_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(runs_dir: str, day: str, db: str) -> list[fr.Graded]:
        raise RuntimeError("db locked")

    monkeypatch.setattr(bfr, "graded_day", boom)
    (tmp_path / "2026-10-18").mkdir()
    err = bfr.ensure_quietly(str(tmp_path), "2026-10-18", "x.db")
    assert err == "RuntimeError: db locked"


def _doc() -> dict[str, Any]:
    def leg(eid: int, market: str, conf: float, odds: float) -> dict[str, Any]:
        return {"sofascore_event_id": eid, "group_key": f"sofa:{eid}",
                "match": f"M{eid}", "competition": "Liga", "sport": "football",
                "kickoff_utc": "2026-10-18T12:00:00Z", "market": market,
                "subject": "", "line": 9.5, "direction": "OVER",
                "confidence": conf, "offered_odds": odds, "overround": 0.05,
                "position": eid}
    return {"created_at_utc": "2026-10-18T06:00:00Z", "positions": 3,
            "pdf_max_singles": None, "prints_builders": True,
            "singles": [leg(1, "corners_total", 0.80, 1.30),
                        leg(2, "goals_total", 0.80, 1.30),
                        leg(3, "corners_total", 0.80, 1.20)],
            "builders": [], "legs": []}


def _record() -> dict[str, Any]:
    plus = [(_leg(i), "WIN", 1.3) for i in range(60)]
    minus = [(_leg(i, market="goals_total"), "LOSS", 1.3) for i in range(60)]
    return fr.build("2026-10-18", {"2026-10-17": plus + minus}, NOW)


def test_the_view_tags_only_the_families_on_the_plus() -> None:
    view = ch.build_view(_doc(), "2026-10-18", None, _record())
    plus = [r["fam_plus"] for r in view["rows"]]
    assert plus == [True, False, True]
    assert view["rows"][0]["fam_note"] == "rodzina na plusie: ROI +30,0% na 60 nogach"
    assert view["rows"][1]["fam_note"] == ""  # nothing written for the others
    meta = view["meta"]["families"]
    assert meta["span"] == "2026-10-17..2026-10-17" and meta["on_plus"] == 1
    assert meta["measured"] == fr.MEASURED
    bare = ch.build_view(_doc(), "2026-10-18", None)
    assert bare["meta"]["families"] is None
    assert not any(r["fam_plus"] for r in bare["rows"])


def test_write_html_reads_the_days_record(tmp_path: Path) -> None:
    (tmp_path / fr.FILE).write_text(json.dumps(_record()))
    page = ch.write_html(tmp_path, _doc(), "2026-10-18").read_text()
    assert "rodzina na plusie: ROI +30,0% na 60 nogach" in page


def test_one_selection_rule_for_the_page_and_the_measurement() -> None:
    plus = frozenset({"football|corners_total|OVER"})
    leg = {**_leg(1), "confidence": 0.8, "offered_odds": 1.25}
    assert fr.selection_x(leg) == pytest.approx(1.0) and fr.selected(leg, plus)
    assert not fr.selected({**leg, "offered_odds": 1.24}, plus)  # x 0.992
    assert not fr.selected({**leg, "market": "goals_total"}, plus)
    assert not fr.selected({**leg, "offered_odds": None}, plus)
    # an artifact's own (rounded) x is the one the page shows: it decides
    assert fr.selection_x({**leg, "x": 0.9999}) == 0.9999
    assert not fr.selected({**leg, "x": 0.9999}, plus)
    assert fr.selected({**leg, "offered_odds": 1.24, "x": 1.0}, plus)
    view = ch.build_view({**_doc(), "singles": [{**_doc()["singles"][0], "x": 0.9999}]},
                         "2026-10-18", None, _record())
    assert view["rows"][0]["x"] == 0.9999


def _calls_only_under_out_none(source: str, name: str) -> bool:
    """Every call of `name` sits in the body of an `if args.out is None:`."""
    import ast

    tree = ast.parse(source)
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.If) and ast.unparse(node.test) == "args.out is None"):
            for inner in node.body:
                guarded |= {id(n) for n in ast.walk(inner)}
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == name]
    return bool(calls) and all(id(c) in guarded for c in calls)


def test_the_guard_check_sees_a_dedented_call() -> None:
    inside = "if args.out is None:\n    ensure_family_record(1)\n"
    outside = "if args.out is None:\n    pass\nensure_family_record(1)\n"
    assert _calls_only_under_out_none(inside, "ensure_family_record")
    assert not _calls_only_under_out_none(outside, "ensure_family_record")


def test_the_page_renders_scripts_call_ensure_before_the_html() -> None:
    root = Path(__file__).parents[2]
    pdf = (root / "scripts/sofa/build_coupon_pdf.py").read_text()
    assert pdf.index("ensure_family_record(args.runs_dir, args.date)") < pdf.index(
        "write_html(run, doc_json, args.date)")
    # inside the day's own render only: a --out render elsewhere writes nothing
    assert _calls_only_under_out_none(pdf, "ensure_family_record")
    html = (root / "scripts/sofa/build_coupon_html.py").read_text()
    assert html.index("ensure_family_record(") < html.index("write_html(run, doc")
