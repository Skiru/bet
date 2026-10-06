"""The ledger, the settlement's grading of the coupon and the audits: one
test per defect found in the review rounds of 2026-09-30 .. 10-04."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cs2
from bet.sofa import sport_day as sd
from scripts.sofa import audit_settlement, audit_variants, record_results
from tests.sofa.coupon_fixtures import (
    AT,
    DATE,
    official_single,
    snap,
    write_db,
    write_official,
)


def test_a_row_settle_never_wrote_is_unsettled_not_pending() -> None:
    single = {
        "source": {
            "sofascore_event_id": 9,
            "market": "m",
            "subject": "",
            "line": 1.5,
            "direction": "OVER",
            "offered_odds": 1.3,
        }
    }
    other = {
        "sofascore_event_id": 1,
        "market": "m",
        "subject": "",
        "line": 1.5,
        "direction": "OVER",
        "outcome": "WIN",
    }
    [g], _ = audit_settlement.grade_confidence_positions([single], [], [other], {})
    assert g["outcome"] == "UNSETTLED"
    [g], _ = audit_settlement.grade_confidence_positions([single], [], [], {})
    assert g["outcome"] == "PENDING"


def test_an_unfinished_measurement_day_reports_its_retryable_events(
    tmp_path: Path,
) -> None:
    d = sd.day_dir(str(tmp_path), "hockey", DATE)
    d.mkdir(parents=True)
    (d / "settled.json").write_text(
        json.dumps(
            {
                "events": {
                    "1": {"state": "SETTLED", "graded": []},
                    "2": {"state": "NOT_ON_SOFASCORE"},
                }
            }
        ),
        encoding="utf-8",
    )
    [row] = record_results.measure_rows(str(tmp_path), DATE)
    # retried by SETTLE, but most never settle: reported, not pending
    assert row["retryable"] == 1 and row["pending"] == 0


def test_a_crash_in_the_ledger_script_is_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("x")

    monkeypatch.setattr(record_results, "record", boom)
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE])
    assert record_results.main() == 2


def test_the_coupon_artifact_is_audited_by_its_own_dials(tmp_path: Path) -> None:
    import os


    run = write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    assert audit_variants.audit_confidence(str(tmp_path), DATE) == []
    conf = run / "08_confidence.json"
    doc = json.loads(conf.read_text(encoding="utf-8"))
    doc.update(confidence_floor=0.70, min_ev=None, max_overround=0.105)
    doc["singles"][0].update(confidence=0.69, offered_odds=1.40, overround=0.12)
    t = conf.stat().st_mtime
    conf.write_text(json.dumps(doc), encoding="utf-8")
    os.utime(conf, (t, t))
    got = audit_variants.audit_confidence(str(tmp_path), DATE)
    assert any("below floor" in f for f in got) and any("margin" in f for f in got)
    # the official PDF older than its artifact prints another build
    os.utime(run / f"KUPON_{DATE}.pdf", (t - 100, t - 100))
    got = audit_variants.audit_confidence(str(tmp_path), DATE)
    assert any("prints another build" in f for f in got)


def test_an_official_artifact_without_its_dials_is_audited_by_the_old_rule(
    tmp_path: Path,
) -> None:
    """Since 2026-10-05 the official profile is x >= 0.90 / margin <= 15%; an
    official artifact that carries no dials predates them and must still be
    checked against x > 1.0 and 10.5%, not against today's looser rule."""
    import os


    run = write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    conf = run / "08_confidence.json"
    doc = json.loads(conf.read_text(encoding="utf-8"))
    for key in ("min_ev", "max_overround"):
        doc.pop(key, None)
    # x = 0.95 and a 12% margin: fine today, both defects under the old rule
    doc["singles"][0].update(confidence=0.76, offered_odds=1.25, overround=0.12)
    t = conf.stat().st_mtime
    conf.write_text(json.dumps(doc), encoding="utf-8")
    os.utime(conf, (t, t))
    got = audit_variants.audit_confidence(str(tmp_path), DATE)
    assert any("<= 1" in f for f in got) and any("above 0.105" in f for f in got)


