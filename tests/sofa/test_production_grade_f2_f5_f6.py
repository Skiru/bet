"""Plan docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md: F2.1 (calibration per
curve, and the OFF-by-default "a failing curve stops printing"), F5.1 (the
pre-registration registry), F5.2 / F6.2 (CLV completeness, the day status)."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import calibration_audit as ca
from bet.sofa import curve_status, epochs
from scripts.sofa import check_test_registry, day_status, measure_calibration
from tests.sofa.confidence_day import (  # noqa: F401
    DAY,
    _run,
    day,
)

REPO = Path(__file__).resolve().parents[2]


# --- F2.1: calibration_audit ------------------------------------------------


def _pos(
    eid: int,
    conf: float,
    outcome: str,
    curve: str = "market:goals_total|OVER",
    sport: str = "football",
) -> dict[str, Any]:
    return {
        "source": {
            "sofascore_event_id": eid,
            "confidence": conf,
            "calibrated_on": curve,
            "sport": sport,
        },
        "outcome": outcome,
    }


def _legs(
    n_matches: int,
    per_match: int,
    conf: float,
    hit_rate: float,
    curve: str = "market:goals_total|OVER",
) -> list[ca.CalLeg]:
    """n_matches x per_match legs at `conf`; the first round(hit_rate x n)
    matches win every leg, the rest lose - so the realised rate is exact."""
    winners = round(hit_rate * n_matches)
    out = []
    for m in range(n_matches):
        for _ in range(per_match):
            out.append(
                ca.CalLeg(
                    "2026-10-06",
                    "official",
                    "stats_only",
                    "football",
                    curve,
                    conf,
                    "WIN" if m < winners else "LOSS",
                    f"sofa:{m}",
                )
            )
    return out


def test_only_win_and_loss_are_a_result_the_rest_is_counted_beside() -> None:
    legs, other = ca.legs_from_positions(
        "2026-10-06",
        "official",
        "stats_only",
        [
            _pos(1, 0.8, "WIN"),
            _pos(2, 0.8, "LOSS"),
            _pos(3, 0.8, "PENDING"),
            _pos(4, 0.8, "NOT_GRADED:ID_CHANGED"),
            _pos(5, 0.8, "REFUND"),
        ],
        [
            {
                "source": {"sofascore_event_id": 6, "combined_probability": 0.7},
                "outcome": "WIN",
            }
        ],
    )
    assert other == {"PENDING": 1, "NOT_GRADED": 1, "REFUND": 1}
    assert [x.settled for x in legs] == [True, True, False, False, False, True]
    assert legs[-1].curve == ca.BUILDER_CURVE and legs[-1].confidence == 0.7
    r = ca.measure(legs[:5], "official", "stats_only", "football", "c")
    assert (r.n_printed, r.n_settled, r.realised) == (5, 2, 0.5)


def test_verdicts() -> None:
    # 300 settled legs, calibrated: 0.75 claimed, 0.75 realised
    ok = ca.measure(_legs(200, 2, 0.75, 0.75), "official", "stats_only", "f", "c")
    assert ok.verdict == ca.PASS, ok
    assert ok.gap == 0.0 and ok.ci95 is not None and ok.ci95[0] < 0 < ok.ci95[1]
    # over-confident by 10 pp on 400 legs
    bad = ca.measure(_legs(200, 2, 0.85, 0.75), "official", "stats_only", "f", "c")
    assert bad.verdict == ca.FAIL and bad.gap == pytest.approx(0.10)
    # below 300 settled: never a verdict, however wrong
    thin = ca.measure(_legs(100, 2, 0.95, 0.50), "official", "stats_only", "f", "c")
    assert thin.verdict == ca.INSUFFICIENT


def test_the_interval_resamples_matches_not_legs() -> None:
    """300 legs on 10 matches are 10 pieces of evidence: no interval, no
    verdict - a leg-level bootstrap would have called it."""
    r = ca.measure(_legs(10, 30, 0.75, 0.5), "official", "stats_only", "f", "c")
    assert r.n_settled == 300 and r.n_matches == 10
    assert r.ci95 is None and r.verdict == ca.INSUFFICIENT
    # one ladder of 30 legs on a match moves the interval as one draw: the
    # same 200 matches with 1 or 3 legs each give the same match-level gap
    one = ca.measure(_legs(400, 1, 0.80, 0.75), "o", "s", "f", "c")
    three = ca.measure(_legs(400, 3, 0.80, 0.75), "o", "s", "f", "c")
    assert one.gap == three.gap
    assert one.ci95 == three.ci95


def test_failed_curves_lists_one_variant_and_epoch_never_builders() -> None:
    legs = _legs(200, 2, 0.85, 0.75, "market:a") + _legs(200, 2, 0.75, 0.75, "market:b")
    legs += [
        ca.CalLeg(
            x.date,
            "official:pre_stats_only",
            "old",
            x.sport,
            "market:c",
            x.confidence,
            x.outcome,
            x.match,
        )
        for x in _legs(200, 2, 0.85, 0.75)
    ]
    legs += [
        ca.CalLeg(
            x.date,
            "official",
            "stats_only",
            "builder",
            ca.BUILDER_CURVE,
            x.confidence,
            x.outcome,
            x.match,
        )
        for x in _legs(200, 2, 0.85, 0.75)
    ]
    failed = ca.failed_curves(ca.by_curve(legs), "official", "stats_only")
    assert list(failed) == ["market:a"]
    assert failed["market:a"]["n_settled"] == 400


def test_collect_reads_the_ledgers_grades_and_keeps_variants_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake(runs_dir: str, date: str, db_path: str) -> list[dict[str, Any]]:
        return [
            {
                "variant": "official",
                "epoch": "stats_only",
                "singles": [_pos(1, 0.8, "WIN"), _pos(2, 0.8, "PENDING")],
                "builders": [],
            },
            {
                "variant": "official:pre_stats_only",
                "epoch": "old",
                "singles": [_pos(3, 0.7, "LOSS")],
                "builders": [],
            },
        ]

    monkeypatch.setattr(measure_calibration, "graded_confidence", fake)
    legs, other = measure_calibration.collect("r", ["2026-10-05"], "db")
    assert {(x.variant, x.epoch) for x in legs} == {
        ("official", "stats_only"),
        ("official:pre_stats_only", "old"),
    }
    assert other == {
        "official|stats_only": {"PENDING": 1},
        "official:pre_stats_only|old": {},
    }
    variants = ca.by_variant(legs)
    assert len(variants) == 2  # never pooled


def test_graded_confidence_is_what_the_ledger_records() -> None:
    """measure_calibration reads record_results.graded_confidence, the same
    function confidence_rows summarises - not a second grader."""
    src = (REPO / "scripts/sofa/record_results.py").read_text(encoding="utf-8")
    assert "for g in graded_confidence(runs_dir, date, db_path):" in src
    assert (
        measure_calibration.graded_confidence.__module__
        == "scripts.sofa.record_results"
    )


def test_write_config_is_refused_mid_day_or_on_its_own_days(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    (runs / "2026-10-07").mkdir(parents=True)
    assert measure_calibration.write_config_refusal(
        str(runs), "2026-10-07", "2026-10-07"
    )
    assert (
        measure_calibration.write_config_refusal(str(runs), "2026-10-07", "2026-10-06")
        is None
    )
    (runs / "2026-10-07" / "08_confidence.json").write_text("{}")
    why = measure_calibration.write_config_refusal(
        str(runs), "2026-10-07", "2026-10-06"
    )
    assert why and "mid-way" in why


def test_the_written_status_is_what_confidence_reads(tmp_path: Path) -> None:
    legs = _legs(200, 2, 0.85, 0.75, "market:a") + _legs(200, 2, 0.75, 0.75, "market:b")
    path = tmp_path / "sofa_curve_status.json"
    doc = measure_calibration.write_config(
        path,
        "2026-10-07",
        "2026-10-05",
        "2026-10-06",
        str(tmp_path / "no.db"),
        ca.by_curve(legs),
    )
    assert doc["fitted_from"]["before"] == "2026-10-07"
    assert doc["fitted_from"]["fitted_at_utc"]
    status = curve_status.load(path)
    assert status.failed == frozenset({"market:a"})
    assert status.refuses("market:a", "2026-10-07")
    assert not status.refuses("market:a", "2026-10-06")  # before it applies
    assert not status.refuses("market:b", "2026-10-07")


# --- F2.1: the gate is OFF until the operator turns it on -------------------


def test_the_gate_is_off_and_reads_nothing(tmp_path: Path) -> None:
    assert epochs.CURVE_STATUS_FROM_UTC is None
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"failed_curves": {"market:a": {}}}))
    assert not epochs.curve_status_enforced("2030-01-01")
    assert curve_status.for_build("2030-01-01", path=path).failed == frozenset()
    path.write_text("not json")  # not even read while off
    assert curve_status.for_build("2030-01-01", path=path).failed == frozenset()


def test_once_enabled_it_applies_from_its_moment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        epochs, "CURVE_STATUS_FROM_UTC", datetime(2026, 10, 7, 4, 0, tzinfo=UTC)
    )
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {"failed_curves": {"market:a": {}}, "applies_from_date": "2026-10-07"}
        )
    )
    before = datetime(2026, 10, 7, 3, 59, tzinfo=UTC)
    after = datetime(2026, 10, 7, 4, 1, tzinfo=UTC)
    assert not curve_status.for_build("2026-10-07", before, path).refuses(
        "market:a", "2026-10-07"
    )
    assert curve_status.for_build("2026-10-07", after, path).refuses(
        "market:a", "2026-10-07"
    )
    assert (
        curve_status.for_build("2026-10-07", after, tmp_path / "none.json").failed
        == frozenset()
    )
    path.write_text("not json")
    with pytest.raises(ValueError):
        curve_status.for_build("2026-10-07", after, path)


def test_confidence_refuses_a_listed_curve_only_when_enabled(
    day: Path,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = day / DAY
    off = _run("run_confidence.py", day, "--runs-dir", str(day))
    assert off.returncode == 0, off.stderr
    doc = json.loads((run / "08_confidence.json").read_text())
    curves = {leg["calibrated_on"] for leg in doc["singles"]}
    assert len(doc["singles"]) == 2 and curves
    status = tmp_path / "sofa_curve_status.json"
    status.write_text(
        json.dumps({"failed_curves": {c: {} for c in curves}, "applies_from_date": DAY})
    )
    monkeypatch.setattr(curve_status, "default_path", lambda: status)

    def in_process() -> dict[str, Any]:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_confidence.py",
                "--date",
                DAY,
                "--runs-dir",
                str(day),
            ],
        )
        with pytest.raises(SystemExit) as done:
            runpy.run_path(
                str(REPO / "scripts/sofa/run_confidence.py"), run_name="__main__"
            )
        assert done.value.code in (0, None, 1)
        out: dict[str, Any] = json.loads((run / "08_confidence.json").read_text())
        summary = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("{") and '"CONFIDENCE"' in line
        ]
        out["_refused"] = summary[-1]["metrics"]["refused"]
        return out

    # the file lists both curves, the gate is off: both legs still print
    still = in_process()
    assert len(still["singles"]) == 2
    assert curve_status.CURVE_FAILED_CALIBRATION not in still["_refused"]
    monkeypatch.setattr(
        epochs, "CURVE_STATUS_FROM_UTC", datetime(2000, 1, 1, tzinfo=UTC)
    )
    on = in_process()
    assert on["singles"] == []
    assert on["_refused"] == {curve_status.CURVE_FAILED_CALIBRATION: 2}


def test_sport_confidence_applies_the_same_gate() -> None:
    src = (REPO / "scripts/sofa/run_sport_confidence.py").read_text(encoding="utf-8")
    assert "failed_curves = curve_status.for_build(date, at)" in src
    assert "failed_curves.refuses(conf.calibrated_on, date)" in src


# --- F5.1: the registry ------------------------------------------------------


def test_the_installed_registry_is_valid() -> None:
    doc = json.loads((REPO / "config/sofa_test_registry.json").read_text("utf-8"))
    assert check_test_registry.findings(doc) == []
    ids = {t["id"] for t in doc["tests"]}
    assert {"T-F53-coupon-edge", "T-F54-coupon-failure"} <= ids
    assert (REPO / "docs/sofa/REJESTR_TESTOW.md").exists()


def test_a_window_that_starts_before_or_on_registration_is_refused(
    tmp_path: Path,
) -> None:
    doc = json.loads((REPO / "config/sofa_test_registry.json").read_text("utf-8"))
    doc["tests"][0]["data_window"]["from"] = doc["tests"][0]["registered_on"]
    found = check_test_registry.findings(doc)
    assert len(found) == 1 and "REFUSED" in found[0]
    path = tmp_path / "r.json"
    path.write_text(json.dumps(doc))
    res = subprocess.run(
        [
            sys.executable,
            "scripts/sofa/check_test_registry.py",
            "--registry",
            str(path),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert res.returncode == 1, res.stdout + res.stderr


# --- F5.2 / F6.2: day status -------------------------------------------------

D = "2026-10-06"
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _leg(eid: int, kickoff: str) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "kickoff_utc": kickoff,
        "sport": "football",
        "market": "goals_total",
        "subject": "",
        "line": 2.5,
        "direction": "OVER",
        "offered_odds": 1.8,
        "confidence": 0.8,
        "calibrated_on": "market:x",
    }


def _runs(tmp_path: Path, mismatch: int = 0) -> Path:
    runs = tmp_path / "runs"
    run = runs / D
    run.mkdir(parents=True)
    (run / "02_fixtures.json").write_text("[]")
    (run / "04_offer.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 1,
                    "rungs": [
                        {"fetched_at_utc": "2026-10-06T11:50:00Z"},
                        {"fetched_at_utc": "2026-10-06T08:00:00Z"},
                    ],
                }
            ]
        )
    )
    (run / "08_confidence.json").write_text("{}")
    (run / "11_coupon.json").write_text(
        json.dumps(
            {
                "created_at_utc": "2026-10-06T11:55:00Z",
                "pdf_max_singles": None,
                "singles": [
                    _leg(1, "2026-10-06T10:00:00Z"),
                    _leg(2, "2026-10-06T11:00:00Z"),
                    _leg(3, "2026-10-06T18:00:00Z"),
                ],
                "builders": [],
            }
        )
    )
    (run / f"KUPON_{D}.pdf").write_text("pdf")
    (run / "fixture_status.json").write_text(
        json.dumps(
            {
                "checked_at_utc": "2026-10-06T11:00:00Z",
                "events": {
                    "1": {"status": "notstarted"},
                    "3": {"status": "UNVERIFIED"},
                },
            }
        )
    )
    key = "1|goals_total||2.5|OVER"
    (run / "closing.jsonl").write_text(
        json.dumps(
            {
                "variant": "official",
                "leg_key": key,
                "sofascore_event_id": 1,
                "odds_taken": 1.8,
                "odds_close": 1.75,
                "partner_close": 2.05,
                "fetched_at_utc": "2026-10-06T09:50:00+00:00",
                "minutes_before": 10.0,
            }
        )
        + "\n"
    )
    for sub, sport in (
        ("shadow/hockey", "hockey"),
        ("shadow/basketball", ""),
        ("shadow/volleyball", ""),
        ("cs2", ""),
    ):
        d = runs / sub / D
        d.mkdir(parents=True)
        (d / "snapshots.jsonl").write_text(
            json.dumps({"fetched_at_utc": "2026-10-06T07:00:00Z"})
            + "\n"
            + json.dumps({"fetched_at_utc": "2026-10-06T11:30:00Z"})
            + "\n{torn"
        )
        del sport
    (runs / "shadow" / f"daily_{D}.done").write_text("")
    (runs / "cs2" / f"daily_{D}.log").write_text(
        "[2026-10-06T11:30:00+00:00] $ x\nnoise\n"
    )
    ledger = runs / "ledger"
    ledger.mkdir()
    rows = [
        {"date": "2026-10-05", "variant": "official", "outcomes": {"WIN": 1}},
        {
            "date": "2026-10-04",
            "variant": "official",
            "outcomes": {"MISMATCH": mismatch},
        },
    ]
    (ledger / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return runs


def _by_name(runs: Path) -> dict[str, day_status.Check]:
    return {
        c.name: c for c in day_status.checks(runs, D, NOW, command_of=lambda pid: "")
    }


def test_day_status_reads_every_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOFA_CONFIG_DIR", str(tmp_path / "noconfig"))
    got = _by_name(_runs(tmp_path))
    assert got["offer"].status == day_status.OK
    assert "2026-10-06T08:00:00Z" in got["offer"].detail
    assert all(
        got[f"sport:{s}"].status == day_status.OK
        for s in ("hockey", "basketball", "volleyball", "cs2")
    )
    assert "11:30:00Z" in got["sport:hockey"].detail  # the torn tail is skipped
    # leg 3 still to close and no loop: the CLV hole is named
    assert got["loop:capture_closing"].status == day_status.WARN
    assert got["loop:shadow_daily"].status == day_status.OK  # done
    assert got["loop:cs2_daily"].status == day_status.WARN  # neither alive nor done
    assert "11:30:00Z" in got["loop:cs2_daily"].detail
    assert got["bridge"].status == day_status.NOT_CHECKED
    assert got["ledger"].status == day_status.OK
    # legs 1 and 2 are past their window, 1 has a close
    assert got["clv"].status == day_status.WARN
    assert got["clv"].detail.startswith("1/2 ")
    assert got["coupon"].status == day_status.OK
    assert (
        got["fixtures"].status == day_status.WARN
        and "UNVERIFIED 1" in got["fixtures"].detail
    )


def test_day_status_breaks_on_a_mismatch_and_a_stale_coupon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    monkeypatch.setenv("SOFA_CONFIG_DIR", str(tmp_path / "noconfig"))
    runs = _runs(tmp_path, mismatch=2)
    eleven = runs / D / "11_coupon.json"
    os.utime(eleven, (1_000_000_000, 1_000_000_000))
    got = _by_name(runs)
    assert (
        got["ledger"].status == day_status.BROKEN
        and "MISMATCH 2" in got["ledger"].detail
    )
    assert got["coupon"].status == day_status.BROKEN
    assert "STALE_COUPON" in got["coupon"].detail
    res = subprocess.run(
        [
            sys.executable,
            "scripts/sofa/day_status.py",
            "--date",
            D,
            "--runs-dir",
            str(runs),
            "--now",
            NOW.isoformat(),
            "--clv-from",
            "2026-10-05",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": "src:.",
            "PATH": "/usr/bin:/bin",
            "SOFA_CONFIG_DIR": str(tmp_path / "noconfig"),
        },
    )
    assert res.returncode == 2, res.stdout + res.stderr
    assert "| 2026-10-06 | yes | 3 | 2 | 1 |" in res.stdout
    assert "verdict: BROKEN" in res.stdout


def test_sofa_day_runs_the_status_and_the_closing_loop() -> None:
    text = (REPO / ".claude/commands/sofa-day.md").read_text(encoding="utf-8")
    assert "scripts/sofa/day_status.py" in text
    assert "capture_closing.py --date <date> --loop" in text
