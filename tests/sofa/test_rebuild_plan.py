"""The rebuild's plan (bet.sofa.rebuild_plan, scripts/sofa/rebuild_day.py).

Plan 2026-10-05 production grade, F0.2: "a rebuild on a stale offer
refreshes it instead of giving an empty coupon". On 2026-10-05 CONFIDENCE
ran on an offer past its 45-minute limit and emptied 08_confidence.json down
to the locked legs, and SHADOW's 3 h horizon left a 15:30Z hockey game on a
price that SPORT_CONFIDENCE then refused as stale.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from scripts.sofa import rebuild_day, run_shadow

DATE = "2026-10-05"
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
LIMIT = timedelta(minutes=45)


def z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def write_day(
    runs: Path,
    *,
    kickoff: datetime,
    fetched: datetime,
    sheet_epoch: str | None = epochs.STATS_ONLY,
    started: bool = False,
) -> None:
    run = runs / DATE
    run.mkdir(parents=True, exist_ok=True)
    (run / "02_fixtures.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "sport": "football",
        "kickoff_utc": z(kickoff), "superbet_kickoff_utc": z(kickoff),
    }]))
    (run / "04_offer.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "status": "PRICED",
        "superbet_started_utc": z(kickoff) if started else None,
        "superbet_kickoff_seen_utc": z(kickoff),
        "rungs": [{"market": "corners_total", "subject": "", "line": 9.5,
                   "over_odds": 1.9, "under_odds": 1.9,
                   "fetched_at_utc": z(fetched)}],
    }]))
    row: dict[str, Any] = {"sofascore_event_id": 1}
    if sheet_epoch is not None:
        row["epoch"] = sheet_epoch
    (run / "05_sheet.json").write_text(json.dumps([row]))
    (run / "sport_fixtures.json").write_text(json.dumps({"events": []}))
    (run / "06_coupon.json").write_text("{}")  # after the sheet: in step


def write_hockey(runs: Path, records: list[tuple[datetime, str, datetime]]) -> None:
    """(fetched_at, event id, kickoff) snapshot records of D's hockey file."""
    day = runs / "shadow" / "hockey" / DATE
    day.mkdir(parents=True, exist_ok=True)
    out = []
    for fetched, eid, kickoff in records:
        out.append(json.dumps({
            "fetched_at_utc": z(fetched), "superbet_event_id": eid,
            "match_name": "A·B", "team1": "A", "team2": "B",
            "kickoff_utc": z(kickoff), "tournament": "Extraliga",
            "lines": [{"superbet_event_id": eid, "market_id": 623,
                       "family": "total", "period": 0, "subject": "",
                       "line": 5.5, "side": side, "odds": 1.9}
                      for side in ("OVER", "UNDER")],
        }))
    (day / "snapshots.jsonl").write_text("\n".join(out) + "\n")


def plan_for(runs: Path, now: datetime = NOW, **kw: Any) -> rp.Plan:
    return rp.build_plan(rp.observe(str(runs), DATE, now, LIMIT), run_id="t", **kw)


def step(plan: rp.Plan, name: str) -> rp.Step:
    return next(s for s in plan.steps if s.name == name)


# --- the plan's criterion -----------------------------------------------------


def test_stale_offer_is_refreshed_before_confidence(tmp_path: Path) -> None:
    # The 10-05 shape: an open fixture whose price is 50 min old - CONFIDENCE
    # would refuse every rung (STALE_PRICE) and leave only the locked legs.
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=50))
    plan = plan_for(tmp_path)
    names = plan.names()
    assert "OFFER" in names
    assert names.index("OFFER") < names.index("CONFIDENCE")
    offer = step(plan, "OFFER")
    assert offer.argv[1:] == ("scripts/sofa/run_offer.py", "--date", DATE,
                              "--min-minutes-to-kickoff", "20")
    assert not offer.soft  # a failed refresh stops: no coupon on stale prices


def test_offer_inside_the_margin_is_refreshed_too(tmp_path: Path) -> None:
    # 35 min old is under the 45-min limit, but the rebuild takes minutes:
    # by the time CONFIDENCE runs it would be stale.
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=35))
    assert "OFFER" in plan_for(tmp_path).names()


def test_fresh_day_refreshes_nothing(tmp_path: Path) -> None:
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=5))
    write_hockey(tmp_path, [(NOW - timedelta(minutes=10), "1",
                             NOW + timedelta(hours=2))])
    plan = plan_for(tmp_path)
    assert {"OFFER", "SHADOW", "CS2", "SHEET", "SPORT_IDENTITY"}.isdisjoint(
        plan.names())
    assert plan.names() == [
        "BRIDGE", "FIXTURE_CHECK", "CONFIDENCE", "SPORT_CONFIDENCE",
        "COUPON_ASSEMBLY", "PDF", "AUDIT_VARIANTS", "AUDIT_COUPON"]
    assert any(n.startswith("OFFER fresh") for n in plan.notes)