@pytest.mark.parametrize(
    "state, check_rc, want",
    [
        ("port_busy", 0, 2),
        ("unflagged", 0, 1),
        ("healthy", 0, 0),
        ("healthy", 1, 1),
    ],
)
def test_ensure_bridge_exit_codes(
    monkeypatch: pytest.MonkeyPatch, state: str, check_rc: int, want: int
) -> None:
    from scripts.sofa import ensure_bridge as eb

    states = {
        "port_busy": eb.State(False, None, False, False, port_busy=True),
        "unflagged": eb.State(True, 1.0, True, False),
        "healthy": eb.State(True, 1.0, True, True),
    }
    calls: list[list[str]] = []
    monkeypatch.setattr(eb, "observe", lambda: states[state])
    monkeypatch.setattr(
        eb.subprocess, "call", lambda cmd, **k: calls.append(cmd) or check_rc
    )
    monkeypatch.setattr(
        eb, "start_server", lambda: pytest.fail("never start a server here")
    )
    monkeypatch.setattr("sys.argv", ["x"])
    assert eb.main() == want
    if state == "port_busy":
        assert calls == []  # stopped before check_bridge, nothing launched


def test_a_missing_database_is_a_failure_not_a_day_of_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE])
    assert record_results.main() == 2
    assert not record_results.ledger_path(str(tmp_path)).exists()


def test_a_row_filed_under_another_date_still_grades_the_leg(tmp_path: Path) -> None:
    from scripts.sofa import audit_settlement

    write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    row = {
        "sofascore_event_id": 1,
        "market": "corners_total",
        "subject": "",
        "line": 7.5,
        "direction": "OVER",
        "outcome": "WIN",
    }
    # SETTLE filed the rung under the next day (it was on both sheets)
    db = write_db(tmp_path, [row], date="2026-10-01")
    write_db(tmp_path, [{**row, "sofascore_event_id": 99}], date=DATE)  # day ran
    by_key = audit_settlement.settled_by_key(db, DATE, {1})
    assert by_key[audit_settlement._key(row)]["outcome"] == "WIN"
    [rec] = [
        r
        for r in record_results.confidence_rows(str(tmp_path), DATE, db)
        if r["variant"] == "official"
    ]
    assert rec["singles"]["won"] == 1 and rec["singles"]["not_counted"] == 0
    # the day's own row wins over one filed elsewhere
    write_db(tmp_path, [{**row, "outcome": "LOSS"}], date=DATE)
    assert (
        audit_settlement.settled_by_key(db, DATE, {1})[audit_settlement._key(row)][
            "outcome"
        ]
        == "LOSS"
    )


def test_the_ledger_never_replaces_a_graded_row_with_a_less_graded_one(
    tmp_path: Path,
) -> None:

    write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    row = {
        "sofascore_event_id": 1,
        "market": "corners_total",
        "subject": "",
        "line": 7.5,
        "direction": "OVER",
        "outcome": "WIN",
    }
    db = write_db(tmp_path, [row])
    record_results.record(str(tmp_path), DATE, db)
    (tmp_path / "other").mkdir()
    empty = write_db(tmp_path / "other", [])
    record_results.record(str(tmp_path), DATE, empty)
    lines = record_results.ledger_path(str(tmp_path)).read_text(encoding="utf-8")
    [off] = [json.loads(x) for x in lines.splitlines() if '"official"' in x]
    assert off["total"]["won"] == 1


def test_append_records_heals_a_torn_last_line(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.jsonl"
    path.write_text('{"a": 1}\n{"torn', encoding="utf-8")
    cs2.append_records(path, [{"b": 2}])
    rows, lines, bad = sd.read_snapshots(path)
    assert rows == [{"a": 1}, {"b": 2}] and (lines, bad) == (3, 1)


def test_settle_cs2_skips_a_torn_snapshot_line(tmp_path: Path) -> None:
    from scripts.sofa import settle_cs2

    d = cs2.cs2_day_dir(str(tmp_path), DATE)
    d.mkdir(parents=True)
    good = snap(
        "9",
        [
            cs2.Cs2Line("9", "maps_total", 0, "", 2.5, s, o).as_dict()
            for s, o in (("OVER", 1.9), ("UNDER", 1.9))
        ],
        AT - timedelta(hours=1),
        kickoff=AT + timedelta(hours=1),
    )
    (d / cs2.SNAPSHOTS_FILE).write_text(
        '{"torn\n' + json.dumps(good) + "\n", encoding="utf-8"
    )

    class NoNetwork:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError("no Sofascore call for a series not yet played")

    # the series has not started: nothing to settle, and no crash on the line
    res = settle_cs2.settle(DATE, NoNetwork(), str(tmp_path), AT)  # type: ignore[arg-type]
    assert res.get("verdict") != "FAILED"


def test_a_regrade_that_lowers_the_count_replaces_the_row(tmp_path: Path) -> None:

    write_official(
        tmp_path,
        [
            official_single(1, "corners_total", 1.30, 0.77),
            official_single(2, "corners_total", 1.30, 0.77),
        ],
    )
    rows = [
        {
            "sofascore_event_id": i,
            "market": "corners_total",
            "subject": "",
            "line": 7.5,
            "direction": "OVER",
            "outcome": "WIN",
        }
        for i in (1, 2)
    ]
    db = write_db(tmp_path, rows)
    record_results.record(str(tmp_path), DATE, db)
    # regrade: event 2's rung is now a PUSH - one fewer settled, and true
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE sofa_settled_row SET outcome='PUSH' WHERE sofascore_event_id=2"
    )
    conn.commit()
    conn.close()
    record_results.record(str(tmp_path), DATE, db)
    lines = record_results.ledger_path(str(tmp_path)).read_text(encoding="utf-8")
    [off] = [json.loads(x) for x in lines.splitlines() if '"official"' in x]
    assert off["total"]["settled"] == 1 and off["outcomes"] == {"VOID": 1, "WIN": 1}


