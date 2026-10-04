"""Review round of 2026-09-30 (variants): one test per defect found."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cs2
from bet.sofa import sport_coupon as sc
from scripts.sofa import (
    audit_variants,
    record_results,
    run_sport_coupon,
    settle_multi_coupon,
)
from tests.sofa.test_multi_coupon import write_db
from tests.sofa.test_sport_coupon import hline, snap, total_pair, write_snaps

DATE = "2026-09-30"
AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def iso(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, at: datetime = AT, *extra: str
) -> Path:
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(run_sport_coupon, "now", lambda: at)
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE, "--sport", "hockey", *extra])
    assert run_sport_coupon.main() in (0, 1)
    return sc.day_dir(str(tmp_path), "hockey", DATE)


def test_a_torn_snapshot_line_is_skipped_and_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    old = write_snaps(tmp_path, "hockey", "2026-09-29", [])
    (old / "snapshots.jsonl").write_text('{"superbet_event_id": "x", "fetched', "utf-8")
    (old / "settled.json").write_text(json.dumps({"events": {}}), encoding="utf-8")
    # a torn line in the middle (a crash, then the next append) ...
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"half a line\n')
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("2", total_pair("2", 1.25, 3.80), AT - timedelta(minutes=4))],
    )
    # ... and an append still in progress at the end (no newline yet)
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"superbet_event_id": "3", "fetc')
    build(tmp_path, monkeypatch)
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    assert sorted(leg["superbet_event_id"] for leg in doc["legs"]) == ["1", "2"]
    assert doc["unreadable_snapshot_lines"] == 1
    # the unfinished last line is neither read nor counted: a replay after
    # it completes must not see a record the build never saw
    assert doc["snapshot_lines"][DATE] == 3


def test_a_night_game_belongs_to_one_days_coupon_only(tmp_path: Path) -> None:
    night = datetime(2026, 10, 1, 2, 0, tzinfo=UTC)  # 04:00 Warsaw, 10-01
    write_snaps(
        tmp_path,
        "hockey",
        "2026-10-01",
        [
            snap(
                "7",
                total_pair("7", 1.20, 4.20),
                night - timedelta(hours=1),
                kickoff=night,
            )
        ],
    )
    at = night - timedelta(minutes=50)
    for date, expect in (("2026-09-30", 1), ("2026-10-01", 0)):
        events, _ = sc.day_events(str(tmp_path), "hockey", date)
        counts: dict[str, int] = {}
        cands = sc.candidates(
            "hockey",
            events,
            at,
            sc.Rule(),
            counts,
            until=sc.day_end(date),
            since=sc.day_end(sc.prev_date(date)),
        )
        assert len({c["superbet_event_id"] for c in cands}) == expect, date
    assert counts.get("previous_days_window") == 1


def test_a_game_moved_forward_is_locked_not_dropped() -> None:
    printed = {
        "legs": [
            {
                **hline("1", 623, "total", "OVER", 1.2, 5.5),
                "kickoff_utc": iso(AT + timedelta(hours=6)),
                "match_name": "a",
            }
        ]
    }
    moved = {"1": iso(AT - timedelta(minutes=30))}
    assert sc.locked_legs(printed, AT) == []
    assert [x["superbet_event_id"] for x in sc.locked_legs(printed, AT, moved)] == ["1"]


def test_a_rebuild_names_what_it_no_longer_prints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    d = build(tmp_path, monkeypatch)
    # an hour later the price moved out of the rule
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.60, 2.30), AT + timedelta(minutes=55))],
    )
    build(tmp_path, monkeypatch, AT + timedelta(hours=1))
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    assert doc["legs"] == [] and [
        r["superbet_event_id"] for r in doc["replaced_legs"]
    ] == ["1"]


def test_team_kills_never_reach_a_coupon_it_could_not_grade() -> None:
    lines = [
        cs2.Cs2Line("9", "team_kills", 1, "NiP", 70.5, s, o).as_dict()
        for s, o in (("OVER", 1.20), ("UNDER", 4.20))
    ]
    counts: dict[str, int] = {}
    events = sc.latest_events("cs2", [snap("9", lines, AT - timedelta(minutes=5))])
    assert sc.candidates("cs2", events, AT, sc.Rule(), counts) == []
    assert counts["ungradeable_family"] == 2


def test_a_negative_margin_group_is_no_price() -> None:
    assert sc.side_filter(0.8, 1.30, -0.02, sc.Rule()) == "NEGATIVE_MARGIN"


def test_a_veto_with_an_unknown_key_matches_nothing() -> None:
    leg = {**hline("1", 623, "total", "OVER", 1.2, 5.5)}
    assert sc.veto_matches({"superbet_event_id": "1"}, leg)
    typo = {"superbet_event_id": "1", "famliy": "total"}
    assert not sc.veto_matches(typo, leg)
    assert sc.unmatched_vetoes([typo], [leg], {"1"}) == [typo]


def test_the_newest_record_wins_across_the_two_files(tmp_path: Path) -> None:
    ko = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(
                "5",
                total_pair("5", 1.20, 4.20, 5.5),
                AT - timedelta(hours=2),
                kickoff=ko,
            )
        ],
    )
    write_snaps(
        tmp_path,
        "hockey",
        "2026-10-01",
        [
            snap(
                "5",
                total_pair("5", 1.22, 4.00, 6.5),
                AT - timedelta(minutes=5),
                kickoff=ko,
            )
        ],
    )
    events, _ = sc.day_events(str(tmp_path), "hockey", DATE)
    assert events["5"].source_date == "2026-10-01"
    assert {k[3] for k in events["5"].sides} == {6.5}


def test_a_price_taken_after_the_real_start_is_not_counted() -> None:
    leg = {
        **hline("1", 623, "total", "OVER", 1.3, 5.5),
        "fair_p": 0.75,
        "team1": "A",
        "team2": "B",
        "kickoff_utc": iso(AT),
        "price_fetched_at_utc": iso(AT),
    }
    ev = {
        "state": "SETTLED",
        "t1_periods": [3, 2, 1],
        "t2_periods": [0, 0, 0],
        "t1_full": 6,
        "t2_full": 0,
        "overtime": False,
        "graded": [],
        "sofascore_start_utc": iso(AT - timedelta(minutes=5)),
    }
    [g] = sc.grade_coupon(
        {"sport": "hockey", "date": DATE, "legs": [leg]}, {DATE: {"events": {"1": ev}}}
    )
    assert g["outcome"] == "IN_PLAY_PRICE"


def test_a_locked_leg_is_checked_against_the_logged_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(
                "1",
                total_pair("1", 1.20, 4.20),
                AT - timedelta(minutes=5),
                kickoff=AT + timedelta(hours=1),
            )
        ],
    )
    d = build(tmp_path, monkeypatch)
    build(tmp_path, monkeypatch, AT + timedelta(minutes=50))  # leg 1 now locked
    assert audit_variants.audit_sport(str(tmp_path), "hockey", DATE) == []
    path = d / sc.COUPON_FILE
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["legs"][0]["locked"]
    doc["legs"][0]["odds"] = 3.5  # a "locked" leg nobody printed
    path.write_text(json.dumps(doc), encoding="utf-8")
    got = audit_variants.audit_sport(str(tmp_path), "hockey", DATE)
    assert any("locked leg not printed" in f for f in got)


def test_a_record_written_after_the_build_is_not_replayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    build(tmp_path, monkeypatch)
    # stamped before the build, written after it (run_shadow's batch write)
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("2", total_pair("2", 1.10, 6.00), AT - timedelta(seconds=20))],
    )
    assert audit_variants.audit_sport(str(tmp_path), "hockey", DATE) == []


def test_the_variant_is_graded_at_its_own_screen_price(tmp_path: Path) -> None:
    run = tmp_path / DATE
    run.mkdir(parents=True)
    (run / "09_screen_prices.json").write_text('{"3": 2.40}', encoding="utf-8")
    (run / "09_screen_prices_wariant.json").write_text('{"3": 3.10}', encoding="utf-8")
    db = write_db(tmp_path, [])
    _, standard = settle_multi_coupon.official_rows(str(tmp_path), DATE, db, "standard")
    _, wariant = settle_multi_coupon.official_rows(str(tmp_path), DATE, db, "wariant")
    assert (standard, wariant) == ({"3": 2.40}, {"3": 3.10})


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
    [g], _ = settle_multi_coupon.grade_confidence_positions([single], [], [other], {})
    assert g["outcome"] == "UNSETTLED"
    [g], _ = settle_multi_coupon.grade_confidence_positions([single], [], [], {})
    assert g["outcome"] == "PENDING"


def test_an_unfinished_measurement_day_reports_its_retryable_events(
    tmp_path: Path,
) -> None:
    d = sc.day_dir(str(tmp_path), "hockey", DATE)
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


def test_the_directory_lock_serialises_writers(tmp_path: Path) -> None:
    import fcntl

    d = tmp_path / "x"
    with sc.dir_lock(d):
        with (d / ".sport_coupon.lock").open("a") as fh, pytest.raises(BlockingIOError):
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with (d / ".sport_coupon.lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)  # released


def test_a_crash_in_a_ledger_or_settle_script_is_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa import settle_sport_coupon

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("x")

    monkeypatch.setattr(record_results, "record", boom)
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE])
    assert record_results.main() == 2
    monkeypatch.setattr(settle_multi_coupon, "settle_day", boom)
    monkeypatch.setattr("sys.argv", ["x", "--from", DATE, "--to", DATE])
    assert settle_multi_coupon.main() == 2
    monkeypatch.setattr(settle_sport_coupon, "settle_day", boom)
    assert settle_sport_coupon.main() == 2


def test_the_official_and_wariant_artifacts_are_audited(tmp_path: Path) -> None:
    import os

    from tests.sofa.test_multi_coupon import official_single, write_official

    run = write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    assert audit_variants.audit_confidence(str(tmp_path), DATE, "standard") == []
    conf = run / "08_confidence.json"
    doc = json.loads(conf.read_text(encoding="utf-8"))
    doc.update(confidence_floor=0.70, min_ev=None, max_overround=0.105)
    doc["singles"][0].update(confidence=0.69, offered_odds=1.40, overround=0.12)
    t = conf.stat().st_mtime
    conf.write_text(json.dumps(doc), encoding="utf-8")
    os.utime(conf, (t, t))
    got = audit_variants.audit_confidence(str(tmp_path), DATE, "standard")
    assert any("below floor" in f for f in got) and any("margin" in f for f in got)
    # a WARIANT printed at confidence x odds under its tolerance
    var = dict(
        doc, profile="wariant", confidence_floor=0.65, min_ev=0.90, max_overround=0.15
    )
    var["singles"] = [
        dict(doc["singles"][0], confidence=0.66, offered_odds=1.30, overround=0.14)
    ]
    (run / "08_confidence_wariant.json").write_text(json.dumps(var), encoding="utf-8")
    got = audit_variants.audit_confidence(str(tmp_path), DATE, "wariant")
    assert any("< 0.9" in f for f in got)
    assert any("KUPON_2026-09-30_WARIANT.pdf missing" in f for f in got)
    # the official PDF older than its artifact prints another build
    os.utime(run / f"KUPON_{DATE}.pdf", (t - 100, t - 100))
    got = audit_variants.audit_confidence(str(tmp_path), DATE, "standard")
    assert any("prints another build" in f for f in got)


# --- the scenarios named in review round 2 (2026-09-30) ----------------------------


def test_run_sport_coupon_builds_and_writes_under_the_directory_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager

    seen: list[tuple[str, Path]] = []
    real = sc.dir_lock

    @contextmanager
    def spy(directory: Path) -> Any:
        seen.append(("enter", directory))
        with real(directory):
            yield
        seen.append(("exit", directory))

    monkeypatch.setattr(sc, "dir_lock", spy)
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    real_write = run_sport_coupon.write_outputs

    def write_inside(*a: Any, **k: Any) -> Any:
        # the JSON/PDF are written while the lock is held
        assert seen and seen[-1][0] == "enter"
        return real_write(*a, **k)

    monkeypatch.setattr(run_sport_coupon, "write_outputs", write_inside)
    build(tmp_path, monkeypatch)
    d = sc.day_dir(str(tmp_path), "hockey", DATE)
    assert ("enter", d) in seen and seen[-1] == ("exit", d)


def test_run_multi_coupon_reads_each_sport_under_its_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager

    from bet.sofa import multi_coupon as mc
    from tests.sofa.test_multi_coupon import sport_leg, write_sport

    write_sport(tmp_path, "hockey", [sport_leg("1", 1.2, 0.8)])
    seen: list[Path] = []
    real = sc.dir_lock

    @contextmanager
    def spy(directory: Path) -> Any:
        seen.append(directory)
        with real(directory):
            yield

    monkeypatch.setattr(sc, "dir_lock", spy)
    doc, why = mc.sport_source(str(tmp_path), "hockey", DATE, AT)
    assert doc is not None and why is None
    assert seen == [sc.day_dir(str(tmp_path), "hockey", DATE)]


def test_a_second_build_waits_for_the_first(tmp_path: Path) -> None:
    import threading
    import time

    d = tmp_path / "hockey"
    order: list[str] = []
    with sc.dir_lock(d):

        def second() -> None:
            with sc.dir_lock(d):
                order.append("second")

        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.2)
        order.append("first-done")
    t.join(timeout=5)
    assert order == ["first-done", "second"]


def test_two_sequential_builds_the_second_locks_the_firsts_started_leg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(
                "1",
                total_pair("1", 1.20, 4.20),
                AT - timedelta(minutes=5),
                kickoff=AT + timedelta(minutes=40),
            ),
            snap(
                "2",
                total_pair("2", 1.22, 4.00),
                AT - timedelta(minutes=5),
                kickoff=AT + timedelta(hours=5),
            ),
        ],
    )
    d = build(tmp_path, monkeypatch)
    first = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    # half an hour later leg 1 is inside the kickoff margin; leg 2 re-priced
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(
                "2",
                total_pair("2", 1.25, 3.80),
                AT + timedelta(minutes=25),
                kickoff=AT + timedelta(hours=5),
            )
        ],
    )
    build(tmp_path, monkeypatch, AT + timedelta(minutes=30))
    second = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    by1 = {x["superbet_event_id"]: x for x in first["legs"]}
    by2 = {x["superbet_event_id"]: x for x in second["legs"]}
    assert by2["1"]["locked"] is True
    assert {k: v for k, v in by2["1"].items() if k != "locked"} == by1["1"]
    assert by2["2"]["odds"] == 1.25 and not by2["2"].get("locked")
    assert (
        second["locked"] == 1
        and second["previous_build_utc"] == first["created_at_utc"]
    )
    # and the audit proves the locked leg against the logged first build
    assert audit_variants.audit_sport(str(tmp_path), "hockey", DATE) == []


def test_a_torn_line_that_completes_before_the_audit_is_not_replayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    late = json.dumps(snap("2", total_pair("2", 1.10, 6.00), AT - timedelta(minutes=1)))
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(late[:40])  # the append in progress at build time
    build(tmp_path, monkeypatch)
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(late[40:] + "\n")  # it completes after the build
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    assert [x["superbet_event_id"] for x in doc["legs"]] == ["1"]
    assert audit_variants.audit_sport(str(tmp_path), "hockey", DATE) == []


def test_vetoes_changed_after_the_build_are_an_s4_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    d = build(tmp_path, monkeypatch)
    assert audit_variants.audit_sport(str(tmp_path), "hockey", DATE) == []
    (d / sc.VETOES_FILE).write_text(
        json.dumps({"vetoes": [{"superbet_event_id": "1", "reason": "late news"}]}),
        encoding="utf-8",
    )
    got = audit_variants.audit_sport(str(tmp_path), "hockey", DATE)
    assert any(f.startswith("S4") and "changed after the build" in f for f in got)


def test_a_build_after_the_cutover_must_carry_its_hash_and_replay_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    d = build(tmp_path, monkeypatch)
    path = d / sc.COUPON_FILE
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["created_at_utc"] >= audit_variants.REPLAY_CUTOVER
    for field in ("pdf_sha256", "snapshot_lines", "vetoes_applied"):
        stripped = {k: v for k, v in doc.items() if k != field}
        path.write_text(json.dumps(stripped), encoding="utf-8")
        got = audit_variants.audit_sport(str(tmp_path), "hockey", DATE)
        assert any(f"no {field}" in f for f in got), field


def test_a_truncated_snapshot_file_is_an_s5_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(str(i), total_pair(str(i), 1.20, 4.20), AT - timedelta(minutes=5))
            for i in range(3)
        ],
    )
    build(tmp_path, monkeypatch)
    lines = (d / "snapshots.jsonl").read_text(encoding="utf-8").splitlines(True)
    (d / "snapshots.jsonl").write_text("".join(lines[:1]), encoding="utf-8")
    got = audit_variants.audit_sport(str(tmp_path), "hockey", DATE)
    assert any("truncated or restored" in f for f in got)


def test_the_replay_applies_the_days_lower_window_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 03:00Z on D is 05:00 Warsaw - still D-1's night, so not D's leg
    early = datetime(2026, 9, 30, 3, 0, tzinfo=UTC)
    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            snap(
                "8",
                total_pair("8", 1.20, 4.20),
                early - timedelta(hours=1),
                kickoff=early,
            ),
            snap(
                "9",
                total_pair("9", 1.20, 4.20),
                early - timedelta(hours=1),
                kickoff=early + timedelta(hours=10),
            ),
        ],
    )
    d = build(tmp_path, monkeypatch, early - timedelta(minutes=50))
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    assert [x["superbet_event_id"] for x in doc["legs"]] == ["9"]
    assert doc["counts"]["previous_days_window"] == 1
    assert audit_variants.audit_sport(str(tmp_path), "hockey", DATE) == []


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
    from tests.sofa.test_multi_coupon import official_single, write_official

    write_official(tmp_path, [official_single(1, "corners_total", 1.30, 0.77)])
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE])
    assert record_results.main() == 2
    assert not record_results.ledger_path(str(tmp_path)).exists()


def test_a_row_filed_under_another_date_still_grades_the_leg(tmp_path: Path) -> None:
    from scripts.sofa import audit_settlement
    from tests.sofa.test_multi_coupon import official_single, write_official

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
    from tests.sofa.test_multi_coupon import official_single, write_official

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
    rows, lines, bad = sc.read_snapshots(path)
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


# --- review round 3 (2026-09-30): what is recorded, and how it exits ------------


def _hockey_day_with_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A built hockey coupon whose leg the measurement graded the other way."""
    from tests.sofa.test_multi_coupon import write_db

    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    d = build(tmp_path, monkeypatch)
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    leg = doc["legs"][0]
    measured = {
        k: leg[k]
        for k in (
            "superbet_event_id",
            "market_id",
            "family",
            "period",
            "subject",
            "line",
            "side",
            "odds",
        )
    }
    ev = {
        "state": "SETTLED",
        "t1_periods": [3, 2, 1],
        "t2_periods": [0, 0, 0],
        "t1_full": 6,
        "t2_full": 0,
        "overtime": False,
        "graded": [{**measured, "partner_odds": 4.2, "fair_p": 0.8, "outcome": "LOSS"}],
    }  # 6 goals: over 5.5 won - disagrees
    (d / "settled.json").write_text(json.dumps({"events": {"1": ev}}), encoding="utf-8")
    return write_db(tmp_path, [])


