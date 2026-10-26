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
    assert "write_html(run, doc_json, args.date" in pdf
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
run("xmin",()=>set("xmin","0.95"));
const hidden=getComputedStyle(document.getElementById("famwrap")).display==="none"
 &&getComputedStyle(document.getElementById("best")).display==="none";
out.famhidden=hidden;
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
        "odds": 0, "xmin": 2, "famhidden": True}


# --- the filters, against an independent predicate, in a real browser --------

_SORTS = ("ko_local", "match", "confidence", "odds", "x", "margin", "line",
          "sample", "position")


def _plus_keys(families: dict[str, Any] | None) -> set[str]:
    """The families on the plus, read off the record by hand."""
    if not families:
        return set()
    return {k for k, v in families["families"].items()
            if v["legs"] >= families["min_legs"] and v["units"] > 0}


def _expected(doc: dict[str, Any], day: str, f: dict[str, Any],
              families: dict[str, Any] | None = None) -> set[int]:
    """The ids (index in printed singles) a filter set must leave on the page,
    computed from the artifact alone - not through build_view."""
    plus = _plus_keys(families)
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Warsaw")
    midnight = datetime.combine(date.fromisoformat(day), time(), tzinfo=tz)
    from bet.sofa import confidence as cf
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
            and ("xmin" not in f or (_x(leg) is not None and _x(leg) >= f["xmin"]))
            and not (f.get("famplus") and f"{leg['sport']}|{leg['market']}|"
                     f"{leg['direction']}" not in plus)
            and not (f.get("nolock") and leg.get("locked"))
            and not (f.get("readonly") and not leg.get("reads"))
            and ("q" not in f or f["q"].lower() in hay)
        )
        if ok:
            out.add(i)
    return out


def _x(leg: dict[str, Any]) -> float | None:
    """The page's x by hand: the artifact's own x, else confidence x odds."""
    if leg.get("x") is not None:
        return float(leg["x"])
    odds = leg.get("offered_odds")
    return None if odds is None else leg["confidence"] * odds


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
    if rng.random() < .3:
        x = _x(pick)
        f["xmin"] = x if rng.random() < .5 else round(rng.uniform(0.6, 1.4), 2)
    f["nolock"] = rng.random() < .3
    f["readonly"] = rng.random() < .2
    f["famplus"] = rng.random() < .3
    return f