def test_the_measurement_keeps_the_two_way_series_and_splits_the_rest(
    tmp_path: Path,
) -> None:
    d = sd.day_dir(str(tmp_path), "hockey", DATE)
    d.mkdir(parents=True)

    def row(
        fam: str, side: str, fair: float, outcome: str, **kw: Any
    ) -> dict[str, Any]:
        return {
            "superbet_event_id": "1",
            "market_id": 1,
            "family": fam,
            "period": 0,
            "subject": "",
            "line": 5.5,
            "side": side,
            "odds": 1.5,
            "fair_p": fair,
            "outcome": outcome,
            **kw,
        }

    graded = [
        row("total", "OVER", 0.6, "WIN", partner_odds=2.4),
        row("total", "UNDER", 0.4, "LOSS", partner_odds=1.5),
        row(
            "result_1x2",
            "T1",
            0.5,
            "LOSS",
            line=None,
            group_odds={"T1": 1.9, "DRAW": 4.0, "T2": 3.5},
            overround=0.06,
        ),
        row(
            "result_1x2",
            "DRAW",
            0.22,
            "WIN",
            line=None,
            group_odds={"T1": 1.9, "DRAW": 4.0, "T2": 3.5},
            overround=0.06,
        ),
        row(
            "result_1x2",
            "T2",
            0.28,
            "LOSS",
            line=None,
            group_odds={"T1": 1.9, "DRAW": 4.0, "T2": 3.5},
            overround=0.06,
        ),
        row("player_points", "OVER", 0.7, "WIN", subject="A B", partner_odds=2.0),
        row("player_points", "UNDER", 0.3, "LOSS", subject="A B", partner_odds=1.3),
    ]
    (d / "settled.json").write_text(
        json.dumps({"events": {"1": {"state": "SETTLED", "graded": graded}}}),
        encoding="utf-8",
    )
    [m] = record_results.measure_rows(str(tmp_path), DATE)
    assert m["favourite_side"]["sides"] == 1  # the two-way total only
    assert set(m["by_shape"]) == {"two", "three"}
    assert m["by_shape"]["three"]["mean_fair_p"] == 0.5
    assert set(m["by_family"]) == {"total", "result_1x2"}
    assert m["players"]["sides"] == 1


