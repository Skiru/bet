"""A settled day's results on its own coupon (bet.sofa.coupon_results).

After SETTLE, KUPON_<d>.pdf and .html colour every printed row - green won,
red lost, yellow not known / refund - show the leg's claim beside what the
market counted, and end with a percent summary. The grades are the ledger's
(record_results.graded_confidence), never a second grader; a leg the results
do not hold is never green. Offline and fast (the browser check is skipped
without Chrome).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import coupon_html as ch
from bet.sofa import coupon_results as cr
from bet.sofa import sport_day as sd
from bet.sofa.confidence import COUPON_PROFILE, STAKEABLE_RULE_X
from bet.sofa.locked_print import leg_key
from tests.sofa.test_coupon_html import CHROME

ROOT = Path(__file__).parents[2]


def _single(eid: int, market: str, line: float, direction: str, conf: float,
            **kw: Any) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "group_key": f"sofa:{eid}",
            "match": f"Home{eid} - Away{eid}", "competition": "Liga",
            "sport": kw.pop("sport", "football"),
            "kickoff_utc": "2026-10-16T15:00:00Z", "market": market,
            "subject": kw.pop("subject", ""), "line": line, "direction": direction,
            "confidence": conf, "offered_odds": kw.pop("odds", 1.25),
            "overround": 0.06, "sample_size": 10, "position": kw.pop("position", 1),
            "block": kw.pop("block", eid), **kw}


def _hockey(conf: float = 0.75, **kw: Any) -> dict[str, Any]:
    return {"sport": "hockey", "group_key": "sofa:900", "sofascore_event_id": 900,
            "superbet_event_id": "77", "market_id": 623, "family": "total",
            "market": "total", "period": 0, "subject": "", "line": 5.5,
            "side": "UNDER", "direction": "UNDER", "confidence": conf,
            "odds": 1.4, "offered_odds": 1.4, "kickoff_utc": "2026-10-16T18:00:00Z",
            "match": "Team A - Team B", "competition": "NHL", "position": 4,
            "block": 900, **kw}


def _graded() -> list[dict[str, Any]]:
    won = _single(1, "corners_total", 9.5, "OVER", 0.80)
    lost = _single(1, "goals_total", 2.5, "UNDER", 0.72, odds=1.6)
    pending = _single(2, "cards_points_total", 40.5, "UNDER", 0.70)
    dc = _single(3, "double_chance", 0.5, "OVER", 0.85, subject="1X")
    refund = _single(4, "shots_total", 20.5, "OVER", 0.71)
    hockey = {**_hockey(), "outcome": "WIN", "actual_value": 4.0,
              "score": "3:1 (1:0, 1:1, 1:0)"}
    builder = {"sofascore_event_id": 5, "builder_no": "B1", "match": "H5 - A5",
               "kickoff_utc": "2026-10-16T19:00:00Z", "combined_probability": 0.7,
               "n_legs": 2, "odds_if_product": 1.5,
               "legs": [{"market": "corners_total", "subject": "", "line": 8.5,
                         "direction": "OVER", "odds": 1.2, "confidence": 0.85},
                        {"market": "goals_total", "subject": "", "line": 1.5,
                         "direction": "OVER", "odds": 1.25, "confidence": 0.82}]}
    rows = {
        leg_key(won): {"outcome": "WIN", "actual_value": 11.0},
        leg_key(lost): {"outcome": "LOSS", "actual_value": 3.0},
        leg_key(dc): {"outcome": "WIN", "actual_value": 1.0},
        leg_key(refund): {"outcome": "REFUND", "actual_value": None},
        leg_key(builder["legs"][0], 5): {"outcome": "WIN", "actual_value": 10.0},
        leg_key(builder["legs"][1], 5): {"outcome": "LOSS", "actual_value": 1.0},
    }
    return [
        {"variant": "official", "rows": rows,
         "singles": [
             {"source": won, "odds": 1.25, "outcome": "WIN"},
             {"source": lost, "odds": 1.6, "outcome": "LOSS"},
             {"source": pending, "odds": 1.25, "outcome": "UNSETTLED"},
             {"source": dc, "odds": 1.25, "outcome": "WIN"},
             {"source": refund, "odds": 1.25, "outcome": "REFUND"},
             {"source": hockey, "odds": 1.4, "outcome": "WIN"}],
         "builders": [{"source": builder, "odds": 1.4, "outcome": "LOSS"}]},
        # not on the page: never in its results
        {"variant": "removed:reads", "rows": {},
         "singles": [{"source": _single(9, "corners_total", 9.5, "OVER", 0.9),
                      "odds": 1.3, "outcome": "WIN"}], "builders": []},
    ]


def _results() -> dict[str, Any]:
    return cr.compute("2026-10-16", _graded(), {3: "2:0 (do przerwy 1:0)",
                                                5: "1:0"}, "2026-10-17T06:00:00Z")


def _coupon() -> dict[str, Any]:
    g = _graded()[0]
    singles = [{k: v for k, v in s["source"].items()
                if k not in ("outcome", "actual_value", "score")}
               for s in g["singles"]]
    singles.append(_single(6, "fouls_total", 25.5, "UNDER", 0.74))  # not graded
    return {"created_at_utc": "2026-10-16T08:00:00Z", "profile": COUPON_PROFILE.name,
            "epoch": "stats_only", "confidence_floor": 0.7, "min_ev": 0.9,
            "max_overround": 0.15, "pdf_max_singles": None, "prints_builders": True,
            "positions": len(singles), "singles": singles,
            "builders": [{**g["builders"][0]["source"], "best_for_fixture": True,
                          "stakeable_rule": STAKEABLE_RULE_X,
                          "odds_after_haircut": 1.4}],
            "legs": [], "blocks": []}


# --- grading -------------------------------------------------------------------


def test_status_is_green_only_for_a_win() -> None:
    assert cr.status("WIN") == cr.WON
    assert cr.status("LOSS") == cr.LOST
    assert cr.status("REFUND") == cr.status("VOID") == cr.REFUND
    for raw in ("PENDING", "UNSETTLED", "MISMATCH", "UNGRADEABLE",
                "NOT_GRADED:GAVE_UP", "PENDING:LIVE", None):
        assert cr.status(raw) == cr.UNKNOWN


def test_compute_takes_the_ledger_grades_and_the_counted_values() -> None:
    res = _results()
    legs = res["legs"]
    assert len(legs) == 6  # removed:reads is not on the page
    by = {json.loads(k)[1]: v for k, v in legs.items()}
    assert by["corners_total"]["status"] == cr.WON
    assert by["corners_total"]["actual"] == 11.0
    assert by["goals_total"]["status"] == cr.LOST
    assert by["goals_total"]["actual"] == 3.0
    assert by["cards_points_total"]["status"] == cr.UNKNOWN
    assert by["cards_points_total"]["actual"] is None
    assert by["shots_total"]["status"] == cr.REFUND
    assert by["double_chance"]["score"] == "2:0 (do przerwy 1:0)"
    assert by["total"]["actual"] == 4.0 and by["total"]["score"].startswith("3:1")
    (b,) = res["builders"].values()
    assert b["status"] == cr.LOST and b["score"] == "1:0"
    assert [x["status"] for x in b["legs"]] == [cr.WON, cr.LOST]
    assert [x["actual"] for x in b["legs"]] == [10.0, 1.0]


def test_a_leg_the_results_do_not_hold_is_never_green() -> None:
    res = _results()
    missing = cr.of_leg(res, _single(6, "fouls_total", 25.5, "UNDER", 0.74))
    assert missing["status"] == cr.UNKNOWN
    assert cr.of_leg(None, _single(1, "corners_total", 9.5, "OVER", 0.8)) == {}
    found = cr.of_leg(res, _single(1, "corners_total", 9.5, "OVER", 0.8))
    assert found["status"] == cr.WON


def test_the_page_text_of_claim_and_count() -> None:
    res = _results()
    corners = _single(1, "corners_total", 9.5, "OVER", 0.8)
    assert cr.claim_text(corners) == "pow. 9.5"
    named = {**corners, "superbet_selection": "powyżej 9.5"}
    assert cr.claim_text(named) == "powyżej 9.5"
    assert cr.actual_text(corners, cr.of_leg(res, corners)) == "11"
    # a yes / no market shows the match score, not "1"
    dc = _single(3, "double_chance", 0.5, "OVER", 0.85, subject="1X")
    assert cr.actual_text(dc, cr.of_leg(res, dc)) == "wynik 2:0 (do przerwy 1:0)"
    # a measured sport's handicap is team1 minus team2, and says so
    hcp = {**_hockey(), "family": "handicap", "market": "handicap"}
    assert cr.actual_text(hcp, {"actual": -2.0, "status": cr.LOST}).startswith(
        "różnica -2")
    pending = _single(2, "cards_points_total", 40.5, "UNDER", 0.70)
    assert cr.actual_text(pending, cr.of_leg(res, pending)) == "—"
    assert cr.outcome_text(cr.of_leg(res, pending)) == "nie wiadomo (nie rozliczono)"
    assert cr.outcome_text({"status": cr.UNKNOWN, "outcome": "NOT_GRADED:GAVE_UP"}) \
        == "nie wiadomo (nie rozliczono: gave_up)"
    assert cr.outcome_text({"status": cr.WON, "outcome": "WIN"}) == "weszło"


def test_summary_in_percent_per_sport_and_in_all() -> None:
    res = _results()
    coupon = _coupon()
    pairs = [(leg, cr.of_leg(res, leg)) for leg in coupon["singles"]]
    s = cr.summarize(pairs)
    a = s["all"]
    assert a["legs"] == 7
    assert (a[cr.WON], a[cr.LOST], a[cr.REFUND], a[cr.UNKNOWN]) == (3, 1, 1, 2)
    assert a["share"][cr.WON] == pytest.approx(3 / 7)
    assert a["hit_rate"] == pytest.approx(3 / 4)
    # predicted: the mean confidence of the decided legs
    assert a["mean_confidence"] == pytest.approx((0.80 + 0.72 + 0.85 + 0.75) / 4)
    # flat units at the printed price: +0.25 +0.25 +0.40 -1
    assert a["units"] == pytest.approx(-0.10)
    assert set(s["sports"]) == {"football", "hockey"}
    assert s["sports"]["hockey"]["legs"] == 1
    lines = cr.summary_lines(s)
    assert lines[-1]["name"] == "cały kupon"
    assert lines[-1]["won"] == "3 (42.9%)" and lines[-1]["hit"] == "75.0%"


# --- the measured sports' grader carries the counted value ---------------------


def test_sport_grade_legs_carries_the_value_and_the_score() -> None:
    leg = {"superbet_event_id": "9", "market_id": 230060, "family": "points_total",
           "period": 0, "subject": "", "line": 130.5, "side": "OVER", "odds": 1.8,
           "kickoff_utc": "2026-10-16T18:00:00Z"}
    ev = {"state": "SETTLED", "t1_periods": [25, 25, 25], "t2_periods": [20, 18, 22],
          "t1_full": 3, "t2_full": 0, "winner": "T1", "overtime": False}
    (g,) = sd.grade_legs({"sport": "volleyball", "date": "2026-10-16", "legs": [leg]},
                         {"2026-10-16": {"events": {"9": ev}}})
    assert g["outcome"] == "WIN"
    assert g["actual_value"] == 135.0
    assert g["score"] == "3:0 (25:20, 25:18, 25:22)"
    # an outcome that is not a win or a loss carries no value
    (p,) = sd.grade_legs({"sport": "volleyball", "date": "2026-10-16", "legs": [leg]},
                         {"2026-10-16": {"events": {}}})
    assert p["outcome"] == "PENDING"
    assert p["actual_value"] is None and p["score"] is None


def test_cs2_score_is_maps_won_then_rounds() -> None:
    assert sd.event_score("cs2", {"state": "SETTLED", "maps": [[8, 13], [13, 11]]}) \
        == "1:1 (8:13, 13:11)"
    assert sd.event_score("hockey", {"state": "PENDING"}) is None


# --- the HTML page -------------------------------------------------------------


def test_the_html_rows_carry_their_results_and_the_summary() -> None:
    view = ch.build_view(_coupon(), "2026-10-16", None, results=_results())
    statuses = [r["res"]["status"] for r in view["rows"]]
    assert sorted(statuses) == sorted(
        [cr.WON, cr.LOST, cr.UNKNOWN, cr.WON, cr.REFUND, cr.WON, cr.UNKNOWN])
    corners = next(r for r in view["rows"]
                   if r["market"].startswith("corners_total"))
    assert corners["res"]["actual"] == "11" and corners["res"]["word"] == "weszło"
    meta = view["meta"]["results"]
    assert meta["summary"][-1]["name"] == "cały kupon"
    assert meta["builders"][cr.LOST] == 1
    (b,) = view["builders"]
    assert b["res"]["status"] == cr.LOST
    assert [x["res"]["status"] for x in b["legs"]] == [cr.WON, cr.LOST]
    # before the day is settled the page has no results
    plain = ch.build_view(_coupon(), "2026-10-16", None)
    assert all(r["res"] is None for r in plain["rows"])
    assert plain["meta"]["results"] is None


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_the_results_page_works_in_a_browser(tmp_path: Path) -> None:
    assert CHROME
    view = ch.build_view(_coupon(), "2026-10-16", None, results=_results())
    page = ch.render_html("2026-10-16", view)
    probe = """
