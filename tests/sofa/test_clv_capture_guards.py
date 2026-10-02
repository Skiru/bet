"""CLV must say when it was never measured, and one day runs one capture loop."""

from __future__ import annotations

import os
from pathlib import Path

from scripts.sofa import audit_clv, capture_closing


def test_a_printed_day_without_a_closing_file_is_named(tmp_path: Path) -> None:
    day = tmp_path / "2026-09-30"
    day.mkdir()
    (day / "08_confidence.json").write_text("{}", encoding="utf-8")
    [line] = audit_clv.missing_closes(tmp_path, "2026-09-30")
    assert line.startswith("NO_CLOSING_FILE 2026-09-30")
    assert "unmeasured, not zero" in line


def test_a_day_with_its_closing_file_or_nothing_printed_is_silent(
    tmp_path: Path,
) -> None:
    day = tmp_path / "2026-09-30"
    day.mkdir()
    assert audit_clv.missing_closes(tmp_path, "2026-09-30") == []
    (day / "08_confidence.json").write_text("{}", encoding="utf-8")
    (day / "closing.jsonl").write_text("", encoding="utf-8")
    assert audit_clv.missing_closes(tmp_path, "2026-09-30") == []


def test_a_second_loop_for_a_day_sees_the_first(tmp_path: Path) -> None:
    assert capture_closing.loop_holder(tmp_path) is None
    (tmp_path / capture_closing.PID_FILE).write_text(str(os.getppid()), encoding="utf-8")

    def ours(pid: int) -> str:
        return f"python scripts/sofa/capture_closing.py --date {tmp_path.name} --loop"

    assert capture_closing.loop_holder(tmp_path, ours) == os.getppid()


def test_a_dead_loop_s_pid_file_does_not_block(tmp_path: Path) -> None:
    (tmp_path / capture_closing.PID_FILE).write_text("999999", encoding="utf-8")
    assert capture_closing.loop_holder(tmp_path) is None
    capture_closing.claim_loop(tmp_path)
    assert capture_closing.loop_holder(tmp_path) is None, "our own pid is not a rival"
