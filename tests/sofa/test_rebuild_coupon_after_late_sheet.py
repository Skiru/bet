"""rebuild: a SHEET inserted after FIXTURE_CHECK (a referee named late) is
followed by COUPON, so 06_coupon.json is never older than the sheet when
audit_coupon reads it (2026-11-06 19:42Z: COUPON, FIXTURE_CHECK, SHEET ->
"vanished in silence"). Offline."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import rebuild_plan as rp
from scripts.sofa import rebuild_day

DAY = "2026-11-06"
NOW = datetime(2026, 11, 6, 19, 42, tzinfo=UTC)


def _s(name: str) -> rp.Step:
    return rp.Step(name, ("x",), name)


def test_coupon_follows_a_late_sheet_only_when_audited() -> None:
    sheet = [_s("SHEET")]
    tail = [_s("CONFIDENCE"), _s("PDF"), _s("AUDIT_COUPON")]
    out = rp.coupon_after_late_sheet(sheet, tail, DAY, run_id="r")
    assert [s.name for s in out] == ["SHEET", "COUPON"]
    assert out[1].soft and "--only" in out[1].argv and "COUPON" in out[1].argv
    assert "r" in out[1].argv
    # nothing added: no SHEET, audits skipped, or a COUPON still to come
    assert rp.coupon_after_late_sheet([], tail, DAY) == []
    assert [s.name for s in rp.coupon_after_late_sheet(
        sheet, [_s("CONFIDENCE"), _s("PDF")], DAY)] == ["SHEET"]
    assert [s.name for s in rp.coupon_after_late_sheet(
        sheet, [_s("COUPON"), *tail], DAY)] == ["SHEET"]


def test_rebuild_day_runs_coupon_after_the_late_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / DAY).mkdir()
    ran: list[str] = []
    plan = rp.Plan(DAY, "stats_only", False, steps=[
        _s("COUPON"), rp.Step("FIXTURE_CHECK", ("x",), "fresh /event", soft=True),
        _s("CONFIDENCE"), _s("COUPON_ASSEMBLY"), _s("PDF"),
        _s("AUDIT_VARIANTS"), _s("AUDIT_COUPON")])

    def after(runs_dir: str, date: str, now: datetime, db_path: Any,
              run_id: str = "rebuild") -> list[rp.Step]:
        return [rp.Step("SHEET", ("x",), "referee named")]

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setattr(sys, "argv", ["rebuild_day.py", "--date", DAY])
    monkeypatch.setattr(rp, "observe", lambda *a, **k: rp.DayState(
        DAY, NOW, timedelta(minutes=30)))
    monkeypatch.setattr(rp, "build_plan", lambda *a, **k: plan)
    monkeypatch.setattr(rp, "after_fixture_check", after)
    monkeypatch.setattr(rebuild_day, "run_step",
                        lambda step, env, log: (ran.append(step.name), (0, []))[1])
    assert rebuild_day.main() == 0
    assert ran == ["COUPON", "FIXTURE_CHECK", "SHEET", "COUPON", "CONFIDENCE",
                   "COUPON_ASSEMBLY", "PDF", "AUDIT_VARIANTS", "AUDIT_COUPON"]
    assert ran.index("AUDIT_COUPON") > max(
        i for i, n in enumerate(ran) if n == "COUPON") > ran.index("SHEET")
