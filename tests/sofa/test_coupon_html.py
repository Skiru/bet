"""KUPON_<d>.html: the coupon's legs as a filterable page (bet.sofa.coupon_html).

The page holds exactly the legs of 11_coupon.json (a filter can hide a leg, the
file must not lose one), shows the start in Europe/Warsaw and names a start the
fixture check read differently. The PDF render writes it beside the PDF.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import coupon_html as ch

ROOT = Path(__file__).parents[2]
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or next(
    (p for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",)
     if Path(p).exists()), None)


def _leg(eid: int, match: str, ko: str, conf: float, **kw: Any) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "group_key": f"sofa:{eid}", "match": match,
        "competition": "ITF X", "sport": "tennis", "kickoff_utc": ko,
        "market": "games_total", "subject": "", "line": 20.5,
        "direction": "OVER", "confidence": conf, "offered_odds": 1.20,
        "overround": 0.05, "sample_hit_rate": 0.9, "sample_observations": 10,
        "sample_size": 10, "position": kw.pop("position", 1), **kw,
    }


def _doc() -> dict[str, Any]:
    return {
        "created_at_utc": "2026-10-08T08:18:44Z", "positions": 3,
        "pdf_max_singles": None, "prints_builders": True,
        "singles": [
            _leg(1, "Early - Match", "2026-10-08T06:30:00Z", 0.90, locked=True,
                 position=None),
            _leg(2, "Noon - Match", "2026-10-08T09:30:00Z", 0.80, position=1),
            _leg(2, "Noon - Match", "2026-10-08T09:30:00Z", 0.75, position=2,
                 market="games_won_for", subject="a b",
                 reads=[{"verdict": "KEEP"}, {"verdict": "WATCH"}]),
            _leg(3, "Late - Match </script><b>", "2026-10-08T22:30:00Z", 0.72,
                 position=3, sport="football"),
        ],
        "builders": [], "legs": [],
    }


def test_the_page_holds_every_leg_with_local_times() -> None:
    doc = _doc()
    view = ch.build_view(doc, "2026-10-08", None)
    assert len(view["rows"]) == len(doc["singles"])
    assert [r["ko_local"] for r in view["rows"]] == [
        "2026-10-08 08:30", "2026-10-08 11:30", "2026-10-08 11:30",
        "2026-10-09 00:30"]
    # minutes since the day's local midnight: 00:30 the next day is past 1440
    assert [r["ko_min"] for r in view["rows"]] == [510, 690, 690, 1470]
    assert view["rows"][0]["locked"] and view["rows"][2]["verdict"] == "WATCH"
    assert view["rows"][1]["x"] == pytest.approx(0.96)


def test_a_start_the_fixture_check_read_differently_is_named() -> None:
    status = {"checked_at_utc": "2026-10-08T08:12:00Z", "events": {
        "1": {"start_utc": "2026-10-08T07:30:00Z",
              "checked_at_utc": "2026-10-08T08:12:00Z"},
        "2": {"start_utc": "2026-10-08T09:30:00Z",
              "checked_at_utc": "2026-10-08T08:12:00Z"}}}
    rows = ch.build_view(_doc(), "2026-10-08", status)["rows"]
    assert rows[0]["clock_note"] == "FIXTURE_CHECK: start 09:30"
    assert rows[1]["clock_note"] == ""  # same start: nothing to say
    assert rows[3]["clock_note"] == ""  # never checked
    assert rows[0]["clock_checked"] == "10:12"


def test_embedded_data_cannot_close_the_script_element() -> None:
    page = ch.render_html("2026-10-08", ch.build_view(_doc(), "2026-10-08", None))
    body = re.search(
        r'<script id="data" type="application/json">(.*?)</script>', page, re.S)
    assert body and "</" not in body.group(1)
    data = json.loads(body.group(1))
    assert any("</script>" in r["match"] for r in data["rows"])  # intact
    assert "__DATA__" not in page and "__DATE__" not in page


def test_write_html_lands_beside_the_pdf(tmp_path: Path) -> None:
    out = ch.write_html(tmp_path, _doc(), "2026-10-08")
    assert out == tmp_path / "KUPON_2026-10-08.html" and out.exists()
    assert not list(tmp_path.glob("*.tmp*"))


def test_pdf_render_and_rebuild_plan_carry_the_html() -> None:
    pdf = (ROOT / "scripts/sofa/build_coupon_pdf.py").read_text()
    assert "write_html(run, doc_json, args.date)" in pdf
    plan = (ROOT / "src/bet/sofa/rebuild_plan.py").read_text()
    assert "KUPON_<d>.html" in plan


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_filters_work_in_a_browser(tmp_path: Path) -> None:
    assert CHROME
    page = ch.render_html("2026-10-08", ch.build_view(_doc(), "2026-10-08", None))
    probe = """