const set=(id,v)=>{const e=document.getElementById(id);e.value=v;
 e.dispatchEvent(new Event("input"))};
const rows=()=>[...document.querySelectorAll("#body tr[data-id]")];
const out={};
out.classes=rows().map(tr=>tr.className.replace("lk","").trim()).sort();
out.summary=document.getElementById("summary").textContent.includes("cały kupon");
set("res","won");out.won=rows().length;
set("res","unknown");out.unknown=rows().length;
const sm=()=>document.getElementById("summary").textContent;
out.live=sm().includes("W bieżącym filtrze (3 nóg)");
document.getElementById("reset").click();out.reset=rows().length;
const pre=document.createElement("pre");pre.id="probe";
pre.textContent=JSON.stringify(out);document.body.appendChild(pre);
"""
    html = tmp_path / "probe.html"
    html.write_text(page.replace("</body>", f"<script>{probe}</script></body>"),
                    encoding="utf-8")
    dom = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=10000",
         "--dump-dom", html.as_uri()],
        capture_output=True, text=True, timeout=60, check=True).stdout
    m = re.search(r'<pre id="probe">(.*?)</pre>', dom, re.S)
    assert m, "the page's script did not run"
    out = json.loads(m.group(1))
    assert out["classes"] == sorted(
        ["won", "lost", "unknown", "won", "refund", "won", "unknown"])
    assert out["summary"] and out["live"]
    assert out["won"] == 3 and out["unknown"] == 3 and out["reset"] == 7


# --- the PDF -------------------------------------------------------------------


def _pdf_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_coupon_pdf", ROOT / "scripts" / "sofa" / "build_coupon_pdf.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _day(tmp_path: Path, results: bool = True) -> Path:
    run = tmp_path / "2026-10-16"
    run.mkdir()
    for name in ("02_fixtures.json", "03_samples.json", "05_sheet.json"):
        (run / name).write_text("[]", encoding="utf-8")
    (run / "11_coupon.json").write_text(json.dumps(_coupon()), encoding="utf-8")
    if results:
        (run / cr.RESULTS_FILE).write_text(json.dumps(_results()), encoding="utf-8")
    return run


def test_the_pdf_with_results_marks_rows_and_records_no_print(
    tmp_path: Path, monkeypatch: Any
) -> None:
    pypdf = pytest.importorskip("pypdf")
    run = _day(tmp_path)
    pdf = _pdf_module()
    monkeypatch.setattr(sys, "argv", ["build_coupon_pdf.py", "--date", "2026-10-16",
                                      "--runs-dir", str(tmp_path), "--with-results"])
    # as printed: the plain render first (it writes the print record)
    monkeypatch.setattr(sys, "argv", ["build_coupon_pdf.py", "--date", "2026-10-16",
                                      "--runs-dir", str(tmp_path)])
    assert pdf.main() == 0
    plain = " ".join(" ".join(p.extract_text() for p in pypdf.PdfReader(
        run / "KUPON_2026-10-16.pdf").pages).split())
    # results on disk never reach a normal render
    assert "Podsumowanie wyników" not in plain and "weszło" not in plain
    assert '"computed_utc"' not in (run / "KUPON_2026-10-16.html").read_text()
    printed = sorted((run / "printed").iterdir())
    os.utime(run / "KUPON_2026-10-16.pdf", (1_000_000, 1_000_000))
    os.utime(run / "KUPON_2026-10-16.html", (1_000_000, 1_000_000))
    original = (run / "KUPON_2026-10-16.pdf").read_bytes()
    monkeypatch.setattr(sys, "argv", ["build_coupon_pdf.py", "--date", "2026-10-16",
                                      "--runs-dir", str(tmp_path), "--with-results"])
    assert pdf.main() == 0
    # the print kept beside it, the files' time kept, no new print record
    assert (run / "KUPON_2026-10-16.przed_wynikami.pdf").read_bytes() == original
    assert (run / "KUPON_2026-10-16.przed_wynikami.html").exists()
    assert (run / "KUPON_2026-10-16.pdf").stat().st_mtime == 1_000_000
    assert (run / "KUPON_2026-10-16.html").stat().st_mtime == 1_000_000
    assert sorted((run / "printed").iterdir()) == printed
    text = "\n".join(p.extract_text() for p in
                     pypdf.PdfReader(run / "KUPON_2026-10-16.pdf").pages)
    flat = " ".join(text.split())
    assert "Podsumowanie wyników" in flat
    assert "weszło 3 (42.9%)" in flat
    assert "nie weszło" in flat and "było: 11" in flat
    assert "Builder: nie weszło" in flat
    # the HTML beside it carries the same results
    page = (run / "KUPON_2026-10-16.html").read_text(encoding="utf-8")
    assert '"cały kupon"' in page


def test_with_results_refuses_a_day_not_over(tmp_path: Path, monkeypatch: Any) -> None:
    from bet.sofa import timeutil

    run = _day(tmp_path)
    pdf = _pdf_module()
    monkeypatch.setattr(timeutil, "now", lambda: __import__("datetime").datetime(
        2026, 10, 16, 12, 0, tzinfo=__import__("datetime").UTC))
    monkeypatch.setattr(sys, "argv", ["build_coupon_pdf.py", "--date", "2026-10-16",
                                      "--runs-dir", str(tmp_path), "--with-results"])
    assert pdf.main() == 2
    assert not (run / "KUPON_2026-10-16.pdf").exists()


def test_with_results_refuses_a_day_not_marked(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _day(tmp_path, results=False)
    pdf = _pdf_module()
    monkeypatch.setattr(sys, "argv", ["build_coupon_pdf.py", "--date", "2026-10-16",
                                      "--runs-dir", str(tmp_path), "--with-results"])
    assert pdf.main() == 2


def test_result_rows_are_painted_in_their_colour() -> None:
    pdf = _pdf_module()
    from reportlab.platypus import Table

    t = pdf.paint_results(Table([["a"], ["b"], ["c"]]), [(1, cr.WON), (2, cr.LOST)])
    cmds = [c for c in t._bkgrndcmds if c[0] == "BACKGROUND"]
    hexes = [(c[1], c[3].hexval()) for c in cmds]
    assert hexes == [((0, 1), "0x" + cr.COLOURS[cr.WON][1:]),
                     ((0, 2), "0x" + cr.COLOURS[cr.LOST][1:])]


# --- marking a day -------------------------------------------------------------


def test_mark_writes_the_results_and_renders_only_on_a_change(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from scripts.sofa import mark_coupon_results as mcr

    run = _day(tmp_path, results=False)
    (run / "KUPON_2026-10-16.pdf").write_text("printed")
    monkeypatch.setattr(mcr, "graded_confidence", lambda *a: _graded())
    monkeypatch.setattr(cr, "match_scores", lambda *a: {3: "2:0"})
    calls: list[str] = []

    def fake_render(runs_dir: str, date: str) -> tuple[bool, str]:
        calls.append(date)
        (run / f"KUPON_{date}.pdf").write_text("x")
        return True, "ok"

    monkeypatch.setattr(mcr, "render", fake_render)
    verdict, _ = mcr.mark(str(tmp_path), "2026-10-16", str(tmp_path / "db"))
    assert verdict == "MARKED" and calls == ["2026-10-16"]
    doc = cr.load(run)
    assert doc is not None and len(doc["legs"]) == 6
    # the same grades again: nothing re-rendered
    verdict, _ = mcr.mark(str(tmp_path), "2026-10-16", str(tmp_path / "db"))
    assert verdict == "UNCHANGED" and calls == ["2026-10-16"]
    assert mcr.mark(str(tmp_path), "2026-10-17", "db")[0] == "NOT_MARKED: NO_PDF"
    # a file changed since the last results render (a plain rebuild): drawn again
    (run / "KUPON_2026-10-16.pdf").write_text("plain rebuild")
    verdict, _ = mcr.mark(str(tmp_path), "2026-10-16", str(tmp_path / "db"))
    assert verdict == "MARKED" and len(calls) == 2
    # a failed render is retried on the next run (no stamp written)
    monkeypatch.setattr(mcr, "render", lambda *a: (False, "boom"))
    (run / "KUPON_2026-10-16.pdf").write_text("plain again")
    assert mcr.mark(str(tmp_path), "2026-10-16", "db")[0] == "RENDER_FAILED: boom"
    monkeypatch.setattr(mcr, "render", fake_render)
    assert mcr.mark(str(tmp_path), "2026-10-16", "db")[0] == "MARKED"


def test_only_finished_days_from_the_first_marked_day() -> None:
    from datetime import UTC, datetime

    now = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)
    assert cr.markable("2026-10-17", now) is None
    assert cr.markable("2026-10-13", now) is None
    assert cr.markable("2026-10-18", now) == "DAY_NOT_OVER"
    assert cr.markable("2026-10-19", now) == "DAY_NOT_OVER"
    # 10-08 is never re-PDF'd; the days before ran under other rules
    assert cr.markable("2026-10-08", now).startswith("BEFORE_RESULTS_FROM")
    assert cr.markable("2026-10-12", now).startswith("BEFORE_RESULTS_FROM")


def test_mark_never_touches_a_day_it_may_not_mark(tmp_path: Path) -> None:
    from scripts.sofa import mark_coupon_results as mcr

    run = tmp_path / "2026-10-08"
    run.mkdir()
    (run / "KUPON_2026-10-08.pdf").write_text("as printed")
    verdict, _ = mcr.mark(str(tmp_path), "2026-10-08", "db")
    assert verdict.startswith("NOT_MARKED: BEFORE_RESULTS_FROM")
    assert (run / "KUPON_2026-10-08.pdf").read_text() == "as printed"
    assert sorted(p.name for p in run.iterdir()) == ["KUPON_2026-10-08.pdf"]


def test_record_results_marks_every_recorded_day_and_survives_a_failure(
    monkeypatch: Any, capsys: Any
) -> None:
    from scripts.sofa import mark_coupon_results as mcr
    from scripts.sofa import record_results as rr

    seen: list[str] = []

    def fake_mark(runs_dir: str, date: str, db: str) -> tuple[str, None]:
        seen.append(date)
        if date == "2026-10-16":
            raise RuntimeError("boom")
        return "MARKED", None

    monkeypatch.setattr(mcr, "mark", fake_mark)
    rr.mark_days("runs", ["2026-10-15", "2026-10-16"], "db")
    assert seen == ["2026-10-15", "2026-10-16"]
    captured = capsys.readouterr()
    assert "KUPON_2026-10-15: MARKED" in captured.out
    assert "FAILED: RuntimeError: boom" in captured.err


def test_the_score_shown_is_the_ninety_minutes() -> None:
    """10-15, Preston Lions - Wollongong Wolves: 0:0 after 90 minutes, lost
    on penalties; the double chance 12 lost and must not read "5:6"."""
    event = {"homeScore": {"current": 5, "normaltime": 0, "period1": 0,
                           "penalties": 5},
             "awayScore": {"current": 6, "normaltime": 0, "period1": 0,
                           "penalties": 6}}
    assert cr._score_of_detail(event) == (
        "0:0 (do przerwy 0:0) po 90 min; karne 5:6")
    aet = {"homeScore": {"current": 2, "display": 2, "normaltime": 1, "period1": 0,
                         "extra1": 1},
           "awayScore": {"current": 1, "display": 1, "normaltime": 1, "period1": 1}}
    assert cr._score_of_detail(aet) == (
        "1:1 (do przerwy 0:1) po 90 min; po dogrywce 2:1")
    plain = {"homeScore": {"current": 4, "normaltime": 4, "period1": 2},
             "awayScore": {"current": 2, "normaltime": 2, "period1": 2}}
    assert cr._score_of_detail(plain) == "4:2 (do przerwy 2:2)"
    # `current` holding only the shootout (Club Leon U21 - America U21,
    # 10-17): the 90 minutes from normaltime, nothing invented
    leon = {"status": {"code": 120},
            "homeScore": {"current": 4, "display": 1, "normaltime": 1},
            "awayScore": {"current": 3, "display": 1, "normaltime": 1}}
    assert cr._score_of_detail(leon) == "1:1"
    # a normal end with a placeholder normaltime keeps the match score
    # (16587598: normaltime 0, display 2)
    odd = {"status": {"code": 100},
           "homeScore": {"current": 2, "display": 2, "normaltime": 0},
           "awayScore": {"current": 0, "display": 0, "normaltime": 0}}
    assert cr._score_of_detail(odd) == "2:0"


def test_no_other_games_score_and_no_placeholder_rounds() -> None:
    hockey = {**_hockey(), "outcome": "NOT_GRADED:ID_CHANGED", "actual_value": None,
              "score": "7:1 (3:1, 2:0, 2:0)"}
    res = cr.compute("2026-10-16", [{"variant": "official", "rows": {},
                                     "singles": [{"source": hockey, "odds": 1.4,
                                                  "outcome": hockey["outcome"]}],
                                     "builders": []}])
    (entry,) = res["legs"].values()
    assert entry["status"] == cr.UNKNOWN and entry["score"] is None
    assert sd.event_score("cs2", {"state": "SETTLED", "series_only": True,
                                  "maps": [[1, 0], [1, 0]]}) == "2:0"


def test_a_period_yes_no_market_shows_its_period() -> None:
    dc = {**_hockey(), "family": "period_double_chance",
          "market": "period_double_chance",
          "line": None, "period": 1, "side": "1X"}
    entry = {"status": cr.WON, "actual": 1.0, "score": "1:2 (1:0, 0:1, 0:1)"}
    assert cr.actual_text(dc, entry) == "1. tercja 1:0 (mecz 1:2)"


def test_the_summary_lists_the_sports_in_a_fixed_order() -> None:
    s = cr.summarize([({"sport": sp, "confidence": 0.8, "offered_odds": 1.2},
                       {"status": cr.WON, "odds": 1.2})
                      for sp in ("cs2", "basketball", "football", "tennis")])
    assert [x["name"] for x in cr.summary_lines(s)] == [
        "piłka nożna", "tenis", "koszykówka", "CS2", "cały kupon"]


def test_event_score_never_raises_on_a_missing_period() -> None:
    assert sd.event_score("hockey", {"state": "SETTLED", "t1_full": 3, "t2_full": 1,
                                     "t1_periods": [1, None, 2],
                                     "t2_periods": [0, 1, None]}) \
        == "3:1 (1:0, ?:1, 2:?)"
    assert sd.event_score("cs2", {"state": "SETTLED",
                                  "maps": [[13, 5], [None, 3]]}) == "1:0 (13:5)"
    assert sd.event_score("hockey", {"state": "SETTLED", "t1_full": None,
                                     "t2_full": 1}) is None


# --- second review (2026-10-18) -------------------------------------------------


def test_half_time_from_the_incidents_over_a_placeholder_period1() -> None:
    """15458641, 10-16 (IFK Stocksund - Enköpings SK): the re-fetched payload
    reads period1 0:0, the incidents HT 0:2 - SETTLE graded the halves on
    0:2 (metrics.half_time_disagrees), and the page says so."""
    event = {"status": {"code": 100},
             "homeScore": {"current": 1, "display": 1, "period1": 0},
             "awayScore": {"current": 3, "display": 3, "period1": 0}}
    incidents = {"incidents": [
        {"incidentType": "period", "text": "FT", "homeScore": 1, "awayScore": 3},
        {"incidentType": "period", "text": "HT", "homeScore": 0, "awayScore": 2}]}
    assert cr._score_of_detail(event, incidents) == "1:3 (do przerwy 0:2)"
    assert cr._score_of_detail(event) == "1:3 (do przerwy 0:0)"
    # no period1 at all (17332487): the half time from the incidents
    bare = {"homeScore": {"current": 0, "display": 0},
            "awayScore": {"current": 2, "display": 2}}
    hti = {"incidents": [{"incidentType": "period", "text": "HT",
                          "homeScore": 0, "awayScore": 0}]}
    assert cr._score_of_detail(bare, hti) == "0:2 (do przerwy 0:0)"


def test_a_refunded_builders_legs_are_never_green_or_red() -> None:
    graded = _graded()
    graded[0]["builders"][0]["outcome"] = "REFUND"
    res = cr.compute("2026-10-16", graded)
    (b,) = res["builders"].values()
    assert b["status"] == cr.REFUND
    assert [x["status"] for x in b["legs"]] == [cr.REFUND, cr.REFUND]
    assert [x["own_status"] for x in b["legs"]] == [cr.WON, cr.LOST]
    assert cr.outcome_text(b["legs"][0]) == "zwrot buildera (noga: weszło)"
    # a builder that lost keeps its legs' own colours
    (lost,) = _results()["builders"].values()
    assert [x["status"] for x in lost["legs"]] == [cr.WON, cr.LOST]
    assert "own_status" not in lost["legs"][0]


def test_measured_keys_hold_the_market_and_the_map() -> None:
    base = {"sport": "cs2", "sofascore_event_id": 7, "family": "map_rounds_total",
            "period": 0, "subject": "", "line": 21.5, "side": "OVER"}
    map1, map2 = {**base, "map_nr": 1}, {**base, "map_nr": 2}
    assert cr.key_of(map1) != cr.key_of(map2)
    hk = {**_hockey()}
    assert cr.key_of({**hk, "market_id": 623}) != cr.key_of({**hk, "market_id": 624})
    graded = [{"variant": "official", "rows": {}, "builders": [], "singles": [
        {"source": {**map1, "outcome": "WIN", "actual_value": 24.0}, "odds": 1.5,
         "outcome": "WIN"},
        {"source": {**map2, "outcome": "LOSS", "actual_value": 19.0}, "odds": 1.5,
         "outcome": "LOSS"}]}]
    res = cr.compute("2026-10-16", graded)
    assert cr.of_leg(res, map1)["status"] == cr.WON
    assert cr.of_leg(res, map2)["status"] == cr.LOST


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_the_results_page_on_a_phone_and_its_other_filters(tmp_path: Path) -> None:
    assert CHROME
    view = ch.build_view(_coupon(), "2026-10-16", None, results=_results())
    page = ch.render_html("2026-10-16", view)
    probe = """
