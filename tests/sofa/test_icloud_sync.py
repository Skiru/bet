"""The KUPON pdf + html copy on the operator's iCloud Drive
(bet.sofa.icloud_sync): every render replaces it, a scratch runs dir never
reaches it, a failure never raises; day_status compares it byte for byte."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from bet.sofa import icloud_sync as ic
from scripts.sofa import build_coupon_html
from scripts.sofa.day_status import NOT_CHECKED, OK, WARN, icloud_check

D = "2026-10-25"


def _day(runs: Path, pdf: bytes = b"%PDF-1", html: bytes = b"<html>") -> Path:
    run = runs / D
    run.mkdir(parents=True, exist_ok=True)
    (run / f"KUPON_{D}.pdf").write_bytes(pdf)
    (run / f"KUPON_{D}.html").write_bytes(html)
    return run


def test_day_folder_is_the_operators_layout() -> None:
    assert ic.day_folder("2026-10-05") == "05.10.2026"


def test_scratch_runs_dir_never_reaches_icloud(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ic.ENV)
    _day(tmp_path / "runs")
    res = ic.sync_day(tmp_path / "runs", D)
    assert res.status == ic.SKIPPED and "not the real" in res.detail


def test_empty_env_is_off(tmp_path: Path) -> None:  # conftest sets it empty
    _day(tmp_path / "runs")
    assert ic.sync_day(tmp_path / "runs", D).status == ic.SKIPPED


def test_every_render_replaces_the_copy(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = tmp_path / "cloud"
    monkeypatch.setenv(ic.ENV, str(cloud))
    runs = tmp_path / "runs"
    run = _day(runs, b"%PDF-old", b"<old>")
    os.utime(run / f"KUPON_{D}.pdf", (1_700_000_000, 1_700_000_000))
    first = ic.sync_day(runs, D)
    dest = cloud / "25.10.2026"
    assert first.status == ic.OK and set(first.copied) == {
        f"KUPON_{D}.pdf", f"KUPON_{D}.html"}
    assert (dest / f"KUPON_{D}.pdf").read_bytes() == b"%PDF-old"
    assert (dest / f"KUPON_{D}.pdf").stat().st_mtime == 1_700_000_000
    _day(runs, b"%PDF-rebuilt", b"<rebuilt>")
    assert ic.sync_day(runs, D).status == ic.OK
    assert (dest / f"KUPON_{D}.pdf").read_bytes() == b"%PDF-rebuilt"
    assert (dest / f"KUPON_{D}.html").read_bytes() == b"<rebuilt>"
    assert sorted(p.name for p in dest.iterdir()) == [
        f"KUPON_{D}.html", f"KUPON_{D}.pdf"]  # no partial left behind


def test_no_render_no_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ic.ENV, str(tmp_path / "cloud"))
    (tmp_path / "runs" / D).mkdir(parents=True)
    assert ic.sync_day(tmp_path / "runs", D).status == ic.SKIPPED
    assert not (tmp_path / "cloud").exists()


def test_a_failed_copy_is_failed_not_a_crash(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = tmp_path / "cloud"
    cloud.mkdir()
    (cloud / "25.10.2026").write_text("a file where the folder goes")
    monkeypatch.setenv(ic.ENV, str(cloud))
    _day(tmp_path / "runs")
    assert ic.sync_day(tmp_path / "runs", D).status == ic.FAILED


def test_day_status_compares_the_copy(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    _day(runs)
    assert icloud_check(runs, D).status == NOT_CHECKED  # env off
    cloud = tmp_path / "cloud"
    monkeypatch.setenv(ic.ENV, str(cloud))
    assert icloud_check(runs, D).status == WARN  # never copied
    ic.sync_day(runs, D)
    assert icloud_check(runs, D).status == OK
    _day(runs, b"%PDF-rebuilt-but-not-copied")
    check = icloud_check(runs, D)
    assert check.status == WARN and f"KUPON_{D}.pdf differs" in check.detail
    (cloud / "25.10.2026" / f"KUPON_{D}.pdf").unlink()
    (cloud / "25.10.2026" / f".KUPON_{D}.pdf.icloud").write_bytes(b"")
    assert "evicted" in icloud_check(runs, D).detail


def test_html_render_alone_refreshes_the_copy(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    cloud = tmp_path / "cloud"
    monkeypatch.setenv(ic.ENV, str(cloud))
    runs = tmp_path / "runs"
    run = _day(runs)
    (run / "11_coupon.json").write_text("{}")

    def page(run_dir: Path, doc: object, date: str) -> Path:
        out = run_dir / f"KUPON_{date}.html"
        out.write_text("<new page>")
        return out

    monkeypatch.setattr(build_coupon_html, "write_html", page)
    monkeypatch.setattr(build_coupon_html, "ensure_family_record",
                        lambda *a: "")
    monkeypatch.setattr(sys, "argv", ["x", "--date", D, "--runs-dir", str(runs)])
    assert build_coupon_html.main() == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["icloud"]["status"] == ic.OK
    assert (cloud / "25.10.2026" / f"KUPON_{D}.html").read_text() == "<new page>"