const set=(id,v)=>{const e=document.getElementById(id);
 if(e.type==="checkbox")e.checked=v;else e.value=v;e.dispatchEvent(new Event("input"))};
const n=()=>[...document.querySelectorAll("#body tr:not(.m)")]
 .filter(tr=>tr.children.length>1).length;  // not the "nothing matches" row
const out={};const run=(k,f)=>{document.getElementById("reset").click();f();out[k]=n()};
run("all",()=>{});
run("window",()=>{set("t0","10:45");set("t1","13:00")});
run("cmin",()=>set("cmin","0.78"));
run("sport",()=>set("sport","football"));
run("nolock",()=>set("nolock",true));
run("q",()=>set("q","noon"));
run("odds",()=>{set("o0","1.3")});
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
    assert json.loads(m.group(1)) == {
        "all": 4, "window": 2, "cmin": 2, "sport": 1, "nolock": 3, "q": 2,
        "odds": 0}


# --- the filters, against an independent predicate, in a real browser --------

_SORTS = ("ko_local", "match", "confidence", "odds", "x", "margin", "line",
          "sample", "position")


def _expected(doc: dict[str, Any], day: str, f: dict[str, Any]) -> set[int]:
    """The ids (index in printed singles) a filter set must leave on the page,
    computed from the artifact alone - not through build_view."""
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Warsaw")
    midnight = datetime.combine(date.fromisoformat(day), time(), tzinfo=tz)
    from bet.sofa import confidence as cf
    read = {id(x) for x in cf.legs_requiring_read(doc)}
    out: set[int] = set()
    for i, leg in enumerate(cf.printed_singles(doc)):
        ko = datetime.fromisoformat(
            leg["kickoff_utc"].replace("Z", "+00:00")).astimezone(tz)
        mins = int((ko - midnight).total_seconds() // 60)
        label = leg.get("display_market") or (
            f"{leg['market']}" + (f" ({leg['subject']})" if leg.get("subject")
                                  else ""))
        hay = f"{leg['match']} {leg.get('competition') or ''} {label} " \
              f"{leg.get('family') or leg['market']}".lower()
        odds = leg.get("offered_odds")
        ok = (
            ("t0" not in f or mins >= f["t0"])
            and ("t1" not in f or mins <= f["t1"])
            and ("cmin" not in f or leg["confidence"] >= f["cmin"])
            and ("o0" not in f or (odds is not None and odds >= f["o0"]))
            and ("o1" not in f or (odds is not None and odds <= f["o1"]))
            and ("sport" not in f or leg["sport"] == f["sport"])
            and ("comp" not in f or leg["competition"] == f["comp"])
            and ("fam" not in f or (leg.get("family") or leg["market"]) == f["fam"])
            and ("dir" not in f or leg["direction"] == f["dir"])
            and not (f.get("nolock") and leg.get("locked"))
            and not (f.get("readonly") and id(leg) not in read)
            and ("q" not in f or f["q"].lower() in hay)
        )
        if ok:
            out.add(i)
    return out


def _local_minutes(leg: dict[str, Any], day: str) -> int:
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Warsaw")
    ko = datetime.fromisoformat(leg["kickoff_utc"].replace("Z", "+00:00"))
    midnight = datetime.combine(date.fromisoformat(day), time(), tzinfo=tz)
    return int((ko.astimezone(tz) - midnight).total_seconds() // 60)


def _random_filters(
    doc: dict[str, Any], day: str, rng: random.Random
) -> dict[str, Any]:
    """Random filter sets; half the bounds sit exactly on a leg's own value
    (a time, a confidence, a price), where an off-by-one in < vs <= shows."""
    singles = doc["singles"]
    pick = rng.choice(singles)
    other = rng.choice(singles)
    f: dict[str, Any] = {}
    if rng.random() < .5:
        lo, hi = sorted((_local_minutes(pick, day), _local_minutes(other, day)))
        if rng.random() < .5:
            f["t0"], f["t1"] = lo, hi
        else:
            f["t0" if rng.random() < .5 else "t1"] = lo
    if rng.random() < .3:
        f["t0"] = rng.randrange(0, 1400)  # alone, possibly after the day's legs
    if rng.random() < .5:
        f["cmin"] = (round(pick["confidence"], 2) if rng.random() < .5
                     else round(rng.uniform(0.6, 0.92), 2))
    if rng.random() < .4:
        a, z = sorted((pick["offered_odds"], other["offered_odds"]))
        if rng.random() < .5:
            f["o0"], f["o1"] = a, z
        else:
            f["o0" if rng.random() < .5 else "o1"] = a
    if rng.random() < .4:
        f["sport"] = pick["sport"]
    if rng.random() < .3:
        f["comp"] = pick["competition"]
    if rng.random() < .3:
        f["fam"] = pick.get("family") or pick["market"]
    if rng.random() < .3:
        f["dir"] = rng.choice(["OVER", "UNDER"])
    if rng.random() < .3:
        word = rng.choice(pick["match"].replace("'", " ").split())
        f["q"] = word[: rng.randrange(1, len(word) + 1)]
    if rng.random() < .15:
        f["q"] = rng.choice(pick["competition"].split())  # a competition word
    if rng.random() < .15:
        f["q"] = rng.choice(["zzzz", "(", "'", "&", "<b>", " "])
    f["nolock"] = rng.random() < .3
    f["readonly"] = rng.random() < .2
    return f


def _hm(m: int) -> str:
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def browser_sweep(
    doc: dict[str, Any], day: str, tmp_path: Path, n: int = 150, seed: int = 7,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply n random filter sets (grouped and flat) in headless Chrome and
    compare the ids left on the page with `_expected`; check every column's
    sort order both ways. Returns {"checked": n, "failures": [...]}."""
    assert CHROME
    rng = random.Random(seed)
    cases = []
    for _ in range(n):
        f = _random_filters(doc, day, rng)
        # a time input can only hold HH:MM within the day
        ex = dict(f)
        for k in ("t0", "t1"):
            if k in f and f[k] >= 1440:
                del f[k], ex[k]
        cases.append({"f": {**f, **{k: _hm(f[k]) for k in ("t0", "t1") if k in f}},
                      "exp": sorted(_expected(doc, day, ex)),
                      "group": rng.random() < .5})
    page = ch.render_html(day, ch.build_view(doc, day, status))
    probe = """
const cases=__CASES__, sorts=__SORTS__, out={cases:[],sorts:[],errs:[]};
window.onerror=e=>out.errs.push(String(e));
const G=id=>document.getElementById(id);
const set=(id,v)=>{const e=G(id);if(e.type==="checkbox")e.checked=!!v;else e.value=v;
  e.dispatchEvent(new Event("input"))};
const ids=()=>[...document.querySelectorAll("#body tr[data-id]")].map(t=>+t.dataset.id);
const IDS=["t0","t1","cmin","o0","o1","sport","comp","fam","dir","q"];
for(const c of cases){
  G("reset").click();
  for(const k of IDS)if(k in c.f)set(k,String(c.f[k]));
  set("nolock",c.f.nolock);set("readonly",c.f.readonly);set("group",c.group);
  const got=ids().sort((a,b)=>a-b);
  const empty=!!document.querySelector("#body tr:not([data-id]):not(.m)");
  out.cases.push({got,empty,count:G("count").textContent});
}
G("reset").click();set("group",false);
for(const k of sorts){
  for(let pass=0;pass<2;pass++){
    document.querySelector('th[data-k="'+k+'"]').click();
    const rows=[...document.querySelectorAll("#body tr[data-id]")]
      .map(t=>+t.dataset.id);
    // text columns: monotone under the browser's own collation (what the eye
    // reads as alphabetical), the numeric ones are checked in Python
    const v=rows.map(i=>R[i][k]);let mono=true;
    for(let i=1;i<v.length;i++){const c=String(v[i-1]).localeCompare(String(v[i]));
      if(pass===0?c>0:c<0)mono=false}
    out.sorts.push({k,pass,rows,mono});
  }
}
const pre=document.createElement("pre");pre.id="probe";
pre.textContent=JSON.stringify(out);document.body.appendChild(pre);
""".replace("__CASES__", json.dumps(cases)).replace(
        "__SORTS__", json.dumps(list(_SORTS)))
    html = tmp_path / "sweep.html"
    html.write_text(page.replace("</body>", f"<script>{probe}</script></body>"),
                    encoding="utf-8")
    dom = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=120000",
         "--dump-dom", html.as_uri()],
        capture_output=True, text=True, timeout=300, check=True).stdout
    m = re.search(r'<pre id="probe">(.*?)</pre>', dom, re.S)
    assert m, "the page's script did not run"
    import html as htmllib
    out = json.loads(htmllib.unescape(m.group(1)))
    failures: list[str] = list(out["errs"])
    for c, r in zip(cases, out["cases"]):
        if r["got"] != c["exp"]:
            failures.append(f"filters {c['f']} group={c['group']}: page "
                            f"{len(r['got'])} legs, expected {len(c['exp'])}")
        if not c["exp"] and not r["empty"]:
            failures.append(f"filters {c['f']}: no 'nothing matches' row")
        if len(r["got"]) != len(set(r["got"])):
            failures.append(f"filters {c['f']}: a leg shown twice")
    view = ch.build_view(doc, day, status)["rows"]
    for srt in out["sorts"]:
        key = {"line": "line_num", "sample": "sample_rate"}.get(srt["k"], srt["k"])
        vals = [view[i][key] for i in srt["rows"]]
        if srt["k"] in ("ko_local", "match"):
            if not srt["mono"]:
                failures.append(f"sort {srt['k']} pass {srt['pass']} not ordered")
            if sorted(srt["rows"]) != list(range(len(view))):
                failures.append(f"sort {srt['k']}: legs lost or doubled")
            continue
        known = [v for v in vals if v is not None]
        desc = srt["pass"] == (0 if srt["k"] in ("confidence", "x", "odds") else 1)
        ordered = known == sorted(known, reverse=desc)
        if not ordered or vals[: len(known)] != known:  # unknowns go last
            failures.append(f"sort {srt['k']} pass {srt['pass']} not ordered")
        if sorted(srt["rows"]) != list(range(len(view))):
            failures.append(f"sort {srt['k']}: legs lost or doubled")
    return {"checked": len(cases), "failures": failures}


def _synthetic(n: int = 90, seed: int = 3) -> dict[str, Any]:
    rng = random.Random(seed)
    singles = []
    for i in range(n):
        eid = 100 + i // 3
        hh, mm = divmod(rng.randrange(6 * 4, 24 * 4 + 6) * 15, 60)
        day = "2026-10-08" if hh < 24 else "2026-10-09"
        ko = f"{day}T{hh % 24:02d}:{mm:02d}:00Z"
        odds = rng.choice([1.1, 1.2, 1.3, 1.5, 2.0])
        singles.append(_leg(
            eid, f"Team {eid} - Rival {eid} (K)'s", ko,
            rng.choice([0.7, 0.75, 0.8, 0.85, 0.9, 0.93]),
            position=None if i % 5 == 0 else i,
            locked=i % 5 == 0, offered_odds=odds,
            sport=rng.choice(["tennis", "football", "hockey"]),
            market=rng.choice(["games_total", "goals_total", "winner"]),
            subject=rng.choice(["", "a b"]), line=rng.choice([7.5, 10.5, 20.5, 2.5]),
            direction=rng.choice(["OVER", "UNDER"]),
            competition=rng.choice(["ITF A", "Liga B", "NHL"]),
            sample_hit_rate=rng.choice([0.9, 0.8, 0.95]),
            sample_observations=rng.choice([10, 20])))
    return {"created_at_utc": "2026-10-08T08:18:44Z", "positions": n,
            "pdf_max_singles": None, "prints_builders": True,
            "singles": singles, "builders": [], "legs": []}


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_random_filter_sets_and_every_sort_match_an_independent_predicate(
    tmp_path: Path,
) -> None:
    result = browser_sweep(_synthetic(), "2026-10-08", tmp_path, n=120)
    assert result["checked"] == 120
    assert not result["failures"], result["failures"][:5]


def test_the_peer_note_is_the_pdfs_own_sentence() -> None:
    from bet.sofa.peer_choice import label

    doc = _doc()
    doc["singles"][1]["peer"] = {
        "preferred": True, "peers": 1, "band": [1.04, 1.16]}
    rows = ch.build_view(doc, "2026-10-08", None)["rows"]
    assert rows[1]["starred"] and rows[1]["peer"] == label(doc["singles"][1])
    assert "najpewniejsza z 2 nóg tego meczu w pasie kursu 1.04" in rows[1]["peer"]
    assert rows[2]["peer"] == "" and not rows[2]["starred"]