def _hm(m: int) -> str:
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def browser_sweep(
    doc: dict[str, Any], day: str, tmp_path: Path, n: int = 150, seed: int = 7,
    status: dict[str, Any] | None = None,
    families: dict[str, Any] | None = None,
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
                      "exp": sorted(_expected(doc, day, ex, families)),
                      "group": rng.random() < .5})
    page = ch.render_html(day, ch.build_view(doc, day, status, families))
    probe = """
const cases=__CASES__, sorts=__SORTS__, out={cases:[],sorts:[],errs:[]};
window.onerror=e=>out.errs.push(String(e));
const G=id=>document.getElementById(id);
const set=(id,v)=>{const e=G(id);if(e.type==="checkbox")e.checked=!!v;else e.value=v;
  e.dispatchEvent(new Event("input"))};
const ids=()=>[...document.querySelectorAll("#body tr[data-id]")].map(t=>+t.dataset.id);
const IDS=["t0","t1","cmin","xmin","o0","o1","sport","comp","fam","dir","q"];
for(const c of cases){
  G("reset").click();
  for(const k of IDS)if(k in c.f)set(k,String(c.f[k]));
  set("nolock",c.f.nolock);set("readonly",c.f.readonly);set("famplus",c.f.famplus);
  set("group",c.group);
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
G("reset").click();set("group",true);out.gsorts=[];
for(const k of ["x","confidence","odds"]){
  document.querySelector('th[data-k="'+k+'"]').click();
  out.gsorts.push({k,rows:[...document.querySelectorAll("#body tr[data-id]")]
    .map(t=>+t.dataset.id)});
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
    view = ch.build_view(doc, day, status, families)["rows"]
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
    # grouped: a match's legs follow the chosen column, and matches follow
    # their first leg (each click picks a new column, which opens descending)
    for srt in out["gsorts"]:
        desc = True
        vals = [view[i][srt["k"]] for i in srt["rows"]]
        evs = [view[i]["event"] for i in srt["rows"]]
        firsts = [v for j, v in enumerate(vals) if j == 0 or evs[j] != evs[j - 1]]
        if firsts != sorted(firsts, reverse=desc):
            failures.append(f"grouped sort {srt['k']}: matches not ordered")
        for j in range(1, len(vals)):
            if evs[j] == evs[j - 1] and (vals[j] > vals[j - 1] if desc
                                         else vals[j] < vals[j - 1]):
                failures.append(f"grouped sort {srt['k']}: legs not ordered")
                break
        if sorted(srt["rows"]) != list(range(len(view))):
            failures.append(f"grouped sort {srt['k']}: legs lost or doubled")
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
        if i % 4 == 1:  # read; the reason carries markup that must stay text
            singles[-1]["reads"] = [{"verdict": "KEEP", "author": "analyst",
                                     "reason": f"<b>form</b> & 'h2h' {i}"}]
        if i % 7 == 0:  # an artifact's own rounded x, off confidence x odds
            leg = singles[-1]
            leg["x"] = round(leg["confidence"] * leg["offered_odds"], 4) + (
                0.0001 if i % 2 else -0.0001)
    return {"created_at_utc": "2026-10-08T08:18:44Z", "positions": n,
            "pdf_max_singles": None, "prints_builders": True,
            "singles": singles, "builders": [], "legs": []}


def _families() -> dict[str, Any]:
    """A record with two families on the plus, one with too few legs and one
    at a loss (bet.sofa.family_record's shape)."""
    def e(legs: int, units: float) -> dict[str, Any]:
        return {"legs": legs, "matches": legs, "won": 0, "units": units,
                "roi": units / legs, "hit": 0.5, "implied": 0.8}
    return {"before": "2026-10-08", "days": ["2026-10-07"], "variant": "official",
            "min_legs": 50, "created_at_utc": "2026-10-08T05:00:00Z",
            "families": {"football|goals_total|OVER": e(80, 3.0),
                         "tennis|games_total|UNDER": e(50, 0.5),
                         "hockey|winner|OVER": e(49, 9.0),
                         "football|goals_total|UNDER": e(300, -12.0)}}


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_the_measured_selection_button_sets_x_and_the_families(tmp_path: Path) -> None:
    assert CHROME
    doc = _synthetic()
    fam = _families()
    page = ch.render_html("2026-10-08", ch.build_view(doc, "2026-10-08", None, fam))
    probe = """
const sp=document.getElementById("sport");sp.value="football";
sp.dispatchEvent(new Event("input"));
document.getElementById("best").click();
const ids=[...document.querySelectorAll("#body tr[data-id]")].map(t=>+t.dataset.id);
const out={ids,xmin:document.getElementById("xmin").value,
 fam:document.getElementById("famplus").checked,
 note:document.getElementById("famnote").textContent,
 tags:document.querySelectorAll("#body .tag.acc").length};
document.getElementById("reset").click();
out.after=[document.getElementById("xmin").value,document.getElementById("famplus").checked];
const pre=document.createElement("pre");pre.id="probe";
pre.textContent=JSON.stringify(out);document.body.appendChild(pre);
"""
    html = tmp_path / "best.html"
    html.write_text(page.replace("</body>", f"<script>{probe}</script></body>"),
                    encoding="utf-8")
    dom = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=10000",
         "--dump-dom", html.as_uri()],
        capture_output=True, text=True, timeout=60, check=True).stdout
    m = re.search(r'<pre id="probe">(.*?)</pre>', dom, re.S)
    assert m, "the page's script did not run"
    import html as htmllib
    out = json.loads(htmllib.unescape(m.group(1)))
    # the button sets x and the families and leaves the other filters alone
    exp = _expected(doc, "2026-10-08",
                    {"xmin": 1.0, "famplus": True, "sport": "football"}, fam)
    assert exp and sorted(out["ids"]) == sorted(exp)
    assert out["xmin"] == "1.00" and out["fam"] is True
    assert out["tags"] == len(exp)  # every shown leg is on the plus, tagged
    assert "zysk nieudowodniony" in out["note"] and "2026-10-07" in out["note"]
    assert out["after"] == ["", False]


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_random_filter_sets_and_every_sort_match_an_independent_predicate(
    tmp_path: Path,
) -> None:
    result = browser_sweep(_synthetic(), "2026-10-08", tmp_path, n=120,
                           families=_families())
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


