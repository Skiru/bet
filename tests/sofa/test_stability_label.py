"""The analyst's stability label (epochs.STABILITY_LABEL_FROM_UTC, operator
2026-11-16): the read field, the report rule, its display and its accounting,
and the retro measurement script (T-STABILITY-LABEL-RETRO / -FORWARD)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from bet.sofa import epochs, report_check
from bet.sofa.contracts import LegRead
from bet.sofa.coupon_html import read_notes
from bet.sofa.slip_builder import read_column, read_stability
from bet.sofa.veto import leg_stability, read_note, stability_note
from scripts.sofa import measure_stability_label as msl
from scripts.sofa.build_coupon_pdf import read_label, stability_label
from scripts.sofa.merge_reads import BLOCKING_FINDINGS

READ = {"sofascore_event_id": 1, "market": "goals_total", "subject": "",
        "line": 2.5, "direction": "UNDER", "verdict": "KEEP", "author": "analyst",
        "reason": "oczekuję 2.1 gola; obie strony 8/10 poniżej"}


def _read(**kw: Any) -> LegRead:
    return LegRead.model_validate({**READ, **kw})


# ------------------------------------------------------------------ contract

def test_read_takes_stability_with_a_reason() -> None:
    r = _read(stability="CHWIEJNA", stability_reason="trzy porażki z rzędu")
    assert r.stability == "CHWIEJNA"
    assert _read().stability is None  # optional: older reads still validate


@pytest.mark.parametrize("kw", [
    {"stability": "CHWIEJNA"},                           # no reason
    {"stability": "CHWIEJNA", "stability_reason": " "},  # blank reason
    {"stability_reason": "bez etykiety"},                # reason alone
    {"stability": "SHAKY", "stability_reason": "x"},     # unknown label
])
def test_read_refuses_a_broken_stability(kw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _read(**kw)


def test_read_note_carries_stability() -> None:
    note = read_note(_read(stability="STABILNA", stability_reason="skład pewny"))
    assert note["stability"] == "STABILNA"
    assert note["stability_reason"] == "skład pewny"
    assert "stability" not in read_note(_read())


def test_shaky_wins_and_none_is_dash() -> None:
    leg = {"reads": [
        {"verdict": "KEEP", "stability": "STABILNA", "stability_reason": "a",
         "read_at_utc": "2026-11-16T10:00:00+00:00"},
        {"verdict": "KEEP", "stability": "CHWIEJNA", "stability_reason": "b",
         "read_at_utc": "2026-11-16T09:00:00+00:00"},
    ]}
    assert leg_stability(leg) == "CHWIEJNA"
    assert stability_note(leg["reads"]) == ("CHWIEJNA", "b")
    assert leg_stability({"reads": [{"verdict": "KEEP"}]}) == "-"
    assert stability_note([]) is None


# ------------------------------------------------------------------ the rule

def _report(reads: list[dict[str, Any]]) -> str:
    return "```json reads\n" + json.dumps(reads, ensure_ascii=False) + "\n```\n"


def test_stability_findings_name_every_read_without_it() -> None:
    ok = {**READ, "stability": "STABILNA", "stability_reason": "skład pewny"}
    bare = {**READ, "line": 3.5}
    no_reason = {**READ, "line": 4.5, "stability": "CHWIEJNA"}
    found = report_check.stability_findings([ok, bare, no_reason])
    assert len(found) == 2
    assert found[0].startswith("STABILNOŚĆ:") and "3.5" in found[0]
    assert found[1].startswith("STABILNOŚĆ BEZ POWODU")
    assert all(f.startswith(BLOCKING_FINDINGS) for f in found)  # merge refuses


def test_findings_require_stability_only_when_asked() -> None:
    text = _report([READ])
    assert not [f for f in report_check.findings(text, stability=False)
                if f.startswith("STABILNOŚĆ")]
    assert [f for f in report_check.findings(text, stability=True)
            if f.startswith("STABILNOŚĆ")]


def test_required_from_the_switch_clock_and_day(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "STABILITY_LABEL_FROM_UTC",
                        datetime(2026, 11, 16, 17, 0, tzinfo=UTC))
    before = datetime(2026, 11, 16, 16, 59, tzinfo=UTC)
    after = datetime(2026, 11, 16, 17, 0, tzinfo=UTC)
    assert not report_check.stability_required("2026-11-16", before)
    assert report_check.stability_required("2026-11-16", after)
    # an older day's report re-merged keeps its rules; a nameless report too
    assert not report_check.stability_required("2026-11-15", after)
    assert not report_check.stability_required(None, after)
    monkeypatch.setattr(epochs, "STABILITY_LABEL_FROM_UTC", None)
    assert not report_check.stability_required("2026-11-20", after)


def test_removal_switch_is_off() -> None:
    # a CHWIEJNA read removes nothing until the operator's go
    assert epochs.STABILITY_REMOVAL_FROM_UTC is None
    assert not epochs.stability_removal(datetime(2030, 1, 1, tzinfo=UTC))


# ------------------------------------------------------------------ display

def test_pdf_label_shows_stability() -> None:
    leg = {"reads": [{"verdict": "KEEP", "author": "analyst", "reason": "ok",
                      "stability": "CHWIEJNA",
                      "stability_reason": "Brute przegrał serię dzień wcześniej"}]}
    out = read_label(leg)
    assert "chwiejna" in out and "Brute" in out
    assert stability_label([{"verdict": "KEEP"}]) == ""


def test_html_notes_carry_stability() -> None:
    leg = {"reads": [{"verdict": "KEEP", "author": "analyst", "reason": "ok",
                      "stability": "STABILNA", "stability_reason": "pewny skład"}]}
    assert read_notes(leg)[0]["stability"] == "STABILNA"
    assert "stability" not in read_notes({"reads": [{"verdict": "KEEP"}]})[0]
    page = (Path(__file__).resolve().parents[2]
            / "src/bet/sofa/templates/coupon_view.html").read_text(encoding="utf-8")
    assert 'id="shaky"' in page and 'id="stable"' in page and "HASSTAB" in page


def test_slip_column_shows_stability() -> None:
    leg = {"sofascore_event_id": 1, "market": "goals_total", "subject": "",
           "line": 2.5, "direction": "UNDER", "sport": "football"}
    st = read_stability(leg, [], [_read(stability="CHWIEJNA",
                                        stability_reason="nowy trener | rotacja")])
    assert st == ("CHWIEJNA", "nowy trener | rotacja")
    cell = read_column("KEEP", st)
    assert cell.startswith("KEEP · chwiejna: nowy trener / rotacja")
    assert "|" not in cell  # a md table cell
    assert read_column("KEEP", None) == "KEEP"
    assert read_stability(leg, [], [_read(line=3.5, stability="STABILNA",
                                          stability_reason="x")]) is None


# ------------------------------------------------------------------ retro script

def _day(tmp: Path, day: str, *, recorded: str, kickoff: str,
         outcome: str = "WIN") -> None:
    dd = tmp / day
    dd.mkdir(parents=True)
    leg = {"sofascore_event_id": 1, "sport": "football", "market": "goals_total",
           "subject": "", "line": 2.5, "direction": "UNDER", "offered_odds": 1.25,
           "confidence": 0.8, "kickoff_utc": kickoff,
           "superbet_market": "Liczba goli", "superbet_selection": "poniżej 2.5"}
    (dd / "11_coupon.json").write_text(json.dumps({"singles": [leg]}))
    (dd / "analyses.json").write_text(json.dumps({"version": 1, "events": {"1": [
        {"author": "analyst", "recorded_at_utc": recorded,
         "markdown": "### A – B · sofa:1\n**W skrócie:** spokojny mecz"}]}}))
    (dd / "reads.json").write_text(json.dumps([{**READ, "read_at_utc": recorded}]))
    key = json.dumps([1, "goals_total", "", 2.5, "UNDER"])
    (dd / "13_results.json").write_text(json.dumps({"legs": {key: {
        "outcome": outcome, "odds": 1.25, "confidence": 0.8, "sport": "football"}}}))


def test_build_input_is_blind(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _day(runs, "2026-11-10", recorded="2026-11-10T10:00:00+00:00",
         kickoff="2026-11-10T19:00:00Z")
    out = tmp_path / "out" / "input"
    assert msl.build_input(str(runs), ["2026-11-10"], out, 2) == 0
    text = "".join(p.read_text() for p in out.glob("shard_*.jsonl"))
    rec = json.loads(text.strip().splitlines()[0])
    assert rec["legs"][0]["superbet"] == "Liczba goli: poniżej 2.5"
    assert "WIN" not in text and "outcome" not in text  # no result leaks
    pairs = (out.parent / "pairs.jsonl").read_text()
    assert json.loads(pairs)["leg_id"] == rec["legs"][0]["leg_id"]


def test_section_after_kickoff_is_dropped(tmp_path: Path) -> None:
    _day(tmp_path, "2026-11-10", recorded="2026-11-10T19:00:00+00:00",
         kickoff="2026-11-10T19:00:00Z")
    ps, skipped = msl.pairs(str(tmp_path), ["2026-11-10"])
    assert ps == [] and skipped["section_at_or_after_kickoff"] == 1


def _rows(label: str, wins: int, n: int, half: str, odds: float = 1.25,
          start: int = 0) -> list[dict[str, Any]]:
    return [{"day": "d", "event": start + i, "label": label, "win": i < wins,
             "odds": odds, "conf": 0.8, "half": half} for i in range(n)]


def test_verdict_rule_a5() -> None:
    # shaky clearly below stable in both halves, enough shaky legs: PASSED
    hold = (_rows("CHWIEJNA", 100, 200, "holdout")
            + _rows("STABILNA", 380, 400, "holdout", start=1000))
    dev = (_rows("CHWIEJNA", 70, 100, "dev")
           + _rows("STABILNA", 90, 100, "dev", start=1000))
    v = msl.verdict(dev, hold)
    assert v["verdict"] == "PASSED" and v["holdout_ci"][1] < 0
    assert v["removal_may_be_proposed"]
    # too few shaky legs on the hold-out: NOT_PASSED whatever the gap
    small = _rows("CHWIEJNA", 50, 100, "holdout") + _rows("STABILNA", 380, 400,
                                                          "holdout", start=1000)
    assert msl.verdict(dev, small)["verdict"] == "NOT_PASSED"
    # dev of the other sign: NOT_PASSED
    dev_up = (_rows("CHWIEJNA", 99, 100, "dev")
              + _rows("STABILNA", 50, 100, "dev", start=1000))
    assert msl.verdict(dev_up, hold)["verdict"] == "NOT_PASSED"


def test_band_and_stratified() -> None:
    assert msl.band(1.05) == "<1.10" and msl.band(1.30) == "1.30-1.60"
    rows = (_rows("CHWIEJNA", 5, 10, "holdout", odds=1.2)
            + _rows("STABILNA", 8, 10, "holdout", odds=1.2, start=100))
    d = msl.stratified(rows)
    assert d is not None and d == pytest.approx(msl.diff(rows))


def test_read_key_joins_sport_legs() -> None:
    leg = {"sofascore_event_id": 5, "sport": "hockey", "family": "total",
           "market": "total", "period": 2, "subject": "", "line": 1.5,
           "side": "UNDER", "direction": "UNDER"}
    read = {"sofascore_event_id": 5, "market": "total", "period": 2,
            "subject": "", "line": 1.5, "direction": "UNDER"}
    assert msl.leg_read_key(leg) == msl.read_key(read)
    assert msl.leg_read_key(leg) != msl.read_key({**read, "period": 3})


def test_forward_cut_and_rule_without_dev() -> None:
    shaky = _rows("CHWIEJNA", 150, 400, "holdout")
    stable = _rows("STABILNA", 380, 400, "holdout", start=1000)
    mixed = [r for pair in zip(shaky, stable, strict=True) for r in pair]
    rows = [{**r, "kickoff_utc": f"2026-11-17T00:00:{i:04d}"}
            for i, r in enumerate(mixed)]
    cut, reached = msl.forward_cut(rows, n=300)
    assert reached and sum(r["label"] == "CHWIEJNA" for r in cut) == 300
    assert not msl.forward_cut(rows[:100], n=300)[1]
    assert msl.verdict([], cut, require_dev=False)["verdict"] == "PASSED"
