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
    assert pdf.main() == 0
    text = "\n".join(p.extract_text() for p in
                     pypdf.PdfReader(run / "KUPON_2026-10-16.pdf").pages)
    flat = " ".join(text.split())
    assert "Podsumowanie wyników" in flat
    assert "weszło 3 (42.9%)" in flat
    assert "nie weszło" in flat and "było: 11" in flat
    assert "Builder: nie weszło" in flat
    # a view of a finished day, not a print: no print record
    assert not (run / "printed").exists()
    # the HTML beside it carries the same results
    page = (run / "KUPON_2026-10-16.html").read_text(encoding="utf-8")
    assert '"cały kupon"' in page


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
    assert mcr.mark(str(tmp_path), "2026-10-17", "db")[0] == "NO_COUPON"


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