# --- the analysts' notes ---------------------------------------------------------


def _read_doc() -> dict[str, Any]:
    doc = _doc()
    doc["singles"][2]["reads"] = [
        {"verdict": "KEEP", "author": "analyst", "reason": "Form holds <i>x</i>."},
        {"verdict": "WATCH", "author": "verifier", "reason": "Rest & travel."}]
    bleg = {k: doc["singles"][2][k] for k in ("market", "subject", "line",
                                               "direction", "confidence")}
    doc["builders"] = [{
        "sofascore_event_id": 2, "match": "Noon - Match", "competition": "ITF X",
        "kickoff_utc": "2026-10-08T09:30:00Z", "combined_probability": 0.6,
        "best_for_fixture": True, "ev_after_haircut": 0.1,
        "legs": [{**bleg, "odds": 1.2},
                 {**bleg, "market": "games_total", "subject": "", "odds": 1.3}]}]
    return doc


def test_a_read_legs_notes_ride_on_its_row_and_its_builder_leg() -> None:
    view = ch.build_view(_read_doc(), "2026-10-08", None)
    rows = view["rows"]
    assert rows[2]["read_done"] and [n["author"] for n in rows[2]["notes"]] == [
        "analyst", "verifier"]
    assert rows[2]["notes"][0]["reason"] == "Form holds <i>x</i>."
    assert not rows[1]["read_done"] and rows[1]["notes"] == []
    # a builder's leg carries no reads itself: it shows the single's read of
    # the same leg, and none where no single of that leg was read
    legs = view["builders"][0]["legs"]
    assert legs[0]["notes"] == rows[2]["notes"] and legs[1]["notes"] == []


def test_read_notes_skip_a_leg_without_a_graders_key() -> None:
    doc = _read_doc()
    doc["legs"] = [{"reads": [{"verdict": "KEEP"}]}]  # no event, no market
    doc["builders"][0]["legs"].append({"odds": 1.1})  # a builder leg too
    legs = ch.build_view(doc, "2026-10-08", None)["builders"][0]["legs"]
    assert legs[-1]["notes"] == []


