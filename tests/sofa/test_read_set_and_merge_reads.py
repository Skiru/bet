"""read_set.py hands the analysts C3's read set per sport (plus a buffer, or
only the unread legs), and merge_reads.py merges their reports into
vetoes.json / reads.json - the deterministic halves of /sofa-day steps 5-6
that used to be Python pasted into the prompts (2026-10-19)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import READ_REQUIRED_EVENTS, legs_requiring_read
from scripts.sofa import merge_reads, read_set
from scripts.sofa.build_coupon import assemble


def leg(eid: int, conf: float, odds: float, sport: str = "football",
        line: float = 5.5) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "confidence": conf, "sport": sport,
            "kickoff_utc": "2026-10-14T20:00:00Z", "market": "corners_total",
            "subject": "", "line": line, "direction": "OVER",
            "offered_odds": odds, "match": f"M{eid}", "display_market": "c"}


def day(tmp_path: Path, singles: list[dict[str, Any]]) -> Path:
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": []}
    doc = assemble(conf, None, [], {}, "now", "2026-10-14", read_events=True,
                   read_value_order=True)
    run = tmp_path / "2026-10-14"
    run.mkdir()
    (run / "11_coupon.json").write_text(json.dumps(doc))
    return run


def read(eid: int, verdict: str = "KEEP", author: str = "analyst",
         line: float = 5.5) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "market": "corners_total", "subject": "",
            "line": line, "direction": "OVER", "verdict": verdict,
            "author": author, "reason": "r"}


def test_the_read_set_is_c3s_split_by_sport(tmp_path: Path) -> None:
    singles = [leg(e, 0.80, 1.25) for e in range(1, 41)]
    singles += [leg(100, 0.75, 1.30, sport="hockey")]
    run = day(tmp_path, singles)
    doc = json.loads((run / "11_coupon.json").read_text())
    sets = read_set.read_set(run)
    assert sum(len(v) for v in sets.values()) == len(legs_requiring_read(doc))
    matches = {x["group_key"] for v in sets.values() for x in v}
    assert len(matches) == READ_REQUIRED_EVENTS
    assert all(x["in_set"] == "required" for v in sets.values() for x in v)


def test_a_buffer_adds_the_next_matches_in_read_order(tmp_path: Path) -> None:
    run = day(tmp_path, [leg(e, 0.80 - e * 0.001, 1.25) for e in range(1, 41)])
    sets = read_set.read_set(run, buffer=5)["football"]
    buffered = [x for x in sets if x["in_set"] == "buffer"]
    assert len({x["group_key"] for x in buffered}) == 5
    # the best value first: the required matches are 1..30, the buffer 31..35
    assert {x["sofascore_event_id"] for x in buffered} == set(range(31, 36))


def test_unread_drops_legs_an_analyst_read_and_keeps_verifier_only_ones(
        tmp_path: Path) -> None:
    run = day(tmp_path, [leg(e, 0.80, 1.25) for e in range(1, 4)])
    (run / "reads.json").write_text(json.dumps(
        [read(1), read(2, "WATCH", author="verifier")]))
    unread = read_set.read_set(run, unread=True)["football"]
    left = {x["sofascore_event_id"] for x in unread}
    assert left == {2, 3}


def test_read_set_cli_writes_one_file_per_sport_and_clears_stale_ones(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = day(tmp_path, [leg(1, 0.80, 1.25), leg(2, 0.8, 1.3, sport="tennis")])
    out = tmp_path / "out"
    out.mkdir()
    (out / "read_set_cs2.json").write_text("[]")
    assert read_set.main(["--date", run.name, "--runs-dir", str(tmp_path),
                          "--out-dir", str(out), "--no-h2h", "--no-lineups"]) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "read_set_football.json", "read_set_tennis.json"]
    assert "football: 1 legs, 1 matches" in capsys.readouterr().out


def test_split_writes_whole_matches_per_part(tmp_path: Path) -> None:
    run = day(tmp_path, [leg(e, 0.80, 1.25, line=x) for e in range(1, 6)
                         for x in (5.5, 6.5)])
    out = tmp_path / "out"
    assert read_set.main(["--date", run.name, "--runs-dir", str(tmp_path),
                          "--out-dir", str(out), "--split", "2"]) == 0
    files = sorted(out.iterdir())
    assert [p.name for p in files] == [f"read_set_football_{i}.json" for i in (1, 2, 3)]
    per_file = [{x["group_key"] for x in json.loads(p.read_text())} for p in files]
    assert [len(m) for m in per_file] == [2, 2, 1]
    assert not set.intersection(*per_file)


REPORT = """# Analiza

tekst

```json vetoes
[{"sofascore_event_id": 1, "market": null, "subject": null, "line": null,
  "direction": null, "reason_class": "OTHER", "reason": "zly mecz"}]
```