def test_the_ledger_reader_keeps_every_variant_apart(tmp_path: Path) -> None:
    from scripts.sofa import audit_ledger

    path = record_results.ledger_path(str(tmp_path))
    path.parent.mkdir(parents=True)
    rows = [
        {
            "date": "2026-09-28",
            "variant": "official",
            "total": {"positions": 2, "settled": 2, "won": 1, "lost": 1, "units": -0.5},
        },
        {
            "date": "2026-09-29",
            "variant": "official",
            "total": {"positions": 1, "settled": 1, "won": 1, "lost": 0, "units": 0.3},
        },
        {
            "date": "2026-09-29",
            "variant": "sport:hockey",
            "total": {"positions": 1, "settled": 1, "won": 0, "lost": 1, "units": -1.0},
            "by_family": {"total": {"settled": 1, "won": 0, "units": -1.0}},
        },
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    loaded = audit_ledger.load(str(tmp_path), "2026-09-28", "2026-09-29")
    text = "\n".join(audit_ledger.render(loaded, None))
    # split by rule epoch since 2026-10-05 (K7); both days are "do 10-04"
    assert "| official [do 10-04] | 2 | 3 | 3 | 2 | 1 | -0.20 |" in text
    assert "| sport:hockey [do 10-04] | 1 | 1 | 1 | 0 | 1 | -1.00 |" in text
    fam = "\n".join(audit_ledger.render(loaded, "sport:hockey"))
    assert "| total | 1 | 0 | -1.00 |" in fam and "official" not in fam


def test_the_ledger_roi_interval_resamples_matches_not_days():
    from scripts.sofa import audit_ledger

    def day(units, settled, matches=None):
        row = {"total": {"units": units, "settled": settled}}
        if matches is not None:
            row["by_match"] = matches
        return row

    # a day written before the per-match record cannot be clustered
    assert audit_ledger.roi_interval([day(5.0, 10), day(-5.0, 10)]) is None
    # two matches over two days are two pieces of evidence, not an interval
    two = [day(1.0, 1, {"sofa:1": [1.0, 1]}), day(-1.0, 1, {"sofa:2": [-1.0, 1]})]
    assert audit_ledger.roi_interval(two) is None
    many = [day(0.0, 30, {f"sofa:{i}": [1.0 if i % 2 else -1.0, 1]
                          for i in range(30)})]
    lo, hi = audit_ledger.roi_interval(many)
    assert lo < 0 < hi
    tight = audit_ledger.roi_interval(
        [day(-1.0, 100, {f"sofa:{i}": [-1.0, 1] for i in range(25)})] * 2)
    assert tight == (-1.0, -1.0)


def test_a_cache_replay_row_never_grades_a_printed_leg(tmp_path: Path) -> None:
    # Review 2026-10-04: live SETTLE skipped Hellas Kagran - Vienna Amateure
    # (NOT_FINISHED); tonight's rebuild-cache-rows wrote a cache-calibration
    # row for it and 7d / the ledger graded the printed leg from that row.
    from scripts.sofa import audit_settlement

    write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    row = {"sofascore_event_id": 1, "market": "corners_total", "subject": "",
           "line": 7.5, "direction": "OVER", "outcome": "WIN"}
    db = write_db(tmp_path, [row], date="cache-calibration")
    write_db(tmp_path, [{**row, "sofascore_event_id": 99}], date=DATE)  # day ran
    assert audit_settlement._key(row) not in audit_settlement.settled_by_key(
        db, DATE, {1})
    [rec] = [r for r in record_results.confidence_rows(str(tmp_path), DATE, db)
             if r["variant"] == "official"]
    assert rec["singles"]["won"] == 0 and rec["singles"]["not_counted"] == 1


def test_a_mismatch_fails_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two graders disagreeing on a leg is a defect: exit 1, never a pass."""
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    row = {"date": DATE, "variant": "official", "pending": 0,
           "total": {"positions": 1, "settled": 0, "won": 0, "lost": 0,
                     "units": 0.0, "roi": None},
           "outcomes": {"MISMATCH": 1}}
    monkeypatch.setattr(record_results, "record", lambda *a: [row])
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE])
    assert record_results.main() == 1
    row["outcomes"] = {"PENDING": 1}
    row["pending"] = 1
    assert record_results.main() == 0  # pending legs are shown, not failed


def test_a_rerun_keeps_the_rows_of_the_retired_variants(tmp_path: Path) -> None:
    """WARIANT, WSZYSTKIE and the sport coupons are no longer produced; their
    recorded rows are history a re-run of the day must not erase."""
    write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    db = write_db(tmp_path, [{"sofascore_event_id": 1, "market": "corners_total",
                              "subject": "", "line": 7.5, "direction": "OVER",
                              "outcome": "WIN"}])
    path = record_results.ledger_path(str(tmp_path))
    path.parent.mkdir(parents=True)
    old = [{"date": DATE, "variant": v, "total": {"settled": 1}}
           for v in ("wariant", "multi", "sport:hockey", "rule:cs2", "official")]
    path.write_text("".join(json.dumps(r) + "\n" for r in old), encoding="utf-8")
    record_results.record(str(tmp_path), DATE, db)
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert sorted(r["variant"] for r in rows) == [
        "multi", "official", "rule:cs2", "sport:hockey", "wariant"]
    [off] = [r for r in rows if r["variant"] == "official"]
    assert off["total"]["won"] == 1  # the coupon's own row is re-recorded
