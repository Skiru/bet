"""bet.sofa.analyses - the analysts' match sections kept by match
(analyses.json), recorded by merge_reads.py, pointed at by read_set.py's
`prior_analysis`, shown folded on the HTML view and in the PDF's appendix
(2026-10-26: 50 reports a day, nobody could find the section behind a leg)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from reportlab.lib.styles import ParagraphStyle

from bet.sofa import analyses
from bet.sofa.contracts import LegRead
from bet.sofa.coupon_html import build_view, render_html
from bet.sofa.report_check import findings
from bet.sofa.veto import read_note
from scripts.sofa import build_analyses, merge_reads, read_set
from scripts.sofa.build_coupon import assemble
from scripts.sofa.build_coupon_pdf import (
    READ_CELL_CHARS,
    analysis_appendix_flowables,
    analysis_ref_label,
    analysis_refs,
    md_paragraphs,
    read_label,
)

small = ParagraphStyle("t")
T8, T12 = "2026-10-26T08:00:00+00:00", "2026-10-26T12:00:00+00:00"
KEEP_REASON = (
    "rożne: oczekuję ~10, 15/18 > 7.5; tabela 2. vs 18.; "
    "nic istotnego [WEB: bbc.com, publ. 10-25, fetched 08:00Z]"
)


def read(eid: int, verdict: str = "KEEP") -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "market": "corners_total",
        "subject": "",
        "line": 5.5,
        "direction": "OVER",
        "verdict": verdict,
        "author": "analyst",
        "reason": KEEP_REASON,
    }


def report(reads: list[dict[str, Any]], body: str) -> str:
    return (
        f"# Analiza piłkarska\n\n## Nagłówek\nDossier przeczytane.\n\n{body}\n"
        "## Zdjęte\nbrak\n\n## NIE PODANO\nnic\n\n```json vetoes\n[]\n```\n\n"
        f"```json reads\n{json.dumps(reads)}\n```\n"
    )


SECTION_A = (
    "### Alfa – Beta — Liga, 9. kolejka · sofa:101\n**Start:** 20:00Z\n\n"
    "**Kontekst (web).** nic [WEB: bbc.com, publ. x, fetched y]\n\n"
    "#### Nogi\n- rożne — KEEP\n\n**Werdykt:** KEEP — wszystko gra\n\n"
)
SECTION_B = "### Gamma – Delta — Liga\nsofa:202\n\nKontekst (web): nic\n\n"


def test_sections_are_cut_by_the_token_in_or_under_the_heading() -> None:
    text = report([read(101), read(202)], SECTION_A + SECTION_B)
    found = analyses.split_sections(text)
    assert [s["event_id"] for s in found] == [101, 202]
    a = found[0]
    # the sub-heading stays inside its match; Zdjęte / NIE PODANO are no match
    assert "#### Nogi" in a["markdown"] and "Zdjęte" not in a["markdown"]
    assert a["heading"] == "Alfa – Beta — Liga, 9. kolejka"
    assert a["web_tags"] == 1 and a["context_pass"] is True
    assert a["delta"] is False
    # the token on the line under the heading counts too
    assert found[1]["context_pass"] is True and "```" not in found[1]["markdown"]


def test_a_heading_without_a_token_is_matched_by_both_names() -> None:
    names = {
        301: "Sparta Rotterdam - AFC Ajax",
        302: "Jong Ajax - Sparta Rotterdam",
        303: "Olympiacos FC - PS Kalamata",
    }
    text = report(
        [read(303)],
        "### Sparta Rotterdam – AFC Ajax — Eredivisie\nx\n\n"
        "### Olympiacos – Kalamata — Super League\ny\n\n"
        "### Nikt – Nikomu\nz\n",
    )
    found = analyses.split_sections(text, names)
    # the exact pair; then the loose word match among the report's own reads
    # (303: "Olympiacos" / "Kalamata"); a heading naming no match is skipped
    assert [s["event_id"] for s in found] == [301, 303]


def test_the_loose_match_needs_the_reports_own_read_and_one_candidate() -> None:
    names = {401: "Olympiacos FC - PS Kalamata", 402: "Olympiacos B - Kalamata U19"}
    text = report([read(401), read(402)], "### Olympiacos – Kalamata\nx\n")
    assert analyses.split_sections(text, names) == []  # two candidates: none
    alone = report([], "### Olympiacos – Kalamata\nx\n")
    assert analyses.split_sections(alone, {401: names[401]}) == []  # not read


def test_the_store_keeps_every_report_newest_first_and_replaces_its_own(
    tmp_path: Path,
) -> None:
    run = tmp_path / "2026-10-26"
    run.mkdir()
    first = run / "2026-10-26_analiza_football.md"
    first.write_text(report([read(101)], SECTION_A))
    again = run / "2026-10-26_analiza_football_r2.md"
    again.write_text(report([read(101)], SECTION_A.replace("wszystko gra", "delta")))
    store: dict[str, Any] = {"version": 1, "events": {}}
    assert analyses.add_report(store, first, "analyst", T8) == 1
    assert analyses.add_report(store, again, "analyst", T12) == 1
    entries = store["events"]["101"]
    assert [e["report"] for e in entries] == [again.name, first.name]
    # the same report recorded again replaces its own section, never doubles it
    analyses.add_report(store, first, "analyst", "2026-10-26T13:00:00+00:00")
    assert [e["report"] for e in store["events"]["101"]] == [first.name, again.name]
    assert analyses.latest(store, 101)["recorded_at_utc"].startswith("2026-10-26T13")
    assert analyses.latest(store, 101, "verifier") is None
    analyses.save(run, store)
    assert analyses.load(run)["events"]["101"][0]["report"] == first.name
    # a broken store reads as empty: display only, never a crash
    (run / analyses.STORE).write_text("{not json")
    assert analyses.load(run) == {"version": 1, "events": {}}


def test_rebuild_reads_every_report_oldest_first(tmp_path: Path) -> None:
    run = tmp_path / "2026-10-26"
    run.mkdir()
    (run / "2026-10-26_analiza_football.md").write_text(report([read(101)], SECTION_A))
    (run / "2026-10-26_weryfikacja.md").write_text(
        report([read(101)], SECTION_A.replace("KEEP — wszystko gra", "WATCH — nie"))
    )
    store, n = analyses.rebuild(run, "2026-10-26", {})
    assert n == 2
    assert {e["author"] for e in store["events"]["101"]} == {"analyst", "verifier"}
    assert (
        build_analyses.main(["--date", "2026-10-26", "--runs-dir", str(tmp_path)]) == 0
    )
    assert (run / analyses.STORE).exists()
    assert (
        build_analyses.main(["--date", "1999-01-01", "--runs-dir", str(tmp_path)]) == 2
    )


def test_merge_stamps_reads_once_and_records_sections(tmp_path: Path) -> None:
    run = tmp_path / "2026-10-26"
    run.mkdir()
    path = run / "2026-10-26_analiza_football.md"
    path.write_text(report([read(101)], SECTION_A))
    args = ["--date", run.name, "--runs-dir", str(tmp_path), "--report", str(path)]
    assert merge_reads.main([*args, "--dry-run"]) == 0
    assert not (run / analyses.STORE).exists()  # a dry run writes nothing
    assert merge_reads.main([*args, "--author", "analyst"]) == 0
    reads = json.loads((run / "reads.json").read_text())
    assert len(reads) == 1 and reads[0]["read_at_utc"]
    LegRead.model_validate(reads[0])
    stamp = reads[0]["read_at_utc"]
    # merged again: one read, its first stamp kept
    assert merge_reads.main(args) == 0
    again = json.loads((run / "reads.json").read_text())
    assert len(again) == 1 and again[0]["read_at_utc"] == stamp
    store = json.loads((run / analyses.STORE).read_text())
    assert store["events"]["101"][0]["report"] == path.name
    # a chat slip's merge never touches the coupon's store
    (run / analyses.STORE).unlink()
    assert merge_reads.main([*args, "--slip"]) == 0
    assert not (run / analyses.STORE).exists()


def test_a_report_without_sections_is_named_not_refused(
    tmp_path: Path, capsys: Any
) -> None:
    run = tmp_path / "2026-10-26"
    run.mkdir()
    path = run / "2026-10-26_analiza_tennis.md"
    path.write_text(report([read(9)], "### bez tokenu\nx\n"))
    assert (
        merge_reads.main(
            ["--date", run.name, "--runs-dir", str(tmp_path), "--report", str(path)]
        )
        == 0
    )
    assert "NO_SECTIONS" in capsys.readouterr().out


def test_read_note_carries_the_stamp_and_the_tag_only_when_set() -> None:
    bare = LegRead.model_validate({**read(1), "verdict": "WATCH"})
    assert read_note(bare) == {
        "verdict": "WATCH",
        "author": "analyst",
        "reason": KEEP_REASON,
    }
    full = LegRead.model_validate({**read(1), "read_at_utc": T8, "context": "ABSENCES"})
    assert read_note(full)["read_at_utc"].startswith("2026-10-26T08")
    assert read_note(full)["context"] == "ABSENCES"


def coupon_day(tmp_path: Path) -> Path:
    singles = [
        {
            "sofascore_event_id": e,
            "confidence": 0.8,
            "sport": "football",
            "kickoff_utc": "2026-10-26T20:00:00Z",
            "market": "corners_total",
            "subject": "",
            "line": 5.5,
            "direction": "OVER",
            "offered_odds": 1.25,
            "match": f"M{e} - N{e}",
            "display_market": "c",
        }
        for e in (101, 102)
    ]
    conf = {
        "profile": "standard",
        "epoch": "stats_only",
        "created_at_utc": "x",
        "singles": singles,
        "legs": singles,
        "builders": [],
    }
    doc = assemble(
        conf, None, [], {}, "now", "2026-10-26", read_events=True, read_value_order=True
    )
    run = tmp_path / "2026-10-26"
    run.mkdir()
    (run / "11_coupon.json").write_text(json.dumps(doc))
    return run


def test_read_set_points_a_reread_at_the_earlier_section(tmp_path: Path) -> None:
    run = coupon_day(tmp_path)
    store: dict[str, Any] = {"version": 1, "events": {}}
    path = run / "2026-10-26_analiza_football.md"
    path.write_text(report([read(101)], SECTION_A))
    analyses.add_report(store, path, "analyst", T8)
    analyses.save(run, store)
    legs = {x["sofascore_event_id"]: x for x in read_set.read_set(run)["football"]}
    prior = legs[101]["prior_analysis"]
    assert prior == {
        "report": path.name,
        "recorded_at_utc": T8,
        "web_tags": 1,
        "context_pass": True,
        "full_pass_report": path.name,
        "full_pass_at_utc": T8,
    }
    assert "prior_analysis" not in legs[102]


def test_the_page_inlines_only_its_own_matches_sections(tmp_path: Path) -> None:
    run = coupon_day(tmp_path)
    doc = json.loads((run / "11_coupon.json").read_text())
    store = {
        "version": 1,
        "events": {
            "101": [{"author": "analyst", "report": "r.md", "markdown": "### x"}],
            "999": [{"author": "analyst", "report": "r.md", "markdown": "### other"}],
        },
    }
    view = build_view(doc, "2026-10-26", analyses=store)
    assert set(view["meta"]["analyses"]) == {"101"}
    assert {r["event_id"] for r in view["rows"]} == {"101", "102"}
    assert build_view(doc, "2026-10-26")["meta"]["analyses"] == {}


def test_the_pdf_numbers_read_matches_and_prints_their_sections() -> None:
    singles = [{"sofascore_event_id": e} for e in (5, 7, 5, 9)]
    store = {
        "events": {
            "7": [
                {
                    "author": "verifier",
                    "report": "w.md",
                    "heading": "Gamma – Delta",
                    "markdown": "### Gamma – Delta\n| a | b |\n|---|---|\n| 1 | <2> |",
                    "recorded_at_utc": "2026-10-26T09:10:00+00:00",
                },
                {
                    "author": "analyst",
                    "report": "a.md",
                    "heading": "Gamma – Delta",
                    "markdown": "### Gamma – Delta\n**Dossier.** forma & tabela\n\n- x",
                    "recorded_at_utc": "2026-10-26T08:00:00+00:00",
                },
            ],
            "9": [
                {
                    "author": "analyst",
                    "report": "b.md",
                    "heading": "E – F",
                    "markdown": "### E – F\ny",
                }
            ],
        }
    }
    refs = analysis_refs(singles, [], store)
    assert refs == {"7": "A1", "9": "A2"}  # coupon order; 5 has no section
    assert "A1" in analysis_ref_label(refs, 7) and analysis_ref_label(refs, 5) == ""
    assert analysis_appendix_flowables({}, store, small, small) == []
    flow = analysis_appendix_flowables(refs, store, small, small)
    text = " ".join(getattr(f, "text", "") for f in flow)
    # the newest of each author, analyst first; escaped, bold, table cells
    assert text.index("analityk") < text.index("weryfikator")
    assert "<b>Dossier.</b> forma &amp; tabela" in text and "1 · &lt;2&gt;" in text


def test_md_paragraphs_keep_lines_and_drop_table_rules() -> None:
    out = md_paragraphs("## H\nline one\nline `two`\n\n|a|b|\n|:-|-:|\n|c|d|")
    assert out == ["<b>H</b>", "line one<br/>line two", "a · b<br/>c · d"]


def test_report_check_names_a_read_match_without_its_token() -> None:
    text = report(
        [read(101), read(303)],
        SECTION_A + "### Olympiacos – Kalamata\nKontekst (web): nic\n",
    )
    found = [f for f in findings(text) if f.startswith("SEKCJA BEZ TOKENU")]
    assert len(found) == 1 and "303" in found[0] and "101" not in found[0]


def test_a_delta_section_never_restarts_the_full_pass_clock() -> None:
    """A re-read's delta section (it cites "[wcześniej: ...]") is the newest
    section, yet the 6 h clock of the context pass counts from the last full
    pass; a section with no web source is no full pass either."""
    full = {
        "author": "analyst",
        "recorded_at_utc": "2026-10-26T08:00:00+00:00",
        "context_pass": True,
        "web_tags": 3,
        "delta": False,
    }
    delta = {
        "author": "analyst",
        "recorded_at_utc": "2026-10-26T12:00:00+00:00",
        "context_pass": True,
        "web_tags": 1,
        "delta": True,
    }
    bare = {
        "author": "analyst",
        "recorded_at_utc": "2026-10-26T13:00:00+00:00",
        "context_pass": True,
        "web_tags": 0,
        "delta": False,
    }
    verifier = {
        "author": "verifier",
        "recorded_at_utc": "2026-10-26T14:00:00+00:00",
        "context_pass": True,
        "web_tags": 5,
        "delta": False,
    }
    store = {"events": {"7": [verifier, bare, delta, full]}}
    assert analyses.full_pass_at(store, 7) == "2026-10-26T08:00:00+00:00"
    assert analyses.full_pass_at({"events": {"7": [delta]}}, 7) is None
    text = "### A - B · sofa:7\n**Dossier.** [wcześniej: r1.md, 08:00Z]\n"
    assert analyses.split_sections(text)[0]["delta"] is True


def test_a_report_heading_citing_a_match_is_never_its_section() -> None:
    """2026-10-25 hockey r3: "## Nagłówek" cited `sofa:16340931` in its first
    bullet and was filed as a second analysis of SC Bern - Lugano; a
    "## Zdjęte" line after the section became the newest entry (the PDF
    appendix and prior_analysis then pointed at it)."""
    text = (
        "## Nagłówek\n- 8 nóg z meczu SC Bern - Lugano, `sofa:7`.\n\n"
        "### SC Bern – Lugano · sofa:7\n**Kontekst (web).** nic\n"
        "#### Kontekst (web)\n- inny mecz sofa:8 też grał wczoraj\n\n"
        "## Zdjęte\n- SC Bern - Lugano (sofa:7) WATCH\n\n"
        "## Uwagi\n**Sofascore:** `sofa:9`\ntreść\n"
    )
    found = analyses.split_sections(text)
    assert [(s["event_id"], s["heading"]) for s in found] == [
        (7, "SC Bern – Lugano"),
        (9, "Uwagi"),
    ]
    assert "inny mecz" in found[0]["markdown"]


def test_headings_in_a_fence_and_crlf_do_not_cut_a_section() -> None:
    text = (
        "### A – B · sofa:1\r\nlinia\r\n```\r\n## nie nagłówek\r\n```\r\n"
        "dalej\r\n### C – D · sofa:2\r\nx\r\n"
    )
    found = analyses.split_sections(text)
    assert [s["event_id"] for s in found] == [1, 2]
    assert "dalej" in found[0]["markdown"] and found[0]["heading"] == "A – B"
    assert "\r" not in found[0]["markdown"]


def test_one_reports_sections_of_a_match_keep_their_order(tmp_path: Path) -> None:
    path = tmp_path / "2026-10-26_analiza_football.md"
    path.write_text("### A – B · sofa:1\npierwsza\n\n### A – B (2) · sofa:1\ndruga\n")
    store: dict[str, Any] = {
        "events": {"1": [{"author": "analyst", "report": "old.md"}]}
    }
    analyses.add_report(store, path, "analyst", T8)
    assert [e["report"] for e in store["events"]["1"]] == [
        path.name,
        path.name,
        "old.md",
    ]
    assert "pierwsza" in store["events"]["1"][0]["markdown"]


def test_a_hand_edited_store_loads_without_its_broken_entries(tmp_path: Path) -> None:
    (tmp_path / analyses.STORE).write_text(
        json.dumps(
            {"events": {"1": [{"author": "analyst"}, "x", 3], "2": "zły", "3": None}}
        )
    )
    assert analyses.load(tmp_path)["events"] == {"1": [{"author": "analyst"}]}


def test_the_read_cell_is_bounded_however_many_long_reads() -> None:
    """A table row never splits across a page: three 600-character reads on
    one leg overflowed the frame and reportlab refused the whole coupon PDF
    (LayoutError). Past READ_CELL_CHARS a read shows its verdict line only."""
    reason = "bardzo długi powód z kontekstem; " * 30
    leg = {
        "reads": [
            {"verdict": "KEEP", "author": a, "reason": reason}
            for a in ("analyst", "verifier") * 4
        ]
    }
    label = read_label(leg)
    text = re.sub(r"<[^>]+>", "", label)
    assert label.count("<br/>") == 8
    assert len(text) < READ_CELL_CHARS + 8 * 60


def test_the_inlined_page_data_survives_any_markup_in_a_section() -> None:
    """`<!--` in an analyst's markdown made the escape "<\\!--" - no JSON
    escape - and JSON.parse blanked the page."""
    view = {"meta": {"analyses": {"1": [{"markdown": "<!-- x --> </script> <b>"}]}}}
    page = render_html("2026-10-26", view)
    blob = (
        page.split('type="application/json"', 1)[1]
        .split(">", 1)[1]
        .split("</script>", 1)[0]
    )
    assert "<" not in blob
    assert (
        json.loads(blob)["meta"]["analyses"]["1"][0]["markdown"]
        == "<!-- x --> </script> <b>"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_markdown_renderer_never_stalls(tmp_path: Path) -> None:
    """An indented "  ## x" line matched neither the heading branch nor the
    paragraph loop, and md() spun forever when a section was unfolded."""
    tpl = (
        Path(analyses.__file__).parent / "templates" / "coupon_view.html"
    ).read_text()
    lines = tpl.split("\n")
    esc = next(x for x in lines if x.startswith("const esc="))
    s = next(i for i, x in enumerate(lines) if x.startswith("function inl"))
    e = next(i for i in range(s, len(lines)) if lines[i].strip() == "return h}")
    cases = [
        "text\\n  ## indented",
        "    # bash\\nx",
        "a\\n```\\n## f\\n<b>\\n```\\nb",
        "| a | b |\\n|---|---|\\n| 1 | 2 |",
        "open\\n```\\nrest",
    ]
    js = tmp_path / "md.js"
    js.write_text(
        "\n".join(
            [
                esc,
                *lines[s : e + 1],
                f"for (const c of {json.dumps(cases)}) "
                "console.log(JSON.stringify(md(c.replace(/\\\\n/g, '\\n'))));",
            ]
        )
    )
    out = subprocess.run(
        ["node", str(js)], capture_output=True, text=True, timeout=10, check=True
    ).stdout.splitlines()
    assert len(out) == len(cases)
    assert "&lt;b&gt;" in out[2] and "<pre>" in out[2] and "<table>" in out[3]


def test_a_rebuild_never_takes_a_chat_slips_reports(tmp_path: Path) -> None:
    """merge_reads --slip leaves slip reports out of analyses.json; a rebuild
    from disk took them in (10-20..10-25: 39 files, 82 sections) and they,
    being the newest, became the appendix's and prior_analysis's section."""
    day = "2026-10-26"
    for name in (f"{day}_analiza_football.md",
                 f"{day}_analiza_football_kupon_1400_1.md",
                 f"{day}_weryfikacja.md"):
        (tmp_path / name).write_text("x")
    assert [p.name for p in analyses.report_files(tmp_path, day)] == sorted(
        [f"{day}_analiza_football.md", f"{day}_weryfikacja.md"],
        key=lambda n: ((tmp_path / n).stat().st_mtime, n))


def test_a_reread_after_a_delta_still_points_at_the_full_pass() -> None:
    """The third read of a match: the newest section is a delta ("[wcześniej:
    ...]" plus what changed); prior_analysis must also name the full pass,
    or the analyst reads a section with no dossier and no context in it. A
    full pass that honestly ends UNVERIFIED (an ITF match) is one."""
    full = {"author": "analyst", "report": "r1.md", "recorded_at_utc": T8,
            "context_pass": True, "web_tags": 0, "delta": False,
            "markdown": "Kontekst (web): skład UNVERIFIED"}
    delta = {"author": "analyst", "report": "r2.md", "recorded_at_utc": T12,
             "context_pass": True, "web_tags": 1, "delta": True, "markdown": ""}
    store = {"events": {"5": [delta, full]}}
    assert analyses.full_pass(store, 5)["report"] == "r1.md"
    assert analyses.latest(store, 5, "analyst")["report"] == "r2.md"


def test_the_pdf_points_only_at_matches_its_appendix_prints() -> None:
    store = {"events": {"1": [{"author": "analyst"}], "2": [], "3": [{"author": "x"}]}}
    legs = [{"sofascore_event_id": e} for e in (3, 2, 1)]
    assert analysis_refs(legs, [], store) == {"1": "A1"}


def test_the_hook_and_the_store_read_the_token_alike() -> None:
    """A token on a report heading ("## Zdjęte · sofa:1") files nothing, so
    the hook must not count it as the match's section."""
    body = "## Zdjęte · sofa:1\nbrak\n"
    assert any("SEKCJA BEZ TOKENU" in f for f in findings(report([read(1)], body)))
    good = "### A – B · sofa:1\n**Kontekst (web).** nic\n"
    assert not any("SEKCJA BEZ TOKENU" in f for f in findings(report([read(1)], good)))