def test_over_day_refreshes_no_price_and_says_so(tmp_path: Path) -> None:
    # Every match started: the prices are historical and must stay so.
    write_day(tmp_path, kickoff=NOW - timedelta(hours=2),
              fetched=NOW - timedelta(hours=3))
    write_hockey(tmp_path, [(NOW - timedelta(hours=6), "1",
                             NOW - timedelta(hours=1))])
    plan = plan_for(tmp_path)
    assert {"OFFER", "SHADOW", "CS2"}.isdisjoint(plan.names())
    assert any(n.startswith("DAY_OVER football/tennis") for n in plan.notes)
    assert any(n.startswith("DAY_OVER hockey") for n in plan.notes)
    assert "CONFIDENCE" in plan.names() and "PDF" in plan.names()


def test_superbet_started_fixture_is_not_open(tmp_path: Path) -> None:
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(hours=2), started=True)
    assert "OFFER" not in plan_for(tmp_path).names()


def test_fixture_inside_twenty_minutes_does_not_force_a_refresh(tmp_path: Path) -> None:
    # run_offer --min-minutes-to-kickoff 20 would not re-price it anyway.
    write_day(tmp_path, kickoff=NOW + timedelta(minutes=18),
              fetched=NOW - timedelta(hours=2))
    assert "OFFER" not in plan_for(tmp_path).names()


# --- the measured sports ----------------------------------------------------


def test_shadow_horizon_reaches_the_farthest_open_start(tmp_path: Path) -> None:
    # The 10-05 hockey case: the morning snapshot priced a 15:30Z game, the
    # 11:00Z snapshot (3 h horizon) skipped it as already on file - its price
    # is 6 h old at noon and SPORT_CONFIDENCE refuses it (STALE_PRICE).
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=5))
    late = datetime(2026, 10, 5, 15, 30, tzinfo=UTC)
    write_hockey(tmp_path, [
        (datetime(2026, 10, 5, 6, 0, tzinfo=UTC), "late", late),
        (datetime(2026, 10, 5, 11, 0, tzinfo=UTC), "soon",
         datetime(2026, 10, 5, 13, 0, tzinfo=UTC)),
    ])
    plan = plan_for(tmp_path)
    shadow = step(plan, "SHADOW")
    assert shadow.argv[1] == "scripts/sofa/run_shadow.py"
    horizon = float(shadow.argv[shadow.argv.index("--horizon-h") + 1])
    assert NOW + timedelta(hours=horizon) >= late
    assert shadow.soft
    names = plan.names()
    # a fresh snapshot is identified (bridge) before SPORT_CONFIDENCE reads it
    assert names.index("SHADOW") < names.index("BRIDGE") < names.index(
        "SPORT_IDENTITY") < names.index("SPORT_CONFIDENCE")
    assert names.count("BRIDGE") == 1


def test_shadow_event_skipped_by_the_horizon_triggers_a_refresh(tmp_path: Path) -> None:
    # Not stale yet (2 h < 2.5 h), but the latest snapshot (11:50Z) skipped
    # it: it starts beyond that snapshot's 3 h horizon.
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=5))
    write_hockey(tmp_path, [
        (NOW - timedelta(hours=2), "late", NOW + timedelta(hours=8)),
        (NOW - timedelta(minutes=10), "soon", NOW + timedelta(hours=1)),
    ])
    plan = plan_for(tmp_path)
    shadow = step(plan, "SHADOW")
    assert "skipped by the last snapshot" in shadow.reason
    assert float(shadow.argv[-1]) >= 8.0


def test_shadow_event_priced_recently_is_not_lagging(tmp_path: Path) -> None:
    # 10-05 12:01Z: the rebuild's full-horizon SHADOW priced the late game
    # 18 min ago; the loop's 3 h snapshot came after it. Not a reason to
    # ask Superbet again.
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=5))
    write_hockey(tmp_path, [
        (NOW - timedelta(minutes=18), "late", NOW + timedelta(hours=8)),
        (NOW - timedelta(minutes=1), "soon", NOW + timedelta(hours=1)),
    ])
    assert "SHADOW" not in plan_for(tmp_path).names()


