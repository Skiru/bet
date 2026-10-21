"""Every priced row and its reason (bet.sofa.priced_rows, bet.sofa.priced_view).

The operator (2026-10-21): "you compute markets but don't show them". The
record is display only: CONFIDENCE / SPORT_CONFIDENCE write it beside their
artifact, its per-reason tally is exactly the stage's own `refused`, no gate
reads it, and the coupon page shows it in a separate "Wszystkie wyceny" tab
that is not the coupon.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import coupon_html as ch
from bet.sofa import priced_rows as pr
from bet.sofa import priced_view as pv
from tests.sofa.confidence_day import DAY, _run, day  # noqa: F401
from tests.sofa.test_coupon_html import CHROME
from tests.sofa.test_run_sport_confidence import (
    _build,
    _calibration,
    _fixture,
    _fixtures,
    _snapshot,
    _write,
)

ROOT = Path(__file__).parents[2]


def test_a_refusal_is_counted_once_and_recorded_with_what_was_known() -> None:
    counts: dict[str, int] = {}
    rec = pr.RefusalRecord(counts)
    ev = rec.event((1,), {"sport": "football", "sofascore_event_id": 1,
                          "match": "A - B", "kickoff_utc": "2026-10-20T18:00:00Z"})
    assert rec.event((1,), {}) == ev  # one event, however many rows
    rec.start(ev, "goals_total", None, None, "", 2.5, "OVER", 1.80, 0.61234)
    rec.refuse("NO_PRICE")
    rec.start(ev, "goals_total", None, None, "", 1.5, "OVER", 1.25, 0.8)
    rec.odds = 1.30  # re-priced at the fresh price
    rec.confidence = 0.78123456
    rec.refuse("BELOW_CONFIDENCE_FLOOR")
    rec.start(ev, "corners_total", None, None, "", 8.5, "OVER", 1.5, 0.8)
    rec.passed()
    rec.passed()  # nothing open: nothing recorded twice
    assert counts == {"NO_PRICE": 1, "BELOW_CONFIDENCE_FLOOR": 1}
    doc = rec.doc(DAY, "t", "CONFIDENCE")
    rows = pr.rows_as_dicts(json.loads(pr.dumps(doc)))
    assert [r["reason"] for r in rows] == ["NO_PRICE", "BELOW_CONFIDENCE_FLOOR", None]
    assert rows[0]["p"] == 0.6123 and rows[0]["confidence"] is None
    assert rows[1]["odds"] == 1.30 and rows[1]["confidence"] == 0.7812
    assert rows[2]["match"] == "A - B"


def test_no_gate_stage_or_grader_reads_the_record() -> None:
    """Display only: the files are named in the two writers, the record's own
    module, the page's view module and tests - nowhere else."""
    allowed = {"src/bet/sofa/priced_rows.py", "src/bet/sofa/priced_view.py",
               "src/bet/sofa/coupon_html.py", "scripts/sofa/run_confidence.py",
               "scripts/sofa/run_sport_confidence.py"}
    hits = set()
    for base in ("src/bet/sofa", "scripts/sofa"):
        for path in (ROOT / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"08_refusals|sofa(\.| import )priced_(rows|view)", text):
                hits.add(str(path.relative_to(ROOT)))
    assert hits <= allowed, hits - allowed
    # the writers write it and never load it
    for script in ("run_confidence.py", "run_sport_confidence.py"):
        text = (ROOT / "scripts/sofa" / script).read_text(encoding="utf-8")
        assert "priced_rows.load" not in text and "priced_view" not in text


def test_confidence_records_every_sheet_row_and_its_tally_is_refused(
        day: Path) -> None:  # noqa: F811
    run = day / DAY
    sheet = json.loads((run / "05_sheet.json").read_text())
    # two more rows: one without a price, one priced below the minimum odds
    sheet += [{**sheet[0], "line": 2.5, "offered_odds": None},
              {**sheet[0], "line": 0.5, "offered_odds": 1.01}]
    (run / "05_sheet.json").write_text(json.dumps(sheet))
    out = _run("run_confidence.py", day, "--runs-dir", str(day))
    assert out.returncode == 0, out.stderr
    record = pr.load(run / pr.FILE)
    assert record is not None and record["stage"] == "CONFIDENCE"
    rows = pr.rows_as_dicts(record)
    assert len(rows) == len(sheet)
    summary = json.loads(out.stdout.strip().splitlines()[-1])["metrics"]
    refused = {k: v for k, v in summary["refused"].items()
               if k != "BUILDER_LEGS_INCOHERENT"}  # a builder, not a row
    assert dict(Counter(r["reason"] for r in rows if r["reason"])) == refused
    conf = json.loads((run / "08_confidence.json").read_text())
    printed = {(s["sofascore_event_id"], s["line"]) for s in conf["singles"]}
    assert {(r["sofascore_event_id"], r["line"]) for r in rows
            if r["reason"] is None} == printed
    assert {r["reason"] for r in rows if r["line"] in (0.5, 2.5)} == {
        "NO_PRICE", "ODDS_TOO_LOW"}
    assert all(r["match"] == f"Home {r['sofascore_event_id']} - Away "
               f"{r['sofascore_event_id']}" for r in rows)