```json reads
[{"sofascore_event_id": 2, "market": "corners_total", "subject": "",
  "line": 5.5, "direction": "OVER", "verdict": "WATCH", "author": "analyst",
  "reason": "r"}]
```
"""


def test_parse_report_reads_labelled_and_unlabelled_arrays() -> None:
    vetoes, reads = merge_reads.parse_report(REPORT)
    assert len(vetoes) == 1 and len(reads) == 1
    # two passes saved into one file, unlabelled: classified by their entries
    two = REPORT.replace("json vetoes", "json").replace("json reads", "json")
    vetoes, reads = merge_reads.parse_report(two + two)
    assert len(vetoes) == 2 and len(reads) == 2
    with pytest.raises(merge_reads.ReportError):
        merge_reads.parse_report(REPORT.replace("json vetoes", "json reads"))
    with pytest.raises(merge_reads.ReportError):
        merge_reads.parse_report("no arrays here")
    # a block indented inside a list, a label with a note, CRLF: all read
    indented = "- weto:\n  ```json vetoes (pass 2)\n  " + REPORT.split(
        "```json vetoes\n")[1].split("```")[0].replace("\n", "\n  ") + "```\n"
    vetoes, _ = merge_reads.parse_report(indented.replace("\n", "\r\n"))
    assert len(vetoes) == 1
    # a ```json opening that never closes refuses the whole report
    with pytest.raises(merge_reads.ReportError):
        merge_reads.parse_report(REPORT + "\n```json reads\n[]\n")


def test_merge_appends_carries_over_and_validates_before_writing(
        tmp_path: Path) -> None:
    run = tmp_path / "2026-10-14"
    run.mkdir()
    earlier = [read(3, "NO_BET", author="verifier")]
    (run / "reads.json").write_text(json.dumps(earlier))
    report = tmp_path / "football.md"
    report.write_text(REPORT)
    args = ["--date", run.name, "--runs-dir", str(tmp_path), "--report", str(report)]
    assert merge_reads.main([*args, "--author", "analyst"]) == 0
    reads = json.loads((run / "reads.json").read_text())
    assert reads[0] == earlier[0] and len(reads) == 2
    assert len(json.loads((run / "vetoes.json").read_text())) == 1
    # a repeat merges nothing new
    assert merge_reads.main(args) == 0
    assert len(json.loads((run / "reads.json").read_text())) == 2
    # a wrong author or an invalid entry is refused and writes nothing
    assert merge_reads.main([*args, "--author", "verifier"]) == 2
    bad = tmp_path / "bad.md"
    bad.write_text(REPORT.replace('"verdict": "WATCH"', '"verdict": "MAYBE"'))
    before = (run / "reads.json").read_text()
    assert merge_reads.main(["--date", run.name, "--runs-dir", str(tmp_path),
                             "--report", str(bad)]) == 2
    assert (run / "reads.json").read_text() == before


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    run = tmp_path / "2026-10-14"
    run.mkdir()
    report = tmp_path / "r.md"
    report.write_text(REPORT)
    assert merge_reads.main(["--date", run.name, "--runs-dir", str(tmp_path),
                             "--report", str(report), "--dry-run"]) == 0
    assert not (run / "reads.json").exists() and not (run / "vetoes.json").exists()


def test_unmatched_veto_exit_counts_fresh_ones_and_spares_sport_games(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "2026-10-14"
    run.mkdir()
    (run / "05_sheet.json").write_text("[]")
    monkeypatch.setattr(merge_reads, "find_unmatched_vetoes",
                        lambda rows, vetoes: list(vetoes))
    monkeypatch.setattr(merge_reads, "sport_event_ids", lambda run: {77})
    veto = {"sofascore_event_id": 77, "market": None, "subject": None,
            "line": None, "direction": None, "reason_class": "OTHER",
            "reason": "sport"}
    report = tmp_path / "s.md"
    report.write_text("```json vetoes\n" + json.dumps([veto]) + "\n```\n")
    args = ["--date", run.name, "--runs-dir", str(tmp_path), "--report", str(report)]
    # a veto on a measured-sport game acts (COUPON_ASSEMBLY): not unmatched
    assert merge_reads.main(args) == 0
    # a fresh veto that hits nothing: exit 1; once carried over, only listed
    other = tmp_path / "o.md"
    other.write_text(report.read_text().replace("77", "5"))
    assert merge_reads.main(["--date", run.name, "--runs-dir", str(tmp_path),
                             "--report", str(other)]) == 1
    third = tmp_path / "t.md"
    third.write_text(REPORT.split("```json reads")[0].replace('"zly mecz"', '"x"')
                     .replace("1,", "77,"))
    assert merge_reads.main(["--date", run.name, "--runs-dir", str(tmp_path),
                             "--report", str(third)]) == 0