def test_stale_cs2_is_refreshed_through_the_pipeline() -> None:
    state = rp.DayState(
        DATE, NOW, LIMIT, open_fixtures=0, offer_fixtures=1,
        sports={"cs2": rp.SportState("cs2", 2, 2, NOW - timedelta(hours=3),
                                     NOW + timedelta(hours=4))})
    plan = rp.build_plan(state, run_id="t")
    cs2 = step(plan, "CS2")
    assert cs2.argv[1:] == ("scripts/sofa/run_pipeline.py", "--date", DATE,
                            "--only", "CS2", "--run-id", "t")
    assert "SPORT_IDENTITY" in plan.names()


def test_shadow_horizon_default_matches_run_shadow() -> None:
    assert rp.SHADOW_DEFAULT_HORIZON_H == run_shadow.DEFAULT_HORIZON_H


def test_shadow_horizon_never_below_the_default() -> None:
    assert rp.shadow_horizon_h(NOW, NOW + timedelta(hours=1)) == 3.0
    assert rp.shadow_horizon_h(NOW, None) == 3.0
    assert rp.shadow_horizon_h(NOW, NOW + timedelta(hours=11, minutes=10)) == 11.5


# --- the sheet, the epoch, refusals -------------------------------------------


def test_sheet_rebuilt_only_when_confidence_would_refuse_it(tmp_path: Path) -> None:
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=5), sheet_epoch=None)
    plan = plan_for(tmp_path)
    names = plan.names()
    assert "SHEET" in names
    assert names.index("SHEET") < names.index("CONFIDENCE")
    assert step(plan, "SHEET").argv[-4:] == ("--only", "SHEET", "--run-id", "t")


def test_missing_sheet_or_fixtures_refuses(tmp_path: Path) -> None:
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=5))
    (tmp_path / DATE / "05_sheet.json").unlink()
    assert plan_for(tmp_path).refusal is not None
    (tmp_path / DATE / "02_fixtures.json").unlink()
    assert "02_fixtures" in str(plan_for(tmp_path).refusal)


def test_old_epoch_day_has_no_coupon_assembly() -> None:
    state = rp.DayState("2026-10-03", NOW, LIMIT, sheet_epoch=epochs.OLD)
    plan = rp.build_plan(state)
    assert plan.epoch == epochs.OLD
    assert plan.names() == ["CONFIDENCE", "PDF", "AUDIT_VARIANTS", "AUDIT_COUPON"]


def test_skip_audits_is_named() -> None:
    state = rp.DayState(DATE, NOW, LIMIT)
    plan = rp.build_plan(state, skip_audits=True)
    assert not {"AUDIT_VARIANTS", "AUDIT_COUPON"} & set(plan.names())
    assert any("AUDITS SKIPPED" in n for n in plan.notes)


# --- the runner ---------------------------------------------------------------


def test_runner_refuses_a_frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOFA_NOW", "2026-10-05T10:00:00Z")
    monkeypatch.setattr("sys.argv", ["rebuild_day.py", "--date", DATE, "--dry-run"])
    assert rebuild_day.main() == 2


def test_runner_dry_run_honours_runs_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=50))
    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(rebuild_day, "now", lambda: NOW)
    monkeypatch.setattr("sys.argv", ["rebuild_day.py", "--date", DATE, "--dry-run"])
    assert rebuild_day.main() == 0
    out = capsys.readouterr().out
    summary = json.loads(out.split("SOFA_SUMMARY: ", 1)[1])
    assert summary["verdict"] == "DRY_RUN"
    assert summary["output_path"] == str(tmp_path.resolve() / DATE)
    assert summary["plan"][0]["step"] == "OFFER"
    assert not list((tmp_path / DATE).glob("rebuild_*.log"))  # ran nothing


def test_summary_prefers_the_stage_over_the_pipeline_wrapper() -> None:
    lines = ["noise",
             'SOFA_SUMMARY: {"stage": "SHEET", "verdict": "OK", '
             '"metrics": {"rows": 3}}',
             'SOFA_SUMMARY: {"stage": "PIPELINE", "verdict": "OK"}']
    s = rebuild_day.summary_of(lines)
    assert s is not None and s["stage"] == "SHEET"
    assert rebuild_day.compact(s) == "rows=3"


def test_overall_exit_soft_failure_is_partial_hard_failure_is_failed() -> None:
    ok = {"verdict": "OK", "exit": 0, "soft": False}
    soft_fail = {"verdict": "FAILED", "exit": 2, "soft": True}
    hard_fail = {"verdict": "FAILED", "exit": 2, "soft": False}
    skipped = {"verdict": "SKIPPED", "exit": None, "soft": False}
    assert rebuild_day.overall([ok]) == 0
    assert rebuild_day.overall([ok, soft_fail]) == 1
    assert rebuild_day.overall([ok, hard_fail, skipped]) == 2