def test_confidence_writes_the_same_artifact_with_or_without_the_record(
        day: Path, tmp_path: Path) -> None:  # noqa: F811
    """The record changes no leg: two builds of one day, the second with the
    record's file removed in between, give the same artifact (but the clock)."""
    run = day / DAY
    assert _run("run_confidence.py", day, "--runs-dir", str(day)).returncode == 0
    first = json.loads((run / "08_confidence.json").read_text())
    (run / pr.FILE).unlink()
    assert _run("run_confidence.py", day, "--runs-dir", str(day)).returncode == 0
    second = json.loads((run / "08_confidence.json").read_text())
    for doc in (first, second):
        doc.pop("created_at_utc")
    assert first == second and (run / pr.FILE).exists()


def test_sport_confidence_records_every_priced_side(tmp_path: Path) -> None:
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture()])
    doc, _ = _build(tmp_path, _calibration(tmp_path))
    record = pr.load(tmp_path / "2026-10-06" / pr.SPORTS_FILE)
    assert record is not None and record["stage"] == "SPORT_CONFIDENCE"
    rows = pr.rows_as_dicts(record)
    refused = {k: v for k, v in doc["sports"]["hockey"]["refused"].items()
               if k != "MARKET_NOT_ALLOWED" and v}  # a market nobody priced
    assert dict(Counter(r["reason"] for r in rows if r["reason"])) == refused
    passed = {(r["market_id"], r["direction"]) for r in rows if r["reason"] is None}
    assert passed == {(g["market_id"], g["side"]) for g in doc["legs"]}
    low = [r for r in rows if r["reason"] == "BELOW_FLOOR"]
    assert low and all(r["p"] == 0.19 and r["confidence"] == 0.42 for r in low)
    assert {r["sofascore_event_id"] for r in rows} == {9001}


def test_a_refused_event_records_each_of_its_sides(tmp_path: Path) -> None:
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture(sofascore_start_utc="2026-10-06T15:10:00Z")])
    doc, _ = _build(tmp_path, _calibration(tmp_path))
    rows = pr.rows_as_dicts(pr.load(tmp_path / "2026-10-06" / pr.SPORTS_FILE) or {})
    assert doc["sports"]["hockey"]["refused"]["KICKED_OFF"] == len(rows) == 4
    assert all(r["reason"] == "KICKED_OFF" and r["p"] is None for r in rows)


# --- the page's tab -----------------------------------------------------------


def _record(rows: list[tuple[Any, ...]], sport: str = "football") -> dict[str, Any]:
    rec = pr.RefusalRecord()
    for eid, market, line, direction, odds, p, conf, reason in rows:
        ev = rec.event((eid,), {"sport": sport, "sofascore_event_id": eid,
                                "match": f"Home {eid} - Away {eid}",
                                "competition": "Liga",
                                "kickoff_utc": "2026-10-20T18:00:00Z"})
        rec.start(ev, market, None, None, "", line, direction, odds, p)
        rec.confidence = conf
        if reason:
            rec.refuse(reason)
        else:
            rec.passed()
    return rec.doc("2026-10-20", "t", "CONFIDENCE")


def _single(eid: int, line: float, conf: float) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "sport": "football", "market": "goals_total",
            "subject": "", "line": line, "direction": "OVER", "confidence": conf,
            "offered_odds": 1.5, "match": f"Home {eid} - Away {eid}",
            "kickoff_utc": "2026-10-20T18:00:00Z", "overround": 0.05}