const set=(id,v)=>{const e=document.getElementById(id);
 if(e.type==="checkbox")e.checked=v;else e.value=v;e.dispatchEvent(new Event("input"))};
const n=()=>document.querySelectorAll("#body tr[data-id]").length;
const out={};const run=(k,f)=>{document.getElementById("reset").click();f();out[k]=n()};
out.page_w=document.documentElement.scrollWidth;out.view_w=window.innerWidth;
run("all",()=>{});
run("window",()=>{set("t0","19:30");set("t1","21:00")});
run("odds",()=>set("o0","1.30"));
run("comp",()=>set("comp","NHL"));
run("q",()=>set("q","home1"));
run("res_lost_q",()=>{set("res","lost");set("q","home1")});
const pre=document.createElement("pre");pre.id="probe";
pre.textContent=JSON.stringify(out);document.body.appendChild(pre);
"""
    html = tmp_path / "probe.html"
    html.write_text(page.replace("</body>", f"<script>{probe}</script></body>"),
                    encoding="utf-8")
    dom = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--window-size=390,844",
         f"--user-data-dir={tmp_path / 'prof'}", "--virtual-time-budget=10000",
         "--dump-dom", html.as_uri()],
        capture_output=True, text=True, timeout=60, check=True).stdout
    m = re.search(r'<pre id="probe">(.*?)</pre>', dom, re.S)
    assert m, "the page's script did not run"
    out = json.loads(m.group(1))
    # no sideways page scroll at phone width: the table scrolls in its box
    assert out["page_w"] <= out["view_w"]
    # 17:00 / 20:00 / 21:00 Warsaw starts (15:00Z singles, 18:00Z hockey)
    assert out["all"] == 7 and out["window"] == 1
    assert out["odds"] == 2 and out["comp"] == 1
    assert out["q"] == 2 and out["res_lost_q"] == 1