def test_a_match_whose_read_legs_were_all_removed_is_not_unread() -> None:
    doc = _doc()
    removed = _leg(3, "Late - Match", "2026-10-08T22:30:00Z", 0.8,
                   sport="football", reads=[{"verdict": "WATCH",
                                             "author": "analyst", "reason": "r"}])
    doc["removed_by_reads"] = [removed]
    events = ch.build_view(doc, "2026-10-08", None)["meta"]["read_events"]
    assert "sofa:3" in events and "sofa:2" in events and "sofa:1" not in events


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_the_page_shows_each_read_and_names_an_unread_match(tmp_path: Path) -> None:
    page = ch.render_html("2026-10-08", ch.build_view(_read_doc(), "2026-10-08",
                                                      None))
    probe = """
const set=(id,v)=>{const e=document.getElementById(id);e.checked=v;
 e.dispatchEvent(new Event("input"))};
const out={};
out.notes=[...document.querySelectorAll("#body details.rn")].map(d=>d.textContent);
out.markup=document.querySelectorAll("#body details.rn i").length;
out.unread=[...document.querySelectorAll("#body tr.m")].filter(
 tr=>tr.textContent.includes("nieczytany")).map(tr=>tr.textContent.slice(0,40));
out.kept=document.querySelectorAll("#body .tag.ok").length;
out.blnotes=document.querySelectorAll("#builders details.rn").length;
out.blunread=[...document.querySelectorAll("#builders .tag.warn")].length;
set("readonly",true);
out.readonly=[...document.querySelectorAll("#body tr:not(.m)")].length;
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
    import html as htmllib
    out = json.loads(htmllib.unescape(m.group(1)))
    assert len(out["notes"]) == 1
    note = out["notes"][0]
    assert "KEEP (analityk)" in note and "WATCH (weryfikator)" in note
    assert "Form holds <i>x</i>." in note and "Rest & travel." in note
    assert out["markup"] == 0  # the reason is text, never markup
    # the leg's WATCH is the bad tag, not "przeczytana"
    assert out["kept"] == 0
    # Early and Late have no read leg; Noon has one
    assert len(out["unread"]) == 2 and not any("Noon" in u for u in out["unread"])
    assert out["blnotes"] == 1 and out["blunread"] == 1
    assert out["readonly"] == 1


def _probe(page: str, probe: str, tmp_path: Path, phone: bool = False) -> Any:
    """Run `probe` in the page in headless Chrome (a profile kept in tmp_path)
    and return what it passes to done(). `phone`: the page sits in a 390 px
    frame (an iPhone 13 Pro) - headless Chrome keeps a window >= 500 px."""
    assert CHROME
    done = ('const done=o=>{const t=JSON.stringify(o);if(parent!==window)'
            'parent.postMessage(t,"*");else{const p=document.createElement("pre");'
            'p.id="probe";p.textContent=t;document.body.appendChild(p)}};')
    html = tmp_path / "probe.html"
    html.write_text(page.replace("</body>", f"<script>{done}{probe}</script></body>"),
                    encoding="utf-8")
    url = html.as_uri()
    if phone:
        host = tmp_path / "host.html"
        host.write_text(
            '<body><script>addEventListener("message",e=>{const p=document.'
            'createElement("pre");p.id="probe";p.textContent=e.data;document.body.'
            'appendChild(p)})</script><iframe src="probe.html" style="border:0;'
            'width:390px;height:844px"></iframe></body>', encoding="utf-8")
        url = host.as_uri()
    dom = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--window-size=1280,900",
         f"--user-data-dir={tmp_path / 'prof'}", "--virtual-time-budget=10000",
         "--dump-dom", url],
        capture_output=True, text=True, timeout=60, check=True).stdout
    m = re.search(r'<pre id="probe">(.*?)</pre>', dom, re.S)
    assert m, "the page's script did not run"
    import html as htmllib
    return json.loads(htmllib.unescape(m.group(1)))


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_a_long_day_draws_in_chunks_and_loses_no_leg(tmp_path: Path) -> None:
    # 450 legs: the page draws 200, the rest follows on "pokaż więcej"
    page = ch.render_html("2026-10-08", ch.build_view(_synthetic(450), "2026-10-08"))
    out = _probe(page, """
const G=id=>document.getElementById(id);
const n=()=>document.querySelectorAll("#body tr[data-id]").length;
const out={first:n(),more:!!G("more")};
for(let i=0;i<10&&G("more");i++)G("more").click();
out.all=n();out.left=!!G("more");
out.ids=new Set([...document.querySelectorAll("#body tr[data-id]")]
 .map(t=>t.dataset.id)).size;