def test_a_mismatch_is_counted_recorded_and_fails_the_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa import settle_sport_coupon

    db = _hockey_day_with_mismatch(tmp_path, monkeypatch)
    rows = record_results.record(str(tmp_path), DATE, db)
    [sport] = [r for r in rows if r["variant"] == "sport:hockey"]
    assert sport["outcomes"] == {"MISMATCH": 1}
    monkeypatch.setenv("SOFA_DB_PATH", db)
    monkeypatch.setattr("sys.argv", ["x", "--date", DATE])
    assert record_results.main() == 1
    monkeypatch.setattr(
        "sys.argv", ["x", "--from", DATE, "--to", DATE, "--sport", "hockey"]
    )
    assert settle_sport_coupon.main() == 1


def test_pending_legs_are_shown_not_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa import settle_sport_coupon

    write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))],
    )
    build(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "sys.argv", ["x", "--from", DATE, "--to", DATE, "--sport", "hockey"]
    )
    assert settle_sport_coupon.main() == 0  # nothing settled yet: normal


def test_a_regrade_that_lowers_the_count_replaces_the_row(tmp_path: Path) -> None:
    from tests.sofa.test_multi_coupon import official_single, write_db, write_official

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
    d = sc.day_dir(str(tmp_path), "hockey", DATE)
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