def _view_day(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    run = tmp_path / "2026-10-20"
    run.mkdir()
    (run / pr.FILE).write_text(pr.dumps(_record([
        (1, "goals_total", 1.5, "OVER", 1.5, 0.8, 0.78, None),
        (1, "goals_total", 2.5, "OVER", 2.1, 0.55, 0.52, "BELOW_CONFIDENCE_FLOOR"),
        (2, "goals_total", 1.5, "OVER", None, 0.7, None, "NO_PRICE"),
        (2, "corners_total", 9.5, "UNDER", 1.6, 0.75, 0.72, None),
    ])))
    doc = {"pdf_max_singles": None, "prints_builders": True,
           "singles": [_single(1, 1.5, 0.78), _single(3, 3.5, 0.75)],
           "builders": [], "removed_by_reads": []}
    return run, doc


def _payload(run: Path, doc: dict[str, Any]) -> dict[str, Any] | None:
    return pv.build(run, doc, "2026-10-20", {}, ch.to_local, ch.minutes_of_day)


def test_the_tab_lists_every_row_with_printed_and_reason(tmp_path: Path) -> None:
    run, doc = _view_day(tmp_path)
    payload = _payload(run, doc)
    assert payload is not None
    rows = list(pv.as_dicts(payload))
    # 4 recorded rows + the printed single of match 3 the record lacks
    assert len(rows) == 5
    by = {(r["match"], r["family"], r["line"]): r for r in rows}
    printed = by[("Home 1 - Away 1", "goals_total", "1.5")]
    assert printed["printed"] == pv.SINGLE and printed["reason"] == ""
    assert printed["market"] == "Liczba goli: powyżej 1.5"  # Superbet's words
    assert printed["ko_local"] == "2026-10-20 20:00"
    assert by[("Home 1 - Away 1", "goals_total", "2.5")]["reason"] == \
        "BELOW_CONFIDENCE_FLOOR"
    assert by[("Home 2 - Away 2", "goals_total", "1.5")]["odds"] is None
    # passed CONFIDENCE, not on the coupon
    assert by[("Home 2 - Away 2", "corners_total", "9.5")]["reason"] == pv.NOT_ON_COUPON
    assert by[("Home 3 - Away 3", "goals_total", "3.5")]["printed"] == pv.SINGLE
    # the payload survives the page's encoding
    assert pv.decode(pv.encode(payload)) == json.loads(json.dumps(payload))


def test_a_day_without_the_record_falls_back_to_the_sheet(tmp_path: Path) -> None:
    run = tmp_path / "2026-10-20"
    run.mkdir()
    (run / "05_sheet.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "sport": "football", "market": "goals_total",
         "subject": "", "line": 1.5, "direction": "OVER", "offered_odds": 1.5,
         "p_central": 0.8}]))
    (run / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "home_name": "H", "away_name": "A",
         "competition_name": "L", "kickoff_utc": "2026-10-20T18:00:00Z"}]))
    payload = _payload(run, {"singles": [], "builders": [], "pdf_max_singles": None})
    assert payload is not None
    (row,) = pv.as_dicts(payload)
    assert row["reason"] == pv.UNKNOWN_REASON and row["match"] == "H - A"
    assert _payload(tmp_path, {"singles": []}) is None  # nothing on disk


def test_the_page_says_it_is_not_the_coupon_and_keeps_the_coupon_tab(
        tmp_path: Path) -> None:
    run, doc = _view_day(tmp_path)
    view = ch.build_view(doc, "2026-10-20")
    page = ch.render_html("2026-10-20", view, _payload(run, doc))
    assert "nie kupon - podgląd wszystkich wycen" in page
    assert 'id="priced" type="text/plain">H4sI' in page  # gzip, base64
    # the coupon's own data is untouched by the tab
    plain = ch.render_html("2026-10-20", view)
    data = re.compile(r'<script id="data" type="application/json">(.*?)</script>', re.S)
    assert data.findall(page) == data.findall(plain)
    assert '<script id="priced" type="text/plain"></script>' in plain


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_the_tab_filters_in_a_browser(tmp_path: Path) -> None:
    assert CHROME
    run, doc = _view_day(tmp_path)
    page = ch.render_html("2026-10-20", ch.build_view(doc, "2026-10-20"),
                          _payload(run, doc))
    probe = """
<script>
(async()=>{const T=window.pricedTab;T.show(true);
 for(let i=0;i<200&&!T.ready();i++)await new Promise(r=>setTimeout(r,10));
 const set=(id,v)=>{const e=document.getElementById(id);e.value=v;
  e.dispatchEvent(new Event("input"))};
 const n=()=>document.querySelectorAll("#abody tr[data-id]").length;
 const out={tab:!document.getElementById("paneA").hidden,all:n()};
 set("aprinted","1");out.printed=n();set("aprinted","0");out.notprinted=n();set("aprinted","");
 set("areason","NO_PRICE");out.reason=n();set("areason","");
 set("afam","corners_total");out.fam=n();set("afam","");
 set("asport","football");out.sport=n();
 const p=document.createElement("pre");p.id="probe";
 p.textContent=JSON.stringify(out);document.body.appendChild(p)})();
</script></body>"""
    html = tmp_path / "page.html"
    html.write_text(page.replace("</body>", probe), encoding="utf-8")
    dom = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=10000",
         "--dump-dom", html.as_uri()],
        capture_output=True, text=True, timeout=60, check=True).stdout
    m = re.search(r'<pre id="probe">(.*?)</pre>', dom, re.S)
    assert m, "the tab's script did not run"
    assert json.loads(m.group(1)) == {"tab": True, "all": 5, "printed": 2,
                                      "notprinted": 3, "reason": 1, "fam": 1,
                                      "sport": 5}