done(out);
""", tmp_path)
    assert out["first"] <= 200 + 3 and out["more"]  # whole matches per chunk
    assert out["all"] == 450 and out["ids"] == 450 and not out["left"]


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_chips_upcoming_and_saved_filters(tmp_path: Path) -> None:
    doc = _synthetic()
    page = ch.render_html("2026-10-08", ch.build_view(doc, "2026-10-08"))
    sports = {s["sport"] for s in doc["singles"]}
    out = _probe(page, """
const G=id=>document.getElementById(id);
const n=()=>document.querySelectorAll("#body tr[data-id]").length;
const out={all:n(),chips:{}};
document.querySelectorAll("#chips .chip[data-sport]").forEach(c=>{
  if(!c.dataset.sport)return;
  c.click();out.chips[c.dataset.sport]=[n(),G("sport").value,c.classList.contains("on")]});
G("reset").click();
// every start of 2026-10-08 is in the past: "nierozpoczęte" leaves nothing
document.querySelector('#chips .chip[data-t="upcoming"]').click();
out.upcoming=n();out.badge=G("fcount").textContent;
G("reset").click();
document.querySelector('#chips .chip[data-t="xone"]').click();
out.xmin=G("xmin").value;
out.saved=JSON.parse(localStorage.getItem("kupon:2026-10-08")).xmin;
out.page_w=document.documentElement.scrollWidth;out.view_w=window.innerWidth;
done(out);
""", tmp_path, phone=True)
    assert out["all"] == 90
    assert set(out["chips"]) == sports
    for sport, (n, chosen, on) in out["chips"].items():
        assert n == sum(s["sport"] == sport for s in doc["singles"])
        assert chosen == sport and on
    assert out["upcoming"] == 0 and out["badge"] == "1"
    assert out["xmin"] == "1.00" and out["saved"] == "1.00"
    assert out["page_w"] <= out["view_w"]


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_saved_filters_are_restored_on_reopen(tmp_path: Path) -> None:
    page = ch.render_html("2026-10-08", ch.build_view(_synthetic(), "2026-10-08"))
    first = _probe(page, """
const G=id=>document.getElementById(id);G("sport").value="hockey";
G("sport").dispatchEvent(new Event("input"));
done(document.querySelectorAll("#body tr[data-id]").length);
""", tmp_path)
    # the same profile opens the page again: the filter is back
    again = _probe(page, """
done([document.getElementById("sport").value,
 document.querySelectorAll("#body tr[data-id]").length]);
""", tmp_path)
    assert again == ["hockey", first] and first < 90


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_review_fixes_hold_on_a_phone(tmp_path: Path) -> None:
    page = ch.render_html("2026-10-08", ch.build_view(_synthetic(450), "2026-10-08"))
    out = _probe(page, """
const G=id=>document.getElementById(id);
const n=()=>document.querySelectorAll("#body tr[data-id]").length;
const out={};
// coming back to the page keeps the drawn chunks and an open note
G("more").click();out.before=n();
const d=document.querySelector("#body details.rn");d.open=true;
document.dispatchEvent(new Event("visibilitychange"));
out.after=n();out.open=d.isConnected&&d.open;
// a header click shows in the sort list
document.querySelector('th[data-k="line"]').click();
const so=G("sort");out.sort=so.options[so.selectedIndex].textContent;
// ungrouped cards show their start time
G("group").checked=false;G("group").dispatchEvent(new Event("input"));
const ko=document.querySelector("#body tr[data-id] .c-ko");
out.ko=getComputedStyle(ko).display!=="none"&&ko.textContent.length===5;
out.badge=G("fcount").textContent;
// an open panel is not stuck over the legs
G("ftoggle").click();out.pos=getComputedStyle(G("tool")).position;
out.page_w=document.documentElement.scrollWidth;out.view_w=window.innerWidth;
done(out);
""", tmp_path, phone=True)
    assert out["after"] == out["before"] > 200 and out["open"]
    assert out["sort"] == "linia ↑"
    assert out["ko"] and out["badge"] == "1"
    assert out["pos"] == "static"
    assert out["view_w"] == 390 and out["page_w"] <= 390


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_a_saved_family_filter_is_not_restored_without_a_record(
        tmp_path: Path) -> None:
    doc = _synthetic()
    with_fam = ch.render_html("2026-10-08",
                              ch.build_view(doc, "2026-10-08", None, _families()))
    _probe(with_fam, """
