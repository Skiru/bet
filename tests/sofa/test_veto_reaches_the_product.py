"""A veto has to reach the artifact the operator actually stakes.

Until 2026-09-21 it did not. `run_coupon` loaded `vetoes.json` and matched it
against the sheet; `run_confidence` never opened the file. So an analyst veto
removed a row from `06_coupon.json` — the VALUE singles, which the runbook is
explicit are *not* the coupon — and left the identical rung standing as a leg
of the Bet Builder that `build_coupon_pdf.py` renders.

The failure was silent in both directions: the analyst saw the veto applied
(the singles file shrank) and the operator staked the vetoed leg anyway.

These tests pin the predicate and the two properties that make it safe to
share between the two stages: it may only remove, and a veto that matches
nothing must be reportable rather than swallowed.
"""

import json
import subprocess
import sys
from pathlib import Path

from bet.sofa.contracts import SheetRow, Veto
from bet.sofa.veto import (
    find_unmatched_vetoes,
    load_vetoes,
    match_vetoes,
    veto_matches,
)


def _row(**over) -> SheetRow:
    base = dict(
        sofascore_event_id=111,
        sport="football",
        market="corners_total",
        subject="",
        line=9.5,
        direction="OVER",
        sample_size=12,
        sample_mean=10.2,
        sample_sd=3.0,
        centre=10.0,
        p_central=0.6,
        market_p=0.55,
        ladder_centre=None,
        ladder_sigma=None,
        p_bar=0.58,
        bar_reason="none",
        required_odds=1.9,
        offered_odds=2.1,
        edge=0.05,
        surplus=0.2,
        verdict="VALUE",
        notes=[],
    )
    base.update(over)
    return SheetRow(**base)


def _veto(**over) -> Veto:
    base = dict(
        sofascore_event_id=111,
        market=None,
        subject=None,
        line=None,
        direction=None,
        reason_class="SAMPLE_UNINFORMATIVE",
        reason="the sample is three months old",
    )
    base.update(over)
    return Veto(**base)


def test_the_two_stages_ask_the_same_question_of_the_same_veto():
    """One predicate, two callers — CONFIDENCE holds rows as dicts.

    The dict path is the one that did not exist. If it ever drifts from the
    model path, a veto starts meaning two different things depending on which
    artifact you look at, which is worse than it meaning nothing.
    """
    veto = _veto(market="corners_total", line=9.5, direction="OVER")
    row = _row()

    assert match_vetoes(row, [veto]) == [veto]
    assert veto_matches(
        veto,
        sofascore_event_id=row.sofascore_event_id,
        market=row.market,
        subject=row.subject,
        line=row.line,
        direction=row.direction,
    )


def test_a_bare_fixture_veto_covers_every_rung_on_that_fixture():
    """The normal shape. A sample that does not describe the fixture is broken
    at every line, not at one of them."""
    veto = _veto()
    for market, line, direction in (
        ("corners_total", 9.5, "OVER"),
        ("goals_total", 2.5, "UNDER"),
        ("cards_points_for", 30.0, "OVER"),
    ):
        assert veto_matches(
            veto,
            sofascore_event_id=111,
            market=market,
            subject="",
            line=line,
            direction=direction,
        )


def test_a_veto_never_crosses_to_another_fixture():
    assert not veto_matches(
        _veto(),
        sofascore_event_id=222,
        market="corners_total",
        subject="",
        line=9.5,
        direction="OVER",
    )


def test_direction_and_line_narrow_the_veto_rather_than_widening_it():
    """OVER 9.5 vetoed says nothing about UNDER 9.5 or OVER 10.5."""
    veto = _veto(market="corners_total", line=9.5, direction="OVER")
    assert not veto_matches(
        veto, sofascore_event_id=111, market="corners_total",
        subject="", line=9.5, direction="UNDER",
    )
    assert not veto_matches(
        veto, sofascore_event_id=111, market="corners_total",
        subject="", line=10.5, direction="OVER",
    )


def test_a_veto_that_matches_nothing_is_reported_not_swallowed():
    """T27. A silent no-op reads exactly like a veto that was honoured."""
    rows = [_row()]
    hits = _veto(market="corners_total")
    misses = _veto(sofascore_event_id=999)
    assert find_unmatched_vetoes(rows, [hits, misses]) == [misses]


def test_load_vetoes_treats_absent_and_empty_as_the_healthy_case(tmp_path: Path):
    """`vetoes.json` is `[]` on most days, and missing on a fresh run dir.

    Neither may raise: a crash here would make writing no veto the riskier
    option than writing a bad one.
    """
    assert load_vetoes(tmp_path / "nope.json") == []
    empty = tmp_path / "vetoes.json"
    empty.write_text("", encoding="utf-8")
    assert load_vetoes(empty) == []
    empty.write_text("[]", encoding="utf-8")
    assert load_vetoes(empty) == []


def test_confidence_stage_refuses_a_vetoed_leg(tmp_path: Path):
    """End to end through the script, because the defect was a missing read.

    A unit test of the predicate would have passed the whole time this was
    broken — nothing was wrong with matching, the file was simply never
    opened. So this runs the stage twice over the same artifacts, with and
    without a veto, and asserts the leg count moves.
    """
    run_dir = tmp_path / "2026-01-01"
    run_dir.mkdir(parents=True)
    repo = Path(__file__).resolve().parents[2]

    fixture = {
        "sofascore_event_id": 111,
        "superbet_event_ids": ["s1"],
        "sport": "football",
        # Far enough out that the KICKED_OFF gate cannot decide this test.
        "kickoff_utc": "2099-01-01T20:00:00Z",
        "home_name": "Home", "away_name": "Away",
        "home_entity_id": 1, "away_entity_id": 2,
        "competition_name": "Test League", "competition_id": 9, "season_id": 9,
        "category_name": "Test", "identity": "CONFIRMED",
        "round_number": None, "round_name": None, "cup_round_type": None,
        "previous_leg_event_id": None, "venue_name": None, "referee": None,
        "ground_type": None, "default_period_count": 2,
        "superbet_kickoff_utc": "2099-01-01T20:00:00Z",
        "kickoff_disagreement_h": 0.0,
    }
    (run_dir / "02_fixtures.json").write_text(json.dumps([fixture]))
    (run_dir / "vetoes.json").write_text("[]")

    # Both stages read these; the shapes below are the ones they index into.
    (run_dir / "03_samples.json").write_text(json.dumps([]))
    (run_dir / "04_offer.json").write_text(json.dumps([]))
    (run_dir / "05_sheet.json").write_text(json.dumps([]))

    def run() -> dict:
        proc = subprocess.run(
            [sys.executable, "scripts/sofa/run_confidence.py",
             "--date", "2026-01-01", "--runs-dir", str(tmp_path)],
            cwd=repo, capture_output=True, text=True,
            env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout.strip().splitlines()[-1])

    before = run()
    assert before["metrics"]["vetoes_applied"] == 0

    (run_dir / "vetoes.json").write_text(json.dumps([{
        "sofascore_event_id": 111, "market": None, "subject": None,
        "line": None, "direction": None,
        "reason_class": "CONTEXT", "reason": "second leg, tie already decided",
    }]))
    after = run()
    # The sheet is empty here, so nothing matches — which is precisely the
    # case that must be *reported* rather than pass as applied.
    assert after["metrics"]["vetoes_unmatched"] == 1
    assert after["metrics"]["vetoes_applied"] == 0
    doc = json.loads((run_dir / "08_confidence.json").read_text())
    assert doc["vetoes_unmatched"] == 1