def test_priced_selector_rerun_only_when_older_than_its_inputs(tmp_path: Path) -> None:
    write_day(tmp_path, kickoff=NOW + timedelta(hours=3),
              fetched=NOW - timedelta(minutes=5))
    c06 = tmp_path / DATE / "06_coupon.json"
    c06.unlink()
    assert "COUPON" in plan_for(tmp_path).names()  # 06 missing
    c06.write_text("{}")
    assert "COUPON" not in plan_for(tmp_path).names()
    reads = tmp_path / DATE / "reads.json"
    reads.write_text("[]")
    os.utime(reads, (c06.stat().st_mtime + 10, c06.stat().st_mtime + 10))
    plan = plan_for(tmp_path)
    assert "COUPON" in plan.names()
    assert plan.names().index("COUPON") < plan.names().index("AUDIT_COUPON")
    assert "COUPON" not in plan_for(tmp_path, skip_audits=True).names()


def test_unmatched_vetoes_and_reads_are_counted() -> None:
    lines = ["UNMATCHED_READ: {}", "UNMATCHED_READ: {}", "UNMATCHED_VETO: {}", "x"]
    assert rebuild_day.unmatched_counts(lines) == {
        "UNMATCHED_READ": 2, "UNMATCHED_VETO": 1}


def _fake_step(name: str, code: int, soft: bool = False) -> rp.Step:
    doc = json.dumps({"stage": name, "metrics": {"n": code}})
    src = f"import sys; print('SOFA_SUMMARY: ' + {doc!r}); sys.exit({code})"
    return rp.Step(name, (rp.PY, "-c", src), "test", soft=soft)


def test_runner_stops_after_a_hard_failure_and_goes_on_after_a_soft_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / DATE).mkdir()
    steps = [_fake_step("A", 1), _fake_step("B", 2, soft=True),
             _fake_step("C", 2), _fake_step("D", 0)]

    def fake_plan(state: rp.DayState, run_id: str = "",
                  skip_audits: bool = False) -> rp.Plan:
        return rp.Plan(DATE, epochs.STATS_ONLY, True, steps=list(steps))

    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(rebuild_day, "now", lambda: NOW)
    monkeypatch.setattr(rp, "build_plan", fake_plan)
    monkeypatch.setattr("sys.argv", ["rebuild_day.py", "--date", DATE])
    assert rebuild_day.main() == 2
    out = capsys.readouterr().out
    summary = json.loads(out.rsplit("SOFA_SUMMARY: ", 1)[1])
    assert [(s["step"], s["verdict"]) for s in summary["steps"]] == [
        ("A", "PARTIAL"), ("B", "FAILED"), ("C", "FAILED"), ("D", "SKIPPED")]
    assert summary["step_summaries"]["A"]["metrics"] == {"n": 1}
    assert len(list((tmp_path / DATE).glob("rebuild_*.log"))) == 1


def test_match_moved_later_is_open_and_its_stale_price_refreshed(
        tmp_path: Path) -> None:
    # 10-05 12:22Z, Gaubas: RESOLVE froze 12:30Z, FIXTURE_CHECK read 13:30Z
    # (Superbet 13:30Z too). On the frozen clocks it looked inside run_offer's
    # 20 min, so neither the plan nor OFFER re-priced it, and CONFIDENCE -
    # which gates on the fresh clock - printed it on a 39-min-old price.
    now = datetime(2026, 10, 5, 12, 22, tzinfo=UTC)
    frozen = datetime(2026, 10, 5, 12, 30, tzinfo=UTC)
    write_day(tmp_path, kickoff=frozen,
              fetched=datetime(2026, 10, 5, 11, 43, tzinfo=UTC))
    run = tmp_path / DATE
    offer = json.loads((run / "04_offer.json").read_text())
    offer[0]["superbet_kickoff_seen_utc"] = "2026-10-05T13:30:00Z"
    (run / "04_offer.json").write_text(json.dumps(offer))
    (run / "fixture_status.json").write_text(json.dumps({"events": {"1": {
        "status": "notstarted", "start_utc": "2026-10-05T13:30:00Z",
        "why": "clock_gap", "checked_at_utc": "2026-10-05T11:43:38Z"}}}))
    state = rp.observe(str(tmp_path), DATE, now, LIMIT)
    assert state.open_fixtures == 1
    assert "OFFER" in rp.build_plan(state, run_id="t").names()
    # Without the fresh start the frozen clock is all there is: not open.
    (run / "fixture_status.json").unlink()
    offer[0]["superbet_kickoff_seen_utc"] = z(frozen)
    (run / "04_offer.json").write_text(json.dumps(offer))
    assert rp.observe(str(tmp_path), DATE, now, LIMIT).open_fixtures == 0