def test_the_rule_is_recorded_on_a_settled_day_without_a_coupon(tmp_path: Path) -> None:
    from tests.sofa.test_sport_coupon import hline

    ko = AT - timedelta(days=1)
    d = write_snaps(
        tmp_path,
        "hockey",
        "2026-09-29",
        [
            snap(
                "1",
                [
                    hline("1", 623, "total", "OVER", 1.20, 5.5),
                    hline("1", 623, "total", "UNDER", 4.20, 5.5),
                ],
                ko - timedelta(hours=1),
                kickoff=ko,
            )
        ],
    )
    ev = {
        "state": "SETTLED",
        "t1_periods": [3, 2, 1],
        "t2_periods": [0, 0, 0],
        "t1_full": 6,
        "t2_full": 0,
        "overtime": False,
        "graded": [],
    }
    (d / "settled.json").write_text(json.dumps({"events": {"1": ev}}), encoding="utf-8")
    [rule] = record_results.rule_rows(str(tmp_path), "2026-09-29")
    assert rule["variant"] == "rule:hockey"
    assert (rule["total"]["settled"], rule["total"]["won"]) == (1, 1)


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
    assert "| official | 2 | 3 | 3 | 2 | 1 | -0.20 |" in text
    assert "| sport:hockey | 1 | 1 | 1 | 0 | 1 | -1.00 |" in text
    fam = "\n".join(audit_ledger.render(loaded, "sport:hockey"))
    assert "| total | 1 | 0 | -1.00 |" in fam and "official" not in fam


@pytest.mark.parametrize(
    "n, want",
    [
        (1, "1 weto nie pasuje"),
        (2, "2 weta nie pasują"),
        (4, "4 weta nie pasują"),
        (5, "5 wet nie pasuje"),
        (12, "12 wet nie pasuje"),
        (22, "22 weta nie pasują"),
    ],
)
def test_veto_count_is_proper_polish(n: int, want: str) -> None:
    assert run_sport_coupon.veto_count_pl(n) == want


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
    from tests.sofa.test_multi_coupon import official_single, write_official

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