const c=document.getElementById("famplus");c.checked=true;
c.dispatchEvent(new Event("input"));done(0);
""", tmp_path)
    # the same day rendered without family_record.json: the box is hidden
    out = _probe(ch.render_html("2026-10-08", ch.build_view(doc, "2026-10-08")), """
done([document.getElementById("famplus").checked,
 document.querySelectorAll("#body tr[data-id]").length]);
""", tmp_path)
    assert out == [False, 90]


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_phone_panel_comma_decimals_and_a_next_days_date(tmp_path: Path) -> None:
    doc = _synthetic()
    page = ch.render_html("2026-10-08", ch.build_view(doc, "2026-10-08"))
    out = _probe(page, """
const G=id=>document.getElementById(id);
const n=()=>document.querySelectorAll("#body tr[data-id]").length;
const out={};
// the panel's checkboxes stay boxes beside their words (not stretched to the row)
G("ftoggle").click();out.box=G("nolock").getBoundingClientRect().width;
// a Polish keyboard types a comma: the filter reads it as the dot
G("cmin").value="0,8";G("cmin").dispatchEvent(new Event("input"));out.comma=n();
G("reset").click();
// a flat list: a start on the next day carries its date
G("group").checked=false;G("group").dispatchEvent(new Event("input"));
out.next=[...document.querySelectorAll("#body tr[data-id]")].filter(t=>
  V.rows[+t.dataset.id].ko_local.slice(0,10)!=="2026-10-08").map(t=>t.querySelector(".c-ko").textContent);
done(out);
""", tmp_path, phone=True)
    assert out["box"] <= 24
    assert out["comma"] == sum(s["confidence"] >= 0.8 for s in doc["singles"])
    assert out["next"] and all(t.endswith("(10-09)") for t in out["next"])


@pytest.mark.skipif(CHROME is None, reason="no headless Chrome here")
def test_an_open_page_moves_its_clock_without_a_redraw(tmp_path: Path) -> None:
    import datetime as dt
    start = dt.datetime.now(dt.UTC).replace(microsecond=0) + dt.timedelta(minutes=30)
    day = f"{start:%Y-%m-%d}"
    doc = _doc()
    doc["singles"] = [_leg(7, "Soon - Match", f"{start:%Y-%m-%dT%H:%M:%SZ}", 0.8)]
    page = ch.render_html(day, ch.build_view(doc, day))
    out = _probe(page, """
const tag=()=>document.querySelector("#body .clk").textContent;
const before=tag(),row=document.querySelector("#body tr[data-id]");
const real=Date.now;Date.now=()=>real()+40*60000;paint();
done([before,tag(),row.isConnected]);
""", tmp_path)
    assert re.fullmatch(r"za (29|30) min", out[0])
    assert out[1] == "rozpoczęty" and out[2]


def _contrast(fg: str, bg: str) -> float:
    def lum(h: str) -> float:
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def test_print_keeps_the_table_and_small_labels_are_readable() -> None:
    css = ch._TEMPLATE
    # an A4 page is narrower than 760 px: the cards are the screen's only
    assert "@media screen and (max-width:760px){" in css
    assert "@media print,(min-width:761px){" in css
    assert "@media (max-width:760px)" not in css
    # the 11 px card labels (--dim) on a card (--s1) and on the page (--bg)
    tok = dict(re.findall(r"--(dim|s1|bg):(#[0-9a-f]{6})", css.split("@media")[0]))
    assert _contrast(tok["dim"], tok["s1"]) >= 4.5
    assert _contrast(tok["dim"], tok["bg"]) >= 4.5
